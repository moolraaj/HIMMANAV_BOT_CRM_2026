# tools/tools.py - ADD THESE NEW METHODS

import requests
import os
from typing import Dict, List, Optional
from dotenv import load_dotenv

load_dotenv('.env')

WP_API_BASE = os.getenv('WP_API_BASE')


class TravelTools:
    """All travel tools for the agent"""
    
    def __init__(self, phone_number: str = None):
        """
        Initialize tools with partner's phone number
        Args:
            phone_number: Business WhatsApp number (e.g., "919816440734")
        """
        self.phone_number = phone_number or os.getenv('DEFAULT_PHONE_NUMBER', '919816440734')
    
    def _request(self, endpoint: str, params: Dict = None) -> Dict:
        """Make API request to WordPress"""
        if params is None:
            params = {}
        params['phone'] = self.phone_number
        
        url = f"{WP_API_BASE}/{endpoint}"
        
        try:
            print(f"🌐 API: {endpoint} | Params: {params}")
            response = requests.get(url, params=params, timeout=15)
            if response.status_code == 200:
                return response.json()
            return {"error": f"HTTP {response.status_code}"}
        except Exception as e:
            return {"error": str(e)}
    
    # ========== LOCATION TOOLS (ADD THESE) ==========
    
    def get_all_locations(self) -> List[Dict]:
        """
        Tool: get_all_locations
        API: wp-json/hm/v1/locations
        Returns: List of all locations with names and slugs
        """
        result = self._request("hm/v1/locations")
        if isinstance(result, dict):
            return result.get("locations", result.get("data", []))
        return result if isinstance(result, list) else []
    
    def get_location_by_slug(self, slug: str) -> Dict:
        """
        Tool: get_location_by_slug
        API: wp-json/hm/v1/location?slug={slug}
        Returns: Single location details
        """
        result = self._request("hm/v1/location", {"slug": slug})
        if isinstance(result, dict):
            return result
        return {}
    
    def get_hotels_by_location_slug(self, slug: str) -> List[Dict]:
        """
        Tool: get_hotels_by_location_slug
        API: wp-json/hm/v1/location?slug={slug}&include=hotels
        Returns: Hotels in that location
        """
        result = self._request("hm/v1/location", {"slug": slug, "include": "hotels"})
        if isinstance(result, dict):
            return result.get("hotels", [])
        return result if isinstance(result, list) else []
    
    def get_packages_by_location_slug(self, slug: str) -> List[Dict]:
        """
        Tool: get_packages_by_location_slug
        API: wp-json/hm/v1/location?slug={slug}&include=packages
        Returns: Packages in that location
        """
        result = self._request("hm/v1/location", {"slug": slug, "include": "packages"})
        if isinstance(result, dict):
            return result.get("packages", [])
        return result if isinstance(result, list) else []
    
    # ========== EXISTING LOCATION TOOLS (KEEP) ==========
    
    def get_locations(self) -> List[str]:
        """Get all available travel destinations"""
        result = self._request("hm/v1/location")
        if isinstance(result, dict):
            return result.get("locations", [])
        return result if isinstance(result, list) else []
    
    def get_hotels_by_location(self, location: str) -> List[Dict]:
        """Get all hotels in a location"""
        result = self._request("hm/v1/location", {"location": location, "include": "hotels"})
        if isinstance(result, dict):
            return result.get("hotels", [])
        return result if isinstance(result, list) else []
    
    def get_packages_by_location(self, location: str) -> List[Dict]:
        """Get all packages in a location"""
        result = self._request("hm/v1/location", {"location": location, "include": "packages"})
        if isinstance(result, dict):
            return result.get("packages", [])
        return result if isinstance(result, list) else []
    
    # ========== HOTEL TOOLS ==========
    
    def get_all_hotels(self) -> List[Dict]:
        """Get all hotels"""
        result = self._request("hm/v1/hotels")
        if isinstance(result, dict):
            return result.get("hotels", [])
        return result if isinstance(result, list) else []
    
    def get_hotel_categories(self) -> List[str]:
        """Get hotel categories (Luxury, Budget, Homestay, Resort, Heritage, Eco-Lodge)"""
        result = self._request("hm/v1/hotel-categories")
        if isinstance(result, dict):
            return result.get("categories", [])
        return result if isinstance(result, list) else []
    
    def get_hotel_types(self) -> List[str]:
        """Get hotel types (Resort, Boutique, etc.)"""
        result = self._request("hm/v1/hotel-types")
        if isinstance(result, dict):
            return result.get("types", [])
        return result if isinstance(result, list) else []
    
    def get_hotels_by_category(self, category: str) -> List[Dict]:
        """Get hotels filtered by category"""
        result = self._request("hm/v1/hotel-categories", {"hotel_category": category})
        if isinstance(result, dict):
            return result.get("hotels", [])
        return result if isinstance(result, list) else []
    
    def get_hotel_by_id(self, hotel_id: int) -> Dict:
        """Get hotel details by ID"""
        hotels = self.get_all_hotels()
        for hotel in hotels:
            if hotel.get('id') == hotel_id:
                return hotel
        return {"error": "Hotel not found"}
    
    # ========== ROOM TOOLS ==========
    
    def get_room_categories(self) -> List[str]:
        """Get room categories (Suite, Deluxe, Standard, Premium)"""
        result = self._request("hm/v1/room-categories")
        if isinstance(result, dict):
            return result.get("room_categories", [])
        return result if isinstance(result, list) else []
    
    def get_room_types(self, room_type: str = None) -> List[Dict]:
        """Get room types (suite-room, deluxe-room, etc.)"""
        params = {}
        if room_type:
            params['type'] = room_type
        result = self._request("hm/v1/room-types", params)
        if isinstance(result, dict):
            return result.get("room_types", [])
        return result if isinstance(result, list) else []
    
    def get_rooms_by_category(self, category: str) -> List[Dict]:
        """Get rooms filtered by category"""
        result = self._request("hm/v1/room-categories", {"category": category})
        if isinstance(result, dict):
            return result.get("rooms", [])
        return result if isinstance(result, list) else []
    
    def get_hotel_rooms(self, hotel_id: int) -> List[Dict]:
        """Get all rooms in a hotel"""
        hotel = self.get_hotel_by_id(hotel_id)
        return hotel.get('rooms', [])
    
    # ========== VEHICLE TOOLS ==========
    
    def get_all_vehicles(self) -> List[Dict]:
        """Get all vehicles"""
        result = self._request("hm/v1/vehicle")
        if isinstance(result, dict):
            return result.get("vehicles", [])
        return result if isinstance(result, list) else []
    
    def get_vehicles_by_type(self, vehicle_type: str) -> List[Dict]:
        """Get vehicles by type (bike, car, tempo, bus)"""
        result = self._request("hm/v1/vehicle", {"include": vehicle_type})
        if isinstance(result, dict):
            return result.get("vehicles", [])
        return result if isinstance(result, list) else []
    
    # ========== PACKAGE TOOLS ==========
    
    def get_all_packages(self) -> List[Dict]:
        """Get all packages"""
        result = self._request("hm/v1/packages")
        if isinstance(result, dict):
            return result.get("packages", [])
        return result if isinstance(result, list) else []
    
    def get_package_by_slug(self, slug: str) -> Dict:
        """Get package by slug"""
        result = self._request("hm/v1/packages", {"include": slug})
        if isinstance(result, dict):
            return result.get("package", {})
        return result if isinstance(result, dict) else {}
    
    # ========== SEASON TOOLS ==========
    
    def get_seasons(self) -> List[Dict]:
        """Get season date ranges for pricing"""
        result = self._request("hm/v1/seasons")
        if isinstance(result, dict):
            return result.get("seasons", [])
        return result if isinstance(result, list) else []
    
    def get_season_for_date(self, date: str) -> Dict:
        """Get season for a specific date (peak/off_peak) with pricing multiplier"""
        seasons = self.get_seasons()
        from datetime import datetime
        
        check_date = datetime.strptime(date, "%Y-%m-%d")
        
        for season in seasons:
            start_str = season.get('start_date', season.get('from', ''))
            end_str = season.get('end_date', season.get('to', ''))
            
            if start_str and end_str:
                start_date = datetime.strptime(start_str, "%Y-%m-%d")
                end_date = datetime.strptime(end_str, "%Y-%m-%d")
                
                if start_date <= check_date <= end_date:
                    return {
                        "season": season.get('name', season.get('season', 'peak')),
                        "multiplier": season.get('price_multiplier', 1.0),
                        "is_peak": True
                    }
        
        return {"season": "off_peak", "multiplier": 0.8, "is_peak": False}