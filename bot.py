# bot.py

from services.api import fetch_packages, fetch_hotels
from services.email_service import send_admin_booking_alert
from services.pdf_generator import generate_package_pdf
from services.llm import (
    generate_activities_list,
    generate_vehicles_list,
    generate_inclusions_list,
    generate_exclusions_list,
    generate_hotels_list,
    generate_itinerary_list,
    extract_travel_dates_llm,
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

    # ── EXIT / LOGOUT ──────────────────────────────────────────
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
        fresh = create_fresh_state(state)
        fresh["search_mode"] = "package"
        return _ask_travel_dates(fresh)

    if user_input == "start_hotel_search":
        fresh = create_fresh_state(state)
        fresh["search_mode"] = "hotel"
        return _ask_travel_dates(fresh)

    if user_input == "load_more":
        if state.get("search_mode") == "package":
            return _handle_load_more_packages(state)
        else:
            return _handle_load_more_hotels(state)

    if user_input == "book_package":
        return _handle_book_package(state)

    if user_input == "book_hotel":
        return _handle_book_hotel(state)

    if user_input.startswith("download_pdf_"):
        return _handle_download_pdf(user_input, state)

    # ── Step-based conversation ───────────────────────────────
    if step == "asking_dates":
        return _handle_dates_input(user_input, state)

    if step == "confirming_dates":
        return _confirm_dates(user_input, state)

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
# EXIT HANDLER - Clear memory completely
# ══════════════════════════════════════════════════════════════

def _handle_exit_chat(state):
    """Handle user exit/logout - COMPLETELY RESET everything"""
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
            "👋 *Goodbye!* Thank you for chatting with us! 🙏\n\n"
            "✨ Feel free to come back anytime you need travel assistance!\n\n"
            "🌟 *Have a wonderful day!* 🌟"
        ),
        "notify_agent": True,
        "agent_message": agent_message,
        "new_state": create_exit_state(state)
    }


# ══════════════════════════════════════════════════════════════
# STEP 1 — TRAVEL DATES (shared for both flows)
# ══════════════════════════════════════════════════════════════

def _ask_travel_dates(state):
    context = state.get("context", {})
    mode = state.get("search_mode", "package")
    icon = "🏨" if mode == "hotel" else "📦"
    thing = "hotel" if mode == "hotel" else "travel package"

    return {
        "type": "text",
        "content": f"👋 *Hello! Let's find you the perfect {thing}!* {icon}\n\n📅 *When are you planning to travel?*",
        "new_state": create_new_state(state, "asking_dates", context)
    }


def _handle_dates_input(user_input, state):
    context = state.get("context", {})
    extracted = extract_travel_dates_llm(user_input)

    if not extracted.get("valid"):
        return {
            "type": "text",
            "content": f"😅 _{extracted.get('error', 'I could not understand that date.')}_\n\n📅 *Please tell me your travel dates:*",
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

    # Validate dates
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
            {"text": "✅ Yes, correct", "value": "confirm_dates_yes"},
            {"text": "✏️ Change dates", "value": "confirm_dates_no"}
        ],
        "new_state": create_new_state(state, "confirming_dates", context)
    }


