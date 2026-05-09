ui_card.py

# agent/ui_cards.py
# ─────────────────────────────────────────────────────────────────────────────
# Pure UI / card-formatting helpers.
# Every function returns a dict  { "type": ..., "content": ..., "buttons": ... }
# NO business logic lives here — only presentation.
# ─────────────────────────────────────────────────────────────────────────────

from typing import Dict, List, Optional


# ═══════════════════════════════════════════════════════════════════════════════
# SHARED PRIMITIVES
# ═══════════════════════════════════════════════════════════════════════════════

def _section_header(title: str) -> str:
    """Bold section title."""
    return f"*{title.upper()}*\n\n"


def _row(label: str, value: str) -> str:
    """Single label: value row."""
    return f"*{label}:* {value}\n"


def fp(price) -> str:
    """Format price to Rs.X,XXX"""
    try:
        return f"Rs.{float(str(price).replace(',', '')):,.0f}"
    except (ValueError, TypeError):
        return f"Rs.{price}"


# ═══════════════════════════════════════════════════════════════════════════════
# WELCOME
# ═══════════════════════════════════════════════════════════════════════════════

def card_welcome() -> Dict:
    content = (
        "*TRAVEL ASSISTANT*\n\n"
        "Welcome! I'm your personal travel booking assistant.\n\n"
        "What would you like to book today?"
    )
    return {
        "type": "buttons",
        "content": content,
        "buttons": [
            {"text": "Hotel Booking", "value": "hotel"},
            {"text": "Travel Package", "value": "package"},
        ],
    }


# ═══════════════════════════════════════════════════════════════════════════════
# HOTEL FLOW CARDS
# ═══════════════════════════════════════════════════════════════════════════════

def card_hotel_categories(context: Dict, error_category: str = None) -> Dict:
    """Category selection card."""
    categories = context.get("categories_from_api", [])
    if not categories:
        return {"type": "text", "content": "No categories found. Please try again."}

    dest      = context.get("destination", "")
    check_in  = context.get("check_in", "")
    check_out = context.get("check_out", "")
    guests    = context.get("guests", "")

    content  = _section_header("Hotel Search")
    content += _row("Destination", dest)
    content += _row("Dates", f"{check_in}  to  {check_out}")
    content += _row("Guests", str(guests))
    content += "\n"

    if error_category:
        content += (
            f"No *{error_category}* hotels found in {dest}.\n"
            "Please choose another category:\n"
        )
    else:
        content += "Details confirmed! Choose a *hotel category* below:\n"

    buttons = [{"text": cat["name"], "value": cat["name"]} for cat in categories]
    buttons.append({"text": "Change City", "value": "change_city"})

    return {"type": "buttons_grid", "content": content, "buttons": buttons}


def card_hotel_list(context: Dict) -> Dict:
    """Hotel listing cards."""
    hotels   = context.get("hotels_list", [])[:8]
    category = context.get("selected_category", "")
    dest     = context.get("destination", "")

    content  = _section_header(f"{category} Hotels in {dest}")

    buttons = []
    for i, hotel in enumerate(hotels):
        name     = hotel.get("name", "Unknown")
        location = hotel.get("location", "N/A")
        desc     = hotel.get("description", "")

        content += f"*{i + 1}. {name}*\n"
        content += f"Location: {location}\n"
        if desc:
            content += f"{desc[:80]}{'...' if len(desc) > 80 else ''}\n"
        content += "\n"

        buttons.append({"text": name[:30], "value": f"view_rooms:{name}"})

    buttons.append({"text": "Back to Categories", "value": "back_to_categories"})
    buttons.append({"text": "Change City",        "value": "change_city"})

    content += "Select a hotel to view rooms:"
    return {"type": "buttons_grid", "content": content, "buttons": buttons}


def card_hotel_rooms(context: Dict) -> Dict:
    """Room listing cards."""
    rooms      = context.get("rooms_list", [])[:6]
    hotel_name = context.get("selected_hotel", "Hotel")

    content  = _section_header(f"Rooms at {hotel_name}")

    buttons = []
    for i, room in enumerate(rooms):
        cat     = room.get("category", "")
        rtype   = room.get("type", "")
        min_cap = room.get("minimum_capacity", "?")
        max_cap = room.get("maximum_capacity", "?")
        base    = room.get("base_price", 0)
        extra   = room.get("extra_person_price", 0)

        content += f"*Room {i + 1}: {cat} — {rtype}*\n"
        content += f"Capacity: {min_cap}-{max_cap} guests\n"
        content += f"Base: Rs.{int(base):,}/night\n"
        if extra and int(extra) > 0:
            content += f"Extra person: Rs.{int(extra):,}/night\n"
        content += "\n"

        buttons.append({"text": f"Room {i + 1} — {cat}", "value": f"pick_room:{i}"})

    buttons.append({"text": "Other Hotels", "value": "other_hotels"})
    content += "Select a room to continue:"
    return {"type": "buttons_grid", "content": content, "buttons": buttons}


