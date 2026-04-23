import os
import requests
from dotenv import load_dotenv

load_dotenv('.env')

PACKAGE_API = os.getenv("PACKAGE_API")
HOTEL_API   = os.getenv("HOTEL_API")


def fetch_packages(phone):
    """Fetch packages from API — returns full response dict so caller can access user.email"""
    try:
        url = f"{PACKAGE_API}?phone={phone}"
        print(f"🌐 Package API Request: {url}")
        res = requests.get(url, timeout=10)

        if res.status_code != 200:
            print(f"❌ Package API Error: {res.status_code}")
            return {}

        data = res.json()

        if data.get("status") and data.get("packages"):
            print(f"✅ Fetched {len(data['packages'])} packages | partner: {data.get('user', {}).get('email', 'N/A')}")
            return data   # ← full dict: { status, user, packages, ... }

        print("⚠️ No packages in response")
        return {}

    except Exception as e:
        print(f"❌ Package API Exception: {e}")
        return {}


def fetch_hotels(phone):
    """Fetch hotels from API — returns full response dict so caller can access user.email"""
    try:
        url = f"{HOTEL_API}?phone={phone}"
        print(f"🌐 Hotel API Request: {url}")
        res = requests.get(url, timeout=10)

        if res.status_code != 200:
            print(f"❌ Hotel API Error: {res.status_code}")
            return {}

        data = res.json()

        if data.get("status") and data.get("hotels"):
            print(f"✅ Fetched {len(data['hotels'])} hotels | partner: {data.get('user', {}).get('email', 'N/A')}")
            return data   # ← full dict: { status, user, hotels, ... }

        print("⚠️ No hotels in response")
        return {}

    except Exception as e:
        print(f"❌ Hotel API Exception: {e}")
        return {}