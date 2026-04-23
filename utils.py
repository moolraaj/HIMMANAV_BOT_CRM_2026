# utils.py

import re
from datetime import datetime

PACKAGES_PER_PAGE = 2

def calculate_per_person_price(package_price, adults, children):
    """Calculate per person price based on travelers"""
    try:
        total_price = float(package_price) if package_price else 0
        total_people = adults + (children * 0.5)
        if total_people > 0:
            per_person = total_price / total_people
            return f"₹{int(per_person):,}"
    except:
        pass
    return "Contact for price"

def clean_text(text):
    """Clean text by removing special characters and extra spaces"""
    if not text:
        return ""
    text = re.sub(r'\s+', ' ', str(text))
    text = re.sub(r'[^\w\s\-.,!?]', '', text)
    return text.strip()

def clean_itinerary_text(text):
    """Clean itinerary text by removing HTML tags and formatting properly"""
    if not text:
        return ""
    cleaned = re.sub(r'<[^>]+>', '\n', text)
    cleaned = re.sub(r'&[a-z]+;', '', cleaned)
    cleaned = re.sub(r'&#\d+;', '', cleaned)
    cleaned = re.sub(r'style="[^"]*"', '', cleaned)
    cleaned = re.sub(r'class="[^"]*"', '', cleaned)
    cleaned = re.sub(r'&#8217;', "'", cleaned)
    cleaned = re.sub(r'&quot;', '"', cleaned)
    cleaned = re.sub(r'&amp;', '&', cleaned)
    lines = []
    for line in cleaned.split('\n'):
        line = line.strip()
        if not line:
            continue
        line = re.sub(r'\s+', ' ', line)
        line = re.sub(r'[•●■]', '•', line)
        lines.append(line)
    return '\n'.join(lines)

def format_itinerary_for_display(itinerary_items):
    """Format itinerary items for display in WhatsApp"""
    if not itinerary_items:
        return "📅 *Itinerary:*\nContact us for detailed itinerary."

    formatted = []
    formatted.append("📅 *COMPLETE ITINERARY:*")
    formatted.append("")

    if isinstance(itinerary_items, str):
        cleaned = clean_itinerary_text(itinerary_items)
        day_pattern = r'Day\s+(\d+)[:\s]+([^\n]+)'
        parts = re.split(day_pattern, cleaned)
        for i in range(1, len(parts), 3):
            if i + 2 < len(parts):
                day_num = parts[i]
                title = parts[i + 1].strip()
                content = parts[i + 2].strip()
                formatted.append(f"*Day {day_num}: {title}*")
                formatted.append("")
                bullet_points = re.findall(r'[•●\-]\s*([^\n]+)', content)
                if not bullet_points:
                    lines = content.split('\n')
                    for line in lines:
                        if line.strip():
                            bullet_points.append(line.strip())
                for point in bullet_points:
                    point = re.sub(r'\s+', ' ', point.strip())
                    if point:
                        formatted.append(f"  • {point}")
                formatted.append("")
                formatted.append("━━━━━━━━━━━━━━━━━━━━━━")
                formatted.append("")
        return '\n'.join(formatted)

    if isinstance(itinerary_items, list):
        for idx, day in enumerate(itinerary_items, 1):
            if isinstance(day, dict):
                title = day.get('title', f'Day {idx}')
                description = day.get('description', '')
            else:
                title = f"Day {idx}"
                description = str(day)
            clean_desc = clean_itinerary_text(description)
            formatted.append(f"*Day {idx}: {title}*")
            formatted.append("")
            if clean_desc:
                for line in clean_desc.split('\n'):
                    if line.strip():
                        if not line.startswith('•'):
                            formatted.append(f"  • {line.strip()}")
                        else:
                            formatted.append(f"  {line.strip()}")
            formatted.append("")
            formatted.append("━━━━━━━━━━━━━━━━━━━━━━")
            formatted.append("")
        return '\n'.join(formatted)

    return str(itinerary_items)

def safe_price(pkg):
    """Safely extract price from package"""
    try:
        return int(pkg.get("package_price", 0))
    except (ValueError, TypeError):
        return 0

def filter_packages_by_destinations(packages, destinations):
    """Filter packages by destination list"""
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
        pkg_name_lower = clean_text(pkg.get('package_name', '')).lower()

        is_match = False
        for user_dest in dest_list:
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

def filter_hotels_by_destinations(hotels, destinations):
    """Filter hotels by destination list"""
    if not destinations or not hotels:
        return []

    dest_list = [d.lower().strip() for d in (
        [destinations] if isinstance(destinations, str) else destinations
    ) if d]

    matched = []
    seen_ids = set()

    for hotel in hotels:
        hotel_id = hotel.get('id')
        if hotel_id in seen_ids:
            continue
        hotel_location = str(hotel.get('hotel_location', '')).lower().strip()
        hotel_name_lower = clean_text(hotel.get('hotel_name', '')).lower()

        is_match = False
        for user_dest in dest_list:
            if user_dest in hotel_location or hotel_location in user_dest:
                is_match = True
                break
            if user_dest in hotel_name_lower:
                is_match = True
                break

        if is_match:
            seen_ids.add(hotel_id)
            matched.append(hotel)

    return matched

