# from services.api import fetch_packages
# from services.llm import (
#     understand_user,
#     generate_package_details_for_display,
#     generate_followup_questions,
#     generate_activities_list,
#     generate_vehicles_list,
#     generate_inclusions_list,
#     generate_hotels_list,
#     generate_itinerary_list
# )

# import os
# from dotenv import load_dotenv
# load_dotenv('.env')
# OWNER_PHONE=os.getenv('OWNER_PHONE')
 

# def process_message(user_input, phone, state):
#     """Main conversational bot function"""
    
#     if not user_input or not user_input.strip():
#         return {"type": "text", "content": "Please type something 😊"}
    
#     user_lower = user_input.lower()
#     current_step = state.get("step", "greeting")
#     context = state.get("context", {})
    
    
#     if user_input.startswith("pkg_"):
#         package_id = int(user_input.split("_")[1])
#         packages = state.get("packages", [])
        
         
#         selected_package = None
#         for pkg in packages:
#             if pkg.get("id") == package_id:
#                 selected_package = pkg
#                 break
        
#         if selected_package:
            
#             details = generate_package_details_for_display(selected_package)
#             followups = generate_followup_questions(selected_package)
            
#             return {
#                 "type": "buttons",
#                 "content": details,
#                 "buttons": followups,
#                 "new_state": {
#                     "step": "package_details",
#                     "context": {"selected_package": selected_package}
#                 }
#             }
    
     
#     if user_input.startswith("followup_"):
#         followup_type = user_input.split("_")[1]
#         selected_package = context.get("selected_package", {})
        
#         if followup_type == "activities":
#             reply = generate_activities_list(selected_package)
#             return {
#                 "type": "buttons",
#                 "content": reply,
#                 "buttons": [
#                     {"text": "🏨 Hotels", "value": "followup_hotels"},
#                     {"text": "🚗 Vehicles", "value": "followup_vehicles"},
#                     {"text": "✅ Inclusions", "value": "followup_inclusions"},
#                     {"text": "📅 Itinerary", "value": "followup_itinerary"},
#                     {"text": "🔙 Back to Packages", "value": "back_to_packages"}
#                 ]
#             }
        
#         elif followup_type == "hotels":
#             reply = generate_hotels_list(selected_package)
#             return {
#                 "type": "buttons",
#                 "content": reply,
#                 "buttons": [
#                     {"text": "🎯 Activities", "value": "followup_activities"},
#                     {"text": "🚗 Vehicles", "value": "followup_vehicles"},
#                     {"text": "✅ Inclusions", "value": "followup_inclusions"},
#                     {"text": "📅 Itinerary", "value": "followup_itinerary"},
#                     {"text": "🔙 Back to Packages", "value": "back_to_packages"}
#                 ]
#             }
        
#         elif followup_type == "vehicles":
#             reply = generate_vehicles_list(selected_package)
#             return {
#                 "type": "buttons",
#                 "content": reply,
#                 "buttons": [
#                     {"text": "🎯 Activities", "value": "followup_activities"},
#                     {"text": "🏨 Hotels", "value": "followup_hotels"},
#                     {"text": "✅ Inclusions", "value": "followup_inclusions"},
#                     {"text": "📅 Itinerary", "value": "followup_itinerary"},
#                     {"text": "🔙 Back to Packages", "value": "back_to_packages"}
#                 ]
#             }
        
#         elif followup_type == "inclusions":
#             reply = generate_inclusions_list(selected_package)
#             return {
#                 "type": "buttons",
#                 "content": reply,
#                 "buttons": [
#                     {"text": "🎯 Activities", "value": "followup_activities"},
#                     {"text": "🏨 Hotels", "value": "followup_hotels"},
#                     {"text": "🚗 Vehicles", "value": "followup_vehicles"},
#                     {"text": "📅 Itinerary", "value": "followup_itinerary"},
#                     {"text": "🔙 Back to Packages", "value": "back_to_packages"}
#                 ]
#             }
        