def _confirm_dates(user_input, state):
    context = state.get("context", {})

    if user_input == "confirm_dates_yes":
        return {
            "type": "text",
            "content": "Perfect! 📅\n\n👥 *How many people are traveling?*",
            "new_state": create_new_state(state, "asking_pax", context)
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
# STEP 2 — TRAVELERS (shared)
# ══════════════════════════════════════════════════════════════

def _handle_pax_input(user_input, state):
    context = state.get("context", {})

    ambiguous_patterns = [
        r'\bor\b', r'\bmaybe\b', r'\bprobably\b', r'\baround\b',
        r'\bapproximately\b', r'\bperhaps\b', r'\bnot sure\b', r'\bsome\b'
    ]
    for pat in ambiguous_patterns:
        if re.search(pat, user_input.lower()):
            return {
                "type": "text",
                "content": "😊 Please give me the *exact number* of travelers.",
                "new_state": create_new_state(state, "asking_pax", context)
            }

    extracted = extract_travelers_llm(user_input)

    if not extracted.get("valid"):
        return {
            "type": "text",
            "content": f"😅 _{extracted.get('error', 'I could not understand that.')}_\n\n👥 *How many people are traveling?*",
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
            {"text": "✅ Yes, correct", "value": "confirm_pax_yes"},
            {"text": "✏️ Change travelers", "value": "confirm_pax_no"}
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
# STEP 3 — DESTINATION (routes to packages OR hotels)
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
            {"text": "✅ Yes, correct", "value": "confirm_dest_yes"},
            {"text": "✏️ Change destination", "value": "confirm_dest_no"}
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
            state["filtered_hotels"] = filtered if filtered else hotels
            state["hotel_page"] = 0

            if filtered:
                message = f"{summary}\n\n🎉 *Found {len(filtered)} hotel(s) for {dest_text}!*"
                return _show_hotels(filtered[:PACKAGES_PER_PAGE], message, state)
            else:
                message = f"{summary}\n\n😔 *No exact matches for {dest_text}.*\n\n🌟 *Here are all available hotels:*"
                return _show_hotels(hotels[:PACKAGES_PER_PAGE], message, state)
        else:
            packages = _fetch_and_cache_packages(state)
            filtered = filter_packages_by_destinations(packages, destinations)
            state["filtered_packages"] = filtered if filtered else packages
            state["current_page"] = 0

            if filtered:
                message = f"{summary}\n\n🎉 *Found {len(filtered)} package(s) for {dest_text}!*"
                return _show_packages(filtered[:PACKAGES_PER_PAGE], message, state)
            else:
                message = f"{summary}\n\n😔 *No exact matches for {dest_text}.*\n\n🌟 *Here are some popular packages:*"
                return _show_packages(packages[:PACKAGES_PER_PAGE], message, state)

    else:
        context.pop("destinations", None)
        return {
            "type": "text",
            "content": "🗺️ *Where would you like to travel?*",
            "new_state": create_new_state(state, "asking_destination", context)
        }


# ══════════════════════════════════════════════════════════════
# PACKAGE DISPLAY (with proper pagination)
# ══════════════════════════════════════════════════════════════

def _show_packages(packages, message, state):
    """Show packages with image, price, location, per person price"""
    if not packages:
        return {
            "type": "buttons",
            "content": "😅 *No packages found.*",
            "buttons": [
                {"text": "🔍 Find Package", "value": "start_search"},
                {"text": "🏨 Find Hotel", "value": "start_hotel_search"},
                {"text": "🏠 Main Menu", "value": "main_menu"},
                {"text": "🚪 Exit", "value": "exit"},
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
                {"text": "📋 View Details", "value": f"pkg_{pkg_id}"},
                {"text": "✅ Book Now", "value": "book_package"},
            ]
        })

    all_packages = state.get("filtered_packages", state.get("packages", []))
    current_page = state.get("current_page", 0)
    
    # Calculate pagination info
    has_more = has_more_items(all_packages, current_page, PACKAGES_PER_PAGE)
    remaining = get_remaining_count(all_packages, current_page, PACKAGES_PER_PAGE)
    
    # Build navigation buttons
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
            "user_phone": state.get("user_phone", "")
        }
    }


