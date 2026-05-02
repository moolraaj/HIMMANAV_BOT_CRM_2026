# """
# agent/agent_executor.py

# Complete travel agent with room display, meal selection, and full summary
# """

# import os
# import sys
# import json
# import logging
# from datetime import date, datetime
# from dotenv import load_dotenv
# from openai import OpenAI

# sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# from agent.prompts import (
#     DATE_PROMPT,
#     VALIDATE_CITY_PROMPT,
#     HOTEL_PROMPT,
#     CONFIRM_PROMPT,
#     PEOPLE_PROMPT,
#     PARTIAL_TRIP_PROMPT,
#     MEAL_SELECTION_PROMPT,
#     FINAL_COMPLETE_SUMMARY_PROMPT
# )
# from helpers.helper import extract_number, parse_date, clean_llm_response

# import requests

# logger = logging.getLogger(__name__)

# CATEGORIES_URL = "https://silver-spoonbill-286441.hostingersite.com/wp-json/hm/v1/hotel-categories"
# HOTELS_URL = "https://silver-spoonbill-286441.hostingersite.com/wp-json/hm/v1/hotels?phone=919816440734"

# load_dotenv()


# def get_hotel_categories():
#     try:
#         response = requests.get(CATEGORIES_URL, timeout=10)
#         response.raise_for_status()
#         return response.json()
#     except Exception as e:
#         logger.error(f"get_hotel_categories error: {e}")
#         return {"data": []}


# def get_all_hotels():
#     """Fetch all hotels from the API"""
#     try:
#         response = requests.get(HOTELS_URL, timeout=10)
#         response.raise_for_status()
#         data = response.json()
#         return data.get("hotels", [])
#     except Exception as e:
#         logger.error(f"get_all_hotels error: {e}")
#         return []


# def get_hotels_by_category(category: str, location: str) -> list:
#     """Filter hotels by category and location"""
#     all_hotels = get_all_hotels()
#     filtered = []
    
#     for hotel in all_hotels:
#         hotel_category = hotel.get("category", "").lower()
#         hotel_location = hotel.get("location", "").lower()
        
#         if hotel_category == category.lower() and location.lower() in hotel_location:
#             filtered.append(hotel)
    
#     return filtered


# def calculate_total_price(hotel_room, check_in, check_out, guests):
#     """Calculate total price based on seasons and guests"""
#     try:
#         check_in_date = datetime.strptime(check_in, "%Y-%m-%d")
#         check_out_date = datetime.strptime(check_out, "%Y-%m-%d")
#         nights = (check_out_date - check_in_date).days
        
#         seasons = hotel_room.get("seasons", [])
#         applicable_season = None
        
#         for season in seasons:
#             start = datetime.strptime(season["starting_date"], "%d %B %Y")
#             end = datetime.strptime(season["end_date"], "%d %B %Y")
#             if start <= check_in_date <= end:
#                 applicable_season = season
#                 break
        
#         if applicable_season:
#             price_per_night = float(applicable_season["price"])
#             extra_person_price = float(applicable_season["extra_price"])
#         else:
#             price_per_night = float(hotel_room.get("base_price", 0))
#             extra_person_price = float(hotel_room.get("extra_person_price", 0))
        
#         max_capacity = int(hotel_room.get("maximum_capacity", 2))
#         extra_people = max(0, guests - max_capacity)
        
#         base_total = price_per_night * nights
#         extra_total = extra_person_price * extra_people * nights
#         total = base_total + extra_total
        
#         return {
#             "base_price": price_per_night,
#             "extra_person_price": extra_person_price,
#             "total": total,
#             "nights": nights,
#             "extra_people": extra_people,
#             "room_base_total": base_total,
#             "extra_total": extra_total
#         }
#     except Exception as e:
#         logger.error(f"calculate_total_price error: {e}")
#         return {
#             "base_price": 0,
#             "extra_person_price": 0,
#             "total": 0,
#             "nights": 0,
#             "extra_people": 0,
#             "room_base_total": 0,
#             "extra_total": 0
#         }


# def calculate_meal_price(meal_plan, guests, nights):
#     """Calculate meal plan total price"""
#     meal_prices = {
#         "1": {"name": "No Meals", "price": 0},
#         "2": {"name": "Breakfast Only", "price": 500},
#         "3": {"name": "Half Board (Breakfast + Dinner)", "price": 1200},
#         "4": {"name": "Full Board (All Meals)", "price": 1800}
#     }
    
#     selected = meal_prices.get(meal_plan, meal_prices["1"])
#     total = selected["price"] * guests * nights
    
#     return {
#         "plan_name": selected["name"],
#         "price_per_person": selected["price"],
#         "total": total
#     }


# class AgentExecutor:

#     def __init__(self):
#         self._client = OpenAI(api_key=os.getenv("OPEN_API_KEY"))
#         self._sessions = {}
#         logger.info("AgentExecutor initialised")

#     def execute(self, phone: str, user_message: str) -> dict:
#         """Main entry point for processing messages"""
#         if phone not in self._sessions:
#             self._sessions[phone] = self._fresh_state()

#         state = self._sessions[phone]
#         logger.info(f"[{phone}] step={state['step']} msg={user_message}")

#         return self._route(phone, user_message, state)

#     def get_state(self, phone: str) -> dict:
#         if phone not in self._sessions:
#             self._sessions[phone] = self._fresh_state()
#         return self._sessions[phone]

#     def _fresh_state(self) -> dict:
#         return {
#             "step": "start",
#             "flow": None,
#             "data": {}
#         }

#     def _reset(self, phone: str):
#         self._sessions[phone] = self._fresh_state()

#     def _route(self, phone: str, message: str, state: dict) -> dict:
#         step = state["step"]
#         text = message.lower().strip()

#         if step == "start":
#             if text in ["hi", "hii", "hello", "hey"]:
#                 return {
#                     "type": "buttons",
#                     "content": "Hi 👋 I'm your travel assistant.\nWhat can I help you with?",
#                     "buttons": [
#                         {"text": "Find Hotels", "value": "hotels"},
#                         {"text": "Find Packages", "value": "packages"}
#                     ]
#                 }
#             elif text in ["hotels", "find hotels"]:
#                 state["step"] = "hotel_ask_destination"
#                 state["flow"] = "hotel"
#                 state["data"] = {}
#                 return {
#                     "type": "text",
#                     "content": "🏨 Let me help you find the best hotels!\n\n📍 First, tell me your destination city."
#                 }
#             elif text in ["packages", "find packages"]:
#                 state["step"] = "package_ask_dates"
#                 state["flow"] = "package"
#                 state["data"] = {}
#                 return {
#                     "type": "text",
#                     "content": "📅 Tell me your travel dates (e.g., '12 to 20 june' or '12th to 20th')"
#                 }
#             else:
#                 partial = self._extract_partial_trip(message)
#                 destination = partial.get("destination", "")
#                 start_date = partial.get("start_date", "")
#                 end_date = partial.get("end_date", "")

#                 if "hotel" in text:
#                     flow = "hotel"
#                 elif any(k in text for k in ["package", "trip", "tour", "itinerary"]):
#                     flow = "package"
#                 elif destination or start_date:
#                     flow = None
#                 else:
#                     return {
#                         "type": "buttons",
#                         "content": "What would you like to do?",
#                         "buttons": [
#                             {"text": "Find Hotels", "value": "hotels"},
#                             {"text": "Find Packages", "value": "packages"}
#                         ]
#                     }

#                 if flow is None:
#                     state["data"] = {}
#                     if destination:
#                         state["data"]["destination"] = destination
#                     if start_date:
#                         state["data"]["start_date"] = start_date
#                     if end_date:
#                         state["data"]["end_date"] = end_date
#                     state["step"] = "ask_flow"
#                     return {
#                         "type": "buttons",
#                         "content": f"Got it! Are you looking for hotels or a travel package?",
#                         "buttons": [
#                             {"text": "Find Hotels", "value": "hotels"},
#                             {"text": "Find Packages", "value": "packages"}
#                         ]
#                     }

#                 state["flow"] = flow
#                 state["data"] = {}

#                 if flow == "hotel":
#                     if destination:
#                         state["data"]["destination"] = destination
#                     if start_date:
#                         state["data"]["start_date"] = start_date
#                     if end_date:
#                         state["data"]["end_date"] = end_date
#                     return self._jump_hotel_flow(state)
#                 else:
#                     if destination:
#                         state["data"]["destination"] = destination
#                     if start_date:
#                         state["data"]["start_date"] = start_date
#                     if end_date:
#                         state["data"]["end_date"] = end_date
#                     return self._jump_package_flow(state)

#         if step == "ask_flow":
#             if text in ["hotels", "find hotels"]:
#                 state["flow"] = "hotel"
#                 return self._jump_hotel_flow(state)
#             elif text in ["packages", "find packages"]:
#                 state["flow"] = "package"
#                 return self._jump_package_flow(state)
#             else:
#                 return {
#                     "type": "buttons",
#                     "content": "Please choose one:",
#                     "buttons": [
#                         {"text": "Find Hotels", "value": "hotels"},
#                         {"text": "Find Packages", "value": "packages"}
#                     ]
#                 }

#         # Hotel Flow
#         if step == "hotel_ask_destination":
#             return self._handle_destination(message, state)
#         if step == "hotel_ask_dates":
#             return self._handle_dates(message, state)
#         if step == "hotel_ask_end_date_only":
#             return self._handle_end_date(message, state)
#         if step == "hotel_confirm_details":
#             return self._handle_confirmation(message, state)
#         if step == "hotel_ask_people":
#             return self._handle_people(message, state)
#         if step == "hotel_category_selection":
#             return self._handle_category(message, state)
#         if step == "hotel_selection":
#             return self._handle_hotel_selection(phone, message, state)
        
#         # Room Selection Flow
#         if step == "room_selection":
#             return self._handle_room_selection(message, state)
        
#         # Meal Selection Flow
#         if step == "meal_selection":
#             return self._handle_meal_selection(message, state)
        
#         # Final Summary
#         if step == "final_summary":
#             return self._handle_final_summary(message, state)

#         # Package Flow
#         if step == "package_ask_dates":
#             return self._handle_package_dates(message, state)
#         if step == "package_ask_end_date":
#             return self._handle_package_end_date(message, state)
#         if step == "package_ask_destination":
#             return self._handle_package_destination(message, state)
#         if step == "package_confirm_details":
#             return self._handle_package_confirmation(message, state)
#         if step == "package_ask_people":
#             return self._handle_package_people(message, state)

#         # Navigation
#         if text in ["see other hotels", "new search"]:
#             state["step"] = "start"
#             return {
#                 "type": "buttons",
#                 "content": "What would you like to do?",
#                 "buttons": [
#                     {"text": "Find Hotels", "value": "hotels"},
#                     {"text": "Find Packages", "value": "packages"}
#                 ]
#             }

