import os
import re
import sys
import requests
from PIL import Image
from io import BytesIO
from fuzzywuzzy import fuzz
from fuzzywuzzy import process
from requests.auth import HTTPBasicAuth
from azure.core.credentials import AzureKeyCredential
from azure.ai.documentintelligence import DocumentIntelligenceClient
from azure.ai.documentintelligence.models import AnalyzeResult
from azure.cognitiveservices.vision.customvision.prediction import CustomVisionPredictionClient
from msrest.authentication import ApiKeyCredentials
from azure.storage.blob import BlobServiceClient, BlobClient, ContainerClient

# Azure Document Intelligence configuration
DOCUMENT_ENDPOINT = "https://trial99.cognitiveservices.azure.com/"
DOCUMENT_KEY = ""

# Azure Custom Vision configuration
CUSTOM_VISION_ENDPOINT = "https://receiptclassifier-prediction.cognitiveservices.azure.com/"
PREDICTION_KEY = ""
PROJECT_ID = ""
PUBLISHED_NAME = "ReceiptClassifier-v2"

AZURE_STORAGE_ACCOUNT_NAME = ""
AZURE_STORAGE_ACCOUNT_KEY = ""
CONTAINER_NAME = ""

validation_list =[]

def get_access_token(api_url, client_id, client_secret):
    headers = {
        'Content-Type': 'application/x-www-form-urlencoded'
    }
    
    try:
        # Sending GET request with Basic Auth
        response = requests.get(api_url, headers=headers, auth=HTTPBasicAuth(client_id, client_secret))
        response.raise_for_status()  # Check if the request was successful
        token_data = response.json()
        # Return only the access token if available
        return token_data.get('access_token', None)
    except requests.exceptions.RequestException as e:
        #print(f"Error fetching access token: {e}")
        return None
    
# Initialize Azure Document Intelligence client
document_intelligence_client = DocumentIntelligenceClient(
    endpoint=DOCUMENT_ENDPOINT, credential=AzureKeyCredential(DOCUMENT_KEY)
)

# Initialize the Custom Vision prediction client
custom_vision_credentials = ApiKeyCredentials(in_headers={"Prediction-key": PREDICTION_KEY})
custom_vision_predictor = CustomVisionPredictionClient(CUSTOM_VISION_ENDPOINT, custom_vision_credentials)

req=[]
def get_transaction_detail(api_url, api_key):
    transaction_data = fetch_transaction_details(api_url, api_key)

    if transaction_data:
        total_amount = transaction_data.get("TotalAmount", "Not available")
        total_tax = transaction_data.get("TotalVAT", "Not available")
        invoice_number = str(transaction_data.get("ReceiptNumber", "Not available"))
        invoice_vendorname = (transaction_data.get("Seller", {}).get("Address", {}).get("Name", "Not available") )
        #print(f"ffffffff={invoice_vendorname}")
        
        if isinstance(invoice_number, str):  # Ensure it's a string
            invoice_number = "".join(char.upper() if char.isalpha() else char for char in invoice_number)

        return total_amount, total_tax, invoice_number, invoice_vendorname 
    
    return None, None, None  ,None# Return None values if fetching fails


def fetch_transaction_details(api_url, api_key):
    headers = {
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json'
    }
    
    try:
        response = requests.get(api_url, headers=headers)
        response.raise_for_status()
        return response.json()  # Assuming API returns JSON data
    except requests.exceptions.RequestException as e:
        print(f"Error fetching transaction details: {e}")
        return None
    
def format_price(price_dict):
    
    return "".join([f"{p}" for p in price_dict.values()])
'''

def identify_receipt_type(image):
    try:
        # Convert PIL image to raw bytes
        image_bytes = BytesIO()
        image.save(image_bytes, format='PNG')  # Ensure PNG format (or 'JPEG' if required)
        image_bytes = image_bytes.getvalue()

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
        print(f"Error: {e}")
        return None
'''

def check_missing_elements(validation_list, required_elements):
    # Set of validation list elements for faster lookup
    validation_set = set(validation_list)
    
    # Check for missing required elements
    missing_elements = [element for element in required_elements if element not in validation_set]
    
    if missing_elements:
        print(f"Missing required elements: {', '.join(missing_elements)}, Send for manual validation")
         
        sys.exit()
    else:
        print("------All required elements are present. ") 
        for data in req:
            print(data)
        print("------Proceed to VALIDATION.")
        


'''subtotal_value = subtotal.get('valueCurrency').get('amount') if subtotal else None
                tax_value = tax.get('valueCurrency').get('amount') if tax else None
                total_value = invoice_total.get('valueCurrency').get('amount') if invoice_total else None'''
