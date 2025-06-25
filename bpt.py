import pandas as pd
import subprocess
import time
import os
import concurrent.futures
from PIL import Image
from io import BytesIO
from azure.storage.blob import BlobServiceClient
from msrest.authentication import ApiKeyCredentials
from azure.cognitiveservices.vision.customvision.prediction import CustomVisionPredictionClient
import sys

# Azure Blob Storage and Custom Vision configuration
CUSTOM_VISION_ENDPOINT = "https://receiptclassifier-prediction.cognitiveservices.azure.com/"
PREDICTION_KEY = ""
PROJECT_ID = ""
PUBLISHED_NAME = "ReceiptClassifier-v2"

BLOB_STORAGE_ACCOUNT_NAME = ""
BLOB_STORAGE_ACCOUNT_KEY = ""
CONTAINER_NAME = ""

# Initialize Azure Blob Service Client
# Initialize Custom Vision Client
credentials = ApiKeyCredentials(in_headers={"Prediction-key": PREDICTION_KEY})
custom_vision_predictor = CustomVisionPredictionClient(endpoint=CUSTOM_VISION_ENDPOINT, credentials=credentials)
blob_service_client = BlobServiceClient(
    account_url=f"https://{BLOB_STORAGE_ACCOUNT_NAME}.blob.core.windows.net",
    credential=BLOB_STORAGE_ACCOUNT_KEY
)
container_client = blob_service_client.get_container_client(CONTAINER_NAME)

# Function to retrieve image from Blob Storage
def get_image_from_blob(guid):
    try:
        # Define the blob name using the GUID (assuming the GUID is used to name the file in the storage)
        blob_name = f"{guid}"  # Adjust the file type if necessary
        blob_client = container_client.get_blob_client(blob_name)

        # Download the image data from Azure Blob Storage
        image_data = blob_client.download_blob().readall()
        
        # Open the image from the downloaded data
        image = Image.open(BytesIO(image_data))
        return image
    except Exception as e:
        print(f"Error: Unable to fetch the image for GUID {guid} from Blob Storage. {e}")
        sys.exit(1)
        return None

# Importing the identify_receipt_type function from testINvoice.py
'''
def identify_receipt_type(image):
    try:
        # Convert PIL image to raw bytes
        image_bytes = BytesIO()
        image.save(image_bytes, format='PNG')  # Ensure PNG format (or 'JPEG' if required)
        image_bytes = image_bytes.getvalue()

        # Assuming custom_vision_predictor.classify_image is set up in your testINvoice.py
        results = custom_vision_predictor.classify_image(PROJECT_ID, PUBLISHED_NAME, image_bytes)

        # Process predictions
        highest_probability = 0
        identified_type = None
        for prediction in results.predictions:
            if prediction.probability > highest_probability:
                highest_probability = prediction.probability
                identified_type = prediction.tag_name
                
        if identified_type:
            return identified_type
    except Exception as e:
        print(f"Error: yaya {e}")
        print("❌ All attempts to classify invoice type failed.")
    return "Unknown"'''


def process_single_entry(row):
    """Processes a single entry by running testINvoice.py and retrieving invoice type."""
    guid = row["GUID"]
    form_number = row["FormNumber"]
    start_time = time.time()

    print(f"🚀 Processing GUID: {guid}, FormNumber: {form_number}...")

    try:
        result = subprocess.run(
            ['python', 'testINvoice.py', str(guid), str(form_number)],
            capture_output=True, text=True, encoding='utf-8', errors='ignore'  # Ensure proper decoding
        )

        # Retrieve the image from Blob Storage
        image = get_image_from_blob(guid)
        if image is None:
            raise ValueError(f"Failed to retrieve image for GUID {guid}")
        def identify_receipt_type(image):
            try:
                # Convert PIL image to raw bytes
                image_bytes = BytesIO()
                image.save(image_bytes, format='PNG')  # Ensure PNG format (or 'JPEG' if required)
                image_bytes = image_bytes.getvalue()
                
                
                # Assuming custom_vision_predictor.classify_image is set up in your testINvoice.py
                results = custom_vision_predictor.classify_image(PROJECT_ID, PUBLISHED_NAME, image_bytes)

                # Process predictions
                highest_probability = 0
                identified_type = None
                for prediction in results.predictions:
                    if prediction.probability > highest_probability:
                        highest_probability = prediction.probability
                        identified_type = prediction.tag_name
                
                return identified_type
            except Exception as e:
                print(f"Error: yaya {e}")
                return None
            
        

        # Identify the invoice type
        invoice_type = identify_receipt_type(image)

        end_time = time.time()
        execution_time = end_time - start_time
        lines = result.stdout.strip().split('\n')
        last_line = lines[-1]
        second_last_line = lines[-2] if len(lines) > 1 else "No second last line"
        
        # Check if last_line contains "APPROVED", "REJECTED", or "Missing"
        if not any(word in last_line for word in ["APPROVED", "REJECTED", "Missing", "None"]):
            last_line = second_last_line + " " + last_line


        # Determine Decision
        decision = "APPROVED" if "APPROVED" in last_line else "REJECTED"

        print(f" ✅ {form_number} result: {last_line}")
        print(f" Execution time: {execution_time:.2f} seconds.")
        print(f" Invoice Type: {invoice_type if invoice_type else 'Unknown'}")

        return {
            "GUID": guid,
            "FormNumber": form_number,            
            "Invoice Type": invoice_type if invoice_type else "Unknown",
            "Start time": time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(start_time)),
            "End time": time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(end_time)),
            "Execution time (s)": f"{execution_time:.2f}",
            "Decision": decision,
            "Reason": last_line,
            }

    except Exception as e:
        print(f"❌ FormNumber {form_number}: {e}")
        return {
            "GUID": guid,
            "FormNumber": form_number,            
            "Invoice Type": "Unknown",
            "Start time": time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(start_time)),
            "End time": time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(time.time())),
            "Execution time (s)": "N/A",
            "Decision": "Rejected",
            "Reason": f"Failed: {e}",
            }

def process_csv(csv_file_path):
    if not csv_file_path.lower().endswith('.csv'):
        raise ValueError(f"The file {csv_file_path} is not a CSV file.")

    base_name = os.path.splitext(os.path.basename(csv_file_path))[0]
    output_file_path = f"{base_name}_res_test_newdate_attempt3.csv"

    df = pd.read_csv(csv_file_path, encoding='utf-8')  # Ensure proper encoding while reading CSV
    results = []

    # Use ThreadPoolExecutor for parallel execution of testINvoice.py
    num_workers = 5  # Run 5 processes in parallel
    with concurrent.futures.ThreadPoolExecutor(max_workers=num_workers) as executor:
        future_to_entry = {executor.submit(process_single_entry, row): row for _, row in df.iterrows()}
        
        for future in concurrent.futures.as_completed(future_to_entry):
            result = future.result()
            results.append(result)

            # Save intermediate results
            pd.DataFrame(results).to_csv(output_file_path, index=False)
            print(f"💾 Results successfully saved to: {output_file_path}")

    print("✅ All done! Processing complete.")

# Input CSV file path
csv_file_path = "20250303_receipts.csv"

# Process the CSV file
process_csv(csv_file_path)