#         return {
#             "type": "text",
#             "content": "🤔 I didn't understand that. Try 'hi', 'find packages', or 'find hotels'."
#         }

#     def _jump_hotel_flow(self, state: dict) -> dict:
#         data = state["data"]
#         if not data.get("destination"):
#             state["step"] = "hotel_ask_destination"
#             return {
#                 "type": "text",
#                 "content": "🏨 Let me help you find hotels!\n\n📍 Which city would you like to stay in?"
#             }
#         if not data.get("start_date") or not data.get("end_date"):
#             state["step"] = "hotel_ask_dates"
#             return {
#                 "type": "text",
#                 "content": f"📍 Destination: *{data['destination']}*\n\n📅 Now tell me your check-in and check-out dates.\n\n*Example: 12 to 20 june*"
#             }
#         start_dt = parse_date(data["start_date"])
#         end_dt = parse_date(data["end_date"])
#         nights = (end_dt - start_dt).days if (start_dt and end_dt) else "?"
#         state["step"] = "hotel_confirm_details"
#         return {
#             "type": "buttons",
#             "content": (
#                 f"📅 Please confirm your details:\n\n"
#                 f"📍 Destination: {data['destination']}\n"
#                 f"📅 Check-in: {data['start_date']}\n"
#                 f"📅 Check-out: {data['end_date']}\n"
#                 f"📆 Total: {nights} nights\n\n"
#                 f"Is this correct?"
#             ),
#             "buttons": [
#                 {"text": "✅ Yes, Proceed", "value": "yes"},
#                 {"text": "❌ No, Change Dates", "value": "no"}
#             ]
#         }

#     def _jump_package_flow(self, state: dict) -> dict:
#         data = state["data"]
#         if not data.get("start_date") or not data.get("end_date"):
#             state["step"] = "package_ask_dates"
#             return {
#                 "type": "text",
#                 "content": "📅 Tell me your travel dates (e.g., '12 to 20 june')"
#             }
#         if not data.get("destination"):
#             state["step"] = "package_ask_destination"
#             return {
#                 "type": "text",
#                 "content": f"📅 Dates: {data['start_date']} → {data['end_date']}\n\n📍 Now tell me your destination."
#             }
#         state["step"] = "package_confirm_details"
#         return {
#             "type": "buttons",
#             "content": (
#                 f"📍 Destination: {data['destination']}\n"
#                 f"📅 Dates: {data['start_date']} → {data['end_date']}\n\n"
#                 f"Is this correct?"
#             ),
#             "buttons": [
#                 {"text": "✅ Yes, Proceed", "value": "yes"},
#                 {"text": "❌ No, Change", "value": "no"}
#             ]
#         }

#     def _handle_destination(self, message: str, state: dict) -> dict:
#         validation_result = self._validate_city(message)
#         if validation_result.get("is_valid"):
#             corrected_city = validation_result["corrected_name"]
#             state["data"]["destination"] = corrected_city
#             state["step"] = "hotel_ask_dates"
#             prefix = (
#                 f"📍 Got it! You meant **{corrected_city}** ({validation_result.get('country', '')})\n\n"
#                 if corrected_city.lower() != message.lower()
#                 else f"📍 Great! Destination: {corrected_city}\n\n"
#             )
#             return {
#                 "type": "text",
#                 "content": prefix + "Now tell me your check-in and check-out dates.\n\n*Example: 12 to 20 june or 12th to 20th*"
#             }
#         else:
#             return {
#                 "type": "text",
#                 "content": f"❌ \"{message}\" doesn't appear to be a valid city.\n\n{validation_result.get('suggestion', 'Please enter a valid city name')}"
#             }

#     def _handle_dates(self, message: str, state: dict) -> dict:
#         dates = self._extract_dates(message)
#         start_date = dates.get("start_date", "")
#         end_date = dates.get("end_date", "")
#         if start_date and end_date:
#             start_dt = parse_date(start_date)
#             end_dt = parse_date(end_date)
#             if start_dt and end_dt and end_dt > start_dt:
#                 state["data"]["start_date"] = start_date
#                 state["data"]["end_date"] = end_date
#                 state["step"] = "hotel_confirm_details"
#                 return {
#                     "type": "buttons",
#                     "content": (
#                         f"📅 Please confirm your dates:\n\n"
#                         f"📍 Destination: {state['data']['destination']}\n"
#                         f"📅 Check-in: {start_date}\n"
#                         f"📅 Check-out: {end_date}\n"
#                         f"📆 Total: {(end_dt - start_dt).days} nights\n\n"
#                         f"Is this correct?"
#                     ),
#                     "buttons": [
#                         {"text": "✅ Yes, Proceed", "value": "yes"},
#                         {"text": "❌ No, Change Dates", "value": "no"}
#                     ]
#                 }
#             else:
#                 return {
#                     "type": "text",
#                     "content": "❌ Check-out date must be after check-in date.\n\nPlease tell me your dates again (e.g., '12 to 20 june')"
#                 }
#         elif start_date and not end_date:
#             state["data"]["start_date"] = start_date
#             state["step"] = "hotel_ask_end_date_only"
#             return {
#                 "type": "text",
#                 "content": f"👍 Check-in: {start_date}\n\nNow tell me your check-out date."
#             }
#         else:
#             return {
#                 "type": "text",
#                 "content": (
#                     f"❌ I couldn't understand '{message}'.\n\n"
#                     "Please tell me your dates like:\n"
#                     "• 12 to 20 june\n• 12th to 20th\n• 12 june\n• tomorrow"
#                 )
#             }

#     def _handle_end_date(self, message: str, state: dict) -> dict:
#         dates = self._extract_dates(message)
#         end_date = dates.get("start_date", "")
#         if end_date:
#             start_dt = parse_date(state["data"].get("start_date"))
#             end_dt = parse_date(end_date)
#             if start_dt and end_dt and end_dt > start_dt:
#                 state["data"]["end_date"] = end_date
#                 state["step"] = "hotel_confirm_details"
#                 return {
#                     "type": "buttons",
#                     "content": (
#                         f"📅 Please confirm your dates:\n\n"
#                         f"📍 Destination: {state['data']['destination']}\n"
#                         f"📅 Check-in: {state['data']['start_date']}\n"
#                         f"📅 Check-out: {end_date}\n"
#                         f"📆 Total: {(end_dt - start_dt).days} nights\n\n"
#                         f"Is this correct?"
#                     ),
#                     "buttons": [
#                         {"text": "✅ Yes, Proceed", "value": "yes"},
#                         {"text": "❌ No, Change Dates", "value": "no"}
#                     ]
#                 }
#             else:
#                 return {
#                     "type": "text",
#                     "content": f"❌ Check-out date must be after {state['data']['start_date']}.\n\nPlease tell me a valid check-out date."
#                 }
#         else:
#             return {
#                 "type": "text",
#                 "content": f"❌ I couldn't understand '{message}' as a date.\n\nPlease tell me your check-out date (e.g., '20 june', '20th', 'next friday')"
#             }

#     def _handle_confirmation(self, message: str, state: dict) -> dict:
#         if message.lower() in ["yes", "✅ yes, proceed", "proceed"]:
#             state["step"] = "hotel_ask_people"
#             return {
#                 "type": "text",
#                 "content": "👍 Great! Dates confirmed.\n\n👥 How many people are traveling? (Just type the number)"
#             }
#         else:
#             state["step"] = "hotel_ask_dates"
#             return {
#                 "type": "text",
#                 "content": "📅 OK, let's try again. Please tell me your check-in and check-out dates.\n\n*Example: 12 to 20 june*"
#             }

#     def _handle_people(self, message: str, state: dict) -> dict:
#         people_count = extract_number(message)
#         if people_count is None:
#             return {"type": "text", "content": "❌ Please enter a valid number (e.g., 2, 3, 4)."}
#         elif people_count <= 0:
#             return {"type": "text", "content": "❌ Please enter a valid number of people (1 or more)."}
#         elif people_count > 20:
#             return {"type": "text", "content": "❌ For groups larger than 20 people, please contact us directly for a group discount!"}
#         state["data"]["people"] = str(people_count)
#         state["step"] = "hotel_category_selection"
#         return self._show_categories(state)

#     def _show_categories(self, state: dict) -> dict:
#         categories_data = get_hotel_categories()
#         if categories_data and "data" in categories_data:
#             categories = [c["category_name"] for c in categories_data["data"]]
#         else:
#             categories = ["Budget", "Standard", "Luxury"]
#         buttons = [{"text": cat, "value": cat} for cat in categories]
#         buttons.append({"text": "🏨 Show All Hotels", "value": "show all hotels"})
#         buttons.append({"text": "📍 Change Destination", "value": "change destination"})
#         summary = (
#             f"✅ Trip Details Confirmed:\n\n"
#             f"📍 {state['data']['destination']}\n"
#             f"📅 {state['data']['start_date']} → {state['data']['end_date']}\n"
#             f"👥 {state['data']['people']} people\n\n"
#             f"🏨 Please select a hotel category:"
#         )
#         return {
#             "type": "buttons_grid",
#             "content": summary,
#             "buttons": buttons
#         }

#     def _handle_category(self, message: str, state: dict) -> dict:
#         selected_category = message.strip()
#         destination = state["data"]["destination"]
#         if selected_category.lower() == "change destination":
#             state["step"] = "hotel_ask_destination"
#             state["data"] = {}
#             return {"type": "text", "content": "📍 Let's start over. Tell me your destination city."}
#         if selected_category.lower() == "show all hotels":
#             all_hotels = get_all_hotels()
#             unique_hotels = [h for h in all_hotels if destination.lower() in h.get("location", "").lower()]
#         else:
#             unique_hotels = get_hotels_by_category(selected_category, destination)
#         if not unique_hotels:
#             categories_data = get_hotel_categories()
#             categories = [c["category_name"] for c in categories_data.get("data", [])] or ["Budget", "Standard", "Luxury"]
#             buttons = [{"text": cat, "value": cat} for cat in categories]
#             buttons.append({"text": "🏨 Show All Hotels", "value": "show all hotels"})
#             buttons.append({"text": "📍 Change Destination", "value": "change destination"})
#             return {
#                 "type": "buttons_grid",
#                 "content": f"😕 No hotels found in {destination} for '{selected_category}'.\n\nPlease try another category:",
#                 "buttons": buttons
#             }
#         state["data"]["hotels_list"] = unique_hotels
#         state["step"] = "hotel_selection"
#         hotel_buttons = [
#             {"text": h.get("hotel_name", "Unknown Hotel"), "value": h.get("hotel_name", "Unknown Hotel")}
#             for h in unique_hotels[:20]
#         ]
#         hotel_buttons.append({"text": "🔙 Back to Categories", "value": "back to categories"})
#         hotel_buttons.append({"text": "📍 Change Destination", "value": "change destination"})
#         return {
#             "type": "buttons_grid",
#             "content": f"🏨 Found {len(unique_hotels)} hotel(s) in {destination} for '{selected_category}':\n\nSelect a hotel to see details:",
#             "buttons": hotel_buttons
#         }

