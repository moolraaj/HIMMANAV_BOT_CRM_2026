from typing import Dict, List, Optional
import json

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
# HOTEL FLOW CARDS  (unchanged)
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
    """
    Hotel listing - returns a list of cards, each card = image + hotel details + single button.
    """
    hotels   = context.get("hotels_list", [])[:8]
    category = context.get("selected_category", "")
    dest     = context.get("destination", "")

    responses = []

    for i, hotel in enumerate(hotels):
        name      = hotel.get("name", "Unknown")
        location  = hotel.get("location", "N/A")
        desc      = hotel.get("description", "")
        image_url = hotel.get("image", "")

        caption  = f"\n*{name}*"
        caption += f"\n*Hotel Location* {location}"
        caption += f"\n*Hotel Category* {category}"

        if image_url and image_url.startswith(('http://', 'https://')):
            responses.append({
                "type": "image",
                "content": image_url,
                "caption": caption,
                "buttons": [
                    {"text": "View Rooms",          "value": f"view_rooms:{name}"},
                    {"text": "Back to Categories",  "value": "back_to_categories"},
                    {"text": "Change City",         "value": "change_city"},
                ]
            })
        else:
            text_content  = f"*{i + 1}. {name}*\n"
            text_content += f"*Location:* {location}\n"
            if desc:
                text_content += f"{desc[:100]}{'...' if len(desc) > 100 else ''}\n"
            text_content += f"\n*Category:* {category}\n"
            responses.append({
                "type": "buttons",
                "content": text_content,
                "buttons": [
                    {"text": "View Rooms",         "value": f"view_rooms:{name}"},
                    {"text": "Back to Categories", "value": "back_to_categories"},
                    {"text": "Change City",        "value": "change_city"},
                ]
            })

    return {"type": "multi", "responses": responses}


def card_hotel_rooms(context: Dict) -> Dict:
    """
    Room listing - each room with image + room details + button.
    Shows seasonal pricing based on user's check-in date.
    """
    rooms        = context.get("rooms_list", [])[:6]
    hotel_name   = context.get("selected_hotel", "Hotel")
    check_in_str = context.get("check_in", "")

    def get_seasonal_price(room: Dict, check_in_date: str) -> tuple:
        from datetime import datetime
        base_price = float(room.get("base_price", 0))
        base_extra = float(room.get("extra_person_price", 0))
        if not check_in_date:
            return base_price, base_extra, "Standard Rate"
        try:
            check_in = datetime.strptime(check_in_date, "%Y-%m-%d")
            seasons  = room.get("seasons", [])
            for season in seasons:
                start_date_str = season.get("starting_date", "")
                end_date_str   = season.get("end_date", "")
                if not start_date_str or not end_date_str:
                    continue
                try:
                    season_start = datetime.strptime(start_date_str, "%d-%m-%Y")
                    season_end   = datetime.strptime(end_date_str,   "%d-%m-%Y")
                    if season_start <= check_in <= season_end:
                        season_price = float(season.get("price", base_price))
                        season_extra = float(season.get("extra_price", base_extra))
                        season_name  = season.get("season_name", "Seasonal Rate")
                        return season_price, season_extra, season_name
                except ValueError:
                    continue
            return base_price, base_extra, "Standard Rate"
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"Season price error: {e}")
            return base_price, base_extra, "Standard Rate"

    responses = []

    for i, room in enumerate(rooms):
        cat     = room.get("room_category", room.get("category", ""))
        rtype   = room.get("room_type",     room.get("type", ""))
        min_cap = room.get("minimum_capacity", "?")
        max_cap = room.get("maximum_capacity", "?")

        price, extra_price, season_name = get_seasonal_price(room, check_in_str)

        room_images = room.get("room_images", [])
        if not room_images:
            room_images = room.get("images", [])
        if not room_images:
            room_images = room.get("gallery", [])

        caption  = f" Room In  *({hotel_name}) Hotel*\n"
        caption += f"*Room Category* {cat}\n"
        caption += f"*Room Type* {rtype}\n"
        caption += f"*Min Capacity* {min_cap} guests\n"
        caption += f"*Max Capacity* {max_cap} guests\n"
        caption += f"*Price:* Rs.{int(price):,}/night\n"
        if extra_price and int(extra_price) > 0:
            caption += f"*Extra Person:* Rs.{int(extra_price):,}/night\n"

        facilities = room.get("facilities", [])
        if facilities:
            facilities_str = ", ".join(facilities[:3])
            if len(facilities) > 3:
                facilities_str += f" +{len(facilities) - 3} more"
            caption += f"\n*Room Facilities:*\n{facilities_str}\n"

        if room_images and len(room_images) > 0:
            first_image = room_images[0]
            if first_image and first_image.startswith(('http://', 'https://')):
                responses.append({
                    "type": "image",
                    "content": first_image,
                    "caption": caption,
                    "buttons": [
                        {"text": f"Select Room {i + 1}", "value": f"pick_room:{i}"},
                        {"text": "Other Hotels",         "value": "other_hotels"},
                    ]
                })
                continue

        text_content  = f"*{hotel_name}*\n"
        text_content += f"*Room {i + 1}: {cat} — {rtype}*\n\n"
        text_content += f"*Capacity:* {min_cap}-{max_cap} guests\n"
        if season_name != "Standard Rate":
            text_content += f"*Season:* {season_name}\n"
        text_content += f"*Price:* Rs.{int(price):,}/night\n"
        if extra_price and int(extra_price) > 0:
            text_content += f"*Extra Person:* Rs.{int(extra_price):,}/night\n"
        if facilities:
            facilities_str = ", ".join(facilities[:3])
            if len(facilities) > 3:
                facilities_str += f" +{len(facilities) - 3} more"
            text_content += f"*Facilities:* {facilities_str}\n"

        responses.append({
            "type": "buttons",
            "content": text_content,
            "buttons": [
                {"text": f"Select Room {i + 1}", "value": f"pick_room:{i}"},
                {"text": "Other Hotels",         "value": "other_hotels"},
            ]
        })

    return {"type": "multi", "responses": responses}


