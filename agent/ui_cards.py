# agent/ui_cards.py
from typing import Dict, List, Optional


 

def _divider() -> str:
    return "─────────────────────────\n"


def _section_header(title: str, emoji: str = "") -> str:
    return f"{emoji} *{title.upper()}*\n{_divider()}"


def _row(label: str, value: str, emoji: str = "") -> str:
    prefix = f"{emoji} " if emoji else "   "
    return f"{prefix}*{label}:* {value}\n"


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
        "╔══════════════════════════╗\n"
        "║  🌍  *TRAVEL ASSISTANT*  ║\n"
        "╚══════════════════════════╝\n\n"
        "Welcome! I'm your personal travel booking assistant.\n\n"
        "What would you like to book today? 👇"
    )
    return {
        "type": "buttons",
        "content": content,
        "buttons": [
            {"text": "🏨 Hotel Booking", "value": "hotel"},
            {"text": "✈️ Travel Package", "value": "package"},
        ],
    }


 

def card_hotel_categories(context: Dict, error_category: str = None) -> Dict:
    """Category selection card."""
    categories = context.get("categories_from_api", [])
    if not categories:
        return {"type": "text", "content": "No categories found. Please try again."}

    dest      = context.get("destination", "")
    check_in  = context.get("check_in", "")
    check_out = context.get("check_out", "")
    guests    = context.get("guests", "")

    # ── Trip summary card ──
    content  = _section_header("Hotel Search", "🔍")
    content += _row("Destination", dest, "📍")
    content += _row("Dates", f"{check_in}  →  {check_out}", "📅")
    content += _row("Guests", str(guests), "👥")
    content += "\n"

    if error_category:
        content += (
            f"⚠️ No *{error_category}* hotels found in {dest}.\n"
            "Please choose another category:\n\n"
        )
    else:
        content += "✅ Details confirmed! Choose a *hotel category* below:\n"

    buttons = [{"text": f"🏷️ {cat['name']}", "value": cat["name"]} for cat in categories]
    buttons.append({"text": "📍 Change City", "value": "change_city"})

    return {"type": "buttons_grid", "content": content, "buttons": buttons}


def card_hotel_list(context: Dict) -> Dict:
    """Hotel listing cards."""
    hotels   = context.get("hotels_list", [])[:8]
    category = context.get("selected_category", "")
    dest     = context.get("destination", "")

    content  = _section_header(f"{category} Hotels in {dest}", "🏨")

    buttons = []
    for i, hotel in enumerate(hotels):
        name     = hotel.get("name", "Unknown")
        location = hotel.get("location", "N/A")
        desc     = hotel.get("description", "")

        content += f"┌─ *{i + 1}. {name}*\n"
        content += f"│  📍 {location}\n"
        if desc:
            content += f"│  📝 {desc[:80]}{'...' if len(desc) > 80 else ''}\n"
        content += "└─────────────────────────\n\n"

        buttons.append({"text": f"🔑 {name[:28]}", "value": f"view_rooms:{name}"})

    buttons.append({"text": "◀ Back to Categories", "value": "back_to_categories"})
    buttons.append({"text": "📍 Change City",        "value": "change_city"})

    content += "👇 Select a hotel to view rooms:"
    return {"type": "buttons_grid", "content": content, "buttons": buttons}


def card_hotel_rooms(context: Dict) -> Dict:
    """Room listing cards."""
    rooms      = context.get("rooms_list", [])[:6]
    hotel_name = context.get("selected_hotel", "Hotel")

    content  = _section_header(f"Rooms — {hotel_name}", "🚪")

    buttons = []
    for i, room in enumerate(rooms):
        cat      = room.get("category", "")
        rtype    = room.get("type", "")
        min_cap  = room.get("minimum_capacity", "?")
        max_cap  = room.get("maximum_capacity", "?")
        base     = room.get("base_price", 0)
        extra    = room.get("extra_person_price", 0)

        content += f"┌─ *Room {i + 1}: {cat} — {rtype}*\n"
        content += f"│  👥 Capacity : {min_cap}–{max_cap} guests\n"
        content += f"│  💰 Base     : ₹{int(base):,}/night\n"
        if extra and int(extra) > 0:
            content += f"│  ➕ Extra    : ₹{int(extra):,}/person/night\n"
        content += "└─────────────────────────\n\n"

        buttons.append({"text": f"🛏️ Room {i + 1} — {cat}", "value": f"pick_room:{i}"})

    buttons.append({"text": "◀ Other Hotels", "value": "other_hotels"})
    content += "👇 Select a room to continue:"
    return {"type": "buttons_grid", "content": content, "buttons": buttons}


