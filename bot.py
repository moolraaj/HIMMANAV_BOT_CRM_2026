"""
bot.py - Fixed version:
  1. Date: "next 2 days" correctly shows today → today+2, LLM interpretation shown to user
  2. Travelers: ambiguous input ("1 or 2") asks again; adults+children tracked properly
  3. Locations: NO hardcoded names — LLM extracts destinations, fuzzy match against package locations
  4. Navigation (New Search + Main Menu) always visible below packages AND after package details
  5. Wrong input at any step → friendly guide with examples, never crashes
  6. PDF Try Again button on failure
"""

from services.api import fetch_packages
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
    """Main bot function"""

    if not user_input or not user_input.strip():
        return {"type": "text", "content": "Hey there! 👋 How can I help you today?"}

    # user_phone is set by message_handler.py BEFORE calling us — fallback only
    if not state.get("user_phone"):
        state["user_phone"] = phone

    context = state.get("context", {})
    step = state.get("step", "greeting")

    print(f"🔍 Step: {step}, Input: {user_input[:50]}")

    # ── Button callbacks ──────────────────────────────────────

    if user_input.startswith("pkg_"):
        return _handle_package_select(user_input, state)

    if user_input.startswith("followup_"):
        followup_type = user_input.replace("followup_", "")
        selected_package = context.get("selected_package")
        if not selected_package:
            return {"type": "text", "content": "Please select a package first."}
        return _handle_followup(followup_type, selected_package, state)

    if user_input == "back_to_packages":
        return _back_to_packages_handler(state)

    if user_input == "main_menu":
        return _main_menu(state)

    if user_input == "start_search":
        return _ask_travel_dates(_fresh_state(state))

    if user_input == "close_chat":
        return _handle_close_chat(state)

    if user_input == "cheapest":
        packages = _fetch_and_cache(state)
        sorted_pkgs = sorted(packages, key=_safe_price)
        state["filtered_packages"] = sorted_pkgs
        state["current_page"] = 0
        return _show_packages(sorted_pkgs[:3], "💰 *Budget-friendly packages for you:*", state)

    if user_input == "premium":
        packages = _fetch_and_cache(state)
        sorted_pkgs = sorted(packages, key=_safe_price, reverse=True)
        state["filtered_packages"] = sorted_pkgs
        state["current_page"] = 0
        return _show_packages(sorted_pkgs[:3], "💎 *Luxury packages for you:*", state)

    if user_input == "show_all":
        packages = _fetch_and_cache(state)
        state["filtered_packages"] = packages
        state["current_page"] = 0
        return _show_packages(packages[:3], f"📦 *All {len(packages)} packages:*", state)

    if user_input == "load_more_packages":
        return _handle_load_more(state)

    if user_input == "book_package":
        return _handle_book_package(state)

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
        return _confirm_destination_and_show_packages(user_input, state)

    if step == "showing_packages":
        return _handle_showing_packages(user_input, state)

    if step == "package_details":
        selected_package = context.get("selected_package")
        if selected_package:
            return _handle_package_question(user_input, selected_package, state)

    return _greeting_response(user_input, state)


# ══════════════════════════════════════════════════════════════
# STEP 1 — TRAVEL DATES
# ══════════════════════════════════════════════════════════════

def _ask_travel_dates(state):
    context = state.get("context", {})
    return {
        "type": "text",
        "content": (
            "👋 *Hello! I'm Your Travel Assistant* 🧳\n\n"
            "I'll help you find the perfect travel package!\n\n"
            "📅 *When are you planning to travel?*\n\n"
            "You can say things like:\n"
            "• *Tomorrow*\n"
            "• *After 20 days*\n"
            "• *Next 5 days*\n"
            "• *24 April to 30 April*\n"
            "• *This weekend*"
        ),
        "new_state": _ns(state, "asking_dates", context)
    }


