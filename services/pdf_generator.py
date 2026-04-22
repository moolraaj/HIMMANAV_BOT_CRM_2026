# services/pdf_generator.py
import os
import requests
from datetime import datetime
from dotenv import load_dotenv

load_dotenv('.env')

ACCESS_TOKEN = os.getenv('ACCESS_TOKEN')
PHONE_NUMBER_ID = os.getenv('PHONE_NUMBER_ID')


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


def upload_pdf_to_whatsapp(pdf_path):
    """Upload PDF to WhatsApp Cloud API and get media ID"""
    try:
        url = f"https://graph.facebook.com/v18.0/{PHONE_NUMBER_ID}/media"

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
                print(f"❌ Upload failed: {response.text}")
                return None

    except Exception as e:
        print(f"❌ Upload error: {e}")
        return None


def send_pdf_via_whatsapp(to_phone, pdf_path, caption=""):
    """Send PDF file to WhatsApp user"""
    try:
        media_id = upload_pdf_to_whatsapp(pdf_path)

        if not media_id:
            return None

        url = f"https://graph.facebook.com/v18.0/{PHONE_NUMBER_ID}/messages"
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

        response = requests.post(url, headers=headers, json=data)

        if response.status_code == 200:
            print(f"✅ PDF sent successfully to {to_phone}")
            return response.json()
        else:
            print(f"❌ Failed to send PDF: {response.text}")
            return None

    except Exception as e:
        print(f"❌ Send PDF error: {e}")
        return None