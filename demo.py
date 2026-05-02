"""
agent/agent_executor.py

Prompt-driven travel agent with confirmation step
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
from helpers.helper import extract_number, parse_date, clean_llm_response, format_buttons_grid

import requests

logger = logging.getLogger(__name__)

CATEGORIES_URL = "https://silver-spoonbill-286441.hostingersite.com/wp-json/hm/v1/hotel-categories"
HOTELS_URL = "https://silver-spoonbill-286441.hostingersite.com/wp-json/hm/v1/hotel-categories?phone=919816440734"

load_dotenv()

def get_hotel_categories():
    try:
        response = requests.get(CATEGORIES_URL, timeout=10)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        logger.error(f"get_hotel_categories error: {e}")
        return {"data": []}

def get_hotels_by_category(category: str, location: str) -> list:
    try:
        response = requests.get(HOTELS_URL, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        for c in data.get("data", []):
            if c["category_name"].lower() == category.lower():
                return [
                    h for h in c.get("hotels", [])
                    if location.lower() in h.get("location", "").lower()
                ]
        return []
    except Exception as e:
        logger.error(f"get_hotels_by_category error: {e}")
        return []

class AgentExecutor:
    
    def __init__(self):
        self._client = OpenAI(api_key=os.getenv("OPEN_API_KEY"))
        self._sessions = {}
        logger.info("AgentExecutor initialised")
    
    def execute(self, phone: str, user_message: str) -> dict:
        """Main entry point for processing messages"""
        if phone not in self._sessions:
            self._sessions[phone] = self._fresh_state()
        
        state = self._sessions[phone]
        logger.info(f"[{phone}] step={state['step']} msg={user_message}")
        
        return self._route(phone, user_message, state)
    
    def get_state(self, phone: str) -> dict:
        """Get current state for a user"""
        if phone not in self._sessions:
            self._sessions[phone] = self._fresh_state()
        return self._sessions[phone]
    
    def _fresh_state(self) -> dict:
        return {
            "step": "start",
            "flow": None,
            "data": {}
        }
    def _extract_trip_details(self, user_input: str) -> dict:
        """Extract destination and dates from combined message using LLM"""
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
            logger.error(f"Trip details extraction error: {e}")
            return {"destination": "", "start_date": "", "end_date": ""}
    
    def _reset(self, phone: str):
        self._sessions[phone] = self._fresh_state()
    
    def _route(self, phone: str, message: str, state: dict) -> dict:
        step = state["step"]
        text = message.lower().strip()
        
        # Start - detect intent
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
            elif "hotel" in text or "hotels" in text:
                state["step"] = "hotel_ask_destination"
                state["flow"] = "hotel"
                state["data"] = {}
                return {
                    "type": "text",
                    "content": "🏨 Let me help you find the best hotels!\n\n📍 First, tell me your destination city."
                }
            elif "package" in text:
                state["step"] = "package_ask_dates"
                state["flow"] = "package"
                state["data"] = {}
                return {
                    "type": "text",
                    "content": "📅 Tell me your travel dates (e.g., '12 to 20 june' or '12th to 20th')"
                }
            else:
                # Check if user provided destination + dates together
                extracted = self._extract_trip_details(message)
                if extracted.get("destination") and extracted.get("start_date") and extracted.get("end_date"):
                    # User provided everything together
                    state["data"]["destination"] = extracted["destination"]
                    state["data"]["start_date"] = extracted["start_date"]
                    state["data"]["end_date"] = extracted["end_date"]
                    state["step"] = "hotel_confirm_details"
                    
                    start_dt = parse_date(extracted["start_date"])
                    end_dt = parse_date(extracted["end_date"])
                    nights = (end_dt - start_dt).days if start_dt and end_dt else 0
                    
                    return {
                        "type": "buttons",
                        "content": f"""
    📍 Destination: {extracted['destination']}
    📅 Check-in: {extracted['start_date']}
    📅 Check-out: {extracted['end_date']}
    📆 Total: {nights} nights

    Is this correct?
    """,
                        "buttons": [
                            {"text": "✅ Yes, Proceed", "value": "yes"},
                            {"text": "❌ No, Change", "value": "no"}
                        ]
                    }
                else:
                    return {
                        "type": "buttons",
                        "content": "What would you like to do?",
                        "buttons": [
                            {"text": "Find Hotels", "value": "hotels"},
                            {"text": "Find Packages", "value": "packages"}
                        ]
                    }
        
        # HOTEL FLOW
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
            return self._handle_hotel_selection(message, state)
        
        # PACKAGE FLOW (similar structure)
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
        
        # Navigation handlers
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
        
        if text == "book now":
            return {
                "type": "buttons",
                "content": "🔐 Booking feature coming soon! For now, please contact the hotel directly.\n\nWould you like to search for other hotels?",
                "buttons": [
                    {"text": "See Other Hotels", "value": "see other hotels"},
                    {"text": "New Search", "value": "new search"}
                ]
            }
        
        return {
            "type": "text",
            "content": "🤔 I didn't understand that. Try 'hi', 'find packages', or 'find hotels'."
        }
    
    def _handle_destination(self, message: str, state: dict) -> dict:
        """Validate destination - also check if user provided dates in same message"""
        
        # First check if user provided both destination and dates together
        extracted = self._extract_trip_details(message)
        
        if extracted.get("start_date") and extracted.get("end_date"):
            # User provided dates too! Store them
            state["data"]["start_date"] = extracted["start_date"]
            state["data"]["end_date"] = extracted["end_date"]
        
        # Validate the destination
        validation_result = self._validate_city(message)
        
        # If destination found in extracted details, use that
        destination_to_use = extracted.get("destination") if extracted.get("destination") else message
        
        validation_result = self._validate_city(destination_to_use)
        
        if validation_result.get("is_valid"):
            corrected_city = validation_result["corrected_name"]
            state["data"]["destination"] = corrected_city
            
            # If we already have dates from the combined message
            if state["data"].get("start_date") and state["data"].get("end_date"):
                state["step"] = "hotel_confirm_details"
                start_dt = parse_date(state["data"]["start_date"])
                end_dt = parse_date(state["data"]["end_date"])
                nights = (end_dt - start_dt).days if start_dt and end_dt else 0
                
                return {
                    "type": "buttons",
                    "content": f"""
    📍 Destination: {corrected_city}
    📅 Check-in: {state['data']['start_date']}
    📅 Check-out: {state['data']['end_date']}
    📆 Total: {nights} nights

    Is this correct?
    """,
                    "buttons": [
                        {"text": "✅ Yes, Proceed", "value": "yes"},
                        {"text": "❌ No, Change Dates", "value": "no"}
                    ]
                }
            else:
                state["step"] = "hotel_ask_dates"
                if corrected_city.lower() != destination_to_use.lower():
                    return {
                        "type": "text",
                        "content": f"📍 Got it! You meant **{corrected_city}** ({validation_result.get('country', '')})\n\nNow tell me your check-in and check-out dates.\n\n*Example: 12 to 20 june or 12th to 20th*"
                    }
                else:
                    return {
                        "type": "text",
                        "content": f"📍 Great! Destination: {corrected_city}\n\nNow tell me your check-in and check-out dates.\n\n*Example: 12 to 20 june or 12th to 20th*"
                    }
        else:
            return {
                "type": "text",
                "content": f"❌ \"{message}\" doesn't appear to be a valid city.\n\n{validation_result.get('suggestion', 'Please enter a valid city name')}"
            }
    
    def _handle_dates(self, message: str, state: dict) -> dict:
        """Extract dates - handle both standalone dates and dates with context"""
        
        # First try to extract dates from the message
        dates = self._extract_dates(message)
        start_date = dates.get("start_date", "")
        end_date = dates.get("end_date", "")
        
        # If no dates found but message contains date-related words, try again with PARTIAL_TRIP_PROMPT
        if not start_date and not end_date:
            extracted = self._extract_trip_details(message)
            if extracted.get("start_date") and extracted.get("end_date"):
                start_date = extracted["start_date"]
                end_date = extracted["end_date"]
        
        if start_date and end_date:
            start_dt = parse_date(start_date)
            end_dt = parse_date(end_date)
            
            if start_dt and end_dt and end_dt > start_dt:
                state["data"]["start_date"] = start_date
                state["data"]["end_date"] = end_date
                state["step"] = "hotel_confirm_details"
                
                return {
                    "type": "buttons",
                    "content": f"""
    📅 Please confirm your dates:

    📍 Destination: {state['data']['destination']}
    📅 Check-in: {start_date}
    📅 Check-out: {end_date}
    📆 Total: {(end_dt - start_dt).days} nights

    Is this correct?
    """,
                    "buttons": [
                        {"text": "✅ Yes, Proceed", "value": "yes"},
                        {"text": "❌ No, Change Dates", "value": "no"}
                    ]
                }
            else:
                return {
                    "type": "text",
                    "content": f"❌ Check-out date must be after check-in date.\n\nPlease tell me your dates again (e.g., '12 to 20 june')"
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
                "content": f"❌ I couldn't understand '{message}'.\n\nPlease tell me your dates like:\n• 12 to 20 june\n• 12th to 20th\n• 12 june to 20 june"
            }
    def _handle_end_date(self, message: str, state: dict) -> dict:
        """Handle end date only"""
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
                    "content": f"""