def card_hotel_summary(context: Dict) -> Dict:
    """Final hotel booking summary card."""
    price       = context.get("price_details", {})
    meal        = context.get("meal_details", {})
    room        = context.get("selected_room_data", {})
    grand_total = price.get("grand_total", 0) + meal.get("total_meal_price", 0)

    nights   = price.get("nights", 0)
    rooms_n  = price.get("rooms_needed", 1)
    dest     = context.get("destination", "")
    check_in = context.get("check_in", "")
    check_out= context.get("check_out", "")
    guests   = context.get("guests", "")

    content  = _section_header("Booking Summary", "📋")

    # Trip info block
    content += _row("Destination", dest, "📍")
    content += _row("Dates", f"{check_in}  →  {check_out}", "📅")
    content += _row("Nights", str(nights), "🌙")
    content += _row("Guests", str(guests), "👥")
    content += "\n"

    # Hotel block
    content += _section_header("Hotel Details", "🏨")
    content += _row("Hotel", context.get("selected_hotel", ""), "🏩")
    content += _row("Room", f"{room.get('category', '')} — {room.get('type', '')}", "🚪")
    content += _row("Rooms Booked", str(rooms_n), "🔑")
    content += "\n"

    # Price block
    content += _section_header("Price Details", "💰")
    content += _row("Room Cost",  f"₹{price.get('grand_total', 0):,.2f}", "🏠")
    content += _row("Meal Plan",  meal.get('meal_name', 'No meals'), "🍽️")
    content += _row("Meal Cost",  f"₹{meal.get('total_meal_price', 0):,.2f}", "🍴")
    content += _divider()
    content += f"💵 *GRAND TOTAL:  ₹{grand_total:,.2f}*\n\n"
    content += "Please confirm your booking 👇"

    return {
        "type": "buttons",
        "content": content,
        "buttons": [
            {"text": "✅ BOOK NOW",      "value": "confirm"},
            {"text": "🍽️ Change Meal",   "value": "change_meal"},
            {"text": "🏨 Other Hotels",  "value": "other_hotels"},
        ],
    }


 

def card_pkg_packages(context: Dict) -> Dict:
    """Available packages listing card."""
    pkgs = context.get("packages_list", [])
    dest = context.get("destination", "")

    content  = _section_header(f"Packages for {dest}", "✈️")

    buttons = []
    for i, pkg in enumerate(pkgs[:6]):
        name = pkg.get("package_name") or pkg.get("title", "Package")
        nights = len(pkg.get("itinerary", []))

        content += f"┌─ *{i + 1}. {name}*\n"
        if nights:
            content += f"│  🌙 {nights} Nights\n"
        content += "└─────────────────────────\n\n"

        buttons.append({"text": f"📦 Package {i + 1}", "value": f"select_package_{i}"})

    content += "👇 Select a package to view details:"
    return {"type": "buttons_grid", "content": content, "buttons": buttons}


