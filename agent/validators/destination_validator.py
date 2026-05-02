# agent/validators/destination_validator.py
import json
import re
import requests
import os
from typing import Dict, Optional
from dotenv import load_dotenv

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")


class DestinationValidator:
    """Handles destination validation using LLM"""

    def __init__(self):
        self.llm_api_key = GROQ_API_KEY

    def extract_destination(self, text: str) -> Dict:
        """
        Extract destination from user input using LLM.
        Returns: {"valid": bool, "destination": str or None, "message": str or None}
        """
        if not self.llm_api_key:
            return self._fallback_extraction(text)

        prompt = self._get_extraction_prompt(text)
        response_text = self._call_llm(prompt)

        if response_text:
            try:
                response_text = re.sub(r'```json\s*', '', response_text)
                response_text = re.sub(r'```\s*', '', response_text)
                result = json.loads(response_text)
                return {
                    "valid": result.get("valid", False),
                    "destination": result.get("destination"),
                    "message": result.get("message")
                }
            except json.JSONDecodeError:
                pass

        return self._fallback_extraction(text)

    def _get_extraction_prompt(self, text: str) -> str:
        return f"""
User said: "{text}"

Extract the destination/city from user's message.

Return ONLY JSON (no other text):
{{
    "valid": true or false,
    "destination": "city name" or null,
    "message": "error message if invalid, otherwise null"
}}

Rules:
- If user mentions a real city or travel destination anywhere in the world → valid=true, destination="City Name"
- If user mentions gibberish or clearly fake name → valid=false, message="Sorry, I don't recognize that as a city. Please tell me a real destination."
- If no city mentioned → valid=false, message="Please tell me which city you want to visit."
- Correct minor spelling errors (e.g. "Shimlaa" → "Shimla")

Examples:
Input: "I want to go to Shimla" → {{"valid": true, "destination": "Shimla", "message": null}}
Input: "Manali" → {{"valid": true, "destination": "Manali", "message": null}}
Input: "XYZ city" → {{"valid": false, "destination": null, "message": "Sorry, I don't recognize 'XYZ city'. Please tell me a real city name."}}
"""

    def _call_llm(self, prompt: str) -> Optional[str]:
        if not self.llm_api_key:
            return None
        try:
            response = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {self.llm_api_key}", "Content-Type": "application/json"},
                json={
                    "model": "llama-3.3-70b-versatile",
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.1,
                    "max_tokens": 150
                },
                timeout=10
            )
            if response.status_code == 200:
                return response.json()["choices"][0]["message"]["content"].strip()
            return None
        except Exception as e:
            print(f"LLM error in destination validator: {e}")
            return None

    def _fallback_extraction(self, text: str) -> Dict:
        """Fallback when LLM fails - checks common Indian cities"""
        common_cities = [
            "shimla", "manali", "goa", "delhi", "mumbai", "kerala",
            "jaipur", "udaipur", "spiti", "ladakh", "ooty", "coorg",
            "agra", "varanasi", "rishikesh", "bangalore", "hyderabad",
            "chennai", "kolkata", "pune", "ahmedabad", "srinagar"
        ]
        text_lower = text.lower()
        for city in common_cities:
            if city in text_lower:
                return {"valid": True, "destination": city.title(), "message": None}
        return {"valid": False, "destination": None, "message": "Please tell me which city you want to visit."}

    def validate_destination(self, destination: str) -> Dict:
        if not destination or len(destination) < 2:
            return {"valid": False, "destination": None, "message": "Please provide a valid city name."}

        prompt = f"""
Is "{destination}" a real city or travel destination?

Return ONLY JSON:
{{
    "valid": true or false,
    "destination": "corrected city name" or null,
    "message": "error message if invalid, otherwise null"
}}

Correct minor spelling errors if needed.
"""
        response = self._call_llm(prompt)
        if response:
            try:
                response = re.sub(r'```json\s*', '', response)
                response = re.sub(r'```\s*', '', response)
                result = json.loads(response)
                return {
                    "valid": result.get("valid", False),
                    "destination": result.get("destination", destination),
                    "message": result.get("message")
                }
            except:
                pass

        return {"valid": True, "destination": destination, "message": None}