#     def _handle_hotel_selection(self, phone: str, message: str, state: dict) -> dict:
#         selected = message.strip()
#         if selected.lower() in ["🔙 back to categories", "back to categories"]:
#             state["step"] = "hotel_category_selection"
#             return self._show_categories(state)
#         if selected.lower() in ["📍 change destination", "change destination"]:
#             state["step"] = "hotel_ask_destination"
#             state["data"] = {}
#             return {"type": "text", "content": "📍 Tell me your destination city."}
#         hotels_list = state["data"].get("hotels_list", [])
#         selected_hotel = next(
#             (h for h in hotels_list if h.get("hotel_name", "").lower() == selected.lower()),
#             None
#         )
#         if not selected_hotel:
#             hotel_buttons = [
#                 {"text": h.get("hotel_name", "Unknown Hotel"), "value": h.get("hotel_name", "Unknown Hotel")}
#                 for h in hotels_list[:20]
#             ]
#             hotel_buttons.append({"text": "🔙 Back to Categories", "value": "back to categories"})
#             hotel_buttons.append({"text": "📍 Change Destination", "value": "change destination"})
#             return {
#                 "type": "buttons_grid",
#                 "content": "❌ Hotel not found. Please select from the list:",
#                 "buttons": hotel_buttons
#             }
        
#         state["data"]["selected_hotel"] = selected_hotel
#         rooms = selected_hotel.get("rooms", [])
        
#         if not rooms:
#             return {
#                 "type": "buttons",
#                 "content": "❌ No rooms available for this hotel.\n\nWould you like to see other hotels?",
#                 "buttons": [
#                     {"text": "See Other Hotels", "value": "see other hotels"},
#                     {"text": "New Search", "value": "new search"}
#                 ]
#             }
        
#         # Store rooms and show room selection
#         state["data"]["rooms_list"] = rooms
#         state["step"] = "room_selection"
#         return self._show_rooms(state)

#     def _show_rooms(self, state: dict) -> dict:
#         """Display rooms with images, category, type, and Yes/No buttons"""
#         hotel = state["data"].get("selected_hotel", {})
#         rooms = state["data"].get("rooms_list", [])
        
#         if not rooms:
#             return {
#                 "type": "text",
#                 "content": "❌ No rooms available.",
#                 "buttons": [{"text": "Back to Hotels", "value": "back to hotels"}]
#             }
        
#         # Show each room with full details
#         room_buttons = []
#         content = f"🏨 *{hotel.get('hotel_name')}* - Available Rooms\n\n"
#         content += f"📅 {state['data']['start_date']} → {state['data']['end_date']}\n"
#         content += f"👥 {state['data']['people']} guests\n\n"
#         content += "─" * 40 + "\n\n"
        
#         for idx, room in enumerate(rooms):
#             room_category = room.get("room_category", "N/A")
#             room_type = room.get("room_type", "N/A")
#             min_cap = room.get("minimum_capacity", "1")
#             max_cap = room.get("maximum_capacity", "2")
#             base_price = room.get("base_price", "0")
#             room_images = room.get("room_images", [])
#             facilities = room.get("facilities", [])
            
#             # Room header with image
#             if room_images:
#                 content += f"🖼️ *Room {idx + 1}*\n"
#                 content += f"![Room Image]({room_images[0]})\n\n"
            
#             content += f"📋 *Category:* {room_category}\n"
#             content += f"🏷️ *Type:* {room_type}\n"
#             content += f"👥 *Capacity:* {min_cap} - {max_cap} people\n"
#             content += f"💰 *Base Price:* ₹{int(base_price):,}/night\n\n"
            
#             # Facilities
#             if facilities:
#                 content += f"✨ *Facilities:*\n"
#                 for facility in facilities[:5]:
#                     content += f"  • {facility}\n"
#                 if len(facilities) > 5:
#                     content += f"  • +{len(facilities) - 5} more\n"
#                 content += "\n"
            
#             # Seasons info
#             seasons = room.get("seasons", [])
#             if seasons:
#                 content += f"📅 *Seasonal Pricing Available*\n"
#                 for season in seasons[:2]:
#                     content += f"  • {season.get('season_name', 'N/A')}: ₹{int(season.get('price', 0)):,}/night\n"
#                 content += "\n"
            
#             content += "─" * 40 + "\n\n"
            
#             # Add Yes/No buttons for each room
#             room_buttons.append({"text": f"✅ Yes - Select Room {idx + 1} ({room_category})", "value": f"select_room_{idx}"})
        
#         room_buttons.append({"text": "🔙 Back to Hotels", "value": "back_to_hotels"})
#         room_buttons.append({"text": "🏠 New Search", "value": "new_search"})
        
#         content += "Please select a room by clicking 'Yes' next to your preferred room:"
        
#         return {
#             "type": "buttons_grid",
#             "content": content,
#             "buttons": room_buttons
#         }

#     def _handle_room_selection(self, message: str, state: dict) -> dict:
#         """Handle room selection and move to meal plan"""
#         if message == "back_to_hotels":
#             state["step"] = "hotel_selection"
#             hotels_list = state["data"].get("hotels_list", [])
#             hotel_buttons = [
#                 {"text": h.get("hotel_name", "Unknown Hotel"), "value": h.get("hotel_name", "Unknown Hotel")}
#                 for h in hotels_list[:20]
#             ]
#             hotel_buttons.append({"text": "🔙 Back to Categories", "value": "back to categories"})
#             return {
#                 "type": "buttons_grid",
#                 "content": "🏨 Select a hotel:",
#                 "buttons": hotel_buttons
#             }
        
#         if message == "new_search":
#             state["step"] = "start"
#             return {
#                 "type": "buttons",
#                 "content": "What would you like to do?",
#                 "buttons": [
#                     {"text": "Find Hotels", "value": "hotels"},
#                     {"text": "Find Packages", "value": "packages"}
#                 ]
#             }
        
#         if message.startswith("select_room_"):
#             room_idx = int(message.split("_")[2])
#             rooms = state["data"].get("rooms_list", [])
            
#             if 0 <= room_idx < len(rooms):
#                 selected_room = rooms[room_idx]
#                 state["data"]["selected_room"] = selected_room
                
#                 # Calculate price
#                 check_in = state["data"].get("start_date")
#                 check_out = state["data"].get("end_date")
#                 guests = int(state["data"].get("people", 1))
                
#                 price_details = calculate_total_price(
#                     selected_room,
#                     check_in,
#                     check_out,
#                     guests
#                 )
                
#                 state["data"]["price_details"] = price_details
#                 state["step"] = "meal_selection"
                
#                 return self._show_meal_selection(state)
        
#         return {
#             "type": "text",
#             "content": "❌ Invalid selection. Please select a room using the Yes button."
#         }

#     def _show_meal_selection(self, state: dict) -> dict:
#         """Show meal plan selection options"""
#         hotel = state["data"].get("selected_hotel", {})
#         room = state["data"].get("selected_room", {})
#         price = state["data"].get("price_details", {})
        
#         # Create meal selection prompt
#         prompt = MEAL_SELECTION_PROMPT.format(
#             hotel_name=hotel.get("hotel_name", "N/A"),
#             room_category=room.get("room_category", "N/A"),
#             room_type=room.get("room_type", "N/A"),
#             check_in=state["data"]["start_date"],
#             check_out=state["data"]["end_date"],
#             nights=price.get("nights", 0),
#             guests=state["data"].get("people", "N/A"),
#             room_total=f"{price.get('total', 0):,.2f}"
#         )
        
#         content = self._call_llm(prompt)
        
#         # Add manual options as fallback
#         content += "\n\n*Please select a meal plan:*\n"
#         content += "1. 🚫 No Meals\n"
#         content += "2. 🍳 Breakfast Only\n"
#         content += "3. 🍽️ Half Board (Breakfast + Dinner)\n"
#         content += "4. 🍱 Full Board (All Meals)\n"
        
#         return {
#             "type": "buttons",
#             "content": content,
#             "buttons": [
#                 {"text": "🚫 No Meals", "value": "meal_1"},
#                 {"text": "🍳 Breakfast Only", "value": "meal_2"},
#                 {"text": "🍽️ Half Board", "value": "meal_3"},
#                 {"text": "🍱 Full Board", "value": "meal_4"},
#                 {"text": "🔙 Back to Rooms", "value": "back_to_rooms"}
#             ]
#         }

#     def _handle_meal_selection(self, message: str, state: dict) -> dict:
#         """Handle meal plan selection and show final summary"""
#         if message == "back_to_rooms":
#             state["step"] = "room_selection"
#             return self._show_rooms(state)
        
#         meal_map = {
#             "meal_1": "1",
#             "meal_2": "2", 
#             "meal_3": "3",
#             "meal_4": "4"
#         }
        
#         meal_plan = meal_map.get(message)
#         if not meal_plan:
#             return {
#                 "type": "text",
#                 "content": "❌ Invalid selection. Please select a meal plan from the options."
#             }
        
#         # Calculate meal price
#         guests = int(state["data"].get("people", 1))
#         nights = state["data"]["price_details"]["nights"]
#         meal_details = calculate_meal_price(meal_plan, guests, nights)
        
#         state["data"]["meal_plan"] = meal_details
#         state["step"] = "final_summary"
        
#         return self._show_final_summary(state)

#     def _show_final_summary(self, state: dict) -> dict:
#         """Show complete final summary with all user selections"""
#         hotel = state["data"].get("selected_hotel", {})
#         room = state["data"].get("selected_room", {})
#         price = state["data"].get("price_details", {})
#         meal = state["data"].get("meal_plan", {})
        
#         # Calculate grand total
#         room_total = price.get("total", 0)
#         meal_total = meal.get("total", 0)
#         grand_total = room_total + meal_total
        
#         # Format facilities
#         facilities = room.get("facilities", [])
#         facilities_text = ", ".join(facilities[:5]) if facilities else "Standard amenities"
#         if len(facilities) > 5:
#             facilities_text += f" +{len(facilities) - 5} more"
        
