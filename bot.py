# bot.py
from services.api import fetch_packages, fetch_hotels
from services.email_service import send_admin_booking_alert
from services.pdf_generator import download_pdf_from_url, send_pdf_via_whatsapp
from services.llm import (
    generate_activities_list,
    generate_vehicles_list,
    generate_inclusions_list,
    generate_exclusions_list,
    generate_hotels_list,
    generate_itinerary_list,
    extract_travel_dates_llm,
    extract_duration_llm,
    extract_travelers_llm,
    extract_destinations_llm,
    understand_user,
    _clean
)

from utils import (
    PACKAGES_PER_PAGE,
    calculate_per_person_price,
    clean_text,
    clean_itinerary_text,
    format_itinerary_for_display,
    safe_price,
    filter_packages_by_destinations,
    filter_hotels_by_destinations,
    create_summary,
    get_next_batch,
    has_more_items,
    get_remaining_count,
    build_navigation_buttons,
    validate_dates,
    validate_duration,
    create_new_state,
    create_fresh_state,
    create_exit_state
)

import os
import re
from datetime import datetime
from dotenv import load_dotenv

load_dotenv('.env')
OWNER_PHONE = os.getenv('OWNER_PHONE')


# ══════════════════════════════════════════════════════════════
# MAIN ENTRY POINT
# ══════════════════════════════════════════════════════════════

def process_message(user_input, phone, state):
    if not user_input or not user_input.strip():
        return {"type": "text", "content": "Hey there! 👋 How can I help you today?"}

    if not state.get("user_phone"):
        state["user_phone"] = phone

    context = state.get("context", {})
    step = state.get("step", "greeting")

    print(f"🔍 Step: {step}, Mode: {state.get('search_mode','package')}, Input: {user_input[:50]}")

    # ── EXIT / LOGOUT — only these break the session ───────────
    if user_input.lower() in ["exit", "logout", "end_chat", "quit"]:
        return _handle_exit_chat(state)

    # ── Package button callbacks ──────────────────────────────
    if user_input.startswith("pkg_"):
        return _handle_package_select(user_input, state)

    if user_input.startswith("followup_"):
        followup_type = user_input.replace("followup_", "")
        selected_package = context.get("selected_package")
        if not selected_package:
            return {"type": "text", "content": "Please select a package first."}
        return _handle_followup(followup_type, selected_package, state)

    # ── Hotel button callbacks ────────────────────────────────
    if user_input.startswith("hotel_"):
        return _handle_hotel_select(user_input, state)

    # ── Navigation ────────────────────────────────────────────
    if user_input == "back_to_packages":
        return _back_to_packages_handler(state)

    if user_input == "back_to_hotels":
        return _back_to_hotels_handler(state)

    if user_input == "main_menu":
        return _main_menu(state)

    if user_input == "start_search":
        state["context"] = {}
        state["step"] = "asking_dates"
        state["search_mode"] = "package"
        # Clear previous search results
        state.pop("filtered_packages", None)
        state.pop("current_page", None)
        state.pop("packages", None)
        state.pop("filtered_hotels", None)
        state.pop("hotel_page", None)
        state.pop("hotels", None)
        return _ask_travel_dates(state)

    if user_input == "start_hotel_search":
        state["search_mode"] = "hotel"
        # If all required info already in context → go directly to results
        if _context_is_complete(context):
            return _jump_to_results(state, "hotel")
        # Otherwise start fresh collection
        fresh = create_fresh_state(state)
        fresh["search_mode"] = "hotel"
        return _ask_travel_dates(fresh)

    if user_input == "load_more":
        if state.get("search_mode") == "hotel":
            return _handle_load_more_hotels(state)
        else:
            return _handle_load_more_packages(state)

    # book_package and book_hotel END the session
    if user_input == "book_package":
        return _handle_book_package(state)

    if user_input == "book_hotel":
        return _handle_book_hotel(state)

    if user_input.startswith("download_pdf_pkg_"):
        return _handle_download_pdf_package(user_input, state)

    if user_input.startswith("download_pdf_hotel_"):
        return _handle_download_pdf_hotel(user_input, state)

    # Legacy support for old download_pdf_ prefix (packages)
    if user_input.startswith("download_pdf_"):
        suffix = user_input.replace("download_pdf_", "")
        if suffix.isdigit():
            return _handle_download_pdf_package(f"download_pdf_pkg_{suffix}", state)

    # ── Step-based conversation ───────────────────────────────
    if step == "asking_dates":
        return _handle_dates_input(user_input, state)

    if step == "confirming_dates":
        return _confirm_dates(user_input, state)

    if step == "asking_duration":
        return _handle_duration_input(user_input, state)

    if step == "confirming_duration":
        return _confirm_duration(user_input, state)

    if step == "asking_pax":
        return _handle_pax_input(user_input, state)

    if step == "confirming_pax":
        return _confirm_pax(user_input, state)

    if step == "asking_destination":
        return _handle_destination_input(user_input, state)

    if step == "confirming_destination":
        return _confirm_destination_and_show_results(user_input, state)

    if step == "showing_packages":
        return _handle_showing_packages(user_input, state)

    if step == "showing_hotels":
        return _handle_showing_hotels(user_input, state)

    if step == "package_details":
        selected_package = context.get("selected_package")
        if selected_package:
            return _handle_package_question(user_input, selected_package, state)

    if step == "hotel_details":
        selected_hotel = context.get("selected_hotel")
        if selected_hotel:
            return _handle_hotel_question(user_input, selected_hotel, state)

    return _greeting_response(user_input, state)


# ══════════════════════════════════════════════════════════════
# EXIT HANDLER  — resets the entire session
# ══════════════════════════════════════════════════════════════

def _handle_exit_chat(state):
    user_phone = state.get("user_phone", "Unknown")

    agent_message = (
        f"🔔 *USER LOGGED OUT*\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📱 *Customer:* {user_phone}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"User has ended the conversation."
    )

    return {
        "type": "text",
        "content": (
            "👋  Thank you for chatting with us! 🙏\n\n"
            "✨ Feel free to come back anytime you need travel assistance!\n\n"
            "🌟 *Have a wonderful day!* 🌟"
        ),
        "notify_agent": True,
        "agent_message": agent_message,
        "new_state": create_exit_state(state)
    }


# ══════════════════════════════════════════════════════════════
# STEP 1 — TRAVEL DATES
# ══════════════════════════════════════════════════════════════

def _ask_travel_dates(state):
    context = state.get("context", {})
    mode = state.get("search_mode", "package")
    icon = "🏨" if mode == "hotel" else "📦"
    thing = "hotel" if mode == "hotel" else "travel package"

    return {
        "type": "text",
        "content": (
            f"👋 *Hello! Let\'s find you the perfect {thing}!* {icon}\n\n"
            f"📅 *When are you planning to travel?*"
        ),
        "new_state": create_new_state(state, "asking_dates", context)
    }