def check_receipt_correctness(subtotal_value, subtotal_v, tax_value, tax_v, total_value, total_v):
    if None in (subtotal_value, subtotal_v, tax_value, tax_v, total_value, total_v):
        print("Error: One or more extracted values are None. Check OCR extraction.")
        return False  # Or log the issue instead of proceeding
    
    return abs(subtotal_value - subtotal_v) < 0.01 and \
           abs(tax_value - tax_v) < 0.01 and \
           abs(total_value - total_v) < 0.01


    
def process_receipt(image):
    # Identify the receipt type (if needed)
    
    #invoice_type = identify_receipt_type(image) 
    # Convert the image to bytes
    img_byte_arr = BytesIO()
    image.save(img_byte_arr, format="png")
    img_byte_arr.seek(0) 
    # Reset the pointer to the beginning of the byte stream

    # Call the Document Intelligence API with the image as bytes
    poller = document_intelligence_client.begin_analyze_document(
        "prebuilt-invoice", body=img_byte_arr, locale="en-AE", content_type="application/octet-stream"
    )
    invoices: AnalyzeResult = poller.result()

    # Get the raw text of the receipt
    raw_text = invoices.content
    
    trn_number = extract_trn(raw_text)
    if trn_number:
        print(f"Extracted TRN Number: {trn_number}")
        validation_list.append('TRN number')
        req.append(f"Extracted TRN Number: {trn_number}")
    else:
        print("No TRN Number found in the receipt.")
    
    
    
    if "TAX INVOICE" in raw_text.upper():
        
        
        tax_invoice = True
        validation_list.append('TAX INVOICE')
        print("The receipt contains the word 'TAX INVOICE'.")
        req.append("The receipt contains the word 'TAX INVOICE'.")
    else:
        raw1 = raw_text.split("\n")
        clean_raw1 = [line.strip().replace(" ", "").upper() for line in raw1]

            #best_match = process.extractOne(invoice_number_detail_strb, clean_raw, scorer=fuzz.token_set_ratio)
        top_match1 = process.extractOne("TAX INVOICE", clean_raw1, scorer=fuzz.ratio)
        print(top_match1)
        if top_match1 and top_match1[1] > 80:  # Confidence threshold (adjust as needed)
            validation_list.append('TAX INVOICE')
            print("The receipt contains the word 'TAX INVOICE'.")
            req.append("The receipt contains the word 'TAX INVOICE'.")
            
        else:
            tax_invoice = None
            print("The word 'TAX INVOICE' is not found in the receipt.")
      
        
    required_elements = [
        'TRN number', 'TAX INVOICE', 'Vendor name', 'Invoice date', 
        'Invoice total', 'Subtotal', 'Total tax'
    ]

    if invoices.documents:
        for idx, invoices in enumerate(invoices.documents):
            print(f"--------Analysis of receipt #{idx + 1}--------")
            #print(f"Receipt type (from OCR): {receipt.doc_type if receipt.doc_type else 'N/A'}")
            #print(f"Receipt type (from classifier): {invoice_type}")
            #print(receipt.fields)
            if invoices.fields:
                vendor_name = invoices.fields.get("VendorName")
                if vendor_name:
                    
                    validation_list.append('Vendor name')
                    print(f"Vendor Name: {vendor_name.get('content').strip()} has confidence: {vendor_name.get('confidence')}")
                    req.append(f"Vendor Name: {vendor_name.get('content').strip()}")
                 
                else:
                    raw11 = raw_text.split("\n")
                    clean_raw11 = [line.strip().replace(" ", "").upper() for line in raw11]
                    
                    #best_match = process.extractOne(invoice_number_detail_strb, clean_raw, scorer=fuzz.token_set_ratio)
                    top_match11 = process.extractOne(invoice_vendorname, clean_raw11, scorer=fuzz.ratio)
                    print(top_match11)
                    if top_match11 and top_match11[1] > 50:  # Confidence threshold (adjust as needed)
                        validation_list.append('Vendor name')
                        print(f"Vendor Name: {top_match11}")
                        req.append(f"Vendor Name: {top_match11}")
                    
        
                    
                vendor_address = invoices.fields.get("VendorAddress")
                
                
                if vendor_address:
                    
                    print(
                        f"Vendor Address: {vendor_address.get('content').strip()} has confidence: {vendor_address.get('confidence')}"
                        )
                customer_name = invoices.fields.get("CustomerName")
                
                if customer_name:
                    
                    print(
                        f"Customer Name: {customer_name.get('content').strip()} has confidence: {customer_name.get('confidence')}")
                              
                    
                customer_address_recipient = invoices.fields.get("CustomerAddressRecipient")
                if customer_address_recipient:
                    print(
                        f"Customer Address Recipient: {customer_address_recipient.get('content').strip()} has confidence: {customer_address_recipient.get('confidence')}"
                    )
                invoice_id = invoices.fields.get("InvoiceId")
                invoice_num =""
                if invoice_id:
                    #validation_list.append('Invoice id')
                    invoice_num = str(invoice_id.get('content'))
                    if isinstance(invoice_num, str):  # Ensure it's a string
                        invoice_num = "".join(char.upper() if char.isalpha() else char for char in invoice_num)
                        print(f"invoice id:{invoice_num}")
                    #req.append(f"Invoice Id: {invoice_num}")
                invoice_date = invoices.fields.get("InvoiceDate")
                if invoice_date:
                    validation_list.append('Invoice date')
                    print(
                        f"Invoice Date: {invoice_date.get('content')} has confidence: {invoice_date.get('confidence')}"
                    )  
                    req.append(f"Invoice Date: {invoice_date.get('content')}")
                due_date = invoices.fields.get("DueDate")
                if due_date:
                    print(f"Due Date: {due_date.get('content')} has confidence: {due_date.get('confidence')}")
                purchase_order = invoices.fields.get("PurchaseOrder")
                if purchase_order:
                    print(
                        f"Purchase Order: {purchase_order.get('content')} has confidence: {purchase_order.get('confidence')}"
                    )
                billing_address = invoices.fields.get("BillingAddress")
                if billing_address:
                    print(
                        f"Billing Address: {billing_address.get('content')} has confidence: {billing_address.get('confidence')}"
                    )
                billing_address_recipient = invoices.fields.get("BillingAddressRecipient")
                if billing_address_recipient:
                    print(
                        f"Billing Address Recipient: {billing_address_recipient.get('content')} has confidence: {billing_address_recipient.get('confidence')}"
                    )
                shipping_address = invoices.fields.get("ShippingAddress")
                if shipping_address:
                    print(
                        f"Shipping Address: {shipping_address.get('content').strip()} has confidence: {shipping_address.get('confidence')}"
                    )
                shipping_address_recipient = invoices.fields.get("ShippingAddressRecipient")
                if shipping_address_recipient:
                    print(
                        f"Shipping Address Recipient: {shipping_address_recipient.get('content').strip()} has confidence: {shipping_address_recipient.get('confidence')}"
                    )
                print("Invoice items:")
                items = invoices.fields.get("Items")
                if items:
                    for idx, item in enumerate(items.get("valueArray")):
                        print(f"...Item #{idx + 1}")
                        item_details = item.get("valueObject")  # Fetch item details once
                        if item_details:  # Ensure item_details is not None
                            # List of attributes to extract
                            attributes = {
                                "Description": "Description",
                                "Quantity": "Quantity",
                                "Unit": "Unit",
                                "UnitPrice": "Unit Price",
                                "ProductCode": "Product Code",
                                "Date": "Date",
                                "Tax": "Tax",
                                "Amount": "Amount",
                            }
                            # Iterate through each attribute and print values safely
                            for key, label in attributes.items():
                                value = item_details.get(key)
                                if value:
                                    print(f"......{label}: {value.get('content')} has confidence: {value.get('confidence')}")
                                else:
                                    print(f"......{label} not available.")

                else:
                    print("......Item details not available.")

                
                print("--------------------------------------")
                
                
                def extract_numeric_value(text):
                    """Converts the string to a float, ensuring the last special character is a decimal point."""
                    text = str(text)
                    # If there's a comma in the number, replace the last one with a decimal point
                    if ',' in text:
                        # Split by comma and check if it's likely a decimal
                        parts = text.rsplit(',', 1)  # Only split the last comma
                        if len(parts) > 1 and re.match(r'\d{2}$', parts[1]):  # if the part after comma has 2 digits
                            text = text.replace(',', '.')  # Replace all commas with decimal
                        else:
                            text = text.replace(',', '')  # Remove all commas if not part of the decimal
                    # Now ensure the last special character is a decimal point
                    if '.' in text:
                        parts = text.rsplit('.', 1)  # Split by last dot
                        if len(parts) > 1 and re.match(r'\d{2}$', parts[1]):  # if the part after dot has 2 digits
                            text = parts[0] + '.' + parts[1]  # Keep only the first two digits after decimal
                    try:
                        return float(text)
                    except ValueError:
                        return None  # Return None if conversion fails

                
                def validate_missing_values(subtotal_value, tax_value, total_value, raw_text, total_amount_detail, total_tax_detail): 
                    try:
                        total_amount_detail = float(total_amount_detail)
                    except ValueError:
                        print(f"Error: Invalid value for total_amount_detail: {total_amount_detail}")
                        total_amount_detail = 0.0  # Handle as needed

                    try:
                        total_tax_detail = float(total_tax_detail)
                    except ValueError:
                        print(f"Error: Invalid value for total_tax_detail: {total_tax_detail}")
                        total_tax_detail = 0.0  # Handle as needed
                        
                    """Checks if missing values can be recovered from raw text before raising an error."""
                    missing_values_list = [("Subtotal", subtotal_value), ("Tax", tax_value), ("Total", total_value)]
                    missing_values = [name for name, value in missing_values_list if value is None]
                    print(f"\U0001F50D Searching raw OCR text for missing values...")
                    possible_matches = re.findall(r"[-+]?\d{1,5}(?:[.,]\d{4})*[.,]\d+", raw_text)
                    # Check if we can recover the Total Value
                    if total_value is None or abs(total_value - total_amount_detail) >= 0.01:
                        for match in possible_matches:
                            extracted_value = extract_numeric_value(match)
                            if extracted_value and abs(extracted_value - total_amount_detail) < 0.01:  # Allow small rounding differences
                                total_value = extracted_value
                                print(f"✅ Recovered/Corrected Total Amount: {total_value}")
                                if "Total" in missing_values:
                                    missing_values.remove("Total")
                                break

                    # Check if we can recover the Tax Value
                    if tax_value is None or abs(tax_value - total_tax_detail) >= 0.01:
                        
                        for match in possible_matches:
                            extracted_value = extract_numeric_value(match)
                            if extracted_value and abs(extracted_value - total_tax_detail) < 0.01:
                                tax_value = extracted_value
                                print(f"✅ Recovered Tax Amount: {tax_value}")
                                if "Tax" in missing_values:
                                    missing_values.remove("Tax")
                                break
                    
                    # If Subtotal is missing, recalculate
                    if subtotal_value is None:
                        if total_value is not None and tax_value is not None:
                            
                            subtotal_value = total_value - tax_value
                            print(f"✅ Calculated Subtotal: {subtotal_value}")
                            missing_values.remove("Subtotal")
                        
                    '''else:
                        subtotal_value = total_value - tax_value
                        print(f"✅ Calculated Subtotal: {subtotal_value}")
                        missing_values.remove("Subtotal")'''
                        
                    # Check if enough values are available to continue
                    if len(missing_values) >= 2:
                        print(f" Error: Missing {len(missing_values)} amount values ({', '.join(missing_values)}). Sending for manual validation.")
                        sys.exit()
                    return subtotal_value, tax_value, total_value
                
                def extract_num_val(value):
                    if isinstance(value, float):
                        return abs(value)  # Ensure positive value
                    if isinstance(value, str):  # Process only if it's a string
                        value = value.replace("\n", " ")  # Remove newlines
                        # Handle cases where OCR misreads a decimal point as an underscore
                        if "_" in value:
                            possible_fix = value.replace("_", ".")  # Convert underscores to decimal points
                            numeric_part = re.search(r"[-+]?\d*\.?\d+", possible_fix)
                        else:
                            numeric_part = re.search(r"[-+]?\d*\.?\d+", value)  # Extract numeric value

                        return abs(float(numeric_part.group())) if numeric_part else None  # Ensure positive value
                    return None



                
                
                #print(raw_text)
                invoice_total = invoices.fields.get("InvoiceTotal")
                
                subtotal = invoices.fields.get("SubTotal")
                total_tax = invoices.fields.get("TotalTax")
                
                total_value = extract_num_val(invoice_total.get('valueCurrency', {}).get('amount', '')) if invoice_total else None
                subtotal_value =extract_num_val(subtotal.get('valueCurrency', {}).get('amount', '')) if subtotal else None
                tax_value = extract_num_val(total_tax.get('content', '')) if total_tax else None
                print(f"ocr={total_value,tax_value,subtotal_value}")                
                
                total_amount_td = total_amount_detail

                total_tax_td = total_tax_detail
                print(f"td={total_tax_td,total_amount_td}")
                

                
                subtotal_conf = subtotal.get("confidence") if subtotal else None
                tax_conf = total_tax.get("confidence") if total_tax else None
                total_conf = invoice_total.get("confidence") if invoice_total else None 
                
            
                
                subtotal_value, tax_value, total_value = validate_missing_values(subtotal_value, tax_value, total_value, raw_text, total_amount_td, total_tax_td)

                if total_value:
                    validation_list.append('Invoice total')
                    #total_value = extract_numeric_value(invoice_total.get('valueCurrency', {}).get('amount', '')) if invoice_total else None    
                          
                    print(f"Invoice Total: {total_value}AED"+ (f" has confidence: {total_conf}" if total_conf is not None else ""))
                    req.append(f"Invoice Total: {total_value} AED")
                                
                if subtotal_value:
                    validation_list.append('Subtotal')
                    #subtotal_value = extract_numeric_value(subtotal.get('valueCurrency', {}).get('amount', '')) if subtotal else None
                    
                    print(f"Subtotal: {subtotal_value}AED "+ (f" has confidence: {subtotal_conf}" if subtotal_conf is not None else ""))
                    req.append(f"Subtotal: {subtotal_value} AED")
                            
                if tax_value:
                    validation_list.append('Total tax')
                    #tax_value = extract_numeric_value(total_tax.get('content', '')) if total_tax else None
                    
                    print(f"Total Tax: {tax_value}AED "+ (f" has confidence: {tax_conf}" if tax_conf is not None else ""))
                    req.append(f"Total Tax: {tax_value} AED")
                
                

                previous_unpaid_balance = invoices.fields.get("PreviousUnpaidBalance")
                if previous_unpaid_balance:
                    print(
                        f"Previous Unpaid Balance: {previous_unpaid_balance.get('content')} has confidence: {previous_unpaid_balance.get('confidence')}"
                    )
                amount_due = invoices.fields.get("AmountDue")
                if amount_due:
                    print(f"Amount Due: {amount_due.get('content')} has confidence: {amount_due.get('confidence')}")
                service_start_date = invoices.fields.get("ServiceStartDate")
                if service_start_date:
                    print(
                        f"Service Start Date: {service_start_date.get('content')} has confidence: {service_start_date.get('confidence')}"
                    )
                service_end_date = invoices.fields.get("ServiceEndDate")
                if service_end_date:
                    print(
                        f"Service End Date: {service_end_date.get('content')} has confidence: {service_end_date.get('confidence')}"
                    )
                service_address = invoices.fields.get("ServiceAddress")
                if service_address:
                    print(
                        f"Service Address: {service_address.get('content')} has confidence: {service_address.get('confidence')}"
                    )
                service_address_recipient = invoices.fields.get("ServiceAddressRecipient")
                if service_address_recipient:
                    print(
                        f"Service Address Recipient: {service_address_recipient.get('content')} has confidence: {service_address_recipient.get('confidence')}"
                    )
                remittance_address = invoices.fields.get("RemittanceAddress")
                if remittance_address:
                    print(
                        f"Remittance Address: {remittance_address.get('content')} has confidence: {remittance_address.get('confidence')}"
                    )
                remittance_address_recipient = invoices.fields.get("RemittanceAddressRecipient")
                if remittance_address_recipient:
                    print(
                        f"Remittance Address Recipient: {remittance_address_recipient.get('content')} has confidence: {remittance_address_recipient.get('confidence')}"
                    )
                print("------------------------------------------------------------------------")     
                #print(validation_list)
                
                #cleaned_data = [item.replace('\n', ' ') if isinstance(item, str) else item for item in validation_list]
                check_missing_elements(validation_list, required_elements)
                
                print("--------------------------------Calculation Check-------------------------------")
                

                
                    
                # Initialize the variables
                total_v = None
                subtotal_v = None
                tax_v = None
                    
                if tax_value is not None and total_value is not None:
                    subtotal_v = total_value - tax_value  # Calculate subtotal
                   
                if subtotal_value is not None and total_value is not None:
                    tax_v = total_value - subtotal_value  # Calculate tax
                        
                if subtotal_value is not None and tax_value is not None:
                    total_v = subtotal_value + tax_value  # Calculate total

                # Check if total_v, subtotal_v, and tax_v have been calculated
                if total_v is not None and subtotal_v is not None and tax_v is not None:
                    # Print calculated values
                    print(f"Invoice Total: {round(total_v, 2)} AED")
                    print(f"Subtotal Total: {round(subtotal_v, 2)} AED")
                    print(f"Tax Total: {round(tax_v, 2)} AED")
                    
                        # Validate receipt correctness
                    is_correct = check_receipt_correctness(subtotal_value, subtotal_v, tax_value, tax_v, total_value, total_v)
                    
                    if is_correct:
                        print("Receipt values are correct:", is_correct)
                    else:
                        print("After Calculation Check, Receipt values are incorrect:", is_correct, ". Send for manual validation.")
                else:
                    print("Error: One or more required values (total_v, subtotal_v, tax_v) are missing.")

       
                print("-------------------------DemoValidation-----------------------------------")    
                
                demo_validation(total_amount_detail,total_tax_detail, total_value,tax_value,invoice_number_detail,invoice_num, raw_text)

