import requests
import json
import re
import os
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv('.env')
GROQ_API_KEY = os.getenv("GROQ_API_KEY")


def understand_user(user_input, conversation_context=None):
    """Understand what user wants using LLM with conversation context"""
    try:
        url = "https://api.groq.com/openai/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "Content-Type": "application/json"
        }

        context_str = json.dumps(conversation_context) if conversation_context else "{}"
        
        prompt = f"""
Conversation Context: {context_str}
User message: "{user_input}"

Analyze this message and return ONLY valid JSON (no extra text, no markdown):

{{
  "intent": "greeting or requirement_answer or search_packages or followup or chitchat or connect_ceo",
  "requirement_type": "dates or travelers or destination or null",
  "requirement_value": "extracted value or null",
  "price": "lowest or highest or any",
  "locations": ["list", "of", "destinations"] or null,
  "package_name": "specific package name or null",
  "followup_type": "itinerary or hotels or activities or vehicles or inclusions or exclusions or null",
  "chitchat_reply": "friendly response if intent is chitchat",
  "is_complete": true or false
}}

Rules:
- If user provides travel dates → intent="requirement_answer", requirement_type="dates"
- If user provides number of people → intent="requirement_answer", requirement_type="travelers"
- If user provides destination preferences → intent="requirement_answer", requirement_type="destination"
- If user says "find packages" or "show me packages" → intent="search_packages"
- If user asks about itinerary/hotels/activities → intent="followup"
- If user says "connect to agent" → intent="connect_ceo"
- For greetings, respond warmly
- For chitchat, respond helpfully
"""

        body = {
            "model": "llama-3.3-70b-versatile",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1
        }

        response = requests.post(url, headers=headers, json=body, timeout=15)

        if response.status_code == 200:
            data = response.json()
            content = data["choices"][0]["message"]["content"]
            content = re.sub(r'```json\s*', '', content)
            content = re.sub(r'```\s*', '', content)
            content = content.strip()
            parsed = json.loads(content)
            print(f"🧠 LLM Intent: {parsed}")
            return parsed

        print(f"⚠️ Groq API error: {response.status_code}")
        return _default_intent()

    except Exception as e:
        print(f"❌ LLM error: {e}")
        return _default_intent()


def extract_travel_dates_llm(user_input):
    """Extract travel dates using LLM - handles relative dates, single dates, ranges"""
    try:
        url = "https://api.groq.com/openai/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "Content-Type": "application/json"
        }
        
        current_date = datetime.now()
        today_str = current_date.strftime("%Y-%m-%d")
        
        prompt = f"""
Extract travel dates from user input: "{user_input}"

Current date is: {today_str}
Current year is: {current_date.year}
Current month is: {current_date.month}

Return ONLY valid JSON (no other text):

{{
  "valid": true or false,
  "start_date": "YYYY-MM-DD" or null,
  "end_date": "YYYY-MM-DD" or null,
  "has_end_date": true or false,
  "error": "error message if invalid",
  "interpretation": "brief explanation of how you interpreted the input"
}}

Interpretation rules (apply intelligently):
1. "after X days" or "in X days" → start_date = today + X days, has_end_date = false
2. "tomorrow" → start_date = tomorrow, has_end_date = false
3. "next X days" → start_date = today, end_date = today + X days, has_end_date = true
4. "X to Y" (just day numbers) → use current month, start_date = X of current month, end_date = Y of current month
5. "X/Y to A/B" → treat as MM/DD or DD/MM based on context
6. "next week" → start_date = today + 7 days
7. "this weekend" → start_date = next Saturday, end_date = next Sunday
8. Any valid date range → extract both dates
9. Single date mentioned → start_date = that date, has_end_date = false
10. Nonsense input → valid = false with helpful error

Examples:
- "after 20 days" → start_date = (today+20), has_end_date=false
- "tomorrow" → start_date = tomorrow, has_end_date=false  
- "next 2 days" → start_date = today, end_date = (today+2), has_end_date=true
- "20 to 30" → start_date = 2026-04-20, end_date = 2026-04-30
- "24 april to 30 april" → start_date = 2026-04-24, end_date = 2026-04-30
- "25/12" → start_date = 2026-12-25, has_end_date=false

Be intelligent and handle any date format the user provides.
"""

        body = {
            "model": "llama-3.3-70b-versatile",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1
        }
        
        response = requests.post(url, headers=headers, json=body, timeout=15)
        
        if response.status_code == 200:
            content = response.json()["choices"][0]["message"]["content"]
            content = re.sub(r'```json\s*', '', content)
            content = re.sub(r'```\s*', '', content)
            content = content.strip()
            result = json.loads(content)
            print(f"📅 LLM date extraction: {result}")
            return result
        
        return {"valid": False, "error": "Technical error, please try again", "has_end_date": False}
        
    except Exception as e:
        print(f"❌ LLM date extraction error: {e}")
        return {"valid": False, "error": "Please provide your travel dates", "has_end_date": False}