📅 Please confirm your dates:

📍 Destination: {state['data']['destination']}
📅 Check-in: {state['data']['start_date']}
📅 Check-out: {end_date}
📆 Total: {(end_dt - start_dt).days} nights

Is this correct?
""",
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
        """Handle date confirmation"""
        if message.lower() in ["yes", "✅ yes, proceed", "proceed"]:
            state["step"] = "hotel_ask_people"
            return {
                "type": "text",
                "content": f"👍 Great! Dates confirmed.\n\n👥 How many people are traveling? (Just type the number)"
            }
        else:
            state["step"] = "hotel_ask_dates"
            return {
                "type": "text",
                "content": "📅 OK, let's try again. Please tell me your check-in and check-out dates.\n\n*Example: 12 to 20 june*"
            }
    
    def _handle_people(self, message: str, state: dict) -> dict:
        """Handle number of people and show categories"""
        people_count = extract_number(message)
        
        if people_count is None:
            return {
                "type": "text",
                "content": "❌ Please enter a valid number (e.g., 2, 3, 4)."
            }
        elif people_count <= 0:
            return {
                "type": "text",
                "content": "❌ Please enter a valid number of people (1 or more)."
            }
        elif people_count > 20:
            return {
                "type": "text",
                "content": "❌ For groups larger than 20 people, please contact us directly for a group discount!"
            }
        
        state["data"]["people"] = str(people_count)
        state["step"] = "hotel_category_selection"
        
        # Get ALL categories from API
        categories_data = get_hotel_categories()
        logger.info(f"Categories data: {categories_data}")  # Debug log
        
        if categories_data and "data" in categories_data:
            categories = [c["category_name"] for c in categories_data["data"]]
        else:
            categories = ["Budget", "Standard", "Luxury"]
        
        logger.info(f"Categories to show: {categories}")  # Debug log
        
        # Create buttons for ALL categories
        buttons = []
        for cat in categories:
            buttons.append({"text": cat, "value": cat})
        
        # Add action buttons
        buttons.append({"text": "🏨 Show All Hotels", "value": "show all hotels"})
        buttons.append({"text": "📍 Change Destination", "value": "change destination"})
        
        summary = f"""
    ✅ *Trip Details Confirmed*

    📍 *Destination:* {state['data']['destination']}
    📅 *Check-in:* {state['data']['start_date']}
    📅 *Check-out:* {state['data']['end_date']}
    👥 *Guests:* {state['data']['people']} people

    ━━━━━━━━━━━━━━━━━━━━
    🏨 *Select Hotel Category:*
    ━━━━━━━━━━━━━━━━━━━━
    """
        
        return {
            "type": "buttons_grid",
            "content": summary,
            "buttons": buttons
        }
    
    def _handle_category(self, message: str, state: dict) -> dict:
        """Handle category selection and show hotels"""
        selected_category = message.strip()
        destination = state["data"]["destination"]
        
        logger.info(f"Category selected: {selected_category}, Destination: {destination}")  # Debug log
        
        # Handle Change Destination
        if selected_category.lower() == "change destination":
            state["step"] = "hotel_ask_destination"
            state["data"] = {}
            return {
                "type": "text",
                "content": "📍 Let's start over. Tell me your destination city."
            }
        
        # Handle Back to Categories (from hotel selection)
        if selected_category.lower() in ["back to categories", "🔙 back to categories"]:
            state["step"] = "hotel_category_selection"
            categories_data = get_hotel_categories()
            categories = [c["category_name"] for c in categories_data.get("data", [])] or ["Budget", "Standard", "Luxury"]
            
            buttons = [{"text": cat, "value": cat} for cat in categories]
            buttons.append({"text": "🏨 Show All Hotels", "value": "show all hotels"})
            buttons.append({"text": "📍 Change Destination", "value": "change destination"})
            
            return {
                "type": "buttons_grid",
                "content": f"📍 {state['data']['destination']}\n📅 {state['data']['start_date']} → {state['data']['end_date']}\n👥 {state['data']['people']} people\n\n🏨 Select hotel category:",
                "buttons": buttons
            }
        
        # Fetch hotels for selected category
        if selected_category.lower() == "show all hotels":
            categories_data = get_hotel_categories()
            all_hotels = []
            if categories_data and "data" in categories_data:
                for category in categories_data["data"]:
                    hotels = get_hotels_by_category(category["category_name"], destination)
                    all_hotels.extend(hotels)
        else:
            all_hotels = get_hotels_by_category(selected_category, destination)
        
        logger.info(f"Hotels found: {len(all_hotels)}")  # Debug log
        
        # Remove duplicates
        seen = set()
        unique_hotels = []
        for hotel in all_hotels:
            hotel_name = hotel.get("name", "")
            if hotel_name and hotel_name not in seen:
                seen.add(hotel_name)
                unique_hotels.append(hotel)
        
        if not unique_hotels:
            # No hotels found - show categories again
            categories_data = get_hotel_categories()
            categories = [c["category_name"] for c in categories_data.get("data", [])] or ["Budget", "Standard", "Luxury"]
            
            buttons = [{"text": cat, "value": cat} for cat in categories]
            buttons.append({"text": "🏨 Show All Hotels", "value": "show all hotels"})
            buttons.append({"text": "📍 Change Destination", "value": "change destination"})
            
            return {
                "type": "buttons_grid",
                "content": f"😕 No hotels found in *{destination}* for '*{selected_category}*' category.\n\nPlease try another category:",
                "buttons": buttons
            }
        
        # Store hotels and show them
        state["data"]["hotels_list"] = unique_hotels
        state["step"] = "hotel_selection"
        
        # Create buttons for ALL hotels
        hotel_buttons = []
        for hotel in unique_hotels[:20]:  # Limit to 20 for better UX
            hotel_name = hotel.get("name", "Unknown Hotel")
            hotel_buttons.append({"text": hotel_name, "value": hotel_name})
        
        # Add navigation buttons
        hotel_buttons.append({"text": "🔙 Back to Categories", "value": "back to categories"})
        hotel_buttons.append({"text": "📍 Change Destination", "value": "change destination"})
        
        return {
            "type": "buttons_grid",
            "content": f"🏨 Found *{len(unique_hotels)}* hotel(s) in *{destination}* for '*{selected_category}*':\n\nSelect a hotel to see details:",
            "buttons": hotel_buttons
        }
    
    def _handle_hotel_selection(self, message: str, state: dict) -> dict:
        """Show hotel details"""
        selected_hotel_name = message.strip()
        
        if selected_hotel_name.lower() in ["🔙 back to categories", "back to categories"]:
            state["step"] = "hotel_category_selection"
            
            categories_data = get_hotel_categories()
            categories = [c["category_name"] for c in categories_data.get("data", [])] or ["Budget", "Standard", "Luxury"]
            
            buttons = [{"text": cat, "value": cat} for cat in categories]
            buttons.append({"text": "🏨 Show All Hotels", "value": "show all hotels"})
            buttons.append({"text": "📍 Change Destination", "value": "change destination"})
            
            return {
                "type": "buttons_grid",
                "content": f"📍 {state['data']['destination']}\n📅 {state['data']['start_date']} → {state['data']['end_date']}\n👥 {state['data']['people']} people\n\nSelect hotel category:",
                "buttons": buttons
            }
        
        if selected_hotel_name.lower() in ["📍 change destination", "change destination"]:
            state["step"] = "hotel_ask_destination"
            state["data"] = {}
            return {
                "type": "text",
                "content": "📍 Tell me your destination city."
            }
        
        hotels_list = state["data"].get("hotels_list", [])
        selected_hotel = None
        
        for hotel in hotels_list:
            if hotel.get("name", "").lower() == selected_hotel_name.lower():
                selected_hotel = hotel
                break
        
        if not selected_hotel:
            hotel_buttons = [{"text": h.get("name", "Unknown Hotel"), "value": h.get("name", "Unknown Hotel")} for h in hotels_list[:20]]
            hotel_buttons.append({"text": "🔙 Back to Categories", "value": "back to categories"})
            hotel_buttons.append({"text": "📍 Change Destination", "value": "change destination"})
            
            return {
                "type": "buttons_grid",
                "content": "❌ Hotel not found. Please select from the list:",
                "buttons": hotel_buttons
            }
        
        state["step"] = "done"
        
        return {
            "type": "buttons",
            "content": f"""
