# agent/ai_agent.py
import json
import os
import logging
from typing import Dict, Any, List
from openai import OpenAI
from agent.tools import TravelTools, TOOL_DEFINITIONS
from datetime import datetime
import re

logger = logging.getLogger(__name__)

class AIHotelAgent:
    def __init__(self):
        self.client = OpenAI(api_key=os.getenv("OPEN_API_KEY"))
        self.tools = TravelTools()
        self.sessions = {}

    def get_system_prompt(self) -> str:
        return """You are a hotel booking AI agent with REAL data access.

FIRST: Ask user "Are you looking for hotels or travel packages?"
- If hotels, proceed with hotel flow
- If packages, respond: "Packages feature coming soon!"

HOTEL BOOKING FLOW (Follow STRICTLY in this order):
1. Ask: "Which city are you looking for hotels in?"
2. DESTINATION VALIDATION (CRITICAL):
   - When user provides a city name, use your parametric knowledge to verify it is a real, known city or town in India or worldwide.
   - If the city name does NOT match any real place you know of, respond: "I could not find a place called [city]. Could you please retype the destination?"
   - Do NOT proceed to step 3 until a valid, recognizable city is confirmed.
3. After valid destination confirmed, ask: "What are your check-in and check-out dates?"
4. After dates, ask: "How many guests will be staying?"
5. After guests, call get_categories() and show ALL categories from API as suggestion buttons
6. User selects category, call search_hotels_by_category(category, destination)
   - If no hotels found for that category in the destination, show all category buttons again + a "Change City" button at the bottom. Do NOT ask for dates or guests again.
   - If hotels found, show hotels with: Image, Name, Category, Description, and "View Rooms" button
7. User clicks "Change City":
   - Only reset the city. Keep check-in, check-out, and guests as they are. Do NOT ask for dates or guests again.
   - Ask only: "Which city would you like to search hotels in?"
   - After user gives new city, validate it, then immediately show category buttons (skip dates and guests steps entirely)
8. User clicks View Rooms, call get_hotel_rooms(hotel_name)
9. Show ALL rooms with: Image, Room Category, Room Type, Capacity, Price, and "Pick" button
10. User picks room, call calculate_room_price() and show price breakdown
11. Show meal plan options ONCE: MAP / CP / EP buttons
12. User selects meal, call calculate_meal_price() and show FINAL SUMMARY
13. FINAL SUMMARY must always show these 3 buttons only:
    - "Confirm Booking"
    - "Change Meal Plan" (shows MAP/CP/EP again, user can change as many times as they want until confirmed)
    - "Other Hotels" (shows remaining hotels in the list excluding the currently selected hotel)
14. "Other Hotels" logic:
    - If other hotels exist in the current list → show them (excluding current hotel), same hotel card format
    - If no other hotels → show message with current hotel name + "Continue with [Hotel Name]" button only
    - "Continue with [Hotel Name]" → go directly to FINAL SUMMARY (do NOT show rooms or meal again, everything already selected)
15. "Change Meal Plan":
    - Show MAP / CP / EP buttons again
    - User picks new meal → recalculate and show updated FINAL SUMMARY with same 3 buttons
    - Repeat until user confirms
16. Ask: "Confirm booking?"
17. After user confirms booking, show booking confirmation and start a NEW conversation (clear all session data)

CRITICAL RULES:
- NEVER hardcode cities or categories, ALWAYS fetch from API
- Use LLM to extract dates, cities, and guest counts from natural language
- Validate dates: end date must be AFTER start date, no past dates
- ALWAYS use tools to fetch real data
- NEVER hallucinate hotels, rooms, or categories
- Show images when available from API
- Do NOT use emoji, icons, dashes (---), or underscores (__) in any response
- Keep all responses clean plain text or structured data
- NEVER ask for dates or guests again once they are already collected
- NEVER show MAP/CP/EP buttons inside the final summary directly — only show "Change Meal Plan" button there
- After booking is confirmed, reset the session completely so user can start fresh
"""

    def execute(self, phone: str, user_message: str, state: dict = None) -> Dict:
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
                "full_hotel_details": None,  # NEW: store full hotel details
                "step": "ask_service_type"
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

        # ── NEW: Handle "Change City" button ──────────────────────────────────
        # User wants to pick a different city — keep dates and guests intact.
        if user_message.strip().lower() == "change_city":
            context["destination"] = None
            context["selected_category"] = None
            context["selected_hotel"] = None
            context["selected_hotel_data"] = None
            context["hotels_list"] = None
            context["rooms_list"] = None
            # Mark that when next city arrives we jump straight to categories
            context["step"] = "change_city_ask_destination"
            if state is not None:
                state["data"] = context
            return {"type": "text", "content": "Which city would you like to search hotels in?"}
        # ─────────────────────────────────────────────────────────────────────

        # Handle "View Rooms" button click
        if "View Rooms -" in user_message:
            hotel_name = user_message.replace("View Rooms -", "").strip()
            context["selected_hotel"] = hotel_name
            rooms_result = self.tools.get_hotel_rooms(hotel_name)
            if rooms_result.get("success"):
                context["rooms_list"] = rooms_result.get("rooms", [])
                context["meal_plan_data"] = rooms_result.get("meal_plan", {})
                context["full_hotel_details"] = rooms_result.get("full_hotel_details", {})  # NEW: store full hotel details
                context["step"] = "rooms_shown"
                # Save to persistent state
                if state is not None:
                    state["data"] = context
                return self._format_response("", context)
            else:
                return {"type": "text", "content": f"Sorry, could not fetch rooms: {rooms_result.get('error')}"}

        # Handle room pick by index (pick_room_0, pick_room_1, ...)
        if user_message.startswith("pick_room_"):
            try:
                room_index = int(user_message.replace("pick_room_", "").strip())
                rooms_list = context.get("rooms_list") or []

                # Re-fetch rooms if lost after server restart
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

                    # If dates lost after restart, ask user again
                    if not check_in or not check_out:
                        context["step"] = "ask_dates_for_room"
                        # Save to persistent state
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
                        # Save to persistent state
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

        # Handle "Continue with current hotel" — skip room pick, go straight to final summary
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
                # fallback: re-show rooms
                return self._format_response("", context)

        # Handle "Change Meal Plan" button — show meal options again
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

        # Handle meal selection from buttons
        if user_message.lower() in ["map", "cp", "ep"] and context.get("price_details"):
            meal_result = self.tools.calculate_meal_price(
                user_message.lower(),
                context.get("meal_plan_data", {}),
                context.get("guests", 1),
                context.get("price_details", {}).get("nights", 1)
            )
            if meal_result.get("success"):
                context["meal_details"] = meal_result
                context["step"] = "final_summary"
                # Save to persistent state
                if state is not None:
                    state["data"] = context
                return self._format_response("", context)

        # Handle confirm booking
        if user_message.lower() == "confirm" and context.get("step") == "final_summary":
            context["step"] = "booking_confirmed"
            # Save to persistent state before clearing
            if state is not None:
                state["data"] = context
            
            # Get the confirmation response
            response = self._format_response("confirm", context)
            
            # CRITICAL: Reset the session after booking confirmation
            # This clears all conversation history and context
            self.reset_session(phone)
            
            # Also clear persistent state
            if state is not None:
                # Reset to fresh state
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
                    "step": "ask_service_type"
                }
            
            logger.info(f"Session reset for {phone} after booking confirmation")
            return response

        # Handle category selection directly without LLM (eliminates double LLM call)
        categories_in_context = context.get("categories_from_api") or []
        known_categories = [c.get("name", "").lower() for c in categories_in_context]
        if user_message.strip().lower() in known_categories and context.get("destination"):
            matched_category = user_message.strip()
            context["selected_category"] = matched_category
            result = self.tools.search_hotels_by_category(matched_category, context.get("destination"))
            self._update_context("search_hotels_by_category", result, context)
            # Save to persistent state
            if state is not None:
                state["data"] = context
            return self._format_response("", context)

        # Use LLM to extract info from message
        extracted_info = self._extract_info_with_llm(user_message, context)
        self._apply_extracted_info(extracted_info, context)
        
        # CRITICAL FIX: Immediately save context after extraction
        if state is not None:
            state["data"] = context
            logger.info(f"Saved context after extraction - check_in={context.get('check_in')}, check_out={context.get('check_out')}, destination={context.get('destination')}, guests={context.get('guests')}")

        # If city just changed and dates/guests already exist, fetch categories immediately
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

        # If dates were just provided and a room is already selected, calculate price now
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
                # Save to persistent state
                if state is not None:
                    state["data"] = context
                return self._format_response("", context)

        # Save context to persistent state after any update
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

                # Save to persistent state
                if state is not None:
                    state["data"] = context

                return self._format_response(final_message, context)

            else:
                response_text = assistant_message.content
                session["history"].append(assistant_message)
                
                # Save to persistent state
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
   - "12th to 16th" means assume current month and year
   - "12 to 16" means assume current month and year
   - "next week" means calculate
   - "Dec 25th to Dec 30th" means specific dates
   - "1/12/2026 to 5/12/2026" means specific dates

   Rules:
   - End date must be AFTER start date
   - No past dates allowed
   - If year not specified, use current year or next year if date has passed