def extract_trn(raw_text):
    # Define a regex pattern for TRN (adjust this pattern to match the TRN format in your region)
    trn_pattern = r"\b1\d{13,14}3\b"  # Example: 15-digit TRN number
    matches = re.findall(trn_pattern, raw_text)
    #print(matches)
    if matches:
        
        return matches[0]  # Return the first match (if there are multiple matches, handle accordingly)
    else:
        raw2 = raw_text.split("\n")
        clean_raw2 = [line.strip().replace(" ", "").upper() for line in raw2]
        cleaned_text = " ".join(clean_raw2)
            
        number_pattern = r"\b\d{14,15}\b"  # Adjust to match the length of TRN-like numbers
        number_matches = re.findall(number_pattern,cleaned_text)
        if number_matches:
            # Use fuzzy matching to find the closest match from the regex number matches
            best_number_match = process.extractOne(number_matches[0], clean_raw2, scorer=fuzz.ratio)
            if best_number_match and best_number_match[1] > 80:
                return best_number_match[0]
    return None
def demo_validation(total_amount_detail, total_tax_detail, total_value, tax_value, invoice_number_detail, invoice_num, raw_text):
    approved = True 
    unmatch = []
    details_mismatch = {}
    tolerance = 0.5  # Allowed tolerance for numerical values
    fuzzy_threshold = 80 # Threshold for fuzzy string matching
    jaccard_threshold=0.7

    if tax_value is not None and total_tax_detail is not None:
        if total_tax_detail not in [0.0, "0.0", 'Not available']:
            tolerance = 0.5  
            try:
                total_tax_detail = float(total_tax_detail)
                tax_value = float(tax_value)
            except ValueError:
                print("Error: Invalid numerical values for total tax comparison.")
                approved = False
                unmatch.append("Total Tax")
                details_mismatch["Total Tax"] = f"TD: {total_tax_detail}, OCR: {tax_value}"
                         
            if  total_tax_detail == tax_value or total_tax_detail < total_value or abs(total_tax_detail - tax_value) <= tolerance:
                print("The tax value is accurate")
                print(f"TD: {total_tax_detail}")
                print(f"OCR: {tax_value}")
            else:
                print("The total tax from the invoice and the transaction details are not the same")
                approved = True
                unmatch.append("Total Tax")
                details_mismatch["Total Tax"] = f"TD: {total_tax_detail}, OCR: {tax_value}"
                print(f"TD: {total_tax_detail}")
                print(f"OCR: {tax_value}")
        else:
            print("Total tax detail is either '0.0' or 'Not available'. Cannot proceed.")
            approved = False
            unmatch.append("Total Tax")
            details_mismatch["Total Tax"] = f"TD: {total_tax_detail}, OCR: {tax_value}"

    if total_value is not None and total_amount_detail is not None:
        if total_amount_detail not in [0.0, "0.0", 'Not available']:
            tolerance = 0.5  
            try:
                total_amount_detail = float(total_amount_detail)
                total_value = float(total_value)
            except ValueError:
                print("Error: Invalid numerical values for total amount comparison.")
                approved = False
                unmatch.append("Total Amount")
                details_mismatch["Total Value"] = f"TD: {total_amount_detail}, OCR: {total_value}"
                         
            if  total_amount_detail == total_value or total_amount_detail < total_value or abs(total_amount_detail - total_value) <= tolerance:
                print("The total value is accurate")
                print(f"TD: {total_amount_detail}")
                print(f"OCR: {total_value}")
            else:
                print("The total value from the invoice and the transaction details are not the same")
                approved = False
                unmatch.append("Total Amount")
                details_mismatch["Total Value"] = f"TD: {total_amount_detail}, OCR: {total_value}"
                print(f"TD: {total_amount_detail}")
                print(f"OCR: {total_value}")
        else:
            print("Total amount detail is either '0.0' or 'Not available'. Cannot proceed.")
            approved = False
            unmatch.append("Total Amount")
            details_mismatch["Total Value"] = f"TD: {total_amount_detail}, OCR: {total_value}"
            
    if invoice_num is not None and invoice_number_detail is not None:
        
        invoice_num_strb = str(invoice_num)
        invoice_number_detail_strb = str(invoice_number_detail)
        
        print(f"Before processing: {invoice_num_strb, invoice_number_detail_strb}")

        # Function to clean invoice numbers
        def remove_leading_zeros(invoice_number):
            return invoice_number.lstrip('0')

        def remove_special_characters(invoice_number):
            return re.sub(r'\W+', '', invoice_number).replace("\n", "")
        
        def clean_invoice_number(invoice_number):
            # Remove special characters and leading zeros
            return remove_leading_zeros(remove_special_characters(invoice_number))
        def split_and_clean(invoice_number):
            
            """ Split invoice number on newlines and clean each part. """
            return invoice_number.split('\n')
        
          # Splitting on spaces & newlines
            

        # Apply different cleaning methods
        invoice_num_str_lead = remove_leading_zeros(invoice_num_strb)
        invoice_number_detail_str_lead = remove_leading_zeros(invoice_number_detail_strb)

        invoice_num_str_special = remove_special_characters(invoice_num_strb)
        invoice_number_detail_str_special = remove_special_characters(invoice_number_detail_strb)

        invoice_num_str_clean = clean_invoice_number(invoice_num_strb)
        invoice_number_detail_str_clean = clean_invoice_number(invoice_number_detail_strb)
        
        invoice_num_str_split = split_and_clean(invoice_num_strb)
        print(invoice_num_str_split)
        
        #invoice_number_detail_split = split_and_clean(invoice_number_detail_strb)
        

        print(f"Leading Zeros Removed: {invoice_num_str_lead, invoice_number_detail_str_lead}")
        print(f"Special Characters Removed: {invoice_num_str_special, invoice_number_detail_str_special}")
        print(f"Fully Cleaned: {invoice_num_str_clean, invoice_number_detail_str_clean}")
        
        def jaccard_similarity(str1, str2):
            set1 = set(str1)
            set2 = set(str2)
            intersection = set1.intersection(set2)
            union = set1.union(set2)
            return len(intersection) / len(union) if union else 0.0
        
        def compare_and_check(raw_text, invoice_num_str, invoice_number_detail_str, label):
            if isinstance(raw_text, list):
                raw_text = " ".join(raw_text)
                
            if invoice_number_detail_str == invoice_num_str:
                print(f"{label} - The Invoice ID is accurate")
                print(f"TD: {invoice_number_detail_str}")
                print(f"OCR: {invoice_num_str}")
                return True  # Stop further checking if a match is found
            
                # Check if the invoice number is present in the raw text
            if fuzz.ratio(invoice_number_detail_str, invoice_num_str) >= fuzzy_threshold:
                print("Fuzzy match found for invoice number.")
                return True
            
            jaccard_score = jaccard_similarity(invoice_num_str, invoice_number_detail_str)
            if jaccard_score >= jaccard_threshold:
                print(f"{label} - Jaccard similarity match found (Score: {jaccard_score:.2f}).")
                return True
                
            if re.search(r"\b" + re.escape(invoice_number_detail_str) + r"\b", raw_text):
                print(f"{label} - The Invoice ID '{invoice_number_detail_str}' is found in the raw data. Approving the Invoice ID.")
                return True
            
            raw_text_cleaned = re.sub(r'\D', '', raw_text)  # Remove non-numeric characters from raw text
            invoice_number_cleaned = invoice_number_detail_str.lstrip('0').rstrip('0')  # Remove leading/trailing zeros
            
            if invoice_number_cleaned in raw_text_cleaned:
                print(f"{label} - The Invoice ID '{invoice_number_cleaned}' is found as a subset in the raw data. Approving the Invoice ID.")
                return True
            
            raw = raw_text.split("\n")
            clean_raw = [line.strip().replace(" ", "").upper() for line in raw]

            #best_match = process.extractOne(invoice_number_detail_strb, clean_raw, scorer=fuzz.token_set_ratio)
            top_match = process.extractOne(invoice_number_detail_str, clean_raw, scorer=fuzz.ratio)
            print(f"{top_match},{invoice_number_detail_str}")
            if top_match and top_match[1] > 70:  # Confidence threshold (adjust as needed)
                best_match_text = top_match[0]
                print(f"td:{invoice_number_detail_strb}, best match={best_match_text}")# Extract the matched string    
                return True

            return False  # Continue checking next level of cleaning
        
        
        #jaccard_score = jaccard_similarity(invoice_number_detail_strb, invoice_num_strb)
        # Step-by-step checking
        match_found = False
        if compare_and_check(raw_text, invoice_num_strb, invoice_number_detail_strb, "OG Values"):
            match_found = True  # Stop further checks if matched
        elif compare_and_check(raw_text, invoice_num_str_lead, invoice_number_detail_str_lead, "Leading Zeros Removed"):
            match_found = True  # Stop further checks if matched
        elif compare_and_check(raw_text, invoice_num_str_special, invoice_number_detail_str_special, "Special Characters Removed"):
            match_found = True # Stop further checks if matched
        elif compare_and_check(raw_text, invoice_num_str_clean, invoice_number_detail_str_clean, "Fully Cleaned"):
            match_found = True  # Stop further checks if matched
        else :
            match_found =False
            for i in invoice_num_str_split:
                print(f"td: {invoice_number_detail_strb}, ocr={i}")
                if compare_and_check(raw_text,i ,invoice_number_detail_strb,"Split and clean" ):
                    match_found = True
                    break
                if i.isdigit():
                    cleaned_inv_dtl_id =re.sub(r'[^0-9]+', '', invoice_number_detail_strb)
                    print(cleaned_inv_dtl_id)
                    if compare_and_check(raw_text,i ,cleaned_inv_dtl_id,"Split and cleanesttt" ):
                        match_found = True
                        break
            
                # Call your compare function with the best match
                '''if compare_and_check(clean_raw, invoice_number_detail_strb, best_match_text,"Top match"):
                    match_found = True'''
                
                    
                
                    
            if match_found:
                print("Match found, skipping rejection.")
            else:
                
                print("No match found, continue with other processing.")
        
        
                print("Invoice ID from invoice and transaction details are not the same.")
                approved = False
                unmatch.append("Invoice ID")
                details_mismatch["Invoice ID"] = f"TD: {invoice_number_detail_strb}, OCR: {invoice_num_strb}"
        
        
    if approved:
        print("APPROVED. Transaction details are matching") 
    else:
        print(f"REJECTED. {', '.join(unmatch)} details not matching", end=". ")

        print("; ".join([f"{key} Mismatch - {value}" for key, value in details_mismatch.items()]))


    sys.exit()

