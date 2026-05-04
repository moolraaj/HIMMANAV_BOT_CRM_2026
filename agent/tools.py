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
ROOM_CATEGORIES_API = "https://silver-spoonbill-286441.hostingersite.com/wp-json/hm/v1/room-categories"
VEHICLE_CATEGORIES_API = "https://silver-spoonbill-286441.hostingersite.com/wp-json/hm/v1/vehicle"
VEHICLE_BY_TYPE_API = "https://silver-spoonbill-286441.hostingersite.com/wp-json/hm/v1/vehicle?phone=919816440734&include={vehicle_type}"
ROOM_PRICES_API = "https://silver-spoonbill-286441.hostingersite.com/wp-json/hm/v1/room-prices"
VEHICLE_PRICES_API = "https://silver-spoonbill-286441.hostingersite.com/wp-json/hm/v1/vehicle-prices"
PACKAGES_API = "https://silver-spoonbill-286441.hostingersite.com/wp-json/hm/v1/packages?phone=919816440734"


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

            # Build full hotel details for summary display
            full_hotel_details = {
                "hotel_name": selected.get("hotel_name"),
                "category": selected.get("category", ""),
                "location": selected.get("location", ""),
                "description": selected.get("description", ""),
                "phones": selected.get("phones", []),
                "emails": selected.get("emails", []),
                "extra_services": selected.get("extra_services", []),
                "gallery": selected.get("gallery", []),
            }

            return {
                "success": True,
                "hotel_name": selected.get("hotel_name"),
                "hotel_location": selected.get("location"),
                "meal_plan": {
                    "map_price": int(selected.get("meal_plan", {}).get("map_price", 0)),
                    "cp_price": int(selected.get("meal_plan", {}).get("cp_price", 0)),
                    "ep_price": 0
                },
                "rooms": formatted_rooms,
                "total_rooms": len(formatted_rooms),
                "hotel_gallery": selected.get("gallery", []),
                "full_hotel_details": full_hotel_details,
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
        try:
            meal_type_lower = meal_type.lower()
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
    def get_room_categories() -> Dict[str, Any]:
        """Fetch room categories from API"""
        try:
            response = requests.get(ROOM_CATEGORIES_API, timeout=10)
            response.raise_for_status()
            data = response.json()
            if data.get("status") and data.get("room_categories"):
                return {
                    "success": True,
                    "room_categories": data.get("room_categories", [])
                }
            return {"success": False, "error": "No room categories found", "room_categories": []}
        except Exception as e:
            logger.error(f"Room categories error: {e}")
            return {"success": False, "error": str(e), "room_categories": []}

    @staticmethod
    def get_vehicle_categories() -> Dict[str, Any]:
        """Fetch vehicle category names with slugs (for button display and API calls)"""
        try:
            response = requests.get(VEHICLE_CATEGORIES_API, timeout=10)
            response.raise_for_status()
            data = response.json()
            if data.get("status") and data.get("categories"):
                # Return both name and slug for each category
                return {
                    "success": True,
                    "vehicle_categories": data.get("categories", [])  # Already has {id, name, slug}
                }
            return {"success": False, "error": "No vehicle categories found", "vehicle_categories": []}
        except Exception as e:
            logger.error(f"Vehicle categories error: {e}")
            return {"success": False, "error": str(e), "vehicle_categories": []}

    @staticmethod
    def get_vehicles_by_type(vehicle_type: str) -> Dict[str, Any]:
        """
        Fetch vehicles filtered by type (e.g. 'bike', 'suv', 'sedan') with pricing.
        Uses: /wp-json/hm/v1/vehicle?phone=919816440734&include=<vehicle_type>
        """
        try:
            url = VEHICLE_BY_TYPE_API.format(vehicle_type=vehicle_type.lower())
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            data = response.json()

            vehicles = []
            # Handle both list and dict responses
            raw = data if isinstance(data, list) else data.get("vehicles", data.get("data", []))
            for v in raw:
                vehicles.append({
                    "id": v.get("id"),
                    "name": v.get("name") or v.get("vehicle_name", ""),
                    "type": v.get("type") or vehicle_type,
                    "capacity": v.get("capacity") or v.get("seating_capacity", ""),
                    "price": v.get("price") or v.get("price_per_day") or v.get("flat_price", 0),
                    "image": v.get("image") or v.get("vehicle_image", ""),
                    "description": v.get("description", ""),
                })
            return {"success": True, "vehicles": vehicles, "vehicle_type": vehicle_type}
        except Exception as e:
            logger.error(f"Vehicle by type error: {e}")
            return {"success": False, "error": str(e), "vehicles": []}

    @staticmethod
    def get_hotels_in_location_for_package(location: str, hotel_category: str = None) -> Dict[str, Any]:
        """
        Fetch hotels matching a specific location (and optionally category) for itinerary display.
        """
        try:
            response = requests.get(HOTELS_BY_CATEGORY_API, timeout=10)
            response.raise_for_status()
            data = response.json()
            matched = []
            for cat_data in data.get("data", []):
                cat_name = cat_data.get("category_name", "")
                if hotel_category and cat_name.lower() != hotel_category.lower():
                    continue
                for hotel in cat_data.get("hotels", []):
                    hotel_loc = hotel.get("location", "")
                    if location.lower() in hotel_loc.lower():
                        matched.append({
                            "name": hotel.get("name", "").split(",")[0],
                            "location": hotel_loc,
                            "category": cat_name,
                            "image": hotel.get("image", ""),
                            "description": hotel.get("description", "")[:200],
                        })
            return {"success": True, "hotels": matched, "count": len(matched)}
        except Exception as e:
            logger.error(f"Hotels for package error: {e}")
            return {"success": False, "error": str(e), "hotels": []}

    @staticmethod
    def get_packages(destination: str = None) -> Dict[str, Any]:
        """Fetch travel packages, optionally filtered by destination."""
        try:
            response = requests.get(PACKAGES_API, timeout=15)
            response.raise_for_status()
            data = response.json()
            all_packages = data if isinstance(data, list) else data.get("packages", data.get("data", []))
            if destination:
                dest_lower = destination.lower()
                matched = [p for p in all_packages if
                           dest_lower in str(p.get("locations", [])).lower() or
                           dest_lower in p.get("title", "").lower() or
                           dest_lower in p.get("package_name", "").lower()]
                return {"success": True, "packages": matched}
            return {"success": True, "packages": all_packages}
        except Exception as e:
            logger.error(f"Packages error: {e}")
            return {"success": False, "error": str(e), "packages": []}

    @staticmethod
    def get_room_prices() -> Dict[str, Any]:
        """Fetch room prices from API"""
        try:
            response = requests.get(ROOM_PRICES_API, timeout=10)
            response.raise_for_status()
            data = response.json()
            if data.get("status") and data.get("prices"):
                return {"success": True, "prices": data.get("prices", {})}
            return {"success": False, "error": "No room prices found", "prices": {}}
        except Exception as e:
            logger.error(f"Room prices error: {e}")
            return {"success": False, "error": str(e), "prices": {}}

    @staticmethod
    def get_vehicle_prices() -> Dict[str, Any]:
        """Fetch vehicle prices from API"""
        try:
            response = requests.get(VEHICLE_PRICES_API, timeout=10)
            response.raise_for_status()
            data = response.json()
            if data.get("status") and data.get("prices"):
                return {"success": True, "prices": data.get("prices", {})}
            return {"success": False, "error": "No vehicle prices found", "prices": {}}
        except Exception as e:
            logger.error(f"Vehicle prices error: {e}")
            return {"success": False, "error": str(e), "prices": {}}

    @staticmethod
    def calculate_package_price(room_category: Dict, vehicle_category: Dict,
                                check_in: str, check_out: str, guests: int,
                                want_activities: bool = False) -> Dict[str, Any]:
        """Calculate package price — fetches prices from API, no hardcoding."""
        try:
            check_in_date = datetime.strptime(check_in, "%Y-%m-%d")
            check_out_date = datetime.strptime(check_out, "%Y-%m-%d")
            nights = (check_out_date - check_in_date).days

            room_prices_result = TravelTools.get_room_prices()
            vehicle_prices_result = TravelTools.get_vehicle_prices()

            room_name = room_category.get("name", "")
            vehicle_name = vehicle_category.get("name", "")

            room_price_per_night = 0
            if room_prices_result.get("success"):
                room_prices = room_prices_result.get("prices", {})
                room_price_per_night = room_prices.get(room_name, 0)

            vehicle_price_per_night = 0
            if vehicle_prices_result.get("success"):
                vehicle_prices = vehicle_prices_result.get("prices", {})
                vehicle_price_per_night = vehicle_prices.get(vehicle_name, 0)

            room_total = room_price_per_night * nights * guests
            vehicle_total = vehicle_price_per_night * nights

            activities_price_per_night = 0
            try:
                act_response = requests.get(
                    "https://silver-spoonbill-286441.hostingersite.com/wp-json/hm/v1/activities-prices",
                    timeout=10
                )
                if act_response.status_code == 200:
                    act_data = act_response.json()
                    if act_data.get("status"):
                        activities_price_per_night = int(act_data.get("price_per_person_per_night", 0))
            except Exception:
                activities_price_per_night = 0

            activities_total = activities_price_per_night * nights * guests if want_activities else 0
            grand_total = room_total + vehicle_total + activities_total

            return {
                "success": True,
                "nights": nights,
                "guests": guests,
                "room_category": room_name,
                "vehicle_category": vehicle_name,
                "room_price_per_night": room_price_per_night,
                "vehicle_price_per_night": vehicle_price_per_night,
                "activities_price_per_night": activities_price_per_night,
                "room_total": room_total,
                "vehicle_total": vehicle_total,
                "activities_total": activities_total,
                "want_activities": want_activities,
                "grand_total": grand_total
            }
        except Exception as e:
            logger.error(f"Package price calculation error: {e}")
            return {"success": False, "error": str(e)}


TOOL_DEFINITIONS = [
    # ── Hotel tools ────────────────────────────────────────────────────────
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
            "description": "Get all rooms for a specific hotel",
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
            "description": "Calculate price for selected room",
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
            "description": "Calculate meal plan price",
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
    },
    # ── Package tools ──────────────────────────────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "get_room_categories",
            "description": "Get all room categories for packages",
            "parameters": {"type": "object", "properties": {}, "required": []}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_vehicle_categories",
            "description": "Get all vehicle category names for packages",
            "parameters": {"type": "object", "properties": {}, "required": []}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_vehicles_by_type",
            "description": "Fetch specific vehicles with pricing filtered by type (e.g. bike, suv, sedan)",
            "parameters": {
                "type": "object",
                "properties": {
                    "vehicle_type": {
                        "type": "string",
                        "description": "Vehicle type slug, e.g. 'bike', 'suv', 'sedan', 'tempo'"
                    }
                },
                "required": ["vehicle_type"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_hotels_in_location_for_package",
            "description": "Get hotels in a location for package itinerary display",
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {"type": "string"},
                    "hotel_category": {"type": "string"}
                },
                "required": ["location"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_packages",
            "description": "Fetch travel packages, optionally filtered by destination",
            "parameters": {
                "type": "object",
                "properties": {
                    "destination": {"type": "string"}
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "calculate_package_price",
            "description": "Calculate total price for travel package",
            "parameters": {
                "type": "object",
                "properties": {
                    "room_category": {"type": "object"},
                    "vehicle_category": {"type": "object"},
                    "check_in": {"type": "string"},
                    "check_out": {"type": "string"},
                    "guests": {"type": "integer"},
                    "want_activities": {"type": "boolean"}
                },
                "required": ["room_category", "vehicle_category", "check_in", "check_out", "guests"]
            }
        }
    },
]