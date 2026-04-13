# services/llm.py
import requests
import json
import re
import os 

from dotenv import load_dotenv
load_dotenv('.env')  
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

def understand_user(user_input):
    """Simple understanding of what user wants"""
    try:
        url = "https://api.groq.com/openai/v1/chat/completions"
        
        headers = {
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "Content-Type": "application/json"
        }
        
        prompt = f"""
User message: "{user_input}"

Return ONLY this JSON format:
{{
  "intent": "greeting or search or question",
  "price": "lowest or highest or any",
  "location": "place name or null",
  "activity": "activity name or null"
}}
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
            return json.loads(content)
        
        return {"intent": "search", "price": "any", "location": None, "activity": None}
        
    except Exception as e:
        print(f"Error: {e}")
        return {"intent": "search", "price": "any", "location": None, "activity": None}

def generate_package_list_with_buttons(packages, title="📦 Packages Found"):
    """Generate package list with button data (not actual buttons)"""
    if not packages:
        return "No packages found 😅", []
    
    buttons = []
    for pkg in packages[:6]:
        buttons.append({
            "text": f"📦 {pkg.get('package_name', 'Package')[:25]} - ₹{pkg.get('package_price', '?')}",
            "value": f"pkg_{pkg.get('id')}"
        })
    
    return title, buttons

def generate_package_details_for_display(package):
    """Generate beautiful package details"""
    
    def clean_text(text):
        if text:
            return re.sub(r'&amp;', '&', text)
        return text
    
    name = package.get('package_name', 'Package')
    price = package.get('package_price', 'N/A')
    package_type = package.get('package_type', 'Standard')
    package_category = package.get('package_category', 'Tour')
    locations = package.get('locations', [])
    
    details = f"""
📦 **{name}**
━━━━━━━━━━━━━━━━━━━━━━

💰 **Price:** ₹{price}
🏷️ **Type:** {package_type}
📂 **Category:** {package_category}
📍 **Destinations:** {', '.join(locations[:3]) if locations else 'Various'}

━━━━━━━━━━━━━━━━━━━━━━

