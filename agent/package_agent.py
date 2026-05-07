# agent/package_agent.py - Complete Package Booking Agent with LLM Date Parsing

import json
import os
import logging
import math
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta, date
from openai import OpenAI
from agent.tools import TravelTools
import re

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# PROMPTS
# ═══════════════════════════════════════════════════════════════════════════════

PACKAGE_INTENT_PROMPT = """You are a travel package booking intent extractor.

Given a user message and today's date, extract as much info as possible.

Return ONLY valid JSON (no markdown, no explanation):
{{
  "destination": "city name" | null,
  "check_in": "YYYY-MM-DD" | null,
  "check_out": "YYYY-MM-DD" | null,
  "guests": integer | null,
  "confirm_booking": true | false,
  "possible_city": "raw word if it might be a misspelled city" | null,
  "confidence": "high" | "medium" | "low"
}}

Rules:
- Today is {today}. Convert relative dates like "12 to 14", "12 june to 16 june", "next week", "after 10 days" to YYYY-MM-DD.
- If only day numbers given like "12 to 14" → use current month (or next month if dates passed).
- If month not specified, assume current year. If date has passed, assume next month.
- "10 people" or "10 guests" or "for 10" → guests: 10
- If message contains "book now", "confirm", "yes book", "okay book", "proceed", "finalize", "done book", "book it", "yes confirm" → confirm_booking: true
- destination should only be set if you are confident it is a real, correctly spelled city.
- If a word looks like it could be a city name but you are not sure it is real, put it in possible_city.
- Return null for anything not mentioned — do NOT guess.

User message: "{message}"
"""

CITY_VALIDATION_PROMPT = """The user is trying to book a travel package and typed: "{city}"

Is this a real city, town, hill station, or tourist destination anywhere in the world?
OR is it a misspelling/typo of a real place?

Return ONLY valid JSON:
{{
  "valid": true,
  "corrected": "correct name if different from input, else null",
  "message": null
}}
OR if not valid and not a recognizable misspelling:
{{
  "valid": false,
  "corrected": null,
  "message": "friendly short message explaining you don't recognize this place"
}}
OR if it looks like a misspelling:
{{
  "valid": false,
  "corrected": "the real place name you think they meant",
  "message": "Did you mean [place]? Please confirm or type the correct city name."
}}

Be generous — include small towns, pilgrimage sites, hill stations, villages etc.
Be smart about common misspellings: shila=Shimla, mnsali=Manali, dlehi=Delhi, goa=Goa (valid), mumbai=Mumbai (valid).
Always return the message field — it will be shown directly to the user."""


# ═══════════════════════════════════════════════════════════════════════════════
# PACKAGE AGENT
# ═══════════════════════════════════════════════════════════════════════════════

