# agent/ai_agent.py
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
        self.tools = TravelTools()
        self.package_agent = PackageAgent()
        self.sessions = {}

    def get_system_prompt(self) -> str:
        return """You are a hotel booking AI agent with REAL data access.

FIRST: Ask user "Are you looking for hotels or travel packages?"
- If hotels, proceed with hotel flow
- If packages, you will respond: "Let me help you book a travel package"

HOTEL BOOKING FLOW (Follow STRICTLY in this order):
1. Ask: "Which city are you looking for hotels in?"
2. DESTINATION VALIDATION (CRITICAL):
   - When user provides a city name, use your parametric knowledge to verify it is a real, known city or town in India or worldwide.
   - If the city name does NOT match any real place you know of, respond: "I could not find a place called [city]. Could you please retype the destination?"
   - Do NOT proceed to step 3 until a valid, recognizable city is confirmed.
3. After valid destination confirmed, ask: "What are your check-in and check-out dates?"
4. DATE VALIDATION RULES (CRITICAL):
   - Check-in date MUST be TODAY or FUTURE date (cannot be past date)
   - Check-out date MUST be AFTER check-in date (cannot be same day or before)
   - Example: If today is 2026-05-05, check-in cannot be 2026-05-04 or earlier
   - Example: If user says "12 may to 10 may" - this is INVALID because end date is before start date
   - Example: If user says "10 may to 15 may" - this is VALID (check-in=10 may, check-out=15 may)
   - If dates are invalid, show error message: "Invalid dates. Please provide check-in date that is today or future, and check-out date after check-in date."
   - Do NOT proceed until valid dates are provided
5. After valid dates, ask: "How many guests will be staying?"
6. After guests, call get_categories() and show ALL categories from API as suggestion buttons
7. User selects category, call search_hotels_by_category(category, destination)
   - If no hotels found for that category in the destination, show all category buttons again, then show a separate "Change City" button below
   - If hotels found, show hotels with: Image, Name, Category, Description, and "View Rooms" button
8. User clicks "Change City":
   - Only reset the city. Keep check-in, check-out, and guests as they are. Do NOT ask for dates or guests again.
   - Ask only: "Which city would you like to search hotels in?"
   - After user gives new city, validate it, then immediately show category buttons (skip dates and guests steps entirely)
9. User clicks View Rooms, call get_hotel_rooms(hotel_name)
10. Show ALL rooms with: Image, Room Category, Room Type, Capacity, Price, and "Pick" button
11. User picks room, call calculate_room_price() and show price breakdown
12. Show meal plan options ONCE: MAP / CP / EP buttons
13. User selects meal, call calculate_meal_price() and show FINAL SUMMARY
14. FINAL SUMMARY must always show these 3 buttons only:
    - "📖 BOOK NOW"
    - "Change Meal Plan"
    - "Other Hotels"
15. "Other Hotels" logic:
    - If other hotels exist in the current list → show them (excluding current hotel), same hotel card format
    - If no other hotels → show message with current hotel name + "Continue with [Hotel Name]" button only
16. "Change Meal Plan":
    - Show MAP / CP / EP buttons again
    - User picks new meal → recalculate and show updated FINAL SUMMARY
17. After user confirms booking, show booking confirmation and start a NEW conversation

CRITICAL RULES:
- NEVER hardcode cities or categories, ALWAYS fetch from API
- Use LLM to extract dates, cities, and guest counts from natural language
- Validate dates STRICTLY: end date must be AFTER start date, no past dates
- If user provides invalid dates (past date or end date before start date), show error and ask again
- ALWAYS use tools to fetch real data
- NEVER hallucinate hotels, rooms, or categories
- Show images when available from API
- Do NOT use emoji, icons, dashes (---), or underscores (__) in any response except the BOOK NOW button
- Keep all responses clean plain text or structured data
- NEVER ask for dates or guests again once they are already collected
- After booking is confirmed, reset the session completely so user can start fresh
- When user updates guest count, recalculate prices automatically
"""

    def execute(self, phone: str, user_message: str, state: dict = None) -> Dict:
        # ============================================================
        # PACKAGE ROUTING - Check for active package session first
        # ============================================================
        if phone in self.package_agent.sessions:
            pkg_context = self.package_agent.sessions[phone].get("context", {})
            if pkg_context.get("flow") == "package" or pkg_context.get("step"):
                logger.info(f"Routing to PackageAgent for {phone} (active package session)")
                response = self.package_agent.execute(phone, user_message, state)
                if state is not None and phone in self.package_agent.sessions:
                    state["package_data"] = self.package_agent.sessions[phone].get("context", {})
                return response

        # ============================================================
        # Check if user wants to start a package booking
        # ============================================================
        msg_lower = user_message.strip().lower()
        
        if msg_lower == "travel package" or msg_lower == "package":
            logger.info(f"User selected PACKAGE booking for {phone}")
            response = self.package_agent.execute(phone, user_message, state)
            if state is not None and phone in self.package_agent.sessions:
                state["package_data"] = self.package_agent.sessions[phone].get("context", {})
            return response
        
        if any(word in msg_lower for word in ["package", "tour", "trip", "holiday", "vacation"]):
            if phone not in self.sessions or self.sessions[phone].get("context", {}).get("step") == "ask_service_type":
                logger.info(f"User indicated PACKAGE interest for {phone}")
                response = self.package_agent.execute(phone, user_message, state)
                if state is not None and phone in self.package_agent.sessions:
                    state["package_data"] = self.package_agent.sessions[phone].get("context", {})
                return response

        # ============================================================
        # HOTEL FLOW
        # ============================================================
        if phone not in self.sessions:
            # Restore context from persistent state (survives server restarts)
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
                "categories_from_api": None,
                "rooms_list": None,
                "hotels_list": None,
                "full_hotel_details": None,
                "step": "ask_service_type",
                "date_error": None
            }

            if saved_context:
                for key in default_context:
                    if key not in saved_context:
                        saved_context[key] = default_context[key]
                restored_context = saved_context
                logger.info(f"Restored context for {phone}: check_in={restored_context.get('check_in')}, check_out={restored_context.get('check_out')}, destination={restored_context.get('destination')}")
            else:
                restored_context = default_context

            self.sessions[phone] = {
                "history": [],
                "context": restored_context
            }

        session = self.sessions[phone]
        context = session["context"]

        session["history"].append({"role": "user", "content": user_message})

        # Handle guest count update (NEW)
        if any(word in user_message.lower() for word in ["we are", "we have", "peoples", "people", "guests", "members"]) and not any(word in user_message.lower() for word in ["map", "cp", "ep", "change_meal_plan", "other_hotels", "confirm"]):
            extracted_info = self._extract_info_with_llm(user_message, context)
            if extracted_info.get("guests"):
                new_guests = int(extracted_info["guests"])
                old_guests = context.get("guests", 0)
                
                if new_guests != old_guests and new_guests > 0:
                    logger.info(f"Updating guests from {old_guests} to {new_guests}")
                    context["guests"] = new_guests
                    
                    # Recalculate price with new guest count
                    if context.get("selected_room_data") and context.get("check_in") and context.get("check_out"):
                        price_result = self.tools.calculate_room_price(
                            context["selected_room_data"],
                            context["check_in"],
                            context["check_out"],
                            new_guests
                        )
                        if price_result.get("success"):
                            context["price_details"] = price_result
                            
                            # If meal was already selected, recalculate meal price too
                            if context.get("meal_details"):
                                meal_type = context.get("meal_plan", "map")
                                meal_result = self.tools.calculate_meal_price(
                                    meal_type,
                                    context.get("meal_plan_data", {}),
                                    new_guests,
                                    price_result.get("nights", 1)
                                )
                                if meal_result.get("success"):
                                    context["meal_details"] = meal_result
                            
                            context["step"] = "final_summary"
                            if state is not None:
                                state["data"] = context
                            return self._format_response("", context)

        # Handle "Change City" button
        if user_message.strip().lower() == "change_city":
            context["destination"] = None
            context["selected_category"] = None
            context["selected_hotel"] = None
            context["selected_hotel_data"] = None
            context["hotels_list"] = None
            context["rooms_list"] = None
            context["step"] = "change_city_ask_destination"
            if state is not None:
                state["data"] = context
            return {"type": "text", "content": "Which city would you like to search hotels in?"}

        # Handle "View Rooms" button click
        if "View Rooms -" in user_message:
            hotel_name = user_message.replace("View Rooms -", "").strip()
            context["selected_hotel"] = hotel_name
            rooms_result = self.tools.get_hotel_rooms(hotel_name)
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
                    logger.info(f"Re-fetching rooms for {context['selected_hotel']} after restart")
                    refetch = self.tools.get_hotel_rooms(context["selected_hotel"])
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
                    
                    logger.info(f"Room selected - Check-in: {check_in}, Check-out: {check_out}, Guests: {context.get('guests')}")

                    if not check_in or not check_out:
                        context["step"] = "ask_dates_for_room"
                        if state is not None:
                            state["data"] = context
                        return {"type": "text", "content": "Please provide your check-in and check-out dates to continue."}

                    price_result = self.tools.calculate_room_price(
                        room_data,
                        check_in,
                        check_out,
                        context.get("guests", 1)
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
                    "buttons": [
                        {"text": f"Continue with {current_hotel[:30]}", "value": "continue_current_hotel"}
                    ]
                }

        # Handle "Continue with current hotel"
        if user_message.lower() == "continue_current_hotel":
            if context.get("price_details") and context.get("meal_details"):
                context["step"] = "final_summary"
                if state is not None:
                    state["data"] = context
                return self._format_response("", context)
            elif context.get("price_details"):
                context["step"] = "price_calculated"
                if state is not None:
                    state["data"] = context
                return self._format_response("", context)
            else:
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
            meal_result = self.tools.calculate_meal_price(
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
            self.reset_session(phone)
            
            if state is not None:
                state["data"] = {
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
                    "categories_from_api": None,
                    "rooms_list": None,
                    "hotels_list": None,
                    "full_hotel_details": None,
                    "step": "ask_service_type",
                    "date_error": None
                }
            
            logger.info(f"Session reset for {phone} after booking confirmation")
            return response

        # Handle category selection directly
        categories_in_context = context.get("categories_from_api") or []
        known_categories = [c.get("name", "").lower() for c in categories_in_context]
        if user_message.strip().lower() in known_categories and context.get("destination"):
            matched_category = user_message.strip()
            context["selected_category"] = matched_category
            result = self.tools.search_hotels_by_category(matched_category, context.get("destination"))
            self._update_context("search_hotels_by_category", result, context)
            if state is not None:
                state["data"] = context
            return self._format_response("", context)

        # Use LLM to extract info from message
        extracted_info = self._extract_info_with_llm(user_message, context)
        self._apply_extracted_info(extracted_info, context)
        
        if state is not None:
            state["data"] = context
            logger.info(f"Saved context after extraction - check_in={context.get('check_in')}, check_out={context.get('check_out')}, destination={context.get('destination')}, guests={context.get('guests')}")

        if (context.get("step") == "show_categories"
                and context.get("destination")
                and context.get("check_in")
                and context.get("check_out")
                and context.get("guests")):
            cat_result = self.tools.get_categories()
            self._update_context("get_categories", cat_result, context)
            if state is not None:
                state["data"] = context
            return self._format_response("", context)

        if (context.get("step") == "ask_dates_for_room"
                and context.get("check_in")
                and context.get("check_out")
                and context.get("selected_room_data")):
            logger.info(f"Calculating price with dates: {context['check_in']} to {context['check_out']}")
            price_result = self.tools.calculate_room_price(
                context["selected_room_data"],
                context["check_in"],
                context["check_out"],
                context.get("guests", 1)
            )
            if price_result.get("success"):
                context["price_details"] = price_result
                context["step"] = "price_calculated"
                if state is not None:
                    state["data"] = context
                return self._format_response("", context)

        if state is not None:
            state["data"] = context

        flow_status = self._get_flow_status(context)

        try:
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": self.get_system_prompt() + "\n\n" + flow_status},
                    *session["history"]
                ],
                tools=TOOL_DEFINITIONS,
                tool_choice="auto",
                temperature=0.3
            )

            assistant_message = response.choices[0].message

            if assistant_message.tool_calls:
                tool_results = []
                for tool_call in assistant_message.tool_calls:
                    function_name = tool_call.function.name
                    arguments = json.loads(tool_call.function.arguments)

                    print(f"[TOOL] {function_name}({arguments})")

                    result = self._execute_tool(function_name, arguments, context)
                    tool_results.append({
                        "tool_call_id": tool_call.id,
                        "role": "tool",
                        "content": json.dumps(result, ensure_ascii=False)
                    })

                    self._update_context(function_name, result, context)

                session["history"].append(assistant_message)
                session["history"].extend(tool_results)

                final_response = self.client.chat.completions.create(
                    model="gpt-4o",
                    messages=session["history"],
                    temperature=0.3
                )

                final_message = final_response.choices[0].message.content
                session["history"].append({"role": "assistant", "content": final_message})

                if state is not None:
                    state["data"] = context

                return self._format_response(final_message, context)

            else:
                response_text = assistant_message.content
                session["history"].append(assistant_message)
                
                if state is not None:
                    state["data"] = context
                    
                return self._format_response(response_text, context)

        except Exception as e:
            logger.error(f"Error: {e}")
            return {"type": "text", "content": f"Sorry, an error occurred: {str(e)}"}

    def _extract_info_with_llm(self, message: str, context: Dict) -> Dict:
        extraction_prompt = f"""
You are an information extraction system. Extract the following from the user message:

1. Destination/City: Any city name (Shimla, Manali, Delhi, Mumbai, Goa, Jaipur, etc.)

2. Dates: Check-in and check-out dates. Support natural language like:
   - "12th may to 16th may" means check-in=12 may, check-out=16 may
   - "12 to 16" means assume current month and year
   - "next week" means calculate
   - "Dec 25th to Dec 30th" means specific dates
   - "1/12/2026 to 5/12/2026" means specific dates

   CRITICAL DATE VALIDATION RULES:
   - Check-in date MUST be TODAY or FUTURE (cannot be past date)
   - Check-out date MUST be AFTER check-in date (cannot be same day or before)
   - If user says "12 may to 10 may" - this is INVALID (check-out before check-in)
   - If check-in is past date, mark as invalid
   - If check-out is not after check-in, mark as invalid
   - Current date is: {datetime.now().strftime("%Y-%m-%d")}

3. Number of Guests: Extract from phrases like:
   - "me and my wife" means 2
   - "me, my wife, sister, father" means 4
   - "couple" means 2
   - "family of 4" means 4
   - "2 adults" means 2
   - "single" means 1
   - "we are 4 peoples" means 4
   - "okay we are 4 peoples" means 4

IMPORTANT: For dates like "12 may to 16 may", assume the current year is 2026.
Convert to YYYY-MM-DD format.

User message: "{message}"

Current context:
- Destination already set: {context.get('destination')}
- Check-in already set: {context.get('check_in')}
- Check-out already set: {context.get('check_out')}
- Guests already set: {context.get('guests')}

Return JSON ONLY with this structure:
{{
    "destination": "city name or null if not found",
    "check_in": "YYYY-MM-DD or null",
    "check_out": "YYYY-MM-DD or null",
    "check_in_valid": true or false,
    "check_out_valid": true or false,
    "guests": number or null,
    "service_type": "hotel" or "package" or null,
    "date_error": "error message if dates invalid, else null"
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
            return {"destination": None, "check_in": None, "check_out": None, "guests": None, "service_type": None, "date_error": None}

    def _apply_extracted_info(self, extracted: Dict, context: Dict):
        if not context.get("service_type") and extracted.get("service_type"):
            context["service_type"] = extracted["service_type"]
            context["flow"] = extracted["service_type"]
            if extracted["service_type"] == "hotel":
                context["step"] = "ask_destination"

        if not context.get("destination") and extracted.get("destination"):
            context["destination"] = extracted["destination"].title()
            if context.get("step") == "ask_destination":
                context["step"] = "ask_dates"
            elif context.get("step") == "change_city_ask_destination":
                context["step"] = "show_categories"

        today = datetime.now().date()

        # Date validation logic
        if extracted.get("check_in") and extracted.get("check_out"):
            try:
                check_in_date = datetime.strptime(extracted["check_in"], "%Y-%m-%d").date()
                check_out_date = datetime.strptime(extracted["check_out"], "%Y-%m-%d").date()
                
                # Check if dates are valid
                is_valid = True
                error_msg = None
                
                if check_in_date < today:
                    is_valid = False
                    error_msg = f"Check-in date {extracted['check_in']} is in the past. Please provide a future date."
                elif check_out_date <= check_in_date:
                    is_valid = False
                    error_msg = f"Check-out date {extracted['check_out']} must be after check-in date {extracted['check_in']}. Please provide valid dates."
                
                if is_valid:
                    context["check_in"] = extracted["check_in"]
                    context["check_out"] = extracted["check_out"]
                    context["date_error"] = None
                    logger.info(f"Valid dates saved - Check-in: {context['check_in']}, Check-out: {context['check_out']}")
                    
                    if context.get("step") == "ask_dates":
                        context["step"] = "ask_guests"
                    elif context.get("step") == "ask_dates_for_room":
                        pass
                else:
                    context["date_error"] = error_msg
                    context["check_in"] = None
                    context["check_out"] = None
                    logger.warning(f"Invalid dates: {error_msg}")
                    
            except Exception as e:
                logger.error(f"Date validation error: {e}")
                context["date_error"] = f"Could not parse dates. Please provide dates in format like '12 may 2026 to 16 may 2026'"

        if not context.get("guests") and extracted.get("guests"):
            guests = int(extracted["guests"])
            if 1 <= guests <= 20:
                context["guests"] = guests
                logger.info(f"Guests saved to context: {context['guests']}")
                if context.get("destination") and context.get("check_in") and context.get("check_out") and not context.get("date_error"):
                    context["step"] = "show_categories"

    def _get_flow_status(self, context: Dict) -> str:
        date_error = context.get("date_error", "")
        error_section = f"\n- DATE ERROR: {date_error}" if date_error else ""
        
        return f"""
