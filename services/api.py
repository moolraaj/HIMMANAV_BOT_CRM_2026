# services/api.py

import os
import requests
from dotenv import load_dotenv
from database.database import get_whatsapp_config

load_dotenv('.env')

PACKAGE_API = os.getenv("PACKAGE_API")
HOTEL_API = os.getenv("HOTEL_API")


def get_display_number_from_sender_id(sender_phone_number_id):
    """
    Get clean display number from database using sender_phone_number_id
    Returns: cleaned phone number (e.g., "919816440734")
    """
    if not sender_phone_number_id:
        return None
    
    config = get_whatsapp_config(sender_phone_number_id)
    if not config:
        return None
    
    display_number = config.get("display_number")
    if not display_number:
        return None
    
    # Clean the phone number (remove +, spaces, etc.)
    cleaned = display_number.replace("+", "").replace(" ", "").strip()
    return cleaned


def fetch_packages(sender_phone_number_id=None):
    """
    Fetch packages from API using sender's phone number
    Args:
        sender_phone_number_id: The Meta phone_number_id
    Returns: full response dict
    """
    try:
        # Get the actual phone number from database
        phone = get_display_number_from_sender_id(sender_phone_number_id)
        
        if not phone:
            print(f"❌ No phone number found for sender_id: {sender_phone_number_id}")
            return {}
        
        url = f"{PACKAGE_API}?phone={phone}"
        print(f"🌐 Package API Request: {url}")
        res = requests.get(url, timeout=10)

        if res.status_code != 200:
            print(f"❌ Package API Error: {res.status_code}")
            return {}

        data = res.json()

        if data.get("status") and data.get("packages"):
            print(f"✅ Fetched {len(data['packages'])} packages | partner: {data.get('user', {}).get('email', 'N/A')}")
            return data

        print("⚠️ No packages in response")
        return {}

    except Exception as e:
        print(f"❌ Package API Exception: {e}")
        return {}


def fetch_hotels(sender_phone_number_id=None):
    """
    Fetch hotels from API using sender's phone number
    Args:
        sender_phone_number_id: The Meta phone_number_id
    Returns: full response dict
    """
    try:
        # Get the actual phone number from database
        phone = get_display_number_from_sender_id(sender_phone_number_id)
        
        if not phone:
            print(f"❌ No phone number found for sender_id: {sender_phone_number_id}")
            return {}
        
        url = f"{HOTEL_API}?phone={phone}"
        print(f"🌐 Hotel API Request: {url}")
        res = requests.get(url, timeout=10)

        if res.status_code != 200:
            print(f"❌ Hotel API Error: {res.status_code}")
            return {}

        data = res.json()

        if data.get("status") and data.get("hotels"):
            print(f"✅ Fetched {len(data['hotels'])} hotels | partner: {data.get('user', {}).get('email', 'N/A')}")
            return data

        print("⚠️ No hotels in response")
        return {}

    except Exception as e:
        print(f"❌ Hotel API Exception: {e}")
        return {}