class PackageAgent:

    def __init__(self):
        self.client = OpenAI(api_key=os.getenv("OPEN_API_KEY"))
        self.tools = None
        self.sessions: Dict[str, Dict] = {}

    def _get_tools(self, business_phone: str = None) -> TravelTools:
        if business_phone:
            return TravelTools(display_phone=business_phone)
        return TravelTools()

    def get_system_prompt(self) -> str:
        return """You are a TRAVEL PACKAGE booking AI agent.

PACKAGE BOOKING FLOW (Follow STRICTLY):
1. Ask: "Which destination are you looking for a package in?"
2. Validate destination is a real city
3. Ask: "What are your travel dates? (check-in and check-out)"
4. Validate dates (no past dates, check-out must be after check-in)
5. Ask: "How many guests will be travelling?"
6. After collecting destination, dates, guests -> show hotel category buttons
7. After hotel category -> show room category buttons
8. After room category -> show vehicle category buttons
9. After vehicle category -> show vehicles in that category
10. After vehicle selection -> fetch and show packages
11. User picks package -> calculate price with hotel + vehicle + margin
12. Show full itinerary with hotel names and price breakdown
13. Show Book Now, Change Vehicle, Change Hotel, Other Packages buttons
14. On Book Now -> booking confirmation and reset session

CRITICAL RULES:
- NEVER hardcode any data — always fetch from API using tools
- NEVER hardcode room categories, hotel categories, or vehicle types
- ALWAYS call get_room_categories() to fetch real room categories from API
- ALWAYS call get_categories() to fetch real hotel categories from API
- ALWAYS call get_vehicle_categories() to fetch real vehicle types from API
- Meal plan is always MAP (Breakfast + Dinner)
- Vehicle price is FLAT for entire trip
- Do NOT use emoji in responses except BOOK NOW button
- Ask ONLY for the next missing field — do not repeat questions already answered
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
            "date_error": None,
        }

    # ─────────────────────────────────────────────────────────────────────────
    # INTENT EXTRACTION  (same pattern as hotel agent)
    # ─────────────────────────────────────────────────────────────────────────

    def _extract_intent(self, message: str) -> Dict:
        today = datetime.now().strftime("%Y-%m-%d")
        prompt = PACKAGE_INTENT_PROMPT.format(today=today, message=message)
        try:
            resp = self.client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.0,
                response_format={"type": "json_object"},
                max_tokens=300,
            )
            result = json.loads(resp.choices[0].message.content)
            logger.info(f"📦 Package intent extracted: {result}")
            return result
        except Exception as e:
            logger.error(f"Package intent extraction error: {e}")
            return {
                "destination": None, "check_in": None, "check_out": None,
                "guests": None, "confirm_booking": False, "possible_city": None,
                "confidence": "low"
            }

    def _validate_city(self, city: str) -> Dict:
        """Same city validation as hotel agent."""
        try:
            resp = self.client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[{"role": "user", "content": CITY_VALIDATION_PROMPT.format(city=city)}],
                temperature=0.0,
                response_format={"type": "json_object"},
                max_tokens=100,
            )
            result = json.loads(resp.choices[0].message.content)
            logger.info(f"🏙️ Package city validation for '{city}': {result}")
            return result
        except Exception:
            return {"valid": True, "corrected": None, "message": None}  # fail open

    def _validate_dates(self, check_in: str, check_out: str) -> Dict:
        """Same date validation as hotel agent."""
        try:
            today = datetime.now().date()
            ci = datetime.strptime(check_in, "%Y-%m-%d").date()
            co = datetime.strptime(check_out, "%Y-%m-%d").date()
            if ci < today:
                return {"valid": False, "error": f"Check-in date {check_in} is in the past."}
            if co <= ci:
                return {"valid": False, "error": "Check-out must be after check-in."}
            return {"valid": True, "nights": (co - ci).days}
        except ValueError:
            return {"valid": False, "error": "Invalid date format."}

    # ─────────────────────────────────────────────────────────────────────────
    # MISSING FIELD CHECKER  (same pattern as hotel agent)
    # ─────────────────────────────────────────────────────────────────────────

    def _get_missing_field(self, context: Dict) -> Optional[str]:
        if not context.get("destination"):
            return "destination"
        if not context.get("check_in") or not context.get("check_out"):
            return "dates"
        if not context.get("guests"):
            return "guests"
        return None

    def _ask_for_field(self, field: str, context: Dict) -> Dict:
        if field == "destination":
            return {"type": "text", "content": "Which destination are you looking for a package in?"}
        if field == "dates":
            dest = context.get("destination", "")
            return {
                "type": "text",
                "content": (
                    f"What are your travel dates for {dest}?\n"
                    "Examples: 12 June to 16 June  |  12 to 16  |  next week  |  after 10 days"
                )
            }
        if field == "guests":
            return {"type": "text", "content": "How many guests will be travelling?"}
        return {"type": "text", "content": "How can I help with your package booking?"}

    # ─────────────────────────────────────────────────────────────────────────
    # CONFIRM BOOKING HELPER
    # ─────────────────────────────────────────────────────────────────────────

    def _confirm_booking_response(self, context: Dict, phone: str, business_phone: str, state: dict) -> Dict:
        pd = context.get("price_details", {})
        total_price = pd.get("total_price", 0)
        try:
            total_str = f"Rs.{float(total_price):,.0f}"
        except (ValueError, TypeError):
            total_str = f"Rs.{total_price}"

        self.reset_session(phone, business_phone=business_phone)
        if state is not None:
            state["package_data"] = self._default_context()

        return {
            "type": "text",
            "content": (
                f"BOOKING CONFIRMED\n\n"
                f"Package: {context.get('selected_package', {}).get('package_name', 'Package')}\n"
                f"Total: {total_str}\n"
                f"Reference: PKG{datetime.now().strftime('%Y%m%d%H%M%S')}\n\n"
                f"Thank you for booking with us! Have a wonderful trip.\n\n"
                f"Type 'hi' to start a new booking!"
            ),
        }

    # ─────────────────────────────────────────────────────────────────────────
    # MAIN ENTRY POINT
    # ─────────────────────────────────────────────────────────────────────────

    def execute(self, phone: str, user_message: str, state: dict = None,
                business_phone: str = "default") -> Dict:

        session_key = f"{business_phone}:{phone}"
        self.tools = self._get_tools(business_phone)

        if session_key not in self.sessions:
            saved = (state or {}).get("package_data", {})
            default = self._default_context()
            if saved and saved.get("flow") == "package":
                for k in default:
                    if k not in saved:
                        saved[k] = default[k]
                ctx = saved
            else:
                ctx = default
            self.sessions[session_key] = {"history": [], "context": ctx}

        session = self.sessions[session_key]
        context = session["context"]
        session["history"].append({"role": "user", "content": user_message})
        msg = user_message.strip().lower()

        # ════════════════════════════════════════════════════════
        #  BUTTON HANDLERS  (hard-coded button values)
        # ════════════════════════════════════════════════════════

        # Hotel category (from API)
        hotel_cats = [c.get("name", "").lower() for c in (context.get("hotel_categories") or [])]
        if msg in hotel_cats and not context.get("hotel_category"):
            context["hotel_category"] = user_message.strip()
            context["step"] = "ask_room_category"
            self._save(state, context)
            return self._fetch_and_show_room_categories(context)

        # Room category (from API)
        room_cats = [c.get("name", "").lower() for c in (context.get("room_categories") or [])]
        if msg in room_cats and not context.get("room_category"):
            context["room_category"] = user_message.strip()
            context["step"] = "ask_vehicle_category"
            self._save(state, context)
            return self._fetch_and_show_vehicle_categories(context)

        # Vehicle category (from API)
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

        # Vehicle selection
        if user_message.startswith("select_vehicle_"):
            try:
                idx = int(user_message.replace("select_vehicle_", "").strip())
                vehicles = context.get("vehicles_list", [])
                if idx < len(vehicles):
                    context["vehicle"] = vehicles[idx]
                    context["step"] = "fetch_packages"
                    self._save(state, context)
                    return self._fetch_and_show_packages(context)
            except ValueError:
                pass

        # Package selection
        if user_message.startswith("select_package_"):
            try:
                idx = int(user_message.replace("select_package_", "").strip())
                pkgs = context.get("packages_list", [])
                if idx < len(pkgs):
                    context["selected_package"] = pkgs[idx]
                    context["step"] = "calculate_price"
                    self._save(state, context)
                    return self._calculate_and_show_price(context, state)
            except ValueError:
                pass

        # Other Packages
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

        if msg == "continue_package":
            context["step"] = "final_summary"
            self._save(state, context)
            return self._show_final_summary(context)

        if msg == "change_vehicle":
            context["vehicle"] = None
            context["vehicle_category"] = None
            context["step"] = "ask_vehicle_category"
            self._save(state, context)
            return self._fetch_and_show_vehicle_categories(context)

        if msg == "change_hotel":
            context["hotel_category"] = None
            context["room_category"] = None
            context["selected_hotels"] = {}
            context["step"] = "ask_hotel_category"
            self._save(state, context)
            return self._fetch_and_show_hotel_categories(context)

        # Confirm booking button
        if msg in ("book_now", "confirm_package"):
            return self._confirm_booking_response(context, phone, business_phone, state)

        # ════════════════════════════════════════════════════════
        #  NATURAL LANGUAGE HANDLING
        #  Same pattern as hotel agent — single LLM call extracts
        #  everything, then we validate and merge.
        # ════════════════════════════════════════════════════════

        intent = self._extract_intent(user_message)

        # ── FIX: Confirm booking via free text ────────────────────
        if intent.get("confirm_booking") and context.get("step") in ("show_itinerary", "final_summary"):
            logger.info("✅ Package free-text booking confirmation detected")
            return self._confirm_booking_response(context, phone, business_phone, state)

        # ── Guest update mid-flow → recalculate if price exists ───
        if intent.get("guests"):
            try:
                new_guests = int(intent["guests"])
                if 1 <= new_guests <= 50:
                    context["guests"] = new_guests
                    if context.get("selected_package") and context.get("price_details"):
                        context["step"] = "calculate_price"
                        self._save(state, context)
                        return self._calculate_and_show_price(context, state)
            except (TypeError, ValueError):
                pass

        # ── Smart city validation (same as hotel agent) ───────────
        # Use confident city from intent, OR possible_city if we're
        # still waiting for a destination.
        city_to_check = intent.get("destination") or (
            intent.get("possible_city")
            if not context.get("destination")
            else None
        )

        if city_to_check:
            city_candidate = city_to_check.title()
            city_check = self._validate_city(city_candidate)
            logger.info(f"🏙️ Package city check for '{city_candidate}': {city_check}")

            if city_check.get("valid"):
                # Accept — use corrected spelling if LLM provided one
                context["destination"] = city_check.get("corrected") or city_candidate
                logger.info(f"✅ Package city accepted: {context['destination']}")
            else:
                # Show LLM's friendly message directly — same as hotel agent
                error_msg = city_check.get("message") or (
                    f"I don't recognise *{city_candidate}* as a city or destination. "
                    f"Please check the spelling and try again."
                )
                self._save(state, context)
                return {"type": "text", "content": f"⚠️ {error_msg}"}

        # ── Merge dates ───────────────────────────────────────────
        if intent.get("check_in"):
            context["check_in"] = intent["check_in"]
        if intent.get("check_out"):
            context["check_out"] = intent["check_out"]

        # ── Validate dates if just received ──────────────────────
        if context.get("check_in") and context.get("check_out"):
            validation = self._validate_dates(context["check_in"], context["check_out"])
            if not validation.get("valid"):
                context["check_in"] = None
                context["check_out"] = None
                self._save(state, context)
                return {
                    "type": "text",
                    "content": (
                        f"⚠️ {validation['error']} Please provide valid dates.\n"
                        "Examples: 12 June to 16 June  |  12 to 16  |  next week"
                    )
                }

        # ── Merge guests (if not already handled above) ───────────
        if not context.get("guests") and intent.get("guests"):
            try:
                g = int(intent["guests"])
                if 1 <= g <= 50:
                    context["guests"] = g
            except (TypeError, ValueError):
                pass

        self._save(state, context)

        # ── Auto-advance once all basics collected ────────────────
        if (context.get("destination") and
                context.get("check_in") and
                context.get("check_out") and
                context.get("guests") and
                not context.get("hotel_category")):
            context["step"] = "ask_hotel_category"
            self._save(state, context)
            return self._fetch_and_show_hotel_categories(context)

        # ── Ask for next missing field (one at a time) ────────────
        missing = self._get_missing_field(context)
        if missing:
            return self._ask_for_field(missing, context)

        # ── Fallback to LLM for anything else ────────────────────
        return self._llm_next_question(session, context)

    # ─────────────────────────────────────────────────────────────────────────
    # FETCH & DISPLAY  — ALL FROM API, NOTHING HARDCODED
    # ─────────────────────────────────────────────────────────────────────────

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
        logger.info(f"Room categories API response: {result}")
        if result.get("success") and result.get("room_categories"):
            context["room_categories"] = result.get("room_categories", [])
        else:
            context["room_categories"] = []
        if not context["room_categories"]:
            return {"type": "text", "content": "No room categories available. Please try again later."}
        buttons = [{"text": c["name"], "value": c["name"]} for c in context["room_categories"] if c.get("name")]
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
        return {"type": "buttons_grid", "content": "Select Vehicle Type:", "buttons": buttons}

    def _fetch_and_show_vehicles_by_type(self, context: Dict, slug: str) -> Dict:
        try:
            result = self.tools.get_vehicles_by_type(slug)
            if not result.get("success") or not result.get("vehicles"):
                return {
                    "type": "text",
                    "content": f"No vehicles available in {slug} category. Please select another type."
                }
            vehicles = result.get("vehicles", [])
            content = f"{slug.upper()} VEHICLES\n"
            content += "Vehicle price is FLAT for entire trip (not per person)\n\n"
            for i, v in enumerate(vehicles):
                name = v.get("name", "Vehicle")
                try:
                    price = float(str(v.get("price", 0)).replace(",", ""))
                    price_str = f"Rs.{price:,.0f}"
                except (ValueError, TypeError):
                    price_str = f"Rs.{v.get('price', 0)}"
                capacity = v.get("capacity", "N/A")
                content += f"{i+1}. {name}\n"
                content += f"   Price: {price_str} (flat for entire trip)\n"
                if str(capacity) != "N/A":
                    content += f"   Capacity: {capacity} persons\n"
                content += "\n"
            buttons = [
                {"text": v.get("name", "Vehicle"), "value": f"select_vehicle_{i}"}
                for i, v in enumerate(vehicles)
            ]
            context["vehicles_list"] = vehicles
            return {"type": "buttons_grid", "content": content, "buttons": buttons}
        except Exception as e:
            logger.error(f"Vehicle fetch error: {e}")
            return {"type": "text", "content": f"Error loading vehicles: {str(e)}"}

    def _fetch_and_show_packages(self, context: Dict) -> Dict:
        try:
            result = self.tools.get_packages(context["destination"])
            if not result.get("success"):
                return {"type": "text", "content": "Unable to fetch packages. Please try again."}
            matched = result.get("packages", [])
            context["packages_list"] = matched
            if matched:
                return self._show_packages(context)
            return {
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
        buttons = [
            {"text": f"Package {i+1}", "value": f"select_package_{i}"}
            for i in range(min(6, len(pkgs)))
        ]
        return {"type": "buttons_grid", "content": content, "buttons": buttons}

    # ─────────────────────────────────────────────────────────────────────────
    # PRICE CALCULATION HELPERS
    # ─────────────────────────────────────────────────────────────────────────

    def _parse_date(self, date_str: str) -> Optional[datetime]:
        if not date_str:
            return None
        for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%Y/%m/%d"):
            try:
                return datetime.strptime(date_str, fmt)
            except ValueError:
                continue
        return None

    def _find_matching_season(self, seasons: List[Dict],
                               check_in_date: datetime,
                               check_out_date: datetime) -> Optional[Dict]:
        """Year-agnostic season matching — same fix as tools.py."""
        try:
            for season in seasons:
                season_start = self._parse_date(season.get("starting_date", ""))
                season_end = self._parse_date(season.get("end_date", ""))
                if not season_start or not season_end:
                    continue

                # Compare month/day only — ignore year on season dates
                s_md  = (season_start.month, season_start.day)
                e_md  = (season_end.month,   season_end.day)
                ci_md = (check_in_date.month, check_in_date.day)
                co_md = (check_out_date.month, check_out_date.day)

                if s_md > e_md:           # season wraps year-end (e.g. Dec–Mar)
                    if ci_md >= s_md or ci_md <= e_md:
                        return season
                    if co_md >= s_md or co_md <= e_md:
                        return season
                else:                     # normal season within one calendar year
                    if s_md <= ci_md <= e_md:
                        return season
                    if s_md <= co_md <= e_md:
                        return season
            return None
        except Exception as e:
            logger.error(f"Season matching error: {e}")
            return None

    def _get_seasonal_price(self, room: Dict,
                             check_in_date: datetime,
                             check_out_date: datetime) -> tuple:
        base_price = float(room.get("base_price", 0))
        base_extra = float(room.get("extra_person_price", 0))
        matching = self._find_matching_season(room.get("seasons", []), check_in_date, check_out_date)
        if matching:
            try:
                price = float(matching.get("price", base_price))
                extra = float(matching.get("extra_price", base_extra))
                name = matching.get("season_name", "Seasonal Rate")
                return price, extra, name
            except (ValueError, TypeError):
                pass
        return base_price, base_extra, "Regular Rate"

    def _calculate_rooms_and_extra(self, guests: int, min_cap: int, max_cap: int) -> Dict:
        rooms_needed = math.ceil(guests / max_cap)
        extra_persons = max(0, guests - (rooms_needed * min_cap))
        return {"rooms_needed": rooms_needed, "extra_persons_total": extra_persons}

    def _get_hotel_for_location(self, location: str,
                                 hotel_category: str,
                                 room_category: str) -> Optional[Dict]:
        try:
            result = self.tools.get_hotels_in_location_for_package(location, hotel_category)
            if result.get("success") and result.get("hotels"):
                for hotel in result["hotels"]:
                    hotel_name = hotel.get("name")
                    rooms_result = self.tools.get_hotel_rooms(hotel_name)
                    if rooms_result.get("success"):
                        for room in rooms_result.get("rooms", []):
                            if room.get("category", "").lower() == room_category.lower():
                                return {
                                    "hotel": hotel,
                                    "room": room,
                                    "hotel_name": hotel_name,
                                    "room_category": room.get("category"),
                                    "meal_plan": rooms_result.get("meal_plan", {}),
                                }
            return None
        except Exception as e:
            logger.error(f"Hotel for location error: {e}")
            return None

    # ─────────────────────────────────────────────────────────────────────────
    # PRICE CALCULATION
    # ─────────────────────────────────────────────────────────────────────────

    def _calculate_and_show_price(self, context: Dict, state=None) -> Dict:
        try:
            pkg = context.get("selected_package", {})
            itinerary = pkg.get("itinerary", [])
            check_in_str = context.get("check_in")
            check_out_str = context.get("check_out")
            guests = context.get("guests", 1)
            hotel_category = context.get("hotel_category")
            room_category = context.get("room_category")
            vehicle = context.get("vehicle", {})

            check_in_dt = datetime.strptime(check_in_str, "%Y-%m-%d")
            check_out_dt = datetime.strptime(check_out_str, "%Y-%m-%d")
            nights = (check_out_dt - check_in_dt).days

            # Unique locations from itinerary
            unique_locations, seen = [], set()
            for day in itinerary:
                loc = day.get("stay_location") or day.get("location", "")
                if loc and loc not in seen:
                    seen.add(loc)
                    unique_locations.append(loc)
            if not unique_locations:
                unique_locations = [context.get("destination", "Unknown")]

            hotel_costs = []
            total_hotel_price = 0
            total_map_price = 0
            selected_hotels = {}

            for location in unique_locations:
                hotel_data = self._get_hotel_for_location(location, hotel_category, room_category)
                if hotel_data:
                    room = hotel_data["room"]
                    hotel_name = hotel_data["hotel_name"]
                    meal_plan = hotel_data["meal_plan"]

                    min_cap = int(room.get("minimum_capacity", 2))
                    max_cap = int(room.get("maximum_capacity", 3))
                    price_per_room, extra_price, season_name = self._get_seasonal_price(
                        room, check_in_dt, check_out_dt
                    )
                    map_per_person = float(meal_plan.get("map_price", 0))

                    calc = self._calculate_rooms_and_extra(guests, min_cap, max_cap)
                    rooms_needed = calc["rooms_needed"]
                    extra_persons = calc["extra_persons_total"]

                    hotel_total = ((price_per_room * rooms_needed) + (extra_persons * extra_price)) * nights
                    map_total = map_per_person * guests * nights

                    hotel_costs.append({
                        "location": location,
                        "hotel_name": hotel_name,
                        "room_category": room_category,
                        "price_per_room": price_per_room,
                        "extra_person_price": extra_price,
                        "rooms_needed": rooms_needed,
                        "extra_persons_total": extra_persons,
                        "min_capacity": min_cap,
                        "max_capacity": max_cap,
                        "hotel_total": hotel_total,
                        "map_price_per_person": map_per_person,
                        "map_total": map_total,
                        "season_name": season_name,
                    })
                    selected_hotels[location] = hotel_name
                    total_hotel_price += hotel_total
                    total_map_price += map_total
                else:
                    hotel_costs.append({
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
                    })
                    selected_hotels[location] = f"{hotel_category} Hotel"

            context["selected_hotels"] = selected_hotels

            # Vehicle price (flat)
            vehicle_price = 0
            vehicle_name = "None"
            if vehicle:
                vehicle_name = vehicle.get("name", "Unknown")
                try:
                    vehicle_price = float(str(vehicle.get("price", 0)).replace(",", ""))
                except (ValueError, TypeError):
                    vehicle_price = 0

            # Package margin
            package_margin = 0
            try:
                margin_raw = pkg.get("package_margin_price_manual", pkg.get("margin", "0"))
                package_margin = float(str(margin_raw).replace(",", ""))
            except (ValueError, TypeError):
                package_margin = 0

            total_price = total_hotel_price + total_map_price + vehicle_price + package_margin

            context["price_details"] = {
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
            context["step"] = "show_itinerary"
            self._save(state, context)
            return self._show_full_details_with_buttons(context)

        except Exception as e:
            logger.error(f"Price calculation error: {e}", exc_info=True)
            return {"type": "text", "content": f"Error calculating price: {str(e)}"}

    def _show_full_details_with_buttons(self, context: Dict) -> Dict:
        pkg = context.get("selected_package", {})
        itinerary = pkg.get("itinerary", [])
        pd = context.get("price_details", {})
        nights = pd.get("nights", 0)
        total_price = pd.get("total_price", 0)
        total_hotel = pd.get("total_hotel_price", 0)
        total_map = pd.get("total_map_price", 0)
        vehicle_price = pd.get("vehicle_price", 0)
        vehicle_name = pd.get("vehicle_name", "None")
        package_margin = pd.get("package_margin", 0)
        guests = pd.get("guests", 1)
        hotel_costs = pd.get("hotel_costs", [])
        selected_hotels = pd.get("selected_hotels", {})

        def fp(price):
            try:
                return f"Rs.{float(price):,.0f}"
            except (ValueError, TypeError):
                return f"Rs.{price}"

        content = "PACKAGE DETAILS\n\n"
        content += f"Package: {pkg.get('package_name', pkg.get('title', 'Package'))}\n"
        content += f"Destination: {context.get('destination')}\n"
        content += f"Dates: {context.get('check_in')} to {context.get('check_out')} ({nights} nights)\n"
        content += f"Guests: {guests}\n"
        content += f"Hotel Category: {context.get('hotel_category')}\n"
        content += f"Room Category: {context.get('room_category')}\n"
        content += f"Vehicle: {vehicle_name}"
        if vehicle_price > 0:
            content += f" ({fp(vehicle_price)} flat for entire trip)"
        content += "\n\n"

        content += "ITINERARY\n\n"
        for i, day in enumerate(itinerary[:nights], 1):
            title = day.get("title", f"Day {i}")
            loc = day.get("stay_location") or day.get("location", context.get("destination", "N/A"))
            hotel_name = selected_hotels.get(loc, context.get("hotel_category", "Hotel"))
            content += f"Day {i}: {title}\n"
            content += f"   Location: {loc}\n"
            content += f"   Hotel: {hotel_name}\n"
            content += f"   Vehicle: {vehicle_name}\n\n"

        content += "PRICE BREAKDOWN\n\n"
        for cost in hotel_costs:
            content += f"Hotel at {cost.get('location')}:\n"
            content += f"   Name: {cost.get('hotel_name')}\n"
            content += f"   Room: {cost.get('room_category')}\n"
            content += f"   Season: {cost.get('season_name', 'Regular Rate')}\n"
            content += f"   Rooms: {cost.get('rooms_needed')} (Capacity: {cost.get('min_capacity')}-{cost.get('max_capacity')} guests)\n"
            content += f"   Room price: {fp(cost.get('price_per_room'))}/night\n"
            if cost.get("extra_persons_total", 0) > 0:
                content += (
                    f"   Extra persons: {cost.get('extra_persons_total')} "
                    f"@ {fp(cost.get('extra_person_price'))}/night\n"
                )
            content += f"   Hotel total: {fp(cost.get('hotel_total'))}\n"
            content += f"   MAP Meal: {fp(cost.get('map_total'))}\n\n"

        content += f"Subtotal Hotel: {fp(total_hotel)}\n"
        content += f"Subtotal MAP Meal: {fp(total_map)}\n"
        if vehicle_price > 0:
            content += f"Vehicle: {fp(vehicle_price)}\n"
        if package_margin > 0:
            content += f"Package Margin: {fp(package_margin)}\n"
        content += f"\nTOTAL PACKAGE PRICE: {fp(total_price)}\n"
        content += "Meal Plan: MAP (Breakfast + Dinner included)\n\n"
        content += "Please review the details above and select an option:"

        return {
            "type": "buttons",
            "content": content,
            "buttons": [
                {"text": "BOOK NOW", "value": "book_now"},
                {"text": "Change Vehicle", "value": "change_vehicle"},
                {"text": "Change Hotel", "value": "change_hotel"},
                {"text": "Other Packages", "value": "other_packages"},
            ],
        }

    def _show_final_summary(self, context: Dict) -> Dict:
        pd = context.get("price_details", {})
        total_price = pd.get("total_price", 0)

        def fp(price):
            try:
                return f"Rs.{float(price):,.0f}"
            except (ValueError, TypeError):
                return f"Rs.{price}"

        content = (
            f"PACKAGE SUMMARY\n\n"
            f"Package: {context.get('selected_package', {}).get('package_name', 'Package')}\n"
            f"Destination: {context.get('destination')}\n"
            f"Dates: {context.get('check_in')} to {context.get('check_out')}\n"
            f"Guests: {context.get('guests')}\n"
            f"Hotel Category: {context.get('hotel_category')}\n"
            f"Room Category: {context.get('room_category')}\n"
            f"Vehicle: {context.get('vehicle', {}).get('name', 'None')}\n\n"
            f"TOTAL PRICE: {fp(total_price)}\n"
            f"Meal Plan: MAP (Breakfast + Dinner)\n\n"
            f"Confirm your booking?"
        )
        return {
            "type": "buttons",
            "content": content,
            "buttons": [
                {"text": "Confirm Booking", "value": "confirm_package"},
                {"text": "Change Vehicle", "value": "change_vehicle"},
                {"text": "Change Hotel", "value": "change_hotel"},
                {"text": "Other Packages", "value": "other_packages"},
            ],
        }

    # ─────────────────────────────────────────────────────────────────────────
    # LLM FALLBACK  (only for truly ambiguous cases)
    # ─────────────────────────────────────────────────────────────────────────

    def _llm_next_question(self, session: Dict, context: Dict) -> Dict:
        flow_status = f"""
PACKAGE FLOW STATUS:
- Step: {context.get('step')}
- Destination: {context.get('destination') or 'Not provided'}
- Check-in: {context.get('check_in') or 'Not provided'}
- Check-out: {context.get('check_out') or 'Not provided'}
- Guests: {context.get('guests') or 'Not provided'}
- Hotel Category: {context.get('hotel_category') or 'Not selected'}
- Room Category: {context.get('room_category') or 'Not selected'}
- Vehicle: {context.get('vehicle', {}).get('name') if context.get('vehicle') else 'Not selected'}

Ask ONLY for the next missing piece of information. Do NOT ask for anything already collected above.
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

    # ─────────────────────────────────────────────────────────────────────────
    # UTILS
    # ─────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _save(state, context):
        if state is not None:
            state["package_data"] = context

    def reset_session(self, phone: str, business_phone: str = "default"):
        session_key = f"{business_phone}:{phone}"
        if session_key in self.sessions:
            del self.sessions[session_key]
            logger.info(f"Package session reset for {session_key}")