CURRENT BOOKING STATUS:
- Service Type: {context.get('service_type') or 'Not selected'}
- Step: {context.get('step')}
- Destination: {context.get('destination') or 'Not provided'}
- Check-in: {context.get('check_in') or 'Not provided'}
- Check-out: {context.get('check_out') or 'Not provided'}
- Guests: {context.get('guests') or 'Not provided'}
- Category: {context.get('selected_category') or 'Not selected'}
- Hotel: {context.get('selected_hotel') or 'Not selected'}
- Room: {context.get('selected_room') or 'Not selected'}{error_section}

IMPORTANT DATE RULES:
- Check-in date must be TODAY or FUTURE (not past)
- Check-out date must be AFTER check-in date
- Example: "12 may to 10 may" is INVALID
- Example: "10 may to 15 may" is VALID

Based on current step, ask user for missing information or call appropriate tools.
If there is a DATE ERROR, explain the error and ask for valid dates again.
"""

    def _execute_tool(self, tool_name: str, args: Dict, context: Dict) -> Any:
        if tool_name == "get_categories":
            return self.tools.get_categories()

        elif tool_name == "search_hotels_by_category":
            category = args.get("category")
            location = args.get("location") or context.get("destination")
            return self.tools.search_hotels_by_category(category, location)

        elif tool_name == "get_hotel_rooms":
            hotel_name = args.get("hotel_name")
            context["selected_hotel"] = hotel_name
            return self.tools.get_hotel_rooms(hotel_name)

        elif tool_name == "calculate_room_price":
            room = args.get("room") or context.get("selected_room_data")
            check_in = args.get("check_in") or context.get("check_in")
            check_out = args.get("check_out") or context.get("check_out")
            guests = args.get("guests") or context.get("guests", 1)
            if not room:
                return {"success": False, "error": "Room not found"}
            return self.tools.calculate_room_price(room, check_in, check_out, guests)

        elif tool_name == "calculate_meal_price":
            meal_type = args.get("meal_type")
            meal_plan_data = args.get("meal_plan_data") or context.get("meal_plan_data", {})
            guests = args.get("guests") or context.get("guests", 1)
            nights = context.get("price_details", {}).get("nights", 1)
            return self.tools.calculate_meal_price(meal_type, meal_plan_data, guests, nights)

        else:
            return {"success": False, "error": f"Unknown tool: {tool_name}"}

    def _update_context(self, tool_name: str, result: Dict, context: Dict):
        if tool_name == "get_categories" and result.get("success"):
            context["step"] = "categories_shown"
            context["categories_from_api"] = result.get("categories", [])

        elif tool_name == "search_hotels_by_category":
            if result.get("success") and result.get("hotels"):
                context["step"] = "hotels_shown"
                context["hotels_list"] = result.get("hotels", [])
                context["selected_category"] = result.get("category")
            else:
                context["step"] = "no_hotels_found"
                context["no_hotels_category"] = result.get("category") or context.get("selected_category")

        elif tool_name == "get_hotel_rooms" and result.get("success"):
            context["step"] = "rooms_shown"
            context["rooms_list"] = result.get("rooms", [])
            context["selected_hotel"] = result.get("hotel_name")
            context["meal_plan_data"] = result.get("meal_plan", {})
            context["full_hotel_details"] = result.get("full_hotel_details", {})

        elif tool_name == "calculate_room_price" and result.get("success"):
            context["step"] = "price_calculated"
            context["price_details"] = result

        elif tool_name == "calculate_meal_price" and result.get("success"):
            context["step"] = "final_summary"
            context["meal_details"] = result

    def _format_response(self, message: str, context: Dict) -> Dict:
        # Check for date error first
        if context.get("date_error") and context.get("step") in ["ask_dates", "ask_dates_for_room"]:
            error_msg = context["date_error"]
            context["date_error"] = None
            return {
                "type": "text",
                "content": f"{error_msg}\n\nPlease provide your check-in and check-out dates again."
            }

        if context.get("step") == "ask_service_type":
            return {
                "type": "buttons",
                "content": "Welcome! What would you like to book?\n\nPlease select an option:",
                "buttons": [
                    {"text": "Hotel Booking", "value": "hotel"},
                    {"text": "Travel Package", "value": "package"}
                ]
            }

        if context.get("service_type") == "package":
            return {
                "type": "text",
                "content": "Travel packages feature is coming soon! Would you like to book a hotel instead? Type 'hotel' to continue."
            }

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

        if context.get("step") == "no_hotels_found":
            categories = context.get("categories_from_api", [])
            failed_cat = context.get("no_hotels_category", "selected")
            destination = context.get("destination", "this city")
            
            # Return category buttons grid first
            category_buttons = [{"text": cat.get("name"), "value": cat.get("name")} for cat in categories if cat.get("name")]
            
            # Then return separate response for Change City button
            # Using a special response type that the frontend will handle as two separate components
            return {
                "type": "buttons_grid_with_separate_button",
                "content": f"No hotels found in {destination} for the {failed_cat} category.\n\nPlease select another category:",
                "buttons": category_buttons,
                "separate_button": {"text": "Change City", "value": "change_city"}
            }

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

        if context.get("rooms_list") and context.get("step") == "rooms_shown":
            rooms = context["rooms_list"]
            hotel_name = context.get("selected_hotel", "Hotel")
            content = f"Rooms at {hotel_name}\n\n"
            for i, room in enumerate(rooms, 1):
                if room.get("images") and len(room["images"]) > 0:
                    content += f"![Room {i}]({room['images'][0]})\n\n"
                content += f"Room {i}: {room.get('room_category', room.get('category', 'N/A'))} - {room.get('room_type', room.get('type', 'N/A'))}\n"
                content += f"Capacity: {room.get('minimum_capacity', 'N/A')} - {room.get('maximum_capacity', 'N/A')} guests\n"
                content += f"Base Price: Rs.{room.get('base_price', 0)}/night\n"
                if room.get('extra_person_price', 0) > 0:
                    content += f"Extra person: Rs.{room.get('extra_person_price', 0)}/night\n"
                content += "\n"
            content += "Select a room to proceed:"
            buttons = [{"text": f"Pick - {r.get('room_category', r.get('category', 'N/A'))} {r.get('room_type', r.get('type', 'N/A'))}", "value": f"pick_room_{i-1}"} for i, r in enumerate(rooms[:5])]
            return {"type": "buttons_grid", "content": content, "buttons": buttons}

        if context.get("step") == "price_calculated":
            price = context.get("price_details", {})
            rooms_needed = price.get("rooms_needed", 1)
            return {
                "type": "buttons",
                "content": f"Room Price Summary\n\n"
                          f"Rooms Needed: {rooms_needed} room(s)\n"
                          f"Nights: {price.get('nights', 0)}\n"
                          f"Total Room Cost: Rs.{price.get('grand_total', 0):,.2f}\n\n"
                          f"Select Meal Plan:",
                "buttons": [
                    {"text": "MAP (Breakfast + Dinner)", "value": "map"},
                    {"text": "CP (Breakfast only)", "value": "cp"},
                    {"text": "EP (No meals)", "value": "ep"}
                ]
            }

        if context.get("step") == "final_summary":
            price = context.get("price_details", {})
            meal = context.get("meal_details", {})
            hotel_name = context.get("selected_hotel", "Hotel")
            room = context.get("selected_room_data", {})
            full_hotel = context.get("full_hotel_details", {})
            
            # Get hotel details
            display_hotel_name = full_hotel.get('hotel_name', hotel_name)
            hotel_category = full_hotel.get('category', context.get('selected_category', 'N/A'))
            hotel_location = full_hotel.get('location', context.get('destination', 'N/A'))
            
            # Get room details
            room_category = room.get('room_category', room.get('category', 'N/A'))
            room_type = room.get('room_type', room.get('type', 'N/A'))
            min_capacity = room.get('minimum_capacity', 'N/A')
            max_capacity = room.get('maximum_capacity', 'N/A')
            extra_person_capacity = room.get('extra_person_capacity', 'N/A')
            base_price = int(room.get('base_price', 0))
            extra_person_price = int(room.get('extra_person_price', 0))
            
            # Get price details
            rooms_needed = price.get('rooms_needed', 1)
            nights = price.get('nights', 0)
            room_total = price.get('room_total', 0)
            extra_total = price.get('extra_total', 0)
            extra_people = price.get('extra_people', 0)
            season_used = price.get('season_used', 'Regular Rate')
            
            # Get seasonal pricing
            seasonal_price_per_night = price.get('seasonal_base_price', base_price)
            seasonal_extra_price = price.get('seasonal_extra_price', extra_person_price)
            
            # Get meal details
            meal_name = meal.get('meal_name', 'No meals')
            meal_total = meal.get('total_meal_price', 0)
            
            # Calculate totals
            room_cost_calculation = f"{rooms_needed} rooms x Rs.{seasonal_price_per_night} x {nights} nights"
            extra_cost_calculation = f"{extra_people} extra persons x Rs.{seasonal_extra_price} x {nights} nights" if extra_people > 0 else "None"
            
            grand_total = room_total + extra_total + meal_total
            
            # Build clean summary card without dashes and underscores
            content = f"""