def _handle_dates_input(user_input, state):
    context = state.get("context", {})

    extracted = extract_travel_dates_llm(user_input)

    if not extracted.get("valid"):
        # Wrong input — guide with examples
        return {
            "type": "text",
            "content": (
                f"😅 _{extracted.get('error', 'I could not understand that date.')}_\n\n"
                "📅 *Please tell me your travel dates:*\n\n"
                "Examples:\n"
                "• *Tomorrow*\n"
                "• *After 20 days*\n"
                "• *Next 5 days*\n"
                "• *25 April to 30 April*\n"
                "• *This weekend*"
            ),
            "new_state": _ns(state, "asking_dates", context)
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

    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    
    # Calculate max allowed date (2 years from today)
    max_allowed_date = today.replace(year=today.year + 2)
    
    # VALIDATION 1: Check if date is in the past
    if start_date and start_date < today:
        return {
            "type": "text",
            "content": (
                f"😅 *{start_date.strftime('%d %B %Y')}* is already in the past!\n\n"
                "📅 Please give me a *future date*:\n\n"
                "Examples: *Tomorrow*, *After 10 days*, *Next month*"
            ),
            "new_state": _ns(state, "asking_dates", context)
        }
    
    # VALIDATION 2: Check if date is too far in the future (beyond 2 years)
    if start_date and start_date > max_allowed_date:
        return {
            "type": "text",
            "content": (
                f"😅 *{start_date.strftime('%d %B %Y')}* is too far in the future!\n\n"
                f"📅 We can only accept bookings up to *{(today.year + 2)}* (2 years from now).\n\n"
                "Please provide a date within the next 2 years.\n\n"
                "Examples: *Tomorrow*, *Next month*, *December this year*"
            ),
            "new_state": _ns(state, "asking_dates", context)
        }
    
    # VALIDATION 3: If end date provided, check it
    if end_date:
        if end_date < today:
            return {
                "type": "text",
                "content": (
                    f"😅 Your end date *{end_date.strftime('%d %B %Y')}* is already in the past!\n\n"
                    "📅 Please provide valid future dates."
                ),
                "new_state": _ns(state, "asking_dates", context)
            }
        
        if end_date > max_allowed_date:
            return {
                "type": "text",
                "content": (
                    f"😅 Your end date *{end_date.strftime('%d %B %Y')}* is too far in the future!\n\n"
                    f"📅 We can only accept bookings up to *{(today.year + 2)}* (2 years from now).\n\n"
                    "Please provide dates within the next 2 years."
                ),
                "new_state": _ns(state, "asking_dates", context)
            }
        
        # VALIDATION 4: Check if start date is after end date
        if start_date and end_date and start_date > end_date:
            return {
                "type": "text",
                "content": (
                    f"😅 Your start date *{start_date.strftime('%d %B %Y')}* is after your end date *{end_date.strftime('%d %B %Y')}*!\n\n"
                    "📅 Please provide correct date range (start date should be before end date)."
                ),
                "new_state": _ns(state, "asking_dates", context)
            }

    # Build human-readable display
    if end_date:
        date_display = f"{start_date.strftime('%d %B %Y')} → {end_date.strftime('%d %B %Y')}"
        context["end_date_str"] = extracted.get("end_date", "")
    else:
        date_display = f"Starting {start_date.strftime('%d %B %Y')}"

    context["travel_dates"] = date_display
    context["start_date_str"] = extracted.get("start_date", "")

    # Show LLM interpretation so user knows what it understood
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
        "new_state": _ns(state, "confirming_dates", context)
    }

def _validate_date_range(start_date, end_date=None):
    """Validate dates are within acceptable range (not past, not beyond 2 years)"""
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    max_allowed = today.replace(year=today.year + 2)
    
    # Check if date is too far in future (more than 2 years)
    if start_date and start_date > max_allowed:
        years_diff = start_date.year - today.year
        return False, f"Date is {years_diff} years in future. Maximum allowed is 2 years."
    
    if end_date and end_date > max_allowed:
        years_diff = end_date.year - today.year
        return False, f"End date is {years_diff} years in future. Maximum allowed is 2 years."
    
    # Check if date is in past
    if start_date and start_date < today:
        return False, "Date is in the past. Please provide a future date."
    
    if end_date and end_date < today:
        return False, "End date is in the past. Please provide future dates."
    
    return True, "Valid date range"

def _confirm_dates(user_input, state):
    context = state.get("context", {})

    if user_input == "confirm_dates_yes":
        return {
            "type": "text",
            "content": (
                "Perfect! 📅\n\n"
                "👥 *How many people are traveling?*\n\n"
                "You can say:\n"
                "• *2 people*\n"
                "• *4 adults and 2 children*\n"
                "• *couple*\n"
                "• *1 adult*"
            ),
            "new_state": _ns(state, "asking_pax", context)
        }
    else:
        # Clear date from context on edit
        for k in ["travel_dates", "start_date_str", "end_date_str"]:
            context.pop(k, None)
        return {
            "type": "text",
            "content": "No problem! 📅 *Please tell me your travel dates:*",
            "new_state": _ns(state, "asking_dates", context)
        }


# ══════════════════════════════════════════════════════════════
# STEP 2 — TRAVELERS
# ══════════════════════════════════════════════════════════════

def _handle_pax_input(user_input, state):
    context = state.get("context", {})

    # FIX: Detect ambiguous input like "1 or 2", "maybe 3", etc. — ask for exact number
    ambiguous_patterns = [
        r'\bor\b', r'\bmaybe\b', r'\bprobably\b', r'\baround\b',
        r'\bapproximately\b', r'\bperhaps\b', r'\bnot sure\b',
        r'\babout\b \d', r'\bsome\b'
    ]
    for pat in ambiguous_patterns:
        if re.search(pat, user_input.lower()):
            return {
                "type": "text",
                "content": (
                    "😊 I want to make sure I book for the right number!\n\n"
                    "👥 *Please give me the exact number of travelers:*\n\n"
                    "Examples:\n"
                    "• *2 people*\n"
                    "• *1 adult and 1 child*\n"
                    "• *3 adults*\n"
                    "• *couple*"
                ),
                "new_state": _ns(state, "asking_pax", context)
            }

    extracted = extract_travelers_llm(user_input)

    if not extracted.get("valid"):
        return {
            "type": "text",
            "content": (
                f"😅 _{extracted.get('error', 'I could not understand that.')}_\n\n"
                "👥 *How many people are traveling?*\n\n"
                "Examples:\n"
                "• *2 people*\n"
                "• *4 adults and 2 children*\n"
                "• *couple*"
            ),
            "new_state": _ns(state, "asking_pax", context)
        }

    adults = extracted.get("adults") or 0
    children = extracted.get("children") or 0
    has_children = extracted.get("has_children", False)

    if adults <= 0:
        return {
            "type": "text",
            "content": (
                "😅 Please tell me at least how many *adults* are traveling.\n\n"
                "Examples: *2 adults*, *1 adult*, *couple*"
            ),
            "new_state": _ns(state, "asking_pax", context)
        }

    # FIX: Store both adults and children
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
        "new_state": _ns(state, "confirming_pax", context)
    }


