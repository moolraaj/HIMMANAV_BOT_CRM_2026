# agent/agent_executor.py

from typing import Dict
import requests
import json
import re
import os
from datetime import datetime, timedelta
from dotenv import load_dotenv
from agent.validators.date_validator import DateValidator
from agent.validators.destination_validator import DestinationValidator
from agent.validators.people_validator import PeopleValidator
from agent.validators.llm_validator import LLMValidator

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")


class AgentExecutor:
    """
    Travel booking agent.
    Flow: main_menu → start_date → end_date → destination → confirm → people_count → confirm_people
    """

    def __init__(self, phone_number: str = None):
        self.phone_number = phone_number
        self.sessions: Dict[str, Dict] = {}
        self.date_validator = DateValidator()
        self.destination_validator = DestinationValidator()
        self.people_validator = PeopleValidator()
        self.llm_validator = LLMValidator()

    # ────────────────────────── STATE HELPERS ──────────────────────────

    def get_state(self, phone: str) -> Dict:
        if phone not in self.sessions:
            self.sessions[phone] = self._fresh_state()
        return self.sessions[phone]

    def _fresh_state(self) -> Dict:
        return {
            "step": "main_menu",
            "booking_type": None,
            "start_date": None,
            "end_date": None,
            "destination": None,
            "people_count": None,
        }

    def update_state(self, phone: str, updates: Dict):
        state = self.get_state(phone)
        state.update(updates)

    def _reset_booking(self, phone: str):
        self.sessions[phone] = self._fresh_state()

    # ────────────────────────── UTILS ──────────────────────────

    def _format_date_display(self, date_str: str) -> str:
        """Convert YYYY-MM-DD → DD/MM/YYYY"""
        if not date_str:
            return "Not set"
        try:
            return datetime.strptime(date_str, "%Y-%m-%d").strftime("%d/%m/%Y")
        except:
            return date_str

    def _booking_summary(self, state: Dict) -> str:
        btype = "Packages" if state.get("booking_type") == "package" else "Hotels"
        lines = [f"📍 Destination: {state.get('destination', '-')}",
                 f"📅 Dates: {self._format_date_display(state.get('start_date'))} → {self._format_date_display(state.get('end_date'))}",
                 f"🔖 Type: {btype}"]
        if state.get("people_count"):
            p = state["people_count"]
            lines.append(f"👥 Travelers: {p} {'adult' if p == 1 else 'adults'}")
        return "\n".join(lines)

    def _cancelled_response(self) -> Dict:
        return {
            "type": "buttons",
            "content": "Cancelled! How can I help you?",
            "buttons": [
                {"text": "Find Packages", "value": "package"},
                {"text": "Find Hotels", "value": "hotel"}
            ]
        }

    def _is_cancel(self, text: str) -> bool:
        return text.lower() in ["cancel", "exit", "menu"]

    def _is_yes(self, text: str) -> bool:
        return text.lower() in ["yes", "yeah", "correct", "right", "y", "ok", "okay", "yep", "yup"]

    def _is_no(self, text: str) -> bool:
        return text.lower() in ["no", "nope", "wrong", "nah", "n"]

    def _is_rubbish_input(self, text: str) -> bool:
        """Quick check for completely meaningless input"""
        text_lower = text.lower().strip()

        valid_patterns = [
            r'\d+',
            r'(package|hotel|travel|trip|book|find|search)',
            r'(manali|shimla|goa|delhi|mumbai|kerala|jaipur|udaipur|spiti|ladakh|ooty|coorg)',
            r'(tomorrow|tomarrow|tommorow|today|next|after|to|till|until|from)',
            r'(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)',
            r'(monday|tuesday|wednesday|thursday|friday|saturday|sunday)',
            r'(hi|hello|hey|hii|helo|hai|namaste)',
            r'(yes|no|yeah|nope|correct|wrong|back|cancel|exit|menu|okay|ok)',
            r'(just me|myself|alone|solo)',
            r'(people|adults|pax|family)',
        ]

        for pattern in valid_patterns:
            if re.search(pattern, text_lower):
                return False

        # Very short non-numeric input
        if len(text) <= 3 and not text.isdigit():
            return True

        # Check if any real words exist
        words = text_lower.split()
        real_words = sum(1 for w in words if len(w) > 2 and any(v in w for v in 'aeiou'))
        return real_words == 0

    def _handle_rubbish_with_llm(self, user_input: str) -> str:
        prompt = f"""
User sent a meaningless/nonsense message: "{user_input}"

Respond VERY briefly (1-2 sentences) as a friendly travel assistant.
Tell them you couldn't understand and ask them to choose Packages or Hotels to start.

Return ONLY the message, no JSON.
"""
        if GROQ_API_KEY:
            try:
                response = requests.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
                    json={"model": "llama-3.3-70b-versatile",
                          "messages": [{"role": "user", "content": prompt}],
                          "temperature": 0.5, "max_tokens": 80},
                    timeout=10
                )
                if response.status_code == 200:
                    return response.json()["choices"][0]["message"]["content"].strip()
            except Exception as e:
                print(f"LLM rubbish handler error: {e}")
        return "I'm a travel assistant! Please choose 'Find Packages' or 'Find Hotels' to get started. 😊"

    # ────────────────────────── MAIN EXECUTE ──────────────────────────

    def execute(self, phone: str, user_input: str) -> Dict:
        state = self.get_state(phone)
        user_input = user_input.strip()

        print(f"[Step: {state['step']}] User: {user_input}")

        # Global cancel check (except main_menu)
        if state["step"] != "main_menu" and self._is_cancel(user_input):
            self._reset_booking(phone)
            return self._cancelled_response()

        # Rubbish check (skip for short valid inputs like "4", "hi", "yes")
        if len(user_input) > 3 and self._is_rubbish_input(user_input):
            msg = self._handle_rubbish_with_llm(user_input)
            return {"type": "text", "content": msg}

        # Route
        handlers = {
            "main_menu": self._handle_main_menu,
            "start_date": self._handle_start_date,
            "end_date": self._handle_end_date,
            "destination": self._handle_destination,
            "confirm": self._handle_confirm,
            "people_count": self._handle_people_count,
            "confirm_people": self._handle_confirm_people,
        }

        handler = handlers.get(state["step"])
        if handler:
            return handler(phone, user_input)

        return {"type": "text", "content": "Welcome! How can I help you today?"}

    # ────────────────────────── MAIN MENU ──────────────────────────

    def _handle_main_menu(self, phone: str, user_input: str) -> Dict:
        user_lower = user_input.lower().strip()

        greetings = ["hi", "hello", "hey", "hii", "helo", "hai", "namaste", "hiya"]
        if any(g == user_lower or g in user_lower for g in greetings):
            return {
                "type": "buttons",
                "content": "👋 Hello! I'm your travel assistant.\n\nHow can I help you today?",
                "buttons": [
                    {"text": "Find Packages", "value": "package"},
                    {"text": "Find Hotels", "value": "hotel"}
                ]
            }

        # User clicked a button
        if user_lower in ["package", "hotel"]:
            self.update_state(phone, {"booking_type": user_lower, "step": "start_date"})
            btype = "packages" if user_lower == "package" else "hotels"
            return {
                "type": "text",
                "content": (
                    f"Great! Let's find {btype} for you. 🎒\n\n"
                    "📅 Please tell me your *start date*.\n\n"
                    "Examples:\n"
                    "• 12\n"
                    "• 12th June\n"
                    "• tomorrow\n"
                    "• next Friday\n"
                    "• 12 to 20 (I'll set both dates at once!)"
                )
            }

        # Default: show menu
        return {
            "type": "buttons",
            "content": "👋 Welcome! How can I help you today?",
            "buttons": [
                {"text": "Find Packages", "value": "package"},
                {"text": "Find Hotels", "value": "hotel"}
            ]
        }

    # ────────────────────────── START DATE ──────────────────────────

    def _handle_start_date(self, phone: str, user_input: str) -> Dict:
        state = self.get_state(phone)

        date_result = self.date_validator.extract_dates(user_input)

        if not date_result.get("valid"):
            return {
                "type": "text",
                "content": date_result.get("message", "I couldn't understand that date. Please try again.\n\nExamples: tomorrow, 12th June, 12 to 20")
            }

        # Got a range — set both dates, skip to destination
        if date_result.get("end_date"):
            self.update_state(phone, {
                "start_date": date_result["start_date"],
                "end_date": date_result["end_date"],
                "step": "destination"
            })
            return {
                "type": "text",
                "content": (
                    f"✅ Dates set!\n"
                    f"Start: {self._format_date_display(date_result['start_date'])}\n"
                    f"End:   {self._format_date_display(date_result['end_date'])}\n\n"
                    "📍 Now tell me your *destination city*:"
                )
            }

        # Got single date — save as start, ask for end
        self.update_state(phone, {
            "start_date": date_result["start_date"],
            "step": "end_date"
        })
        return {
            "type": "text",
            "content": (
                f"✅ Start date: {self._format_date_display(date_result['start_date'])}\n\n"
                "📅 Now tell me your *end date*:"
            )
        }

    # ────────────────────────── END DATE ──────────────────────────

    def _handle_end_date(self, phone: str, user_input: str) -> Dict:
        state = self.get_state(phone)

        if user_input.lower() == "back":
            self.update_state(phone, {"step": "start_date", "start_date": None})
            return {"type": "text", "content": "No problem! Tell me your start date again:"}

        # Pass existing start date so validator can check order
        date_result = self.date_validator.extract_dates(user_input, existing_start_date=state["start_date"])

        if not date_result.get("valid"):
            return {
                "type": "text",
                "content": date_result.get("message", "I couldn't understand that date. Please tell me your end date.")
            }

        # Accept whichever date slot was filled
        end_date = date_result.get("end_date") or date_result.get("start_date")
        self.update_state(phone, {"end_date": end_date, "step": "destination"})

        return {
            "type": "text",
            "content": (
                f"✅ Dates set!\n"
                f"Start: {self._format_date_display(state['start_date'])}\n"
                f"End:   {self._format_date_display(end_date)}\n\n"
                "📍 Now tell me your *destination city*:"
            )
        }

    # ────────────────────────── DESTINATION ──────────────────────────

    def _handle_destination(self, phone: str, user_input: str) -> Dict:
        state = self.get_state(phone)

        if user_input.lower() == "back":
            self.update_state(phone, {"step": "end_date", "end_date": None})
            return {"type": "text", "content": f"No problem! Your start date is {self._format_date_display(state['start_date'])}.\n\nPlease tell me your end date:"}

        # Try DestinationValidator first (uses LLM)
        dest_result = self.destination_validator.extract_destination(user_input)

        if not dest_result.get("valid"):
            # Fallback to LLMValidator
            llm_result = self.llm_validator.validate_travel_plan(user_input, context=state)
            if llm_result.get("destination_valid"):
                dest_result = {"valid": True, "destination": llm_result["destination"]}
            else:
                return {
                    "type": "text",
                    "content": (
                        dest_result.get("message") or llm_result.get("message") or
                        "I couldn't recognize that city. Please tell me a real destination.\n\nExamples: Manali, Shimla, Goa, Delhi, Mumbai"
                    )
                }

        self.update_state(phone, {"destination": dest_result["destination"], "step": "confirm"})

        return {
            "type": "buttons",
            "content": (
                "Please confirm your trip details:\n\n"
                + self._booking_summary({**state, "destination": dest_result["destination"]})
                + "\n\nIs this correct?"
            ),
            "buttons": [
                {"text": "Yes, looks good!", "value": "yes"},
                {"text": "No, change it", "value": "no"}
            ]
        }

    # ────────────────────────── CONFIRM ──────────────────────────

    def _handle_confirm(self, phone: str, user_input: str) -> Dict:
        state = self.get_state(phone)

        if self._is_yes(user_input):
            self.update_state(phone, {"step": "people_count"})
            return {
                "type": "text",
                "content": (
                    "👥 Almost there! How many people are traveling?\n\n"
                    "Examples: 2 people, 4 adults, just me, family of 5"
                )
            }

        # User said no — restart from start date
        self.update_state(phone, {
            "step": "start_date",
            "start_date": None,
            "end_date": None,
            "destination": None,
            "people_count": None
        })
        return {
            "type": "text",
            "content": "No worries! Let's start over. 😊\n\nPlease tell me your start date:"
        }

    # ────────────────────────── PEOPLE COUNT ──────────────────────────

    def _handle_people_count(self, phone: str, user_input: str) -> Dict:
        state = self.get_state(phone)

        people_result = self.people_validator.extract_people_count(user_input)

        if not people_result.get("valid"):
            return {
                "type": "text",
                "content": (
                    f"{people_result.get('message')}\n\n"
                    f"Your trip so far:\n{self._booking_summary(state)}"
                )
            }

        people_count = people_result["people_count"]
        self.update_state(phone, {"people_count": people_count, "step": "confirm_people"})

        p_label = "adult" if people_count == 1 else "adults"
        return {
            "type": "buttons",
            "content": (
                "Please confirm your complete booking:\n\n"
                + self._booking_summary({**state, "people_count": people_count})
                + "\n\nAll good?"
            ),
            "buttons": [
                {"text": "Yes, confirm!", "value": "yes"},
                {"text": "No, change", "value": "no"}
            ]
        }

    # ────────────────────────── CONFIRM PEOPLE ──────────────────────────

    def _handle_confirm_people(self, phone: str, user_input: str) -> Dict:
        state = self.get_state(phone)

        if self._is_yes(user_input):
            # Capture details BEFORE resetting state
            destination = state.get("destination", "-")
            start_date = self._format_date_display(state.get("start_date"))
            end_date = self._format_date_display(state.get("end_date"))
            people_count = state.get("people_count", 1)
            booking_type = "Packages" if state.get("booking_type") == "package" else "Hotels"
            p_label = "adult" if people_count == 1 else "adults"

            print(f"✅ BOOKING CONFIRMED: {state}")

            # Now reset
            self._reset_booking(phone)

            return {
                "type": "text",
                "content": (
                    "🎉 *Booking Confirmed!*\n\n"
                    f"📍 Destination: {destination}\n"
                    f"📅 Dates: {start_date} → {end_date}\n"
                    f"👥 Travelers: {people_count} {p_label}\n"
                    f"🔖 Type: {booking_type}\n\n"
                    "We'll send you the best options shortly! ✈️\n\n"
                    "Type *hi* to plan another trip!"
                )
            }

        # User said no — go back to people count
        self.update_state(phone, {"step": "people_count", "people_count": None})
        return {
            "type": "text",
            "content": (
                "No problem! Let's fix that.\n\n"
                f"Your trip:\n{self._booking_summary(state)}\n\n"
                "How many people are traveling?"
            )
        }