def _handle_dates_input(user_input, state):
    context = state.get("context", {})
    extracted = extract_travel_dates_llm(user_input)

    if not extracted.get("valid"):
        return {
            "type": "text",
            "content": (
                f"😅 _{extracted.get('error', 'I could not understand that date.')}_\n\n"
                f"📅 *Please tell me your travel dates:*"
            ),
            "new_state": create_new_state(state, "asking_dates", context)
        }

    start_date = None
    end_date = None

    try:
        if extracted.get("start_date"):
            start_date = datetime.strptime(extracted["start_date"], "%Y-%m-%d")
    except Exception:
        pass

    try:
        if extracted.get("end_date") and extracted.get("has_end_date"):
            end_date = datetime.strptime(extracted["end_date"], "%Y-%m-%d")
    except Exception:
        pass

    is_valid, error_msg = validate_dates(start_date, end_date)
    if not is_valid:
        return {
            "type": "text",
            "content": f"😅 {error_msg}\n\n📅 Please give me valid future dates.",
            "new_state": create_new_state(state, "asking_dates", context)
        }

    if end_date:
        date_display = f"{start_date.strftime('%d %B %Y')} → {end_date.strftime('%d %B %Y')}"
        context["end_date_str"] = extracted.get("end_date", "")
    else:
        date_display = f"Starting {start_date.strftime('%d %B %Y')}"

    context["travel_dates"] = date_display
    context["start_date_str"] = extracted.get("start_date", "")

    interpretation = extracted.get("interpretation", "")
    confirm_text = f"✅ Got it!\n\n📅 *Travel dates:* {date_display}"
    if interpretation:
        confirm_text += f"\n_💡 Understood as: {interpretation}_"
    confirm_text += "\n\nIs that correct?"

    return {
        "type": "buttons",
        "content": confirm_text,
        "buttons": [
            {"text": "Is this Corrent ?", "value": "confirm_dates_yes"},
            {"text": "Change dates", "value": "confirm_dates_no"}
        ],
        "new_state": create_new_state(state, "confirming_dates", context)
    }


def _confirm_dates(user_input, state):
    context = state.get("context", {})

    if user_input == "confirm_dates_yes":
        # Move to DURATION step
        return {
            "type": "text",
            "content": (
                "Perfect! 📅\n\n"
                "⏳ *How long is your tour?*\n"
                "_Maximum: 60 days / 60 nights_"
            ),
            "new_state": create_new_state(state, "asking_duration", context)
        }
    else:
        for k in ["travel_dates", "start_date_str", "end_date_str"]:
            context.pop(k, None)
        return {
            "type": "text",
            "content": "No problem! 📅 *Please tell me your travel dates:*",
            "new_state": create_new_state(state, "asking_dates", context)
        }

# ══════════════════════════════════════════════════════════════
# STEP 2 — TOUR DURATION  (NEW)
# ══════════════════════════════════════════════════════════════

def _handle_duration_input(user_input, state):
    context = state.get("context", {})
    
    # NEW: Handle "2 and 3" or "2 and 4" pattern
    import re
    match = re.search(r'(\d+)\s+and\s+(\d+)', user_input.lower())
    if match:
        days = int(match.group(1))
        nights = int(match.group(2))
        extracted = {
            "valid": True,
            "days": days,
            "nights": nights,
            "interpretation": f"{days} days and {nights} nights"
        }
    else:
        extracted = extract_duration_llm(user_input)

    if not extracted.get("valid"):
        return {
            "type": "text",
            "content": (
                f"😅 _{extracted.get('error', 'I could not understand the duration.')}_\n\n"
                f"⏳ *How long is your tour?*\n"
                f"_Example: 5 days 4 nights or 2 and 3_"
            ),
            "new_state": create_new_state(state, "asking_duration", context)
        }

    days = extracted.get("days")
    nights = extracted.get("nights")

    # Extra safety validation
    is_valid, error_msg = validate_duration(days, nights)
    if not is_valid:
        return {
            "type": "text",
            "content": (
                f"😅 _{error_msg}_\n\n"
                f"⏳ *Please tell me your tour duration:*\n"
                f"_Example: 5 days 4 nights or 2 and 3_"
            ),
            "new_state": create_new_state(state, "asking_duration", context)
        }

    # Build display text
    parts = []
    if days is not None:
        parts.append(f"{days} Day{'s' if days != 1 else ''}")
    if nights is not None:
        parts.append(f"{nights} Night{'s' if nights != 1 else ''}")
    duration_text = " / ".join(parts) if parts else "Not specified"

    context["duration_days"] = days
    context["duration_nights"] = nights
    context["duration_text"] = duration_text

    interpretation = extracted.get("interpretation", "")
    confirm_text = f"✅ Got it!\n\n⏳ *Tour Duration:* {duration_text}"
    if interpretation:
        confirm_text += f"\n_💡 Understood as: {interpretation}_"
    confirm_text += "\n\nIs that correct?"

    return {
        "type": "buttons",
        "content": confirm_text,
        "buttons": [
            {"text": "Yes, correct", "value": "confirm_duration_yes"},
            {"text": "Change duration", "value": "confirm_duration_no"}
        ],
        "new_state": create_new_state(state, "confirming_duration", context)
    }


def _confirm_duration(user_input, state):
    context = state.get("context", {})

    if user_input == "confirm_duration_yes":
        return {
            "type": "text",
            "content": "Wonderful! ⏳\n\n👥 *How many people are traveling?*",
            "new_state": create_new_state(state, "asking_pax", context)
        }
    else:
        for k in ["duration_days", "duration_nights", "duration_text"]:
            context.pop(k, None)
        return {
            "type": "text",
            "content": "No problem! ⏳ *How long is your tour?*\n_Maximum: 60 days / 60 nights_",
            "new_state": create_new_state(state, "asking_duration", context)
        }


# ══════════════════════════════════════════════════════════════
# STEP 3 — TRAVELERS
# ══════════════════════════════════════════════════════════════

def _handle_pax_input(user_input, state):
    context = state.get("context", {})
    
    import re
    
    # NEW: Handle "X and Y" pattern for adults and children
    match_and = re.search(r'(\d+)\s+and\s+(\d+)', user_input.lower())
    if match_and:
        adults = int(match_and.group(1))
        children = int(match_and.group(2))
        extracted = {
            "valid": True,
            "adults": adults,
            "children": children,
            "has_children": children > 0,
            "interpretation": f"{adults} adults and {children} children"
        }
    # NEW: Handle "X or Y" pattern - ask for clarification
    elif re.search(r'(\d+)\s+or\s+(\d+)', user_input.lower()):
        return {
            "type": "text",
            "content": (
                f"😊 I see you're not sure between two numbers.\n\n"
                f"👥 *Please tell me the EXACT number of travelers.*\n\n"
                f"_Example: 4 adults or 2 adults and 2 children_"
            ),
            "new_state": create_new_state(state, "asking_pax", context)
        }
    # Handle "X,X" pattern (comma separated)
    elif re.search(r'(\d+)\s*,\s*(\d+)', user_input.lower()):
        match_comma = re.search(r'(\d+)\s*,\s*(\d+)', user_input.lower())
        adults = int(match_comma.group(1))
        children = int(match_comma.group(2))
        extracted = {
            "valid": True,
            "adults": adults,
            "children": children,
            "has_children": children > 0,
            "interpretation": f"{adults} adults and {children} children"
        }
    else:
        # Use existing LLM function
        extracted = extract_travelers_llm(user_input)

    ambiguous_patterns = [
        r'\bor\b', r'\bmaybe\b', r'\bprobably\b', r'\baround\b',
        r'\bapproximately\b', r'\bperhaps\b', r'\bnot sure\b', r'\bsome\b'
    ]
    
    # Check for "or" specifically
    if re.search(r'\d+\s+or\s+\d+', user_input.lower()):
        return {
            "type": "text",
            "content": "😊 Please give me the *exact number* of travelers (no 'or' or 'maybe').",
            "new_state": create_new_state(state, "asking_pax", context)
        }
    
    for pat in ambiguous_patterns:
        if re.search(pat, user_input.lower()):
            return {
                "type": "text",
                "content": "😊 Please give me the *exact number* of travelers.",
                "new_state": create_new_state(state, "asking_pax", context)
            }

    if not extracted.get("valid"):
        return {
            "type": "text",
            "content": (
                f"😅 _{extracted.get('error', 'I could not understand that.')}_\n\n"
                f"👥 *How many people are traveling?*\n"
                f"_Example: 4 adults OR 2 adults and 2 children_"
            ),
            "new_state": create_new_state(state, "asking_pax", context)
        }
    
    adults = extracted.get("adults") or 0
    children = extracted.get("children") or 0
    has_children = extracted.get("has_children", False)

    if adults <= 0:
        return {
            "type": "text",
            "content": "😅 Please tell me at least how many *adults* are traveling.",
            "new_state": create_new_state(state, "asking_pax", context)
        }

    context["adults"] = adults
    context["children"] = children if has_children else 0

    if has_children and children > 0:
        travellers_text = f"{adults} adult{'s' if adults > 1 else ''} & {children} child{'ren' if children > 1 else ''}"
    else:
        travellers_text = f"{adults} adult{'s' if adults > 1 else ''}"

    context["travellers"] = travellers_text

    interpretation = extracted.get("interpretation", "")
    confirm_text = f"✅ Got it!\n\n👥 *Travelers:* {travellers_text}"
    if interpretation:
        confirm_text += f"\n_💡 Understood as: {interpretation}_"
    confirm_text += "\n\nIs that correct?"

    return {
        "type": "buttons",
        "content": confirm_text,
        "buttons": [
            {"text": "Yes, correct", "value": "confirm_pax_yes"},
            {"text": "Change travelers", "value": "confirm_pax_no"}
        ],
        "new_state": create_new_state(state, "confirming_pax", context)
    }


