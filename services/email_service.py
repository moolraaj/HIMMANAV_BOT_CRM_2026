import smtplib
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from dotenv import load_dotenv

load_dotenv('.env')

SMTP_HOST = os.getenv('SMTP_HOST', 'smtp.gmail.com')
SMTP_PORT = int(os.getenv('SMTP_PORT', 587))
SMTP_USER = os.getenv('SMTP_USER', 'raaj73906@gmail.com')
SMTP_PASSWORD = os.getenv('SMTP_PASSWORD', '')
FROM_EMAIL = os.getenv('FROM_EMAIL', 'noreply@gmail.com')
ADMIN_EMAIL = os.getenv('ADMIN_EMAIL', '')  # Add this to your .env file

def send_admin_booking_alert(booking_details, customer_phone, admin_email=None):
    """
    Send booking alert email to admin with all customer details
    If admin_email is not provided, use from environment variable
    """
    # Use provided admin_email or fallback to environment variable
    if not admin_email:
        admin_email = ADMIN_EMAIL
    
    if not admin_email:
        print("❌ No admin email provided - check ADMIN_EMAIL in .env")
        return False
    
    # Determine item type (package or hotel)
    item_type = "PACKAGE"
    if booking_details.get('package_name', '').startswith('Hotel:'):
        item_type = "HOTEL"
    
    item_name = booking_details.get('package_name', 'N/A')
    if item_type == "HOTEL":
        item_name = item_name.replace('Hotel:', '').strip()
    
    subject = f"🔔 NEW {item_type} BOOKING - {item_name}"
    
    current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    body = f"""
🚨 NEW BOOKING REQUEST RECEIVED 🚨
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
⏰ Time: {current_time}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

👤 CUSTOMER DETAILS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📱 WhatsApp Number: {customer_phone}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📋 BOOKING DETAILS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📦 {item_type}: {item_name}
🆔 ID: {booking_details.get('package_id', 'N/A')}
💰 Total Price: {booking_details.get('package_price', 'N/A')}
👤 Per Person Price: {booking_details.get('per_person_price', 'N/A')}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📅 TRAVEL DETAILS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🗓️ Travel Dates: {booking_details.get('travel_dates', 'Not specified')}
👥 Travelers: {booking_details.get('travellers', 'Not specified')}
📍 Destination: {booking_details.get('destinations', 'Not specified')}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🎯 ACTION REQUIRED
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✅ Contact customer on WhatsApp immediately: {customer_phone}
✅ Confirm {item_type} availability  
✅ Process payment
✅ Send final confirmation

⚡ URGENT - Customer is waiting for your call!

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📞 Customer WhatsApp: {customer_phone}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
    
    return send_email(admin_email, subject, body)

def send_email(recipient, subject, body):
    """
    Generic email sending function using SMTP
    """
    try:
        msg = MIMEMultipart()
        msg['From'] = FROM_EMAIL
        msg['To'] = recipient
        msg['Subject'] = subject
        
        msg.attach(MIMEText(body, 'plain'))
        
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.send_message(msg)
        
        print(f"✅ Email sent successfully to {recipient}")
        return True
        
    except Exception as e:
        print(f"❌ Failed to send email: {str(e)}")
        return False