def card_hotel_summary(context: Dict) -> Dict:
    """Final hotel booking summary card with full price breakdown."""
    price       = context.get("price_details", {})
    meal        = context.get("meal_details", {})
    room        = context.get("selected_room_data", {})
    grand_total = price.get("grand_total", 0) + meal.get("total_meal_price", 0)

    nights        = price.get("nights", 0)
    rooms_n       = price.get("rooms_needed", 1)
    extra_persons = price.get("extra_people", 0)
    room_total    = price.get("room_total", 0)
    extra_total   = price.get("extra_total", 0)
    base_price    = price.get("price_per_night_per_room", 0)
    extra_price   = price.get("extra_price_per_night", 0)

    dest       = context.get("destination", "")
    check_in   = context.get("check_in", "")
    check_out  = context.get("check_out", "")
    guests     = context.get("guests", "")
    hotel_name = context.get("selected_hotel", "")

    content  = _section_header("Booking Summary")
    content += _row("Destination", dest)
    content += _row("Dates",   f"{check_in}  to  {check_out}")
    content += _row("Nights",  str(nights))
    content += _row("Guests",  str(guests))
    content += "\n"

    content += _section_header("Hotel Details")
    content += _row("Hotel", hotel_name)
    content += _row("Room",  f"{room.get('room_category', room.get('category', ''))} — {room.get('room_type', room.get('type', ''))}")
    content += _row("Rooms Booked", str(rooms_n))
    if extra_persons > 0:
        content += _row("Extra Persons", str(extra_persons))
    content += "\n"

    content += _section_header("Price Details")
    content += _row(f"Room Cost ({rooms_n} rooms × {nights} nights)", f"Rs.{room_total:,.0f}")
    if extra_persons > 0:
        content += _row(
            f"Extra Person Cost ({extra_persons} persons × {nights} nights @ Rs.{int(extra_price):,}/night)",
            f"Rs.{extra_total:,.0f}"
        )
    content += _row("Meal Plan", meal.get("meal_name", "No meals"))
    content += _row("Meal Cost", f"Rs.{meal.get('total_meal_price', 0):,.0f}")
    content += "\n"
    content += f"*GRAND TOTAL:  Rs.{grand_total:,.0f}*\n\n"
    content += "\nPlease confirm your booking"

    return {
        "type": "buttons",
        "content": content,
        "buttons": [
            {"text": "BOOK NOW",     "value": "confirm"},
            {"text": "Change Meal",  "value": "change_meal"},
            {"text": "Other Hotels", "value": "other_hotels"},
        ],
    }


# ═══════════════════════════════════════════════════════════════════════════════
# PACKAGE FLOW CARDS
# ═══════════════════════════════════════════════════════════════════════════════

