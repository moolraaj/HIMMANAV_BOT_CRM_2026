# services/pdf_generator.py

import os
import requests
from datetime import datetime
from dotenv import load_dotenv
from database.database import get_whatsapp_config, get_all_active_whatsapp_numbers

load_dotenv('.env')

ACCESS_TOKEN = os.getenv('ACCESS_TOKEN')


def download_pdf_from_url(pdf_url, package_name):
    """
    Directly download PDF from URL
    """
    try:
        os.makedirs("generated_pdfs", exist_ok=True)
        
        pkg_name_clean = "".join(c for c in package_name[:30] if c.isalnum() or c in (' ', '-', '_')).rstrip()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"generated_pdfs/{pkg_name_clean}_{timestamp}.pdf"
        
        print(f"📥 Downloading PDF directly from: {pdf_url}")
        
        response = requests.get(pdf_url, timeout=30)
        
        if response.status_code == 200:
            with open(filename, 'wb') as f:
                f.write(response.content)
            
            print(f"✅ PDF downloaded and saved: {filename}")
            return filename
        else:
            print(f"❌ Failed to download PDF. Status: {response.status_code}")
            return None
            
    except Exception as e:
        print(f"❌ PDF download error: {e}")
        return None


def upload_pdf_to_whatsapp(pdf_path, sender_phone_number_id):
    """
    Upload PDF to WhatsApp Cloud API and get media ID
    Uses sender_phone_number_id to determine which number to upload from
    """
    try:
        # Get sender config from database
        sender_config = get_whatsapp_config(sender_phone_number_id)
        
        if not sender_config:
            print(f"❌ No config found for sender: {sender_phone_number_id}")
            # Try to get first active number as fallback
            active_numbers = get_all_active_whatsapp_numbers()
            if active_numbers:
                fallback_id = active_numbers[0]["phone_number_id"]
                print(f"⚠️ Using fallback sender: {fallback_id}")
                sender_config = get_whatsapp_config(fallback_id)
            else:
                print(f"❌ No active WhatsApp numbers found in database")
                return None
        
        url = f"https://graph.facebook.com/v18.0/{sender_config['phone_number_id']}/media"
        
        with open(pdf_path, 'rb') as f:
            files = {
                'file': (os.path.basename(pdf_path), f, 'application/pdf'),
                'messaging_product': (None, 'whatsapp'),
                'type': (None, 'application/pdf')
            }
            headers = {'Authorization': f'Bearer {ACCESS_TOKEN}'}
            response = requests.post(url, headers=headers, files=files)

            if response.status_code == 200:
                media_id = response.json().get('id')
                print(f"✅ PDF uploaded, Media ID: {media_id}")
                return media_id
            else:
                print(f"❌ Upload failed: {response.status_code} - {response.text}")
                return None

    except Exception as e:
        print(f"❌ Upload error: {e}")
        return None


def send_pdf_via_whatsapp(to_phone, pdf_path, caption="", sender_phone_number_id=None):
    """
    Send PDF file to WhatsApp user
    Args:
        to_phone: Recipient's phone number
        pdf_path: Path to PDF file
        caption: Optional caption text
        sender_phone_number_id: Which WhatsApp number to send FROM
    """
    try:
        # If no sender_id provided, get first active number from DB
        if not sender_phone_number_id:
            active_numbers = get_all_active_whatsapp_numbers()
            if active_numbers:
                sender_phone_number_id = active_numbers[0]["phone_number_id"]
                print(f"⚠️ No sender_id provided, using: {sender_phone_number_id}")
            else:
                print("❌ No active WhatsApp numbers found in database")
                return None
        
        # Upload PDF to WhatsApp
        media_id = upload_pdf_to_whatsapp(pdf_path, sender_phone_number_id)

        if not media_id:
            return None

        # Get sender config for message URL
        sender_config = get_whatsapp_config(sender_phone_number_id)
        if not sender_config:
            print(f"❌ No config found for sender: {sender_phone_number_id}")
            return None

        # Send the PDF message
        url = f"https://graph.facebook.com/v18.0/{sender_config['phone_number_id']}/messages"
        headers = {
            "Authorization": f"Bearer {ACCESS_TOKEN}",
            "Content-Type": "application/json"
        }

        data = {
            "messaging_product": "whatsapp",
            "to": to_phone,
            "type": "document",
            "document": {
                "id": media_id,
                "caption": caption or "📄 Your travel package details",
                "filename": os.path.basename(pdf_path)
            }
        }

        response = requests.post(url, headers=headers, json=data, timeout=30)

        if response.status_code == 200:
            print(f"✅ PDF sent successfully to {to_phone}")
            return response.json()
        else:
            print(f"❌ Failed to send PDF: {response.status_code} - {response.text}")
            return None

    except Exception as e:
        print(f"❌ Send PDF error: {e}")
        return None