#         elif followup_type == "itinerary":
#             reply = generate_itinerary_list(selected_package)
#             return {
#                 "type": "buttons",
#                 "content": reply,
#                 "buttons": [
#                     {"text": "🎯 Activities", "value": "followup_activities"},
#                     {"text": "🏨 Hotels", "value": "followup_hotels"},
#                     {"text": "🚗 Vehicles", "value": "followup_vehicles"},
#                     {"text": "✅ Inclusions", "value": "followup_inclusions"},
#                     {"text": "🔙 Back to Packages", "value": "back_to_packages"}
#                 ]
#             }
    
    
#     if user_input == "back_to_packages":
#         packages = state.get("packages", [])
#         if packages:
#             return show_packages_with_buttons(packages, "Here are the packages again:")
    
     
#     packages = fetch_packages(OWNER_PHONE)
    
#     if not packages:
#         return {"type": "text", "content": "⚠️ No packages available right now. Please try again later."}
    
     
#     if current_step == "greeting" or user_lower in ["hi", "hello", "hey", "namaste", "hii"]:
#         return {
#             "type": "buttons",
#             "content": "👋 Hi there! I'm your travel assistant. How can I help you with your travel journey today?",
#             "buttons": [
#                 {"text": "📍 Find by Location", "value": "find_by_location"},
#                 {"text": "💰 Find by Budget", "value": "find_by_budget"},
#                 {"text": "🎯 Find by Activity", "value": "find_by_activity"},
#                 {"text": "📦 Show All Packages", "value": "show_all"}
#             ],
#             "new_state": {"step": "main_menu", "context": {"packages": packages}}
#         }
    
     
#     if user_input == "find_by_location":
#         return {
#             "type": "text",
#             "content": "📍 Great! Which location are you interested in?\n\n(Example: Shimla, Manali, Goa, Kerala, etc.)",
#             "new_state": {"step": "asking_location"}
#         }
    
#     if user_input == "find_by_budget":
#         return {
#             "type": "text",
#             "content": "💰 What's your budget range?\n\n(Example: under 10000, between 10000-20000, lowest price, highest price)",
#             "new_state": {"step": "asking_budget"}
#         }
    
#     if user_input == "find_by_activity":
#         return {
#             "type": "text",
#             "content": "🎯 What activities are you interested in?\n\n(Example: camping, helicopter, trekking, rafting)",
#             "new_state": {"step": "asking_activity"}
#         }
    
#     if user_input == "show_all":
#         return show_packages_with_buttons(packages, "📦 Here are all our packages:")
    
    
#     if current_step == "asking_location":
#         location = user_input.strip()
#         filtered = [p for p in packages if any(location.lower() in loc.lower() for loc in p.get("locations", []))]
        
#         if filtered:
#             return show_packages_with_buttons(filtered, f"📍 Here are packages in {location}:")
#         else:
#             return {
#                 "type": "buttons",
#                 "content": f"😔 Sorry, no packages found in {location}. Would you like to try another location or see all packages?",
#                 "buttons": [
#                     {"text": "📍 Try Another Location", "value": "find_by_location"},
#                     {"text": "📦 Show All Packages", "value": "show_all"},
#                     {"text": "🏠 Main Menu", "value": "main_menu"}
#                 ],
#                 "new_state": {"step": "main_menu"}
#             }
    
    
#     if current_step == "asking_budget":
#         user_lower = user_input.lower()
        
#         if "highest" in user_lower or "expensive" in user_lower:
#             filtered = sorted(packages, key=lambda x: int(x.get("package_price", 0)), reverse=True)[:5]
#             return show_packages_with_buttons(filtered, "💎 Here are our premium packages (highest price):")
        
#         elif "lowest" in user_lower or "cheapest" in user_lower or "under" in user_lower:
#             filtered = sorted(packages, key=lambda x: int(x.get("package_price", 0)))[:5]
#             return show_packages_with_buttons(filtered, "💰 Here are our budget-friendly packages:")
        
#         else:
            
