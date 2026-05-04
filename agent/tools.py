# agent/tools.py
from typing import Dict, Any, List, Optional
import requests
import logging
from datetime import datetime
import re

logger = logging.getLogger(__name__)

CATEGORIES_API = "https://silver-spoonbill-286441.hostingersite.com/wp-json/hm/v1/hotel-categories"
HOTELS_BY_CATEGORY_API = "https://silver-spoonbill-286441.hostingersite.com/wp-json/hm/v1/hotel-categories?phone=919816440734"
ALL_HOTELS_API = "https://silver-spoonbill-286441.hostingersite.com/wp-json/hm/v1/hotels?phone=919816440734"

class TravelTools:
    
    @staticmethod
    def get_categories() -> Dict[str, Any]:
        try:
            response = requests.get(CATEGORIES_API, timeout=10)
            response.raise_for_status()
            data = response.json()
            if data and data.get("status") and data.get("data"):
                categories = [{"name": cat.get("category_name")} for cat in data["data"]]
                return {"success": True, "categories": categories}
            return {
                "success": True,
                "categories": [
                    {"name": "Budget"}, {"name": "Standard"},
                    {"name": "Deluxe"}, {"name": "Premium"}, {"name": "Luxury"}
                ]
            }
        except Exception as e:
            logger.error(f"Categories error: {e}")
            return {"success": False, "error": str(e), "categories": []}

    @staticmethod
    def search_hotels_by_category(category: str, location: str = None) -> Dict[str, Any]:
        try:
            response = requests.get(HOTELS_BY_CATEGORY_API, timeout=10)
            response.raise_for_status()
            data = response.json()
            if not data.get("status"):
                return {"success": False, "error": "API error", "hotels": []}
            selected = None
            for cat_data in data.get("data", []):
                if cat_data.get("category_name", "").lower() == category.lower():
                    selected = cat_data
                    break
            if not selected:
                return {"success": False, "message": f"No category '{category}'", "hotels": []}
            hotels = selected.get("hotels", [])
            filtered = []
            for hotel in hotels:
                if not location or location.lower() in hotel.get("location", "").lower():
                    filtered.append({
                        "name": hotel.get("name", "").split(",")[0],
                        "full_name": hotel.get("name"),
                        "location": hotel.get("location"),
                        "image": hotel.get("image"),
                        "description": hotel.get("description", "")[:300],
                        "category": category,
                        "original_data": hotel
                    })
            return {"success": True, "category": category, "location": location, "hotels": filtered, "count": len(filtered)}
        except Exception as e:
            logger.error(f"Search error: {e}")
            return {"success": False, "error": str(e), "hotels": []}

    @staticmethod
    def get_hotel_rooms(hotel_name: str) -> Dict[str, Any]:
        try:
            response = requests.get(ALL_HOTELS_API, timeout=10)
            response.raise_for_status()
            data = response.json()
            all_hotels = data.get("hotels", [])
            search_name = hotel_name.replace("Hotel", "").strip().lower()
            selected = None
            for hotel in all_hotels:
                hotel_api_name = hotel.get("hotel_name", "").lower()
                if (search_name == hotel_api_name or
                    search_name in hotel_api_name or
                    hotel_api_name in search_name):
                    selected = hotel
                    break
            if not selected:
                for hotel in all_hotels:
                    if hotel_name.lower() in hotel.get("hotel_name", "").lower():
                        selected = hotel
                        break
            if not selected:
                return {"success": False, "error": f"Hotel '{hotel_name}' not found"}
            rooms = selected.get("rooms", [])
            if not rooms:
                return {"success": False, "error": "No rooms available"}
            formatted_rooms = []
            for room in rooms:
                room_data = {
                    "category": room.get("room_category", "Standard"),
                    "type": room.get("room_type", "Regular"),
                    "min_capacity": int(room.get("minimum_capacity", 1)),
                    "max_capacity": int(room.get("maximum_capacity", 2)),
                    "base_price": int(room.get("base_price", 0)),
                    "extra_person_price": int(room.get("extra_person_price", 0)),
                    "images": room.get("room_images", []),
                    "facilities": room.get("facilities", []),
                    "seasons": room.get("seasons", [])
                }
                formatted_rooms.append(room_data)
            return {
                "success": True,
                "hotel_name": selected.get("hotel_name"),
                "hotel_location": selected.get("location"),
                "meal_plan": {
                    "map_price": int(selected.get("meal_plan", {}).get("map_price", 0)),
                    "cp_price": int(selected.get("meal_plan", {}).get("cp_price", 0)),
                    "ep_price": 0  # EP = No meals = always free
                },
                "rooms": formatted_rooms,
                "total_rooms": len(formatted_rooms),
                "hotel_gallery": selected.get("gallery", [])
            }
        except Exception as e:
            logger.error(f"Get rooms error: {e}")
            return {"success": False, "error": str(e)}

    @staticmethod
    def calculate_room_price(room: Dict, check_in: str, check_out: str, guests: int) -> Dict[str, Any]:
        try:
            check_in_date = datetime.strptime(check_in, "%Y-%m-%d")
            check_out_date = datetime.strptime(check_out, "%Y-%m-%d")
            nights = (check_out_date - check_in_date).days
            month = check_in_date.month
            price_per_night = int(room.get("base_price", 0))
            extra_price = int(room.get("extra_person_price", 0))
            seasons = room.get("seasons", [])
            for season in seasons:
                season_name = season.get("season_name", "").lower()
                season_price = int(season.get("price", 0))
                season_extra = int(season.get("extra_price", 0))
                if "spring" in season_name and 3 <= month <= 5:
                    price_per_night = season_price if season_price > 0 else price_per_night
                    extra_price = season_extra if season_extra > 0 else extra_price
                elif "summer" in season_name and 4 <= month <= 6:
                    price_per_night = season_price if season_price > 0 else price_per_night
                    extra_price = season_extra if season_extra > 0 else extra_price
                elif "monsoon" in season_name and 7 <= month <= 9:
                    price_per_night = season_price if season_price > 0 else price_per_night
                    extra_price = season_extra if season_extra > 0 else extra_price
                elif "autumn" in season_name and 10 <= month <= 11:
                    price_per_night = season_price if season_price > 0 else price_per_night
                    extra_price = season_extra if season_extra > 0 else extra_price
                elif "winter" in season_name and (month == 12 or month <= 2):
                    price_per_night = season_price if season_price > 0 else price_per_night
                    extra_price = season_extra if season_extra > 0 else extra_price
            max_capacity = int(room.get("max_capacity", 2))
            extra_people = max(0, guests - max_capacity)
            room_total = price_per_night * nights
            extra_total = extra_price * extra_people * nights
            grand_total = room_total + extra_total
            return {
                "success": True,
                "nights": nights,
                "guests": guests,
                "extra_people": extra_people,
                "price_per_night": price_per_night,
                "extra_price_per_night": extra_price,
                "room_total": room_total,
                "extra_total": extra_total,
                "grand_total": grand_total
            }
        except Exception as e:
            logger.error(f"Price calculation error: {e}")
            return {"success": False, "error": str(e)}

    @staticmethod
    def calculate_meal_price(meal_type: str, meal_plan_data: Dict, guests: int, nights: int) -> Dict[str, Any]:
        """Calculate meal plan total. EP (No meals) is always Rs.0."""
        try:
            meal_type_lower = meal_type.lower()

            # EP = No meals = always zero, ignore API price
            if meal_type_lower == "ep":
                price_per_person = 0
            else:
                prices = {
                    "map": int(meal_plan_data.get("map_price", 0)),
                    "cp": int(meal_plan_data.get("cp_price", 0)),
                }
                price_per_person = prices.get(meal_type_lower, 0)

            total = price_per_person * guests * nights

            names = {
                "map": "MAP (Breakfast + Dinner)",
                "cp": "CP (Breakfast only)",
                "ep": "EP (No meals)"
            }

            return {
                "success": True,
                "meal_type": meal_type,
                "meal_name": names.get(meal_type_lower, meal_type),
                "price_per_person": price_per_person,
                "total_meal_price": total
            }
        except Exception as e:
            logger.error(f"Meal price error: {e}")
            return {"success": False, "error": str(e)}

    @staticmethod
    def get_all_hotels_in_location(location: str) -> Dict[str, Any]:
        try:
            response = requests.get(HOTELS_BY_CATEGORY_API, timeout=10)
            response.raise_for_status()
            data = response.json()
            all_hotels = []
            for cat_data in data.get("data", []):
                for hotel in cat_data.get("hotels", []):
                    if location.lower() in hotel.get("location", "").lower():
                        all_hotels.append({
                            "name": hotel.get("name", "").split(",")[0],
                            "category": cat_data.get("category_name"),
                            "location": hotel.get("location"),
                            "image": hotel.get("image"),
                            "description": hotel.get("description", "")[:200]
                        })
            return {"success": True, "hotels": all_hotels, "count": len(all_hotels)}
        except Exception as e:
            return {"success": False, "error": str(e), "hotels": []}
        