3. Number of Guests: Extract from phrases like:
   - "me and my wife" means 2
   - "me, my wife, sister, father" means 4
   - "couple" means 2
   - "family of 4" means 4
   - "2 adults" means 2
   - "single" means 1

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
    "guests": number or null,
    "service_type": "hotel" or "package" or null
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
            return {"destination": None, "check_in": None, "check_out": None, "guests": None, "service_type": None}

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
                # Dates & guests already set — go straight to categories
                context["step"] = "show_categories"

        today = datetime.now().date()

        if extracted.get("check_in") and extracted.get("check_out"):
            try:
                check_in_date = datetime.strptime(extracted["check_in"], "%Y-%m-%d").date()
                check_out_date = datetime.strptime(extracted["check_out"], "%Y-%m-%d").date()

                if check_in_date >= today and check_out_date > check_in_date:
                    # Update dates in context
                    context["check_in"] = extracted["check_in"]
                    context["check_out"] = extracted["check_out"]
                    logger.info(f"✅ Dates saved to context - Check-in: {context['check_in']}, Check-out: {context['check_out']}")
                    
                    if context.get("step") == "ask_dates":
                        context["step"] = "ask_guests"
                else:
                    logger.warning(f"Invalid dates: {check_in_date} to {check_out_date}")
            except Exception as e:
                logger.error(f"Date validation error: {e}")

        if not context.get("guests") and extracted.get("guests"):
            guests = int(extracted["guests"])
            if 1 <= guests <= 20:
                context["guests"] = guests
                logger.info(f"✅ Guests saved to context: {context['guests']}")
                if context.get("destination") and context.get("check_in") and context.get("check_out"):
                    context["step"] = "show_categories"

    def _get_flow_status(self, context: Dict) -> str:
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
- Room: {context.get('selected_room') or 'Not selected'}