YOUR BOOKING SUMMARY

Destination: {hotel_location}
Travel Dates: {context.get('check_in')} to {context.get('check_out')} ({nights} nights)
Total Guests: {context.get('guests')} people

Hotel Details
Hotel Name: {display_hotel_name}
Category: {hotel_category}

Room Details
Room Type: {room_category} - {room_type}
Capacity: {min_capacity} - {max_capacity} guests per room
Extra Person Capacity: {extra_person_capacity}

Pricing Breakdown
Per Night Rates:
Room Rate: Rs.{seasonal_price_per_night}/night/room
Extra Person Rate: Rs.{seasonal_extra_price}/night/person
Season Applied: {season_used}

Total Room Cost: Rs.{room_total:,.2f}
({room_cost_calculation})

Total Extra Persons Cost: Rs.{extra_total:,.2f}
({extra_cost_calculation})

Meal Plan: {meal_name}
Meal Cost: Rs.{meal_total:,.2f}

GRAND TOTAL: Rs.{grand_total:,.2f}
"""
            
            return {
                "type": "buttons",
                "content": content.strip(),
                "buttons": [
                    {"text": "📖 BOOK NOW", "value": "confirm"},
                    {"text": "Change Meal Plan", "value": "change_meal_plan"},
                    {"text": "Other Hotels", "value": "other_hotels"}
                ]
            }

        if context.get("step") == "booking_confirmed":
            return {
                "type": "text",
                "content": f"BOOKING CONFIRMED!\n\nThank you for booking with us!\n\nReference: {datetime.now().strftime('HOTEL%Y%m%d%H%M%S')}\n\nWe will send details to your phone shortly.\n\nHave a great stay!\n\nType 'hi' to start a new booking!"
            }

        if message and len(message) > 0:
            return {"type": "text", "content": message}

        return {"type": "text", "content": "How can I help you with your hotel booking?"}

    def reset_session(self, phone: str):
        if phone in self.sessions:
            del self.sessions[phone]
            logger.info(f"Hotel session reset for {phone}")
        self.package_agent.reset_session(phone)