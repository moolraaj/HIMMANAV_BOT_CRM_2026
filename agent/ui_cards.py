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
    """
    Hotel listing - returns a list of cards, each card = image + hotel details + single button.
    WhatsApp doesn't support multiple cards in one message, so we return a multi response
    where each hotel is its own message with image, details, and a "View Rooms" button.
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
        
        # Build the hotel details text (will be used as image caption)
        caption = f"\n*{name}*"
        caption += f"\n*Hotel Location* {location}"
        caption += f"\n*Hotel Category* {category}"
        
        # 
        if image_url and image_url.startswith(('http://', 'https://')):
            # Send as image with caption
            responses.append({
                "type": "image",
                "content": image_url,
                "caption": caption,
                "buttons": [{"text": "View Rooms", "value": f"view_rooms:{name}"},  {"text": "Back to Categories", "value": "back_to_categories"},
            {"text": "Change City", "value": "change_city"}]
            })
        else:
            # No image, send as text
            text_content = f"*{i + 1}. {name}*\n"
            text_content += f"*Location:* {location}\n"
            if desc:
                text_content += f"{desc[:100]}{'...' if len(desc) > 100 else ''}\n"
            text_content += f"\n*Category:* {category}\n"
            responses.append({
                "type": "buttons",
                "content": text_content,
                "buttons": [{"text": "View Rooms", "value": f"view_rooms:{name}"},  {"text": "Back to Categories", "value": "back_to_categories"},
            {"text": "Change City", "value": "change_city"}]
            })

     

    # Return multi response (multiple messages in sequence)
    return {"type": "multi", "responses": responses}


def card_hotel_rooms(context: Dict) -> Dict:
    """
    Room listing - each room with image + room details + button.
    Shows seasonal pricing based on user's check-in date.
    """
    rooms      = context.get("rooms_list", [])[:6]
    hotel_name = context.get("selected_hotel", "Hotel")
    check_in_str = context.get("check_in", "")
    
    # Helper function to parse date and find matching season
    def get_seasonal_price(room: Dict, check_in_date: str) -> tuple:
        """Returns (price, extra_price, season_name) based on check-in date."""
        from datetime import datetime
        
        # Default prices from room
        base_price = float(room.get("base_price", 0))
        base_extra = float(room.get("extra_person_price", 0))
        
        if not check_in_date:
            return base_price, base_extra, "Standard Rate"
        
        try:
            # Parse check-in date
            check_in = datetime.strptime(check_in_date, "%Y-%m-%d")
            
            # Get seasons list
            seasons = room.get("seasons", [])
            
            for season in seasons:
                start_date_str = season.get("starting_date", "")
                end_date_str = season.get("end_date", "")
                
                if not start_date_str or not end_date_str:
                    continue
                
                # Parse season dates (format: "01-04-2026")
                try:
                    season_start = datetime.strptime(start_date_str, "%d-%m-%Y")
                    season_end = datetime.strptime(end_date_str, "%d-%m-%Y")
                    
                    # Check if check-in date falls within season
                    if season_start <= check_in <= season_end:
                        season_price = float(season.get("price", base_price))
                        season_extra = float(season.get("extra_price", base_extra))
                        season_name = season.get("season_name", "Seasonal Rate")
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
        rtype   = room.get("room_type", room.get("type", ""))
        min_cap = room.get("minimum_capacity", "?")
        max_cap = room.get("maximum_capacity", "?")
        
        # Get seasonal pricing based on check-in date
        price, extra_price, season_name = get_seasonal_price(room, check_in_str)
        
        # Get room images
        room_images = room.get("room_images", [])
        if not room_images:
            room_images = room.get("images", [])
        if not room_images:
            room_images = room.get("gallery", [])
        
        # Build room details text
        caption = f" Room In  *({hotel_name}) Hotel*\n"
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
            caption += f"\n*Room Facilities:*\n"
            caption += f"{facilities_str}\n"
        
       
        if room_images and len(room_images) > 0:
            first_image = room_images[0]
            if first_image and first_image.startswith(('http://', 'https://')):
                responses.append({
                    "type": "image",
                    "content": first_image,
                    "caption": caption,
                    "buttons": [{"text": f"Select Room {i + 1}", "value": f"pick_room:{i}"}, {"text": "Other Hotels", "value": "other_hotels"}]
                })
                continue
        
       
        text_content = f"*{hotel_name}*\n"
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
            "buttons": [{"text": f"Select Room {i + 1}", "value": f"pick_room:{i}"}, {"text": "Other Hotels", "value": "other_hotels"}]
        })

    return {"type": "multi", "responses": responses}


def card_hotel_summary(context: Dict) -> Dict:
    """Final hotel booking summary card with full price breakdown."""
    price       = context.get("price_details", {})
    meal        = context.get("meal_details", {})
    room        = context.get("selected_room_data", {})
    grand_total = price.get("grand_total", 0) + meal.get("total_meal_price", 0)

    nights    = price.get("nights", 0)
    rooms_n   = price.get("rooms_needed", 1)
   
    extra_persons = price.get("extra_people", 0)
    room_total = price.get("room_total", 0)
    extra_total = price.get("extra_total", 0)
     
    base_price = price.get("price_per_night_per_room", 0)
     
    extra_price = price.get("extra_price_per_night", 0)
    
    dest      = context.get("destination", "")
    check_in  = context.get("check_in", "")
    check_out = context.get("check_out", "")
    guests    = context.get("guests", "")
    hotel_name = context.get("selected_hotel", "")

    content  = _section_header("Booking Summary")
    content += _row("Destination", dest)
    content += _row("Dates", f"{check_in}  to  {check_out}")
    content += _row("Nights", str(nights))
    content += _row("Guests", str(guests))
    content += "\n"

    content += _section_header("Hotel Details")
    content += _row("Hotel", hotel_name)
    content += _row("Room", f"{room.get('room_category', room.get('category', ''))} — {room.get('room_type', room.get('type', ''))}")
    content += _row("Rooms Booked", str(rooms_n))
    if extra_persons > 0:
        content += _row("Extra Persons", str(extra_persons))
    content += "\n"

    content += _section_header("Price Details")
    content += _row(f"Room Cost ({rooms_n} rooms × {nights} nights)", f"Rs.{room_total:,.0f}")
    if extra_persons > 0:
        content += _row(f"Extra Person Cost ({extra_persons} persons × {nights} nights @ Rs.{int(extra_price):,}/night)", f"Rs.{extra_total:,.0f}")
    content += _row("Meal Plan", meal.get("meal_name", "No meals"))
    content += _row("Meal Cost", f"Rs.{meal.get('total_meal_price', 0):,.0f}")
    content += "\n"
    content += f"*GRAND TOTAL:  Rs.{grand_total:,.0f}*\n\n"
    
    content += "\nPlease confirm your booking"

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
    """
    Package listing - each package as its own card with image + package details + button.
    Same design as hotel and room cards.
    """
    pkgs = context.get("packages_list", [])[:6]
    dest = context.get("destination", "")
    responses = []

    for i, pkg in enumerate(pkgs):
        name = pkg.get("package_name") or pkg.get("title", "Package")
        image_url = pkg.get("package_image", "")
        locations = pkg.get("locations", [])
        location_str = ", ".join(locations[:3]) if locations else dest
        if len(locations) > 3:
            location_str += f" +{len(locations) - 3} more"
        itinerary = pkg.get("itinerary", [])
        nights = len(itinerary)
        caption = f"\n*{name}*\n"
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
            text_content = f"*{i + 1}. {name}*\n\n"
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
    """Package summary - same UI format as hotel summary, with itinerary"""
    pd             = context.get("pkg_price_details", {})
    nights         = pd.get("nights", 0)
    total_price    = pd.get("total_price", 0)
    total_hotel    = pd.get("total_hotel_price", 0)
    total_map      = pd.get("total_map_price", 0)
    vehicle_price  = pd.get("vehicle_price", 0)
    vehicle_name   = pd.get("vehicle_name", "None")
    package_margin = pd.get("package_margin", 0)
    guests         = pd.get("guests", 1)
    selected_hotels= pd.get("selected_hotels", {})

    pkg      = context.get("selected_package", {})
    itinerary= pkg.get("itinerary", [])
    pkg_name = pkg.get("package_name") or pkg.get("title", "Package")
    check_in = context.get("check_in", "")
    check_out= context.get("check_out", "")
    dest     = context.get("destination", "")

   
    content  = _section_header("Booking Summary")
    content += _row("Package",     pkg_name)
    content += _row("Destination", dest)
    content += _row("Dates",       f"{check_in}  to  {check_out}")
    content += _row("Nights",      str(nights))
    content += _row("Guests",      str(guests))
    content += "\n"

     
    content += _section_header("Package Details")
    content += _row("Hotel Cat.", context.get("hotel_category", ""))
    content += _row("Room Cat.",  context.get("room_category", ""))
    content += _row("Vehicle",    vehicle_name if vehicle_price > 0 else "None")
    content += "\n"

    
    content += _section_header("Itinerary")
    for i, day in enumerate(itinerary[:nights], 1):
        title      = day.get("title", f"Day {i}")
        loc        = day.get("stay_location") or day.get("location", dest)
        hotel_name = selected_hotels.get(loc, context.get("hotel_category", "Hotel"))
        content += _row(f"Day {i}", title)
        content += _row("Location", loc)
        content += _row("Hotel",    hotel_name)
        content += _row("Vehicle",  vehicle_name)
        content += "\n"

    
    content += _section_header("Price Details")
    content += _row(f"Hotel Cost ({nights} nights)", fp(total_hotel))
    content += _row("MAP Meal (Breakfast + Dinner)",  fp(total_map))
    if vehicle_price > 0:
        content += _row("Vehicle Cost", fp(vehicle_price))
    if package_margin > 0:
        content += _row("Service Charge", fp(package_margin))
    content += "\n"
    content += f"*GRAND TOTAL:  {fp(total_price)}*\n\n"
    content += "\nPlease confirm your booking"

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

def card_vehicles_list(context: Dict) -> Dict:
    """
    Vehicle listing - EXACT same pattern as card_hotel_rooms
    Shows seasonal pricing based on user's check-in date.
    """
    vehicles = context.get("vehicles_list", [])
    vehicle_category = context.get("vehicle_category", "Vehicle")
    check_in_str = context.get("check_in", "")
    
     
    def get_vehicle_seasonal_price(vehicle: Dict, check_in_date: str) -> tuple:
        """Returns (price, season_name) based on check-in date - same as hotel rooms"""
        from datetime import datetime
        
        
        base_price = float(str(vehicle.get("price", "0")).replace(",", ""))
        
        if not check_in_date:
            return base_price, "Standard Rate"
        
        try:
            
            check_in = datetime.strptime(check_in_date, "%Y-%m-%d")
            
            
            seasons = vehicle.get("seasons", [])
            
            for season in seasons:
                start_date_str = season.get("starting_date", "")
                end_date_str = season.get("end_date", "")
                
                if not start_date_str or not end_date_str:
                    continue
                
                
                try:
                    season_start = datetime.strptime(start_date_str, "%d-%m-%Y")
                    season_end = datetime.strptime(end_date_str, "%d-%m-%Y")
                    
                 
                    if season_start <= check_in <= season_end:
                        season_price = float(str(season.get("price", base_price)).replace(",", ""))
                        season_name = season.get("season_name", "Seasonal Rate")
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
        name = vehicle.get("name", "Vehicle")
        capacity = vehicle.get("seater_capacity", "")
        image_url = vehicle.get("image", "")
        
      
        price, season_name = get_vehicle_seasonal_price(vehicle, check_in_str)
        
       
        caption = f"*{vehicle_category} Vehicle*\n"
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
                "buttons": [{"text": f"Select Vehicle", "value": f"select_vehicle_{i}"}]
            })
        else:
            text_content = f"*{i + 1}. {name}*\n"
            text_content += f"*Capacity:* {capacity} seater\n"
            text_content += f"*Price:* Rs.{int(price):,}/trip\n"
            if season_name != "Standard Rate":
                text_content += f"*Season:* {season_name}\n"
            responses.append({
                "type": "buttons",
                "content": text_content,
                "buttons": [{"text": f"Select Vehicle", "value": f"select_vehicle_{i}"}]
            })

    return {"type": "multi", "responses": responses}
