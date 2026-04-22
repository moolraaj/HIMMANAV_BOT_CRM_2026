import os
import requests
from dotenv import load_dotenv
load_dotenv('.env')  
PACKAGE_API = os.getenv("PACKAGE_API")
HOTEL_API = os.getenv("HOTEL_API")


 

def fetch_packages(phone):
    try:
        url = f"{PACKAGE_API}?phone={phone}"
        print(f"🌐 API Request: {url}")
        res = requests.get(url, timeout=10)

        if res.status_code != 200:
            return []

        data = res.json()
        
        if data.get("status") and data.get("packages"):
            packages = data.get("packages", [])
            print(f"✅ Fetched {len(packages)} packages")
            return packages
        return []

    except Exception as e:
        print(f"❌ API Exception: {e}")
        return []



def fetch_hotels(phone):
    """Fetch hotels from API"""
    try:
        url = f"{HOTEL_API}?phone={phone}"
        print(f"🌐 Hotel API Request: {url}")
        res = requests.get(url, timeout=10)

        if res.status_code != 200:
            print(f"❌ Hotel API Error: {res.status_code}")
            return []

        data = res.json()
        
        if data.get("status") and data.get("hotels"):
            hotels = data.get("hotels", [])
            print(f"✅ Fetched {len(hotels)} hotels")
            return hotels
        return []

    except Exception as e:
        print(f"❌ Hotel API Exception: {e}")
        return []