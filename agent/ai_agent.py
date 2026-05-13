# agent/ai_agent.py - Unified Hotel + Package Booking Agent
import json
import os
import logging
import math
import re
import copy
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from openai import OpenAI
from agent.tools import TravelTools, TOOL_DEFINITIONS

# ── UI card helpers ────────────────────────────────────────────────────────────
from agent.ui_cards import (
    card_welcome,
    card_hotel_categories,
    card_hotel_list,
    card_hotel_rooms,
    card_hotel_summary,
    card_pkg_packages,
    card_pkg_summary,
    fp,
)

logger = logging.getLogger(__name__)

console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)
logger.setLevel(logging.INFO)


# ═══════════════════════════════════════════════════════════════════════════════
# PROMPTS
# ═══════════════════════════════════════════════════════════════════════════════

INTENT_EXTRACTION_PROMPT = """You are a travel booking intent extractor.

Given a user message and today's date, extract as much info as possible.

Return ONLY valid JSON (no markdown, no explanation):
{{
  "service_type": "hotel" | "package" | null,
  "city": "city name" | null,
  "check_in": "YYYY-MM-DD" | null,
  "check_out": "YYYY-MM-DD" | null,
  "guests": integer | null,
  "confidence": "high" | "medium" | "low",
  "confirm_booking": true | false,
  "possible_city": "raw word if it might be a misspelled city" | null
}}

Rules:
- Today is {today}. Convert relative dates like "14 may", "this friday", "next week", "12 to 16 june", "after 10 days" to YYYY-MM-DD.
- If month not specified, assume current year current month. If date has passed, assume next month.
- IMPORTANT: A single date like "12 june" or "june 12" or "12" → set ONLY check_in, leave check_out null.
- "14 to 20 may" → check_in: this year's May 14, check_out: this year's May 20
- "10 people" or "10 guests" or "for 10" or "party of 10" → guests: 10
- A bare integer like "4" or "just 4" or "only 3" almost certainly means the number of guests → set guests to that integer.
- A message that is ONLY a number (e.g. "4", "2", "10") → guests: that number.
- If message mentions hotel/room/stay/accommodation → service_type: "hotel"
- If message mentions package/tour/trip/vacation → service_type: "package"
- If message contains "book now", "confirm", "yes book", "okay book", "proceed", "finalize", "done book", "book it", "yes confirm" → confirm_booking: true
- If a word looks like it could be a city name (proper noun, place-like) but you are not sure it is real, put it in possible_city.
- city should only be set if you are confident it is a real, correctly spelled city.
- Return null for anything not mentioned — do NOT guess.

User message: "{message}"
"""

# ── Package-specific date extraction prompt ──────────────────────────────────
PKG_DATE_EXTRACTION_PROMPT = """You are a travel date extractor. Today is {today}.

The user wants to provide a STARTING DATE for a travel package.

Extract the starting date from: "{message}"

Rules:
- A bare number like "12" means day 12 of the current month ({current_month_name}).
- "12 june" or "june 12" → June 12 of current year {current_year}.
- "tomorrow" → {tomorrow}.
- "after 4 days" → {after_4_days}.
- "next week" → {next_week}.
- If a date resolves to today or past → it is INVALID.
- If no clear date found → null.

Return ONLY valid JSON:
{{
  "start_date": "YYYY-MM-DD" | null,
  "is_past": true | false,
  "error": "reason if invalid" | null
}}
"""

