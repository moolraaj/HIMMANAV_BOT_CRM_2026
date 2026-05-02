 



import requests
import logging

logger = logging.getLogger(__name__)

CATEGORIES_URL = "https://silver-spoonbill-286441.hostingersite.com/wp-json/hm/v1/hotel-categories"
HOTELS_URL = "https://silver-spoonbill-286441.hostingersite.com/wp-json/hm/v1/hotel-categories?phone=919816440734"


def get_hotel_categories():
    try:
        response = requests.get(CATEGORIES_URL, timeout=10)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        logger.error(f"❌ get_hotel_categories error: {e}")
        return {"data": []}


def get_hotels_by_category(category: str, location: str) -> list:
    try:
        response = requests.get(HOTELS_URL, timeout=10)
        response.raise_for_status()
        data = response.json()

        for c in data.get("data", []):
            if c["category_name"].lower() == category.lower():
                return [
                    h for h in c.get("hotels", [])
                    if location.lower() in h.get("location", "").lower()
                ]
        return []
    except Exception as e:
        logger.error(f"❌ get_hotels_by_category error: {e}")
        return []