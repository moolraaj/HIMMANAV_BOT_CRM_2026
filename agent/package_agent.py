"""
PACKAGE FLOW (separate from hotel flow)
"""
import json
import os
import logging
import requests
import re
import math
from typing import Dict, Any, List, Optional
from datetime import datetime
from openai import OpenAI
from agent.tools import TravelTools

logger = logging.getLogger(__name__)

# API endpoints
PACKAGES_API = "https://silver-spoonbill-286441.hostingersite.com/wp-json/hm/v1/packages?phone=919816440734"


class PackageAgent:

    def __init__(self):
        self.client = OpenAI(api_key=os.getenv("OPEN_API_KEY"))
        self.tools = TravelTools()
        self.sessions: Dict[str, Dict] = {}

    def get_system_prompt(self) -> str:
        return """You are a TRAVEL PACKAGE booking AI agent (NOT hotel booking).

IMPORTANT: This is PACKAGE flow, completely separate from hotel flow.

PACKAGE BOOKING FLOW (Follow STRICTLY):
1. Ask: "Which destination are you looking for a package in?"
2. Validate destination is a real city
3. Ask: "What are your travel dates? (check-in and check-out)"
4. Validate dates (no past dates, check-out after check-in)
5. Ask: "How many guests will be travelling?"
6. After collecting destination, dates, guests → show hotel category buttons (from API)
7. After hotel category → show room category buttons (from API)  
8. After room category → show vehicle category buttons (from API)
9. After vehicle category → show vehicles in that category
10. After vehicle selection → fetch and show packages
11. User picks package → calculate price with hotel + vehicle + margin
12. Show full itinerary with hotel names and price breakdown with buttons
13. Show Book Now, Change Vehicle, Change Hotel, Other Packages buttons
14. On Book Now → booking confirmation and reset session

CRITICAL RULES:
- NEVER hardcode categories or season names - ALWAYS fetch from API and parse actual dates
- Season matching must use starting_date and end_date from API, not hardcoded month checks
- NEVER ask for destination/dates/guests again once collected
- Meal plan is always MAP (use price from hotel's meal_plan.map_price)
- Vehicle price is FLAT for entire trip
- Calculate rooms needed using min_capacity and max_capacity only
- Extra persons = guests - (rooms_needed × min_capacity)
- Use seasonal pricing when user dates fall within season date ranges
- MAP meal price = map_price × guests × nights
- Add package margin from package_margin_price_manual
- NEVER hardcode any data - always fetch from API
"""

    @staticmethod
    def _default_context() -> Dict:
        return {
            "flow": "package",
            "step": "ask_destination",
            "destination": None,
            "check_in": None,
            "check_out": None,
            "guests": None,
            "hotel_category": None,
            "room_category": None,
            "vehicle_category": None,
            "vehicle_slug": None,
            "vehicle": None,
            "packages_list": None,
            "selected_package": None,
            "price_details": None,
            "hotel_categories": None,
            "room_categories": None,
            "vehicle_types": None,
            "vehicles_list": None,
            "hotel_data_cache": {},
            "selected_hotels": {},
        }

    def execute(self, phone: str, user_message: str, state: dict = None) -> Dict:
        if phone not in self.sessions:
            saved = (state or {}).get("package_data", {})
            default = self._default_context()
            if saved:
                for k in default:
                    if k not in saved:
                        saved[k] = default[k]
                ctx = saved
            else:
                ctx = default
            self.sessions[phone] = {"history": [], "context": ctx}

        session = self.sessions[phone]
        context = session["context"]
        
        session["history"].append({"role": "user", "content": user_message})
        
        msg = user_message.strip().lower()

        # ═══════════════════════════════════════════════════════════════════
        # BUTTON HANDLERS
        # ═══════════════════════════════════════════════════════════════════

        # Hotel category button
        hotel_cats = [c.get("name", "").lower() for c in (context.get("hotel_categories") or [])]
        if msg in hotel_cats and not context.get("hotel_category"):
            logger.info(f"Package: Hotel category selected: {user_message}")
            context["hotel_category"] = user_message.strip()
            context["step"] = "ask_room_category"
            self._save(state, context)
            return self._fetch_and_show_room_categories(context)

        # Room category button
        room_cats = [c.get("name", "").lower() for c in (context.get("room_categories") or [])]
        if msg in room_cats and not context.get("room_category"):
            logger.info(f"Package: Room category selected: {user_message}")
            context["room_category"] = user_message.strip()
            context["step"] = "ask_vehicle_category"
            self._save(state, context)
            return self._fetch_and_show_vehicle_categories(context)

        # Vehicle category button
        vehicle_cats = context.get("vehicle_types") or []
        vehicle_cat_names = [v.get("name", "").lower() for v in vehicle_cats]
        if msg in vehicle_cat_names and not context.get("vehicle_category"):
            matching = [v for v in vehicle_cats if v.get("name", "").lower() == msg]
            if matching:
                context["vehicle_category"] = matching[0].get("name")
                context["vehicle_slug"] = matching[0].get("slug")
                context["step"] = "ask_vehicle"
                self._save(state, context)
                return self._fetch_and_show_vehicles_by_type(context, matching[0].get("slug"))

        # Vehicle selection button
        if user_message.startswith("select_vehicle_"):
            try:
                idx = int(user_message.replace("select_vehicle_", "").strip())
                vehicles = context.get("vehicles_list", [])
                if idx < len(vehicles):
                    logger.info(f"Package: Vehicle selected: {vehicles[idx].get('name')}")
                    context["vehicle"] = vehicles[idx]
                    context["step"] = "fetch_packages"
                    self._save(state, context)
                    return self._fetch_and_show_packages(context)
            except ValueError:
                logger.error(f"Invalid vehicle selection: {user_message}")

        # Package selection button
        if user_message.startswith("select_package_"):
            try:
                idx = int(user_message.replace("select_package_", "").strip())
                pkgs = context.get("packages_list", [])
                if idx < len(pkgs):
                    logger.info(f"Package selected: {pkgs[idx].get('package_name', pkgs[idx].get('title'))}")
                    context["selected_package"] = pkgs[idx]
                    context["step"] = "calculate_price"
                    self._save(state, context)
                    return self._calculate_and_show_price(context, state)
            except ValueError:
                logger.error(f"Invalid package selection: {user_message}")

        # Other Packages button
        if msg == "other_packages":
            pkgs = context.get("packages_list", [])
            selected = context.get("selected_package", {})
            others = [p for p in pkgs if p.get("id") != selected.get("id")]
            if others:
                context["packages_list"] = others
                context["step"] = "show_packages"
                self._save(state, context)
                return self._show_packages(context)
            return {
                "type": "buttons",
                "content": f"No other packages available. Continue with {selected.get('package_name', 'this package')}?",
                "buttons": [{"text": "Continue", "value": "continue_package"}]
            }

        # Continue button
        if msg == "continue_package":
            context["step"] = "final_summary"
            self._save(state, context)
            return self._show_final_summary(context)

        # Change Vehicle button
        if msg == "change_vehicle":
            context["vehicle"] = None
            context["vehicle_category"] = None
            context["step"] = "ask_vehicle_category"
            self._save(state, context)
            return self._fetch_and_show_vehicle_categories(context)

        # Change Hotel button
        if msg == "change_hotel":
            context["hotel_category"] = None
            context["room_category"] = None
            context["selected_hotels"] = {}
            context["step"] = "ask_hotel_category"
            self._save(state, context)
            return self._fetch_and_show_hotel_categories(context)

        # Book Now button - Confirm and reset session
        if msg == "book_now":
            response = self._confirm_booking(context, phone)
            self.reset_session(phone)
            if state is not None:
                state["package_data"] = self._default_context()
            return response

        # Confirm booking button (from final summary)
        if msg in ("confirm_package", "confirm", "book") and context.get("step") == "final_summary":
            response = self._confirm_booking(context, phone)
            self.reset_session(phone)
            if state is not None:
                state["package_data"] = self._default_context()
            return response

        # Update guests from text message
        guest_match = re.search(r'we are (\d+) people', msg) or re.search(r'(\d+) (?:people|guests|members)', msg)
        if guest_match:
            try:
                num = int(guest_match.group(1))
                if num != context.get("guests"):
                    logger.info(f"Updating guests from {context.get('guests')} to {num}")
                    context["guests"] = num
                    if context.get("selected_package") and context.get("price_details"):
                        context["step"] = "calculate_price"
                        self._save(state, context)
                        return self._calculate_and_show_price(context, state)
            except:
                pass

        # ═══════════════════════════════════════════════════════════════════
        # LLM EXTRACTION
        # ═══════════════════════════════════════════════════════════════════
        
        logger.info(f"Package: Processing text message: {user_message[:50]}...")
        extracted = self._extract_info_with_llm(user_message, context)
        self._apply_extracted_info(extracted, context)
        self._save(state, context)

        if (context.get("destination") and 
            context.get("check_in") and 
            context.get("check_out") and 
            context.get("guests") and 
            not context.get("hotel_category")):
            context["step"] = "ask_hotel_category"
            self._save(state, context)
            return self._fetch_and_show_hotel_categories(context)

        return self._llm_next_question(session, context)

    # ═══════════════════════════════════════════════════════════════════════
    # EXTRACTION METHODS
    # ═══════════════════════════════════════════════════════════════════════

    def _extract_info_with_llm(self, message: str, context: Dict) -> Dict:
        extraction_prompt = f"""
Extract travel package booking details from the user message.

Return JSON ONLY:
{{
    "destination": "city name or null",
    "check_in": "YYYY-MM-DD or null", 
    "check_out": "YYYY-MM-DD or null",
    "guests": number or null
}}

Rules:
- Today is {datetime.now().strftime('%Y-%m-%d')}
- No past dates, check_out must be after check_in
- "we are 4 people" = 4, "we are 8 people" = 8, "we are 10 people" = 10

Already collected:
- Destination: {context.get('destination')}
- Check-in: {context.get('check_in')}
- Check-out: {context.get('check_out')}
- Guests: {context.get('guests')}

User message: "{message}"
"""
        try:
            response = self.client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[{"role": "user", "content": extraction_prompt}],
                temperature=0.1,
                response_format={"type": "json_object"}
            )
            result = json.loads(response.choices[0].message.content)
            logger.info(f"Package extraction: {result}")
            return result
        except Exception as e:
            logger.error(f"Package extraction error: {e}")
            return {"destination": None, "check_in": None, "check_out": None, "guests": None}

    def _apply_extracted_info(self, extracted: Dict, context: Dict):
        today = datetime.now().date()

        if not context.get("destination") and extracted.get("destination"):
            context["destination"] = extracted["destination"].title()
            if context.get("step") == "ask_destination":
                context["step"] = "ask_dates"

        if extracted.get("check_in") and extracted.get("check_out"):
            try:
                ci = datetime.strptime(extracted["check_in"], "%Y-%m-%d").date()
                co = datetime.strptime(extracted["check_out"], "%Y-%m-%d").date()
                if ci >= today and co > ci:
                    context["check_in"] = extracted["check_in"]
                    context["check_out"] = extracted["check_out"]
                    if context.get("step") == "ask_dates":
                        context["step"] = "ask_guests"
            except Exception as e:
                logger.error(f"Date error: {e}")

        if not context.get("guests") and extracted.get("guests"):
            g = int(extracted["guests"])
            if 1 <= g <= 50:
                context["guests"] = g

    # ═══════════════════════════════════════════════════════════════════════
    # FETCH & DISPLAY METHODS
    # ═══════════════════════════════════════════════════════════════════════

    def _fetch_and_show_hotel_categories(self, context: Dict) -> Dict:
        result = self.tools.get_categories()
        context["hotel_categories"] = result.get("categories", [])
        if not context["hotel_categories"]:
            return {"type": "text", "content": "No hotel categories available. Please try again later."}
        
        buttons = [{"text": c["name"], "value": c["name"]} for c in context["hotel_categories"]]
        return {
            "type": "buttons_grid",
            "content": f"Select Hotel Category in {context.get('destination')}\n\nPlease choose your preferred hotel type:",
            "buttons": buttons,
        }

    def _fetch_and_show_room_categories(self, context: Dict) -> Dict:
        result = self.tools.get_room_categories()
        if result.get("success"):
            context["room_categories"] = result.get("room_categories", [])
        else:
            context["room_categories"] = []
            
        if not context["room_categories"]:
            return {"type": "text", "content": "No room categories available. Please try again later."}
            
        buttons = [{"text": c["name"], "value": c["name"]} for c in context["room_categories"]]
        return {
            "type": "buttons_grid",
            "content": "Select Room Category\n\nChoose your preferred room type:",
            "buttons": buttons,
        }

    def _fetch_and_show_vehicle_categories(self, context: Dict) -> Dict:
        result = self.tools.get_vehicle_categories()
        
        if not result.get("success") or not result.get("vehicle_categories"):
            return {"type": "text", "content": "Unable to fetch vehicle categories. Please try again later."}
        
        context["vehicle_types"] = result.get("vehicle_categories", [])
        buttons = [{"text": vt["name"], "value": vt["name"]} for vt in context["vehicle_types"]]
        
        return {
            "type": "buttons_grid",
            "content": "Select Vehicle Type:",
            "buttons": buttons,
        }

    def _fetch_and_show_vehicles_by_type(self, context: Dict, slug: str) -> Dict:
        try:
            result = self.tools.get_vehicles_by_type(slug)
            
            if not result.get("success") or not result.get("vehicles"):
                return {"type": "text", "content": f"No vehicles available in {slug} category. Please select another type."}
            
            vehicles = result.get("vehicles", [])
            
            content = f"{slug.upper()} VEHICLES\n"
            content += "Vehicle price is FLAT for entire trip (NOT per person)\n\n"
            
            for i, vehicle in enumerate(vehicles):
                name = vehicle.get("name", "Vehicle")
                price_raw = vehicle.get("price", 0)
                
                try:
                    if isinstance(price_raw, str):
                        price_raw = price_raw.replace(",", "")
                    price = float(price_raw)
                    price_str = f"Rs.{price:,.0f}"
                except (ValueError, TypeError):
                    price_str = f"Rs.{price_raw}"
                
                capacity = vehicle.get("capacity", "N/A")
                content += f"{i+1}. {name}\n"
                content += f"   Price: {price_str} (flat for entire trip)\n"
                if capacity != "N/A":
                    content += f"   Capacity: {capacity} persons\n"
                content += "\n"
            
            buttons = [
                {"text": v.get("name", "Vehicle"), "value": f"select_vehicle_{i}"}
                for i, v in enumerate(vehicles)
            ]
            
            context["vehicles_list"] = vehicles
            
            return {
                "type": "buttons_grid",
                "content": content,
                "buttons": buttons
            }
            
        except Exception as e:
            logger.error(f"Vehicle fetch error: {e}")
            return {"type": "text", "content": f"Error loading vehicles: {str(e)}"}

    def _fetch_and_show_packages(self, context: Dict) -> Dict:
        try:
            response = requests.get(PACKAGES_API, timeout=15)
            data = response.json()
            all_packages = data if isinstance(data, list) else data.get("packages", data.get("data", []))
            
            dest_lower = context["destination"].lower()
            matched = [p for p in all_packages if 
                       dest_lower in str(p.get("locations", [])).lower() or 
                       dest_lower in p.get("title", "").lower() or 
                       dest_lower in p.get("package_name", "").lower()]
            
            context["packages_list"] = matched
            return self._show_packages(context) if matched else {
                "type": "text",
                "content": f"No packages found for {context['destination']}. Please try a different destination."
            }
        except Exception as e:
            logger.error(f"Packages error: {e}")
            return {"type": "text", "content": "Unable to fetch packages. Please try again."}

    def _show_packages(self, context: Dict) -> Dict:
        pkgs = context.get("packages_list", [])
        content = f"Available Packages for {context.get('destination')}\n\n"
        for i, pkg in enumerate(pkgs[:6], 1):
            pkg_name = pkg.get("package_name") or pkg.get("title", "Package")
            content += f"{i}. {pkg_name}\n"
        buttons = [{"text": f"Package {i+1}", "value": f"select_package_{i}"} for i in range(min(6, len(pkgs)))]
        return {
            "type": "buttons_grid",
            "content": content, 
            "buttons": buttons
        }

    # ═══════════════════════════════════════════════════════════════════════
    # SEASON MATCHING - DYNAMIC BASED ON ACTUAL DATE RANGES
    # ═══════════════════════════════════════════════════════════════════════

    def _parse_date(self, date_str: str) -> Optional[datetime]:
        """Parse date string in various formats"""
        if not date_str:
            return None
        
        formats = ["%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%Y/%m/%d"]
        for fmt in formats:
            try:
                return datetime.strptime(date_str, fmt)
            except ValueError:
                continue
        return None

    def _find_matching_season(self, seasons: List[Dict], check_in_date: datetime, check_out_date: datetime) -> Optional[Dict]:
        """Find which season the user's dates fall into based on actual starting_date and end_date from API"""
        try:
            for season in seasons:
                starting_date_str = season.get("starting_date", "")
                end_date_str = season.get("end_date", "")
                
                if not starting_date_str or not end_date_str:
                    continue
                
                season_start = self._parse_date(starting_date_str)
                season_end = self._parse_date(end_date_str)
                
                if not season_start or not season_end:
                    continue
                
                # Handle seasons that cross year boundary
                if season_start > season_end:
                    if check_in_date >= season_start or check_in_date <= season_end:
                        return season
                else:
                    if season_start <= check_in_date <= season_end:
                        return season
                
                if season_start > season_end:
                    if check_out_date >= season_start or check_out_date <= season_end:
                        return season
                else:
                    if season_start <= check_out_date <= season_end:
                        return season
            
            return None
        except Exception as e:
            logger.error(f"Season matching error: {e}")
            return None

    def _get_seasonal_price(self, room: Dict, check_in_date: datetime, check_out_date: datetime) -> tuple:
        """Get seasonal price and extra price based on date range"""
        base_price = float(room.get("base_price", 0))
        base_extra_price = float(room.get("extra_person_price", 0))
        seasons = room.get("seasons", [])
        
        matching_season = self._find_matching_season(seasons, check_in_date, check_out_date)
        
        if matching_season:
            try:
                price = float(matching_season.get("price", base_price))
                extra_price = float(matching_season.get("extra_price", base_extra_price))
                season_name = matching_season.get("season_name", "Seasonal Rate")
                logger.info(f"Seasonal pricing applied: {season_name} - Price: {price}, Extra: {extra_price}")
                return price, extra_price, season_name
            except (ValueError, TypeError):
                pass
        
        logger.info(f"Using base pricing - Price: {base_price}, Extra: {base_extra_price}")
        return base_price, base_extra_price, "Regular Rate"

    def _get_map_meal_price(self, meal_plan: Dict) -> float:
        """Get MAP meal price from meal plan"""
        try:
            return float(meal_plan.get("map_price", 0))
        except (ValueError, TypeError):
            return 0

    # ═══════════════════════════════════════════════════════════════════════
    # ROOM CALCULATION - USING ONLY MIN AND MAX CAPACITY
    # ═══════════════════════════════════════════════════════════════════════

    def _calculate_rooms_and_extra_persons(self, guests: int, min_capacity: int, max_capacity: int) -> Dict:
        """
        Calculate rooms needed and extra persons using ONLY min and max capacity.
        
        Each room:
        - Minimum capacity: base price for up to min_capacity guests
        - Maximum capacity: can accommodate up to max_capacity guests
        - Extra persons = guests beyond min_capacity in each room
        
        Examples with min=2, max=3:
        - 5 guests: rooms_needed = ceil(5/3) = 2 rooms, extra = 5 - (2×2) = 1
        - 6 guests: rooms_needed = ceil(6/3) = 2 rooms, extra = 6 - (2×2) = 2
        - 7 guests: rooms_needed = ceil(7/3) = 3 rooms, extra = 7 - (3×2) = 1
        """
        rooms_needed = math.ceil(guests / max_capacity)
        extra_persons_total = max(0, guests - (rooms_needed * min_capacity))
        
        logger.info(f"Room calculation: guests={guests}, min={min_capacity}, max={max_capacity}")
        logger.info(f"  Rooms needed: {rooms_needed}, Extra persons: {extra_persons_total}")
        
        return {
            "rooms_needed": rooms_needed,
            "extra_persons_total": extra_persons_total
        }

    def _get_hotel_for_location(self, location: str, hotel_category: str, room_category: str) -> Optional[Dict]:
        """Fetch hotel and room matching the category at specific location"""
        try:
            result = self.tools.search_hotels_by_category(hotel_category, location)
            
            if result.get("success") and result.get("hotels"):
                hotels = result.get("hotels", [])
                for hotel in hotels:
                    hotel_name = hotel.get("name")
                    rooms_result = self.tools.get_hotel_rooms(hotel_name)
                    
                    if rooms_result.get("success"):
                        rooms = rooms_result.get("rooms", [])
                        for room in rooms:
                            room_cat = room.get("category", "").lower()
                            if room_cat == room_category.lower():
                                return {
                                    "hotel": hotel,
                                    "room": room,
                                    "hotel_name": hotel_name,
                                    "room_category": room.get("category"),
                                    "meal_plan": rooms_result.get("meal_plan", {})
                                }
            
            return None
            
        except Exception as e:
            logger.error(f"Error fetching hotel for {location}: {e}")
            return None

    def _calculate_and_show_price(self, context: Dict, state=None) -> Dict:
        """Calculate package price with hotel, vehicle, and margin"""
        try:
            pkg = context.get("selected_package", {})
            itinerary = pkg.get("itinerary", [])
            check_in_str = context.get("check_in")
            check_out_str = context.get("check_out")
            guests = context.get("guests", 1)
            hotel_category = context.get("hotel_category")
            room_category = context.get("room_category")
            vehicle = context.get("vehicle", {})
            
            check_in = datetime.strptime(check_in_str, "%Y-%m-%d")
            check_out = datetime.strptime(check_out_str, "%Y-%m-%d")
            nights = (check_out - check_in).days
            
            # Get unique locations from itinerary
            unique_locations = []
            seen = set()
            for day in itinerary:
                location = day.get("stay_location") or day.get("location", "")
                if location and location not in seen:
                    seen.add(location)
                    unique_locations.append(location)
            
            if not unique_locations:
                unique_locations = [context.get("destination", "Unknown")]
            
            hotel_costs = []
            total_hotel_price = 0
            total_map_price = 0
            selected_hotels = {}
            
            # For each location, find a matching hotel
            for location in unique_locations:
                hotel_data = self._get_hotel_for_location(location, hotel_category, room_category)
                
                if hotel_data:
                    room = hotel_data.get("room", {})
                    hotel_name = hotel_data.get("hotel_name", "Unknown Hotel")
                    meal_plan = hotel_data.get("meal_plan", {})
                    
                    # Get capacities from room - ONLY min and max
                    min_capacity = int(room.get("minimum_capacity", 2))
                    max_capacity = int(room.get("maximum_capacity", 3))
                    
                    # Get seasonal pricing
                    price_per_room, extra_person_price, season_name = self._get_seasonal_price(room, check_in, check_out)
                    map_price_per_person = self._get_map_meal_price(meal_plan)
                    
                    # Calculate rooms and extra persons using ONLY min and max
                    calc = self._calculate_rooms_and_extra_persons(guests, min_capacity, max_capacity)
                    rooms_needed = calc["rooms_needed"]
                    extra_persons_total = calc["extra_persons_total"]
                    
                    hotel_nightly_price = (price_per_room * rooms_needed) + (extra_persons_total * extra_person_price)
                    hotel_total = hotel_nightly_price * nights
                    map_total = map_price_per_person * guests * nights
                    
                    hotel_cost_entry = {
                        "location": location,
                        "hotel_name": hotel_name,
                        "room_category": room_category,
                        "price_per_room": price_per_room,
                        "extra_person_price": extra_person_price,
                        "rooms_needed": rooms_needed,
                        "extra_persons_total": extra_persons_total,
                        "min_capacity": min_capacity,
                        "max_capacity": max_capacity,
                        "hotel_total": hotel_total,
                        "map_price_per_person": map_price_per_person,
                        "map_total": map_total,
                        "season_name": season_name,
                    }
                    hotel_costs.append(hotel_cost_entry)
                    selected_hotels[location] = hotel_name
                    
                    total_hotel_price += hotel_total
                    total_map_price += map_total
                else:
                    hotel_cost_entry = {
                        "location": location,
                        "hotel_name": f"{hotel_category} Hotel",
                        "room_category": room_category,
                        "price_per_room": 0,
                        "extra_person_price": 0,
                        "rooms_needed": 0,
                        "extra_persons_total": 0,
                        "min_capacity": 2,
                        "max_capacity": 3,
                        "hotel_total": 0,
                        "map_price_per_person": 0,
                        "map_total": 0,
                        "season_name": "N/A",
                    }
                    hotel_costs.append(hotel_cost_entry)
                    selected_hotels[location] = f"{hotel_category} Hotel"
            
            context["selected_hotels"] = selected_hotels
            
            # Vehicle price
            vehicle_price = 0
            vehicle_name = "None"
            if vehicle:
                vehicle_name = vehicle.get("name", "Unknown")
                price_raw = vehicle.get("price", 0)
                try:
                    if isinstance(price_raw, str):
                        price_raw = price_raw.replace(",", "")
                    vehicle_price = float(price_raw)
                except (ValueError, TypeError):
                    vehicle_price = 0
            
            # Package margin
            package_margin = 0
            margin_manual = pkg.get("package_margin_price_manual", pkg.get("margin", "0"))
            try:
                if margin_manual:
                    package_margin = float(str(margin_manual).replace(",", ""))
            except (ValueError, TypeError):
                package_margin = 0
            
            total_price = total_hotel_price + total_map_price + vehicle_price + package_margin
            
            price_details = {
                "hotel_costs": hotel_costs,
                "total_hotel_price": total_hotel_price,
                "total_map_price": total_map_price,
                "vehicle_price": vehicle_price,
                "vehicle_name": vehicle_name,
                "package_margin": package_margin,
                "total_price": total_price,
                "nights": nights,
                "guests": guests,
                "selected_hotels": selected_hotels,
            }
            
            context["price_details"] = price_details
            context["step"] = "show_itinerary"
            self._save(state, context)
            
            return self._show_full_details_with_buttons(context)
            
        except Exception as e:
            logger.error(f"Price calculation error: {e}")
            import traceback
            traceback.print_exc()
            return {"type": "text", "content": f"Error calculating price: {str(e)}"}

    def _show_full_details_with_buttons(self, context: Dict) -> Dict:
        """Show full package details with itinerary and price breakdown with buttons"""
        pkg = context.get("selected_package", {})
        itinerary = pkg.get("itinerary", [])
        price_details = context.get("price_details", {})
        
        nights = price_details.get("nights", 0)
        total_price = price_details.get("total_price", 0)
        total_hotel_price = price_details.get("total_hotel_price", 0)
        total_map_price = price_details.get("total_map_price", 0)
        vehicle_price = price_details.get("vehicle_price", 0)
        vehicle_name = price_details.get("vehicle_name", "None")
        package_margin = price_details.get("package_margin", 0)
        guests = price_details.get("guests", 1)
        hotel_costs = price_details.get("hotel_costs", [])
        selected_hotels = price_details.get("selected_hotels", {})
        
        def format_price(price):
            try:
                return f"Rs.{float(price):,.0f}"
            except (ValueError, TypeError):
                return f"Rs.{price}"
        
        # Build content WITHOUT buttons first
        content = "🏝️ PACKAGE DETAILS\n\n"
        content += f"📦 Package: {pkg.get('package_name', pkg.get('title', 'Package'))}\n"
        content += f"📍 Destination: {context.get('destination')}\n"
        content += f"📅 Dates: {context.get('check_in')} to {context.get('check_out')} ({nights} nights)\n"
        content += f"👥 Guests: {guests}\n"
        content += f"🏨 Hotel Category: {context.get('hotel_category')}\n"
        content += f"🛏️ Room Category: {context.get('room_category')}\n"
        content += f"🚗 Vehicle: {vehicle_name}\n"
        if vehicle_price > 0:
            content += f"💰 Vehicle Price: {format_price(vehicle_price)} (flat for entire trip)\n\n"
        else:
            content += "\n"
        
        content += "📋 ITINERARY\n\n"
        for i, day in enumerate(itinerary[:nights], 1):
            title = day.get("title", f"Day {i}")
            location = day.get("stay_location") or day.get("location", context.get("destination", "N/A"))
            hotel_name = selected_hotels.get(location, context.get('hotel_category', 'Luxury'))
            
            content += f"Day {i}: {title}\n"
            content += f"   Location: {location}\n"
            content += f"   Hotel: {hotel_name}\n"
            content += f"   Vehicle: {vehicle_name}\n\n"
        
        content += "💰 PRICE BREAKDOWN\n\n"
        
        for cost in hotel_costs:
            content += f"🏨 Hotel at {cost.get('location')}:\n"
            content += f"   Name: {cost.get('hotel_name')}\n"
            content += f"   Room: {cost.get('room_category')}\n"
            content += f"   Season: {cost.get('season_name', 'Regular Rate')}\n"
            content += f"   Rooms: {cost.get('rooms_needed')} (Capacity: {cost.get('min_capacity')}-{cost.get('max_capacity')} guests)\n"
            content += f"   Room price: {format_price(cost.get('price_per_room'))}/night\n"
            if cost.get('extra_persons_total', 0) > 0:
                content += f"   Extra persons: {cost.get('extra_persons_total')} @ {format_price(cost.get('extra_person_price'))}/night\n"
            content += f"   Hotel total: {format_price(cost.get('hotel_total'))}\n"
            content += f"   MAP Meal: {format_price(cost.get('map_total'))}\n\n"
        
        content += f"📊 Subtotal Hotel: {format_price(total_hotel_price)}\n"
        content += f"🍽️ Subtotal MAP Meal: {format_price(total_map_price)}\n"
        if vehicle_price > 0:
            content += f"🚗 Vehicle: {format_price(vehicle_price)}\n"
        if package_margin > 0:
            content += f"📈 Package Margin: {format_price(package_margin)}\n"
        content += f"\n💵 TOTAL PACKAGE PRICE: {format_price(total_price)}\n"
        content += "🍽️ Meal Plan: MAP (Breakfast + Dinner included)\n\n"
        content += "Please review the details above and select an option:"
        
        # Return as separate text and then buttons
        # First send the content as text response
        return {
            "type": "buttons",
            "content": content,
            "buttons": [
                {"text": "📖 BOOK NOW", "value": "book_now"},
                {"text": "🚗 Change Vehicle", "value": "change_vehicle"},
                {"text": "🏨 Change Hotel", "value": "change_hotel"},
                {"text": "📦 Other Packages", "value": "other_packages"},
            ]
        }

    def _show_final_summary(self, context: Dict) -> Dict:
        """Show final summary before booking"""
        price_details = context.get("price_details", {})
        total_price = price_details.get("total_price", 0)
        
        def format_price(price):
            try:
                return f"Rs.{float(price):,.0f}"
            except (ValueError, TypeError):
                return f"Rs.{price}"
        
        content = f"PACKAGE SUMMARY\n\n"
        content += f"Package: {context.get('selected_package', {}).get('package_name', 'Package')}\n"
        content += f"Destination: {context.get('destination')}\n"
        content += f"Dates: {context.get('check_in')} to {context.get('check_out')}\n"
        content += f"Guests: {context.get('guests')}\n"
        content += f"Hotel Category: {context.get('hotel_category')}\n"
        content += f"Room Category: {context.get('room_category')}\n"
        content += f"Vehicle: {context.get('vehicle', {}).get('name', 'None')}\n"
        content += f"\nTOTAL PRICE: {format_price(total_price)}\n"
        content += "Meal Plan: MAP (Breakfast + Dinner)\n\n"
        content += "Confirm your booking?"
        
        return {
            "type": "buttons",
            "content": content,
            "buttons": [
                {"text": "Confirm Booking", "value": "confirm_package"},
                {"text": "Change Vehicle", "value": "change_vehicle"},
                {"text": "Change Hotel", "value": "change_hotel"},
                {"text": "Other Packages", "value": "other_packages"},
            ]
        }

    def _confirm_booking(self, context: Dict, phone: str = None) -> Dict:
        """Confirm booking and generate reference"""
        price_details = context.get("price_details", {})
        total_price = price_details.get("total_price", 0)
        
        def format_price(price):
            try:
                return f"Rs.{float(price):,.0f}"
            except (ValueError, TypeError):
                return f"Rs.{price}"
        
        return {
            "type": "text",
            "content": f"BOOKING CONFIRMED\n\nPackage: {context.get('selected_package', {}).get('package_name', 'Package')}\nTotal: {format_price(total_price)}\nReference: PKG{datetime.now().strftime('%Y%m%d%H%M%S')}\n\nThank you for booking with us! Have a wonderful trip."
        }

    def _llm_next_question(self, session: Dict, context: Dict) -> Dict:
        """Fallback to LLM for next question"""
        flow_status = f"""
PACKAGE FLOW STATUS:
- Step: {context.get('step')}
- Destination: {context.get('destination') or 'Not provided'}
- Check-in: {context.get('check_in') or 'Not provided'}
- Check-out: {context.get('check_out') or 'Not provided'}
- Guests: {context.get('guests') or 'Not provided'}

Ask for the next missing information. Use the tools to fetch real data.
"""
        try:
            resp = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": self.get_system_prompt() + "\n\n" + flow_status},
                    *session["history"],
                ],
                temperature=0.3,
            )
            text = resp.choices[0].message.content
            session["history"].append({"role": "assistant", "content": text})
            return {"type": "text", "content": text}
        except Exception as e:
            logger.error(f"LLM error: {e}")
            return {"type": "text", "content": "Sorry, something went wrong. Please try again."}

    @staticmethod
    def _save(state, context):
        if state is not None:
            state["package_data"] = context

    def reset_session(self, phone: str):
        if phone in self.sessions:
            del self.sessions[phone]
            logger.info(f"Package session reset for {phone}")