CITY_VALIDATION_PROMPT = """The user is trying to book travel and typed: "{city}"

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

WELCOME_KEYWORDS = {
    "hi", "hii", "hello", "hey", "helo", "hiya", "howdy",
    "start", "begin", "help", "menu", "home", "restart",
    "new booking", "new", "reset", "back", "main menu",
}


# ═══════════════════════════════════════════════════════════════════════════════
# UNIFIED AGENT
# ═══════════════════════════════════════════════════════════════════════════════

class AIHotelAgent:
    """
    Single agent that handles BOTH hotel and package flows.
    Flow is determined by context["service_type"]:
      - None      → welcome / service selection
      - "hotel"   → hotel booking sub-flow
      - "package" → package booking sub-flow (asks ONLY start date, derives end from itinerary)
    """

    def __init__(self):
        self.client = OpenAI(api_key=os.getenv("OPEN_API_KEY"))
        self.sessions: Dict[str, Dict] = {}
        self.available_tools = TOOL_DEFINITIONS
        logger.info("=" * 60)
        logger.info("UNIFIED TRAVEL AGENT INITIALIZED")
        logger.info("=" * 60)

    # ─────────────────────────────────────────────────────────────
    # SESSION / CONTEXT HELPERS
    # ─────────────────────────────────────────────────────────────

    def _session_key(self, phone: str, business_phone: str) -> str:
        return f"{business_phone}:{phone}"

    def _make_tools(self, business_phone: str) -> TravelTools:
        return TravelTools(display_phone=business_phone)

    def _default_context(self, business_phone: str = "default") -> Dict:
        """Single flat context for both flows."""
        return {
            # ── routing ──
            "service_type": None,       # "hotel" | "package" | None
            "flow": "initial",
            "step": "welcome",
            "business_phone": business_phone,
            # ── shared fields ──
            "destination": None,
            "check_in": None,
            "check_out": None,
            "guests": None,
            # ── hotel-only fields ──
            "selected_category": None,
            "selected_hotel": None,
            "selected_room_data": None,
            "meal_plan": None,
            "meal_plan_data": None,
            "price_details": None,
            "meal_details": None,
            "categories_from_api": None,
            "rooms_list": None,
            "hotels_list": None,
            # ── package-only fields ──
            "hotel_category": None,
            "room_category": None,
            "vehicle_category": None,
            "vehicle_slug": None,
            "vehicle": None,
            "packages_list": None,
            "selected_package": None,
            "pkg_price_details": None,
            "hotel_categories": None,
            "room_categories": None,
            "vehicle_types": None,
            "vehicles_list": None,
            "hotel_data_cache": {},
            "selected_hotels": {},
            "date_error": None,
            # ── package date collection step ──
            "pkg_awaiting_start_date": False,
        }

    def _save(self, state, context):
        if state is not None:
            state["data"] = context

    def _generate_and_send_pdf(self, context: Dict, phone: str, business_phone: str, state: dict) -> Dict:
        import os
        from datetime import datetime
        from services.pdf_generator import generate_package_pdf, send_pdf_via_whatsapp
        from database.database import get_whatsapp_config

        pkg = context.get("selected_package", {})
        if not pkg:
            return {"type": "text", "content": "No package selected. Please select a package first."}

        pkg_name = pkg.get("package_name") or pkg.get("title", "package")
        safe_name = "".join(c for c in pkg_name[:30] if c.isalnum() or c in (" ", "-", "_")).rstrip()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        pdf_path = f"generated_pdfs/{safe_name}_{timestamp}.pdf"

        try:
            generate_package_pdf(
                package_data=pkg,
                context=context,
                output_path=pdf_path,
            )
            sender_config = get_whatsapp_config(business_phone)
            sender_phone_number_id = sender_config.get("phone_number_id") if sender_config else None
            caption = f"📄 *{pkg_name}* - Travel Package Details\n\n✅ *PDF Generated Successfully!*"
            result = send_pdf_via_whatsapp(
                to_phone=phone,
                pdf_path=pdf_path,
                caption=caption,
                sender_phone_number_id=sender_phone_number_id,
            )
            if result:
                return {
                    "type": "buttons",
                    "buttons": [
                        {"text": "BOOK NOW", "value": "pkg_book_now"},
                    ],
                }
            else:
                return {
                    "type": "text",
                    "content": "⚠️ *PDF Generation Failed*\n\nUnable to send the PDF. Please try again or click BOOK NOW to proceed."
                }
        except Exception as e:
            logger.error(f"PDF generation error: {e}")
            return {
                "type": "text",
                "content": f"❌ *Error generating PDF:* {str(e)}\n\nPlease try again or contact support."
            }

    # ─────────────────────────────────────────────────────────────
    # INTENT + CITY VALIDATION  (shared)
    # ─────────────────────────────────────────────────────────────

    def _extract_intent(self, message: str) -> Dict:
        today = datetime.now().strftime("%Y-%m-%d")
        prompt = INTENT_EXTRACTION_PROMPT.format(today=today, message=message)
        try:
            resp = self.client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.0,
                response_format={"type": "json_object"},
                max_tokens=300,
            )
            result = json.loads(resp.choices[0].message.content)
            logger.info(f"🧠 Intent: {result}")
            return result
        except Exception as e:
            logger.error(f"Intent extraction error: {e}")
            return {
                "service_type": None, "city": None,
                "check_in": None, "check_out": None,
                "guests": None, "confidence": "low",
                "confirm_booking": False, "possible_city": None,
            }

    def _extract_pkg_start_date(self, message: str) -> Dict:
        """
        Extract ONLY a starting date for package flow.
        Returns {"start_date": "YYYY-MM-DD" | None, "is_past": bool, "error": str | None}
        """
        today = datetime.now()
        tomorrow = today + timedelta(days=1)
        after_4 = today + timedelta(days=4)
        next_week = today + timedelta(days=7)

        import calendar
        month_name = today.strftime("%B")

        prompt = PKG_DATE_EXTRACTION_PROMPT.format(
            today=today.strftime("%Y-%m-%d"),
            current_month_name=month_name,
            current_year=today.year,
            tomorrow=tomorrow.strftime("%Y-%m-%d"),
            after_4_days=after_4.strftime("%Y-%m-%d"),
            next_week=next_week.strftime("%Y-%m-%d"),
            message=message,
        )
        try:
            resp = self.client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.0,
                response_format={"type": "json_object"},
                max_tokens=100,
            )
            result = json.loads(resp.choices[0].message.content)
            logger.info(f"📅 Pkg start date extraction: {result}")

            # Double-check: if start_date is today or past → reject
            if result.get("start_date"):
                try:
                    sd = datetime.strptime(result["start_date"], "%Y-%m-%d").date()
                    if sd <= today.date():
                        return {
                            "start_date": None,
                            "is_past": True,
                            "error": f"*{result['start_date']}* is today or in the past. Please provide a future date."
                        }
                except ValueError:
                    pass
            return result
        except Exception as e:
            logger.error(f"Pkg date extraction error: {e}")
            return {"start_date": None, "is_past": False, "error": None}

    def _validate_city(self, city: str) -> Dict:
        try:
            resp = self.client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[{"role": "user", "content": CITY_VALIDATION_PROMPT.format(city=city)}],
                temperature=0.0,
                response_format={"type": "json_object"},
                max_tokens=100,
            )
            result = json.loads(resp.choices[0].message.content)
            logger.info(f"🏙️ City validation '{city}': {result}")
            return result
        except Exception:
            return {"valid": True, "corrected": None, "message": None}

    def _validate_dates(self, check_in: str, check_out: str) -> Dict:
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

    # ─────────────────────────────────────────────────────────────
    # PACKAGE — DERIVE CHECK-OUT FROM ITINERARY + START DATE
    # ─────────────────────────────────────────────────────────────

    def _derive_pkg_checkout(self, start_date_str: str, itinerary: List[Dict]) -> str:
        """
        Count unique overnight stay days from itinerary (ignore Day 0 travel day
        and last day if it's just a return with no new stay).
        Returns check_out as YYYY-MM-DD = start_date + nights.
        """
        try:
            start_dt = datetime.strptime(start_date_str, "%Y-%m-%d")

            # Count days that have a stay_location (actual hotel nights)
            # Typical pattern: Day 0 = travel, Day 1..N = stay, Day N+1 = return
            # We count total itinerary items - 1 (last day is usually departure/return)
            total_days = len(itinerary)

            # nights = total_days - 1 (last item is usually return day with no new hotel)
            # but if all days have stay_location, use total_days - 1 as nights
            nights = max(total_days - 1, 1)

            check_out_dt = start_dt + timedelta(days=nights)
            logger.info(f"📅 Package: start={start_date_str}, itinerary_days={total_days}, nights={nights}, checkout={check_out_dt.strftime('%Y-%m-%d')}")
            return check_out_dt.strftime("%Y-%m-%d")
        except Exception as e:
            logger.error(f"Derive checkout error: {e}")
            # Fallback: start + 3 nights
            try:
                start_dt = datetime.strptime(start_date_str, "%Y-%m-%d")
                return (start_dt + timedelta(days=3)).strftime("%Y-%m-%d")
            except Exception:
                return start_date_str

    # ─────────────────────────────────────────────────────────────
    # GUEST PARSE HELPER  (shared)
    # ─────────────────────────────────────────────────────────────

    @staticmethod
    def _try_parse_guest_count(message: str) -> Optional[int]:
        stripped = message.strip()
        if re.fullmatch(r'\d+', stripped):
            val = int(stripped)
            return val if 1 <= val <= 50 else None
        m = re.search(
            r'\b(?:just|only|around|about|approx(?:imately)?|we\s+are|there\s+are|total|party\s+of)?\s*(\d{1,2})\b',
            stripped, re.IGNORECASE,
        )
        if m and not re.search(
            r'\bto\b|\bjune\b|\bjuly\b|\baug\b|\bjan\b|\bfeb\b|\bmar\b|\bapr\b'
            r'|\bmay\b|\bsep\b|\boct\b|\bnov\b|\bdec\b', stripped, re.IGNORECASE
        ):
            val = int(m.group(1))
            return val if 1 <= val <= 50 else None
        return None

    # ─────────────────────────────────────────────────────────────
    # MISSING FIELD CHECKERS
    # ─────────────────────────────────────────────────────────────

    def _get_missing_field(self, context: Dict) -> Optional[str]:
        """
        For hotel: service_type → destination → dates (both) → guests
        For package: service_type → destination → check_in (start date only) → guests
        """
        if not context.get("service_type"):
            return "service_type"
        if not context.get("destination"):
            return "destination"
        svc = context.get("service_type")
        if svc == "package":
            # Package only needs start date; check_out is auto-derived later
            if not context.get("check_in"):
                return "dates"
        else:
            if not context.get("check_in") or not context.get("check_out"):
                return "dates"
        if not context.get("guests"):
            return "guests"
        return None

    def _ask_for_field(self, field: str, context: Dict) -> Dict:
        svc = context.get("service_type", "")
        if field == "service_type":
            return self._welcome_message()
        if field == "destination":
            if svc == "package":
                return {"type": "text", "content": "Which destination are you looking for a package in?"}
            return {"type": "text", "content": "Which city are you looking for hotels in?"}
        if field == "dates":
            dest = context.get("destination", "")
            if svc == "package":
                # Ask ONLY starting date for package
                return {
                    "type": "text",
                    "content": (
                        f"📅 *When would you like to start your trip to {dest}?*\n\n"
                        "Please share your *starting date*.\n"
                        "Examples: _15 June_ · _20_ · _tomorrow_ · _after 5 days_"
                    )
                }
            return {
                "type": "text",
                "content": f"What are your check-in and check-out dates for {dest}?"
            }
        if field == "guests":
            return {"type": "text", "content": "How many guests will be travelling?"}
        return {"type": "text", "content": "How can I help with your booking?"}

    # ─────────────────────────────────────────────────────────────
    # WELCOME MESSAGE
    # ─────────────────────────────────────────────────────────────

    def _welcome_message(self) -> Dict:
        return card_welcome()

    # ─────────────────────────────────────────────────────────────
    # TOOL EXECUTION  (hotel flow)
    # ─────────────────────────────────────────────────────────────

    def execute_tool(self, tool_name: str, parameters: Dict, tools: TravelTools) -> Dict:
        logger.info(f"🚀 TOOL: {tool_name} | PARAMS: {json.dumps(parameters, default=str)}")
        try:
            if tool_name == "get_categories":
                return tools.get_categories()
            elif tool_name == "search_hotels_by_category":
                return tools.search_hotels_by_category(
                    parameters.get("category"), parameters.get("location")
                )
            elif tool_name == "get_hotel_rooms":
                return tools.get_hotel_rooms(parameters.get("hotel_name"))
            elif tool_name == "validate_dates":
                return tools.validate_dates(parameters.get("check_in"), parameters.get("check_out"))
            elif tool_name == "calculate_room_price":
                return tools.calculate_room_price(
                    parameters.get("room"), parameters.get("check_in"),
                    parameters.get("check_out"), parameters.get("guests")
                )
            elif tool_name == "calculate_meal_price":
                return tools.calculate_meal_price(
                    parameters.get("meal_type"), parameters.get("meal_plan_data"),
                    parameters.get("guests"), parameters.get("nights")
                )
            else:
                return {"success": False, "error": f"Unknown tool: {tool_name}"}
        except Exception as e:
            logger.error(f"Tool error [{tool_name}]: {e}")
            return {"success": False, "error": str(e)}

    # ─────────────────────────────────────────────────────────────
    # HOTEL FLOW — RESPONSE FORMATTERS
    # ─────────────────────────────────────────────────────────────

    def _format_categories_response(self, context: Dict, error_category: str = None) -> Dict:
        return card_hotel_categories(context, error_category)

    def _format_hotels_response(self, context: Dict) -> Dict:
        return card_hotel_list(context)

    def _format_rooms_response(self, context: Dict) -> Dict:
        return card_hotel_rooms(context)

    def _format_hotel_summary_response(self, context: Dict) -> Dict:
        return card_hotel_summary(context)

    # ─────────────────────────────────────────────────────────────
    # HOTEL FLOW — CONFIRM BOOKING
    # ─────────────────────────────────────────────────────────────

    def _confirm_hotel_booking(self, phone: str, business_phone: str, state: dict) -> Dict:
        ref = f"HOTEL{datetime.now().strftime('%Y%m%d%H%M%S')}"
        logger.info(f"✅ HOTEL BOOKING CONFIRMED: {ref}")
        self._reset_to_welcome(phone, business_phone, state)
        return {
            "type": "text",
            "content": (
                f"✅ *BOOKING CONFIRMED!*\n\n"
                f"Reference: *{ref}*\n\n"
                f"Thank you for booking with us! 🎉\n\n"
                f"Type 'hi' to start a new booking."
            ),
        }

    # ─────────────────────────────────────────────────────────────
    # HOTEL FLOW — PROCEED TO CATEGORIES
    # ─────────────────────────────────────────────────────────────

    def _proceed_to_categories(self, context: Dict, tools: TravelTools, state: dict) -> Dict:
        result = self.execute_tool("get_categories", {}, tools)
        if result.get("success"):
            context["categories_from_api"] = result.get("categories", [])
            context["step"] = "show_categories"
            self._save(state, context)
            return self._format_categories_response(context)
        return {"type": "text", "content": "Trouble fetching hotel categories. Please type 'retry'."}

    # ─────────────────────────────────────────────────────────────
    # PACKAGE FLOW — FETCH & DISPLAY
    # ─────────────────────────────────────────────────────────────

    def _pkg_fetch_hotel_categories(self, context: Dict, tools: TravelTools, state: dict) -> Dict:
        result = tools.get_categories()
        context["hotel_categories"] = result.get("categories", [])
        if not context["hotel_categories"]:
            return {"type": "text", "content": "No hotel categories available. Please try again later."}
        buttons = [{"text": c["name"], "value": c["name"]} for c in context["hotel_categories"]]
        context["step"] = "pkg_ask_hotel_category"
        self._save(state, context)
        return {
            "type": "buttons_grid",
            "content": (
                f"*SELECT HOTEL CATEGORY*\n\n"
                f"*Destination* {context.get('destination')}\n\n"
                f"Choose your preferred hotel type"
            ),
            "buttons": buttons,
        }

    def _pkg_fetch_room_categories(self, context: Dict, tools: TravelTools, state: dict) -> Dict:
        result = tools.get_room_categories()
        logger.info(f"Room categories API response: {result}")
        context["room_categories"] = result.get("room_categories", []) if result.get("success") else []
        if not context["room_categories"]:
            return {"type": "text", "content": "No room categories available. Please try again later."}
        buttons = [{"text": c["name"], "value": c["name"]} for c in context["room_categories"] if c.get("name")]
        context["step"] = "pkg_ask_room_category"
        self._save(state, context)
        return {
            "type": "buttons_grid",
            "content": (
                f"*SELECT ROOM CATEGORY*\n\n"
                f"*Hotel* {context.get('hotel_category')}\n\n"
                f"Choose your preferred room type"
            ),
            "buttons": buttons,
        }

    def _pkg_fetch_vehicle_categories(self, context: Dict, tools: TravelTools, state: dict) -> Dict:
        result = tools.get_vehicle_categories()
        if not result.get("success") or not result.get("vehicle_categories"):
            return {"type": "text", "content": "Unable to fetch vehicle categories. Please try again later."}
        context["vehicle_types"] = result.get("vehicle_categories", [])
        buttons = [{"text": vt["name"], "value": vt["name"]} for vt in context["vehicle_types"]]
        context["step"] = "pkg_ask_vehicle_category"
        self._save(state, context)
        return {
            "type": "buttons_grid",
            "content": (
                f"*SELECT VEHICLE TYPE*\n\n"
                f"Choose how you'd like to travel"
            ),
            "buttons": buttons,
        }

    def _pkg_fetch_vehicles_by_type(self, context: Dict, tools: TravelTools, slug: str, state: dict) -> Dict:
        try:
            result = tools.get_vehicles_by_type(slug)
            if not result.get("success") or not result.get("vehicles"):
                context["vehicle_category"] = None
                context["vehicle_slug"] = None
                self._save(state, context)
                vehicle_cats = context.get("vehicle_types") or []
                if vehicle_cats:
                    buttons = [{"text": vt["name"], "value": vt["name"]} for vt in vehicle_cats]
                    return {
                        "type": "buttons_grid",
                        "content": (
                            f"⚠️ *No vehicles available in {slug} category.*\n\n"
                            f"*SELECT VEHICLE TYPE*\n\n"
                            f"Please choose another vehicle type:"
                        ),
                        "buttons": buttons,
                    }
                return self._pkg_fetch_vehicle_categories(context, tools, state)

            context["vehicles_list"] = result.get("vehicles", [])
            context["step"] = "pkg_ask_vehicle"
            self._save(state, context)

            from agent.ui_cards import card_vehicles_list
            return card_vehicles_list(context)

        except Exception as e:
            logger.error(f"Vehicle fetch error: {e}")
            return {"type": "text", "content": f"Error loading vehicles: {str(e)}"}

    def _pkg_fetch_packages(self, context: Dict, tools: TravelTools, state: dict) -> Dict:
        try:
            result = tools.get_packages(context["destination"])
            if not result.get("success"):
                return {"type": "text", "content": "Unable to fetch packages. Please try again."}
            matched = result.get("packages", [])
            context["packages_list"] = matched
            if matched:
                context["step"] = "pkg_show_packages"
                self._save(state, context)
                return self._pkg_show_packages(context)
            return {"type": "text", "content": f"No packages found for {context['destination']}. Please try a different destination."}
        except Exception as e:
            logger.error(f"Packages error: {e}")
            return {"type": "text", "content": "Unable to fetch packages. Please try again."}

    def _pkg_show_packages(self, context: Dict) -> Dict:
        return card_pkg_packages(context)

    def _parse_date(self, date_str: str) -> Optional[datetime]:
        if not date_str:
            return None
        for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%Y/%m/%d"):
            try:
                return datetime.strptime(date_str, fmt)
            except ValueError:
                continue
        return None

    def _find_matching_season(self, seasons: List[Dict], check_in_date: datetime, check_out_date: datetime) -> Optional[Dict]:
        try:
            for season in seasons:
                season_start = self._parse_date(season.get("starting_date", ""))
                season_end   = self._parse_date(season.get("end_date", ""))
                if not season_start or not season_end:
                    continue
                s_md  = (season_start.month, season_start.day)
                e_md  = (season_end.month,   season_end.day)
                ci_md = (check_in_date.month, check_in_date.day)
                co_md = (check_out_date.month, check_out_date.day)
                if s_md > e_md:
                    if ci_md >= s_md or ci_md <= e_md:
                        return season
                    if co_md >= s_md or co_md <= e_md:
                        return season
                else:
                    if s_md <= ci_md <= e_md:
                        return season
                    if s_md <= co_md <= e_md:
                        return season
            return None
        except Exception as e:
            logger.error(f"Season matching error: {e}")
            return None

    def _get_seasonal_price(self, room: Dict, check_in_date: datetime, check_out_date: datetime) -> tuple:
        base_price = float(room.get("base_price", 0))
        base_extra = float(room.get("extra_person_price", 0))
        matching = self._find_matching_season(room.get("seasons", []), check_in_date, check_out_date)
        if matching:
            try:
                price = float(matching.get("price", base_price))
                extra = float(matching.get("extra_price", base_extra))
                name  = matching.get("season_name", "Seasonal Rate")
                return price, extra, name
            except (ValueError, TypeError):
                pass
        return base_price, base_extra, "Regular Rate"

    def _calculate_rooms_and_extra(self, guests: int, min_cap: int, max_cap: int) -> Dict:
        rooms_needed  = math.ceil(guests / max_cap)
        extra_persons = max(0, guests - (rooms_needed * min_cap))
        return {"rooms_needed": rooms_needed, "extra_persons_total": extra_persons}

    def _get_hotel_for_location(self, location: str, hotel_category: str, room_category: str, tools: TravelTools) -> Optional[Dict]:
        try:
            result = tools.get_hotels_in_location_for_package(location, hotel_category)
            if result.get("success") and result.get("hotels"):
                for hotel in result["hotels"]:
                    hotel_name   = hotel.get("name")
                    rooms_result = tools.get_hotel_rooms(hotel_name)
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

    # ─────────────────────────────────────────────────────────────
    # PACKAGE PRICE CALCULATION  (season-aware, start-date-based)
    # ─────────────────────────────────────────────────────────────

    def _pkg_calculate_and_show_price(self, context: Dict, tools: TravelTools, state: dict) -> Dict:
        """
        Package pricing:
        1. check_in  = user-provided start date
        2. check_out = start_date + itinerary_nights  (auto-derived)
        3. For each unique stay_location in itinerary:
             → fetch hotel for that location + hotel_category
             → find matching room for room_category
             → match room's seasons[] against check_in date
             → use seasonal price if matched, else base_price
        4. Sum hotel costs + MAP meal + vehicle + package_margin
        """
        try:
            pkg           = context.get("selected_package", {})
            itinerary     = pkg.get("itinerary", [])
            check_in_str  = context.get("check_in")
            guests        = context.get("guests", 1)
            hotel_category = context.get("hotel_category")
            room_category  = context.get("room_category")
            vehicle        = context.get("vehicle", {})

            if not check_in_str:
                return {"type": "text", "content": "⚠️ Start date missing. Please provide your travel start date."}

            # ── Auto-derive check_out from itinerary ──────────────
            check_out_str = self._derive_pkg_checkout(check_in_str, itinerary)
            context["check_out"] = check_out_str
            logger.info(f"📦 Package dates: {check_in_str} → {check_out_str}")

            check_in_dt  = datetime.strptime(check_in_str,  "%Y-%m-%d")
            check_out_dt = datetime.strptime(check_out_str, "%Y-%m-%d")
            nights       = (check_out_dt - check_in_dt).days

            # ── Collect unique stay locations from itinerary ──────
            unique_locations, seen = [], set()
            for day in itinerary:
                loc = day.get("stay_location") or day.get("location", "")
                if loc and loc not in seen:
                    seen.add(loc)
                    unique_locations.append(loc)
            if not unique_locations:
                unique_locations = [context.get("destination", "Unknown")]

            hotel_costs       = []
            total_hotel_price = 0
            total_map_price   = 0
            selected_hotels   = {}

            for location in unique_locations:
                hotel_data = self._get_hotel_for_location(location, hotel_category, room_category, tools)
                if hotel_data:
                    room       = hotel_data["room"]
                    hotel_name = hotel_data["hotel_name"]
                    meal_plan  = hotel_data["meal_plan"]
                    min_cap    = int(room.get("minimum_capacity", 2))
                    max_cap    = int(room.get("maximum_capacity", 3))

                    # ── Season-based price using check_in date ────
                    price_per_room, extra_price, season_name = self._get_seasonal_price(
                        room, check_in_dt, check_out_dt
                    )
                    logger.info(
                        f"📍 Location={location} Hotel={hotel_name} "
                        f"Season={season_name} Price={price_per_room} Extra={extra_price}"
                    )

                    map_per_person = float(meal_plan.get("map_price", 0))
                    calc           = self._calculate_rooms_and_extra(guests, min_cap, max_cap)
                    rooms_needed   = calc["rooms_needed"]
                    extra_persons  = calc["extra_persons_total"]
                    hotel_total    = ((price_per_room * rooms_needed) + (extra_persons * extra_price)) * nights
                    map_total      = map_per_person * guests * nights

                    hotel_costs.append({
                        "location":            location,
                        "hotel_name":          hotel_name,
                        "room_category":       room_category,
                        "price_per_room":      price_per_room,
                        "extra_person_price":  extra_price,
                        "rooms_needed":        rooms_needed,
                        "extra_persons_total": extra_persons,
                        "min_capacity":        min_cap,
                        "max_capacity":        max_cap,
                        "hotel_total":         hotel_total,
                        "map_price_per_person": map_per_person,
                        "map_total":           map_total,
                        "season_name":         season_name,
                    })
                    selected_hotels[location] = hotel_name
                    total_hotel_price += hotel_total
                    total_map_price   += map_total
                else:
                    logger.warning(f"⚠️ No hotel found for location={location} category={hotel_category}")
                    hotel_costs.append({
                        "location":            location,
                        "hotel_name":          f"{hotel_category} Hotel",
                        "room_category":       room_category,
                        "price_per_room":      0,
                        "extra_person_price":  0,
                        "rooms_needed":        0,
                        "extra_persons_total": 0,
                        "min_capacity":        2,
                        "max_capacity":        3,
                        "hotel_total":         0,
                        "map_price_per_person": 0,
                        "map_total":           0,
                        "season_name":         "N/A",
                    })
                    selected_hotels[location] = f"{hotel_category} Hotel"

            context["selected_hotels"] = selected_hotels

            # ── Vehicle price (season-aware × nights) ────────────
            vehicle_price        = 0
            vehicle_price_per_day = 0
            vehicle_name         = "None"
            vehicle_season_name  = "Regular Rate"
            if vehicle:
                vehicle_name = vehicle.get("name", "Unknown")
                # Check season on vehicle using check_in date
                v_base = 0
                try:
                    v_base = float(str(vehicle.get("price", 0)).replace(",", ""))
                except (ValueError, TypeError):
                    v_base = 0

                v_seasons = vehicle.get("seasons", [])
                v_matched = self._find_matching_season(v_seasons, check_in_dt, check_out_dt)
                if v_matched:
                    try:
                        v_base = float(str(v_matched.get("price", v_base)).replace(",", ""))
                        vehicle_season_name = v_matched.get("season_name", "Seasonal Rate")
                    except (ValueError, TypeError):
                        pass
                else:
                    vehicle_season_name = "Regular Rate"

                vehicle_price_per_day = v_base
                vehicle_price         = v_base * nights   # ← multiply by nights
                logger.info(
                    f"🚗 Vehicle={vehicle_name} Season={vehicle_season_name} "
                    f"Price/day={v_base} Nights={nights} Total={vehicle_price}"
                )

            # ── Package margin ────────────────────────────────────
            package_margin = 0
            try:
                margin_raw     = pkg.get("package_margin_price_manual", pkg.get("margin", "0"))
                package_margin = float(str(margin_raw).replace(",", "")) if margin_raw else 0
            except (ValueError, TypeError):
                package_margin = 0

            total_price = total_hotel_price + total_map_price + vehicle_price + package_margin

            context["pkg_price_details"] = {
                "hotel_costs":           hotel_costs,
                "total_hotel_price":     total_hotel_price,
                "total_map_price":       total_map_price,
                "vehicle_price":         vehicle_price,          # total = per_day × nights
                "vehicle_price_per_day": vehicle_price_per_day,
                "vehicle_season_name":   vehicle_season_name,
                "vehicle_name":          vehicle_name,
                "package_margin":        package_margin,
                "total_price":           total_price,
                "nights":                nights,
                "guests":                guests,
                "selected_hotels":       selected_hotels,
                "check_in":              check_in_str,
                "check_out":             check_out_str,
            }
            context["step"] = "pkg_show_itinerary"
            self._save(state, context)
            return self._pkg_show_full_details(context)

        except Exception as e:
            logger.error(f"Price calculation error: {e}", exc_info=True)
            return {"type": "text", "content": f"Error calculating price: {str(e)}"}

    def _pkg_show_full_details(self, context: Dict) -> Dict:
        return card_pkg_summary(context)

    def _pkg_show_final_summary(self, context: Dict) -> Dict:
        return card_pkg_summary(context)

    # ─────────────────────────────────────────────────────────────
    # PACKAGE FLOW — CONFIRM BOOKING
    # ─────────────────────────────────────────────────────────────

    def _confirm_package_booking(self, context: Dict, phone: str, business_phone: str, state: dict) -> Dict:
        pd          = context.get("pkg_price_details", {})
        total_price = pd.get("total_price", 0)
        try:
            total_str = fp(total_price)
        except (ValueError, TypeError):
            total_str = f"Rs.{total_price}"
        pkg_name = context.get("selected_package", {}).get("package_name", "Package")
        ref      = f"PKG{datetime.now().strftime('%Y%m%d%H%M%S')}"
        logger.info(f"✅ PACKAGE BOOKING CONFIRMED: {ref}")
        self._reset_to_welcome(phone, business_phone, state)
        return {
            "type": "text",
            "content": (
                f"✅ *BOOKING CONFIRMED!* 🎉\n\n"
                f"📦 *Package:* {pkg_name}\n"
                f"💵 *Total:* {total_str}\n"
                f"🔖 *Reference:* {ref}\n\n"
                f"Thank you for booking with us!\n"
                f"Have a wonderful trip. ✈️\n\n"
                f"Type *'hi'* to start a new booking!"
            ),
        }

    # ─────────────────────────────────────────────────────────────
    # SESSION RESET
    # ─────────────────────────────────────────────────────────────

    def _reset_to_welcome(self, phone: str, business_phone: str, state: dict):
        key   = self._session_key(phone, business_phone)
        fresh = self._default_context(business_phone)
        if key in self.sessions:
            self.sessions[key]["context"] = fresh
            self.sessions[key]["history"] = []
        if state is not None:
            state["data"] = fresh

    def reset_session(self, phone: str, business_phone: str = "default"):
        key = self._session_key(phone, business_phone)
        if key in self.sessions:
            del self.sessions[key]
            logger.info("🗑️ Session deleted")

    # ─────────────────────────────────────────────────────────────
    # MAIN EXECUTE
    # ─────────────────────────────────────────────────────────────

    def execute(self, phone: str, user_message: str, state: dict = None,
                business_phone: str = "default") -> Dict:

        session_key = self._session_key(phone, business_phone)
        tools       = self._make_tools(business_phone)

        logger.info("=" * 60)
        logger.info(f"📱 {phone}  💬 {user_message}")
        logger.info("=" * 60)

        # ── Session init ──────────────────────────────────────────
        if session_key not in self.sessions:
            saved = (state or {}).get("data", {})
            if saved and saved.get("business_phone") == business_phone:
                ctx = {**self._default_context(business_phone), **saved}
            else:
                ctx = self._default_context(business_phone)
            self.sessions[session_key] = {"history": [], "context": ctx}
            logger.info("🆕 New session")

        session = self.sessions[session_key]
        context = session["context"]
        session["history"].append({"role": "user", "content": user_message})
        msg = user_message.strip().lower()

        # ════════════════════════════════════════════════════════
        #  WELCOME / RESET KEYWORDS
        # ════════════════════════════════════════════════════════
        if msg in WELCOME_KEYWORDS or (
            msg in WELCOME_KEYWORDS and context.get("step") == "welcome"
        ):
            if context.get("step") in ("welcome", None) or msg in (
                "hi", "hii", "hello", "hey", "home", "restart",
                "new", "new booking", "reset", "main menu"
            ):
                self._reset_to_welcome(phone, business_phone, state)
                context = self.sessions[session_key]["context"]
                return self._welcome_message()

        svc = context.get("service_type")

        # ════════════════════════════════════════════════════════
        #  GLOBAL BUTTON HANDLERS
        # ════════════════════════════════════════════════════════

        # ── service type selection ────────────────────────────────
        if msg in ("hotel", "package") and not svc:
            context["service_type"] = msg
            svc = msg
            self._save(state, context)
            missing = self._get_missing_field(context)
            if missing and missing != "service_type":
                return self._ask_for_field(missing, context)

        # ════════════════════════════════════════════════════════
        #  HOTEL BUTTON HANDLERS  (unchanged)
        # ════════════════════════════════════════════════════════

        if svc == "hotel":

            if user_message.startswith("view_rooms:"):
                hotel_name = user_message.split(":", 1)[1]
                context["selected_hotel"] = hotel_name
                result = self.execute_tool("get_hotel_rooms", {"hotel_name": hotel_name}, tools)
                if result.get("success"):
                    context["rooms_list"]     = result.get("rooms", [])
                    context["meal_plan_data"] = result.get("meal_plan", {})
                    context["step"]           = "show_rooms"
                    self._save(state, context)
                    return self._format_rooms_response(context)
                return {"type": "text", "content": f"Couldn't fetch rooms for {hotel_name}. Please try another hotel."}

            if user_message.startswith("pick_room:"):
                idx   = int(user_message.split(":", 1)[1])
                rooms = context.get("rooms_list", [])
                if idx < len(rooms):
                    room = rooms[idx]
                    context["selected_room_data"] = room
                    context["selected_room"]      = f"{room.get('category')} – {room.get('type')}"
                    price_result = self.execute_tool(
                        "calculate_room_price",
                        {"room": room, "check_in": context["check_in"],
                         "check_out": context["check_out"], "guests": context["guests"]},
                        tools,
                    )
                    if price_result.get("success"):
                        context["price_details"] = price_result
                        context["step"]          = "select_meal"
                        self._save(state, context)
                        extra_info = ""
                        if price_result.get('extra_people', 0) > 0:
                            extra_info = f"\n  └ Extra ({price_result['extra_people']} persons): Rs.{price_result['extra_total']:,.0f}"
                        return {
                            "type": "buttons",
                            "content": (
                                f"*Room Selected*\n\n"
                                f"*{context.get('selected_hotel')}*\n"
                                f"*Room Category* {room.get('category')}\n"
                                f"*Room Type* {room.get('type')}\n"
                                f"*Room Total* Rs.{price_result['grand_total']:,.0f} "
                                f"({price_result['nights']} nights / {price_result['rooms_needed']} room(s)){extra_info}\n\n"
                                f"Select your *meal plan*"
                            ),
                            "buttons": [
                                {"text": "MAP — Breakfast + Dinner", "value": "map"},
                                {"text": "CP  — Breakfast only",     "value": "cp"},
                                {"text": "EP  — No meals",           "value": "ep"},
                            ],
                        }
                    return {"type": "text", "content": "Couldn't calculate the price. Please try again."}
                return {"type": "text", "content": "Invalid room selection."}

            if msg in ("map", "cp", "ep") and context.get("step") == "select_meal":
                meal_result = self.execute_tool(
                    "calculate_meal_price",
                    {
                        "meal_type": msg,
                        "meal_plan_data": context.get("meal_plan_data", {}),
                        "guests": context.get("guests", 1),
                        "nights": context.get("price_details", {}).get("nights", 1),
                    },
                    tools,
                )
                if meal_result.get("success"):
                    context["meal_plan"]    = msg
                    context["meal_details"] = meal_result
                    context["step"]         = "final_summary"
                    self._save(state, context)
                    return self._format_hotel_summary_response(context)

            if msg == "change_meal":
                context["step"] = "select_meal"
                self._save(state, context)
                return {
                    "type": "buttons",
                    "content": "*Select your meal plan:*",
                    "buttons": [
                        {"text": "MAP — Breakfast + Dinner", "value": "map"},
                        {"text": "CP  — Breakfast only",     "value": "cp"},
                        {"text": "EP  — No meals",           "value": "ep"},
                    ],
                }

            if msg in ("other_hotels", "back_to_hotels"):
                context["step"] = "show_hotels"
                self._save(state, context)
                return self._format_hotels_response(context)

            if msg == "back_to_categories":
                context["step"] = "show_categories"
                self._save(state, context)
                return self._format_categories_response(context)

            if msg == "change_city":
                for k in ("destination", "selected_category", "selected_hotel", "hotels_list",
                          "rooms_list", "selected_room_data", "meal_plan", "meal_details",
                          "price_details", "categories_from_api"):
                    context[k] = None
                context["step"] = "collect_info"
                self._save(state, context)
                return {"type": "text", "content": "Which city would you like to search hotels in?"}

            if msg == "confirm" and context.get("step") == "final_summary":
                return self._confirm_hotel_booking(phone, business_phone, state)

        # ════════════════════════════════════════════════════════
        #  PACKAGE BUTTON HANDLERS
        # ════════════════════════════════════════════════════════

        if svc == "package":
            if msg == "pkg_generate_pdf":
                return self._generate_and_send_pdf(context, phone, business_phone, state)

            # Hotel category selection
            hotel_cats = [c.get("name", "").lower() for c in (context.get("hotel_categories") or [])]
            if msg in hotel_cats and not context.get("hotel_category"):
                context["hotel_category"] = user_message.strip()
                context["step"]           = "pkg_ask_room_category"
                self._save(state, context)
                return self._pkg_fetch_room_categories(context, tools, state)

            # Room category selection
            room_cats = [c.get("name", "").lower() for c in (context.get("room_categories") or [])]
            if msg in room_cats and not context.get("room_category"):
                context["room_category"] = user_message.strip()
                context["step"]          = "pkg_ask_vehicle_category"
                self._save(state, context)
                return self._pkg_fetch_vehicle_categories(context, tools, state)

            # Vehicle category selection
            vehicle_cats      = context.get("vehicle_types") or []
            vehicle_cat_names = [v.get("name", "").lower() for v in vehicle_cats]
            if msg in vehicle_cat_names and not context.get("vehicle_category"):
                matching = [v for v in vehicle_cats if v.get("name", "").lower() == msg]
                if matching:
                    context["vehicle_category"] = matching[0].get("name")
                    context["vehicle_slug"]      = matching[0].get("slug")
                    self._save(state, context)
                    return self._pkg_fetch_vehicles_by_type(context, tools, matching[0].get("slug"), state)

            # Vehicle selection
            if user_message.startswith("select_vehicle_"):
                try:
                    idx      = int(user_message.replace("select_vehicle_", "").strip())
                    vehicles = context.get("vehicles_list", [])
                    if idx < len(vehicles):
                        context["vehicle"] = vehicles[idx]
                        context["step"]    = "pkg_fetch_packages"
                        self._save(state, context)
                        return self._pkg_fetch_packages(context, tools, state)
                except ValueError:
                    pass

            # Package selection
            if user_message.startswith("select_package_"):
                try:
                    idx  = int(user_message.replace("select_package_", "").strip())
                    pkgs = context.get("packages_list", [])
                    if idx < len(pkgs):
                        context["selected_package"] = pkgs[idx]
                        context["step"]             = "pkg_calculate_price"
                        self._save(state, context)
                        return self._pkg_calculate_and_show_price(context, tools, state)
                except ValueError:
                    pass

            if msg == "pkg_other_packages":
                pkgs     = context.get("packages_list", [])
                selected = context.get("selected_package", {})
                others   = [p for p in pkgs if p.get("id") != selected.get("id")]
                if others:
                    context["packages_list"] = others
                    context["step"]          = "pkg_show_packages"
                    self._save(state, context)
                    return self._pkg_show_packages(context)
                return {
                    "type": "buttons",
                    "content": f"No other packages available. Continue with *{selected.get('package_name', 'this package')}*?",
                    "buttons": [{"text": "Continue", "value": "pkg_continue_package"}]
                }

            if msg == "pkg_continue_package":
                context["step"] = "pkg_final_summary"
                self._save(state, context)
                return self._pkg_show_final_summary(context)

            if msg == "pkg_change_vehicle":
                context["vehicle"]          = None
                context["vehicle_category"] = None
                self._save(state, context)
                return self._pkg_fetch_vehicle_categories(context, tools, state)

            if msg == "pkg_change_hotel":
                context["hotel_category"]  = None
                context["room_category"]   = None
                context["selected_hotels"] = {}
                self._save(state, context)
                return self._pkg_fetch_hotel_categories(context, tools, state)

            if msg in ("pkg_book_now", "pkg_confirm_package"):
                return self._confirm_package_booking(context, phone, business_phone, state)

        # ════════════════════════════════════════════════════════
        #  NATURAL LANGUAGE HANDLING
        # ════════════════════════════════════════════════════════

        intent = self._extract_intent(user_message)

        # ── Service type from NL ──────────────────────────────────
        if intent.get("service_type") and not svc:
            context["service_type"] = intent["service_type"]
            svc = intent["service_type"]

        # ── Free-text confirm booking ─────────────────────────────
        if intent.get("confirm_booking"):
            if svc == "hotel" and context.get("step") == "final_summary":
                return self._confirm_hotel_booking(phone, business_phone, state)
            if svc == "package" and context.get("step") in ("pkg_show_itinerary", "pkg_final_summary"):
                return self._confirm_package_booking(context, phone, business_phone, state)

        # ── Guest update mid-flow ─────────────────────────────────
        if intent.get("guests"):
            try:
                new_guests = int(intent["guests"])
                if 1 <= new_guests <= 50:
                    context["guests"] = new_guests
                    logger.info(f"✅ Guests set via LLM intent: {new_guests}")
                    if svc == "package" and context.get("selected_package") and context.get("pkg_price_details"):
                        return self._pkg_calculate_and_show_price(context, tools, state)
                    if svc == "hotel" and context.get("selected_room_data") and context.get("price_details"):
                        room = context["selected_room_data"]
                        pr   = self.execute_tool(
                            "calculate_room_price",
                            {"room": room, "check_in": context["check_in"],
                             "check_out": context["check_out"], "guests": new_guests},
                            tools,
                        )
                        if pr.get("success"):
                            context["price_details"] = pr
                            mr = self.execute_tool(
                                "calculate_meal_price",
                                {"meal_type": context.get("meal_plan", "ep"),
                                 "meal_plan_data": context.get("meal_plan_data", {}),
                                 "guests": new_guests, "nights": pr.get("nights", 1)},
                                tools,
                            )
                            if mr.get("success"):
                                context["meal_details"] = mr
                            self._save(state, context)
                            return self._format_hotel_summary_response(context)
            except (TypeError, ValueError):
                pass

        # ── Bare-number guest shortcut ────────────────────────────
        if (
            not context.get("guests")
            and context.get("destination")
            and context.get("check_in")
            and (svc == "package" or context.get("check_out"))
        ):
            bare = self._try_parse_guest_count(user_message)
            if bare is not None:
                context["guests"] = bare
                logger.info(f"✅ Bare-number guest: {bare}")
                self._save(state, context)
                if svc == "hotel":
                    return self._proceed_to_categories(context, tools, state)
                if svc == "package":
                    return self._pkg_fetch_hotel_categories(context, tools, state)

        # ════════════════════════════════════════════════════════
        #  PACKAGE — DEDICATED START DATE COLLECTION
        #  (runs when svc==package and check_in is missing)
        # ════════════════════════════════════════════════════════
        if svc == "package" and context.get("destination") and not context.get("check_in"):
            date_result = self._extract_pkg_start_date(user_message)

            if date_result.get("start_date"):
                context["check_in"]  = date_result["start_date"]
                context["check_out"] = None   # will be derived later from itinerary
                logger.info(f"✅ Package start date set: {context['check_in']}")
                self._save(state, context)
                # Continue to ask for guests or advance
                if not context.get("guests"):
                    return self._ask_for_field("guests", context)
                # All basics collected — go to hotel category selection
                return self._pkg_fetch_hotel_categories(context, tools, state)

            elif date_result.get("is_past"):
                self._save(state, context)
                return {
                    "type": "text",
                    "content": (
                        f"⚠️ {date_result.get('error', 'That date is in the past.')}\n\n"
                        f"Please provide a *future* starting date.\n"
                        f"Examples: _15 June_ · _20_ · _tomorrow_ · _after 5 days_"
                    )
                }
            else:
                # Could not parse date — ask again
                # But first check if message might be a guest count
                bare = self._try_parse_guest_count(user_message)
                if bare is not None and not context.get("guests"):
                    context["guests"] = bare
                    self._save(state, context)
                    # Now we still need the date
                    return self._ask_for_field("dates", context)

                self._save(state, context)
                return {
                    "type": "text",
                    "content": (
                        f"📅 Please share your *trip starting date* for {context.get('destination')}.\n\n"
                        f"Examples: _15 June_ · _20_ · _tomorrow_ · _after 5 days_"
                    )
                }

        # ── Smart city validation (shared) ────────────────────────
        city_to_check = intent.get("city") or (
            intent.get("possible_city")
            if not context.get("destination") and svc
            else None
        )
        if city_to_check:
            city_candidate = city_to_check.title()
            city_check     = self._validate_city(city_candidate)
            if city_check.get("valid"):
                context["destination"] = city_check.get("corrected") or city_candidate
                logger.info(f"✅ City accepted: {context['destination']}")
            else:
                error_msg = city_check.get("message") or (
                    f"I don't recognise *{city_candidate}* as a city or destination. "
                    f"Please check the spelling and try again."
                )
                self._save(state, context)
                return {"type": "text", "content": f"⚠️ {error_msg}"}

   
        if svc != "package":
           
            if intent.get("check_in"):
                context["check_in"]  = intent["check_in"]
            if intent.get("check_out"):
                context["check_out"] = intent["check_out"]

            # Validate hotel dates
            if context.get("check_in") and context.get("check_out"):
                validation = self._validate_dates(context["check_in"], context["check_out"])
                if not validation.get("valid"):
                    context["check_in"]  = None
                    context["check_out"] = None
                    self._save(state, context)
                    return {
                        "type": "text",
                        "content": (
                            f"⚠️ {validation['error']} Please provide valid dates."
                        )
                    }

        # ── Merge guests (secondary fallback) ─────────────────────
        if not context.get("guests"):
            bare = self._try_parse_guest_count(user_message)
            if bare is not None:
                context["guests"] = bare
                logger.info(f"✅ Bare-number guest fallback (post-intent): {bare}")

        # ── Handle category selection in show_categories step ─────
        if svc == "hotel" and context.get("step") == "show_categories" and context.get("categories_from_api"):
            for cat in context["categories_from_api"]:
                if cat.get("name", "").lower() == msg:
                    context["selected_category"] = cat["name"]
                    result = self.execute_tool(
                        "search_hotels_by_category",
                        {"category": cat["name"], "location": context.get("destination")},
                        tools,
                    )
                    if result.get("success") and result.get("hotels"):
                        context["hotels_list"] = result["hotels"]
                        context["step"]        = "show_hotels"
                        self._save(state, context)
                        return self._format_hotels_response(context)
                    self._save(state, context)
                    return self._format_categories_response(context, error_category=cat["name"])

        # ── Handle hotel selection by number in show_hotels step ──
        if svc == "hotel" and context.get("step") == "show_hotels" and context.get("hotels_list"):
            m = re.search(r"(\d+)", user_message)
            if m:
                idx = int(m.group(1)) - 1
                if 0 <= idx < len(context["hotels_list"]):
                    hotel_name = context["hotels_list"][idx]["name"]
                    context["selected_hotel"] = hotel_name
                    result = self.execute_tool("get_hotel_rooms", {"hotel_name": hotel_name}, tools)
                    if result.get("success"):
                        context["rooms_list"]     = result.get("rooms", [])
                        context["meal_plan_data"] = result.get("meal_plan", {})
                        context["step"]           = "show_rooms"
                        self._save(state, context)
                        return self._format_rooms_response(context)

        self._save(state, context)

        # ── Auto-advance once all basics collected ────────────────
        missing = self._get_missing_field(context)
        if not missing:
            if svc == "hotel" and context.get("step") in ("collect_info", "welcome"):
                return self._proceed_to_categories(context, tools, state)
            if svc == "package" and not context.get("hotel_category"):
                return self._pkg_fetch_hotel_categories(context, tools, state)

        # ── Ask for next missing field ────────────────────────────
        if missing:
            return self._ask_for_field(missing, context)

        return self._welcome_message()