def _confirm_pax(user_input, state):
    context = state.get("context", {})

    if user_input == "confirm_pax_yes":
        return {
            "type": "text",
            "content": (
                "Wonderful! 👨‍👩‍👧‍👦\n\n"
                "🗺️ *Which destination would you like to visit?*\n\n"
                "Just tell me naturally, like:\n"
                "• *Spiti Valley*\n"
                "• *Goa beaches*\n"
                "• *Shimla and Manali*\n"
                "• *Mountains near Delhi*"
            ),
            "new_state": _ns(state, "asking_destination", context)
        }
    else:
        for k in ["adults", "children", "travellers"]:
            context.pop(k, None)
        return {
            "type": "text",
            "content": "No problem! 👥 *How many people are traveling?*",
            "new_state": _ns(state, "asking_pax", context)
        }


# ══════════════════════════════════════════════════════════════
# STEP 3 — DESTINATION (NO HARDCODED LOCATIONS)
# ══════════════════════════════════════════════════════════════

def _handle_destination_input(user_input, state):
    context = state.get("context", {})
    packages = _fetch_and_cache(state)

    # FIX: Collect ALL package locations dynamically — pass to LLM for semantic understanding
    # LLM figures out what user means without any hardcoded location names here
    available_locations = set()
    for pkg in packages:
        for loc in pkg.get("locations", []):
            if loc and isinstance(loc, str):
                available_locations.add(loc.strip())

    extracted = extract_destinations_llm(user_input, available_locations)

    if not extracted.get("valid") or not extracted.get("destinations"):
        return {
            "type": "text",
            "content": (
                "😅 I couldn't find a destination in that.\n\n"
                "🗺️ *Where would you like to travel?*\n\n"
                "You can say things like:\n"
                "• *Spiti*\n"
                "• *Goa*\n"
                "• *Shimla and Manali*\n"
                "• *I want to go to the mountains*"
            ),
            "new_state": _ns(state, "asking_destination", context)
        }

    destinations = [d.strip().title() for d in extracted["destinations"] if d and d.strip()]

    if not destinations:
        return {
            "type": "text",
            "content": "😅 Please tell me your destination.",
            "new_state": _ns(state, "asking_destination", context)
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
        "new_state": _ns(state, "confirming_destination", context)
    }


def _confirm_destination_and_show_packages(user_input, state):
    context = state.get("context", {})

    if user_input == "confirm_dest_yes":
        packages = _fetch_and_cache(state)
        destinations = context.get("destinations", [])

        # LLM-extracted destinations → semantic fuzzy match against package locations
        filtered = _filter_packages_by_destinations(packages, destinations)

        state["packages"] = packages
        state["filtered_packages"] = filtered if filtered else packages
        state["current_page"] = 0

        summary = _create_summary(context)
        dest_text = ", ".join(destinations) if isinstance(destinations, list) else str(destinations)

        if filtered:
            message = f"{summary}\n\n🎉 *Found {len(filtered)} package(s) for {dest_text}!*"
            return _show_packages(filtered[:3], message, state)
        else:
            message = (
                f"{summary}\n\n"
                f"😔 *No exact matches for {dest_text}.*\n\n"
                "🌟 *Here are some popular packages you might like:*"
            )
            return _show_packages(packages[:3], message, state)

    else:
        context.pop("destinations", None)
        return {
            "type": "text",
            "content": "🗺️ *Where would you like to travel?*",
            "new_state": _ns(state, "asking_destination", context)
        }


# ══════════════════════════════════════════════════════════════
# PACKAGE DISPLAY
# ══════════════════════════════════════════════════════════════

