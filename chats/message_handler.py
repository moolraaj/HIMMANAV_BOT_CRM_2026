# chats/message_handler.py
from datetime import datetime
from database.database import messages, mapping
from bot import process_message
from chats.whatsapp_sender import send_whatsapp_message
import os
from dotenv import load_dotenv

load_dotenv('.env')

OWNER_PHONE = os.getenv('OWNER_PHONE')

# Store conversation states in memory
conversation_states = {}


def process_incoming_message(message_data):
    user_phone = message_data.get('from')
    user_message = ""

    if 'text' in message_data:
        user_message = message_data['text']['body'].strip()
    elif 'interactive' in message_data:
        interactive = message_data['interactive']
        if interactive['type'] == 'button_reply':
            user_message = interactive['button_reply']['id']
        elif interactive['type'] == 'list_reply':
            user_message = interactive['list_reply']['id']
    elif 'button' in message_data:
        user_message = message_data['button']['payload']

    print(f"📱 {user_phone} → {user_message}")

    partner = mapping.find_one({"user_phone": user_phone})
    partner_id = partner["partner_id"] if partner else 13

    messages.insert_one({
        "user_phone": user_phone,
        "user_id": partner_id,
        "message": user_message,
        "from": "user",
        "timestamp": datetime.utcnow()
    })

    # Init state for new user
    if user_phone not in conversation_states:
        conversation_states[user_phone] = {
            "step": "greeting",
            "context": {},
            "packages": []
        }

    state = conversation_states[user_phone]

    # ✅ FIX: Set the real sender's phone BEFORE calling process_message.
    # bot.py stores this in state so _handle_download_pdf uses the right number.
    state["user_phone"] = user_phone

    try:
        response = process_message(user_message, OWNER_PHONE, state)
    except Exception as e:
        print("❌ Bot error:", e)
        import traceback
        traceback.print_exc()
        response = {"type": "text", "content": "⚠️ Something went wrong, please try again."}

    # Apply new_state if returned
    if response.get("new_state"):
        conversation_states[user_phone].update(response["new_state"])
        # ✅ FIX: Always re-stamp user_phone after new_state update
        # new_state may have set user_phone correctly, but some paths may not include it
        conversation_states[user_phone]["user_phone"] = user_phone

    # Validate response — multi responses have no top-level content (that's fine)
    if not response:
        response = {"type": "text", "content": "Something went wrong"}
    elif response.get("type") != "multi" and not response.get("content"):
        response = {"type": "text", "content": "Something went wrong"}

    # Notify agent if booking or inquiry
    if response.get("notify_agent") and response.get("agent_message"):
        _notify_agent(response["agent_message"])

    # Log bot response
    log_message = response.get("content", "[package details sent]")
    messages.insert_one({
        "user_phone": user_phone,
        "user_id": partner_id,
        "message": log_message,
        "from": "bot",
        "timestamp": datetime.utcnow()
    })

    send_whatsapp_message(user_phone, response)


def _notify_agent(agent_message):
    """Send booking/inquiry notification to owner"""
    try:
        from chats.whatsapp_sender import send_whatsapp_message as send_msg
        send_msg(OWNER_PHONE, {"type": "text", "content": agent_message})
        print(f"✅ Agent notified: {agent_message[:80]}...")
    except Exception as e:
        print(f"❌ Agent notification failed: {e}")