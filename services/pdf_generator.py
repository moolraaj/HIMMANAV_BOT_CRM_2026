# services/pdf_generator.py
import os
import requests
import base64
from datetime import datetime
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.units import inch
from dotenv import load_dotenv

load_dotenv('.env')

ACCESS_TOKEN = os.getenv('ACCESS_TOKEN')
PHONE_NUMBER_ID = os.getenv('PHONE_NUMBER_ID')

def generate_package_pdf(package, user_info=None):
    """Generate PDF for package and return file path"""
    try:
        # Create PDFs directory if it doesn't exist
        os.makedirs("generated_pdfs", exist_ok=True)
        
        # Generate unique filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        pkg_name = package.get('package_name', 'Package')[:30]
        pkg_name_clean = "".join(c for c in pkg_name if c.isalnum() or c in (' ', '-', '_')).rstrip()
        filename = f"generated_pdfs/{pkg_name_clean}_{timestamp}.pdf"
        
        # Create PDF document
        doc = SimpleDocTemplate(filename, pagesize=letter)
        styles = getSampleStyleSheet()
        story = []
        
        # Custom styles
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=24,
            textColor=colors.HexColor('#2E7D32'),
            spaceAfter=30,
            alignment=1  # Center alignment
        )
        
        heading_style = ParagraphStyle(
            'CustomHeading',
            parent=styles['Heading2'],
            fontSize=16,
            textColor=colors.HexColor('#1565C0'),
            spaceAfter=12,
            spaceBefore=12
        )
        
        subheading_style = ParagraphStyle(
            'Subheading',
            parent=styles['Heading3'],
            fontSize=14,
            textColor=colors.HexColor('#FF6F00'),
            spaceAfter=8
        )
        
        # Title
        story.append(Paragraph(package.get('package_name', 'Travel Package'), title_style))
        story.append(Spacer(1, 0.2*inch))
        
        # Package Basic Info
        story.append(Paragraph(f"<b>💰 Price:</b> ₹{package.get('package_price', 'N/A')}", styles['Normal']))
        story.append(Spacer(1, 0.1*inch))
        
        # Destinations
        locations = package.get('locations', [])
        if locations:
            story.append(Paragraph(f"<b>📍 Destinations:</b> {', '.join(locations)}", styles['Normal']))
            story.append(Spacer(1, 0.1*inch))
        
        # User Info if provided
        if user_info:
            story.append(Paragraph("<b>👤 Customer Information</b>", subheading_style))
            if user_info.get('name'):
                story.append(Paragraph(f"Name: {user_info.get('name')}", styles['Normal']))
            if user_info.get('email'):
                story.append(Paragraph(f"Email: {user_info.get('email')}", styles['Normal']))
            if user_info.get('travel_dates'):
                story.append(Paragraph(f"Travel Dates: {user_info.get('travel_dates')}", styles['Normal']))
            if user_info.get('travelers'):
                story.append(Paragraph(f"Travelers: {user_info.get('travelers')}", styles['Normal']))
            story.append(Spacer(1, 0.2*inch))
        
        # Itinerary
        itinerary = package.get('itinerary', [])
        if itinerary:
            story.append(Paragraph("📅 <b>ITINERARY</b>", heading_style))
            for i, day in enumerate(itinerary, 1):
                title = day.get('title', f'Day {i}')
                desc = day.get('description', '')
                hotel = day.get('hotel', '')
                
                story.append(Paragraph(f"<b>Day {i}: {title}</b>", styles['Normal']))
                if desc:
                    # Clean HTML tags
                    import re
                    clean_desc = re.sub(r'<[^>]+>', '', desc)
                    story.append(Paragraph(clean_desc, styles['Normal']))
                if hotel:
                    story.append(Paragraph(f"<b>🏨 Hotel:</b> {hotel}", styles['Normal']))
                story.append(Spacer(1, 0.1*inch))
        
        # Activities
        activities = package.get('activities', [])
        if activities:
            story.append(Paragraph("🎯 <b>ACTIVITIES</b>", heading_style))
            for act in activities:
                story.append(Paragraph(f"• {act}", styles['Normal']))
            story.append(Spacer(1, 0.1*inch))
        
        # Vehicles
        vehicles = package.get('vehicles', [])
        if vehicles:
            story.append(Paragraph("🚗 <b>VEHICLES</b>", heading_style))
            for veh in vehicles:
                story.append(Paragraph(f"• {veh}", styles['Normal']))
            story.append(Spacer(1, 0.1*inch))
        
        # Hotels (from itinerary)
        hotels = []
        for day in itinerary:
            hotel = day.get('hotel')
            if hotel and hotel not in hotels:
                hotels.append(hotel)
        
        if hotels:
            story.append(Paragraph("🏨 <b>HOTELS</b>", heading_style))
            for hotel in hotels:
                story.append(Paragraph(f"• {hotel}", styles['Normal']))
            story.append(Spacer(1, 0.1*inch))
        
        # Inclusions
        inclusions = package.get('inclusion', [])
        if inclusions:
            story.append(Paragraph("✅ <b>WHAT'S INCLUDED</b>", heading_style))
            for inc in inclusions:
                story.append(Paragraph(f"• {inc}", styles['Normal']))
            story.append(Spacer(1, 0.1*inch))
        
        # Exclusions
        exclusions = package.get('exclusion', [])
        if exclusions:
            story.append(Paragraph("❌ <b>WHAT'S NOT INCLUDED</b>", heading_style))
            for exc in exclusions:
                story.append(Paragraph(f"• {exc}", styles['Normal']))
            story.append(Spacer(1, 0.1*inch))
        
        # Footer
        story.append(Spacer(1, 0.3*inch))
        story.append(Paragraph(
            "<i>Thank you for choosing us! For booking assistance, contact our support team.</i>",
            styles['Italic']
        ))
        story.append(Paragraph(
            f"<i>Generated on: {datetime.now().strftime('%d %B %Y %H:%M')}</i>",
            styles['Italic']
        ))
        
        # Build PDF
        doc.build(story)
        return filename
        
    except Exception as e:
        print(f"❌ PDF generation error: {e}")
        import traceback
        traceback.print_exc()
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
            
            headers = {
                'Authorization': f'Bearer {ACCESS_TOKEN}'
            }
            
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
        # First upload the PDF
        media_id = upload_pdf_to_whatsapp(pdf_path)
        
        if not media_id:
            return None
        
        # Send document message
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