def card_hotel_summary(context: Dict) -> Dict:
    """Final hotel booking summary card."""
    price       = context.get("price_details", {})
    meal        = context.get("meal_details", {})
    room        = context.get("selected_room_data", {})
    grand_total = price.get("grand_total", 0) + meal.get("total_meal_price", 0)

    nights    = price.get("nights", 0)
    rooms_n   = price.get("rooms_needed", 1)
    dest      = context.get("destination", "")
    check_in  = context.get("check_in", "")
    check_out = context.get("check_out", "")
    guests    = context.get("guests", "")

    content  = _section_header("Booking Summary")
    content += _row("Destination", dest)
    content += _row("Dates", f"{check_in}  to  {check_out}")
    content += _row("Nights", str(nights))
    content += _row("Guests", str(guests))
    content += "\n"

    content += _section_header("Hotel Details")
    content += _row("Hotel", context.get("selected_hotel", ""))
    content += _row("Room", f"{room.get('category', '')} — {room.get('type', '')}")
    content += _row("Rooms Booked", str(rooms_n))
    content += "\n"

    content += _section_header("Price Details")
    content += _row("Room Cost",  f"Rs.{price.get('grand_total', 0):,.0f}")
    content += _row("Meal Plan",  meal.get("meal_name", "No meals"))
    content += _row("Meal Cost",  f"Rs.{meal.get('total_meal_price', 0):,.0f}")
    content += "\n"
    content += f"*GRAND TOTAL:  Rs.{grand_total:,.0f}*\n\n"
    content += "Please confirm your booking"

    return {
        "type": "buttons",
        "content": content,
        "buttons": [
            {"text": "BOOK NOW",      "value": "confirm"},
            {"text": "Change Meal",   "value": "change_meal"},
            {"text": "Other Hotels",  "value": "other_hotels"},
        ],
    }


# ═══════════════════════════════════════════════════════════════════════════════
# PACKAGE FLOW CARDS
# ═══════════════════════════════════════════════════════════════════════════════

def card_pkg_packages(context: Dict) -> Dict:
    """Available packages listing card."""
    pkgs = context.get("packages_list", [])
    dest = context.get("destination", "")

    content  = _section_header(f"Packages for {dest}")

    buttons = []
    for i, pkg in enumerate(pkgs[:6]):
        name   = pkg.get("package_name") or pkg.get("title", "Package")
        nights = len(pkg.get("itinerary", []))

        content += f"*{i + 1}. {name}*\n"
        if nights:
            content += f"{nights} Nights\n"
        content += "\n"

        buttons.append({"text": f"Package {i + 1}", "value": f"select_package_{i}"})

    content += "Select a package to view details:"
    return {"type": "buttons_grid", "content": content, "buttons": buttons}


