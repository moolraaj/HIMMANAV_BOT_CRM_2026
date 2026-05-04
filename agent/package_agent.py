"""
PACKAGE FLOW (separate from hotel flow)
"""
import json
import os
import logging
import requests
import re
from typing import Dict, Any, List, Optional
from datetime import datetime
from openai import OpenAI
from agent.tools import TravelTools

logger = logging.getLogger(__name__)

# API endpoints
PACKAGES_API = "https://silver-spoonbill-286441.hostingersite.com/wp-json/hm/v1/packages?phone=919816440734"
HOTELS_API = "https://silver-spoonbill-286441.hostingersite.com/wp-json/hm/v1/hotels"


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
6. After collecting destination, dates, guests → show hotel category buttons
7. After hotel category → show room category buttons  
8. After room category → fetch and show packages
9. User picks package → calculate price with hotel (from stay_location) + margin
10. Show itinerary with hotel names and price breakdown
11. Show Book Now, Change Hotel, Other Packages buttons
12. On confirm → booking confirmation

CRITICAL RULES:
- NEVER ask for destination/dates/guests again once collected
- Meal plan is always MAP (no need to ask user)
- Hotel is determined by stay_location in each itinerary day
- Calculate hotel price based on stay_location, hotel category, room category, and seasonal pricing
- If no season match, use base_price and extra_person_price from room
- Calculate rooms needed based on room capacity and number of guests
- Add package margin from package_margin_price_manual
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
            "packages_list": None,
            "selected_package": None,
            "price_details": None,
            "hotel_categories": None,
            "room_categories": None,
        }

    def execute(self, phone: str, user_message: str, state: dict = None) -> Dict:
        # Session bootstrap
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
            context["step"] = "fetch_packages"
            self._save(state, context)
            return self._fetch_and_show_packages(context)

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

        # Change Hotel button
        if msg == "change_hotel":
            context["hotel_category"] = None
            context["room_category"] = None
            context["step"] = "ask_hotel_category"
            self._save(state, context)
            return self._fetch_and_show_hotel_categories(context)

        # Book Now button
        if msg == "book_now":
            context["step"] = "booking_confirmation"
            self._save(state, context)
            return self._confirm_booking(context)

        # Confirm booking button
        if msg in ("confirm_package", "confirm", "book") and context.get("step") in ["final_summary", "booking_confirmation"]:
            response = self._confirm_booking(context)
            self.reset_session(phone)
            if state is not None:
                state["package_data"] = self._default_context()
            return response

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
- "me and my wife" = 2, "couple" = 2, "family of 4" = 4
- "we are 4 people" = 4, "we are 8 people" = 8

