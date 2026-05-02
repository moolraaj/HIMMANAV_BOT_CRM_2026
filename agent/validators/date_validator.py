# agent/validators/date_validator.py

import re
from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple
import requests
import os
from dotenv import load_dotenv

load_dotenv()
GROQ_API_KEY = os.getenv("GROQ_API_KEY")


class DateValidator:
    """Handles all date validation and extraction - LLM only for unmatched inputs"""

    def __init__(self):
        self.today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

    def _is_gibberish(self, text: str) -> bool:
        """Check if text is gibberish with no meaningful date content"""
        text_lower = text.lower().strip()

        if re.search(r'\d+', text):
            return False

        date_keywords = [
            'tomorrow', 'today', 'next', 'after', 'to', 'till', 'until',
            'jan', 'feb', 'mar', 'apr', 'may', 'jun', 'jul', 'aug',
            'sep', 'oct', 'nov', 'dec', 'monday', 'tuesday', 'wednesday',
            'thursday', 'friday', 'saturday', 'sunday', 'this month', 'tomarrow', 'tommorow'
        ]

        if any(keyword in text_lower for keyword in date_keywords):
            return False

        if len(text) <= 5 and not text.isdigit():
            return True

        words = text_lower.split()
        real_words = 0
        for word in words:
            if len(word) > 2 and any(v in word for v in 'aeiou'):
                real_words += 1

        return real_words == 0

    def _use_llm_for_help(self, user_input: str, context: str = "date") -> str:
        """Use LLM to generate friendly help message when input doesn't match patterns"""
        if not GROQ_API_KEY:
            return self._get_date_error_message()

        prompt = f"""
User said: "{user_input}"

This input does NOT match any valid date pattern for a travel booking system.

Current context: User is being asked for {context}

Your task: Generate a SHORT, FRIENDLY response (1-2 sentences) that:
1. Politely says you couldn't understand the date
2. Shows example of correct format based on context
3. Asks them to try again

Examples of valid formats:
- "12" (single date)
- "12 to 20" (date range)
- "12th June"
- "tomorrow"
- "next Friday"
- "12th of this month"

Return ONLY the response message, no JSON, no quotes, no explanation.
Be warm and helpful, not robotic.
"""

        try:
            response = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
                json={
                    "model": "llama-3.3-70b-versatile",
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.5,
                    "max_tokens": 100
                },
                timeout=10
            )
            if response.status_code == 200:
                return response.json()["choices"][0]["message"]["content"].strip()
        except Exception as e:
            print(f"LLM help error: {e}")

        return self._get_date_error_message()

    def validate_date_order(self, start_date: str, end_date: str) -> Dict:
        """Validate that end date is after start date"""
        if not start_date or not end_date:
            return {"valid": True, "message": None}

        try:
            start = datetime.strptime(start_date, "%Y-%m-%d")
            end = datetime.strptime(end_date, "%Y-%m-%d")

            if end <= start:
                return {
                    "valid": False,
                    "message": f"❌ Your end date ({end.strftime('%d/%m/%Y')}) must be after your start date ({start.strftime('%d/%m/%Y')}).\n\nPlease provide an end date AFTER {start.strftime('%d/%m/%Y')}."
                }
            return {"valid": True, "message": None}
        except ValueError as e:
            return {"valid": False, "message": f"Invalid date format: {e}"}

    def extract_dates(self, text: str, existing_start_date: str = None) -> Dict:
        """
        Extract dates from user input with existing start date context.
        Returns: {
            "valid": bool,
            "start_date": str or None,
            "end_date": str or None,
            "message": str or None,
            "needs_llm_help": bool
        }
        """
        if self._is_gibberish(text):
            llm_message = self._use_llm_for_help(text, "date")
            return {
                "valid": False,
                "start_date": None,
                "end_date": None,
                "message": llm_message,
                "needs_llm_help": True
            }

        # Try regex-based extraction first (more reliable than dateparser)
        result = self._extract_with_regex(text)
        if result and result.get("valid"):
            result = self._apply_existing_start_date(result, existing_start_date)
            if result["valid"] and result.get("start_date") and result.get("end_date"):
                order_check = self.validate_date_order(result["start_date"], result["end_date"])
                if not order_check["valid"]:
                    return {"valid": False, "start_date": None, "end_date": None, "message": order_check["message"], "needs_llm_help": False}
            return {**result, "needs_llm_help": False}

        # Try simple number range
        result = self._extract_simple_range(text)
        if result and result.get("valid"):
            result = self._apply_existing_start_date(result, existing_start_date)
            if result["valid"] and result.get("start_date") and result.get("end_date"):
                order_check = self.validate_date_order(result["start_date"], result["end_date"])
                if not order_check["valid"]:
                    return {"valid": False, "start_date": None, "end_date": None, "message": order_check["message"], "needs_llm_help": False}
            return {**result, "needs_llm_help": False}

        # Try dateparser as last resort
        result = self._extract_with_dateparser(text)
        if result and result.get("valid"):
            result = self._apply_existing_start_date(result, existing_start_date)
            if result["valid"] and result.get("start_date") and result.get("end_date"):
                order_check = self.validate_date_order(result["start_date"], result["end_date"])
                if not order_check["valid"]:
                    return {"valid": False, "start_date": None, "end_date": None, "message": order_check["message"], "needs_llm_help": False}
            return {**result, "needs_llm_help": False}

        # Nothing matched
        llm_message = self._use_llm_for_help(text, "date")
        return {
            "valid": False,
            "start_date": None,
            "end_date": None,
            "message": llm_message,
            "needs_llm_help": True
        }

    def _apply_existing_start_date(self, result: Dict, existing_start_date: str) -> Dict:
        """When collecting end date, treat single parsed date as end date"""
        if existing_start_date and result.get("start_date") and not result.get("end_date"):
            result["end_date"] = result["start_date"]
            result["start_date"] = None

            order_check = self.validate_date_order(existing_start_date, result["end_date"])
            if not order_check["valid"]:
                return {"valid": False, "start_date": None, "end_date": None, "message": order_check["message"]}
        return result

    def _extract_with_dateparser(self, text: str) -> Dict:
        """Extract dates using dateparser library"""
        try:
            from dateparser.search import search_dates

            text_lower = text.lower()

            # Handle "12th of this month"
            this_month_pattern = r'(\d{1,2})(?:st|nd|rd|th)?\s*(?:of\s+)?this\s+month'
            match = re.search(this_month_pattern, text_lower)
            if match:
                return self._create_single_date_current_month(int(match.group(1)))

            # Handle "12th of next month"
            next_month_pattern = r'(\d{1,2})(?:st|nd|rd|th)?\s*(?:of\s+)?next\s+month'
            match = re.search(next_month_pattern, text_lower)
            if match:
                return self._create_single_date_next_month(int(match.group(1)))

            parsed_dates = search_dates(text, settings={
                'PREFER_DATES_FROM': 'future',
                'RELATIVE_BASE': self.today
            })

            if not parsed_dates:
                return {"valid": False}

            if len(parsed_dates) == 1:
                date = parsed_dates[0][1]
                return {
                    "valid": True,
                    "start_date": date.strftime("%Y-%m-%d"),
                    "end_date": None,
                    "message": None
                }

            if len(parsed_dates) >= 2:
                first_date = parsed_dates[0][1]
                second_date = parsed_dates[1][1]
                range_indicators = ["to", "until", "till", "through", "-", "–", "—"]
                if any(ind in text_lower for ind in range_indicators):
                    start = min(first_date, second_date)
                    end = max(first_date, second_date)
                    if end <= start:
                        return {"valid": False}
                    return {
                        "valid": True,
                        "start_date": start.strftime("%Y-%m-%d"),
                        "end_date": end.strftime("%Y-%m-%d"),
                        "message": None
                    }
                else:
                    return {
                        "valid": True,
                        "start_date": first_date.strftime("%Y-%m-%d"),
                        "end_date": None,
                        "message": None
                    }

        except Exception as e:
            print(f"Dateparser error: {e}")

        return {"valid": False}

    def _extract_simple_range(self, text: str) -> Dict:
        """Extract simple number ranges like '12 to 20' (no month specified)"""
        text_lower = text.lower().strip()

        patterns = [
            r'(\d{1,2})\s*(?:to|-|–|—|till|until)\s*(\d{1,2})',
            r'from\s*(\d{1,2})\s*(?:to|-|–|—|till|until)\s*(\d{1,2})',
            r'(\d{1,2})(?:st|nd|rd|th)?\s*(?:to|-|–|—|till|until)\s*(\d{1,2})(?:st|nd|rd|th)?',
        ]

        for pattern in patterns:
            match = re.search(pattern, text_lower)
            if match:
                day1 = int(match.group(1))
                day2 = int(match.group(2))
                if 1 <= day1 <= 31 and 1 <= day2 <= 31:
                    return self._create_range_current_month(day1, day2)

        return {"valid": False}

    def _create_range_current_month(self, day1: int, day2: int) -> Dict:
        """Create date range using current month (or next month if past)"""
        year = self.today.year
        month = self.today.month

        try:
            start_day = min(day1, day2)
            end_day = max(day1, day2)

            start_date = datetime(year, month, start_day)
            end_date = datetime(year, month, end_day)

            # If end date is already past, move to next month
            if end_date < self.today:
                month += 1
                if month > 12:
                    month = 1
                    year += 1
                start_date = datetime(year, month, start_day)
                end_date = datetime(year, month, end_day)

            if end_date <= start_date:
                return {"valid": False}

            return {
                "valid": True,
                "start_date": start_date.strftime("%Y-%m-%d"),
                "end_date": end_date.strftime("%Y-%m-%d"),
                "message": None
            }
        except ValueError:
            return {"valid": False}

    def _extract_with_regex(self, text: str) -> Dict:
        """Extract dates using regex patterns"""
        text_lower = text.lower().strip()

        # --- Handle "after X days till Y" pattern ---
        after_till_pattern = r'after\s+(\d+)\s+days?\s+(?:till|until|to)\s+(\d{1,2})(?:st|nd|rd|th)?'
        match = re.search(after_till_pattern, text_lower)
        if match:
            days_after = int(match.group(1))
            target_day = int(match.group(2))
            
            # Start date: today + days_after
            start_date = self.today + timedelta(days=days_after)
            
            # End date: target_day of next month (if target_day < current day, otherwise current month)
            year = start_date.year
            month = start_date.month
            
            # If target day is less than start date's day, go to next month
            if target_day <= start_date.day:
                month += 1
                if month > 12:
                    month = 1
                    year += 1
            
            try:
                end_date = datetime(year, month, target_day)
                # If end date is still before start date, add another month
                while end_date <= start_date:
                    month += 1
                    if month > 12:
                        month = 1
                        year += 1
                    end_date = datetime(year, month, target_day)
                
                return {
                    "valid": True,
                    "start_date": start_date.strftime("%Y-%m-%d"),
                    "end_date": end_date.strftime("%Y-%m-%d"),
                    "message": None
                }
            except ValueError:
                # If day doesn't exist (e.g., 31st in some months), use last day of month
                if month > 12:
                    month = 1
                    year += 1
                # Get last day of the month
                if month == 12:
                    next_month = datetime(year + 1, 1, 1)
                else:
                    next_month = datetime(year, month + 1, 1)
                last_day = (next_month - timedelta(days=1)).day
                target_day = min(target_day, last_day)
                end_date = datetime(year, month, target_day)
                
                return {
                    "valid": True,
                    "start_date": start_date.strftime("%Y-%m-%d"),
                    "end_date": end_date.strftime("%Y-%m-%d"),
                    "message": None
                }

        # --- Handle "after X days" (without till) ---
        after_pattern = r'after\s+(\d+)\s+days?'
        match = re.search(after_pattern, text_lower)
        if match and 'till' not in text_lower and 'to' not in text_lower and 'until' not in text_lower:
            days = int(match.group(1))
            date = self.today + timedelta(days=days)
            return {"valid": True, "start_date": date.strftime("%Y-%m-%d"), "end_date": None, "message": None}

        # --- Handle "till X" or "until X" ---
        till_pattern = r'(?:till|until|to)\s+(\d{1,2})(?:st|nd|rd|th)?(?:\s+(?:of\s+)?(\w+))?'
        match = re.search(till_pattern, text_lower)
        if match and 'after' not in text_lower:
            target_day = int(match.group(1))
            month_str = match.group(2) if len(match.groups()) > 1 else None
            
            if month_str:
                # Specific month mentioned
                month_num = self._month_to_number(month_str)
                if month_num:
                    return self._create_single_date(target_day, month_num)
            else:
                # Just "till 5" - means 5th of next month
                year = self.today.year
                month = self.today.month + 1
                if month > 12:
                    month = 1
                    year += 1
                try:
                    date = datetime(year, month, target_day)
                    return {"valid": True, "start_date": None, "end_date": date.strftime("%Y-%m-%d"), "message": None}
                except ValueError:
                    return {"valid": False}
        
        # Handle "tomorrow"
        if 'tomorrow' in text_lower or 'tomarrow' in text_lower or 'tommorow' in text_lower:
            date = self.today + timedelta(days=1)
            return {"valid": True, "start_date": date.strftime("%Y-%m-%d"), "end_date": None, "message": None}
        
        # Handle "today"
        if 'today' in text_lower:
            return {"valid": True, "start_date": self.today.strftime("%Y-%m-%d"), "end_date": None, "message": None}
        
        # Handle single day with month (e.g., "12th June")
        single_date_pattern = r'(\d{1,2})(?:st|nd|rd|th)?\s+(\w+)'
        match = re.search(single_date_pattern, text_lower)
        if match:
            day = int(match.group(1))
            month_str = match.group(2)
            month_num = self._month_to_number(month_str)
            if month_num:
                return self._create_single_date(day, month_num)
        
        # Handle date range with month (e.g., "12th to 15th June")
        range_pattern = r'(\d{1,2})(?:st|nd|rd|th)?\s*(?:to|-|–|—)\s*(\d{1,2})(?:st|nd|rd|th)?(?:\s+(\w+))?'
        match = re.search(range_pattern, text_lower)
        if match:
            day1 = int(match.group(1))
            day2 = int(match.group(2))
            month_str = match.group(3) if len(match.groups()) > 2 else None
            
            if month_str:
                month_num = self._month_to_number(month_str)
                if month_num:
                    return self._create_range_date(day1, day2, month_num)
            else:
                # No month specified, use current month
                return self._create_range_current_month(day1, day2)
        
        # Handle single number (e.g., "12")
        if text_lower.isdigit() and 1 <= int(text_lower) <= 31:
            return self._create_single_date_current_month(int(text_lower))

        # Return not valid if no patterns matched
        return {"valid": False}

    def _create_single_date_current_month(self, day: int) -> Dict:
        """Create single date using current month; roll to next month if past"""
        year = self.today.year
        month = self.today.month
        try:
            date = datetime(year, month, day)
            if date < self.today:
                month += 1
                if month > 12:
                    month = 1
                    year += 1
                date = datetime(year, month, day)
            return {"valid": True, "start_date": date.strftime("%Y-%m-%d"), "end_date": None, "message": None}
        except ValueError:
            return {"valid": False}

    def _create_single_date_next_month(self, day: int) -> Dict:
        """Create single date for next month"""
        year = self.today.year
        month = self.today.month + 1
        if month > 12:
            month = 1
            year += 1
        try:
            date = datetime(year, month, day)
            return {"valid": True, "start_date": date.strftime("%Y-%m-%d"), "end_date": None, "message": None}
        except ValueError:
            return {"valid": False}

    def _create_range_date(self, day1: int, day2: int, month_num: int) -> Dict:
        """Create date range within same month"""
        year = self.today.year
        if month_num < self.today.month:
            year += 1
        try:
            start_day = min(day1, day2)
            end_day = max(day1, day2)
            start_date = datetime(year, month_num, start_day)
            end_date = datetime(year, month_num, end_day)
            if end_date <= start_date:
                return {"valid": False}
            return {"valid": True, "start_date": start_date.strftime("%Y-%m-%d"), "end_date": end_date.strftime("%Y-%m-%d"), "message": None}
        except ValueError:
            return {"valid": False}

    def _create_cross_month_range(self, day1: int, month1: int, day2: int, month2: int) -> Dict:
        """Create date range across different months"""
        year = self.today.year
        try:
            start_date = datetime(year, month1, day1)
            end_date = datetime(year, month2, day2)
            if start_date < self.today:
                start_date = datetime(year + 1, month1, day1)
                end_date = datetime(year + 1, month2, day2)
            if end_date <= start_date:
                return {"valid": False}
            return {"valid": True, "start_date": start_date.strftime("%Y-%m-%d"), "end_date": end_date.strftime("%Y-%m-%d"), "message": None}
        except ValueError:
            return {"valid": False}

    def _create_single_date(self, day: int, month_num: int) -> Dict:
        """Create single date from day + month number"""
        year = self.today.year
        try:
            date = datetime(year, month_num, day)
            if date < self.today:
                date = datetime(year + 1, month_num, day)
            return {"valid": True, "start_date": date.strftime("%Y-%m-%d"), "end_date": None, "message": None}
        except ValueError:
            return {"valid": False}

    def _month_to_number(self, month: str) -> Optional[int]:
        """Convert month name to number; returns None if not a month"""
        months = {
            'jan': 1, 'january': 1, 'feb': 2, 'february': 2,
            'mar': 3, 'march': 3, 'apr': 4, 'april': 4,
            'may': 5, 'jun': 6, 'june': 6, 'jul': 7, 'july': 7,
            'aug': 8, 'august': 8, 'sep': 9, 'sept': 9, 'september': 9,
            'oct': 10, 'october': 10, 'nov': 11, 'november': 11,
            'dec': 12, 'december': 12
        }
        return months.get(month[:3].lower() if len(month) >= 3 else month.lower())

    def _get_date_error_message(self) -> str:
        return (
            "I couldn't understand the date. Please use formats like:\n"
            "• 12 (single date - current month)\n"
            "• 12 to 20 (date range - current month)\n"
            "• 12th June\n"
            "• 12th to 20th June\n"
            "• tomorrow\n"
            "• next Friday\n"
            "• after 5 days\n"
            "• 12th of this month"
        )

    def validate_date_string(self, date_string: str) -> Tuple[bool, Optional[str]]:
        """Validate if a string is a valid date"""
        if not date_string:
            return False, "Please provide a date."
        result = self.extract_dates(date_string)
        if result["valid"]:
            return True, None
        return False, result.get("message", "Invalid date format")