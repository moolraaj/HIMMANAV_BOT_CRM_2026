# agent/validators/llm_validator.py
import json
import re
import requests
import os
from typing import Dict
from dotenv import load_dotenv

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")


class LLMValidator:
    """LLM for destination extraction and corrections ONLY - NO date validation here"""

    def __init__(self):
        self.llm_api_key = GROQ_API_KEY

    def validate_travel_plan(self, user_input: str, context: Dict = None) -> Dict:
        """
        LLM CALL - Extracts destination and handles corrections ONLY.
        Returns: {"destination_valid": bool, "destination": str or None, "is_correction": bool, "message": str or None}
        """
        context_prompt = ""
        if context:
            context_prompt = f"""
PREVIOUS CONTEXT (if user is correcting):
- Current destination in system: {context.get('destination', 'none')}
- Current start date: {context.get('start_date', 'none')}
- Current end date: {context.get('end_date', 'none')}
- Step: {context.get('step', 'unknown')}

If user says "No" or "That's wrong" or provides corrections, UPDATE the incorrect fields.
"""

        prompt = f"""
{context_prompt}

User input: "{user_input}"

CRITICAL: Extract destination from the message.

RULES:
1. DESTINATION EXTRACTION:
   - Look for any real city or travel destination
   - Examples: "travelling to Manali" → destination="Manali", "going Shimla" → destination="Shimla"

2. HANDLE CORRECTIONS:
   - If user says "No" or "That's wrong" or "Not Manali, it's Shimla" → update destination

Return ONLY JSON (no other text):
{{
    "destination_valid": true/false,
    "destination": "city name" or null,
    "is_correction": true/false,
    "message": "error message" or null
}}

EXAMPLES:
Input: "travelling to Manali" → {{"destination_valid": true, "destination": "Manali", "is_correction": false, "message": null}}
Input: "Not Manali, it's Shimla" → {{"destination_valid": true, "destination": "Shimla", "is_correction": true, "message": null}}
Input: "asdfghjkl" → {{"destination_valid": false, "destination": null, "is_correction": false, "message": "I couldn't understand. Please tell me a valid city name."}}
"""

        response_text = self._call_llm(prompt)

        if response_text:
            try:
                response_text = re.sub(r'```json\s*', '', response_text)
                response_text = re.sub(r'```\s*', '', response_text)
                result = json.loads(response_text)
                return result
            except json.JSONDecodeError as e:
                print(f"JSON parse error: {e}")
                return self._fallback_validation(user_input)

        return self._fallback_validation(user_input)

    def _call_llm(self, prompt: str) -> str:
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
                    "max_tokens": 300
                },
                timeout=15
            )
            if response.status_code == 200:
                content = response.json()["choices"][0]["message"]["content"]
                print(f"🤖 LLM Response: {content[:300]}")
                return content.strip()
            else:
                print(f"LLM API error: {response.status_code}")
                return None
        except Exception as e:
            print(f"LLM call error: {e}")
            return None

    def _fallback_validation(self, user_input: str) -> Dict:
        return {
            "destination_valid": False,
            "destination": None,
            "is_correction": False,
            "message": "I couldn't understand. Please tell me your destination clearly."
        }