def card_pkg_full_details(context: Dict) -> Dict:
    """Full package details with itinerary + price breakdown cards."""
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

    pkg_name = pkg.get("package_name") or pkg.get("title", "Package")

    # ── Package header card ──
    content  = _section_header("Package Details", "📦")
    content += _row("Package",       pkg_name,                        "🗺️")
    content += _row("Destination",   context.get("destination", ""),  "📍")
    content += _row("Dates",         f"{context.get('check_in')}  →  {context.get('check_out')}", "📅")
    content += _row("Nights",        str(nights),                     "🌙")
    content += _row("Guests",        str(guests),                     "👥")
    content += _row("Hotel Cat.",    context.get("hotel_category", ""), "🏨")
    content += _row("Room Cat.",     context.get("room_category", ""),  "🚪")
    veh_str = vehicle_name
    if vehicle_price > 0:
        veh_str += f"  ({fp(vehicle_price)} flat)"
    content += _row("Vehicle",       veh_str,                         "🚗")
    content += "\n"

    # ── Itinerary cards ──
    content += _section_header("Itinerary", "🗓️")
    for i, day in enumerate(itinerary[:nights], 1):
        title      = day.get("title", f"Day {i}")
        loc        = day.get("stay_location") or day.get("location", context.get("destination", "N/A"))
        hotel_name = selected_hotels.get(loc, context.get("hotel_category", "Hotel"))

        content += f"┌─ *Day {i}* — {title}\n"
        content += f"│  📍 {loc}\n"
        content += f"│  🏨 {hotel_name}\n"
        content += f"│  🚗 {vehicle_name}\n"
        content += "└─────────────────────────\n\n"

    # ── Hotel price breakdown cards ──
    content += _section_header("Price Breakdown", "💰")
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

        content += f"┌─ *🏨 Hotel at {loc}*\n"
        content += f"│  Name   : {h_name}\n"
        content += f"│  Room   : {room_cat}\n"
        content += f"│  Season : {season}\n"
        content += f"│  Rooms  : {rooms_n}  (cap: {min_c}–{max_c} guests)\n"
        content += f"│  Rate   : {fp(price_room)}/night\n"
        if extra_p > 0:
            content += f"│  Extra  : {extra_p} pax @ {fp(extra_pr)}/night\n"
        content += f"│  🏠 Hotel Total : {fp(h_total)}\n"
        content += f"│  🍽️  MAP Meal   : {fp(map_total)}\n"
        content += "└─────────────────────────\n\n"

    # ── Totals card ──
    content += _section_header("Cost Summary", "🧾")
    content += _row("Hotel Subtotal", fp(total_hotel),    "🏠")
    content += _row("MAP Meal",       fp(total_map),      "🍽️")
    if vehicle_price > 0:
        content += _row("Vehicle",    fp(vehicle_price),  "🚗")
    if package_margin > 0:
        content += _row("Margin",     fp(package_margin), "📊")
    content += _divider()
    content += f"💵 *TOTAL PACKAGE:  {fp(total_price)}*\n"
    content += "🍽️  Meal: MAP (Breakfast + Dinner included)\n\n"
    content += "👇 Please select an option:"

    return {
        "type": "buttons",
        "content": content,
        "buttons": [
            {"text": "✅ BOOK NOW",        "value": "pkg_book_now"},
            {"text": "🚗 Change Vehicle",  "value": "pkg_change_vehicle"},
            {"text": "🏨 Change Hotel",    "value": "pkg_change_hotel"},
            {"text": "📦 Other Packages", "value": "pkg_other_packages"},
        ],
    }


def card_pkg_final_summary(context: Dict) -> Dict:
    """Final package confirmation summary card."""
    pd          = context.get("pkg_price_details", {})
    total_price = pd.get("total_price", 0)
    pkg_name    = context.get("selected_package", {}).get("package_name", "Package")
    vehicle     = context.get("vehicle", {})

    content  = _section_header("Booking Confirmation", "📋")
    content += _row("Package",      pkg_name,                                          "📦")
    content += _row("Destination",  context.get("destination", ""),                    "📍")
    content += _row("Dates",        f"{context.get('check_in')}  →  {context.get('check_out')}", "📅")
    content += _row("Guests",       str(context.get("guests", "")),                    "👥")
    content += _row("Hotel Cat.",   context.get("hotel_category", ""),                 "🏨")
    content += _row("Room Cat.",    context.get("room_category", ""),                  "🚪")
    content += _row("Vehicle",      vehicle.get("name", "None"),                       "🚗")
    content += "\n"
    content += _section_header("Price", "💰")
    content += _row("Meal Plan",    "MAP (Breakfast + Dinner)",                        "🍽️")
    content += _divider()
    content += f"💵 *TOTAL:  {fp(total_price)}*\n\n"
    content += "✅ Ready to confirm your booking? 👇"

    return {
        "type": "buttons",
        "content": content,
        "buttons": [
            {"text": "✅ Confirm Booking", "value": "pkg_confirm_package"},
            {"text": "🚗 Change Vehicle",  "value": "pkg_change_vehicle"},
            {"text": "🏨 Change Hotel",    "value": "pkg_change_hotel"},
            {"text": "📦 Other Packages", "value": "pkg_other_packages"},
        ],
    }