def _confirm_pax(user_input, state):
    context = state.get("context", {})
    mode = state.get("search_mode", "package")

    if user_input == "confirm_pax_yes":
        thing = "hotel location" if mode == "hotel" else "destination"
        return {
            "type": "text",
            "content": f"Wonderful! 👨‍👩‍👧‍👦\n\n🗺️ *Which {thing} would you like?*",
            "new_state": create_new_state(state, "asking_destination", context)
        }
    else:
        for k in ["adults", "children", "travellers"]:
            context.pop(k, None)
        return {
            "type": "text",
            "content": "No problem! 👥 *How many people are traveling?*",
            "new_state": create_new_state(state, "asking_pax", context)
        }


# ══════════════════════════════════════════════════════════════
# STEP 4 — DESTINATION
# ══════════════════════════════════════════════════════════════

def _handle_destination_input(user_input, state):
    context = state.get("context", {})
    mode = state.get("search_mode", "package")

    if mode == "hotel":
        items = _fetch_and_cache_hotels(state)
        available_locations = set()
        for h in items:
            loc = h.get("hotel_location", "")
            if loc and isinstance(loc, str):
                available_locations.add(loc.strip())
    else:
        items = _fetch_and_cache_packages(state)
        available_locations = set()
        for pkg in items:
            for loc in pkg.get("locations", []):
                if loc and isinstance(loc, str):
                    available_locations.add(loc.strip())

    extracted = extract_destinations_llm(user_input, available_locations)

    if not extracted.get("valid") or not extracted.get("destinations"):
        return {
            "type": "text",
            "content": "😅 I couldn't find a destination in that.\n\n🗺️ *Where would you like to travel?*",
            "new_state": create_new_state(state, "asking_destination", context)
        }

    destinations = [d.strip().title() for d in extracted["destinations"] if d and d.strip()]

    if not destinations:
        return {
            "type": "text",
            "content": "😅 Please tell me your destination.",
            "new_state": create_new_state(state, "asking_destination", context)
        }

    context["destinations"] = destinations
    dest_text = ", ".join(destinations)

    return {
        "type": "buttons",
        "content": f"✈️ *{dest_text}* — great choice! 🏔️\n\nIs that correct?",
        "buttons": [
            {"text": "Is this Corrent ?", "value": "confirm_dest_yes"},
            {"text": "Change destination", "value": "confirm_dest_no"}
        ],
        "new_state": create_new_state(state, "confirming_destination", context)
    }


def _confirm_destination_and_show_results(user_input, state):
    context = state.get("context", {})
    mode = state.get("search_mode", "package")

    if user_input == "confirm_dest_yes":
        destinations = context.get("destinations", [])
        dest_text = ", ".join(destinations) if isinstance(destinations, list) else str(destinations)
        summary = create_summary(context)

        if mode == "hotel":
            hotels = _fetch_and_cache_hotels(state)
            filtered = filter_hotels_by_destinations(hotels, destinations)
            # Always show results — fall back to all hotels if no match
            result_list = filtered if filtered else hotels
            state["filtered_hotels"] = result_list
            state["hotel_page"] = 0

            if filtered:
                message = f"{summary}\n\n🎉 *Found {len(filtered)} hotel(s) for {dest_text}!*"
            else:
                message = f"{summary}\n\n😔 *No exact matches for {dest_text}.*\n\n🌟 *Here are all available hotels:*"
            return _show_hotels(result_list[:PACKAGES_PER_PAGE], message, state)
        else:
            packages = _fetch_and_cache_packages(state)
            filtered = filter_packages_by_destinations(packages, destinations)
            result_list = filtered if filtered else packages
            state["filtered_packages"] = result_list
            state["current_page"] = 0

            if filtered:
                message = f"{summary}\n\n🎉 *Found {len(filtered)} package(s) for {dest_text}!*"
            else:
                message = f"{summary}\n\n😔 *No exact matches for {dest_text}.*\n\n🌟 *Here are some popular packages:*"
            return _show_packages(result_list[:PACKAGES_PER_PAGE], message, state)

    else:
        context.pop("destinations", None)
        return {
            "type": "text",
            "content": "🗺️ *Where would you like to travel?*",
            "new_state": create_new_state(state, "asking_destination", context)
        }


# ══════════════════════════════════════════════════════════════
# PACKAGE DISPLAY
# ══════════════════════════════════════════════════════════════

def _show_packages(packages, message, state):
    if not packages:
        return {
            "type": "buttons",
            "content": "😅 *No packages found.*",
            "buttons": [
                {"text": "Find Package", "value": "start_search"},
                {"text": "Find Hotel", "value": "start_hotel_search"},
                {"text": "Main Menu", "value": "main_menu"},
                {"text": "Exit", "value": "exit"},
            ],
            "new_state": create_new_state(state, "showing_packages", state.get("context", {}))
        }

    responses = [{"type": "text", "content": message}]

    context = state.get("context", {})
    adults = context.get("adults", 2)
    children = context.get("children", 0)

    for pkg in packages:
        name = clean_text(pkg.get('package_name', 'Package'))
        price = pkg.get('package_price', '?')
        locations = pkg.get('locations', [])
        location_text = ', '.join(locations) if locations else 'Various'
        package_image = pkg.get('package_image', '')
        pkg_id = pkg.get('id')

        per_person_price = calculate_per_person_price(price, adults, children)

        if package_image:
            responses.append({
                "type": "image",
                "content": package_image,
                "caption": f"✨ {name}\n\n💰 ₹{price}\n\n👤 {per_person_price} per person\n\n📍 {location_text}"
            })

        pkg_text = (
            f"✨ *{name}*\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"💰 *Package Price:* ₹{price}\n"
            f"👤 *Per Person:* {per_person_price}\n"
            f"📍 *Location:* {location_text}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━"
        )

        responses.append({
            "type": "buttons",
            "content": pkg_text,
            "buttons": [
                {"text": "View Details", "value": f"pkg_{pkg_id}"},
                {"text": "Book Now", "value": "book_package"},
            ]
        })

    # ── Load more / navigation ────────────────────────────────
    all_packages = state.get("filtered_packages", state.get("packages", []))
    current_page = state.get("current_page", 0)

    has_more = has_more_items(all_packages, current_page, PACKAGES_PER_PAGE)
    remaining = get_remaining_count(all_packages, current_page, PACKAGES_PER_PAGE)
    nav_buttons = build_navigation_buttons(has_more, remaining, PACKAGES_PER_PAGE)

    responses.append({
        "type": "buttons",
        "content": "━ *MAIN MENU* ━",
        "buttons": nav_buttons
    })

    return {
        "type": "multi",
        "responses": responses,
        "new_state": {
            "step": "showing_packages",
            "search_mode": "package",
            "packages": state.get("packages", all_packages),
            "filtered_packages": all_packages,
            "current_page": current_page,
            "hotels": state.get("hotels", []),
            "filtered_hotels": state.get("filtered_hotels", []),
            "hotel_page": state.get("hotel_page", 0),
            "context": state.get("context", {}),
            "user_phone": state.get("user_phone", ""),
            "partner_email": state.get("partner_email", ""),
        }
    }