def _show_packages(packages, message, state):
    """Show packages. Load More is separate bubble. Navigation always at bottom."""
    if not packages:
        return {
            "type": "buttons",
            "content": "😅 *No packages found.*\n\nWhat would you like to do?",
            "buttons": [
                {"text": "🔍 New Search", "value": "start_search"},
                {"text": "📦 All Packages", "value": "show_all"},
                {"text": "🏠 Main Menu", "value": "main_menu"},
            ],
            "new_state": _ns(state, "showing_packages", state.get("context", {}))
        }

    responses = []
    responses.append({"type": "text", "content": message})

    # Display current page packages
    for pkg in packages:
        name = _clean(pkg.get('package_name', 'Package'))
        price = pkg.get('package_price', '?')
        locations = pkg.get('locations', [])
        location_text = ', '.join(locations) if locations else 'Various'
        package_image = pkg.get('package_image', '')
        pkg_id = pkg.get('id')

        pkg_text = (
            f"✨ *{name}*\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"💰 *Price:* ₹{price}\n"
            f"📍 *Location:* {location_text}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━"
        )

        if package_image:
            responses.append({
                "type": "image",
                "content": package_image,
                "caption": f"✨ {name}\n💰 ₹{price} | 📍 {location_text}"
            })
            responses.append({
                "type": "buttons",
                "content": f"*{name}*",
                "buttons": [
                    {"text": "📋 View Details", "value": f"pkg_{pkg_id}"},
                    {"text": "✅ Book Now", "value": "book_package"},
                ]
            })
        else:
            responses.append({
                "type": "buttons",
                "content": pkg_text,
                "buttons": [
                    {"text": "📋 View Details", "value": f"pkg_{pkg_id}"},
                    {"text": "✅ Book Now", "value": "book_package"},
                ]
            })

    # Get all packages and current page
    all_packages = state.get("filtered_packages", state.get("packages", []))
    current_page = state.get("current_page", 0)
    total_packages = len(all_packages)
    packages_per_page = 3
    start_idx = current_page * packages_per_page
    end_idx = start_idx + packages_per_page
    has_more = end_idx < total_packages
    
    # Show Load More button if there are more packages
    if has_more:
        remaining = total_packages - end_idx
        responses.append({
            "type": "buttons",
            "content": f"📦 *{remaining} more package(s) available*",
            "buttons": [
                {"text": f"📥 Load More ({min(packages_per_page, remaining)})", "value": "load_more_packages"}
            ]
        })
    
    # Always show navigation at bottom
    responses.append({
        "type": "buttons",
        "content": "🧭 *Navigation*",
        "buttons": [
            {"text": "🔍 New Search", "value": "start_search"},
            {"text": "🏠 Main Menu", "value": "main_menu"},
            {"text": "💰 Cheapest", "value": "cheapest"},
            {"text": "💎 Premium", "value": "premium"},
        ]
    })

    return {
        "type": "multi",
        "responses": responses,
        "new_state": {
            "step": "showing_packages",
            "packages": state.get("packages", all_packages),
            "filtered_packages": all_packages,
            "current_page": current_page,  # Keep current page
            "context": state.get("context", {}),
            "user_phone": state.get("user_phone", "")
        }
    }


def _show_packages(packages, message, state):
    """Show packages. Load More is separate bubble. Navigation always at bottom."""
    if not packages:
        return {
            "type": "buttons",
            "content": "😅 *No packages found.*\n\nWhat would you like to do?",
            "buttons": [
                {"text": "🔍 New Search", "value": "start_search"},
                {"text": "📦 All Packages", "value": "show_all"},
                {"text": "🏠 Main Menu", "value": "main_menu"},
            ],
            "new_state": _ns(state, "showing_packages", state.get("context", {}))
        }

    responses = []
    responses.append({"type": "text", "content": message})

    # Display current page packages
    for pkg in packages:
        name = _clean(pkg.get('package_name', 'Package'))
        price = pkg.get('package_price', '?')
        locations = pkg.get('locations', [])
        location_text = ', '.join(locations) if locations else 'Various'
        package_image = pkg.get('package_image', '')
        pkg_id = pkg.get('id')

        pkg_text = (
            f"✨ *{name}*\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"💰 *Price:* ₹{price}\n"
            f"📍 *Location:* {location_text}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━"
        )

        if package_image:
            responses.append({
                "type": "image",
                "content": package_image,
                "caption": f"✨ {name}\n💰 ₹{price} | 📍 {location_text}"
            })
            responses.append({
                "type": "buttons",
                "content": f"*{name}*",
                "buttons": [
                    {"text": "📋 View Details", "value": f"pkg_{pkg_id}"},
                    {"text": "✅ Book Now", "value": "book_package"},
                ]
            })
        else:
            responses.append({
                "type": "buttons",
                "content": pkg_text,
                "buttons": [
                    {"text": "📋 View Details", "value": f"pkg_{pkg_id}"},
                    {"text": "✅ Book Now", "value": "book_package"},
                ]
            })

    # Get all packages and current page
    all_packages = state.get("filtered_packages", state.get("packages", []))
    current_page = state.get("current_page", 0)
    total_packages = len(all_packages)
    packages_per_page = 3
    start_idx = current_page * packages_per_page
    end_idx = start_idx + packages_per_page
    has_more = end_idx < total_packages
    
    # Show Load More button if there are more packages
    if has_more:
        remaining = total_packages - end_idx
        responses.append({
            "type": "buttons",
            "content": f"📦 *{remaining} more package(s) available*",
            "buttons": [
                {"text": f"📥 Load More ({min(packages_per_page, remaining)})", "value": "load_more_packages"}
            ]
        })
    
    # Always show navigation at bottom
    responses.append({
        "type": "buttons",
        "content": "🧭 *Navigation*",
        "buttons": [
            {"text": "🔍 New Search", "value": "start_search"},
            {"text": "🏠 Main Menu", "value": "main_menu"},
            {"text": "💰 Cheapest", "value": "cheapest"},
            {"text": "💎 Premium", "value": "premium"},
        ]
    })

    return {
        "type": "multi",
        "responses": responses,
        "new_state": {
            "step": "showing_packages",
            "packages": state.get("packages", all_packages),
            "filtered_packages": all_packages,
            "current_page": current_page,  # Keep current page
            "context": state.get("context", {}),
            "user_phone": state.get("user_phone", "")
        }
    }