def extract_travelers_llm(user_input):
    """Extract adults and children count using LLM"""
    try:
        url = "https://api.groq.com/openai/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "Content-Type": "application/json"
        }
        
        prompt = f"""
Extract number of travelers from: "{user_input}"

Return ONLY valid JSON (no other text):

{{
  "valid": true or false,
  "adults": number or null,
  "children": number or null,
  "has_children": true or false,
  "error": "error message if invalid",
  "interpretation": "how you interpreted the input"
}}

Rules:
- If user says "2 people" or "2 persons" → adults=2, children=null, has_children=false
- If user says "2 adults" → adults=2, children=null, has_children=false
- If user says "2 adults and 1 child" → adults=2, children=1, has_children=true
- If user says "2 adults 1 child" → adults=2, children=1, has_children=true
- If user says "2,1" → adults=2, children=1, has_children=true
- If user says "4" → adults=4, children=null, has_children=false
- If user says "couple" → adults=2, children=null, has_children=false
- Children ONLY appear if explicitly mentioned with words like "child", "kid", "children", or a second number

Examples:
- "2 people" → {{"valid": true, "adults": 2, "children": null, "has_children": false}}
- "4 adults" → {{"valid": true, "adults": 4, "children": null, "has_children": false}}
- "2 adults 1 child" → {{"valid": true, "adults": 2, "children": 1, "has_children": true}}
- "3 and 2" → {{"valid": true, "adults": 3, "children": 2, "has_children": true}}
- "couple" → {{"valid": true, "adults": 2, "children": null, "has_children": false}}
"""

        body = {
            "model": "llama-3.3-70b-versatile",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1
        }
        
        response = requests.post(url, headers=headers, json=body, timeout=15)
        
        if response.status_code == 200:
            content = response.json()["choices"][0]["message"]["content"]
            content = re.sub(r'```json\s*', '', content)
            content = re.sub(r'```\s*', '', content)
            content = content.strip()
            result = json.loads(content)
            print(f"👥 LLM travelers extraction: {result}")
            return result
        
        return {"valid": False, "error": "Please tell me how many people are traveling"}
        
    except Exception as e:
        print(f"❌ LLM travelers extraction error: {e}")
        return {"valid": False, "error": "Please tell me the number of travelers"}


def extract_destinations_llm(user_input, available_locations=None):
    """Extract ONLY the destinations user mentions - NO ADDING EXTRA LOCATIONS"""
    try:
        url = "https://api.groq.com/openai/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "Content-Type": "application/json"
        }
        
        locations_context = ""
        if available_locations:
            locations_list = list(available_locations)[:30]
            locations_context = f"\nAvailable destinations in our packages: {', '.join(locations_list)}"
        
        prompt = f"""
Extract ONLY the destinations/locations the user explicitly mentioned in: "{user_input}"{locations_context}

CRITICAL RULES:
- ONLY extract what the user SAID, DO NOT add any extra locations
- If user says "Spiti", return ONLY ["Spiti"] - DO NOT add Shimla, Manali, or any other location
- If user says "Goa", return ONLY ["Goa"]
- If user says "Shimla and Manali", return ["Shimla", "Manali"]
- If user says "Shimla, Manali, Goa", return ["Shimla", "Manali", "Goa"]
- If user says "Spiti trip", return ["Spiti"]
- If user says "I want to go to Spiti", return ["Spiti"]
- DO NOT assume or add any locations the user didn't mention

Return ONLY valid JSON (no other text):

{{
  "valid": true or false,
  "destinations": ["list", "of", "destinations", "user", "mentioned"] or null,
  "error": "error message if invalid",
  "interpretation": "what the user said"
}}

Examples:
- "Spiti" → {{"valid": true, "destinations": ["Spiti"], "interpretation": "user said Spiti only"}}
- "Goa trip" → {{"valid": true, "destinations": ["Goa"], "interpretation": "user said Goa"}}
- "Shimla and Manali" → {{"valid": true, "destinations": ["Shimla", "Manali"], "interpretation": "user said both"}}
- "I love Spiti" → {{"valid": true, "destinations": ["Spiti"], "interpretation": "user mentioned Spiti"}}
"""

        body = {
            "model": "llama-3.3-70b-versatile",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1
        }
        
        response = requests.post(url, headers=headers, json=body, timeout=15)
        
        if response.status_code == 200:
            content = response.json()["choices"][0]["message"]["content"]
            content = re.sub(r'```json\s*', '', content)
            content = re.sub(r'```\s*', '', content)
            content = content.strip()
            result = json.loads(content)
            print(f"📍 LLM destinations extraction: {result}")
            return result
        
        return {"valid": False, "destinations": None, "error": "Could not extract destinations"}
        
    except Exception as e:
        print(f"❌ LLM destinations extraction error: {e}")
        return {"valid": False, "destinations": None, "error": str(e)}


