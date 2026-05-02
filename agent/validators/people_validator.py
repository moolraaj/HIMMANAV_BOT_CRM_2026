# agent/validators/people_validator.py
import re
from typing import Dict


class PeopleValidator:
    """Handles people count validation and extraction - NO LLM, just regex"""

    def __init__(self):
        pass

    def extract_people_count(self, text: str) -> Dict:
        """
        Extract number of people from user input.
        Returns: {"valid": bool, "people_count": int or None, "message": str or None}
        """
        text_lower = text.lower().strip()

        # "just me", "only me", "myself", "alone", "1 person", "one person"
        single_person_phrases = ['just me', 'only me', 'myself', 'alone', 'single', '1 person', 'one person', 'solo']
        for phrase in single_person_phrases:
            if phrase in text_lower:
                return {"valid": True, "people_count": 1, "message": None}

        # "family of X"
        family_match = re.search(r'family\s+of\s+(\d+)', text_lower)
        if family_match:
            count = int(family_match.group(1))
            if 1 <= count <= 50:
                return {"valid": True, "people_count": count, "message": None}

        # "X adults and Y children" - count adults
        adults_children = re.search(r'(\d+)\s*(?:adults?|people?)\s*(?:and|with)\s*\d+\s*(?:children|kids)', text_lower)
        if adults_children:
            count = int(adults_children.group(1))
            if 1 <= count <= 50:
                return {"valid": True, "people_count": count, "message": None}

        # "X children and Y adults"
        children_adults = re.search(r'\d+\s*(?:children|kids)\s*(?:and|with)\s*(\d+)\s*(?:adults?|people?)', text_lower)
        if children_adults:
            count = int(children_adults.group(1))
            if 1 <= count <= 50:
                return {"valid": True, "people_count": count, "message": None}

        # "X people/persons/adults/pax/members/travellers"
        standard_patterns = [
            r'(\d+)\s*(?:people|persons|adults|pax|members?|travellers?|travelers?)',
            r'(?:we are|just|only|total|group of)\s*(\d+)',
            r'(\d+)\s*(?:of us)',
        ]
        for pattern in standard_patterns:
            match = re.search(pattern, text_lower)
            if match:
                count = int(match.group(1))
                if 1 <= count <= 50:
                    return {"valid": True, "people_count": count, "message": None}
                else:
                    return {"valid": False, "people_count": None, "message": "Please tell me a valid number between 1 and 50."}

        # Pure number like "4"
        pure_number = re.search(r'^(\d+)$', text_lower.strip())
        if pure_number:
            count = int(pure_number.group(1))
            if 1 <= count <= 50:
                return {"valid": True, "people_count": count, "message": None}
            else:
                return {"valid": False, "people_count": None, "message": "Please tell me a valid number between 1 and 50."}

        # Children only (no adults)
        children_only = re.search(r'(\d+)\s*(?:children|kids|infants|babies)', text_lower)
        if children_only:
            return {"valid": False, "people_count": None, "message": "Please tell me number of adults (children are not counted separately)."}

        return {"valid": False, "people_count": None, "message": "Please tell me how many people (e.g., '2 people', '4 adults', 'just me')."}

    def validate_people_count(self, people_count: int) -> Dict:
        if not people_count:
            return {"valid": False, "people_count": None, "message": "Please tell me how many people."}
        if people_count < 1:
            return {"valid": False, "people_count": None, "message": "Minimum 1 person required."}
        if people_count > 50:
            return {"valid": False, "people_count": None, "message": "Maximum 50 people allowed per booking."}
        return {"valid": True, "people_count": people_count, "message": None}