@staticmethod
def get_hotel_rooms(hotel_name: str) -> Dict[str, Any]:
    """Get rooms for a specific hotel with full details"""
    try:
        response = requests.get(ALL_HOTELS_API, timeout=10)
        response.raise_for_status()
        data = response.json()

        all_hotels = data.get("hotels", [])
        search_name = hotel_name.replace("Hotel", "").strip().lower()

        selected = None
        for hotel in all_hotels:
            hotel_api_name = hotel.get("hotel_name", "").lower()
            if (search_name == hotel_api_name
                    or search_name in hotel_api_name
                    or hotel_api_name in search_name):
                selected = hotel
                break

        if not selected:
            for hotel in all_hotels:
                if hotel_name.lower() in hotel.get("hotel_name", "").lower():
                    selected = hotel
                    break

        if not selected:
            return {"success": False, "error": f"Hotel '{hotel_name}' not found"}

        rooms = selected.get("rooms", [])
        if not rooms:
            return {"success": False, "error": "No rooms available"}

        formatted_rooms = []
        for room in rooms:
            formatted_rooms.append({
                "category":           room.get("room_category", "Standard"),
                "type":               room.get("room_type", "Regular"),
                "min_capacity":       int(room.get("minimum_capacity", 1)),
                "max_capacity":       int(room.get("maximum_capacity", 2)),
                "base_price":         int(room.get("base_price", 0)),
                "extra_person_price": int(room.get("extra_person_price", 0)),
                "images":             room.get("room_images", []),
                "facilities":         room.get("facilities", []),
                "seasons":            room.get("seasons", [])
            })

        # NEW: Return full hotel details
        return {
            "success":        True,
            "hotel_name":     selected.get("hotel_name"),
            "hotel_location": selected.get("location"),
            "full_hotel_details": {
                "hotel_name": selected.get("hotel_name"),
                "category": selected.get("category"),
                "location": selected.get("location"),
                "description": selected.get("description"),
                "phones": selected.get("phones", []),
                "emails": selected.get("emails", []),
                "extra_services": selected.get("extra_services", []),
                "gallery": selected.get("gallery", []),
                "pdf": selected.get("pdf")
            },
            "agent_phone": (
                selected.get("agent_phone")
                or selected.get("contact_phone")
                or selected.get("manager_phone")
                or selected.get("phone")
                or ""
            ),
            "meal_plan": {
                "map_price": int(selected.get("meal_plan", {}).get("map_price", 0)),
                "cp_price":  int(selected.get("meal_plan", {}).get("cp_price",  0)),
                "ep_price":  int(selected.get("meal_plan", {}).get("ep_price",  0))
            },
            "rooms":         formatted_rooms,
            "total_rooms":   len(formatted_rooms),
            "hotel_gallery": selected.get("gallery", [])
        }
    except Exception as e:
        logger.error(f"Get rooms error: {e}")
        return {"success": False, "error": str(e)}


TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "get_categories",
            "description": "Get all hotel categories",
            "parameters": {"type": "object", "properties": {}, "required": []}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_hotels_by_category",
            "description": "Search hotels by category and optional location",
            "parameters": {
                "type": "object",
                "properties": {
                    "category": {"type": "string"},
                    "location": {"type": "string"}
                },
                "required": ["category"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_all_hotels_in_location",
            "description": "Get all hotels in a specific location",
            "parameters": {
                "type": "object",
                "properties": {"location": {"type": "string"}},
                "required": ["location"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_hotel_rooms",
            "description": "Get all rooms for a specific hotel with images, types, categories, prices",
            "parameters": {
                "type": "object",
                "properties": {"hotel_name": {"type": "string"}},
                "required": ["hotel_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "calculate_room_price",
            "description": "Calculate price for selected room based on dates and guests",
            "parameters": {
                "type": "object",
                "properties": {
                    "room": {"type": "object"},
                    "check_in": {"type": "string"},
                    "check_out": {"type": "string"},
                    "guests": {"type": "integer"}
                },
                "required": ["room", "check_in", "check_out", "guests"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "calculate_meal_price",
            "description": "Calculate meal plan price. MAP=Breakfast+Dinner, CP=Breakfast only, EP=No meals (always Rs.0)",
            "parameters": {
                "type": "object",
                "properties": {
                    "meal_type": {"type": "string"},
                    "meal_plan_data": {"type": "object"},
                    "guests": {"type": "integer"},
                    "nights": {"type": "integer"}
                },
                "required": ["meal_type", "meal_plan_data", "guests", "nights"]
            }
        }
    }
]