def _handle_load_more(state):
    """Load next batch of packages"""
    all_packages = state.get("filtered_packages", state.get("packages", []))
    
    if not all_packages:
        return {"type": "text", "content": "No packages available."}
    
    current_page = state.get("current_page", 0)
    packages_per_page = 3
    next_page = current_page + 1
    start_idx = next_page * packages_per_page
    end_idx = start_idx + packages_per_page
    
    # Get next batch
    more_packages = all_packages[start_idx:end_idx]
    
    if more_packages:
        # Update current page in state
        state["current_page"] = next_page
        
        total_pages = (len(all_packages) + packages_per_page - 1) // packages_per_page
        message = f"📦 *Page {next_page + 1} of {total_pages}*\n━━━━━━━━━━━━━━━━━━━━━━"
        
        # IMPORTANT: Call _show_packages with updated state
        return _show_packages(more_packages, message, state)
    else:
        # No more packages - show message and offer navigation
        return {
            "type": "buttons",
            "content": "📦 *You've seen all packages!* 🎉\n\nWhat would you like to do next?",
            "buttons": [
                {"text": "🔍 New Search", "value": "start_search"},
                {"text": "💰 Cheapest", "value": "cheapest"},
                {"text": "💎 Premium", "value": "premium"},
                {"text": "🏠 Main Menu", "value": "main_menu"},
            ],
            "new_state": _ns(state, "main_menu", state.get("context", {}))
        }


def _handle_load_more(state):
    current_page = state.get("current_page", 0)
    all_packages = state.get("filtered_packages", state.get("packages", []))

    if not all_packages:
        return {"type": "text", "content": "No packages available."}

    next_page = current_page + 1
    start_idx = next_page * 3
    more_packages = all_packages[start_idx:start_idx + 3]

    if more_packages:
        state["current_page"] = next_page
        total = (len(all_packages) + 2) // 3
        return _show_packages(more_packages, f"📦 *Page {next_page + 1} of {total}:*", state)
    else:
        return {
            "type": "buttons",
            "content": "📦 *You've seen all packages!*",
            "buttons": [
                {"text": "🔍 New Search", "value": "start_search"},
                {"text": "🏠 Main Menu", "value": "main_menu"},
            ]
        }


# ══════════════════════════════════════════════════════════════
# PACKAGE DETAIL VIEW
# ══════════════════════════════════════════════════════════════

def _handle_package_select(user_input, state):
    try:
        package_id = int(user_input.split("_")[1])
    except (IndexError, ValueError):
        return {
            "type": "buttons",
            "content": "❌ Invalid selection. Please try again.",
            "buttons": [
                {"text": "🔙 Back to Packages", "value": "back_to_packages"},
                {"text": "🏠 Main Menu", "value": "main_menu"},
            ]
        }

    packages = state.get("packages", [])
    selected = next((p for p in packages if p.get("id") == package_id), None)

    if not selected:
        return {
            "type": "buttons",
            "content": "❌ Package not found. Please go back and try again.",
            "buttons": [
                {"text": "🔙 Back to Packages", "value": "back_to_packages"},
                {"text": "🏠 Main Menu", "value": "main_menu"},
            ]
        }

    context = state.get("context", {})
    context["selected_package"] = selected

    responses = _build_package_card(selected)
    pkg_id = selected.get('id')

    responses.append({
        "type": "buttons",
        "content": "📋 *What would you like to do?*",
        "buttons": [
            {"text": "✅ Book Now", "value": "book_package"},
            {"text": "📄 Download PDF", "value": f"download_pdf_{pkg_id}"},
            {"text": "🔙 Back to Packages", "value": "back_to_packages"},
        ]
    })
    # FIX: Always show New Search + Main Menu below package details
    responses.append({
        "type": "buttons",
        "content": "🧭 *Navigation*",
        "buttons": [
            {"text": "🔍 New Search", "value": "start_search"},
            {"text": "🏠 Main Menu", "value": "main_menu"},
        ]
    })

    return {
        "type": "multi",
        "responses": responses,
        "new_state": {
            "step": "package_details",
            "context": context,
            "packages": state.get("packages", []),
            "filtered_packages": state.get("filtered_packages", []),
            "current_page": state.get("current_page", 0),
            "user_phone": state.get("user_phone", "")
        }
    }


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
        "content": "📋 *What would you like to do?*",
        "buttons": [
            {"text": "✅ Book Now", "value": "book_package"},
            {"text": "📄 Download PDF", "value": f"download_pdf_{pkg_id}"},
            {"text": "🔙 Back to Package", "value": f"pkg_{pkg_id}"},
        ]
    })
    # FIX: Always show navigation after followup too
    responses.append({
        "type": "buttons",
        "content": "🧭 *Navigation*",
        "buttons": [
            {"text": "🔙 All Packages", "value": "back_to_packages"},
            {"text": "🔍 New Search", "value": "start_search"},
            {"text": "🏠 Main Menu", "value": "main_menu"},
        ]
    })

    return {
        "type": "multi",
        "responses": responses,
        "new_state": {
            "step": "package_details",
            "context": context,
            "packages": state.get("packages", []),
            "filtered_packages": state.get("filtered_packages", []),
            "current_page": state.get("current_page", 0),
            "user_phone": state.get("user_phone", "")
        }
    }


