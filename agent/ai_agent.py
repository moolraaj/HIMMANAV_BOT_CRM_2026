# agent/ai_agent.py - Complete Hotel and Package Booking AI Agent
# FIXED: Forces consistent flow across all business numbers

import json
import os
import logging
from typing import Dict, Any, List
from openai import OpenAI
from agent.tools import TravelTools, TOOL_DEFINITIONS
from agent.package_agent import PackageAgent
from datetime import datetime
import re

logger = logging.getLogger(__name__)

class AIHotelAgent:
    def __init__(self):
        self.client = OpenAI(api_key=os.getenv("OPEN_API_KEY"))
        self.package_agent = PackageAgent()
        self.sessions = {}

    def _session_key(self, phone: str, business_phone: str) -> str:
        return f"{business_phone}:{phone}"

    def _make_tools(self, business_phone: str) -> TravelTools:
        """Create TravelTools instance scoped to the business phone number."""
        return TravelTools(display_phone=business_phone)

    def get_system_prompt(self) -> str:
        return """You are a hotel booking AI agent with REAL data access.

FIRST: Ask user "Are you looking for hotels or travel packages?"
- If hotels, proceed with hotel flow
- If packages, you will respond: "Let me help you book a travel package"

╔═══════════════════════════════════════════════════════════════════════════════╗
║                    HOTEL BOOKING FLOW - STRICT ORDER                          ║
║                    DO NOT SKIP ANY STEP!                                      ║
╚═══════════════════════════════════════════════════════════════════════════════╝

STEP 1: Ask "Which city are you looking for hotels in?"
STEP 2: User provides city -> Validate it's real (use your knowledge)
STEP 3: Ask "What are your check-in and check-out dates?"
STEP 4: Validate dates (must be future, check-out after check-in)
STEP 5: Ask "How many guests will be staying?"
STEP 6: AFTER guests provided -> Call get_categories() tool
STEP 7: Show category buttons to user
STEP 8: WAIT for user to click a category button
STEP 9: User clicks category -> Call search_hotels_by_category(category, destination)
STEP 10: Show hotels with View Rooms buttons
STEP 11: User clicks View Rooms -> Call get_hotel_rooms(hotel_name)
STEP 12: Show rooms with Pick buttons
STEP 13: User picks room -> Call calculate_room_price()
STEP 14: Show meal plan options (MAP/CP/EP)
STEP 15: User selects meal -> Call calculate_meal_price()
STEP 16: Show FINAL SUMMARY with BOOK NOW, Change Meal Plan, Other Hotels

╔═══════════════════════════════════════════════════════════════════════════════╗
║                         CRITICAL RULES - NEVER BREAK                          ║
╚═══════════════════════════════════════════════════════════════════════════════╝

1. NEVER call search_hotels_by_category before user selects a category
2. NEVER call get_all_hotels_in_location - this tool is DISABLED for hotel flow
3. NEVER suggest or show hotels without a category selection
4. NEVER skip the category selection step
5. ALWAYS wait for user input after each step
6. ALWAYS use the tools in the exact order specified above
7. If user hasn't selected a category, ask them to select one from the buttons

╔═══════════════════════════════════════════════════════════════════════════════╗
║                         RESPONSE FORMAT RULES                                 ║
╚═══════════════════════════════════════════════════════════════════════════════╝

- Do NOT use emoji except BOOK NOW button
- Do NOT use dashes (---) or underscores (__)
- Keep responses clean plain text
- Show images when available from API
- After booking confirmed, reset session completely
"""

    def execute(self, phone: str, user_message: str, state: dict = None, business_phone: str = "default") -> Dict:
        session_key = self._session_key(phone, business_phone)

        # ============================================================
        # PACKAGE ROUTING - Check for active package session first
        # ============================================================
        if session_key in self.package_agent.sessions:
            pkg_context = self.package_agent.sessions[session_key].get("context", {})
            if pkg_context.get("flow") == "package" or pkg_context.get("step"):
                logger.info(f"Routing to PackageAgent for {session_key} (active package session)")
                response = self.package_agent.execute(phone, user_message, state, business_phone=business_phone)
                if state is not None and session_key in self.package_agent.sessions:
                    state["package_data"] = self.package_agent.sessions[session_key].get("context", {})
                return response

        # ============================================================
        # Check if user wants to start a package booking
        # ============================================================
        msg_lower = user_message.strip().lower()

        if msg_lower in ("travel package", "package", "packages"):
            logger.info(f"User selected PACKAGE booking for {session_key}")
            response = self.package_agent.execute(phone, user_message, state, business_phone=business_phone)
            if state is not None and session_key in self.package_agent.sessions:
                state["package_data"] = self.package_agent.sessions[session_key].get("context", {})
            return response

        if any(word in msg_lower for word in ["package", "tour", "trip", "holiday", "vacation"]):
            if session_key not in self.sessions or self.sessions[session_key].get("context", {}).get("step") == "ask_service_type":
                logger.info(f"User indicated PACKAGE interest for {session_key}")
                response = self.package_agent.execute(phone, user_message, state, business_phone=business_phone)
                if state is not None and session_key in self.package_agent.sessions:
                    state["package_data"] = self.package_agent.sessions[session_key].get("context", {})
                return response

        # ============================================================
        # HOTEL FLOW - Initialize session
        # ============================================================
        tools = self._make_tools(business_phone)

        if session_key not in self.sessions:
            saved_context = (state or {}).get("data", {})
            default_context = {
                "service_type": None,
                "flow": "initial",
                "destination": None,
                "check_in": None,
                "check_out": None,
                "guests": None,
                "selected_category": None,
                "selected_hotel": None,
                "selected_hotel_data": None,
                "selected_room": None,
                "selected_room_data": None,
                "meal_plan": None,
                "meal_plan_data": None,
                "price_details": None,
                "meal_details": None,
                "categories_from_api": None,
                "rooms_list": None,
                "hotels_list": None,
                "full_hotel_details": None,
                "step": "ask_service_type",
                "date_error": None,
                "business_phone": business_phone,
            }

            if saved_context and saved_context.get("business_phone") == business_phone:
                for key in default_context:
                    if key not in saved_context:
                        saved_context[key] = default_context[key]
                restored_context = saved_context
                logger.info(f"Restored context for {session_key}")
            else:
                restored_context = default_context

            self.sessions[session_key] = {"history": [], "context": restored_context}

        session = self.sessions[session_key]
        context = session["context"]
        session["history"].append({"role": "user", "content": user_message})

        # ============================================================
        # BUTTON HANDLERS - Process user button clicks
        # ============================================================

        # Handle service type selection
        if user_message.lower() in ["hotel", "hotel booking"] and context.get("step") == "ask_service_type":
            context["service_type"] = "hotel"
            context["step"] = "ask_destination"
            if state is not None:
                state["data"] = context
            return {"type": "text", "content": "Which city are you looking for hotels in?"}

        if user_message.lower() in ["package", "travel package"] and context.get("step") == "ask_service_type":
            context["service_type"] = "package"
            context["step"] = "package_flow"
            if state is not None:
                state["data"] = context
            return self.package_agent.execute(phone, user_message, state, business_phone=business_phone)

        # Handle "Change City" button
        if user_message.strip().lower() == "change_city":
            context["destination"] = None
            context["selected_category"] = None
            context["selected_hotel"] = None
            context["selected_hotel_data"] = None
            context["hotels_list"] = None
            context["rooms_list"] = None
            context["step"] = "ask_destination"
            if state is not None:
                state["data"] = context
            return {"type": "text", "content": "Which city would you like to search hotels in?"}

        # Handle category selection from buttons
        categories_in_context = context.get("categories_from_api") or []
        known_categories = [c.get("name", "").lower() for c in categories_in_context]
        
        if (user_message.strip().lower() in known_categories and 
            context.get("destination") and 
            context.get("check_in") and 
            context.get("check_out") and 
            context.get("guests") and
            context.get("step") in ["show_categories", "categories_shown", "ask_hotel_category", "no_hotels_found"]):
            
            matched_category = user_message.strip()
            context["selected_category"] = matched_category
            context["step"] = "searching_hotels"
            
            # Search for hotels
            result = tools.search_hotels_by_category(matched_category, context.get("destination"))
            
            if state is not None:
                state["data"] = context
            
            if result.get("success") and result.get("hotels"):
                context["step"] = "hotels_shown"
                context["hotels_list"] = result.get("hotels", [])
                if state is not None:
                    state["data"] = context
                return self._format_response("", context)
            else:
                context["step"] = "no_hotels_found"
                context["no_hotels_category"] = matched_category
                if state is not None:
                    state["data"] = context
                return self._format_response("", context)

        # Handle "View Rooms" button click
        if "View Rooms -" in user_message:
            hotel_name = user_message.replace("View Rooms -", "").strip()
            context["selected_hotel"] = hotel_name
            rooms_result = tools.get_hotel_rooms(hotel_name)
            if rooms_result.get("success"):
                context["rooms_list"] = rooms_result.get("rooms", [])
                context["meal_plan_data"] = rooms_result.get("meal_plan", {})
                context["full_hotel_details"] = rooms_result.get("full_hotel_details", {})
                context["step"] = "rooms_shown"
                if state is not None:
                    state["data"] = context
                return self._format_response("", context)
            else:
                return {"type": "text", "content": f"Sorry, could not fetch rooms: {rooms_result.get('error')}"}

        # Handle room pick by index
        if user_message.startswith("pick_room_"):
            try:
                room_index = int(user_message.replace("pick_room_", "").strip())
                rooms_list = context.get("rooms_list") or []
                if not rooms_list and context.get("selected_hotel"):
                    logger.info(f"Re-fetching rooms for {context['selected_hotel']}")
                    refetch = tools.get_hotel_rooms(context["selected_hotel"])
                    if refetch.get("success"):
                        context["rooms_list"] = refetch.get("rooms", [])
                        context["meal_plan_data"] = refetch.get("meal_plan", {})
                        context["full_hotel_details"] = refetch.get("full_hotel_details", {})
                        rooms_list = context["rooms_list"]
                if not rooms_list:
                    return {"type": "text", "content": "Could not load room details. Please select the hotel again."}
                if room_index < len(rooms_list):
                    room_data = rooms_list[room_index]
                    context["selected_room_data"] = room_data
                    context["selected_room"] = f"{room_data.get('category')} - {room_data.get('type')}"
                    check_in = context.get("check_in")
                    check_out = context.get("check_out")
                    
                    if not check_in or not check_out:
                        context["step"] = "ask_dates_for_room"
                        if state is not None:
                            state["data"] = context
                        return {"type": "text", "content": "Please provide your check-in and check-out dates to continue."}
                    
                    price_result = tools.calculate_room_price(
                        room_data, check_in, check_out, context.get("guests", 1)
                    )
                    if price_result.get("success"):
                        context["price_details"] = price_result
                        context["step"] = "price_calculated"
                        if state is not None:
                            state["data"] = context
                        return self._format_response("", context)
                    else:
                        return {"type": "text", "content": f"Price calculation error: {price_result.get('error')}"}
                else:
                    return {"type": "text", "content": "Room selection not found. Please try again."}
            except Exception as e:
                logger.error(f"Room pick error: {e}")
                return {"type": "text", "content": "Room selection failed. Please try again."}

        # Handle "Other Hotels" button
        if user_message.lower() == "other_hotels":
            hotels_list = context.get("hotels_list", [])
            current_hotel = context.get("selected_hotel", "")
            other_hotels = [h for h in hotels_list if h.get("name", "") != current_hotel]
            if other_hotels:
                context["step"] = "hotels_shown"
                context["hotels_list"] = other_hotels
                if state is not None:
                    state["data"] = context
                return self._format_response("", context)
            else:
                return {
                    "type": "buttons",
                    "content": f"No other hotels available. You are currently viewing:\n\n{current_hotel}",
                    "buttons": [{"text": f"Continue with {current_hotel[:30]}", "value": "continue_current_hotel"}]
                }

        # Handle "Continue with current hotel"
        if user_message.lower() == "continue_current_hotel":
            if context.get("price_details") and context.get("meal_details"):
                context["step"] = "final_summary"
            elif context.get("price_details"):
                context["step"] = "price_calculated"
            if state is not None:
                state["data"] = context
            return self._format_response("", context)

        # Handle "Change Meal Plan" button
        if user_message.lower() == "change_meal_plan" and context.get("price_details"):
            price = context.get("price_details", {})
            return {
                "type": "buttons",
                "content": f"Select Meal Plan\n\nRoom Total: Rs.{price.get('grand_total', 0):,.2f}\n\nChoose your meal preference:",
                "buttons": [
                    {"text": "MAP (Breakfast + Dinner)", "value": "map"},
                    {"text": "CP (Breakfast only)", "value": "cp"},
                    {"text": "EP (No meals)", "value": "ep"}
                ]
            }

        # Handle meal selection
        if user_message.lower() in ["map", "cp", "ep"] and context.get("price_details"):
            meal_result = tools.calculate_meal_price(
                user_message.lower(),
                context.get("meal_plan_data", {}),
                context.get("guests", 1),
                context.get("price_details", {}).get("nights", 1)
            )
            if meal_result.get("success"):
                context["meal_details"] = meal_result
                context["meal_plan"] = user_message.lower()
                context["step"] = "final_summary"
                if state is not None:
                    state["data"] = context
                return self._format_response("", context)

        # Handle confirm booking
        if user_message.lower() == "confirm" and context.get("step") == "final_summary":
            context["step"] = "booking_confirmed"
            if state is not None:
                state["data"] = context
            response = self._format_response("confirm", context)
            self.reset_session(phone, business_phone=business_phone)
            if state is not None:
                state["data"] = {
                    "service_type": None, "flow": "initial", "destination": None,
                    "check_in": None, "check_out": None, "guests": None,
                    "selected_category": None, "selected_hotel": None, "selected_hotel_data": None,
                    "selected_room": None, "selected_room_data": None, "meal_plan": None,
                    "meal_plan_data": None, "price_details": None, "meal_details": None,
                    "categories_from_api": None, "rooms_list": None, "hotels_list": None,
                    "full_hotel_details": None, "step": "ask_service_type", 
                    "date_error": None, "business_phone": business_phone,
                }
            logger.info(f"Session reset for {session_key} after booking confirmation")
            return response

        # ============================================================
        # GUEST COUNT EXTRACTION
        # ============================================================
        guest_match = (re.search(r"we\s+are\s+(\d+)\s*(?:people|persons?|guests?|members?)?", msg_lower) or
                       re.search(r"(\d+)\s+(?:people|persons?|guests?|members?)", msg_lower) or
                       (msg_lower.isdigit() and len(msg_lower) <= 2 and int(msg_lower) <= 20))
        
        if guest_match and not context.get("guests") and context.get("step") == "ask_guests":
            try:
                num_g = int(guest_match.group(1)) if hasattr(guest_match, 'group') and guest_match.group(1) else int(msg_lower)
                if 1 <= num_g <= 20:
                    context["guests"] = num_g
                    context["step"] = "show_categories"
                    if state is not None:
                        state["data"] = context
                    
                    # Fetch and show categories
                    cat_result = tools.get_categories()
                    if cat_result.get("success"):
                        context["categories_from_api"] = cat_result.get("categories", [])
                        context["step"] = "categories_shown"
                        if state is not None:
                            state["data"] = context
                        return self._format_response("", context)
            except Exception as e:
                logger.error(f"Guest extraction error: {e}")

        # ============================================================
        # DATE PARSING
        # ============================================================
        if context.get("step") == "ask_dates" and not (context.get("check_in") and context.get("check_out")):
            # Try to parse dates from message
            date_result = self._parse_dates_from_message(user_message)
            if date_result.get("check_in") and date_result.get("check_out"):
                today = datetime.now().date()
                ci = datetime.strptime(date_result["check_in"], "%Y-%m-%d").date()
                co = datetime.strptime(date_result["check_out"], "%Y-%m-%d").date()
                
                if ci < today:
                    return {"type": "text", "content": f"Check-in date {date_result['check_in']} is in the past. Please provide a future date."}
                if co <= ci:
                    return {"type": "text", "content": "Check-out date must be after check-in date. Please provide valid dates."}
                
                context["check_in"] = date_result["check_in"]
                context["check_out"] = date_result["check_out"]
                context["step"] = "ask_guests"
                if state is not None:
                    state["data"] = context
                return {"type": "text", "content": "How many guests will be staying?"}

        # ============================================================
        # DESTINATION EXTRACTION
        # ============================================================
        if context.get("step") == "ask_destination" and not context.get("destination"):
            # Simple destination extraction - user usually just says city name
            if len(user_message.strip()) > 2 and not any(x in user_message.lower() for x in ["hotel", "package", "book"]):
                context["destination"] = user_message.strip().title()
                context["step"] = "ask_dates"
                if state is not None:
                    state["data"] = context
                return {"type": "text", "content": "What are your check-in and check-out dates?"}

        # ============================================================
        # LLM FALLBACK - Only for extraction when needed
        # ============================================================
        if context.get("step") in ["ask_destination", "ask_dates", "ask_guests"]:
            extracted_info = self._extract_info_with_llm(user_message, context)
            self._apply_extracted_info(extracted_info, context)
            if state is not None:
                state["data"] = context

        # Auto-fetch categories when all info collected
        if (context.get("destination") and 
            context.get("check_in") and 
            context.get("check_out") and 
            context.get("guests") and 
            context.get("step") == "show_categories" and
            not context.get("categories_from_api")):
            
            cat_result = tools.get_categories()
            if cat_result.get("success"):
                context["categories_from_api"] = cat_result.get("categories", [])
                context["step"] = "categories_shown"
                if state is not None:
                    state["data"] = context
                return self._format_response("", context)

        if state is not None:
            state["data"] = context

        # Return formatted response based on current step
        return self._format_response("", context)

    def _parse_dates_from_message(self, message: str) -> Dict[str, str]:
        """Parse dates from user message without LLM."""
        today = datetime.now()
        current_year = today.year
        current_month = today.month
        
        # Pattern: "12 to 16" or "12th to 16th"
        match = re.search(r"(\d{1,2})(?:st|nd|rd|th)?\s+to\s+(\d{1,2})(?:st|nd|rd|th)?", message.lower())
        if match:
            d1, d2 = int(match.group(1)), int(match.group(2))
            # Check if dates are valid for current month
            try:
                ci = datetime(current_year, current_month, d1)
                co = datetime(current_year, current_month, d2)
                if ci >= today and co > ci:
                    return {"check_in": ci.strftime("%Y-%m-%d"), "check_out": co.strftime("%Y-%m-%d")}
            except ValueError:
                pass
            
            # Try next month
            next_month = current_month + 1 if current_month < 12 else 1
            next_year = current_year if current_month < 12 else current_year + 1
            try:
                ci = datetime(next_year, next_month, d1)
                co = datetime(next_year, next_month, d2)
                if ci >= today and co > ci:
                    return {"check_in": ci.strftime("%Y-%m-%d"), "check_out": co.strftime("%Y-%m-%d")}
            except ValueError:
                pass
        
        # Pattern with month names: "14 june to 16 june"
        months = {
            "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
            "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12
        }
        
        for month_name, month_num in months.items():
            pattern = rf"(\d{{1,2}})(?:st|nd|rd|th)?\s+{month_name}\s+to\s+(\d{{1,2}})(?:st|nd|rd|th)?\s+{month_name}"
            match = re.search(pattern, message.lower())
            if match:
                d1, d2 = int(match.group(1)), int(match.group(2))
                year = current_year
                try:
                    ci = datetime(year, month_num, d1)
                    if ci < today:
                        year = current_year + 1
                        ci = datetime(year, month_num, d1)
                    co = datetime(year, month_num, d2)
                    if co > ci:
                        return {"check_in": ci.strftime("%Y-%m-%d"), "check_out": co.strftime("%Y-%m-%d")}
                except ValueError:
                    pass
        
        return {"check_in": None, "check_out": None}

    def _extract_info_with_llm(self, message: str, context: Dict) -> Dict:
        """Extract info using LLM only when needed."""
        current_year = datetime.now().year
        extraction_prompt = f"""
Extract information from user message. Current year is {current_year}.

User message: "{message}"

Return JSON ONLY:
{{
    "destination": "city name or null",
    "check_in": "YYYY-MM-DD or null",
    "check_out": "YYYY-MM-DD or null",
    "guests": number or null
}}
"""
        try:
            response = self.client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[{"role": "user", "content": extraction_prompt}],
                temperature=0.1,
                response_format={"type": "json_object"}
            )
            result = json.loads(response.choices[0].message.content)
            logger.info(f"Extracted info: {result}")
            return result
        except Exception as e:
            logger.error(f"Extraction error: {e}")
            return {"destination": None, "check_in": None, "check_out": None, "guests": None}

    def _apply_extracted_info(self, extracted: Dict, context: Dict):
        """Apply extracted info to context."""
        if not context.get("destination") and extracted.get("destination"):
            context["destination"] = extracted["destination"].title()
            if context.get("step") == "ask_destination":
                context["step"] = "ask_dates"

        if not context.get("check_in") and extracted.get("check_in"):
            context["check_in"] = extracted["check_in"]
            context["check_out"] = extracted["check_out"]
            if context.get("step") == "ask_dates":
                context["step"] = "ask_guests"

        if not context.get("guests") and extracted.get("guests"):
            guests = int(extracted["guests"])
            if 1 <= guests <= 20:
                context["guests"] = guests
                if context.get("destination") and context.get("check_in") and context.get("check_out"):
                    context["step"] = "show_categories"

    def _format_response(self, message: str, context: Dict) -> Dict:
        """Format response based on current step."""
        
        # Ask service type
        if context.get("step") == "ask_service_type":
            return {
                "type": "buttons",
                "content": "Welcome! What would you like to book?\n\nPlease select an option:",
                "buttons": [
                    {"text": "Hotel Booking", "value": "hotel"},
                    {"text": "Travel Package", "value": "package"}
                ]
            }

        # Show categories
        if context.get("step") in ("show_categories", "categories_shown"):
            categories = context.get("categories_from_api", [])
            if not categories:
                return {"type": "text", "content": "No categories found. Please try again later."}
            buttons = [{"text": cat.get("name"), "value": cat.get("name")} for cat in categories if cat.get("name")]
            return {
                "type": "buttons_grid",
                "content": f"Select Hotel Category in {context.get('destination', 'your city')}\n\nPlease choose your preferred hotel type:",
                "buttons": buttons
            }

        # No hotels found
        if context.get("step") == "no_hotels_found":
            categories = context.get("categories_from_api", [])
            failed_cat = context.get("no_hotels_category", "selected")
            destination = context.get("destination", "this city")
            category_buttons = [{"text": cat.get("name"), "value": cat.get("name")} for cat in categories if cat.get("name")]
            return {
                "type": "buttons_grid_with_separate_button",
                "content": f"No hotels found in {destination} for the {failed_cat} category.\n\nPlease select another category:",
                "buttons": category_buttons,
                "separate_button": {"text": "Change City", "value": "change_city"}
            }

        # Show hotels list
        if context.get("hotels_list") and context.get("step") == "hotels_shown":
            hotels = context["hotels_list"][:8]
            content = f"Hotels in {context.get('destination')}\n\nFound {len(hotels)} hotels. Select a hotel to view rooms:\n\n"
            for i, hotel in enumerate(hotels, 1):
                if hotel.get("image"):
                    content += f"![{hotel['name']}]({hotel['image']})\n\n"
                content += f"{i}. {hotel['name']}\n"
                content += f"Category: {hotel.get('category', 'N/A')}\n"
                content += f"Location: {hotel.get('location', 'N/A')}\n"
                if hotel.get("description"):
                    content += f"{hotel['description'][:150]}...\n"
                content += "\n"
            content += "Click a button below to view rooms:"
            buttons = [{"text": f"View Rooms - {h.get('name', '')[:30]}", "value": f"View Rooms - {h.get('name', '')[:30]}"} for h in hotels]
            return {"type": "buttons_grid", "content": content, "buttons": buttons}

        # Show rooms list
        if context.get("rooms_list") and context.get("step") == "rooms_shown":
            rooms = context["rooms_list"]
            hotel_name = context.get("selected_hotel", "Hotel")
            content = f"Rooms at {hotel_name}\n\n"
            for i, room in enumerate(rooms, 1):
                if room.get("images") and len(room["images"]) > 0:
                    content += f"![Room {i}]({room['images'][0]})\n\n"
                content += f"Room {i}: {room.get('category', 'N/A')} - {room.get('type', 'N/A')}\n"
                content += f"Capacity: {room.get('minimum_capacity', 'N/A')} - {room.get('maximum_capacity', 'N/A')} guests\n"
                content += f"Base Price: Rs.{room.get('base_price', 0)}/night\n"
                if room.get('extra_person_price', 0) > 0:
                    content += f"Extra person: Rs.{room.get('extra_person_price', 0)}/night\n"
                content += "\n"
            content += "Select a room to proceed:"
            buttons = [{"text": f"Pick - {r.get('category', 'N/A')} {r.get('type', 'N/A')}", "value": f"pick_room_{i-1}"} for i, r in enumerate(rooms[:5])]
            return {"type": "buttons_grid", "content": content, "buttons": buttons}

        # Price calculated - show meal plan options
        if context.get("step") == "price_calculated":
            price = context.get("price_details", {})
            return {
                "type": "buttons",
                "content": f"Room Price Summary\n\nRooms Needed: {price.get('rooms_needed', 1)} room(s)\nNights: {price.get('nights', 0)}\nTotal Room Cost: Rs.{price.get('grand_total', 0):,.2f}\n\nSelect Meal Plan:",
                "buttons": [
                    {"text": "MAP (Breakfast + Dinner)", "value": "map"},
                    {"text": "CP (Breakfast only)", "value": "cp"},
                    {"text": "EP (No meals)", "value": "ep"}
                ]
            }

        # Final summary
        if context.get("step") == "final_summary":
            price = context.get("price_details", {})
            meal = context.get("meal_details", {})
            room = context.get("selected_room_data", {})
            full_hotel = context.get("full_hotel_details", {})
            display_hotel_name = full_hotel.get('hotel_name', context.get("selected_hotel", "Hotel"))
            hotel_category = full_hotel.get('category', context.get('selected_category', 'N/A'))
            hotel_location = full_hotel.get('location', context.get('destination', 'N/A'))
            room_category = room.get('category', 'N/A')
            room_type = room.get('type', 'N/A')
            min_capacity = room.get('minimum_capacity', 'N/A')
            max_capacity = room.get('maximum_capacity', 'N/A')
            rooms_needed = price.get('rooms_needed', 1)
            nights = price.get('nights', 0)
            room_total = price.get('room_total', 0)
            extra_total = price.get('extra_total', 0)
            extra_people = price.get('extra_people', 0)
            season_used = price.get('season_used', 'Regular Rate')
            seasonal_price_per_night = price.get('seasonal_base_price', room.get('base_price', 0))
            seasonal_extra_price = price.get('seasonal_extra_price', room.get('extra_person_price', 0))
            meal_name = meal.get('meal_name', 'No meals')
            meal_total = meal.get('total_meal_price', 0)
            room_cost_calculation = f"{rooms_needed} rooms x Rs.{seasonal_price_per_night} x {nights} nights"
            extra_cost_calculation = f"{extra_people} extra persons x Rs.{seasonal_extra_price} x {nights} nights" if extra_people > 0 else "None"
            grand_total = room_total + extra_total + meal_total
            
            content = f"""YOUR BOOKING SUMMARY

Destination: {hotel_location}
Travel Dates: {context.get('check_in')} to {context.get('check_out')} ({nights} nights)
Total Guests: {context.get('guests')} people

Hotel Details
Hotel Name: {display_hotel_name}
Category: {hotel_category}

Room Details
Room Type: {room_category} - {room_type}
Capacity: {min_capacity} - {max_capacity} guests per room

Pricing Breakdown
Room Rate: Rs.{seasonal_price_per_night}/night/room
Extra Person Rate: Rs.{seasonal_extra_price}/night/person
Season Applied: {season_used}

Total Room Cost: Rs.{room_total:,.2f}
({room_cost_calculation})

Total Extra Persons Cost: Rs.{extra_total:,.2f}
({extra_cost_calculation})

Meal Plan: {meal_name}
Meal Cost: Rs.{meal_total:,.2f}

GRAND TOTAL: Rs.{grand_total:,.2f}"""
            
            return {
                "type": "buttons",
                "content": content.strip(),
                "buttons": [
                    {"text": "BOOK NOW", "value": "confirm"},
                    {"text": "Change Meal Plan", "value": "change_meal_plan"},
                    {"text": "Other Hotels", "value": "other_hotels"}
                ]
            }

        # Booking confirmed
        if context.get("step") == "booking_confirmed":
            return {
                "type": "text",
                "content": f"BOOKING CONFIRMED!\n\nThank you for booking with us!\n\nReference: HOTEL{datetime.now().strftime('%Y%m%d%H%M%S')}\n\nWe will send details to your phone shortly.\n\nHave a great stay!\n\nType 'hi' to start a new booking!"
            }

        # Default responses for missing info
        if context.get("step") == "ask_destination" and not context.get("destination"):
            return {"type": "text", "content": "Which city are you looking for hotels in?"}
        
        if context.get("step") == "ask_dates" and not (context.get("check_in") and context.get("check_out")):
            return {"type": "text", "content": "What are your check-in and check-out dates?"}
        
        if context.get("step") == "ask_guests" and not context.get("guests"):
            return {"type": "text", "content": "How many guests will be staying?"}

        if message and len(message) > 0:
            return {"type": "text", "content": message}

        return {"type": "text", "content": "How can I help you with your hotel booking?"}

    def reset_session(self, phone: str, business_phone: str = "default"):
        session_key = self._session_key(phone, business_phone)
        if session_key in self.sessions:
            del self.sessions[session_key]
            logger.info(f"Hotel session reset for {session_key}")
        self.package_agent.reset_session(phone, business_phone=business_phone)