#         # Create prompt for final summary
#         prompt = FINAL_COMPLETE_SUMMARY_PROMPT.format(
#             hotel_name=hotel.get("hotel_name", "N/A"),
#             hotel_location=hotel.get("location", "N/A"),
#             hotel_category=hotel.get("category", "N/A"),
#             hotel_phone=hotel.get("phones", ["N/A"])[0],
#             hotel_email=hotel.get("emails", ["N/A"])[0],
#             room_category=room.get("room_category", "N/A"),
#             room_type=room.get("room_type", "N/A"),
#             min_capacity=room.get("minimum_capacity", "1"),
#             max_capacity=room.get("maximum_capacity", "2"),
#             facilities=facilities_text,
#             check_in=state["data"]["start_date"],
#             check_out=state["data"]["end_date"],
#             nights=price.get("nights", 0),
#             guests=state["data"].get("people", "N/A"),
#             base_price=f"{price.get('base_price', 0):,.2f}",
#             room_base_total=f"{price.get('room_base_total', 0):,.2f}",
#             extra_price=f"{price.get('extra_person_price', 0):,.2f}",
#             extra_people=price.get("extra_people", 0),
#             extra_total=f"{price.get('extra_total', 0):,.2f}",
#             room_subtotal=f"{room_total:,.2f}",
#             meal_plan=meal.get("plan_name", "No Meals"),
#             meal_cost_per_person=f"{meal.get('price_per_person', 0):,.2f}",
#             meal_total=f"{meal_total:,.2f}",
#             grand_total=f"{grand_total:,.2f}"
#         )
        
#         content = self._call_llm(prompt)
        
#         return {
#             "type": "buttons",
#             "content": content,
#             "buttons": [
#                 {"text": "✅ Confirm & Book", "value": "confirm_booking"},
#                 {"text": "🍽️ Change Meal Plan", "value": "change_meal"},
#                 {"text": "🛏️ Change Room", "value": "change_room"},
#                 {"text": "🏨 Other Hotels", "value": "other_hotels"}
#             ]
#         }

#     def _handle_final_summary(self, message: str, state: dict) -> dict:
#         """Handle final booking confirmation"""
#         if message == "confirm_booking":
#             hotel = state["data"].get("selected_hotel", {})
#             room = state["data"].get("selected_room", {})
#             meal = state["data"].get("meal_plan", {})
#             price = state["data"].get("price_details", {})
            
#             meal_total = meal.get("total", 0)
#             room_total = price.get("total", 0)
            
#             return {
#                 "type": "text",
#                 "content": (
#                     f"🎉 *BOOKING CONFIRMED!* 🎉\n\n"
#                     f"Thank you for choosing {hotel.get('hotel_name', 'us')}!\n\n"
#                     f"📧 Confirmation sent to your email\n"
#                     f"📞 Hotel will contact you within 24 hours\n\n"
#                     f"*Booking Reference:* {datetime.now().strftime('HOTEL%Y%m%d%H%M%S')}\n\n"
#                     f"*Summary:*\n"
#                     f"🏨 {hotel.get('hotel_name')}\n"
#                     f"🛏️ {room.get('room_category')} ({room.get('room_type')})\n"
#                     f"🍽️ {meal.get('plan_name', 'No Meals')}\n"
#                     f"📅 {state['data']['start_date']} → {state['data']['end_date']}\n"
#                     f"👥 {state['data']['people']} guests\n"
#                     f"💰 Total Paid: ₹{room_total + meal_total:,.2f}\n\n"
#                     f"Have a wonderful stay! 🌟\n\n"
#                     f"Would you like to book another hotel?"
#                 ),
#                 "buttons": [
#                     {"text": "Book Another Hotel", "value": "new_search"},
#                     {"text": "View My Bookings", "value": "view_bookings"}
#                 ]
#             }
        
#         elif message == "change_meal":
#             state["step"] = "meal_selection"
#             return self._show_meal_selection(state)
        
#         elif message == "change_room":
#             state["step"] = "room_selection"
#             return self._show_rooms(state)
        
#         elif message == "other_hotels":
#             state["step"] = "hotel_category_selection"
#             return self._show_categories(state)
        
#         elif message == "new_search":
#             state["step"] = "start"
#             return {
#                 "type": "buttons",
#                 "content": "What would you like to do?",
#                 "buttons": [
#                     {"text": "Find Hotels", "value": "hotels"},
#                     {"text": "Find Packages", "value": "packages"}
#                 ]
#             }
        
#         else:
#             return {
#                 "type": "buttons",
#                 "content": "Please select an option:",
#                 "buttons": [
#                     {"text": "✅ Confirm Booking", "value": "confirm_booking"},
#                     {"text": "🍽️ Change Meal Plan", "value": "change_meal"},
#                     {"text": "🛏️ Change Room", "value": "change_room"}
#                 ]
#             }

#     # Package Flow Handlers
#     def _handle_package_dates(self, message: str, state: dict) -> dict:
#         dates = self._extract_dates(message)
#         start_date = dates.get("start_date", "")
#         end_date = dates.get("end_date", "")
#         if start_date and end_date:
#             start_dt = parse_date(start_date)
#             end_dt = parse_date(end_date)
#             if start_dt and end_dt and end_dt > start_dt:
#                 state["data"]["start_date"] = start_date
#                 state["data"]["end_date"] = end_date
#                 state["step"] = "package_ask_destination"
#                 nights = (end_dt - start_dt).days
#                 return {
#                     "type": "text",
#                     "content": f"👍 Start date: {start_date}\n👍 End date: {end_date}\n📅 Total {nights} nights\n\n📍 Now tell me your destination."
#                 }
#             else:
#                 return {"type": "text", "content": "❌ End date must be after start date.\n\nPlease tell me your dates again (e.g., '12 to 20 june')"}
#         elif start_date and not end_date:
#             state["data"]["start_date"] = start_date
#             state["step"] = "package_ask_end_date"
#             return {"type": "text", "content": f"👍 Start date: {start_date}\n\nNow tell me your end date."}
#         else:
#             return {"type": "text", "content": f"❌ I couldn't understand '{message}'.\n\nPlease tell me your dates like:\n• 12 to 20 june\n• 12th to 20th"}

#     def _handle_package_end_date(self, message: str, state: dict) -> dict:
#         dates = self._extract_dates(message)
#         end_date = dates.get("start_date", "")
#         if end_date:
#             start_dt = parse_date(state["data"].get("start_date"))
#             end_dt = parse_date(end_date)
#             if start_dt and end_dt and end_dt > start_dt:
#                 state["data"]["end_date"] = end_date
#                 state["step"] = "package_ask_destination"
#                 nights = (end_dt - start_dt).days
#                 return {
#                     "type": "text",
#                     "content": f"👍 Start date: {state['data']['start_date']}\n👍 End date: {end_date}\n📅 Total {nights} nights\n\n📍 Now tell me your destination."
#                 }
#             else:
#                 return {"type": "text", "content": f"❌ End date must be after {state['data']['start_date']}.\n\nPlease tell me a valid end date."}
#         else:
#             return {"type": "text", "content": f"❌ I couldn't understand '{message}' as a date.\n\nPlease tell me your end date (e.g., '20 june', '20th')"}

#     def _handle_package_destination(self, message: str, state: dict) -> dict:
#         validation_result = self._validate_city(message)
#         if validation_result.get("is_valid"):
#             corrected_city = validation_result["corrected_name"]
#             state["data"]["destination"] = corrected_city
#             state["step"] = "package_confirm_details"
#             city_note = (
#                 f"📍 You meant {corrected_city} ({validation_result.get('country', '')}), right?"
#                 if corrected_city.lower() != message.lower()
#                 else f"📍 Destination: {corrected_city}"
#             )
#             return {
#                 "type": "buttons",
#                 "content": f"{city_note}\n\n📅 Dates: {state['data']['start_date']} → {state['data']['end_date']}\n\nIs this correct?",
#                 "buttons": [
#                     {"text": "✅ Yes, Proceed", "value": "yes"},
#                     {"text": "❌ No, Change", "value": "no"}
#                 ]
#             }
#         else:
#             return {
#                 "type": "text",
#                 "content": f"❌ \"{message}\" doesn't appear to be a valid city.\n\n{validation_result.get('suggestion', 'Please enter a valid city name')}"
#             }

#     def _handle_package_confirmation(self, message: str, state: dict) -> dict:
#         if message.lower() in ["yes", "✅ yes, proceed", "proceed"]:
#             state["step"] = "package_ask_people"
#             return {"type": "text", "content": "👍 Great! Trip details confirmed.\n\n👥 How many people are traveling? (Just type the number)"}
#         else:
#             state["step"] = "package_ask_dates"
#             return {"type": "text", "content": "📅 OK, let's start over. Please tell me your travel dates."}

#     def _handle_package_people(self, message: str, state: dict) -> dict:
#         people_count = extract_number(message)
#         if people_count is None:
#             return {"type": "text", "content": "❌ Please enter a valid number (e.g., 2, 3, 4)."}
#         elif people_count <= 0:
#             return {"type": "text", "content": "❌ Please enter a valid number of people (1 or more)."}
#         elif people_count > 20:
#             return {"type": "text", "content": "❌ For groups larger than 20 people, please contact us directly for a group discount!"}
#         state["data"]["people"] = str(people_count)
#         state["step"] = "done"
#         return {
#             "type": "buttons",
#             "content": (
#                 f"Perfect 🎉\n\n"
#                 f"📍 {state['data'].get('destination')}\n"
#                 f"📅 {state['data'].get('start_date')} → {state['data'].get('end_date')}\n"
#                 f"👥 {state['data'].get('people')} people\n\n"
#                 f"You can now:\n👉 Find Hotels\n👉 Generate Itinerary"
#             ),
#             "buttons": [
#                 {"text": "Find Hotels", "value": "find hotels"},
#                 {"text": "Generate Itinerary", "value": "generate itinerary"}
#             ]
#         }

#     # LLM Helpers
#     def _call_llm(self, prompt: str) -> str:
#         try:
#             response = self._client.chat.completions.create(
#                 model="gpt-4o-mini",
#                 messages=[
#                     {"role": "system", "content": "You are a helpful travel assistant. Keep responses concise and friendly."},
#                     {"role": "user", "content": prompt}
#                 ],
#                 temperature=0.2
#             )
#             return response.choices[0].message.content
#         except Exception as e:
#             logger.error(f"LLM error: {e}")
#             return ""

#     def _extract_dates(self, user_input: str) -> dict:
#         prompt = DATE_PROMPT.format(
#             today=str(date.today()),
#             current_month=date.today().strftime("%B"),
#             current_year=date.today().year,
#             input=user_input
#         )
#         try:
#             llm_response = self._call_llm(prompt)
#             cleaned = clean_llm_response(llm_response)
#             parsed = json.loads(cleaned)
#             return {
#                 "start_date": parsed.get("start_date", ""),
#                 "end_date": parsed.get("end_date", "")
#             }
#         except Exception as e:
#             logger.error(f"Date parsing error: {e}")
#             return {"start_date": "", "end_date": ""}