Based on current step, ask user for missing information or call appropriate tools.
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

        # ── UPDATED: No hotels found → show category grid + "Change City" button ──
        if context.get("step") == "no_hotels_found":
            categories = context.get("categories_from_api", [])
            failed_cat = context.get("no_hotels_category", "selected")
            destination = context.get("destination", "this city")

            # Build category buttons
            buttons = [
                {"text": cat.get("name"), "value": cat.get("name")}
                for cat in categories if cat.get("name")
            ]

            # Append the "Change City" button at the end
            buttons.append({"text": "Change City", "value": "change_city"})

            return {
                "type": "buttons_grid",
                "content": (
                    f"No hotels found in {destination} for the {failed_cat} category.\n\n"
                    f"Please select another category or change your city:"
                ),
                "buttons": buttons
            }
        # ─────────────────────────────────────────────────────────────────────

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
                content += f"Room {i}: {room['category']} - {room['type']}\n"
                content += f"Capacity: {room['min_capacity']} - {room['max_capacity']} guests\n"
                content += f"Base Price: Rs.{room['base_price']}/night\n"
                if room.get('extra_person_price', 0) > 0:
                    content += f"Extra person: Rs.{room['extra_person_price']}/night\n"
                content += "\n"
            content += "Select a room to proceed:"
            buttons = [{"text": f"Pick - {r['category']} {r['type']}", "value": f"pick_room_{i-1}"} for i, r in enumerate(rooms[:5])]
            return {"type": "buttons_grid", "content": content, "buttons": buttons}

        if context.get("step") == "price_calculated":
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

        # ============================================================
        # FINAL SUMMARY WITH FULL HOTEL DETAILS (UPDATED)
        # ============================================================
        if context.get("step") == "final_summary":
            price = context.get("price_details", {})
            meal = context.get("meal_details", {})
            hotel_name = context.get("selected_hotel", "Hotel")
            room = context.get("selected_room_data", {})
            room_total = price.get("grand_total", 0)
            meal_total = meal.get("total_meal_price", 0)
            grand_total = room_total + meal_total
            meal_cost_line = f"Rs.{meal_total:,.2f}" if meal_total > 0 else "Rs.0.00 (included)"
            
            # Get full hotel details from context
            full_hotel = context.get("full_hotel_details", {})
            
            # Build hotel information section
            hotel_info = ""
            if full_hotel:
                hotel_info = f"""
HOTEL INFORMATION
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Hotel Name: {full_hotel.get('hotel_name', hotel_name)}
Category: {full_hotel.get('category', 'N/A')}
Location: {full_hotel.get('location', context.get('destination', 'N/A'))}

Description:
{full_hotel.get('description', 'No description available')[:500]}

Contact:
Phone: {', '.join(full_hotel.get('phones', [])) if full_hotel.get('phones') else 'N/A'}
Email: {', '.join(full_hotel.get('emails', [])) if full_hotel.get('emails') else 'N/A'}

Extra Services:
{', '.join(full_hotel.get('extra_services', [])) if full_hotel.get('extra_services') else 'No extra services listed'}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
            
            # Build room facilities section
            room_facilities = ""
            if room.get('facilities'):
                room_facilities = "\nFacilities:\n" + "\n".join([f"  • {f}" for f in room.get('facilities', [])])
            
            # Build seasonal pricing section
            seasonal_info = ""
            if room.get('seasons'):
                seasonal_info = "\n\nSeasonal Pricing (for reference):"
                for season in room.get('seasons', [])[:4]:
                    seasonal_info += f"\n  • {season.get('season_name', 'Unknown')}: Rs.{season.get('price', 'N/A')}/night (Extra: Rs.{season.get('extra_price', 'N/A')})"
            
            room_details = f"""