def _handle_load_more_packages(state):
    """Load next batch of packages"""
    current_page = state.get("current_page", 0)
    all_packages = state.get("filtered_packages", state.get("packages", []))

    if not all_packages:
        return {"type": "text", "content": "No packages available."}

    next_page = current_page + 1
    start_idx = next_page * PACKAGES_PER_PAGE
    more_packages = all_packages[start_idx:start_idx + PACKAGES_PER_PAGE]

    if more_packages:
        state["current_page"] = next_page
        return _show_packages(more_packages, f"📦 *Packages ({start_idx + 1}-{start_idx + len(more_packages)} of {len(all_packages)}):*", state)
    else:
        return {
            "type": "buttons",
            "content": "📦 *You've seen all packages!*",
            "buttons": [
                {"text": "🔍 New Search", "value": "start_search"},
                {"text": "🏨 Find Hotels", "value": "start_hotel_search"},
                {"text": "🏠 Main Menu", "value": "main_menu"},
                {"text": "🚪 Exit", "value": "exit"},
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
# PACKAGE DETAIL VIEW (with Book Now & Download PDF)
# ══════════════════════════════════════════════════════════════

def _handle_package_select(user_input, state):
    try:
        package_id = int(user_input.split("_")[1])
    except (IndexError, ValueError):
        return {
            "type": "buttons",
            "content": "❌ Invalid selection.",
            "buttons": [
                {"text": "🔙 Back to Packages", "value": "back_to_packages"},
                {"text": "🏠 Main Menu", "value": "main_menu"},
                {"text": "🚪 Exit", "value": "exit"},
            ]
        }

    packages = state.get("packages", [])
    selected = next((p for p in packages if p.get("id") == package_id), None)

    if not selected:
        return {
            "type": "buttons",
            "content": "❌ Package not found.",
            "buttons": [
                {"text": "🔙 Back to Packages", "value": "back_to_packages"},
                {"text": "🏠 Main Menu", "value": "main_menu"},
                {"text": "🚪 Exit", "value": "exit"},
            ]
        }

    context = state.get("context", {})
    context["selected_package"] = selected

    # Build full package details
    responses = _build_full_package_details(selected, state)
    pkg_id = selected.get('id')

    # Action buttons: Book Now & Download PDF
    responses.append({
        "type": "buttons",
        "content": "📋 *--ACTIONS--*",
        "buttons": [
            {"text": "✅ Book Now", "value": "book_package"},
            {"text": "📄 Download Pdf", "value": f"download_pdf_{pkg_id}"},
        ]
    })
    
    # Navigation menu (no exit button here - will be in main menu)
    responses.append({
        "type": "buttons",
        "content": "🧭 *--NAVIGATION MENU--*",
        "buttons": [
            {"text": "🔙 Back to Packages", "value": "back_to_packages"},
            {"text": "🔍 New Search", "value": "start_search"},
            {"text": "🏨 Find Hotels", "value": "start_hotel_search"},
            {"text": "🏠 Main Menu", "value": "main_menu"},
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
            "user_phone": state.get("user_phone", "")
        }
    }


def _build_full_package_details(package, state):
    """Build complete package details with all information"""
    name = clean_text(package.get('package_name', 'Package'))
    price = package.get('package_price', 'N/A')
    locations = package.get('locations', [])
    location_text = ', '.join(locations) if locations else 'Various'
    package_image = package.get('package_image', '')
    inclusions = package.get('inclusion', [])
    exclusions = package.get('exclusion', [])
    activities = package.get('activities', [])
    vehicles = package.get('vehicles', [])
    
    # Get per person price
    context = state.get("context", {})
    adults = context.get("adults", 2)
    children = context.get("children", 0)
    per_person = calculate_per_person_price(price, adults, children)

    responses = []

    # Package image
    if package_image:
        responses.append({
            "type": "image",
            "content": package_image,
            "caption": f"✨ {name}\n💰 ₹{price} | 👤 {per_person} per person"
        })

    # Header
    lines = [
        f"✨ *{name}* ✨",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"💰 *Package Price:* ₹{price}",
        f"👤 *Per Person:* {per_person}",
        f"📍 *Destinations:* {location_text}",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
    ]

    # Itinerary (full - using the new formatter)
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

    # Activities
    if activities:
        lines.append("🎯 *ACTIVITIES & EXPERIENCES:*")
        for a in activities:
            lines.append(f"  • {a}")
        lines.append("")
        lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

    # Vehicles
    if vehicles:
        lines.append("🚗 *VEHICLES INCLUDED:*")
        for v in vehicles:
            lines.append(f"  • {v}")
        lines.append("")
        lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

    # Inclusions (full list)
    lines.append("✅ *WHAT'S INCLUDED:*")
    if inclusions:
        for i in inclusions:
            # Clean any HTML tags in inclusions
            clean_i = clean_itinerary_text(i)
            lines.append(f"  ✓ {clean_i}")
    else:
        lines.append("  • Contact us for inclusions")
    lines.append("")
    lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

    # Exclusions (full list)
    lines.append("❌ *WHAT'S NOT INCLUDED:*")
    if exclusions:
        for e in exclusions:
            # Clean any HTML tags in exclusions
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
            {"text": "📄 Download PDF", "value": f"download_pdf_{pkg_id}"},
            {"text": "✅ Book Now", "value": "book_package"},
            {"text": "🔙 Back to Package", "value": f"pkg_{pkg_id}"},
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
        return _handle_download_pdf(f"download_pdf_{selected_package.get('id')}", state)

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
# HOTEL DISPLAY (with proper pagination)
# ══════════════════════════════════════════════════════════════

def _show_hotels(hotels, message, state):
    if not hotels:
        return {
            "type": "buttons",
            "content": "😅 *No hotels found.*",
            "buttons": [
                {"text": "🔍 Find Hotel", "value": "start_hotel_search"},
                {"text": "📦 Find Package", "value": "start_search"},
                {"text": "🏠 Main Menu", "value": "main_menu"},
                {"text": "🚪 Exit", "value": "exit"},
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
        if rooms:
            prices = [int(r.get('room_selling_price', 0)) for r in rooms if r.get('room_selling_price')]
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
                {"text": "📋 View Details", "value": f"hotel_{hotel_id}"},
                {"text": "✅ Book Now", "value": "book_hotel"},
            ]
        })

    all_hotels = state.get("filtered_hotels", state.get("hotels", []))
    hotel_page = state.get("hotel_page", 0)
    
    # Calculate pagination info
    has_more = has_more_items(all_hotels, hotel_page, PACKAGES_PER_PAGE)
    remaining = get_remaining_count(all_hotels, hotel_page, PACKAGES_PER_PAGE)
    
    # Build navigation buttons
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
            "user_phone": state.get("user_phone", "")
        }
    }