#     def _validate_city(self, city_name: str) -> dict:
#         prompt = VALIDATE_CITY_PROMPT.format(city=city_name)
#         try:
#             llm_response = self._call_llm(prompt)
#             cleaned = clean_llm_response(llm_response)
#             result = json.loads(cleaned)
#             return {
#                 "is_valid": result.get("is_valid", False),
#                 "corrected_name": result.get("corrected_name", city_name),
#                 "suggestion": result.get("suggestion", ""),
#                 "country": result.get("country", ""),
#                 "message": result.get("message", "")
#             }
#         except Exception as e:
#             logger.error(f"City validation error: {e}")
#             return {
#                 "is_valid": True,
#                 "corrected_name": city_name,
#                 "suggestion": "",
#                 "country": "",
#                 "message": ""
#             }

#     def _extract_partial_trip(self, user_input: str) -> dict:
#         prompt = PARTIAL_TRIP_PROMPT.format(
#             today=str(date.today()),
#             input=user_input
#         )
#         try:
#             llm_response = self._call_llm(prompt)
#             cleaned = clean_llm_response(llm_response)
#             parsed = json.loads(cleaned)
#             return {
#                 "destination": parsed.get("destination", ""),
#                 "start_date": parsed.get("start_date", ""),
#                 "end_date": parsed.get("end_date", "")
#             }
#         except Exception as e:
#             logger.error(f"Partial trip extraction error: {e}")
#             return {"destination": "", "start_date": "", "end_date": ""}


"""
agent/agent_executor.py

Complete travel agent with card format room display
"""

import os
import sys
import json
import logging
from datetime import date, datetime
from dotenv import load_dotenv
from openai import OpenAI

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent.prompts import (
    DATE_PROMPT,
    VALIDATE_CITY_PROMPT,
    HOTEL_PROMPT,
    CONFIRM_PROMPT,
    PEOPLE_PROMPT,
    PARTIAL_TRIP_PROMPT
)
from helpers.helper import extract_number, parse_date, clean_llm_response

import requests

logger = logging.getLogger(__name__)

CATEGORIES_URL = "https://silver-spoonbill-286441.hostingersite.com/wp-json/hm/v1/hotel-categories"
HOTELS_URL = "https://silver-spoonbill-286441.hostingersite.com/wp-json/hm/v1/hotels?phone=919816440734"

load_dotenv()


def get_hotel_categories():
    try:
        response = requests.get(CATEGORIES_URL, timeout=10)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        logger.error(f"get_hotel_categories error: {e}")
        return {"data": []}


def get_all_hotels():
    try:
        response = requests.get(HOTELS_URL, timeout=10)
        response.raise_for_status()
        data = response.json()
        return data.get("hotels", [])
    except Exception as e:
        logger.error(f"get_all_hotels error: {e}")
        return []


def get_hotels_by_category(category: str, location: str) -> list:
    all_hotels = get_all_hotels()
    filtered = []
    
    for hotel in all_hotels:
        hotel_category = hotel.get("category", "").lower()
        hotel_location = hotel.get("location", "").lower()
        
        if hotel_category == category.lower() and location.lower() in hotel_location:
            filtered.append(hotel)
    
    return filtered


def calculate_total_price(hotel_room, check_in, check_out, guests):
    try:
        check_in_date = datetime.strptime(check_in, "%Y-%m-%d")
        check_out_date = datetime.strptime(check_out, "%Y-%m-%d")
        nights = (check_out_date - check_in_date).days
        
        seasons = hotel_room.get("seasons", [])
        applicable_season = None
        
        for season in seasons:
            start = datetime.strptime(season["starting_date"], "%d %B %Y")
            end = datetime.strptime(season["end_date"], "%d %B %Y")
            if start <= check_in_date <= end:
                applicable_season = season
                break
        
        if applicable_season:
            price_per_night = float(applicable_season["price"])
            extra_person_price = float(applicable_season["extra_price"])
        else:
            price_per_night = float(hotel_room.get("base_price", 0))
            extra_person_price = float(hotel_room.get("extra_person_price", 0))
        
        max_capacity = int(hotel_room.get("maximum_capacity", 2))
        extra_people = max(0, guests - max_capacity)
        
        base_total = price_per_night * nights
        extra_total = extra_person_price * extra_people * nights
        total = base_total + extra_total
        
        return {
            "base_price": price_per_night,
            "extra_person_price": extra_person_price,
            "total": total,
            "nights": nights,
            "extra_people": extra_people,
            "room_base_total": base_total,
            "extra_total": extra_total
        }
    except Exception as e:
        logger.error(f"calculate_total_price error: {e}")
        return {
            "base_price": 0,
            "extra_person_price": 0,
            "total": 0,
            "nights": 0,
            "extra_people": 0,
            "room_base_total": 0,
            "extra_total": 0
        }