def generate_followup_questions(package):
    """Generate followup option buttons for a package"""
    buttons = []
    
    if package.get("itinerary"):
        buttons.append({"text": "📅 Itinerary", "value": "followup_itinerary"})
        buttons.append({"text": "🏨 Hotels", "value": "followup_hotels"})
    
    if package.get("activities"):
        buttons.append({"text": "🎯 Activities", "value": "followup_activities"})
    
    if package.get("vehicles"):
        buttons.append({"text": "🚗 Vehicles", "value": "followup_vehicles"})
    
    if package.get("inclusion"):
        buttons.append({"text": "✅ Inclusions", "value": "followup_inclusions"})
    
    if package.get("exclusion"):
        buttons.append({"text": "❌ Exclusions", "value": "followup_exclusions"})
    
    buttons.append({"text": "✅ Book Now", "value": "book_package"})
    buttons.append({"text": "📄 Download PDF", "value": f"download_pdf_{package.get('id')}"})
    buttons.append({"text": "🔙 Back to Packages", "value": "back_to_packages"})
    
    return buttons


def generate_activities_list(package):
    activities = package.get("activities", [])
    if not activities:
        return f"'{_clean(package.get('package_name'))}' has no activities listed."
    
    lines = "\n".join(f"• {act}" for act in activities)
    return f"🎯 *Activities in '{_clean(package.get('package_name'))}'*:\n\n{lines}"


def generate_vehicles_list(package):
    vehicles = package.get("vehicles", [])
    if not vehicles:
        return f"'{_clean(package.get('package_name'))}' has no vehicles listed."
    
    lines = "\n".join(f"• {veh}" for veh in vehicles)
    return f"🚗 *Vehicles in '{_clean(package.get('package_name'))}'*:\n\n{lines}"


def generate_inclusions_list(package):
    inclusions = package.get("inclusion", [])
    if not inclusions:
        return f"'{_clean(package.get('package_name'))}' has no inclusions listed."
    
    lines = "\n".join(f"✅ {inc}" for inc in inclusions)
    return f"*Inclusions in '{_clean(package.get('package_name'))}'*:\n\n{lines}"


def generate_exclusions_list(package):
    exclusions = package.get("exclusion", [])
    if not exclusions:
        return f"'{_clean(package.get('package_name'))}' has no exclusions listed."
    
    lines = "\n".join(f"❌ {exc}" for exc in exclusions)
    return f"*Exclusions in '{_clean(package.get('package_name'))}'*:\n\n{lines}"


def generate_hotels_list(package):
    itinerary = package.get("itinerary", [])
    hotels = []
    
    for day in itinerary:
        hotel = day.get('hotel')
        if hotel:
            hotel = _clean(hotel)
            if hotel not in hotels:
                hotels.append(hotel)
    
    if not hotels:
        return f"'{_clean(package.get('package_name'))}' has no hotels listed."
    
    lines = "\n".join(f"🏨 {hotel}" for hotel in hotels)
    return f"*Hotels in '{_clean(package.get('package_name'))}'*:\n\n{lines}"


def generate_itinerary_list(package):
    itinerary = package.get("itinerary", [])
    if not itinerary:
        return f"'{_clean(package.get('package_name'))}' has no itinerary listed."
    
    reply = f"📅 *Itinerary for '{_clean(package.get('package_name'))}'*:\n\n"
    
    for i, day in enumerate(itinerary, 1):
        title = day.get('title', f'Day {i}')
        description = _clean(re.sub(r'<[^>]+>', '', day.get('description', '')))
        hotel = _clean(day.get('hotel', ''))
        
        reply += f"*Day {i}: {title}*\n"
        if description:
            reply += f"   📍 {description}\n"
        if hotel:
            reply += f"   🏨 Hotel: {hotel}\n"
        reply += "\n"
    
    return reply.strip()


def _clean(text):
    """Clean HTML entities from text"""
    if not text:
        return ""
    text = str(text)
    text = re.sub(r'&amp;', '&', text)
    text = re.sub(r'&#8211;', '-', text)
    text = re.sub(r'&#8217;', "'", text)
    text = re.sub(r'&#8220;', '"', text)
    text = re.sub(r'&#8221;', '"', text)
    text = re.sub(r'<[^>]+>', '', text)
    return text.strip()


def _default_intent():
    """Return safe default intent"""
    return {
        "intent": "requirement_answer",
        "requirement_type": None,
        "requirement_value": None,
        "price": "any",
        "locations": None,
        "package_name": None,
        "followup_type": None,
        "chitchat_reply": None,
        "is_complete": False
    }