def _handle_load_more_packages(state):
    current_page = state.get("current_page", 0)
    all_packages = state.get("filtered_packages", state.get("packages", []))

    if not all_packages:
        return {"type": "text", "content": "No packages available."}

    next_page = current_page + 1
    start_idx = next_page * PACKAGES_PER_PAGE
    more_packages = all_packages[start_idx:start_idx + PACKAGES_PER_PAGE]

    if more_packages:
        state["current_page"] = next_page
        return _show_packages(
            more_packages,
            f"📦 *Packages ({start_idx + 1}-{start_idx + len(more_packages)} of {len(all_packages)}):*",
            state
        )
    else:
        return {
            "type": "buttons",
            "content": "📦 *You've seen all packages!*",
            "buttons": [
                {"text": "New Search", "value": "start_search"},
                {"text": "Find Hotels", "value": "start_hotel_search"},
                {"text": "Main Menu", "value": "main_menu"},
                {"text": "Exit", "value": "exit"},
            ]
        }


def _handle_showing_packages(user_input, state):
    if user_input.startswith("pkg_"):
        return _handle_package_select(user_input, state)

    if user_input == "load_more":
        return _handle_load_more_packages(state)

    packages = state.get("filtered_packages", state.get("packages", []))
    if not packages:
        return _greeting_response(user_input, state)

    current_page = state.get("current_page", 0)
    start_idx = current_page * PACKAGES_PER_PAGE
    current_pkgs = packages[start_idx:start_idx + PACKAGES_PER_PAGE] or packages[:PACKAGES_PER_PAGE]
    return _show_packages(current_pkgs, "📦 *Available packages:*", state)


# ══════════════════════════════════════════════════════════════
# PACKAGE DETAIL VIEW
# ══════════════════════════════════════════════════════════════

def _handle_package_select(user_input, state):
    try:
        package_id = int(user_input.split("_")[1])
    except (IndexError, ValueError):
        return {
            "type": "buttons",
            "content": "❌ Invalid selection.",
            "buttons": [
                {"text": "Back to Packages", "value": "back_to_packages"},
                {"text": "Main Menu", "value": "main_menu"},
                {"text": "Exit", "value": "exit"},
            ]
        }

    packages = state.get("packages", [])
    selected = next((p for p in packages if p.get("id") == package_id), None)

    if not selected:
        return {
            "type": "buttons",
            "content": "❌ Package not found.",
            "buttons": [
                {"text": "Back to Packages", "value": "back_to_packages"},
                {"text": "Main Menu", "value": "main_menu"},
                {"text": "Exit", "value": "exit"},
            ]
        }

    context = state.get("context", {})
    context["selected_package"] = selected

    responses = _build_full_package_details(selected, state)
    pkg_id = selected.get('id')

    responses.append({
        "type": "buttons",
        "content": "📋 *--ACTIONS--*",
        "buttons": [
            {"text": "Book Now", "value": "book_package"},
            {"text": "Download PDF", "value": f"download_pdf_pkg_{pkg_id}"},
        ]
    })

    responses.append({
        "type": "buttons",
        "content": "🧭 *--NAVIGATION MENU--*",
        "buttons": [
            {"text": "Back to Packages", "value": "back_to_packages"},
            {"text": "New Search", "value": "start_search"},
            {"text": "Find Hotels", "value": "start_hotel_search"},
            {"text": "Main Menu", "value": "main_menu"},
        ]
    })

    return {
        "type": "multi",
        "responses": responses,
        "new_state": {
            "step": "package_details",
            "search_mode": "package",
            "context": context,
            "packages": state.get("packages", []),
            "filtered_packages": state.get("filtered_packages", []),
            "current_page": state.get("current_page", 0),
            "hotels": state.get("hotels", []),
            "filtered_hotels": state.get("filtered_hotels", []),
            "hotel_page": state.get("hotel_page", 0),
            "user_phone": state.get("user_phone", ""),
            "partner_email": state.get("partner_email", ""),
        }
    }


def _build_full_package_details(package, state):
    name = clean_text(package.get('package_name', 'Package'))
    price = package.get('package_price', 'N/A')
    locations = package.get('locations', [])
    location_text = ', '.join(locations) if locations else 'Various'
    package_image = package.get('package_image', '')
    inclusions = package.get('inclusion', [])
    exclusions = package.get('exclusion', [])
    activities = package.get('activities', [])
    vehicles = package.get('vehicles', [])

    context = state.get("context", {})
    adults = context.get("adults", 2)
    children = context.get("children", 0)
    per_person = calculate_per_person_price(price, adults, children)
    duration_text = context.get("duration_text", "")

    responses = []

    if package_image:
        responses.append({
            "type": "image",
            "content": package_image,
            "caption": f"✨ {name}\n💰 ₹{price} | 👤 {per_person} per person"
        })

    lines = [
        f"✨ *{name}* ✨",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"💰 *Package Price:* ₹{price}",
        f"👤 *Per Person:* {per_person}",
    ]
    if duration_text:
        lines.append(f"⏳ *Duration:* {duration_text}")
    lines += [
        f"📍 *Destinations:* {location_text}",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
    ]

    itinerary = package.get('itinerary', package.get('itinerary_text', ''))
    if itinerary:
        formatted_itinerary = format_itinerary_for_display(itinerary)
        lines.append(formatted_itinerary)
        lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    else:
        lines.append("📅 *Itinerary:*")
        lines.append("  • Contact us for detailed itinerary")
        lines.append("")
        lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

    if activities:
        lines.append("🎯 *ACTIVITIES & EXPERIENCES:*")
        for a in activities:
            lines.append(f"  • {a}")
        lines.append("")
        lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

    if vehicles:
        lines.append("🚗 *VEHICLES INCLUDED:*")
        for v in vehicles:
            lines.append(f"  • {v}")
        lines.append("")
        lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

    lines.append("✅ *WHAT\'S INCLUDED:*")
    if inclusions:
        for i in inclusions:
            clean_i = clean_itinerary_text(i)
            lines.append(f"  ✓ {clean_i}")
    else:
        lines.append("  • Contact us for inclusions")
    lines.append("")
    lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

    lines.append("❌ *WHAT\'S NOT INCLUDED:*")
    if exclusions:
        for e in exclusions:
            clean_e = clean_itinerary_text(e)
            lines.append(f"  ✗ {clean_e}")
    else:
        lines.append("  • Contact us for exclusions")
    lines.append("")
    lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    lines.append("✨ *Ready to book this amazing journey?* ✨")
    lines.append("Click BOOK NOW below!")

    responses.append({"type": "text", "content": "\n".join(lines)})
    return responses


def _handle_followup(followup_type, selected_package, state):
    context = state.get("context", {})
    context["selected_package"] = selected_package
    pkg_id = selected_package.get('id')

    handlers = {
        "itinerary": generate_itinerary_list,
        "hotels": generate_hotels_list,
        "activities": generate_activities_list,
        "vehicles": generate_vehicles_list,
        "inclusions": generate_inclusions_list,
        "exclusions": generate_exclusions_list,
    }

    fn = handlers.get(followup_type)
    content = fn(selected_package) if fn else _generate_full_package_details(selected_package)

    responses = [{"type": "text", "content": content}]
    responses.append({
        "type": "buttons",
        "content": "📋 *Actions*",
        "buttons": [
            {"text": "Download PDF", "value": f"download_pdf_pkg_{pkg_id}"},
            {"text": "Book Now", "value": "book_package"},
            {"text": "Back to Package", "value": f"pkg_{pkg_id}"},
        ]
    })

    return {
        "type": "multi",
        "responses": responses,
        "new_state": create_new_state(state, "package_details", context)
    }