def create_summary(context):
    """Create travel summary text"""
    travel_dates = context.get("travel_dates", "Not specified")
    travellers = context.get("travellers", "Not specified")
    destinations = context.get("destinations", [])
    dest_text = ", ".join(destinations) if isinstance(destinations, list) else str(destinations)
    duration = context.get("duration_text", "")

    lines = [
        "📋 *Your Travel Plan:*",
        "━━━━━━━━━━━━━━━━━━━━━━",
        f"📅 *Dates:* {travel_dates}",
    ]
    if duration:
        lines.append(f"⏳ *Duration:* {duration}")
    lines.append(f"👥 *Travelers:* {travellers}")
    lines.append(f"🗺️ *Destination:* {dest_text}")
    lines.append("━━━━━━━━━━━━━━━━━━━━━━")
    return "\n".join(lines)

def get_next_batch(items, current_page, items_per_page=PACKAGES_PER_PAGE):
    """Get next batch of items for pagination"""
    start_idx = current_page * items_per_page
    end_idx = start_idx + items_per_page
    return items[start_idx:end_idx]

def has_more_items(items, current_page, items_per_page=PACKAGES_PER_PAGE):
    """Check if there are more items to load"""
    return (current_page + 1) * items_per_page < len(items)

def get_remaining_count(items, current_page, items_per_page=PACKAGES_PER_PAGE):
    """Get count of remaining items"""
    total_shown = (current_page + 1) * items_per_page
    return max(0, len(items) - total_shown)

def build_navigation_buttons(has_more, remaining_count, items_per_page=PACKAGES_PER_PAGE):
    """Build navigation buttons based on remaining items"""
    nav_buttons = []

    if has_more:
        next_count = min(items_per_page, remaining_count)
        nav_buttons.append({"text": f"Load More ({next_count})", "value": "load_more"})

    nav_buttons.extend([
        {"text": "New Search", "value": "start_search"},
        {"text": "Find Hotels", "value": "start_hotel_search"},
        {"text": "Main Menu", "value": "main_menu"},
        {"text": "Exit", "value": "exit"},
    ])

    return nav_buttons

def validate_dates(start_date, end_date):
    """Validate travel dates"""
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    max_allowed_date = today.replace(year=today.year + 2)

    if start_date and start_date < today:
        return False, f"*{start_date.strftime('%d %B %Y')}* is already in the past!"

    if start_date and start_date > max_allowed_date:
        return False, f"*{start_date.strftime('%d %B %Y')}* is too far in the future!"

    if end_date and start_date and start_date > end_date:
        return False, "Start date is after end date!"

    return True, None

def validate_duration(days, nights):
    """Validate tour duration — max 60 days and 60 nights"""
    if days is not None:
        if days < 1:
            return False, "Days must be at least 1."
        if days > 60:
            return False, "Tour duration cannot exceed 60 days."
    if nights is not None:
        if nights < 0:
            return False, "Nights cannot be negative."
        if nights > 60:
            return False, "Tour duration cannot exceed 60 nights."
    return True, None

def create_new_state(old_state, step, context):
    """Create new state preserving all important keys"""
    return {
        "step": step,
        "search_mode": old_state.get("search_mode", "package"),
        "context": context,
        "packages": old_state.get("packages", []),
        "filtered_packages": old_state.get("filtered_packages", []),
        "current_page": old_state.get("current_page", 0),
        "hotels": old_state.get("hotels", []),
        "filtered_hotels": old_state.get("filtered_hotels", []),
        "hotel_page": old_state.get("hotel_page", 0),
        "user_phone": old_state.get("user_phone", ""),
        "partner_email": old_state.get("partner_email", ""),
    }

def create_fresh_state(old_state):
    """
    Create a fresh search state — but KEEP location/context so the session
    is not broken. Only clears search-specific context (dates, pax, duration)
    while preserving destinations and cached packages/hotels.
    """
    old_context = old_state.get("context", {})
    
    preserved_context = {}
    if old_context.get("destinations"):
        preserved_context["destinations"] = old_context["destinations"]

    return {
        "context": preserved_context,
        "packages": old_state.get("packages", []),
        "hotels": old_state.get("hotels", []),
        "filtered_packages": old_state.get("filtered_packages", []),
        "filtered_hotels": old_state.get("filtered_hotels", []),
        "current_page": 0,
        "hotel_page": 0,
        "user_phone": old_state.get("user_phone", ""),
        "partner_email": old_state.get("partner_email", ""),
        "step": "greeting",
        "search_mode": old_state.get("search_mode", "package"),
    }

def create_exit_state(old_state):
    """Create exit state — completely reset the session"""
    return {
        "step": "greeting",
        "context": {},
        "packages": [],
        "hotels": [],
        "user_phone": "",
        "search_mode": "package",
        "filtered_packages": [],
        "filtered_hotels": [],
        "current_page": 0,
        "hotel_page": 0,
        "partner_email": "",
    }