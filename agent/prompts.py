"""
agent/prompts.py  –  All LLM prompt templates
"""



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
- Always return valid YYYY-MM-DD format or empty string ""

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

A user has sent a free-form travel message. Extract any travel information you can find.

Return ONLY valid JSON in this exact format — no extra text, no markdown fences:
{{
  "destination": "City name if mentioned, otherwise empty string",
  "start_date": "YYYY-MM-DD if a start/from date is mentioned, otherwise empty string",
  "end_date": "YYYY-MM-DD if an end/to date is mentioned, otherwise empty string"
}}

Rules:
- destination: extract the city/place the user wants to travel TO (not from)
- If dates mention only day numbers (e.g. "12 to 20") assume the current or next logical month
- If no destination found → ""
- If no dates found → ""
- Never invent information not present in the input

Examples:
- Input: "I'm going to Shimla from 12 to 20"
  Output: {{"destination": "Shimla", "start_date": "2026-05-12", "end_date": "2026-05-20"}}

- Input: "I want hotels in Manali 15 to 22 june"
  Output: {{"destination": "Manali", "start_date": "2026-06-15", "end_date": "2026-06-22"}}

- Input: "book a trip to Goa"
  Output: {{"destination": "Goa", "start_date": "", "end_date": ""}}

- Input: "find me hotels"
  Output: {{"destination": "", "start_date": "", "end_date": ""}}

- Input: "I need a package for 3 people"
  Output: {{"destination": "", "start_date": "", "end_date": ""}}

User input: {input}
"""


VALIDATE_CITY_PROMPT = """
You are a travel assistant with knowledge of world geography.

The user entered a city name: "{city}"

Return ONLY JSON in this format — no extra text, no markdown fences:
{{
  "is_valid": true or false,
  "corrected_name": "correctly spelled city name, or empty string if invalid",
  "country": "country name, or empty string if invalid",
  "suggestion": "suggestion for a valid city if invalid, otherwise empty string",
  "message": "friendly message explaining the correction or error"
}}

Rules:
- If the city is recognisable (even with typos/misspellings) → is_valid = true, correct the spelling
- If it is completely unrecognisable → is_valid = false
- Be smart: handle common misspellings, local names, abbreviations

Examples:
- "shimlaa" → {{"is_valid": true, "corrected_name": "Shimla", "country": "India", "suggestion": "", "message": "Did you mean Shimla?"}}
- "new yorkk" → {{"is_valid": true, "corrected_name": "New York", "country": "USA", "suggestion": "", "message": "Corrected to New York"}}
- "londn" → {{"is_valid": true, "corrected_name": "London", "country": "UK", "suggestion": "", "message": "Did you mean London?"}}
- "xyzabc" → {{"is_valid": false, "corrected_name": "", "country": "", "suggestion": "Try: Paris, London, New York, Tokyo, Dubai", "message": "I don't recognize this city name."}}
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


 

ROOM_TYPE_PROMPT = """
You are a travel assistant helping users select room types.

Available room types: {room_types}

User selected hotel: {hotel_name}

Your task:
- Present the room types in a clear, numbered list
- Ask the user to select a room type by number or name
- Be friendly and helpful

Output format (use markdown):

🏨 *{hotel_name}* - Select Room Type

Available room types:
{formatted_types}

Please reply with the room type number or name you prefer.
"""

ROOM_CATEGORY_PROMPT = """
You are a travel assistant helping users select room categories.

Available room categories for room type "{room_type}": {room_categories}

User selected:
- Hotel: {hotel_name}
- Room Type: {room_type}

Your task:
- Present the room categories in a clear, numbered list
- Include price information if available
- Ask the user to select a category by number or name

Output format (use markdown):

🏨 *{hotel_name}*
📋 Room Type: *{room_type}*

Available Room Categories:
{formatted_categories}

Please reply with the category number or name you prefer.
"""

FINAL_BOOKING_SUMMARY_PROMPT = """
You are a travel assistant. Create a final booking summary for the user.

User's complete selection:
- Hotel: {hotel_name}
- Location: {hotel_location}
- Room Type: {room_type}
- Room Category: {room_category}
- Check-in: {check_in}
- Check-out: {check_out}
- Nights: {nights}
- Guests: {guests} people
- Base Price: {base_price}
- Extra Person Price: {extra_person_price} (per night)
- Total Price: {total_price}

Create a beautiful, well-formatted summary with:
1. Hotel name and location
2. Room details (type and category)
3. Stay duration
4. Price breakdown
5. Confirmation message
6. Next steps

Use emojis and markdown formatting for better readability.
"""



# Add to your existing prompts.py file

MEAL_SELECTION_PROMPT = """
You are a travel assistant helping users select meal plans.

User's Booking Details:
- Hotel: {hotel_name}
- Room: {room_category} ({room_type})
- Check-in: {check_in}
- Check-out: {check_out}
- Nights: {nights}
- Guests: {guests} people
- Room Total: ₹{room_total}

Available Meal Plans (per person per day):

1. 🚫 No Meals - ₹0
   - Just room only, no meals included

2. 🍳 Breakfast Only - ₹500 per person/day
   - Complimentary breakfast buffet
   - 7:00 AM - 10:00 AM

3. 🍽️ Half Board - ₹1,200 per person/day
   - Breakfast + Dinner
   - Great for exploring during the day

4. 🍱 Full Board - ₹1,800 per person/day
   - Breakfast + Lunch + Dinner
   - All meals included

Meal costs will be added to your room total.

Please select a meal plan by number (1-4).
"""

FINAL_COMPLETE_SUMMARY_PROMPT = """
You are a travel assistant. Create a COMPLETE booking summary for the user including all their selections.

FULL BOOKING DETAILS:

🏨 HOTEL INFORMATION:
- Name: {hotel_name}
- Location: {hotel_location}
- Category: {hotel_category}
- Phone: {hotel_phone}
- Email: {hotel_email}

🛏️ ROOM DETAILS:
- Room Category: {room_category}
- Room Type: {room_type}
- Capacity: {min_capacity} - {max_capacity} people
- Facilities: {facilities}

📅 STAY DETAILS:
- Check-in: {check_in}
- Check-out: {check_out}
- Total Nights: {nights}
- Guests: {guests} people

💰 PRICE BREAKDOWN:
- Room Base Price: ₹{base_price}/night × {nights} nights = ₹{room_base_total}
- Extra Person Charges: ₹{extra_price}/night × {extra_people} extra × {nights} nights = ₹{extra_total}
- Room Subtotal: ₹{room_subtotal}

🍽️ MEAL PLAN:
- Selected: {meal_plan}
- Cost: ₹{meal_cost_per_person}/person/day
- Meal Total: ₹{meal_total}

💵 GRAND TOTAL: ₹{grand_total}

📞 CONTACT INFORMATION:
- Phone: {hotel_phone}
- Email: {hotel_email}

Would you like to confirm this booking?

Create a beautiful, well-formatted summary with emojis and clear sections.
"""