def card_pkg_full_details(context: Dict) -> Dict:
    """
    Full package details card.
    Identical section format as card_hotel_summary:
      PACKAGE SUMMARY / ITINERARY / PRICE BREAKDOWN / COST SUMMARY
    """
    pkg            = context.get("selected_package", {})
    itinerary      = pkg.get("itinerary", [])
    pd             = context.get("pkg_price_details", {})
    nights         = pd.get("nights", 0)
    total_price    = pd.get("total_price", 0)
    total_hotel    = pd.get("total_hotel_price", 0)
    total_map      = pd.get("total_map_price", 0)
    vehicle_price  = pd.get("vehicle_price", 0)
    vehicle_name   = pd.get("vehicle_name", "None")
    package_margin = pd.get("package_margin", 0)
    guests         = pd.get("guests", 1)
    hotel_costs    = pd.get("hotel_costs", [])
    selected_hotels= pd.get("selected_hotels", {})

    pkg_name  = pkg.get("package_name") or pkg.get("title", "Package")
    check_in  = context.get("check_in", "")
    check_out = context.get("check_out", "")
    dest      = context.get("destination", "")

    veh_str = vehicle_name
    if vehicle_price > 0:
        veh_str += f"  ({fp(vehicle_price)} flat)"

    # ── Package Summary (mirrors hotel summary top block) ──
    content  = _section_header("Package Summary")
    content += _row("Package",     pkg_name)
    content += _row("Destination", dest)
    content += _row("Dates",       f"{check_in}  to  {check_out}")
    content += _row("Nights",      str(nights))
    content += _row("Guests",      str(guests))
    content += _row("Hotel Cat.",  context.get("hotel_category", ""))
    content += _row("Room Cat.",   context.get("room_category", ""))
    content += _row("Vehicle",     veh_str)
    content += "\n"

    # ── Itinerary (mirrors Hotel Details block) ──
    content += _section_header("Itinerary")
    for i, day in enumerate(itinerary[:nights], 1):
        title      = day.get("title", f"Day {i}")
        loc        = day.get("stay_location") or day.get("location", dest)
        hotel_name = selected_hotels.get(loc, context.get("hotel_category", "Hotel"))

        content += f"*Day {i}:* {title}\n"
        content += f"Location: {loc}\n"
        content += f"Hotel: {hotel_name}\n"
        content += f"Vehicle: {vehicle_name}\n"
        content += "\n"

    # ── Price Breakdown per location ──
    content += _section_header("Price Breakdown")
    for cost in hotel_costs:
        loc        = cost.get("location", "")
        h_name     = cost.get("hotel_name", "")
        room_cat   = cost.get("room_category", "")
        season     = cost.get("season_name", "Regular Rate")
        rooms_n    = cost.get("rooms_needed", 0)
        min_c      = cost.get("min_capacity", 2)
        max_c      = cost.get("max_capacity", 3)
        price_room = cost.get("price_per_room", 0)
        extra_p    = cost.get("extra_persons_total", 0)
        extra_pr   = cost.get("extra_person_price", 0)
        h_total    = cost.get("hotel_total", 0)
        map_total  = cost.get("map_total", 0)

        content += f"*Hotel at {loc}*\n"
        content += _row("Name",   h_name)
        content += _row("Room",   room_cat)
        content += _row("Season", season)
        content += _row("Rooms",  f"{rooms_n}  (cap: {min_c}-{max_c} guests)")
        content += _row("Rate",   f"{fp(price_room)}/night")
        if extra_p > 0:
            content += _row("Extra", f"{extra_p} pax @ {fp(extra_pr)}/night")
        content += _row("Hotel Total", fp(h_total))
        content += _row("MAP Meal",    fp(map_total))
        content += "\n"

    # ── Cost Summary (mirrors Price Details block) ──
    content += _section_header("Cost Summary")
    content += _row("Hotel Subtotal", fp(total_hotel))
    content += _row("MAP Meal",       fp(total_map))
    if vehicle_price > 0:
        content += _row("Vehicle", fp(vehicle_price))
    if package_margin > 0:
        content += _row("Margin",  fp(package_margin))
    content += "\n"
    content += f"*TOTAL PACKAGE:  {fp(total_price)}*\n"
    content += "Meal Plan: MAP (Breakfast + Dinner included)\n\n"
    content += "Please review and select an option:"

    return {
        "type": "buttons",
        "content": content,
        "buttons": [
            {"text": "BOOK NOW",       "value": "pkg_book_now"},
            {"text": "Change Vehicle", "value": "pkg_change_vehicle"},
            {"text": "Change Hotel",   "value": "pkg_change_hotel"},
            {"text": "Other Packages", "value": "pkg_other_packages"},
        ],
    }


def card_pkg_final_summary(context: Dict) -> Dict:
    """
    Final package confirmation card.
    Same section format as card_hotel_summary.
    """
    pd          = context.get("pkg_price_details", {})
    total_price = pd.get("total_price", 0)
    pkg_name    = context.get("selected_package", {}).get("package_name", "Package")
    vehicle     = context.get("vehicle", {})
    check_in    = context.get("check_in", "")
    check_out   = context.get("check_out", "")

    content  = _section_header("Booking Summary")
    content += _row("Package",     pkg_name)
    content += _row("Destination", context.get("destination", ""))
    content += _row("Dates",       f"{check_in}  to  {check_out}")
    content += _row("Guests",      str(context.get("guests", "")))
    content += "\n"

    content += _section_header("Package Details")
    content += _row("Hotel Cat.", context.get("hotel_category", ""))
    content += _row("Room Cat.",  context.get("room_category", ""))
    content += _row("Vehicle",    vehicle.get("name", "None"))
    content += "\n"

    content += _section_header("Price Details")
    content += _row("Meal Plan", "MAP (Breakfast + Dinner)")
    content += "\n"
    content += f"*TOTAL PACKAGE:  {fp(total_price)}*\n\n"
    content += "Please confirm your booking"

    return {
        "type": "buttons",
        "content": content,
        "buttons": [
            {"text": "Confirm Booking", "value": "pkg_confirm_package"},
            {"text": "Change Vehicle",  "value": "pkg_change_vehicle"},
            {"text": "Change Hotel",    "value": "pkg_change_hotel"},
            {"text": "Other Packages",  "value": "pkg_other_packages"},
        ],
    }