def _handle_package_question(user_input, selected_package, state):
    """Natural language questions about a package"""
    user_lower = user_input.lower()

    keyword_map = {
        "itinerary": ["itinerary", "plan", "schedule", "day by day", "day wise", "daily"],
        "hotels": ["hotel", "stay", "accommodation", "where sleep", "lodge", "room"],
        "activities": ["activit", "things to do", "experience", "adventure", "what to do"],
        "vehicles": ["vehicle", "car", "transport", "cab", "bus", "travel by", "drive"],
        "inclusions": ["inclusion", "included", "what's included", "cover", "comes with"],
        "exclusions": ["exclusion", "excluded", "not included", "extra charge", "pay extra"],
    }

    for followup_type, words in keyword_map.items():
        if any(w in user_lower for w in words):
            return _handle_followup(followup_type, selected_package, state)

    if any(w in user_lower for w in ["price", "cost", "how much", "rate", "fee"]):
        price = selected_package.get('package_price', 'N/A')
        name = _clean(selected_package.get('package_name', 'Package'))
        pkg_id = selected_package.get('id')
        return {
            "type": "buttons",
            "content": f"💰 *{name}*\nPrice: ₹{price}",
            "buttons": [
                {"text": "✅ Book Now", "value": "book_package"},
                {"text": "📋 Full Details", "value": f"pkg_{pkg_id}"},
                {"text": "🏠 Main Menu", "value": "main_menu"},
            ]
        }

    if any(w in user_lower for w in ["book", "reserve", "confirm", "buy"]):
        return _handle_book_package(state)

    # Default — show full details
    return _handle_package_select(f"pkg_{selected_package.get('id')}", state)


def _build_package_card(package):
    name = _clean(package.get('package_name', 'Package'))
    price = package.get('package_price', 'N/A')
    locations = package.get('locations', [])
    location_text = ', '.join(locations) if locations else 'Various'
    package_image = package.get('package_image', '')

    responses = []
    if package_image:
        responses.append({
            "type": "image",
            "content": package_image,
            "caption": f"✨ {name}\n💰 ₹{price} | 📍 {location_text}"
        })

    details = _generate_full_package_details(package)
    responses.append({"type": "text", "content": details})
    return responses


def _generate_full_package_details(package):
    name = _clean(package.get('package_name', 'Package'))
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

    lines.append("📅 *ITINERARY:*")
    if itinerary:
        for i, day in enumerate(itinerary[:5], 1):
            title = day.get('title', f'Day {i}')
            desc = _clean(day.get('description', ''))[:150]
            hotel = day.get('hotel', '')
            lines.append(f"  *Day {i}: {title}*")
            if desc:
                lines.append(f"   📍 {desc}")
            if hotel:
                lines.append(f"   🏨 {_clean(hotel)}")
            lines.append("")
    else:
        lines.append("  • No itinerary available\n")

    lines.append("🎯 *ACTIVITIES:*")
    lines.extend([f"  • {a}" for a in activities[:8]] if activities else ["  • No activities listed"])
    lines.append("")

    lines.append("🚗 *VEHICLES:*")
    lines.extend([f"  • {v}" for v in vehicles[:5]] if vehicles else ["  • No vehicles listed"])
    lines.append("")

    hotels = []
    for day in itinerary:
        h = _clean(day.get('hotel', ''))
        if h and h not in hotels:
            hotels.append(h)
    lines.append("🏨 *HOTELS:*")
    lines.extend([f"  • {h}" for h in hotels[:5]] if hotels else ["  • No hotels listed"])
    lines.append("")

    lines.append("✅ *INCLUDED:*")
    lines.extend([f"  • {_clean(i)}" for i in inclusions[:8]] if inclusions else ["  • No inclusions listed"])
    lines.append("")

    lines.append("❌ *NOT INCLUDED:*")
    lines.extend([f"  • {_clean(e)}" for e in exclusions[:8]] if exclusions else ["  • No exclusions listed"])
    lines.append("")

    lines.append("━━━━━━━━━━━━━━━━━━━━━━")
    lines.append("✅ *Ready to book? Click Book Now!*")

    return "\n".join(lines)


# ══════════════════════════════════════════════════════════════
# SHOWING PACKAGES — freetext while listing
# ══════════════════════════════════════════════════════════════