#             import re
#             numbers = re.findall(r'\d+', user_input)
#             if numbers:
#                 budget = int(numbers[0])
#                 filtered = [p for p in packages if int(p.get("package_price", 0)) <= budget]
#                 if filtered:
#                     return show_packages_with_buttons(filtered, f"💰 Here are packages under ₹{budget}:")
#                 else:
#                     return {
#                         "type": "buttons",
#                         "content": f"😔 No packages found under ₹{budget}. Try a higher budget or see all packages?",
#                         "buttons": [
#                             {"text": "💰 Try Higher Budget", "value": "find_by_budget"},
#                             {"text": "📦 Show All Packages", "value": "show_all"},
#                             {"text": "🏠 Main Menu", "value": "main_menu"}
#                         ],
#                         "new_state": {"step": "main_menu"}
#                     }
#             else:
#                 return {
#                     "type": "text",
#                     "content": "Please tell me your budget (e.g., under 15000, lowest price, highest price)",
#                     "new_state": {"step": "asking_budget"}
#                 }
    
    
#     if current_step == "asking_activity":
#         activity = user_input.lower()
#         filtered = [p for p in packages if any(activity in a.lower() for a in p.get("activities", []))]
        
#         if filtered:
#             return show_packages_with_buttons(filtered, f"🎯 Here are packages with {activity} activities:")
#         else:
#             return {
#                 "type": "buttons",
#                 "content": f"😔 Sorry, no packages found with {activity}. Try another activity or see all packages?",
#                 "buttons": [
#                     {"text": "🎯 Try Another Activity", "value": "find_by_activity"},
#                     {"text": "📦 Show All Packages", "value": "show_all"},
#                     {"text": "🏠 Main Menu", "value": "main_menu"}
#                 ],
#                 "new_state": {"step": "main_menu"}
#             }
    
     
#     if user_input == "main_menu":
#         return {
#             "type": "buttons",
#             "content": "🏠 Main Menu - How can I help you?",
#             "buttons": [
#                 {"text": "📍 Find by Location", "value": "find_by_location"},
#                 {"text": "💰 Find by Budget", "value": "find_by_budget"},
#                 {"text": "🎯 Find by Activity", "value": "find_by_activity"},
#                 {"text": "📦 Show All Packages", "value": "show_all"}
#             ],
#             "new_state": {"step": "main_menu", "context": {"packages": packages}}
#         }
    
     
#     return show_packages_with_buttons(packages[:5], "📦 Here are some packages for you:")

# def show_packages_with_buttons(packages, message):
#     """Display packages as clickable buttons"""
#     if not packages:
#         return {
#             "type": "text",
#             "content": "No packages found 😅",
#             "buttons": []
#         }
    
#     buttons = []
#     for pkg in packages[:6]:   
#         name = pkg.get('package_name', 'Package')
#         price = pkg.get('package_price', '?')
         
#         if len(name) > 30:
#             name = name[:27] + "..."
#         buttons.append({
#             "text": f"📦 {name} - ₹{price}",
#             "value": f"pkg_{pkg.get('id')}"
#         })
    
     
#     buttons.append({"text": "🏠 Main Menu", "value": "main_menu"})
    
#     print(f"🔘 Created {len(buttons)} buttons for {len(packages)} packages")   
    
#     return {
#         "type": "buttons",
#         "content": message,
#         "buttons": buttons,
#         "new_state": {"packages": packages, "step": "showing_packages"}
#     }




"""
bot.py - Travel Bot with Step-by-Step User Questioning Flow
"""

from services.api import fetch_packages
from services.llm import (
    understand_user,
    generate_package_details_for_display,
    generate_followup_questions,
    generate_activities_list,
    generate_vehicles_list,
    generate_inclusions_list,
    generate_exclusions_list,
    generate_hotels_list,
    generate_itinerary_list,
    generate_full_package_details,
    _clean
)

import os
import re
from dotenv import load_dotenv

load_dotenv('.env')
OWNER_PHONE = os.getenv('OWNER_PHONE')
AGENT_PHONE = os.getenv('AGENT_PHONE')  # Chief executive WhatsApp number


# ══════════════════════════════════════════════════════════════
# MAIN ENTRY POINT
# ══════════════════════════════════════════════════════════════