def _handle_package_question(user_input, selected_package, state):
    user_lower = user_input.lower()

    if any(w in user_lower for w in ["details", "full", "complete", "view"]):
        return _handle_package_select(f"pkg_{selected_package.get('id')}", state)

    if any(w in user_lower for w in ["book", "reserve", "confirm"]):
        return _handle_book_package(state)

    if any(w in user_lower for w in ["pdf", "download"]):
        return _handle_download_pdf_package(f"download_pdf_pkg_{selected_package.get('id')}", state)

    return _handle_package_select(f"pkg_{selected_package.get('id')}", state)


def _generate_full_package_details(package):
    name = clean_text(package.get('package_name', 'Package'))
    price = package.get('package_price', 'N/A')
    locations = package.get('locations', [])
    inclusions = package.get('inclusion', [])
    exclusions = package.get('exclusion', [])
    activities = package.get('activities', [])
    vehicles = package.get('vehicles', [])
    itinerary = package.get('itinerary', [])

    lines = [
        f"✨ *{name}* ✨",
        "━━━━━━━━━━━━━━━━━━━━━━",
        f"💰 *Price:* ₹{price}",
        f"📍 *Destinations:* {', '.join(locations) if locations else 'Various'}",
        "━━━━━━━━━━━━━━━━━━━━━━",
    ]

    if itinerary:
        lines.append("📅 *ITINERARY:*")
        for i, day in enumerate(itinerary[:3], 1):
            title = day.get('title', f'Day {i}')
            lines.append(f"  *Day {i}: {title}*")
        lines.append("")

    if activities:
        lines.append("🎯 *ACTIVITIES:*")
        lines.extend([f"  • {a}" for a in activities[:5]])
        lines.append("")

    if vehicles:
        lines.append("🚗 *VEHICLES:*")
        lines.extend([f"  • {v}" for v in vehicles[:3]])
        lines.append("")

    lines.append("✅ *INCLUDED:*")
    lines.extend([f"  • {clean_text(i)}" for i in inclusions[:5]] if inclusions else ["  • No inclusions listed"])
    lines.append("")

    lines.append("❌ *NOT INCLUDED:*")
    lines.extend([f"  • {clean_text(e)}" for e in exclusions[:5]] if exclusions else ["  • No exclusions listed"])
    lines.append("")
    lines.append("━━━━━━━━━━━━━━━━━━━━━━")
    lines.append("✅ *Ready to book? Click Book Now!*")

    return "\n".join(lines)


# ══════════════════════════════════════════════════════════════
# HOTEL DISPLAY
# ══════════════════════════════════════════════════════════════

def _show_hotels(hotels, message, state):
    if not hotels:
        return {
            "type": "buttons",
            "content": "😅 *No hotels found.*",
            "buttons": [
                {"text": "Find Hotel", "value": "start_hotel_search"},
                {"text": "Find Package", "value": "start_search"},
                {"text": "Main Menu", "value": "main_menu"},
                {"text": "Exit", "value": "exit"},
            ],
            "new_state": create_new_state(state, "showing_hotels", state.get("context", {}))
        }

    responses = [{"type": "text", "content": message}]

    for hotel in hotels:
        hotel_id = hotel.get('id')
        name = clean_text(hotel.get('hotel_name', 'Hotel'))
        category = hotel.get('hotel_category', '')
        location = hotel.get('hotel_location', 'Various')
        hotel_image = hotel.get('hotel_image', '')
        rooms = hotel.get('rooms', [])

        price_text = "Contact for price"
        if rooms and isinstance(rooms, list):
            prices = []
            for r in rooms:
                if isinstance(r, dict):
                    sp = r.get('room_selling_price', 0)
                    try:
                        prices.append(int(sp))
                    except (ValueError, TypeError):
                        pass
            if prices:
                price_text = f"₹{min(prices)}/night onwards"

        hotel_text = (
            f"🏨 *{name}*\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"⭐ *Category:* {category}\n"
            f"📍 *Location:* {location}\n"
            f"💰 *Price:* {price_text}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━"
        )

        if hotel_image:
            responses.append({
                "type": "image",
                "content": hotel_image,
                "caption": f"🏨 {name}\n⭐ {category} | 📍 {location}\n💰 {price_text}"
            })

        responses.append({
            "type": "buttons",
            "content": hotel_text,
            "buttons": [
                {"text": "View Details", "value": f"hotel_{hotel_id}"},
                {"text": "Book Now", "value": "book_hotel"},
            ]
        })

    # ── Load more / navigation ────────────────────────────────
    all_hotels = state.get("filtered_hotels", state.get("hotels", []))
    hotel_page = state.get("hotel_page", 0)

    has_more = has_more_items(all_hotels, hotel_page, PACKAGES_PER_PAGE)
    remaining = get_remaining_count(all_hotels, hotel_page, PACKAGES_PER_PAGE)
    nav_buttons = build_navigation_buttons(has_more, remaining, PACKAGES_PER_PAGE)

    responses.append({
        "type": "buttons",
        "content": "━ *MAIN MENU* ━",
        "buttons": nav_buttons
    })

    return {
        "type": "multi",
        "responses": responses,
        "new_state": {
            "step": "showing_hotels",
            "search_mode": "hotel",
            "hotels": state.get("hotels", all_hotels),
            "filtered_hotels": all_hotels,
            "hotel_page": hotel_page,
            "packages": state.get("packages", []),
            "filtered_packages": state.get("filtered_packages", []),
            "current_page": state.get("current_page", 0),
            "context": state.get("context", {}),
            "user_phone": state.get("user_phone", ""),
            "partner_email": state.get("partner_email", ""),
        }
    }


def _handle_load_more_hotels(state):
    hotel_page = state.get("hotel_page", 0)
    all_hotels = state.get("filtered_hotels", state.get("hotels", []))

    if not all_hotels:
        return {"type": "text", "content": "No hotels available."}

    next_page = hotel_page + 1
    start_idx = next_page * PACKAGES_PER_PAGE
    more_hotels = all_hotels[start_idx:start_idx + PACKAGES_PER_PAGE]

    if more_hotels:
        state["hotel_page"] = next_page
        return _show_hotels(
            more_hotels,
            f"🏨 *More hotels ({start_idx + 1}-{start_idx + len(more_hotels)} of {len(all_hotels)}):*",
            state
        )
    else:
        return {
            "type": "buttons",
            "content": "🏨 *You've seen all hotels!*",
            "buttons": [
                {"text": "Find Hotel", "value": "start_hotel_search"},
                {"text": "Find Package", "value": "start_search"},
                {"text": "Main Menu", "value": "main_menu"},
                {"text": "Exit", "value": "exit"},
            ]
        }


def _handle_showing_hotels(user_input, state):
    if user_input.startswith("hotel_"):
        return _handle_hotel_select(user_input, state)

    if user_input == "load_more":
        return _handle_load_more_hotels(state)

    hotels = state.get("filtered_hotels", state.get("hotels", []))
    if not hotels:
        return _greeting_response(user_input, state)

    hotel_page = state.get("hotel_page", 0)
    start_idx = hotel_page * PACKAGES_PER_PAGE
    current_hotels = hotels[start_idx:start_idx + PACKAGES_PER_PAGE] or hotels[:PACKAGES_PER_PAGE]
    return _show_hotels(current_hotels, "🏨 *Available hotels:*", state)