def _handle_load_more_hotels(state):
    """Load next batch of hotels"""
    hotel_page = state.get("hotel_page", 0)
    all_hotels = state.get("filtered_hotels", state.get("hotels", []))

    if not all_hotels:
        return {"type": "text", "content": "No hotels available."}

    next_page = hotel_page + 1
    start_idx = next_page * PACKAGES_PER_PAGE
    more_hotels = all_hotels[start_idx:start_idx + PACKAGES_PER_PAGE]

    if more_hotels:
        state["hotel_page"] = next_page
        return _show_hotels(more_hotels, f"🏨 *More hotels ({start_idx + 1}-{start_idx + len(more_hotels)} of {len(all_hotels)}):*", state)
    else:
        return {
            "type": "buttons",
            "content": "🏨 *You've seen all hotels!*",
            "buttons": [
                {"text": "🔍 Find Hotel", "value": "start_hotel_search"},
                {"text": "📦 Find Package", "value": "start_search"},
                {"text": "🏠 Main Menu", "value": "main_menu"},
                {"text": "🚪 Exit", "value": "exit"},
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
                {"text": "🔙 Back to Hotels", "value": "back_to_hotels"},
                {"text": "🏠 Main Menu", "value": "main_menu"},
                {"text": "🚪 Exit", "value": "exit"},
            ]
        }

    hotels = state.get("hotels", [])
    selected = next((h for h in hotels if h.get("id") == hotel_id), None)

    if not selected:
        return {
            "type": "buttons",
            "content": "❌ Hotel not found.",
            "buttons": [
                {"text": "🔙 Back to Hotels", "value": "back_to_hotels"},
                {"text": "🏠 Main Menu", "value": "main_menu"},
                {"text": "🚪 Exit", "value": "exit"},
            ]
        }

    context = state.get("context", {})
    context["selected_hotel"] = selected

    responses = _build_hotel_card(selected)

    responses.append({
        "type": "buttons",
        "content": "📋 *Actions*",
        "buttons": [
            {"text": "✅ Book Now", "value": "book_hotel"},
            {"text": "🔙 Back to Hotels", "value": "back_to_hotels"},
        ]
    })
    responses.append({
        "type": "buttons",
        "content": "🧭 *Navigation*",
        "buttons": [
            {"text": "🔍 Find Hotel", "value": "start_hotel_search"},
            {"text": "📦 Find Package", "value": "start_search"},
            {"text": "🏠 Main Menu", "value": "main_menu"},
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
            "user_phone": state.get("user_phone", "")
        }
    }


def _build_hotel_card(hotel):
    name = clean_text(hotel.get('hotel_name', 'Hotel'))
    category = hotel.get('hotel_category', 'N/A')
    location = hotel.get('hotel_location', 'N/A')
    description = clean_text(hotel.get('hotel_description', ''))
    hotel_image = hotel.get('hotel_image', '')
    rooms = hotel.get('rooms', [])
    phones = hotel.get('hotel_mobile_numbers', [])
    emails = hotel.get('hotel_email_addresses', [])

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

    if rooms:
        lines.append("\n🛏️ *ROOMS AVAILABLE:*")
        for room in rooms:
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
                lines.append(f"   👥 Capacity: {capacity}")
            if facilities:
                lines.append(f"   ✨ Facilities: {', '.join(facilities)}")
    else:
        lines.append("\n🛏️ *Rooms:* Contact hotel for room availability")

    if phones:
        nums = list(set([p.get('phone_number', '') for p in phones if p.get('phone_number')]))
        if nums:
            lines.append(f"\n📞 *Contact:* {', '.join(nums)}")

    if emails:
        mails = list(set([e.get('email_address', '') for e in emails if e.get('email_address')]))
        if mails:
            lines.append(f"📧 *Email:* {', '.join(mails)}")

    lines.append("\n━━━━━━━━━━━━━━━━━━━━━━")
    lines.append("✅ *Interested? Click Book Now!*")

    responses.append({"type": "text", "content": "\n".join(lines)})
    return responses


def _handle_hotel_question(user_input, selected_hotel, state):
    user_lower = user_input.lower()

    if any(w in user_lower for w in ["room", "stay", "accommodation", "sleep", "lodge", "price", "cost", "rate"]):
        rooms = selected_hotel.get('rooms', [])
        if rooms:
            lines = [f"🛏️ *Rooms at {clean_text(selected_hotel.get('hotel_name', 'Hotel'))}:*\n"]
            for room in rooms:
                lines.append(f"• *{room.get('room_type', 'Room')}* — ₹{room.get('room_selling_price', 'N/A')}/night")
                if room.get('room_capacity'):
                    lines.append(f"  👥 {room.get('room_capacity')}")
                if room.get('room_facilities'):
                    lines.append(f"  ✨ {', '.join(room.get('room_facilities', []))}\n")
            return {
                "type": "buttons",
                "content": "\n".join(lines),
                "buttons": [
                    {"text": "✅ Book Now", "value": "book_hotel"},
                    {"text": "🔙 Back to Hotels", "value": "back_to_hotels"},
                ]
            }

    if any(w in user_lower for w in ["book", "reserve", "confirm"]):
        return _handle_book_hotel(state)

    return _handle_hotel_select(f"hotel_{selected_hotel.get('id')}", state)


# ══════════════════════════════════════════════════════════════
# BOOKING
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
    
    # Calculate per person price
    adults = context.get("adults", 2)
    children = context.get("children", 0)
    per_person = calculate_per_person_price(pkg_price, adults, children)

    # Prepare booking details for admin email
    booking_details = {
        "package_name": pkg_name,
        "package_price": pkg_price,
        "package_id": pkg_id,
        "per_person_price": per_person,
        "travel_dates": context.get("travel_dates", "Not provided"),
        "travellers": context.get("travellers", "Not provided"),
        "destinations": dest_text
    }

    # Send email to admin with all details
    email_sent = send_admin_booking_alert(booking_details, user_phone)
    
    # Prepare WhatsApp response for user
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
            f"👥 *Travelers:* {context.get('travellers', 'Not provided')}\n"
            f"📍 *Destination:* {dest_text}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"⚡ *URGENT - Call customer on WhatsApp!*"
        ),
        "new_state": create_exit_state(state)
    }