def process_message(user_input, phone, state):
    """Main bot function - routes message to correct handler"""

    if not user_input or not user_input.strip():
        return {"type": "text", "content": "Please type something 😊"}

    context = state.get("context", {})
    step = state.get("step", "greeting")

    # ── Button callbacks (never go to LLM) ──────────────────
    if user_input.startswith("pkg_"):
        return _handle_package_select(user_input, state)

    if user_input.startswith("followup_"):
        followup_type = user_input.replace("followup_", "")
        selected_package = context.get("selected_package")
        if not selected_package:
            return {"type": "text", "content": "❌ Please select a package first."}
        return _handle_followup(followup_type, selected_package, state)

    if user_input == "back_to_packages":
        packages = state.get("packages", [])
        if packages:
            return _show_packages(packages[:6], "📦 Here are the matching packages:", state)
        return {"type": "text", "content": "No packages found. Please start a new search."}

    if user_input == "main_menu":
        return _main_menu(context)

    if user_input == "start_search":
        return _ask_travel_dates(state)

    if user_input == "close_chat":
        return _handle_close_chat(state)

    if user_input == "cheapest":
        packages = _fetch_and_cache(state)
        sorted_pkgs = sorted(packages, key=lambda x: int(x.get("package_price", 0)))
        return _show_packages(sorted_pkgs[:6], "💰 *Cheapest Packages:*", state)

    if user_input == "premium":
        packages = _fetch_and_cache(state)
        sorted_pkgs = sorted(packages, key=lambda x: int(x.get("package_price", 0)), reverse=True)
        return _show_packages(sorted_pkgs[:6], "💎 *Premium Packages:*", state)

    if user_input == "show_all":
        packages = _fetch_and_cache(state)
        return _show_packages(packages[:6], f"📦 *All Packages ({len(packages)} total):*", state)

    # ── Step-by-step questioning flow ───────────────────────
    if step == "asking_dates":
        return _save_dates_ask_pickup(user_input, state)

    if step == "asking_pickup":
        return _save_pickup_ask_pax(user_input, state)

    if step == "asking_pax":
        return _save_pax_ask_destination(user_input, state)

    if step == "asking_destination":
        return _save_destination_ask_days(user_input, state)

    if step == "asking_days":
        return _save_days_show_packages(user_input, state)

    # ── LLM intent understanding ─────────────────────────────
    try:
        intent_data = understand_user(user_input)
    except Exception as e:
        print(f"❌ LLM error: {e}")
        intent_data = {"intent": "chitchat", "chitchat_reply": "Something went wrong 😅 Try again!"}

    intent = intent_data.get("intent", "chitchat")
    chitchat_reply = intent_data.get("chitchat_reply")

    # ── Greeting ─────────────────────────────────────────────
    if intent == "greeting":
        return {
            "type": "buttons",
            "content": (
                "👋 *Hello! I'm your Travel Assistant* 🌍\n\n"
                "I'm here to help you find the perfect travel package!\n\n"
                "What would you like to do today?"
            ),
            "buttons": _menu_buttons(),
            "new_state": {"step": "main_menu", "context": context}
        }

    # ── Search / Package request → start questioning ─────────
    if intent == "search":
        return _ask_travel_dates(state)

    # ── Followup on selected package ─────────────────────────
    followup_type = intent_data.get("followup_type")
    if intent == "followup" and followup_type:
        selected_package = context.get("selected_package")
        if selected_package:
            return _handle_followup(followup_type, selected_package, state)
        return _ask_travel_dates(state)

    # ── Chitchat / unclear ───────────────────────────────────
    reply = chitchat_reply or "Not sure what you meant 😊 Use the menu below!"
    return {
        "type": "buttons",
        "content": reply,
        "buttons": _menu_buttons()
    }


# ══════════════════════════════════════════════════════════════
# STEP-BY-STEP QUESTIONING HANDLERS
# ══════════════════════════════════════════════════════════════

def _ask_travel_dates(state):
    """STEP 1: Ask for travel dates"""
    context = state.get("context", {})
    return {
        "type": "text",
        "content": (
            "✈️ Great! Let's find the perfect package for you.\n\n"
            "📅 *Step 1 of 5*\n\n"
            "What are your *travel dates*?\n\n"
            "Please share your start and end dates.\n"
            "_(Example: 15 May to 20 May 2026)_"
        ),
        "new_state": {"step": "asking_dates", "context": context}
    }