def _handle_hotel_select(user_input, state):
    try:
        hotel_id = int(user_input.split("_")[1])
    except (IndexError, ValueError):
        return {
            "type": "buttons",
            "content": "❌ Invalid selection.",
            "buttons": [
                {"text": "Back to Hotels", "value": "back_to_hotels"},
                {"text": "Main Menu", "value": "main_menu"},
                {"text": "Exit", "value": "exit"},
            ]
        }

    hotels = state.get("hotels", [])
    selected = next((h for h in hotels if h.get("id") == hotel_id), None)

    if not selected:
        return {
            "type": "buttons",
            "content": "❌ Hotel not found.",
            "buttons": [
                {"text": "Back to Hotels", "value": "back_to_hotels"},
                {"text": "Main Menu", "value": "main_menu"},
                {"text": "Exit", "value": "exit"},
            ]
        }

    context = state.get("context", {})
    context["selected_hotel"] = selected

    responses = _build_hotel_card(selected)

    hotel_id_val = selected.get('id')
    has_pdf = bool(selected.get('pdf', ''))

    action_buttons = [{"text": "Book Now", "value": "book_hotel"}]
    if has_pdf:
        action_buttons.append({"text": "Download PDF", "value": f"download_pdf_hotel_{hotel_id_val}"})
    action_buttons.append({"text": "Back to Hotels", "value": "back_to_hotels"})

    responses.append({
        "type": "buttons",
        "content": "📋 *Actions*",
        "buttons": action_buttons
    })
    responses.append({
        "type": "buttons",
        "content": "🧭 *Navigation*",
        "buttons": [
            {"text": "Find Hotel", "value": "start_hotel_search"},
            {"text": "Find Package", "value": "start_search"},
            {"text": "Main Menu", "value": "main_menu"},
        ]
    })

    return {
        "type": "multi",
        "responses": responses,
        "new_state": {
            "step": "hotel_details",
            "search_mode": "hotel",
            "context": context,
            "hotels": state.get("hotels", []),
            "filtered_hotels": state.get("filtered_hotels", []),
            "hotel_page": state.get("hotel_page", 0),
            "packages": state.get("packages", []),
            "filtered_packages": state.get("filtered_packages", []),
            "current_page": state.get("current_page", 0),
            "user_phone": state.get("user_phone", ""),
            "partner_email": state.get("partner_email", ""),
        }
    }


def _build_hotel_card(hotel):
    """Build hotel detail card"""
    name = clean_text(hotel.get('hotel_name', 'Hotel'))
    category = hotel.get('hotel_category', 'N/A')
    location = hotel.get('hotel_location', 'N/A')
    description = clean_text(hotel.get('hotel_description', ''))
    hotel_image = hotel.get('hotel_image', '')
    rooms = hotel.get('rooms', [])

    raw_phones = hotel.get('hotel_mobile_numbers', [])
    phone_numbers = []
    for p in raw_phones:
        if isinstance(p, dict):
            num = p.get('phone_number', '')
            if num:
                phone_numbers.append(str(num))
        elif isinstance(p, str) and p.strip():
            phone_numbers.append(p.strip())

    raw_emails = hotel.get('hotel_email_addresses', [])
    email_addresses = []
    for e in raw_emails:
        if isinstance(e, dict):
            addr = e.get('email_address', '')
            if addr:
                email_addresses.append(str(addr))
        elif isinstance(e, str) and e.strip():
            email_addresses.append(e.strip())

    responses = []

    if hotel_image:
        responses.append({
            "type": "image",
            "content": hotel_image,
            "caption": f"🏨 {name} | ⭐ {category} | 📍 {location}"
        })

    lines = [
        f"🏨 *{name}*",
        "━━━━━━━━━━━━━━━━━━━━━━",
        f"⭐ *Category:* {category}",
        f"📍 *Location:* {location}",
    ]

    if description:
        lines.append(f"\n📝 *About:*\n{description[:300]}")

    if rooms and isinstance(rooms, list):
        lines.append("\n🛏️ *ROOMS AVAILABLE:*")
        for room in rooms:
            if not isinstance(room, dict):
                continue
            room_type = room.get('room_type', 'Room')
            selling = room.get('room_selling_price', '')
            base = room.get('room_base_price', '')
            capacity = room.get('room_capacity', '')
            facilities = room.get('room_facilities', [])

            lines.append(f"\n  🛏️ *{room_type}*")
            if selling:
                lines.append(f"   💰 Price: ₹{selling}/night")
                if base and base != selling:
                    lines.append(f"   ~~Base: ₹{base}~~ (Discounted!)")
            if capacity:
                lines.append(f"   👥 Capacity: {capacity} guests")
            if facilities and isinstance(facilities, list):
                lines.append(f"   ✨ Facilities: {', '.join(str(f) for f in facilities)}")
    else:
        lines.append("\n🛏️ *Rooms:* Contact hotel for room availability")

    if phone_numbers:
        lines.append(f"\n📞 *Contact:* {', '.join(phone_numbers)}")

    if email_addresses:
        lines.append(f"📧 *Email:* {', '.join(email_addresses)}")

    lines.append("\n━━━━━━━━━━━━━━━━━━━━━━")
    lines.append("✅ *Interested? Click Book Now!*")

    responses.append({"type": "text", "content": "\n".join(lines)})
    return responses


def _handle_hotel_question(user_input, selected_hotel, state):
    user_lower = user_input.lower()

    if any(w in user_lower for w in ["room", "stay", "accommodation", "sleep", "lodge", "price", "cost", "rate"]):
        rooms = selected_hotel.get('rooms', [])
        if rooms and isinstance(rooms, list):
            lines = [f"🛏️ *Rooms at {clean_text(selected_hotel.get('hotel_name', 'Hotel'))}:*\n"]
            for room in rooms:
                if not isinstance(room, dict):
                    continue
                lines.append(f"• *{room.get('room_type', 'Room')}* — ₹{room.get('room_selling_price', 'N/A')}/night")
                if room.get('room_capacity'):
                    lines.append(f"  👥 {room.get('room_capacity')}")
                if room.get('room_facilities'):
                    fac = room.get('room_facilities', [])
                    lines.append(f"  ✨ {', '.join(str(f) for f in fac)}\n")
            return {
                "type": "buttons",
                "content": "\n".join(lines),
                "buttons": [
                    {"text": "Book Now", "value": "book_hotel"},
                    {"text": "Back to Hotels", "value": "back_to_hotels"},
                ]
            }

    if any(w in user_lower for w in ["book", "reserve", "confirm"]):
        return _handle_book_hotel(state)

    if any(w in user_lower for w in ["pdf", "download"]):
        hotel_id = selected_hotel.get('id')
        return _handle_download_pdf_hotel(f"download_pdf_hotel_{hotel_id}", state)

    return _handle_hotel_select(f"hotel_{selected_hotel.get('id')}", state)


# ══════════════════════════════════════════════════════════════
# BOOKING  — these END the session (create_exit_state)
# ══════════════════════════════════════════════════════════════