Already collected (do NOT extract these again):
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
            if 1 <= g <= 20:
                context["guests"] = g

    # ═══════════════════════════════════════════════════════════════════════
    # FETCH & DISPLAY METHODS
    # ═══════════════════════════════════════════════════════════════════════

    def _fetch_and_show_hotel_categories(self, context: Dict) -> Dict:
        result = self.tools.get_categories()
        context["hotel_categories"] = result.get("categories", [])
        buttons = [{"text": c["name"], "value": c["name"]} for c in context["hotel_categories"]]
        return {
            "type": "buttons_grid",
            "content": f"Select Hotel Category in {context.get('destination')}\n\nPlease choose your preferred hotel type:",
            "buttons": buttons,
        }

    def _fetch_and_show_room_categories(self, context: Dict) -> Dict:
        result = self.tools.get_room_categories()
        context["room_categories"] = result.get("room_categories", []) if result.get("success") else []
        buttons = [{"text": c["name"], "value": c["name"]} for c in context["room_categories"]]
        return {
            "type": "buttons_grid",
            "content": "Select Room Category\n\nChoose your preferred room type:",
            "buttons": buttons,
        }

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
        return {"type": "buttons_grid", "content": content, "buttons": buttons}

    # ═══════════════════════════════════════════════════════════════════════
    # HOTEL & PRICE CALCULATION METHODS
    # ═══════════════════════════════════════════════════════════════════════

    def _get_hotel_for_location(self, location: str, hotel_category: str, room_category: str) -> Optional[Dict]:
        """Get hotel details for a specific location based on user's selected categories"""
        try:
            response = requests.get(HOTELS_API, timeout=15)
            
            if response.status_code != 200:
                logger.warning(f"Hotel API returned {response.status_code}")
                return None
                
            hotels = response.json()
            
            if isinstance(hotels, dict):
                hotels = hotels.get("data", hotels.get("hotels", []))
            
            for hotel in hotels:
                hotel_cat = hotel.get("category", "").lower()
                hotel_location = hotel.get("location", "").lower()
                
                if hotel_cat == hotel_category.lower() and location.lower() in hotel_location:
                    rooms = hotel.get("rooms", [])
                    for room in rooms:
                        room_cat = room.get("room_category", "").lower()
                        if room_cat == room_category.lower():
                            return {
                                "hotel": hotel,
                                "room": room,
                                "hotel_name": hotel.get("hotel_name"),
                                "room_category": room.get("room_category")
                            }
            
            # Fallback: try to find any hotel in this location
            for hotel in hotels:
                hotel_location = hotel.get("location", "").lower()
                if location.lower() in hotel_location:
                    rooms = hotel.get("rooms", [])
                    for room in rooms:
                        room_cat = room.get("room_category", "").lower()
                        if room_cat == room_category.lower():
                            return {
                                "hotel": hotel,
                                "room": room,
                                "hotel_name": hotel.get("hotel_name"),
                                "room_category": room.get("room_category")
                            }
            
            logger.warning(f"No hotel found in {location} with category {hotel_category}")
            return None
            
        except Exception as e:
            logger.error(f"Error fetching hotel for {location}: {e}")
            return None

    def _get_room_price(self, room: Dict, check_in_date: datetime, guests: int) -> Dict:
        """
        Get room price based on:
        1. Seasonal price if date matches season
        2. Base price if no season match
        3. Calculate extra person charges based on room capacity
        """
        try:
            # Get base prices from room
            base_price = float(room.get("base_price", 0))
            extra_person_price = float(room.get("extra_person_price", 0))
            min_capacity = int(room.get("minimum_capacity", 1))
            max_capacity = int(room.get("maximum_capacity", 4))
            
            # Default to base price
            applicable_price = base_price
            
            # Check for seasonal pricing
            seasons = room.get("seasons", [])
            for season in seasons:
                season_name = season.get("season_name", "").lower()
                try:
                    season_price = float(season.get("price", base_price))
                except (ValueError, TypeError):
                    season_price = base_price
                
                # Parse season based on month ranges
                if "april" in season_name and "june" in season_name:
                    if 4 <= check_in_date.month <= 6:
                        applicable_price = season_price
                        logger.info(f"Season matched: {season_name} with price {applicable_price}")
                        break
                elif "july" in season_name and "september" in season_name:
                    if 7 <= check_in_date.month <= 9:
                        applicable_price = season_price
                        logger.info(f"Season matched: {season_name} with price {applicable_price}")
                        break
                elif "october" in season_name and "november" in season_name:
                    if 10 <= check_in_date.month <= 11:
                        applicable_price = season_price
                        logger.info(f"Season matched: {season_name} with price {applicable_price}")
                        break
                elif "december" in season_name or "winter" in season_name:
                    if check_in_date.month == 12 or check_in_date.month <= 3:
                        applicable_price = season_price
                        logger.info(f"Season matched: {season_name} with price {applicable_price}")
                        break
                elif "spring" in season_name or "summer" in season_name:
                    if 3 <= check_in_date.month <= 6:
                        applicable_price = season_price
                        logger.info(f"Season matched: {season_name} with price {applicable_price}")
                        break
            
            # Calculate number of rooms needed based on max capacity
            rooms_needed = 1
            if guests > max_capacity:
                rooms_needed = (guests + max_capacity - 1) // max_capacity
            
            # Calculate guests per room
            guests_per_room = guests / rooms_needed
            
            # Calculate extra persons per room (beyond minimum capacity)
            extra_persons_per_room = max(0, guests_per_room - min_capacity)
            
            # Calculate nightly price per room
            nightly_price_per_room = applicable_price + (extra_persons_per_room * extra_person_price)
            
            logger.info(f"Room calculation details:")
            logger.info(f"  Base price: {base_price}")
            logger.info(f"  Applied price: {applicable_price}")
            logger.info(f"  Extra person price: {extra_person_price}")
            logger.info(f"  Min capacity: {min_capacity}, Max capacity: {max_capacity}")
            logger.info(f"  Total guests: {guests}")
            logger.info(f"  Rooms needed: {rooms_needed}")
            logger.info(f"  Guests per room: {guests_per_room:.1f}")
            logger.info(f"  Extra persons per room: {extra_persons_per_room}")
            logger.info(f"  Nightly price per room: {nightly_price_per_room}")
            
            return {
                "base_price": base_price,
                "applied_price": applicable_price,
                "extra_person_price": extra_person_price,
                "min_capacity": min_capacity,
                "max_capacity": max_capacity,
                "rooms_needed": rooms_needed,
                "extra_persons_per_room": extra_persons_per_room,
                "nightly_price_per_room": nightly_price_per_room,
                "season_applied": applicable_price != base_price,
            }
            
        except Exception as e:
            logger.error(f"Room price calculation error: {e}")
            return {
                "base_price": 0,
                "applied_price": 0,
                "extra_person_price": 0,
                "min_capacity": 1,
                "max_capacity": 2,
                "rooms_needed": 1,
                "extra_persons_per_room": 0,
                "nightly_price_per_room": 0,
                "season_applied": False,
            }

    def _calculate_and_show_price(self, context: Dict, state=None) -> Dict:
        """Calculate complete package price with hotel and margin"""
        try:
            pkg = context.get("selected_package", {})
            itinerary = pkg.get("itinerary", [])
            check_in_str = context.get("check_in")
            check_out_str = context.get("check_out")
            guests = context.get("guests", 1)
            hotel_category = context.get("hotel_category")
            room_category = context.get("room_category")
            
            check_in = datetime.strptime(check_in_str, "%Y-%m-%d")
            check_out = datetime.strptime(check_out_str, "%Y-%m-%d")
            nights = (check_out - check_in).days
            
            # Get unique stay locations from itinerary
            unique_locations = {}
            for day in itinerary:
                location = day.get("stay_location") or day.get("location", "")
                if location and location not in unique_locations:
                    unique_locations[location] = day
            
            logger.info(f"Unique locations from itinerary: {list(unique_locations.keys())}")
            
            # If no locations found, use destination as fallback
            if not unique_locations:
                unique_locations[context.get("destination", "Unknown")] = {}
            
            # Calculate hotel cost for each unique location
            hotel_costs = []
            total_hotel_price = 0
            hotel_info = []
            
            for location in unique_locations.keys():
                hotel_data = self._get_hotel_for_location(location, hotel_category, room_category)
                
                if hotel_data:
                    room = hotel_data.get("room", {})
                    hotel_name = hotel_data.get("hotel_name", "Unknown Hotel")
                    
                    # Get room price calculation
                    price_calc = self._get_room_price(room, check_in, guests)
                    
                    rooms_needed = price_calc.get("rooms_needed", 1)
                    nightly_price_per_room = price_calc.get("nightly_price_per_room", 0)
                    
                    # Total for this location (price per night * nights * rooms needed)
                    total_for_location = nightly_price_per_room * nights * rooms_needed
                    
                    hotel_costs.append({
                        "location": location,
                        "hotel_name": hotel_name,
                        "room_category": room_category,
                        "base_price": price_calc.get("base_price", 0),
                        "applied_price": price_calc.get("applied_price", 0),
                        "extra_person_price": price_calc.get("extra_person_price", 0),
                        "rooms_needed": rooms_needed,
                        "extra_persons_per_room": price_calc.get("extra_persons_per_room", 0),
                        "nightly_price_per_room": nightly_price_per_room,
                        "total": total_for_location,
                    })
                    total_hotel_price += total_for_location
                    
                    hotel_info.append({
                        "location": location,
                        "hotel_name": hotel_name,
                        "rooms_needed": rooms_needed,
                    })
                    
                    logger.info(f"Location: {location} - Hotel: {hotel_name} - Total: {total_for_location}")
                else:
                    logger.warning(f"No hotel found for location: {location}")
            
            # Package margin (fixed amount from package_margin_price_manual)
            package_margin = 0
            margin_manual = pkg.get("package_margin_price_manual", "0")
            
            try:
                if margin_manual:
                    package_margin = float(str(margin_manual).replace(",", ""))
            except (ValueError, TypeError):
                package_margin = 0
            
            total_price = total_hotel_price + package_margin
            
            price_details = {
                "hotel_costs": hotel_costs,
                "total_hotel_price": total_hotel_price,
                "package_margin": package_margin,
                "total_price": total_price,
                "nights": nights,
                "guests": guests,
                "hotel_info": hotel_info,
            }
            
            context["price_details"] = price_details
            context["step"] = "show_itinerary"
            self._save(state, context)
            
            return self._show_itinerary_with_price(context)
            
        except Exception as e:
            logger.error(f"Price calculation error: {e}")
            import traceback
            traceback.print_exc()
            return {"type": "text", "content": f"Error calculating price: {str(e)}"}

    def _show_itinerary_with_price(self, context: Dict) -> Dict:
        """Show itinerary with daily hotel details and price breakdown"""
        pkg = context.get("selected_package", {})
        itinerary = pkg.get("itinerary", [])
        price_details = context.get("price_details", {})
        
        nights = price_details.get("nights", 0)
        total_price = price_details.get("total_price", 0)
        total_hotel_price = price_details.get("total_hotel_price", 0)
        package_margin = price_details.get("package_margin", 0)
        guests = price_details.get("guests", 1)
        hotel_costs = price_details.get("hotel_costs", [])
        
        # Format prices safely
        def format_price(price):
            try:
                return f"Rs.{float(price):,.0f}"
            except (ValueError, TypeError):
                return f"Rs.{price}"
        
        content = f"PACKAGE DETAILS\n\n"
        content += f"Package: {pkg.get('package_name', pkg.get('title', 'Package'))}\n"
        content += f"Destination: {context.get('destination')}\n"
        content += f"Dates: {context.get('check_in')} to {context.get('check_out')} ({nights} nights)\n"
        content += f"Guests: {guests}\n"
        content += f"Hotel Category: {context.get('hotel_category')}\n"
        content += f"Room Category: {context.get('room_category')}\n\n"
        
        content += "ITINERARY\n\n"
        for i, day in enumerate(itinerary[:nights], 1):
            title = day.get("title", f"Day {i}")
            location = day.get("stay_location") or day.get("location", context.get("destination", "N/A"))
            
            # Find hotel name for this location
            hotel_name = context.get('hotel_category', 'Luxury')
            for cost in hotel_costs:
                if cost.get("location") == location:
                    hotel_name = cost.get("hotel_name", hotel_name)
                    break
            
            content += f"Day {i}: {title}\n"
            content += f"Location: {location}\n"
            content += f"Hotel: {hotel_name}\n\n"
        
        content += "PRICE BREAKDOWN\n\n"
        
        # Show detailed hotel costs
        for cost in hotel_costs:
            content += f"Hotel at {cost.get('location')}:\n"
            content += f"  - {cost.get('hotel_name')}\n"
            content += f"  - Room: {cost.get('room_category')}\n"
            content += f"  - Rooms needed: {cost.get('rooms_needed')}\n"
            if cost.get('applied_price') != cost.get('base_price'):
                content += f"  - Seasonal price: {format_price(cost.get('applied_price'))} per night\n"
            else:
                content += f"  - Base price: {format_price(cost.get('applied_price'))} per night\n"
            if cost.get('extra_persons_per_room', 0) > 0:
                content += f"  - Extra persons: {cost.get('extra_persons_per_room')} @ {format_price(cost.get('extra_person_price'))} each\n"
            content += f"  - Subtotal: {format_price(cost.get('total'))}\n\n"
        
        content += f"Subtotal Hotel: {format_price(total_hotel_price)}\n"
        if package_margin > 0:
            content += f"Package Margin: {format_price(package_margin)}\n"
        content += f"\nTOTAL PACKAGE PRICE: {format_price(total_price)}\n"
        content += "Meal Plan: MAP (Breakfast + Dinner included)\n\n"
        
        content += "Please review the details above."
        
        buttons = [
            {"text": "Book Now", "value": "book_now"},
            {"text": "Change Hotel", "value": "change_hotel"},
            {"text": "Other Packages", "value": "other_packages"},
        ]
        
        return {
            "type": "buttons",
            "content": content,
            "buttons": buttons,
        }

    def _show_final_summary(self, context: Dict) -> Dict:
        """Show final summary before booking confirmation"""
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
        content += f"Hotel: {context.get('hotel_category')}\n"
        content += f"Room: {context.get('room_category')}\n"
        content += f"\nTOTAL PRICE: {format_price(total_price)}\n"
        content += "Meal Plan: MAP (Breakfast + Dinner)\n\n"
        content += "Confirm your booking?"
        
        buttons = [
            {"text": "Confirm Booking", "value": "confirm_package"},
            {"text": "Change Hotel", "value": "change_hotel"},
            {"text": "Other Packages", "value": "other_packages"},
        ]
        
        return {
            "type": "buttons",
            "content": content,
            "buttons": buttons,
        }

    def _confirm_booking(self, context: Dict) -> Dict:
        """Confirm the booking"""
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
        """Generate next question using LLM"""
        flow_status = f"""
PACKAGE FLOW STATUS:
- Step: {context.get('step')}
- Destination: {context.get('destination') or 'Not provided'}
- Check-in: {context.get('check_in') or 'Not provided'}
- Check-out: {context.get('check_out') or 'Not provided'}
- Guests: {context.get('guests') or 'Not provided'}

Ask for the next missing information.
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