def _save_dates_ask_pickup(user_input, state):
    """Save dates → STEP 2: Ask pickup & drop"""
    context = state.get("context", {})
    context["travel_dates"] = user_input.strip()

    return {
        "type": "text",
        "content": (
            "✅ Got your dates!\n\n"
            "📍 *Step 2 of 5*\n\n"
            "Where would you like your *pickup and drop* points to be?\n\n"
            "_(Example: Pickup from Shimla Bus Stand, Drop at Chandigarh Airport)_"
        ),
        "new_state": {"step": "asking_pickup", "context": context}
    }


def _save_pickup_ask_pax(user_input, state):
    """Save pickup → STEP 3: Ask adults & children"""
    context = state.get("context", {})
    context["pickup_drop"] = user_input.strip()

    return {
        "type": "text",
        "content": (
            "✅ Pickup & drop noted!\n\n"
            "👨‍👩‍👧‍👦 *Step 3 of 5*\n\n"
            "How many *adults and children* will be travelling?\n\n"
            "_(Example: 2 adults, 1 child)_"
        ),
        "new_state": {"step": "asking_pax", "context": context}
    }


def _save_pax_ask_destination(user_input, state):
    """Save pax → STEP 4: Ask destination"""
    context = state.get("context", {})
    context["travellers"] = user_input.strip()

    return {
        "type": "text",
        "content": (
            "✅ Travellers noted!\n\n"
            "🗺️ *Step 4 of 5*\n\n"
            "Which *destination* would you like to visit?\n\n"
            "_(Example: Manali, Shimla, Goa, Kashmir, Ladakh, Meghalaya...)_"
        ),
        "new_state": {"step": "asking_destination", "context": context}
    }


def _save_destination_ask_days(user_input, state):
    """Save destination → STEP 5: Ask number of days"""
    context = state.get("context", {})
    context["destination"] = user_input.strip()

    return {
        "type": "text",
        "content": (
            "✅ Destination noted!\n\n"
            "🌙 *Step 5 of 5*\n\n"
            "How many *days* are you planning to travel?\n\n"
            "_(Example: 5 days, 7 nights...)_"
        ),
        "new_state": {"step": "asking_days", "context": context}
    }


def _save_days_show_packages(user_input, state):
    """Save days → Fetch & show matching packages"""
    context = state.get("context", {})
    context["travel_days"] = user_input.strip()

    destination = context.get("destination", "")
    dates = context.get("travel_dates", "")
    pickup = context.get("pickup_drop", "")
    pax = context.get("travellers", "")
    days = context.get("travel_days", "")

    # Fetch all packages
    packages = _fetch_and_cache(state)

    # Filter by destination (search in name, locations, description)
    filtered = packages
    if destination:
        keywords = destination.lower().split()
        dest_filtered = [
            p for p in packages
            if any(
                kw in p.get("package_name", "").lower()
                or any(kw in str(loc).lower() for loc in p.get("locations", []))
                or kw in p.get("package_description", "").lower()
                for kw in keywords
            )
        ]
        if dest_filtered:
            filtered = dest_filtered

    # Sort by price (default)
    filtered = sorted(filtered, key=lambda x: int(x.get("package_price", 0)))

    # Save search context
    state["context"] = context
    state["packages"] = packages
    state["filtered_packages"] = filtered

    summary = (
        f"🎉 *Great! Here's your travel summary:*\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📅 Dates: {dates}\n"
        f"📍 Pickup/Drop: {pickup}\n"
        f"👨‍👩‍👧‍👦 Travellers: {pax}\n"
        f"🗺️ Destination: {destination}\n"
        f"🌙 Duration: {days}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
    )

    if not filtered:
        return {
            "type": "buttons",
            "content": (
                summary +
                f"😔 No packages found for *{destination}*.\n\n"
                "Here are all available packages:"
            ),
            "buttons": _menu_buttons(),
            "new_state": {"step": "showing_packages", "context": context}
        }

    count = len(filtered)
    message = summary + f"📦 *Found {count} package{'s' if count != 1 else ''} for {destination}:*\n\nSelect a package to see full details 👇"

    return _show_packages(filtered[:6], message, state)


# ══════════════════════════════════════════════════════════════
# PACKAGE SELECTION & FOLLOWUP
# ══════════════════════════════════════════════════════════════