What would you like to know more about?
"""
    return details

def generate_followup_questions(package):
    """Generate followup question buttons"""
    buttons = []
    
    if package.get("activities"):
        buttons.append({"text": "🎯 Activities", "value": "followup_activities"})
    
    # Check itinerary for hotels
    if package.get("itinerary"):
        buttons.append({"text": "🏨 Hotels", "value": "followup_hotels"})
    
    if package.get("vehicles"):
        buttons.append({"text": "🚗 Vehicles", "value": "followup_vehicles"})
    
    if package.get("inclusion"):
        buttons.append({"text": "✅ Inclusions", "value": "followup_inclusions"})
    
    if package.get("itinerary"):
        buttons.append({"text": "📅 Itinerary", "value": "followup_itinerary"})
    
    buttons.append({"text": "🔙 Back to Packages", "value": "back_to_packages"})
    
    return buttons

# Additional helper functions needed
def generate_activities_list(package):
    activities = package.get("activities", [])
    if not activities:
        return f"'{package.get('package_name')}' has no activities listed."
    
    reply = f"🎯 Activities in '{package.get('package_name')}':\n\n"
    for i, act in enumerate(activities, 1):
        reply += f"{i}) {act}\n"
    return reply

def generate_vehicles_list(package):
    vehicles = package.get("vehicles", [])
    if not vehicles:
        return f"'{package.get('package_name')}' has no vehicles listed."
    
    reply = f"🚗 Vehicles in '{package.get('package_name')}':\n\n"
    for i, veh in enumerate(vehicles, 1):
        reply += f"{i}) {veh}\n"
    return reply

def generate_inclusions_list(package):
    inclusions = package.get("inclusion", [])
    if not inclusions:
        return f"'{package.get('package_name')}' has no inclusions listed."
    
    reply = f"✅ Inclusions in '{package.get('package_name')}':\n\n"
    for i, inc in enumerate(inclusions, 1):
        reply += f"{i}) {inc}\n"
    return reply

def generate_exclusions_list(package):
    exclusions = package.get("exclusion", [])
    if not exclusions:
        return f"'{package.get('package_name')}' has no exclusions listed."
    
    reply = f"❌ Exclusions in '{package.get('package_name')}':\n\n"
    for i, exc in enumerate(exclusions, 1):
        reply += f"{i}) {exc}\n"
    return reply

def generate_hotels_list(package):
    itinerary = package.get("itinerary", [])
    hotels = []
    
    for day in itinerary:
        hotel = day.get('hotel')
        if hotel and hotel not in hotels:
            hotel = re.sub(r'&amp;', '&', hotel)
            hotels.append(hotel)
    
    if not hotels:
        return f"'{package.get('package_name')}' has no hotels listed."
    
    reply = f"🏨 Hotels in '{package.get('package_name')}':\n\n"
    for i, hotel in enumerate(hotels, 1):
        reply += f"{i}) {hotel}\n"
    return reply

def generate_itinerary_list(package):
    itinerary = package.get("itinerary", [])
    if not itinerary:
        return f"'{package.get('package_name')}' has no itinerary listed."
    
    reply = f"📅 Itinerary for '{package.get('package_name')}':\n\n"
    for i, day in enumerate(itinerary, 1):
        title = day.get('title', f'Day {i}')
        description = day.get('description', '')
        description = re.sub(r'<[^>]+>', '', description)
        description = re.sub(r'&amp;', '&', description)
        hotel = day.get('hotel', '')
        if hotel:
            hotel = re.sub(r'&amp;', '&', hotel)
        
        reply += f"{i}) {title}\n"
        if description:
            reply += f"   📍 {description}\n"
        if hotel:
            reply += f"   🏨 Hotel: {hotel}\n"
        reply += "\n"
    return reply

def generate_full_package_details(package):
    def clean_text(text):
        if text:
            return re.sub(r'&amp;', '&', text)
        return text
    
    name = package.get('package_name', 'N/A')
    price = package.get('package_price', 'N/A')
    package_type = package.get('package_type', 'N/A')
    package_category = package.get('package_category', 'N/A')
    description = package.get('package_description', '')
    description = re.sub(r'<[^>]+>', '', description)
    
    locations = package.get('locations', [])
    vehicles = package.get('vehicles', [])
    activities = package.get('activities', [])
    inclusions = package.get('inclusion', [])
    exclusions = package.get('exclusion', [])
    
    hotels = []
    for day in package.get('itinerary', []):
        hotel = day.get('hotel')
        if hotel and hotel not in hotels:
            hotels.append(clean_text(hotel))
    
    reply = f"""
📦 PACKAGE DETAILS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🏷️ Name: {name}
💰 Price: ₹{price}
🏷️ Type: {package_type}
📂 Category: {package_category}

📍 Locations:
"""
    for i, loc in enumerate(locations, 1):
        reply += f"   {i}) {loc}\n"
    
    if hotels:
        reply += f"\n🏨 Hotels:\n"
        for i, hotel in enumerate(hotels, 1):
            reply += f"   {i}) {hotel}\n"
    
    if vehicles:
        reply += f"\n🚗 Vehicles:\n"
        for i, veh in enumerate(vehicles, 1):
            reply += f"   {i}) {veh}\n"
    
    if activities:
        reply += f"\n🎯 Activities:\n"
        for i, act in enumerate(activities, 1):
            reply += f"   {i}) {act}\n"
    
    if inclusions:
        reply += f"\n✅ Inclusions:\n"
        for i, inc in enumerate(inclusions, 1):
            reply += f"   {i}) {inc}\n"
    
    if exclusions:
        reply += f"\n❌ Exclusions:\n"
        for i, exc in enumerate(exclusions, 1):
            reply += f"   {i}) {exc}\n"
    
    if description:
        reply += f"\n📝 Description:\n   {description}\n"
    
    return reply

def generate_single_package_details(package):
    return f"""
📦 {package.get('package_name')}
💰 Price: ₹{package.get('package_price')}
📍 Locations: {', '.join(package.get('locations', []))}
🏷️ Type: {package.get('package_type', 'N/A')}
📂 Category: {package.get('package_category', 'N/A')}

Ask me about: activities, vehicles, hotels, inclusions, exclusions, or itinerary!
"""