def _handle_book_package(state):
    context = state.get("context", {})
    selected_package = context.get("selected_package", {})
    user_phone = state.get("user_phone", "Unknown")

    pkg_name = clean_text(selected_package.get("package_name", "Not selected"))
    pkg_price = selected_package.get("package_price", "N/A")
    pkg_id = selected_package.get("id", "N/A")
    destinations = context.get("destinations", [])
    dest_text = ", ".join(destinations) if isinstance(destinations, list) else str(destinations)

    adults = context.get("adults", 2)
    children = context.get("children", 0)
    per_person = calculate_per_person_price(pkg_price, adults, children)
    duration_text = context.get("duration_text", "Not specified")

    booking_details = {
        "package_name": pkg_name,
        "package_price": pkg_price,
        "package_id": pkg_id,
        "per_person_price": per_person,
        "travel_dates": context.get("travel_dates", "Not provided"),
        "duration": duration_text,
        "travellers": context.get("travellers", "Not provided"),
        "destinations": dest_text
    }

    partner_email = state.get("partner_email", "")
    email_sent = send_admin_booking_alert(booking_details, user_phone, admin_email=partner_email)
    email_status = "\n📧 *Booking details sent to admin!*" if email_sent else "\n⚠️ *Could not notify admin. Our team will still contact you.*"

    return {
        "type": "text",
        "content": (
            "✅ *Booking Request Received!* 🙏\n\n"
            "🎉 Thank you for choosing our package!\n"
            f"{email_status}\n\n"
            "👨‍💼 *Our executive will call you on WhatsApp shortly* to confirm.\n\n"
            "📞 We'll reach out within 15 minutes!\n\n"
            "✨ *Thank you for trusting us!* ✨"
        ),
        "notify_agent": True,
        "agent_message": (
            f"🔔 *NEW BOOKING REQUEST*\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📱 *Customer WhatsApp:* {user_phone}\n"
            f"📦 *Package:* {pkg_name}\n"
            f"💰 *Price:* ₹{pkg_price}\n"
            f"👤 *Per Person:* {per_person}\n"
            f"📅 *Dates:* {context.get('travel_dates', 'Not provided')}\n"
            f"⏳ *Duration:* {duration_text}\n"
            f"👥 *Travelers:* {context.get('travellers', 'Not provided')}\n"
            f"📍 *Destination:* {dest_text}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"⚡ *URGENT - Call customer on WhatsApp!*"
        ),
        "new_state": create_exit_state(state)   # ← session ends on book
    }


def _handle_book_hotel(state):
    context = state.get("context", {})
    selected_hotel = context.get("selected_hotel", {})
    user_phone = state.get("user_phone", "Unknown")

    hotel_name = clean_text(selected_hotel.get("hotel_name", "Not selected"))
    hotel_location = selected_hotel.get("hotel_location", "N/A")
    hotel_id = selected_hotel.get("id", "N/A")
    rooms = selected_hotel.get("rooms", [])
    duration_text = context.get("duration_text", "Not specified")

    price_text = "Contact for price"
    if rooms and isinstance(rooms, list):
        prices = []
        for r in rooms:
            if isinstance(r, dict):
                sp = r.get('room_selling_price', 0)
                try:
                    prices.append(int(sp))
                except (ValueError, TypeError):
                    pass
        if prices:
            price_text = f"₹{min(prices)}/night onwards"

    destinations = context.get("destinations", [])
    dest_text = ", ".join(destinations) if isinstance(destinations, list) else str(destinations)

    booking_details = {
        "package_name": f"Hotel: {hotel_name}",
        "package_price": price_text,
        "package_id": hotel_id,
        "per_person_price": "N/A",
        "travel_dates": context.get("travel_dates", "Not provided"),
        "duration": duration_text,
        "travellers": context.get("travellers", "Not provided"),
        "destinations": dest_text
    }

    partner_email = state.get("partner_email", "")
    send_admin_booking_alert(booking_details, user_phone, admin_email=partner_email)

    return {
        "type": "text",
        "content": (
            "✅ *Hotel Booking Request Received!* 🙏\n\n"
            "🎉 Thank you for choosing our hotel!\n\n"
            "👨‍💼 *Our executive will call you shortly* to confirm your room.\n\n"
            "📞 We'll reach out within 15 minutes!\n\n"
            "✨ *Thank you for trusting us!* ✨"
        ),
        "notify_agent": True,
        "agent_message": (
            f"🔔 *NEW HOTEL BOOKING REQUEST*\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📱 *Customer:* {user_phone}\n"
            f"🏨 *Hotel:* {hotel_name}\n"
            f"📍 *Location:* {hotel_location}\n"
            f"💰 *Price:* {price_text}\n"
            f"📅 *Dates:* {context.get('travel_dates', 'Not provided')}\n"
            f"⏳ *Duration:* {duration_text}\n"
            f"👥 *Travelers:* {context.get('travellers', 'Not provided')}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"⚡ *URGENT - Call customer!*"
        ),
        "new_state": create_exit_state(state)   # ← session ends on book
    }


# ══════════════════════════════════════════════════════════════
# PDF DOWNLOAD — PACKAGES
# ══════════════════════════════════════════════════════════════

def _handle_download_pdf_package(user_input, state):
    """Handle PDF download for packages. Expects value: download_pdf_pkg_<id>"""
    try:
        pkg_id = int(user_input.replace("download_pdf_pkg_", ""))
        packages = state.get("packages", [])
        selected = next((p for p in packages if p.get("id") == pkg_id), None)

        if not selected:
            return {
                "type": "buttons",
                "content": "❌ Package not found.",
                "buttons": [{"text": "Main Menu", "value": "main_menu"}]
            }

        pkg_name = selected.get('package_name', 'Package')
        pdf_url = selected.get('pdf', '')

        if not pdf_url:
            return {
                "type": "buttons",
                "content": "⚠️ *PDF not available for this package.*\n\nPlease contact support.",
                "buttons": [{"text": "Main Menu", "value": "main_menu"}]
            }

        user_phone = state.get("user_phone", "")
        pdf_path = download_pdf_from_url(pdf_url, pkg_name)

        if not pdf_path or not os.path.exists(pdf_path):
            return {
                "type": "buttons",
                "content": "⚠️ *Failed to download PDF. Please try again.*",
                "buttons": [
                    {"text": "Try Again", "value": f"download_pdf_pkg_{pkg_id}"},
                    {"text": "Main Menu", "value": "main_menu"},
                ]
            }

        result = send_pdf_via_whatsapp(user_phone, pdf_path, f"📄 {pkg_name} - Travel Package Details")

        if result:
            return {
                "type": "multi",
                "responses": [
                    {"type": "text", "content": f"✅ *PDF Sent!* 📄\n\n*{clean_text(pkg_name)}* delivered to your WhatsApp!"},
                    {
                        "type": "buttons",
                        "content": "📋 *What next?*",
                        "buttons": [
                            {"text": "Book Now", "value": "book_package"},
                            {"text": "Back to Package", "value": f"pkg_{pkg_id}"},
                            {"text": "Main Menu", "value": "main_menu"},
                        ]
                    }
                ],
                "new_state": state
            }
        else:
            return {
                "type": "buttons",
                "content": "⚠️ *Failed to send PDF. Please try again.*",
                "buttons": [
                    {"text": "Try Again", "value": f"download_pdf_pkg_{pkg_id}"},
                    {"text": "Main Menu", "value": "main_menu"},
                ]
            }

    except Exception as e:
        print(f"❌ Package PDF error: {e}")
        import traceback
        traceback.print_exc()
        return {
            "type": "buttons",
            "content": "⚠️ *PDF error. Please try again.*",
            "buttons": [{"text": "Main Menu", "value": "main_menu"}]
        }


# ══════════════════════════════════════════════════════════════
# PDF DOWNLOAD — HOTELS
# ══════════════════════════════════════════════════════════════