def _handle_showing_packages(user_input, state):
    if user_input.startswith("pkg_"):
        return _handle_package_select(user_input, state)

    if user_input == "load_more_packages":
        return _handle_load_more(state)

    packages = state.get("filtered_packages", state.get("packages", []))

    if not packages:
        return {
            "type": "buttons",
            "content": "No packages found. Start a new search?",
            "buttons": [
                {"text": "🔍 New Search", "value": "start_search"},
                {"text": "🏠 Main Menu", "value": "main_menu"},
            ]
        }

    try:
        intent_data = understand_user(user_input)
        locations = intent_data.get("locations")

        if locations:
            all_pkgs = state.get("packages", packages)
            filtered = _filter_packages_by_destinations(all_pkgs, locations)
            if filtered:
                state["filtered_packages"] = filtered
                state["current_page"] = 0
                return _show_packages(filtered[:3], f"📦 *Packages for {', '.join(locations)}:*", state)

        user_lower = user_input.lower()

        if any(w in user_lower for w in ['all', 'show all', 'see all', 'every']):
            all_packages = state.get("packages", packages)
            state["filtered_packages"] = all_packages
            state["current_page"] = 0
            return _show_packages(all_packages[:3], f"📦 *All {len(all_packages)} packages:*", state)

        if any(w in user_lower for w in ['cheap', 'cheapest', 'budget', 'low price', 'affordable']):
            sorted_pkgs = sorted(packages, key=_safe_price)
            state["filtered_packages"] = sorted_pkgs
            state["current_page"] = 0
            return _show_packages(sorted_pkgs[:3], "💰 *Budget-friendly packages:*", state)

        if any(w in user_lower for w in ['premium', 'luxury', 'expensive', 'best', 'high end']):
            sorted_pkgs = sorted(packages, key=_safe_price, reverse=True)
            state["filtered_packages"] = sorted_pkgs
            state["current_page"] = 0
            return _show_packages(sorted_pkgs[:3], "💎 *Luxury packages:*", state)

    except Exception as e:
        print(f"⚠️ Intent error in showing_packages: {e}")

    # Default — re-show current page
    current_page = state.get("current_page", 0)
    start_idx = current_page * 3
    current_pkgs = packages[start_idx:start_idx + 3] or packages[:3]
    return _show_packages(current_pkgs, "📦 *Available packages:*", state)


# ══════════════════════════════════════════════════════════════
# BOOK & PDF
# ══════════════════════════════════════════════════════════════

def _handle_book_package(state):
    context = state.get("context", {})
    selected_package = context.get("selected_package", {})
    user_phone = state.get("user_phone", "Unknown")

    pkg_name = _clean(selected_package.get("package_name", "Not selected"))
    pkg_price = selected_package.get("package_price", "N/A")
    pkg_id = selected_package.get("id", "N/A")

    destinations = context.get("destinations", [])
    dest_text = ", ".join(destinations) if isinstance(destinations, list) else str(destinations)

    booking_summary = (
        f"🔔 *NEW BOOKING REQUEST*\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📱 *Customer:* {user_phone}\n"
        f"📦 *Package:* {pkg_name} (ID: {pkg_id})\n"
        f"💰 *Price:* ₹{pkg_price}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📅 *Dates:* {context.get('travel_dates', 'Not provided')}\n"
        f"👥 *Travelers:* {context.get('travellers', 'Not provided')}\n"
        f"🗺️ *Destinations:* {dest_text}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"⚡ *URGENT - Customer wants to book!*"
    )

    return {
        "type": "text",
        "content": (
            "✅ *Booking Request Received!* 🙏\n\n"
            "🎉 Thank you for choosing our package!\n\n"
            "👨‍💼 *Our executive will call you shortly* to confirm.\n\n"
            "📞 We'll reach out within 15 minutes!\n\n"
            "✨ *Thank you for trusting us!* ✨"
        ),
        "notify_agent": True,
        "agent_message": booking_summary,
        "new_state": {
            "step": "greeting",
            "context": {},
            "packages": state.get("packages", []),
            "user_phone": state.get("user_phone", "")
        }
    }


def _handle_download_pdf(user_input, state):
    try:
        pkg_id = int(user_input.replace("download_pdf_", ""))
        packages = state.get("packages", [])
        selected = next((p for p in packages if p.get("id") == pkg_id), None)

        if not selected:
            return {"type": "text", "content": "❌ Package not found. Please try again."}

        pkg_name = _clean(selected.get('package_name', 'Package'))
        context = state.get("context", {})
        user_phone = state.get("user_phone", "")

        print(f"📄 Generating PDF: {pkg_name} → {user_phone}")

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
                "content": "⚠️ *PDF generation failed.*\n\nPlease try again.",
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
                    {
                        "type": "text",
                        "content": (
                            f"✅ *PDF Sent!* 📄\n\n"
                            f"Package: *{pkg_name}*\n\n"
                            f"📥 Delivered to your WhatsApp!"
                        )
                    },
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
                "content": "⚠️ *Failed to send PDF.* Please try again.",
                "buttons": [
                    {"text": "🔄 Try Again", "value": f"download_pdf_{pkg_id}"},
                    {"text": "🏠 Main Menu", "value": "main_menu"},
                ]
            }

    except Exception as e:
        print(f"❌ PDF error: {e}")
        import traceback
        traceback.print_exc()
        return {
            "type": "buttons",
            "content": "⚠️ *PDF error. Please try again.*",
            "buttons": [
                {"text": "🏠 Main Menu", "value": "main_menu"},
            ]
        }


# ══════════════════════════════════════════════════════════════
# LOCATION MATCHING — SEMANTIC, NO HARDCODED NAMES
# ══════════════════════════════════════════════════════════════