def _handle_package_select(user_input, state):
    """Handle when user taps a package button → show full details"""
    try:
        package_id = int(user_input.split("_")[1])
    except (IndexError, ValueError):
        return {"type": "text", "content": "Invalid package selection."}

    packages = state.get("packages", [])
    selected = next((p for p in packages if p.get("id") == package_id), None)

    if not selected:
        return {"type": "text", "content": "Package not found. Please search again."}

    context = state.get("context", {})
    new_context = {**context, "selected_package": selected}

    # Show full details + followup buttons + close chat
    content = generate_full_package_details_for_chat(selected, context)

    buttons = generate_followup_questions(selected)
    # Add close chat button
    buttons.append({"text": "❌ Close Chat", "value": "close_chat"})

    return {
        "type": "buttons",
        "content": content,
        "buttons": buttons,
        "new_state": {
            "step": "package_details",
            "context": new_context
        }
    }


def _handle_followup(followup_type, selected_package, state):
    """Handle followup detail request for a selected package"""
    handlers = {
        "itinerary":  generate_itinerary_list,
        "hotels":     generate_hotels_list,
        "activities": generate_activities_list,
        "vehicles":   generate_vehicles_list,
        "inclusions": generate_inclusions_list,
        "exclusions": generate_exclusions_list,
    }

    handler = handlers.get(followup_type)
    reply = handler(selected_package) if handler else "❓ Unknown option."

    context = state.get("context", {})
    buttons = generate_followup_questions(selected_package)
    buttons.append({"text": "❌ Close Chat", "value": "close_chat"})

    return {
        "type": "buttons",
        "content": reply,
        "buttons": buttons,
        "new_state": {
            "step": "package_details",
            "context": {**context, "selected_package": selected_package}
        }
    }


# ══════════════════════════════════════════════════════════════
# CLOSE CHAT → NOTIFY AGENT
# ══════════════════════════════════════════════════════════════

def _handle_close_chat(state):
    """
    Close chat:
    1. Collect all user info from context
    2. Send summary to agent (chief executive)
    3. Clear user history
    4. Show farewell message
    """
    context = state.get("context", {})
    selected_package = context.get("selected_package", {})
    user_phone = state.get("user_phone", "Unknown")

    # Build agent notification message
    pkg_name = _clean(selected_package.get("package_name", "Not selected")) if selected_package else "Not selected"
    pkg_price = selected_package.get("package_price", "N/A") if selected_package else "N/A"

    agent_message = (
        f"🔔 *NEW TRAVEL INQUIRY*\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📱 *Customer Phone:* {user_phone}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📅 *Travel Dates:* {context.get('travel_dates', 'Not provided')}\n"
        f"📍 *Pickup/Drop:* {context.get('pickup_drop', 'Not provided')}\n"
        f"👨‍👩‍👧‍👦 *Travellers:* {context.get('travellers', 'Not provided')}\n"
        f"🗺️ *Destination:* {context.get('destination', 'Not provided')}\n"
        f"🌙 *Duration:* {context.get('travel_days', 'Not provided')}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📦 *Selected Package:* {pkg_name}\n"
        f"💰 *Package Price:* ₹{pkg_price}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"⚡ Please contact the customer soon!"
    )

    # Send to agent via WhatsApp (imported in webhook/message_handler)
    # We return this as a special response type that the caller will handle
    state["agent_message"] = agent_message
    state["notify_agent"] = True

    # Clear conversation history
    state["step"] = "greeting"
    state["context"] = {}
    state["packages"] = []
    state["filtered_packages"] = []

    return {
        "type": "text",
        "content": (
            "✅ *Thank you for your interest!*\n\n"
            "🙏 Your inquiry has been received.\n\n"
            "👨‍💼 Our *Chief Executive* will contact you shortly to finalize your booking.\n\n"
            "📞 We'll reach out on this number soon!\n\n"
            "_Have a wonderful day! 🌟_"
        ),
        "notify_agent": True,
        "agent_message": agent_message,
        "new_state": {
            "step": "greeting",
            "context": {},
            "packages": []
        }
    }


# ══════════════════════════════════════════════════════════════
# PACKAGE DISPLAY HELPERS
# ══════════════════════════════════════════════════════════════