def _handle_book_hotel(state):
    context = state.get("context", {})
    selected_hotel = context.get("selected_hotel", {})
    user_phone = state.get("user_phone", "Unknown")

    hotel_name = clean_text(selected_hotel.get("hotel_name", "Not selected"))
    hotel_location = selected_hotel.get("hotel_location", "N/A")
    hotel_id = selected_hotel.get("id", "N/A")
    rooms = selected_hotel.get("rooms", [])

    price_text = "Contact for price"
    if rooms:
        prices = [int(r.get('room_selling_price', 0)) for r in rooms if r.get('room_selling_price')]
        if prices:
            price_text = f"₹{min(prices)}/night onwards"

    destinations = context.get("destinations", [])
    dest_text = ", ".join(destinations) if isinstance(destinations, list) else str(destinations)

    # Prepare hotel booking details for admin
    booking_details = {
        "package_name": f"Hotel: {hotel_name}",  # Reuse same structure
        "package_price": price_text,
        "package_id": hotel_id,
        "per_person_price": "N/A",
        "travel_dates": context.get("travel_dates", "Not provided"),
        "travellers": context.get("travellers", "Not provided"),
        "destinations": dest_text
    }

    # Send email to admin
    email_sent = send_admin_booking_alert(booking_details, user_phone)

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
            f"👥 *Travelers:* {context.get('travellers', 'Not provided')}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"⚡ *URGENT - Call customer!*"
        ),
        "new_state": create_exit_state(state)
    }