def _handle_download_pdf_hotel(user_input, state):
    """Handle PDF download for hotels. Expects value: download_pdf_hotel_<id>"""
    try:
        hotel_id = int(user_input.replace("download_pdf_hotel_", ""))
        hotels = state.get("hotels", [])
        selected = next((h for h in hotels if h.get("id") == hotel_id), None)

        if not selected:
            return {
                "type": "buttons",
                "content": "❌ Hotel not found.",
                "buttons": [{"text": "Main Menu", "value": "main_menu"}]
            }

        hotel_name = selected.get('hotel_name', 'Hotel')
        pdf_url = selected.get('pdf', '')

        if not pdf_url:
            return {
                "type": "buttons",
                "content": "⚠️ *PDF not available for this hotel.*\n\nPlease contact support.",
                "buttons": [{"text": "Main Menu", "value": "main_menu"}]
            }

        user_phone = state.get("user_phone", "")
        pdf_path = download_pdf_from_url(pdf_url, hotel_name)

        if not pdf_path or not os.path.exists(pdf_path):
            return {
                "type": "buttons",
                "content": "⚠️ *Failed to download PDF. Please try again.*",
                "buttons": [
                    {"text": "Try Again", "value": f"download_pdf_hotel_{hotel_id}"},
                    {"text": "Main Menu", "value": "main_menu"},
                ]
            }

        result = send_pdf_via_whatsapp(user_phone, pdf_path, f"📄 {hotel_name} - Hotel Details")

        if result:
            return {
                "type": "multi",
                "responses": [
                    {"type": "text", "content": f"✅ *PDF Sent!* 📄\n\n*{clean_text(hotel_name)}* hotel details delivered to your WhatsApp!"},
                    {
                        "type": "buttons",
                        "content": "📋 *What next?*",
                        "buttons": [
                            {"text": "Book Now", "value": "book_hotel"},
                            {"text": "Back to Hotel", "value": f"hotel_{hotel_id}"},
                            {"text": "Main Menu", "value": "main_menu"},
                        ]
                    }
                ],
                "new_state": state
            }
        else:
            return {
                "type": "buttons",
                "content": "⚠️ *Failed to send PDF. Please try again.*",
                "buttons": [
                    {"text": "Try Again", "value": f"download_pdf_hotel_{hotel_id}"},
                    {"text": "Main Menu", "value": "main_menu"},
                ]
            }

    except Exception as e:
        print(f"❌ Hotel PDF error: {e}")
        import traceback
        traceback.print_exc()
        return {
            "type": "buttons",
            "content": "⚠️ *PDF error. Please try again.*",
            "buttons": [{"text": "Main Menu", "value": "main_menu"}]
        }


# ══════════════════════════════════════════════════════════════
# BACK NAVIGATION  — preserves session
# ══════════════════════════════════════════════════════════════

def _back_to_packages_handler(state):
    packages = state.get("packages", [])
    filtered = state.get("filtered_packages", packages)
    if filtered:
        state["current_page"] = 0
        return _show_packages(filtered[:PACKAGES_PER_PAGE], "📦 *Back to packages:*", state)
    return {
        "type": "buttons",
        "content": "No packages cached. Start a new search?",
        "buttons": [
            {"text": "Find Package", "value": "start_search"},
            {"text": "Main Menu", "value": "main_menu"},
        ]
    }


def _back_to_hotels_handler(state):
    hotels = state.get("hotels", [])
    filtered = state.get("filtered_hotels", hotels)
    if filtered:
        state["hotel_page"] = 0
        return _show_hotels(filtered[:PACKAGES_PER_PAGE], "🏨 *Back to hotels:*", state)
    return {
        "type": "buttons",
        "content": "No hotels cached. Start a new search?",
        "buttons": [
            {"text": "Find Hotel", "value": "start_hotel_search"},
            {"text": "Main Menu", "value": "main_menu"},
        ]
    }


# ══════════════════════════════════════════════════════════════
# CONTEXT HELPERS — skip re-asking when data already present
# ══════════════════════════════════════════════════════════════

def _context_is_complete(context):
    """
    Returns True if all required travel info is already collected:
    travel_dates, duration, travelers (adults), and destinations.
    When complete, switching between Find Package / Find Hotel goes
    straight to results without asking again.
    """
    return all([
        context.get("travel_dates"),
        context.get("duration_text"),
        context.get("adults"),
        context.get("destinations"),
    ])


def _jump_to_results(state, mode):
    """
    Jump directly to package or hotel results using existing context.
    Called when user clicks Find Package / Find Hotel and context is already complete.
    """
    context = state.get("context", {})
    destinations = context.get("destinations", [])
    dest_text = ", ".join(destinations) if isinstance(destinations, list) else str(destinations)
    summary = create_summary(context)

    state["search_mode"] = mode

    if mode == "hotel":
        hotels = _fetch_and_cache_hotels(state)
        filtered = filter_hotels_by_destinations(hotels, destinations)
        result_list = filtered if filtered else hotels
        state["filtered_hotels"] = result_list
        state["hotel_page"] = 0

        if filtered:
            message = f"{summary}\n\n🎉 *Found {len(filtered)} hotel(s) for {dest_text}!*"
        else:
            message = f"{summary}\n\n😔 *No exact matches for {dest_text}.*\n\n🌟 *Here are all available hotels:*"
        return _show_hotels(result_list[:PACKAGES_PER_PAGE], message, state)
    else:
        packages = _fetch_and_cache_packages(state)
        filtered = filter_packages_by_destinations(packages, destinations)
        result_list = filtered if filtered else packages
        state["filtered_packages"] = result_list
        state["current_page"] = 0

        if filtered:
            message = f"{summary}\n\n🎉 *Found {len(filtered)} package(s) for {dest_text}!*"
        else:
            message = f"{summary}\n\n😔 *No exact matches for {dest_text}.*\n\n🌟 *Here are some popular packages:*"
        return _show_packages(result_list[:PACKAGES_PER_PAGE], message, state)




def _fetch_and_cache_packages(state):
    if state.get("packages"):
        return state["packages"]
    result = fetch_packages(OWNER_PHONE)
    print(f"📦 fetch_packages raw result type: {type(result)}")

    if isinstance(result, dict):
        packages = result.get("packages", [])
        partner = result.get("user", {})
        email = partner.get("email", "")
        if email and not state.get("partner_email"):
            state["partner_email"] = email
    else:
        packages = result or []

    if packages:
        state["packages"] = packages
    return packages


def _fetch_and_cache_hotels(state):
    if state.get("hotels"):
        return state["hotels"]
    result = fetch_hotels(OWNER_PHONE)
    print(f"🏨 fetch_hotels raw result type: {type(result)}")

    if isinstance(result, dict):
        hotels = result.get("hotels", [])
        partner = result.get("user", {})
        email = partner.get("email", "")
        if email and not state.get("partner_email"):
            state["partner_email"] = email
    else:
        hotels = result or []

    if hotels:
        state["hotels"] = hotels
    return hotels


# ══════════════════════════════════════════════════════════════
# GREETING / MAIN MENU
# ══════════════════════════════════════════════════════════════

def _greeting_response(user_input, state):
    return {
        "type": "buttons",
        "content": "👋 *Namaste! I\'m your Travel Assistant* 🧳\n\nWhat would you like to do?",
        "buttons": [
            {"text": "Find Package", "value": "start_search"},
            {"text": "Find Hotel", "value": "start_hotel_search"},
        ],
        "new_state": {
            "step": "main_menu",
            "context": state.get("context", {}),   # keep context alive
            "packages": state.get("packages", []),
            "hotels": state.get("hotels", []),
            "filtered_packages": state.get("filtered_packages", []),
            "filtered_hotels": state.get("filtered_hotels", []),
            "current_page": state.get("current_page", 0),
            "hotel_page": state.get("hotel_page", 0),
            "user_phone": state.get("user_phone", ""),
            "partner_email": state.get("partner_email", ""),
        }
    }


def _main_menu(state=None):
    if state is None:
        state = {}
    return {
        "type": "buttons",
        "content": "🏠 *MAIN MENU*\n\nHow can I help you today?",
        "buttons": [
            {"text": "Find Package", "value": "start_search"},
            {"text": "Find Hotel", "value": "start_hotel_search"},
            {"text": "Exit", "value": "exit"},
        ],
        "new_state": {
            "step": "main_menu",
            "context": state.get("context", {}),    
            "packages": state.get("packages", []),
            "hotels": state.get("hotels", []),
            "filtered_packages": state.get("filtered_packages", []),
            "filtered_hotels": state.get("filtered_hotels", []),
            "current_page": state.get("current_page", 0),
            "hotel_page": state.get("hotel_page", 0),
            "user_phone": state.get("user_phone", ""),
            "partner_email": state.get("partner_email", ""),
        }
    }