def card_pkg_packages(context: Dict) -> Dict:
    """Package listing - each package as its own card."""
    pkgs = context.get("packages_list", [])[:6]
    dest = context.get("destination", "")
    responses = []

    for i, pkg in enumerate(pkgs):
        name      = pkg.get("package_name") or pkg.get("title", "Package")
        image_url = pkg.get("package_image", "")
        locations = pkg.get("locations", [])
        location_str = ", ".join(locations[:3]) if locations else dest
        if len(locations) > 3:
            location_str += f" +{len(locations) - 3} more"
        itinerary = pkg.get("itinerary", [])
        nights    = max(len(itinerary) - 1, 1) if itinerary else 0

        caption  = f"\n*{name}*\n"
        caption += f"\n*Destinations:* {location_str}\n"
        if nights > 0:
            caption += f"\n*Duration:* {nights} Nights\n"

        if image_url and image_url.startswith(('http://', 'https://')):
            responses.append({
                "type": "image",
                "content": image_url,
                "caption": caption,
                "buttons": [{"text": "View Package", "value": f"select_package_{i}"}]
            })
        else:
            text_content  = f"*{i + 1}. {name}*\n\n"
            text_content += f"*Destinations:* {location_str}\n"
            if nights > 0:
                text_content += f"*Duration:* {nights} Nights\n"
            responses.append({
                "type": "buttons",
                "content": text_content,
                "buttons": [{"text": "View Package", "value": f"select_package_{i}"}]
            })

    return {"type": "multi", "responses": responses}


def card_pkg_summary(context: Dict) -> Dict:
    """
    Package summary — shows:
    - Booking summary (package name, destination, start date, auto-derived end date, nights, guests)
    - Package details (hotel cat, room cat, vehicle)
    - Itinerary (per day: location, hotel, season used, vehicle)
    - Price breakdown (hotel cost per location with season, MAP meal, vehicle, margin)
    - Grand total
    """
    pd             = context.get("pkg_price_details", {})
    nights         = pd.get("nights", 0)
    total_price    = pd.get("total_price", 0)
    total_hotel    = pd.get("total_hotel_price", 0)
    total_map      = pd.get("total_map_price", 0)
    vehicle_price  = pd.get("vehicle_price", 0)          # total (per_day × nights)
    vehicle_per_day = pd.get("vehicle_price_per_day", 0)
    vehicle_season  = pd.get("vehicle_season_name", "")
    vehicle_name   = pd.get("vehicle_name", "None")
    package_margin = pd.get("package_margin", 0)
    guests         = pd.get("guests", 1)
    selected_hotels = pd.get("selected_hotels", {})
    hotel_costs    = pd.get("hotel_costs", [])

    pkg       = context.get("selected_package", {})
    pkg_name  = pkg.get("package_name") or pkg.get("title", "Package")
    itinerary = pkg.get("itinerary", [])

    # Use dates from pkg_price_details (most up-to-date) or context fallback
    check_in  = pd.get("check_in",  context.get("check_in",  ""))
    check_out = pd.get("check_out", context.get("check_out", ""))
    dest      = context.get("destination", "")

    # Build a quick season-name lookup by location
    season_by_location = {}
    for hc in hotel_costs:
        loc  = hc.get("location", "")
        sn   = hc.get("season_name", "")
        if loc and sn:
            season_by_location[loc] = sn

    # ── Booking Summary ───────────────────────────────────────────
    content  = _section_header("Booking Summary")
    content += _row("Package",        pkg_name)
    content += _row("Destination",    dest)
    content += _row("Start Date",     check_in)
    content += _row("End Date",       check_out)
    content += _row("Nights",         str(nights))
    content += _row("Guests",         str(guests))
    content += "\n"

    # ── Package Details ───────────────────────────────────────────
    content += _section_header("Package Details")
    content += _row("Hotel Category", context.get("hotel_category", ""))
    content += _row("Room Category",  context.get("room_category", ""))
    if vehicle_price > 0:
        content += _row("Vehicle", f"{vehicle_name}  ({fp(vehicle_per_day)}/day)")
        if vehicle_season and vehicle_season not in ("Regular Rate", ""):
            content += _row("Vehicle Season", vehicle_season)
    else:
        content += _row("Vehicle", "None")
    content += "\n"

    # ── Itinerary ─────────────────────────────────────────────────
    content += _section_header("Itinerary")
    shown_days = 0
    for i, day in enumerate(itinerary):
        day_label = day.get("day", f"Day {i}")
        title     = day.get("title", "")
        loc       = day.get("stay_location") or day.get("location", dest)
        hotel_name = selected_hotels.get(loc, context.get("hotel_category", "Hotel"))
        season    = season_by_location.get(loc, "")

        content += f"*{day_label}:* {title}\n"
        content += f"  *Location:* {loc}\n"
        content += f"  *Hotel:* {hotel_name}\n"
        if season and season != "N/A":
            content += f"  *Season:* {season}\n"
        content += f"  *Vehicle:* {vehicle_name}\n"
        content += "\n"
        shown_days += 1

    # ── Price Breakdown per Location ──────────────────────────────
    content += _section_header("Price Details")

    if hotel_costs:
        for hc in hotel_costs:
            loc        = hc.get("location", "")
            h_name     = hc.get("hotel_name", "")
            season_nm  = hc.get("season_name", "Regular Rate")
            price_room = hc.get("price_per_room", 0)
            rooms_n    = hc.get("rooms_needed", 0)
            extra_p    = hc.get("extra_persons_total", 0)
            extra_pr   = hc.get("extra_person_price", 0)
            h_total    = hc.get("hotel_total", 0)

            content += f"*{loc} — {h_name}*\n"
            content += f"  Season: {season_nm}\n"
            content += f"  Rs.{int(price_room):,}/night × {rooms_n} room(s) × {nights} nights"
            if extra_p > 0:
                content += f" + {extra_p} extra person(s) @ Rs.{int(extra_pr):,}/night"
            content += f" = *{fp(h_total)}*\n"
        content += "\n"

    content += _row(f"Total Hotel Cost ({nights} nights)", fp(total_hotel))
    content += _row("MAP Meal (Breakfast + Dinner)",        fp(total_map))
    if vehicle_price > 0:
        v_line = f"{fp(vehicle_per_day)}/day × {nights} nights = {fp(vehicle_price)}"
        if vehicle_season and vehicle_season not in ("Regular Rate", ""):
            v_line += f"  _(Season: {vehicle_season})_"
        content += _row(f"Vehicle Cost ({vehicle_name})", v_line)
    if package_margin > 0:
        content += _row("Service Charge", fp(package_margin))
    content += "\n"
    content += f"*GRAND TOTAL:  {fp(total_price)}*\n\n"

    # ── Cards ─────────────────────────────────────────────────────
    card_summary = {
        "type": "text",
        "content": content,
    }

    card_actions = {
        "type": "buttons",
        "content": "Please confirm your booking",
        "buttons": [
            {"text": "BOOK NOW",       "value": "pkg_book_now"},
            {"text": "Change Vehicle", "value": "pkg_change_vehicle"},
        ],
    }

    card_options = {
        "type": "buttons",
        "content": "More options",
        "buttons": [
            {"text": "📄 Generate PDF", "value": "pkg_generate_pdf"},
            {"text": "Other Packages",  "value": "pkg_other_packages"},
        ],
    }

    return {"type": "multi", "responses": [card_summary, card_actions, card_options]}