✅ *Hotel Details*

🏨 **{selected_hotel.get('name', 'N/A')}**
📍 Location: {selected_hotel.get('location', 'N/A')}
⭐ Rating: {selected_hotel.get('rating', 'N/A')} ⭐
💰 Price: {selected_hotel.get('price', 'Contact for price')}

📝 Description:
{selected_hotel.get('description', 'No description available')}

📅 Your Trip:
• Check-in: {state['data']['start_date']}
• Check-out: {state['data']['end_date']}
• Guests: {state['data']['people']} people

Would you like to:
• Book this hotel
• See other hotels
• Start over
""",
            "buttons": [
                {"text": "Book Now", "value": "book now"},
                {"text": "See Other Hotels", "value": "see other hotels"},
                {"text": "New Search", "value": "new search"}
            ]
        }
    
    def _handle_package_dates(self, message: str, state: dict) -> dict:
        """Handle package dates with confirmation"""
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
                return {
                    "type": "text",
                    "content": f"❌ End date must be after start date.\n\nPlease tell me your dates again (e.g., '12 to 20 june')"
                }
        elif start_date and not end_date:
            state["data"]["start_date"] = start_date
            state["step"] = "package_ask_end_date"
            return {
                "type": "text",
                "content": f"👍 Start date: {start_date}\n\nNow tell me your end date."
            }
        else:
            return {
                "type": "text",
                "content": f"❌ I couldn't understand '{message}'.\n\nPlease tell me your dates like:\n• 12 to 20 june\n• 12th to 20th"
            }
    
    def _handle_package_end_date(self, message: str, state: dict) -> dict:
        """Handle package end date"""
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
                return {
                    "type": "text",
                    "content": f"❌ End date must be after {state['data']['start_date']}.\n\nPlease tell me a valid end date."
                }
        else:
            return {
                "type": "text",
                "content": f"❌ I couldn't understand '{message}' as a date.\n\nPlease tell me your end date (e.g., '20 june', '20th')"
            }
    
    def _handle_package_destination(self, message: str, state: dict) -> dict:
        """Handle package destination with confirmation"""
        validation_result = self._validate_city(message)
        
        if validation_result.get("is_valid"):
            corrected_city = validation_result["corrected_name"]
            state["data"]["destination"] = corrected_city
            state["step"] = "package_confirm_details"
            
            if corrected_city.lower() != message.lower():
                return {
                    "type": "buttons",
                    "content": f"📍 You meant {corrected_city} ({validation_result.get('country', '')}), right?\n\n📅 Dates: {state['data']['start_date']} → {state['data']['end_date']}\n\nIs this correct?",
                    "buttons": [
                        {"text": "✅ Yes, Proceed", "value": "yes"},
                        {"text": "❌ No, Change", "value": "no"}
                    ]
                }
            else:
                return {
                    "type": "buttons",
                    "content": f"📍 Destination: {corrected_city}\n\n📅 Dates: {state['data']['start_date']} → {state['data']['end_date']}\n\nIs this correct?",
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
        """Handle package confirmation"""
        if message.lower() in ["yes", "✅ yes, proceed", "proceed"]:
            state["step"] = "package_ask_people"
            return {
                "type": "text",
                "content": f"👍 Great! Trip details confirmed.\n\n👥 How many people are traveling? (Just type the number)"
            }
        else:
            state["step"] = "package_ask_dates"
            return {
                "type": "text",
                "content": "📅 OK, let's start over. Please tell me your travel dates."
            }
    
    def _handle_package_people(self, message: str, state: dict) -> dict:
        """Handle package people count"""
        people_count = extract_number(message)
        
        if people_count is None:
            return {
                "type": "text",
                "content": "❌ Please enter a valid number (e.g., 2, 3, 4)."
            }
        elif people_count <= 0:
            return {
                "type": "text",
                "content": "❌ Please enter a valid number of people (1 or more)."
            }
        elif people_count > 20:
            return {
                "type": "text",
                "content": "❌ For groups larger than 20 people, please contact us directly for a group discount!"
            }
        
        state["data"]["people"] = str(people_count)
        state["step"] = "done"
        
        return {
            "type": "buttons",
            "content": f"""
Perfect 🎉

📍 {state['data'].get('destination')}
📅 {state['data'].get('start_date')} → {state['data'].get('end_date')}
👥 {state['data'].get('people')} people

You can now:
👉 Find Hotels
👉 Generate Itinerary
""",
            "buttons": [
                {"text": "Find Hotels", "value": "find hotels"},
                {"text": "Generate Itinerary", "value": "generate itinerary"}
            ]
        }
    
    def _call_llm(self, prompt: str) -> str:
        """Call LLM with prompt"""
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
        """Extract dates using LLM"""
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
        """Validate city using LLM"""
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