def _handle_download_pdf(user_input, state):
    try:
        pkg_id = int(user_input.replace("download_pdf_", ""))
        packages = state.get("packages", [])
        selected = next((p for p in packages if p.get("id") == pkg_id), None)

        if not selected:
            return {"type": "text", "content": "❌ Package not found."}

        pkg_name = clean_text(selected.get('package_name', 'Package'))
        context = state.get("context", {})
        user_phone = state.get("user_phone", "")

        user_info = {
            "phone": user_phone,
            "travel_dates": context.get("travel_dates", ""),
            "travelers": context.get("travellers", ""),
            "destinations": context.get("destinations", [])
        }

        pdf_path = generate_package_pdf(selected, user_info)

        if not pdf_path or not os.path.exists(pdf_path):
            return {
                "type": "buttons",
                "content": "⚠️ *PDF generation failed.*",
                "buttons": [
                    {"text": "🔄 Try Again", "value": f"download_pdf_{pkg_id}"},
                    {"text": "🏠 Main Menu", "value": "main_menu"},
                ]
            }

        from services.pdf_generator import send_pdf_via_whatsapp
        result = send_pdf_via_whatsapp(user_phone, pdf_path, f"📄 {pkg_name} - Travel Package Details")

        if result:
            return {
                "type": "multi",
                "responses": [
                    {"type": "text", "content": f"✅ *PDF Sent!* 📄\n\n*{pkg_name}* delivered to your WhatsApp!"},
                    {
                        "type": "buttons",
                        "content": "📋 *What next?*",
                        "buttons": [
                            {"text": "✅ Book Now", "value": "book_package"},
                            {"text": "🔙 Back to Package", "value": f"pkg_{pkg_id}"},
                            {"text": "🏠 Main Menu", "value": "main_menu"},
                        ]
                    }
                ],
                "new_state": state
            }
        else:
            return {
                "type": "buttons",
                "content": "⚠️ *Failed to send PDF.*",
                "buttons": [
                    {"text": "🔄 Try Again", "value": f"download_pdf_{pkg_id}"},
                    {"text": "🏠 Main Menu", "value": "main_menu"},
                ]
            }

    except Exception as e:
        print(f"❌ PDF error: {e}")
        return {
            "type": "buttons",
            "content": "⚠️ *PDF error. Please try again.*",
            "buttons": [{"text": "🏠 Main Menu", "value": "main_menu"}]
        }


# ══════════════════════════════════════════════════════════════
# UTILITIES (remaining functions)
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
            {"text": "🔍 Find Package", "value": "start_search"},
            {"text": "🏠 Main Menu", "value": "main_menu"},
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
            {"text": "🔍 Find Hotel", "value": "start_hotel_search"},
            {"text": "🏠 Main Menu", "value": "main_menu"},
        ]
    }


def _fetch_and_cache_packages(state):
    if state.get("packages"):
        return state["packages"]
    packages = fetch_packages(OWNER_PHONE)
    if packages:
        state["packages"] = packages
    return packages or []


def _fetch_and_cache_hotels(state):
    if state.get("hotels"):
        return state["hotels"]
    hotels = fetch_hotels(OWNER_PHONE)
    if hotels:
        state["hotels"] = hotels
    return hotels or []


def _greeting_response(user_input, state):
    return {
        "type": "buttons",
        "content": "👋 *Namaste! I'm your Travel Assistant* 🧳\n\nWhat would you like to do?",
        "buttons": [
            {"text": "📦 Find Package", "value": "start_search"},
            {"text": "🏨 Find Hotel", "value": "start_hotel_search"},
        ],
        "new_state": {
            "step": "main_menu",
            "context": {},
            "packages": state.get("packages", []),
            "hotels": state.get("hotels", []),
            "user_phone": state.get("user_phone", "")
        }
    }


def _main_menu(state=None):
    user_phone = state.get("user_phone", "") if state else ""
    packages = state.get("packages", []) if state else []
    hotels = state.get("hotels", []) if state else []
    return {
        "type": "buttons",
        "content": "🏠 *MAIN MENU*\n\nHow can I help you today?",
        "buttons": [
            {"text": "📦 Find Package", "value": "start_search"},
            {"text": "🏨 Find Hotel", "value": "start_hotel_search"},
            {"text": "🚪 Exit", "value": "exit"},
        ],
        "new_state": {
            "step": "main_menu",
            "context": {},
            "packages": packages,
            "hotels": hotels,
            "user_phone": user_phone
        }
    }