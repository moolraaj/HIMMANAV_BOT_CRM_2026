#agent prompts
DATE_PROMPT = """
You are a travel assistant.
 
Today is: {today}
Current month: {current_month}
Current year: {current_year}
 
Extract travel dates from user input. User may provide:
- Single date: "12", "12th", "tomorrow", "next monday"
- Two dates: "12 to 20", "12th to 20th", "12 june to 20 june", "12-20 june"
 
Return EXACTLY this JSON format:
{{
  "start_date": "YYYY-MM-DD",
  "end_date": "YYYY-MM-DD"
}}
 
Rules:
- If only one date provided → return as start_date, end_date = ""
- If two dates provided → return both
- If user says "12 to 20 june" → June 12 to June 20 of current year
- If user says "12th to 20th" → use current month
- If user says "tomorrow to next friday" → calculate based on today
- If user says nonsense like "dgfhdf" → return empty strings
 
Examples:
- Input: "12" → {{"start_date": "2026-06-12", "end_date": ""}}
- Input: "12 to 20" → {{"start_date": "2026-06-12", "end_date": "2026-06-20"}}
- Input: "12 june to 20 june" → {{"start_date": "2026-06-12", "end_date": "2026-06-20"}}
- Input: "12th to 20th" → {{"start_date": "2026-06-12", "end_date": "2026-06-20"}}
- Input: "dgfhdf" → {{"start_date": "", "end_date": ""}}
 
User input: {input}
"""
 
 
 
PARTIAL_TRIP_PROMPT = """
You are a travel assistant.
 
Today is: {today}
 
Extract travel details from user input.
 
Return ONLY JSON:
{{
  "start_date": "",
  "end_date": "",
  "destination": ""
}}
 
User input: {input}
"""
 
VALIDATE_CITY_PROMPT = """
You are a travel assistant with knowledge of world geography.
 
The user entered a city name: "{city}"
 
Return ONLY JSON in this format:
{{
  "is_valid": true/false,
  "corrected_name": "correctly spelled city name",
  "country": "country name",
  "suggestion": "suggestion for valid city if invalid, otherwise empty",
  "message": "friendly message explaining the correction or error"
}}
 
Examples:
- Input: "shimlaa" → {{"is_valid": true, "corrected_name": "Shimla", "country": "India", "suggestion": "", "message": "Did you mean Shimla?"}}
- Input: "new yorkk" → {{"is_valid": true, "corrected_name": "New York", "country": "USA", "suggestion": "", "message": "Corrected to New York"}}
- Input: "londn" → {{"is_valid": true, "corrected_name": "London", "country": "UK", "suggestion": "", "message": "Did you mean London?"}}
- Input: "xyzabc" → {{"is_valid": false, "corrected_name": "", "country": "", "suggestion": "Try: Paris, London, New York, Tokyo, Dubai", "message": "I don't recognize this city name."}}
 
Be smart and use your knowledge of world cities, common misspellings, and variations.
"""
 
HOTEL_PROMPT = """
You are a travel assistant.
 
User trip details:
- Destination: {destination}
- Check-in: {start_date}
- Check-out: {end_date}
- People: {people}
- Category: {category}
 
Your task:
- Suggest 3-5 hotels in {destination} for {category} category
- Consider the dates and number of people
- Provide real hotel names (or realistic suggestions)
- Include estimated price range
 
Output format (use markdown):
 
**Hotel 1: [Hotel Name]**
- Category: {category}
- Price: ₹X,XXX - ₹X,XXX per night
- Why recommend: [2-3 sentences about amenities, location, value]
 
**Hotel 2: [Hotel Name]**
- Category: {category}
- Price: ₹X,XXX - ₹X,XXX per night
- Why recommend: [2-3 sentences]
 
**Hotel 3: [Hotel Name]**
- Category: {category}
- Price: ₹X,XXX - ₹X,XXX per night
- Why recommend: [2-3 sentences]
 
Make it helpful, realistic, and formatted cleanly.
"""
 
CONFIRM_PROMPT = """
You are a travel assistant.
 
User details:
{data}
 
Create a short confirmation message.
 
Format:
- Show dates
- Show destination
- Ask: "Is this correct?"
 
Keep it short and friendly.
"""
 
PEOPLE_PROMPT = """
Ask the user how many people are traveling.
 
Keep it short and friendly.
"""