def _filter_packages_by_destinations(packages, destinations):
    """
    Semantic fuzzy match — destinations come from LLM extraction so they're
    already cleaned. Match against package locations both ways (substring).
    No hardcoded city/region names anywhere.
    """
    if not destinations or not packages:
        return []

    dest_list = [d.lower().strip() for d in (
        [destinations] if isinstance(destinations, str) else destinations
    ) if d]

    matched = []
    seen_ids = set()

    for pkg in packages:
        pkg_id = pkg.get('id')
        if pkg_id in seen_ids:
            continue

        pkg_locations = [str(loc).lower().strip() for loc in pkg.get('locations', [])]
        pkg_name_lower = _clean(pkg.get('package_name', '')).lower()

        is_match = False
        for user_dest in dest_list:
            # Both-direction substring: "spiti" matches "spiti valley", "spiti valley" matches "spiti"
            for pkg_loc in pkg_locations:
                if user_dest in pkg_loc or pkg_loc in user_dest:
                    is_match = True
                    break
            if not is_match and user_dest in pkg_name_lower:
                is_match = True
            if is_match:
                break

        if is_match:
            seen_ids.add(pkg_id)
            matched.append(pkg)

    return matched


# ══════════════════════════════════════════════════════════════
# UTILITIES
# ══════════════════════════════════════════════════════════════

def _back_to_packages_handler(state):
    packages = state.get("packages", [])
    filtered = state.get("filtered_packages", packages)
    if filtered:
        state["current_page"] = 0
        return _show_packages(filtered[:3], "📦 *Back to packages:*", state)
    return {
        "type": "buttons",
        "content": "No packages cached. Start a new search?",
        "buttons": [
            {"text": "🔍 New Search", "value": "start_search"},
            {"text": "🏠 Main Menu", "value": "main_menu"},
        ]
    }


def _create_summary(context):
    travel_dates = context.get("travel_dates", "Not specified")
    travellers = context.get("travellers", "Not specified")
    destinations = context.get("destinations", [])
    dest_text = ", ".join(destinations) if isinstance(destinations, list) else str(destinations)
    return (
        f"📋 *Your Travel Plan:*\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📅 *Dates:* {travel_dates}\n"
        f"👥 *Travelers:* {travellers}\n"
        f"🗺️ *Destination:* {dest_text}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━"
    )


def _handle_close_chat(state):
    context = state.get("context", {})
    selected_package = context.get("selected_package", {})
    pkg_name = _clean(selected_package.get("package_name", "Not selected"))
    pkg_price = selected_package.get("package_price", "N/A")
    destinations = context.get("destinations", [])
    dest_text = ", ".join(destinations) if isinstance(destinations, list) else str(destinations)

    agent_message = (
        f"🔔 *NEW CUSTOMER INQUIRY*\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📅 Dates: {context.get('travel_dates', 'Not provided')}\n"
        f"👥 Travelers: {context.get('travellers', 'Not provided')}\n"
        f"🗺️ Destinations: {dest_text}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📦 Package: {pkg_name}\n"
        f"💰 Price: ₹{pkg_price}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━"
    )
    return {
        "type": "text",
        "content": (
            "✅ *Thank you for your interest!* 🙏\n\n"
            "👨‍💼 *Our executive will call you shortly!*\n\n"
            "✨ *Have a wonderful day!* ✨"
        ),
        "notify_agent": True,
        "agent_message": agent_message,
        "new_state": {
            "step": "greeting",
            "context": {},
            "packages": state.get("packages", []),
            "user_phone": state.get("user_phone", "")
        }
    }


def _fetch_and_cache(state):
    if state.get("packages"):
        return state["packages"]
    packages = fetch_packages(OWNER_PHONE)
    if packages:
        state["packages"] = packages
    return packages or []


def _greeting_response(user_input, state):
    return {
        "type": "buttons",
        "content": "👋 *Namaste! I'm your Travel Assistant* 🧳\n\nWhat would you like to do?",
        "buttons": [
            {"text": "🔍 Find Package", "value": "start_search"},
            {"text": "💰 Cheapest", "value": "cheapest"},
            {"text": "💎 Premium", "value": "premium"},
            {"text": "📦 All Packages", "value": "show_all"},
        ],
        "new_state": {
            "step": "main_menu",
            "context": {},
            "user_phone": state.get("user_phone", "")
        }
    }


def _main_menu(state=None):
    user_phone = state.get("user_phone", "") if state else ""
    packages = state.get("packages", []) if state else []
    return {
        "type": "buttons",
        "content": "🏠 *Main Menu*\n\nHow can I help you today?",
        "buttons": [
            {"text": "🔍 Find Package", "value": "start_search"},
            {"text": "💰 Cheapest", "value": "cheapest"},
            {"text": "💎 Premium", "value": "premium"},
            {"text": "📦 All Packages", "value": "show_all"},
        ],
        "new_state": {
            "step": "main_menu",
            "context": {},
            "packages": packages,
            "user_phone": user_phone
        }
    }


def _fresh_state(state):
    """Clean state for a new search — preserve phone and package cache"""
    return {
        "context": {},
        "packages": state.get("packages", []),
        "user_phone": state.get("user_phone", ""),
        "step": "greeting"
    }


def _ns(state, step, context):
    """Build new_state preserving all important keys"""
    return {
        "step": step,
        "context": context,
        "packages": state.get("packages", []),
        "filtered_packages": state.get("filtered_packages", []),
        "current_page": state.get("current_page", 0),
        "user_phone": state.get("user_phone", "")
    }


def _safe_price(pkg):
    try:
        return int(pkg.get("package_price", 0))
    except (ValueError, TypeError):
        return 0