def generate_full_package_details_for_chat(package, user_context=None):
    """
    Show complete package details including itinerary, inclusions, exclusions, activities
    """
    name = _clean(package.get('package_name', 'Package'))
    price = package.get('package_price', 'N/A')
    package_type = package.get('package_type', 'Standard')
    package_category = package.get('package_category', 'Tour')
    locations = package.get('locations', [])
    activities = package.get('activities', [])
    vehicles = package.get('vehicles', [])
    inclusions = package.get('inclusion', [])
    exclusions = package.get('exclusion', [])
    itinerary = package.get('itinerary', [])

    lines = [
        f"📦 *{name}*",
        f"━━━━━━━━━━━━━━━━━━━━━━",
        f"💰 *Price:* ₹{price}",
        f"🏷️ *Type:* {package_type}",
        f"📂 *Category:* {package_category}",
        f"📍 *Destinations:* {', '.join(locations) if locations else 'Various'}",
        f"━━━━━━━━━━━━━━━━━━━━━━",
    ]

    # Itinerary
    if itinerary:
        lines.append("📅 *Itinerary:*")
        for i, day in enumerate(itinerary, 1):
            title = day.get('title', f'Day {i}')
            desc = _clean(re.sub(r'<[^>]+>', '', day.get('description', '')))
            hotel = _clean(day.get('hotel', ''))
            lines.append(f"  *Day {i}: {title}*")
            if desc:
                lines.append(f"   📍 {desc}")
            if hotel:
                lines.append(f"   🏨 {hotel}")
        lines.append("")

    # Activities
    if activities:
        lines.append("🎯 *Activities:*")
        for act in activities:
            lines.append(f"  • {act}")
        lines.append("")

    # Vehicles
    if vehicles:
        lines.append("🚗 *Vehicles:*")
        for v in vehicles:
            lines.append(f"  • {v}")
        lines.append("")

    # Inclusions
    if inclusions:
        lines.append("✅ *Inclusions:*")
        for inc in inclusions:
            lines.append(f"  • {_clean(inc)}")
        lines.append("")

    # Exclusions
    if exclusions:
        lines.append("❌ *Exclusions:*")
        for exc in exclusions:
            lines.append(f"  • {_clean(exc)}")
        lines.append("")

    lines.append("━━━━━━━━━━━━━━━━━━━━━━")
    lines.append("💬 Want more details or ready to book?")

    return "\n".join(lines)


# ══════════════════════════════════════════════════════════════
# UTILITY HELPERS
# ══════════════════════════════════════════════════════════════

def _fetch_and_cache(state):
    """Fetch packages and cache in state"""
    if state.get("packages"):
        return state["packages"]
    packages = fetch_packages(OWNER_PHONE)
    if packages:
        state["packages"] = packages
    return packages or []


def _show_packages(packages, message, state):
    """Show packages as a button list"""
    if not packages:
        return {"type": "text", "content": "No packages found 😅"}

    buttons = []
    for pkg in packages[:9]:  # WhatsApp list supports up to 10
        name = _clean(pkg.get('package_name', 'Package'))
        price = pkg.get('package_price', '?')
        display = f"{name[:22]}..." if len(name) > 22 else name
        buttons.append({
            "text": f"📦 {display} - ₹{price}",
            "value": f"pkg_{pkg.get('id')}"
        })

    buttons.append({"text": "🏠 Main Menu", "value": "main_menu"})

    context = state.get("context", {})

    return {
        "type": "buttons",
        "content": message,
        "buttons": buttons,
        "new_state": {
            "step": "showing_packages",
            "packages": state.get("packages", packages),
            "context": context
        }
    }


def _main_menu(context):
    return {
        "type": "buttons",
        "content": (
            "🏠 *Main Menu*\n\n"
            "How can I help you? Choose an option below:"
        ),
        "buttons": _menu_buttons(),
        "new_state": {"step": "main_menu", "context": context}
    }


def _menu_buttons():
    return [
        {"text": "🔍 Find My Package",       "value": "start_search"},
        {"text": "💰 Cheapest Packages",      "value": "cheapest"},
        {"text": "💎 Premium Packages",       "value": "premium"},
        {"text": "📦 All Packages",           "value": "show_all"},
    ]