ROOM DETAILS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Room Type: {room.get('category', 'N/A')} - {room.get('type', 'N/A')}
Capacity: {room.get('min_capacity', 'N/A')} - {room.get('max_capacity', 'N/A')} guests
Base Price: Rs.{room.get('base_price', 0)}/night
Extra Person Price: Rs.{room.get('extra_person_price', 0)}/night{room_facilities}{seasonal_info}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

BOOKING SUMMARY
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Guests: {context.get('guests')}
Check-in: {context.get('check_in')}
Check-out: {context.get('check_out')}
Nights: {price.get('nights', 0)}

Meal Plan: {meal.get('meal_name', 'No meals')}
Meal Cost: {meal_cost_line}

Price Breakdown:
Room Total: Rs.{room_total:,.2f}
Meal Total: {meal_cost_line}
Grand Total: Rs.{grand_total:,.2f}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Confirm your booking?
"""
            
            content = hotel_info + room_details
            
            return {
                "type": "buttons",
                "content": content,
                "buttons": [
                    {"text": "Confirm Booking", "value": "confirm"},
                    {"text": "Change Meal Plan", "value": "change_meal_plan"},
                    {"text": "Other Hotels", "value": "other_hotels"}
                ]
            }
        # ============================================================

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
            logger.info(f"Session reset for {phone}")