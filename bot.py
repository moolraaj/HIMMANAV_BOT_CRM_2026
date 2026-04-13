# bot.py
from services.api import fetch_packages
from services.llm import (
    understand_user,
    generate_package_details_for_display,
    generate_followup_questions,
    generate_activities_list,
    generate_vehicles_list,
    generate_inclusions_list,
    generate_hotels_list,
    generate_itinerary_list
)

def process_message(user_input, phone, state):
    """Main conversational bot function"""
    
    if not user_input or not user_input.strip():
        return {"type": "text", "content": "Please type something 😊"}
    
    user_lower = user_input.lower()
    current_step = state.get("step", "greeting")
    context = state.get("context", {})
    
    # Handle button clicks (package selection)
    if user_input.startswith("pkg_"):
        package_id = int(user_input.split("_")[1])
        packages = state.get("packages", [])
        
        # Find the selected package
        selected_package = None
        for pkg in packages:
            if pkg.get("id") == package_id:
                selected_package = pkg
                break
        
        if selected_package:
            # Show package details and ask followup questions
            details = generate_package_details_for_display(selected_package)
            followups = generate_followup_questions(selected_package)
            
            return {
                "type": "buttons",
                "content": details,
                "buttons": followups,
                "new_state": {
                    "step": "package_details",
                    "context": {"selected_package": selected_package}
                }
            }
    
    # Handle followup question clicks
    if user_input.startswith("followup_"):
        followup_type = user_input.split("_")[1]
        selected_package = context.get("selected_package", {})
        
        if followup_type == "activities":
            reply = generate_activities_list(selected_package)
            return {
                "type": "buttons",
                "content": reply,
                "buttons": [
                    {"text": "🏨 Hotels", "value": "followup_hotels"},
                    {"text": "🚗 Vehicles", "value": "followup_vehicles"},
                    {"text": "✅ Inclusions", "value": "followup_inclusions"},
                    {"text": "📅 Itinerary", "value": "followup_itinerary"},
                    {"text": "🔙 Back to Packages", "value": "back_to_packages"}
                ]
            }
        
        elif followup_type == "hotels":
            reply = generate_hotels_list(selected_package)
            return {
                "type": "buttons",
                "content": reply,
                "buttons": [
                    {"text": "🎯 Activities", "value": "followup_activities"},
                    {"text": "🚗 Vehicles", "value": "followup_vehicles"},
                    {"text": "✅ Inclusions", "value": "followup_inclusions"},
                    {"text": "📅 Itinerary", "value": "followup_itinerary"},
                    {"text": "🔙 Back to Packages", "value": "back_to_packages"}
                ]
            }
        
        elif followup_type == "vehicles":
            reply = generate_vehicles_list(selected_package)
            return {
                "type": "buttons",
                "content": reply,
                "buttons": [
                    {"text": "🎯 Activities", "value": "followup_activities"},
                    {"text": "🏨 Hotels", "value": "followup_hotels"},
                    {"text": "✅ Inclusions", "value": "followup_inclusions"},
                    {"text": "📅 Itinerary", "value": "followup_itinerary"},
                    {"text": "🔙 Back to Packages", "value": "back_to_packages"}
                ]
            }
        
        elif followup_type == "inclusions":
            reply = generate_inclusions_list(selected_package)
            return {
                "type": "buttons",
                "content": reply,
                "buttons": [
                    {"text": "🎯 Activities", "value": "followup_activities"},
                    {"text": "🏨 Hotels", "value": "followup_hotels"},
                    {"text": "🚗 Vehicles", "value": "followup_vehicles"},
                    {"text": "📅 Itinerary", "value": "followup_itinerary"},
                    {"text": "🔙 Back to Packages", "value": "back_to_packages"}
                ]
            }
        
        elif followup_type == "itinerary":
            reply = generate_itinerary_list(selected_package)
            return {
                "type": "buttons",
                "content": reply,
                "buttons": [
                    {"text": "🎯 Activities", "value": "followup_activities"},
                    {"text": "🏨 Hotels", "value": "followup_hotels"},
                    {"text": "🚗 Vehicles", "value": "followup_vehicles"},
                    {"text": "✅ Inclusions", "value": "followup_inclusions"},
                    {"text": "🔙 Back to Packages", "value": "back_to_packages"}
                ]
            }
    
    # Handle back to packages
    if user_input == "back_to_packages":
        packages = state.get("packages", [])
        if packages:
            return show_packages_with_buttons(packages, "Here are the packages again:")
    
    # Fetch packages
    packages = fetch_packages(phone)
    
    if not packages:
        return {"type": "text", "content": "⚠️ No packages available right now. Please try again later."}
    
    # Greeting step
    if current_step == "greeting" or user_lower in ["hi", "hello", "hey", "namaste", "hii"]:
        return {
            "type": "buttons",
            "content": "👋 Hi there! I'm your travel assistant. How can I help you with your travel journey today?",
            "buttons": [
                {"text": "📍 Find by Location", "value": "find_by_location"},
                {"text": "💰 Find by Budget", "value": "find_by_budget"},
                {"text": "🎯 Find by Activity", "value": "find_by_activity"},
                {"text": "📦 Show All Packages", "value": "show_all"}
            ],
            "new_state": {"step": "main_menu", "context": {"packages": packages}}
        }
    
    # Handle menu selections
    if user_input == "find_by_location":
        return {
            "type": "text",
            "content": "📍 Great! Which location are you interested in?\n\n(Example: Shimla, Manali, Goa, Kerala, etc.)",
            "new_state": {"step": "asking_location"}
        }
    
    if user_input == "find_by_budget":
        return {
            "type": "text",
            "content": "💰 What's your budget range?\n\n(Example: under 10000, between 10000-20000, lowest price, highest price)",
            "new_state": {"step": "asking_budget"}
        }
    
    if user_input == "find_by_activity":
        return {
            "type": "text",
            "content": "🎯 What activities are you interested in?\n\n(Example: camping, helicopter, trekking, rafting)",
            "new_state": {"step": "asking_activity"}
        }
    
    if user_input == "show_all":
        return show_packages_with_buttons(packages, "📦 Here are all our packages:")
    
    # Handle location input
    if current_step == "asking_location":
        location = user_input.strip()
        filtered = [p for p in packages if any(location.lower() in loc.lower() for loc in p.get("locations", []))]
        
        if filtered:
            return show_packages_with_buttons(filtered, f"📍 Here are packages in {location}:")
        else:
            return {
                "type": "buttons",
                "content": f"😔 Sorry, no packages found in {location}. Would you like to try another location or see all packages?",
                "buttons": [
                    {"text": "📍 Try Another Location", "value": "find_by_location"},
                    {"text": "📦 Show All Packages", "value": "show_all"},
                    {"text": "🏠 Main Menu", "value": "main_menu"}
                ],
                "new_state": {"step": "main_menu"}
            }
    
    # Handle budget input
    if current_step == "asking_budget":
        user_lower = user_input.lower()
        
        if "highest" in user_lower or "expensive" in user_lower:
            filtered = sorted(packages, key=lambda x: int(x.get("package_price", 0)), reverse=True)[:5]
            return show_packages_with_buttons(filtered, "💎 Here are our premium packages (highest price):")
        
        elif "lowest" in user_lower or "cheapest" in user_lower or "under" in user_lower:
            filtered = sorted(packages, key=lambda x: int(x.get("package_price", 0)))[:5]
            return show_packages_with_buttons(filtered, "💰 Here are our budget-friendly packages:")
        
        else:
            # Try to extract numbers
            import re
            numbers = re.findall(r'\d+', user_input)
            if numbers:
                budget = int(numbers[0])
                filtered = [p for p in packages if int(p.get("package_price", 0)) <= budget]
                if filtered:
                    return show_packages_with_buttons(filtered, f"💰 Here are packages under ₹{budget}:")
                else:
                    return {
                        "type": "buttons",
                        "content": f"😔 No packages found under ₹{budget}. Try a higher budget or see all packages?",
                        "buttons": [
                            {"text": "💰 Try Higher Budget", "value": "find_by_budget"},
                            {"text": "📦 Show All Packages", "value": "show_all"},
                            {"text": "🏠 Main Menu", "value": "main_menu"}
                        ],
                        "new_state": {"step": "main_menu"}
                    }
            else:
                return {
                    "type": "text",
                    "content": "Please tell me your budget (e.g., under 15000, lowest price, highest price)",
                    "new_state": {"step": "asking_budget"}
                }
    
    # Handle activity input
    if current_step == "asking_activity":
        activity = user_input.lower()
        filtered = [p for p in packages if any(activity in a.lower() for a in p.get("activities", []))]
        
        if filtered:
            return show_packages_with_buttons(filtered, f"🎯 Here are packages with {activity} activities:")
        else:
            return {
                "type": "buttons",
                "content": f"😔 Sorry, no packages found with {activity}. Try another activity or see all packages?",
                "buttons": [
                    {"text": "🎯 Try Another Activity", "value": "find_by_activity"},
                    {"text": "📦 Show All Packages", "value": "show_all"},
                    {"text": "🏠 Main Menu", "value": "main_menu"}
                ],
                "new_state": {"step": "main_menu"}
            }
    
    # Handle main menu
    if user_input == "main_menu":
        return {
            "type": "buttons",
            "content": "🏠 Main Menu - How can I help you?",
            "buttons": [
                {"text": "📍 Find by Location", "value": "find_by_location"},
                {"text": "💰 Find by Budget", "value": "find_by_budget"},
                {"text": "🎯 Find by Activity", "value": "find_by_activity"},
                {"text": "📦 Show All Packages", "value": "show_all"}
            ],
            "new_state": {"step": "main_menu", "context": {"packages": packages}}
        }
    
    # Default: Show packages
    return show_packages_with_buttons(packages[:5], "📦 Here are some packages for you:")

def show_packages_with_buttons(packages, message):
    """Display packages as clickable buttons"""
    if not packages:
        return {
            "type": "text",
            "content": "No packages found 😅",
            "buttons": []
        }
    
    buttons = []
    for pkg in packages[:6]:  # Show up to 6 packages
        name = pkg.get('package_name', 'Package')
        price = pkg.get('package_price', '?')
        # Truncate long names to fit in button
        if len(name) > 30:
            name = name[:27] + "..."
        buttons.append({
            "text": f"📦 {name} - ₹{price}",
            "value": f"pkg_{pkg.get('id')}"
        })
    
    # Add a main menu button at the end
    buttons.append({"text": "🏠 Main Menu", "value": "main_menu"})
    
    print(f"🔘 Created {len(buttons)} buttons for {len(packages)} packages")  # Debug print
    
    return {
        "type": "buttons",
        "content": message,
        "buttons": buttons,
        "new_state": {"packages": packages, "step": "showing_packages"}
    }