def new_func(invoice):
    items = invoice.fields.get("Items")
    return items



TRANSACTION_DETAILS = {
    "TotalAmount": "Not available",
    "TotalVAT": "Not available",
    "ReceiptNumber": "Not available",
    "Seller": {
        "Address": {
            "Name": "Not Available"  # Example Name, you can replace this dynamically
        }
    }
}              

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python3 testINvoice.py <invoice_image_path> <ChequeNumber>")
        sys.exit(1)

    # Get arguments from batch_processor.py
    guid = sys.argv[1]  # Now expects image path as the first argument
    cheque_number = sys.argv[2]  # Now expects cheque number as the second argument
    
    # Get access token
    api_url_token = "https://refund.planetpayment.ae/API/rest/oAuth2/Token"
    client_id = "Alby.Varughese"
    client_secret = "Albyalexi#123"
    access_token = get_access_token(api_url_token, client_id, client_secret)

    if not access_token:
        print("Failed to retrieve access token.")
        sys.exit(1)

    # Construct API URL with dynamic ChequeNumber
    api_url = f"https://refund.planetpayment.ae/API/rest/Refund/Cheque?ChequeNumber={cheque_number}"

    # Fetch transaction details
    total_amount, total_tax, invoice_number, invoice_vendorname = get_transaction_detail(api_url, access_token)

    if total_amount is not None:
        TRANSACTION_DETAILS["TotalAmount"] = total_amount
    if total_tax is not None:
        TRANSACTION_DETAILS["TotalVAT"] = total_tax
    if invoice_number is not None:
        TRANSACTION_DETAILS["ReceiptNumber"] = invoice_number
    if invoice_vendorname is not None:
        TRANSACTION_DETAILS["Seller"]["Address"]["Name"] = invoice_vendorname
    else:
        print("Error: Could not fetch transaction details.")
        sys.exit(1)

    # Store values in global variables for easier access
    total_amount_detail = TRANSACTION_DETAILS["TotalAmount"]
    total_tax_detail = TRANSACTION_DETAILS["TotalVAT"]
    invoice_number_detail = TRANSACTION_DETAILS["ReceiptNumber"]
    invoice_vendorname =TRANSACTION_DETAILS["Seller"]["Address"]["Name"]
        
    blob_service_client = BlobServiceClient(
        account_url=f"https://{AZURE_STORAGE_ACCOUNT_NAME}.blob.core.windows.net",
        credential=AZURE_STORAGE_ACCOUNT_KEY
    )
    container_client = blob_service_client.get_container_client(CONTAINER_NAME)
    
    # Define the blob name using the GUID (assuming the GUID is used to name the file in the storage)
    blob_name = f"{guid}"  # Modify if the file type is different (e.g., .png)
    blob_client = container_client.get_blob_client(blob_name)
    try:
        # Download the image data from Azure Blob Storage
        image_data = blob_client.download_blob().readall()
        
        # Open the image from the downloaded data
        image = Image.open(BytesIO(image_data))
        
    except Exception as e:
        print(f"Error: Unable to fetch the image for GUID {guid} from Blob Storage. {e}")
        sys.exit(1)


    # Process the invoice image
    result = process_receipt(image)  # Process receipt after fetching image
    print(f"{result}")  # Output used by batch_processor.py