def card_vehicles_list(context: Dict) -> Dict:
    """Vehicle listing - same pattern as card_hotel_rooms."""
    vehicles         = context.get("vehicles_list", [])
    vehicle_category = context.get("vehicle_category", "Vehicle")
    check_in_str     = context.get("check_in", "")

    def get_vehicle_seasonal_price(vehicle: Dict, check_in_date: str) -> tuple:
        from datetime import datetime
        base_price = float(str(vehicle.get("price", "0")).replace(",", ""))
        if not check_in_date:
            return base_price, "Standard Rate"
        try:
            check_in = datetime.strptime(check_in_date, "%Y-%m-%d")
            seasons  = vehicle.get("seasons", [])
            for season in seasons:
                start_date_str = season.get("starting_date", "")
                end_date_str   = season.get("end_date", "")
                if not start_date_str or not end_date_str:
                    continue
                try:
                    season_start = datetime.strptime(start_date_str, "%d-%m-%Y")
                    season_end   = datetime.strptime(end_date_str,   "%d-%m-%Y")
                    if season_start <= check_in <= season_end:
                        season_price = float(str(season.get("price", base_price)).replace(",", ""))
                        season_name  = season.get("season_name", "Seasonal Rate")
                        return season_price, season_name
                except ValueError:
                    continue
            return base_price, "Standard Rate"
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"Vehicle season price error: {e}")
            return base_price, "Standard Rate"

    responses = []

    for i, vehicle in enumerate(vehicles):
        name      = vehicle.get("name", "Vehicle")
        capacity  = vehicle.get("seater_capacity", "")
        image_url = vehicle.get("image", "")

        price, season_name = get_vehicle_seasonal_price(vehicle, check_in_str)

        caption  = f"*{vehicle_category} Vehicle*\n"
        caption += f"*{name}*\n"
        caption += f"*Capacity:* {capacity} seater\n"
        caption += f"*Price:* Rs.{int(price):,}/trip\n"
        if season_name != "Standard Rate":
            caption += f"*Season:* {season_name}\n"

        if image_url and image_url.startswith(('http://', 'https://')):
            responses.append({
                "type": "image",
                "content": image_url,
                "caption": caption,
                "buttons": [{"text": "Select Vehicle", "value": f"select_vehicle_{i}"}]
            })
        else:
            text_content  = f"*{i + 1}. {name}*\n"
            text_content += f"*Capacity:* {capacity} seater\n"
            text_content += f"*Price:* Rs.{int(price):,}/trip\n"
            if season_name != "Standard Rate":
                text_content += f"*Season:* {season_name}\n"
            responses.append({
                "type": "buttons",
                "content": text_content,
                "buttons": [{"text": "Select Vehicle", "value": f"select_vehicle_{i}"}]
            })

    return {"type": "multi", "responses": responses}