class AgentExecutor:

    def __init__(self):
        self._client = OpenAI(api_key=os.getenv("OPEN_API_KEY"))
        self._sessions = {}
        logger.info("AgentExecutor initialised")

    def execute(self, phone: str, user_message: str) -> dict:
        if phone not in self._sessions:
            self._sessions[phone] = self._fresh_state()

        state = self._sessions[phone]
        logger.info(f"[{phone}] step={state['step']} msg={user_message}")

        return self._route(phone, user_message, state)

    def get_state(self, phone: str) -> dict:
        if phone not in self._sessions:
            self._sessions[phone] = self._fresh_state()
        return self._sessions[phone]

    def _fresh_state(self) -> dict:
        return {
            "step": "start",
            "flow": None,
            "data": {}
        }

    def _reset(self, phone: str):
        self._sessions[phone] = self._fresh_state()

    def _route(self, phone: str, message: str, state: dict) -> dict:
        step = state["step"]
        text = message.lower().strip()

        if step == "start":
            if text in ["hi", "hii", "hello", "hey"]:
                return {
                    "type": "buttons",
                    "content": "Hi 👋 I'm your travel assistant.\nWhat can I help you with?",
                    "buttons": [
                        {"text": "Find Hotels", "value": "hotels"},
                        {"text": "Find Packages", "value": "packages"}
                    ]
                }
            elif text in ["hotels", "find hotels"]:
                state["step"] = "hotel_ask_destination"
                state["flow"] = "hotel"
                state["data"] = {}
                return {
                    "type": "text",
                    "content": "🏨 Let me help you find the best hotels!\n\n📍 First, tell me your destination city."
                }
            elif text in ["packages", "find packages"]:
                state["step"] = "package_ask_dates"
                state["flow"] = "package"
                state["data"] = {}
                return {
                    "type": "text",
                    "content": "📅 Tell me your travel dates (e.g., '12 to 20 june' or '12th to 20th')"
                }
            else:
                partial = self._extract_partial_trip(message)
                destination = partial.get("destination", "")
                start_date = partial.get("start_date", "")
                end_date = partial.get("end_date", "")

                if "hotel" in text:
                    flow = "hotel"
                elif any(k in text for k in ["package", "trip", "tour", "itinerary"]):
                    flow = "package"
                elif destination or start_date:
                    flow = None
                else:
                    return {
                        "type": "buttons",
                        "content": "What would you like to do?",
                        "buttons": [
                            {"text": "Find Hotels", "value": "hotels"},
                            {"text": "Find Packages", "value": "packages"}
                        ]
                    }

                if flow is None:
                    state["data"] = {}
                    if destination:
                        state["data"]["destination"] = destination
                    if start_date:
                        state["data"]["start_date"] = start_date
                    if end_date:
                        state["data"]["end_date"] = end_date
                    state["step"] = "ask_flow"
                    return {
                        "type": "buttons",
                        "content": f"Got it! Are you looking for hotels or a travel package?",
                        "buttons": [
                            {"text": "Find Hotels", "value": "hotels"},
                            {"text": "Find Packages", "value": "packages"}
                        ]
                    }

                state["flow"] = flow
                state["data"] = {}

                if flow == "hotel":
                    if destination:
                        state["data"]["destination"] = destination
                    if start_date:
                        state["data"]["start_date"] = start_date
                    if end_date:
                        state["data"]["end_date"] = end_date
                    return self._jump_hotel_flow(state)
                else:
                    if destination:
                        state["data"]["destination"] = destination
                    if start_date:
                        state["data"]["start_date"] = start_date
                    if end_date:
                        state["data"]["end_date"] = end_date
                    return self._jump_package_flow(state)

        if step == "ask_flow":
            if text in ["hotels", "find hotels"]:
                state["flow"] = "hotel"
                return self._jump_hotel_flow(state)
            elif text in ["packages", "find packages"]:
                state["flow"] = "package"
                return self._jump_package_flow(state)
            else:
                return {
                    "type": "buttons",
                    "content": "Please choose one:",
                    "buttons": [
                        {"text": "Find Hotels", "value": "hotels"},
                        {"text": "Find Packages", "value": "packages"}
                    ]
                }

        # Hotel Flow
        if step == "hotel_ask_destination":
            return self._handle_destination(message, state)
        if step == "hotel_ask_dates":
            return self._handle_dates(message, state)
        if step == "hotel_ask_end_date_only":
            return self._handle_end_date(message, state)
        if step == "hotel_confirm_details":
            return self._handle_confirmation(message, state)
        if step == "hotel_ask_people":
            return self._handle_people(message, state)
        if step == "hotel_category_selection":
            return self._handle_category(message, state)
        if step == "hotel_selection":
            return self._handle_hotel_selection(phone, message, state)
        
        # Room Selection - Card Format
        if step == "room_selection":
            return self._handle_room_selection(message, state)
        
        # Meal Plan Question
        if step == "ask_meal_plan":
            return self._handle_meal_question(message, state)
        
        # Meal Plan Selection
        if step == "meal_selection":
            return self._handle_meal_selection(message, state)
        
        # Final Summary
        if step == "final_summary":
            return self._handle_final_summary(message, state)

        # Package Flow
        if step == "package_ask_dates":
            return self._handle_package_dates(message, state)
        if step == "package_ask_end_date":
            return self._handle_package_end_date(message, state)
        if step == "package_ask_destination":
            return self._handle_package_destination(message, state)
        if step == "package_confirm_details":
            return self._handle_package_confirmation(message, state)
        if step == "package_ask_people":
            return self._handle_package_people(message, state)

        if text in ["see other hotels", "new search"]:
            state["step"] = "start"
            return {
                "type": "buttons",
                "content": "What would you like to do?",
                "buttons": [
                    {"text": "Find Hotels", "value": "hotels"},
                    {"text": "Find Packages", "value": "packages"}
                ]
            }

        return {
            "type": "text",
            "content": "🤔 I didn't understand that. Try 'hi', 'find packages', or 'find hotels'."
        }

    def _jump_hotel_flow(self, state: dict) -> dict:
        data = state["data"]
        if not data.get("destination"):
            state["step"] = "hotel_ask_destination"
            return {
                "type": "text",
                "content": "🏨 Let me help you find hotels!\n\n📍 Which city would you like to stay in?"
            }
        if not data.get("start_date") or not data.get("end_date"):
            state["step"] = "hotel_ask_dates"
            return {
                "type": "text",
                "content": f"📍 Destination: *{data['destination']}*\n\n📅 Now tell me your check-in and check-out dates.\n\n*Example: 12 to 20 june*"
            }
        start_dt = parse_date(data["start_date"])
        end_dt = parse_date(data["end_date"])
        nights = (end_dt - start_dt).days if (start_dt and end_dt) else "?"
        state["step"] = "hotel_confirm_details"
        return {
            "type": "buttons",
            "content": (
                f"📅 Please confirm your details:\n\n"
                f"📍 Destination: {data['destination']}\n"
                f"📅 Check-in: {data['start_date']}\n"
                f"📅 Check-out: {data['end_date']}\n"
                f"📆 Total: {nights} nights\n\n"
                f"Is this correct?"
            ),
            "buttons": [
                {"text": "✅ Yes, Proceed", "value": "yes"},
                {"text": "❌ No, Change Dates", "value": "no"}
            ]
        }

    def _jump_package_flow(self, state: dict) -> dict:
        data = state["data"]
        if not data.get("start_date") or not data.get("end_date"):
            state["step"] = "package_ask_dates"
            return {
                "type": "text",
                "content": "📅 Tell me your travel dates (e.g., '12 to 20 june')"
            }
        if not data.get("destination"):
            state["step"] = "package_ask_destination"
            return {
                "type": "text",
                "content": f"📅 Dates: {data['start_date']} → {data['end_date']}\n\n📍 Now tell me your destination."
            }
        state["step"] = "package_confirm_details"
        return {
            "type": "buttons",
            "content": (
                f"📍 Destination: {data['destination']}\n"
                f"📅 Dates: {data['start_date']} → {data['end_date']}\n\n"
                f"Is this correct?"
            ),
            "buttons": [
                {"text": "✅ Yes, Proceed", "value": "yes"},
                {"text": "❌ No, Change", "value": "no"}
            ]
        }

    def _handle_destination(self, message: str, state: dict) -> dict:
        validation_result = self._validate_city(message)
        if validation_result.get("is_valid"):
            corrected_city = validation_result["corrected_name"]
            state["data"]["destination"] = corrected_city
            state["step"] = "hotel_ask_dates"
            prefix = (
                f"📍 Got it! You meant **{corrected_city}** ({validation_result.get('country', '')})\n\n"
                if corrected_city.lower() != message.lower()
                else f"📍 Great! Destination: {corrected_city}\n\n"
            )
            return {
                "type": "text",
                "content": prefix + "Now tell me your check-in and check-out dates.\n\n*Example: 12 to 20 june or 12th to 20th*"
            }
        else:
            return {
                "type": "text",
                "content": f"❌ \"{message}\" doesn't appear to be a valid city.\n\n{validation_result.get('suggestion', 'Please enter a valid city name')}"
            }

    def _handle_dates(self, message: str, state: dict) -> dict:
        dates = self._extract_dates(message)
        start_date = dates.get("start_date", "")
        end_date = dates.get("end_date", "")
        if start_date and end_date:
            start_dt = parse_date(start_date)
            end_dt = parse_date(end_date)
            if start_dt and end_dt and end_dt > start_dt:
                state["data"]["start_date"] = start_date
                state["data"]["end_date"] = end_date
                state["step"] = "hotel_confirm_details"
                return {
                    "type": "buttons",
                    "content": (
                        f"📅 Please confirm your dates:\n\n"
                        f"📍 Destination: {state['data']['destination']}\n"
                        f"📅 Check-in: {start_date}\n"
                        f"📅 Check-out: {end_date}\n"
                        f"📆 Total: {(end_dt - start_dt).days} nights\n\n"
                        f"Is this correct?"
                    ),
                    "buttons": [
                        {"text": "✅ Yes, Proceed", "value": "yes"},
                        {"text": "❌ No, Change Dates", "value": "no"}
                    ]
                }
            else:
                return {
                    "type": "text",
                    "content": "❌ Check-out date must be after check-in date.\n\nPlease tell me your dates again (e.g., '12 to 20 june')"
                }
        elif start_date and not end_date:
            state["data"]["start_date"] = start_date
            state["step"] = "hotel_ask_end_date_only"
            return {
                "type": "text",
                "content": f"👍 Check-in: {start_date}\n\nNow tell me your check-out date."
            }
        else:
            return {
                "type": "text",
                "content": (
                    f"❌ I couldn't understand '{message}'.\n\n"
                    "Please tell me your dates like:\n"
                    "• 12 to 20 june\n• 12th to 20th\n• 12 june\n• tomorrow"
                )
            }

    def _handle_end_date(self, message: str, state: dict) -> dict:
        dates = self._extract_dates(message)
        end_date = dates.get("start_date", "")
        if end_date:
            start_dt = parse_date(state["data"].get("start_date"))
            end_dt = parse_date(end_date)
            if start_dt and end_dt and end_dt > start_dt:
                state["data"]["end_date"] = end_date
                state["step"] = "hotel_confirm_details"
                return {
                    "type": "buttons",
                    "content": (
                        f"📅 Please confirm your dates:\n\n"
                        f"📍 Destination: {state['data']['destination']}\n"
                        f"📅 Check-in: {state['data']['start_date']}\n"
                        f"📅 Check-out: {end_date}\n"
                        f"📆 Total: {(end_dt - start_dt).days} nights\n\n"
                        f"Is this correct?"
                    ),
                    "buttons": [
                        {"text": "✅ Yes, Proceed", "value": "yes"},
                        {"text": "❌ No, Change Dates", "value": "no"}
                    ]
                }
            else:
                return {
                    "type": "text",
                    "content": f"❌ Check-out date must be after {state['data']['start_date']}.\n\nPlease tell me a valid check-out date."
                }
        else:
            return {
                "type": "text",
                "content": f"❌ I couldn't understand '{message}' as a date.\n\nPlease tell me your check-out date (e.g., '20 june', '20th', 'next friday')"
            }

    def _handle_confirmation(self, message: str, state: dict) -> dict:
        if message.lower() in ["yes", "✅ yes, proceed", "proceed"]:
            state["step"] = "hotel_ask_people"
            return {
                "type": "text",
                "content": "👍 Great! Dates confirmed.\n\n👥 How many people are traveling? (Just type the number)"
            }
        else:
            state["step"] = "hotel_ask_dates"
            return {
                "type": "text",
                "content": "📅 OK, let's try again. Please tell me your check-in and check-out dates.\n\n*Example: 12 to 20 june*"
            }

    def _handle_people(self, message: str, state: dict) -> dict:
        people_count = extract_number(message)
        if people_count is None:
            return {"type": "text", "content": "❌ Please enter a valid number (e.g., 2, 3, 4)."}
        elif people_count <= 0:
            return {"type": "text", "content": "❌ Please enter a valid number of people (1 or more)."}
        elif people_count > 20:
            return {"type": "text", "content": "❌ For groups larger than 20 people, please contact us directly for a group discount!"}
        state["data"]["people"] = str(people_count)
        state["step"] = "hotel_category_selection"
        return self._show_categories(state)

    def _show_categories(self, state: dict) -> dict:
        categories_data = get_hotel_categories()
        if categories_data and "data" in categories_data:
            categories = [c["category_name"] for c in categories_data["data"]]
        else:
            categories = ["Budget", "Standard", "Luxury"]
        buttons = [{"text": cat, "value": cat} for cat in categories]
        buttons.append({"text": "🏨 Show All Hotels", "value": "show all hotels"})
        buttons.append({"text": "📍 Change Destination", "value": "change destination"})
        summary = (
            f"✅ Trip Details Confirmed:\n\n"
            f"📍 {state['data']['destination']}\n"
            f"📅 {state['data']['start_date']} → {state['data']['end_date']}\n"
            f"👥 {state['data']['people']} people\n\n"
            f"🏨 Please select a hotel category:"
        )
        return {
            "type": "buttons_grid",
            "content": summary,
            "buttons": buttons
        }

    def _handle_category(self, message: str, state: dict) -> dict:
        selected_category = message.strip()
        destination = state["data"]["destination"]
        if selected_category.lower() == "change destination":
            state["step"] = "hotel_ask_destination"
            state["data"] = {}
            return {"type": "text", "content": "📍 Let's start over. Tell me your destination city."}
        if selected_category.lower() == "show all hotels":
            all_hotels = get_all_hotels()
            unique_hotels = [h for h in all_hotels if destination.lower() in h.get("location", "").lower()]
        else:
            unique_hotels = get_hotels_by_category(selected_category, destination)
        if not unique_hotels:
            categories_data = get_hotel_categories()
            categories = [c["category_name"] for c in categories_data.get("data", [])] or ["Budget", "Standard", "Luxury"]
            buttons = [{"text": cat, "value": cat} for cat in categories]
            buttons.append({"text": "🏨 Show All Hotels", "value": "show all hotels"})
            buttons.append({"text": "📍 Change Destination", "value": "change destination"})
            return {
                "type": "buttons_grid",
                "content": f"😕 No hotels found in {destination} for '{selected_category}'.\n\nPlease try another category:",
                "buttons": buttons
            }
        state["data"]["hotels_list"] = unique_hotels
        state["step"] = "hotel_selection"
        hotel_buttons = [
            {"text": h.get("hotel_name", "Unknown Hotel"), "value": h.get("hotel_name", "Unknown Hotel")}
            for h in unique_hotels[:20]
        ]
        hotel_buttons.append({"text": "🔙 Back to Categories", "value": "back to categories"})
        hotel_buttons.append({"text": "📍 Change Destination", "value": "change destination"})
        return {
            "type": "buttons_grid",
            "content": f"🏨 Found {len(unique_hotels)} hotel(s) in {destination} for '{selected_category}':\n\nSelect a hotel to see details:",
            "buttons": hotel_buttons
        }

    def _handle_hotel_selection(self, phone: str, message: str, state: dict) -> dict:
        selected = message.strip()
        if selected.lower() in ["🔙 back to categories", "back to categories"]:
            state["step"] = "hotel_category_selection"
            return self._show_categories(state)
        if selected.lower() in ["📍 change destination", "change destination"]:
            state["step"] = "hotel_ask_destination"
            state["data"] = {}
            return {"type": "text", "content": "📍 Tell me your destination city."}
        hotels_list = state["data"].get("hotels_list", [])
        selected_hotel = next(
            (h for h in hotels_list if h.get("hotel_name", "").lower() == selected.lower()),
            None
        )
        if not selected_hotel:
            hotel_buttons = [
                {"text": h.get("hotel_name", "Unknown Hotel"), "value": h.get("hotel_name", "Unknown Hotel")}
                for h in hotels_list[:20]
            ]
            hotel_buttons.append({"text": "🔙 Back to Categories", "value": "back to categories"})
            hotel_buttons.append({"text": "📍 Change Destination", "value": "change destination"})
            return {
                "type": "buttons_grid",
                "content": "❌ Hotel not found. Please select from the list:",
                "buttons": hotel_buttons
            }
        
        state["data"]["selected_hotel"] = selected_hotel
        rooms = selected_hotel.get("rooms", [])
        
        if not rooms:
            return {
                "type": "buttons",
                "content": "❌ No rooms available for this hotel.\n\nWould you like to see other hotels?",
                "buttons": [
                    {"text": "See Other Hotels", "value": "see other hotels"},
                    {"text": "New Search", "value": "new search"}
                ]
            }
        
        state["data"]["rooms_list"] = rooms
        state["step"] = "room_selection"
        return self._show_rooms_card_format(state)

    def _show_rooms_card_format(self, state: dict) -> dict:
        """Display rooms in CARD FORMAT with image, type, category, and Yes/No button"""
        hotel = state["data"].get("selected_hotel", {})
        rooms = state["data"].get("rooms_list", [])
        
        # Store room info for tracking
        rooms_info = []
        for idx, room in enumerate(rooms):
            room_images = room.get("room_images", [])
            rooms_info.append({
                "index": idx,
                "category": room.get("room_category", "N/A"),
                "type": room.get("room_type", "N/A"),
                "image": room_images[0] if room_images else None,
                "room_data": room
            })
        
        state["data"]["rooms_info"] = rooms_info
        
        # Create card format response
        content = f"🏨 *{hotel.get('hotel_name')}* - Available Rooms\n\n"
        content += f"📅 {state['data']['start_date']} → {state['data']['end_date']}\n"
        content += f"👥 {state['data']['people']} guests\n\n"
        content += "Please select a room:\n\n"
        
        # Create buttons for each room with image preview in text
        room_buttons = []
        
        for idx, room in enumerate(rooms):
            room_images = room.get("room_images", [])
            room_category = room.get("room_category", "N/A")
            room_type = room.get("room_type", "N/A")
            base_price = room.get("base_price", "0")
            
            # Card format with image URL (will be rendered as image by UI)
            if room_images:
                content += f"🖼️ *Room {idx + 1}*\n"
                content += f"![Room]({room_images[0]})\n\n"
            
            content += f"📋 *Category:* {room_category}\n"
            content += f"🏷️ *Type:* {room_type}\n"
            content += f"💰 *Price:* ₹{int(base_price):,}/night\n"
            content += f"👥 *Capacity:* {room.get('minimum_capacity', '1')} - {room.get('maximum_capacity', '2')} people\n\n"
            
            # Add Yes button for this room
            room_buttons.append({
                "text": f"✅ Yes - Select Room {idx + 1}: {room_category} ({room_type})",
                "value": f"select_room_{idx}"
            })
            
            content += "─" * 30 + "\n\n"
        
        room_buttons.append({"text": "🔙 Back to Hotels", "value": "back_to_hotels"})
        
        return {
            "type": "buttons_grid",
            "content": content,
            "buttons": room_buttons
        }

    def _handle_room_selection(self, message: str, state: dict) -> dict:
        """Handle room selection and ask about meal plan"""
        if message == "back_to_hotels":
            state["step"] = "hotel_selection"
            hotels_list = state["data"].get("hotels_list", [])
            hotel_buttons = [
                {"text": h.get("hotel_name", "Unknown Hotel"), "value": h.get("hotel_name", "Unknown Hotel")}
                for h in hotels_list[:20]
            ]
            hotel_buttons.append({"text": "🔙 Back to Categories", "value": "back to categories"})
            return {
                "type": "buttons_grid",
                "content": "🏨 Select a hotel:",
                "buttons": hotel_buttons
            }
        
        if message.startswith("select_room_"):
            room_idx = int(message.split("_")[2])
            rooms_info = state["data"].get("rooms_info", [])
            
            if 0 <= room_idx < len(rooms_info):
                selected_room_info = rooms_info[room_idx]
                selected_room = selected_room_info["room_data"]
                state["data"]["selected_room"] = selected_room
                state["data"]["selected_room_index"] = room_idx
                
                # Calculate price
                check_in = state["data"].get("start_date")
                check_out = state["data"].get("end_date")
                guests = int(state["data"].get("people", 1))
                
                price_details = calculate_total_price(
                    selected_room,
                    check_in,
                    check_out,
                    guests
                )
                
                state["data"]["price_details"] = price_details
                state["step"] = "ask_meal_plan"
                
                # Ask about meal plan
                return {
                    "type": "buttons",
                    "content": (
                        f"✅ *Room Selected Successfully!*\n\n"
                        f"🏨 Hotel: {state['data']['selected_hotel'].get('hotel_name')}\n"
                        f"🛏️ Room: {selected_room.get('room_category')} ({selected_room.get('room_type')})\n"
                        f"💰 Room Total: ₹{price_details.get('total', 0):,.2f}\n\n"
                        f"🍽️ *Do you want to include a meal plan?*"
                    ),
                    "buttons": [
                        {"text": "✅ Yes, Include Meal Plan", "value": "yes_meal"},
                        {"text": "❌ No, Room Only", "value": "no_meal"},
                        {"text": "🔄 Change Room", "value": "change_room"}
                    ]
                }
        
        return {
            "type": "text",
            "content": "❌ Invalid selection. Please select a room using the Yes button."
        }

    def _handle_meal_question(self, message: str, state: dict) -> dict:
        """Handle yes/no for meal plan"""
        if message == "yes_meal":
            state["step"] = "meal_selection"
            return self._show_meal_options(state)
        elif message == "no_meal":
            # No meal plan selected
            state["data"]["meal_plan"] = {
                "plan_name": "No Meals",
                "price_per_person": 0,
                "total": 0
            }
            state["step"] = "final_summary"
            return self._show_final_summary(state)
        elif message == "change_room":
            state["step"] = "room_selection"
            return self._show_rooms_card_format(state)
        else:
            return {
                "type": "buttons",
                "content": "Please select an option:",
                "buttons": [
                    {"text": "✅ Yes, Include Meal Plan", "value": "yes_meal"},
                    {"text": "❌ No, Room Only", "value": "no_meal"},
                    {"text": "🔄 Change Room", "value": "change_room"}
                ]
            }

    def _show_meal_options(self, state: dict) -> dict:
        """Show meal plan options"""
        hotel = state["data"].get("selected_hotel", {})
        room = state["data"].get("selected_room", {})
        guests = int(state["data"].get("people", 1))
        nights = state["data"]["price_details"]["nights"]
        
        content = f"🍽️ *Meal Plan Options*\n\n"
        content += f"🏨 {hotel.get('hotel_name')}\n"
        content += f"🛏️ {room.get('room_category')} ({room.get('room_type')})\n"
        content += f"👥 {guests} guests × {nights} nights\n\n"
        content += "Select a meal plan:\n\n"
        content += "1️⃣ *No Meals* - ₹0\n"
        content += "   Just room only\n\n"
        content += "2️⃣ *Breakfast Only* - ₹500/person/day\n"
        content += f"   Total: ₹{500 * guests * nights:,}\n\n"
        content += "3️⃣ *Half Board* (Breakfast + Dinner) - ₹1,200/person/day\n"
        content += f"   Total: ₹{1200 * guests * nights:,}\n\n"
        content += "4️⃣ *Full Board* (All Meals) - ₹1,800/person/day\n"
        content += f"   Total: ₹{1800 * guests * nights:,}\n\n"
        
        return {
            "type": "buttons",
            "content": content,
            "buttons": [
                {"text": "🚫 No Meals", "value": "meal_0"},
                {"text": "🍳 Breakfast Only", "value": "meal_500"},
                {"text": "🍽️ Half Board", "value": "meal_1200"},
                {"text": "🍱 Full Board", "value": "meal_1800"},
                {"text": "🔙 Back", "value": "back_to_meal_question"}
            ]
        }

    def _handle_meal_selection(self, message: str, state: dict) -> dict:
        """Handle meal plan selection"""
        if message == "back_to_meal_question":
            state["step"] = "ask_meal_plan"
            return {
                "type": "buttons",
                "content": "🍽️ *Do you want to include a meal plan?*",
                "buttons": [
                    {"text": "✅ Yes, Include Meal Plan", "value": "yes_meal"},
                    {"text": "❌ No, Room Only", "value": "no_meal"},
                    {"text": "🔄 Change Room", "value": "change_room"}
                ]
            }
        
        meal_prices = {
            "meal_0": {"name": "No Meals", "price": 0},
            "meal_500": {"name": "Breakfast Only", "price": 500},
            "meal_1200": {"name": "Half Board (Breakfast + Dinner)", "price": 1200},
            "meal_1800": {"name": "Full Board (All Meals)", "price": 1800}
        }
        
        if message in meal_prices:
            guests = int(state["data"].get("people", 1))
            nights = state["data"]["price_details"]["nights"]
            price_per_person = meal_prices[message]["price"]
            
            state["data"]["meal_plan"] = {
                "plan_name": meal_prices[message]["name"],
                "price_per_person": price_per_person,
                "total": price_per_person * guests * nights
            }
            
            state["step"] = "final_summary"
            return self._show_final_summary(state)
        
        return {
            "type": "text",
            "content": "❌ Invalid selection. Please select a meal plan."
        }

    def _show_final_summary(self, state: dict) -> dict:
        """Show complete final summary"""
        hotel = state["data"].get("selected_hotel", {})
        room = state["data"].get("selected_room", {})
        price = state["data"].get("price_details", {})
        meal = state["data"].get("meal_plan", {"plan_name": "No Meals", "total": 0})
        
        room_total = price.get("total", 0)
        meal_total = meal.get("total", 0)
        grand_total = room_total + meal_total
        
        # Get room image
        room_images = room.get("room_images", [])
        room_image = room_images[0] if room_images else None
        
        content = f"📋 *FULL BOOKING SUMMARY*\n\n"
        
        if room_image:
            content += f"🖼️ ![Room]({room_image})\n\n"
        
        content += f"🏨 *HOTEL:* {hotel.get('hotel_name')}\n"
        content += f"📍 *Location:* {hotel.get('location')}\n"
        content += f"⭐ *Category:* {hotel.get('category')}\n\n"
        
        content += f"🛏️ *ROOM:*\n"
        content += f"   • Category: {room.get('room_category')}\n"
        content += f"   • Type: {room.get('room_type')}\n"
        content += f"   • Capacity: {room.get('minimum_capacity')} - {room.get('maximum_capacity')} people\n\n"
        
        content += f"📅 *STAY DETAILS:*\n"
        content += f"   • Check-in: {state['data']['start_date']}\n"
        content += f"   • Check-out: {state['data']['end_date']}\n"
        content += f"   • Nights: {price.get('nights', 0)}\n"
        content += f"   • Guests: {state['data']['people']}\n\n"
        
        content += f"💰 *PRICE BREAKDOWN:*\n"
        content += f"   • Room Total: ₹{room_total:,.2f}\n"
        if meal_total > 0:
            content += f"   • Meal Plan ({meal.get('plan_name')}): ₹{meal_total:,.2f}\n"
        content += f"   • *GRAND TOTAL: ₹{grand_total:,.2f}*\n\n"
        
        if meal_total == 0:
            content += f"🍽️ *Meal Plan:* No meals selected\n\n"
        
        content += f"📞 *Contact:* {hotel.get('phones', ['N/A'])[0]}\n"
        content += f"📧 *Email:* {hotel.get('emails', ['N/A'])[0]}\n\n"
        
        content += "Would you like to confirm this booking?"
        
        return {
            "type": "buttons",
            "content": content,
            "buttons": [
                {"text": "✅ Confirm Booking", "value": "confirm_booking"},
                {"text": "🍽️ Change Meal Plan", "value": "change_meal"},
                {"text": "🛏️ Change Room", "value": "change_room"},
                {"text": "🏨 Other Hotels", "value": "other_hotels"}
            ]
        }

    def _handle_final_summary(self, message: str, state: dict) -> dict:
        """Handle final booking confirmation"""
        if message == "confirm_booking":
            hotel = state["data"].get("selected_hotel", {})
            room = state["data"].get("selected_room", {})
            meal = state["data"].get("meal_plan", {})
            price = state["data"].get("price_details", {})
            
            room_total = price.get("total", 0)
            meal_total = meal.get("total", 0)
            
            return {
                "type": "text",
                "content": (
                    f"🎉 *BOOKING CONFIRMED!* 🎉\n\n"
                    f"Thank you for choosing {hotel.get('hotel_name', 'us')}!\n\n"
                    f"📧 Confirmation sent to your email\n"
                    f"📞 Hotel will contact you within 24 hours\n\n"
                    f"*Booking Reference:* {datetime.now().strftime('HOTEL%Y%m%d%H%M%S')}\n\n"
                    f"*Summary:*\n"
                    f"🏨 {hotel.get('hotel_name')}\n"
                    f"🛏️ {room.get('room_category')} ({room.get('room_type')})\n"
                    f"🍽️ {meal.get('plan_name', 'No Meals')}\n"
                    f"📅 {state['data']['start_date']} → {state['data']['end_date']}\n"
                    f"👥 {state['data']['people']} guests\n"
                    f"💰 Total Paid: ₹{room_total + meal_total:,.2f}\n\n"
                    f"Have a wonderful stay! 🌟\n\n"
                    f"Would you like to book another hotel?"
                ),
                "buttons": [
                    {"text": "Book Another Hotel", "value": "new_search"},
                    {"text": "View My Bookings", "value": "view_bookings"}
                ]
            }
        
        elif message == "change_meal":
            state["step"] = "meal_selection"
            return self._show_meal_options(state)
        
        elif message == "change_room":
            state["step"] = "room_selection"
            return self._show_rooms_card_format(state)
        
        elif message == "other_hotels":
            state["step"] = "hotel_category_selection"
            return self._show_categories(state)
        
        elif message == "new_search":
            state["step"] = "start"
            return {
                "type": "buttons",
                "content": "What would you like to do?",
                "buttons": [
                    {"text": "Find Hotels", "value": "hotels"},
                    {"text": "Find Packages", "value": "packages"}
                ]
            }
        
        else:
            return {
                "type": "buttons",
                "content": "Please select an option:",
                "buttons": [
                    {"text": "✅ Confirm Booking", "value": "confirm_booking"},
                    {"text": "🍽️ Change Meal Plan", "value": "change_meal"},
                    {"text": "🛏️ Change Room", "value": "change_room"}
                ]
            }

    # Package Flow Handlers
    def _handle_package_dates(self, message: str, state: dict) -> dict:
        dates = self._extract_dates(message)
        start_date = dates.get("start_date", "")
        end_date = dates.get("end_date", "")
        if start_date and end_date:
            start_dt = parse_date(start_date)
            end_dt = parse_date(end_date)
            if start_dt and end_dt and end_dt > start_dt:
                state["data"]["start_date"] = start_date
                state["data"]["end_date"] = end_date
                state["step"] = "package_ask_destination"
                nights = (end_dt - start_dt).days
                return {
                    "type": "text",
                    "content": f"👍 Start date: {start_date}\n👍 End date: {end_date}\n📅 Total {nights} nights\n\n📍 Now tell me your destination."
                }
            else:
                return {"type": "text", "content": "❌ End date must be after start date.\n\nPlease tell me your dates again (e.g., '12 to 20 june')"}
        elif start_date and not end_date:
            state["data"]["start_date"] = start_date
            state["step"] = "package_ask_end_date"
            return {"type": "text", "content": f"👍 Start date: {start_date}\n\nNow tell me your end date."}
        else:
            return {"type": "text", "content": f"❌ I couldn't understand '{message}'.\n\nPlease tell me your dates like:\n• 12 to 20 june\n• 12th to 20th"}

    def _handle_package_end_date(self, message: str, state: dict) -> dict:
        dates = self._extract_dates(message)
        end_date = dates.get("start_date", "")
        if end_date:
            start_dt = parse_date(state["data"].get("start_date"))
            end_dt = parse_date(end_date)
            if start_dt and end_dt and end_dt > start_dt:
                state["data"]["end_date"] = end_date
                state["step"] = "package_ask_destination"
                nights = (end_dt - start_dt).days
                return {
                    "type": "text",
                    "content": f"👍 Start date: {state['data']['start_date']}\n👍 End date: {end_date}\n📅 Total {nights} nights\n\n📍 Now tell me your destination."
                }
            else:
                return {"type": "text", "content": f"❌ End date must be after {state['data']['start_date']}.\n\nPlease tell me a valid end date."}
        else:
            return {"type": "text", "content": f"❌ I couldn't understand '{message}' as a date.\n\nPlease tell me your end date (e.g., '20 june', '20th')"}

    def _handle_package_destination(self, message: str, state: dict) -> dict:
        validation_result = self._validate_city(message)
        if validation_result.get("is_valid"):
            corrected_city = validation_result["corrected_name"]
            state["data"]["destination"] = corrected_city
            state["step"] = "package_confirm_details"
            city_note = (
                f"📍 You meant {corrected_city} ({validation_result.get('country', '')}), right?"
                if corrected_city.lower() != message.lower()
                else f"📍 Destination: {corrected_city}"
            )
            return {
                "type": "buttons",
                "content": f"{city_note}\n\n📅 Dates: {state['data']['start_date']} → {state['data']['end_date']}\n\nIs this correct?",
                "buttons": [
                    {"text": "✅ Yes, Proceed", "value": "yes"},
                    {"text": "❌ No, Change", "value": "no"}
                ]
            }
        else:
            return {
                "type": "text",
                "content": f"❌ \"{message}\" doesn't appear to be a valid city.\n\n{validation_result.get('suggestion', 'Please enter a valid city name')}"
            }

    def _handle_package_confirmation(self, message: str, state: dict) -> dict:
        if message.lower() in ["yes", "✅ yes, proceed", "proceed"]:
            state["step"] = "package_ask_people"
            return {"type": "text", "content": "👍 Great! Trip details confirmed.\n\n👥 How many people are traveling? (Just type the number)"}
        else:
            state["step"] = "package_ask_dates"
            return {"type": "text", "content": "📅 OK, let's start over. Please tell me your travel dates."}

    def _handle_package_people(self, message: str, state: dict) -> dict:
        people_count = extract_number(message)
        if people_count is None:
            return {"type": "text", "content": "❌ Please enter a valid number (e.g., 2, 3, 4)."}
        elif people_count <= 0:
            return {"type": "text", "content": "❌ Please enter a valid number of people (1 or more)."}
        elif people_count > 20:
            return {"type": "text", "content": "❌ For groups larger than 20 people, please contact us directly for a group discount!"}
        state["data"]["people"] = str(people_count)
        state["step"] = "done"
        return {
            "type": "buttons",
            "content": (
                f"Perfect 🎉\n\n"
                f"📍 {state['data'].get('destination')}\n"
                f"📅 {state['data'].get('start_date')} → {state['data'].get('end_date')}\n"
                f"👥 {state['data'].get('people')} people\n\n"
                f"You can now:\n👉 Find Hotels\n👉 Generate Itinerary"
            ),
            "buttons": [
                {"text": "Find Hotels", "value": "find hotels"},
                {"text": "Generate Itinerary", "value": "generate itinerary"}
            ]
        }

    # LLM Helpers
    def _call_llm(self, prompt: str) -> str:
        try:
            response = self._client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "You are a helpful travel assistant. Keep responses concise and friendly."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.2
            )
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"LLM error: {e}")
            return ""

    def _extract_dates(self, user_input: str) -> dict:
        prompt = DATE_PROMPT.format(
            today=str(date.today()),
            current_month=date.today().strftime("%B"),
            current_year=date.today().year,
            input=user_input
        )
        try:
            llm_response = self._call_llm(prompt)
            cleaned = clean_llm_response(llm_response)
            parsed = json.loads(cleaned)
            return {
                "start_date": parsed.get("start_date", ""),
                "end_date": parsed.get("end_date", "")
            }
        except Exception as e:
            logger.error(f"Date parsing error: {e}")
            return {"start_date": "", "end_date": ""}

    def _validate_city(self, city_name: str) -> dict:
        prompt = VALIDATE_CITY_PROMPT.format(city=city_name)
        try:
            llm_response = self._call_llm(prompt)
            cleaned = clean_llm_response(llm_response)
            result = json.loads(cleaned)
            return {
                "is_valid": result.get("is_valid", False),
                "corrected_name": result.get("corrected_name", city_name),
                "suggestion": result.get("suggestion", ""),
                "country": result.get("country", ""),
                "message": result.get("message", "")
            }
        except Exception as e:
            logger.error(f"City validation error: {e}")
            return {
                "is_valid": True,
                "corrected_name": city_name,
                "suggestion": "",
                "country": "",
                "message": ""
            }

    def _extract_partial_trip(self, user_input: str) -> dict:
        prompt = PARTIAL_TRIP_PROMPT.format(
            today=str(date.today()),
            input=user_input
        )
        try:
            llm_response = self._call_llm(prompt)
            cleaned = clean_llm_response(llm_response)
            parsed = json.loads(cleaned)
            return {
                "destination": parsed.get("destination", ""),
                "start_date": parsed.get("start_date", ""),
                "end_date": parsed.get("end_date", "")
            }
        except Exception as e:
            logger.error(f"Partial trip extraction error: {e}")
            return {"destination": "", "start_date": "", "end_date": ""}