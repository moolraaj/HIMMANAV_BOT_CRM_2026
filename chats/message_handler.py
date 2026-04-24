# chats/message_handler.py — FIXED: emits bot reply to frontend after processing

import json
import re
from datetime import datetime
from database.database import messages, mapping, get_or_create_user, increment_user_message_count, get_whatsapp_config, update_username
from bot import process_message
from chats.whatsapp_sender import send_whatsapp_message
import os
from dotenv import load_dotenv

load_dotenv('.env')

OWNER_PHONE = os.getenv('OWNER_PHONE')

conversation_states = {}


def normalize_phone_number(phone_number):
    if not phone_number:
        return None
    normalized = re.sub(r'[^\d]', '', str(phone_number))
    if normalized.startswith('0'):
        normalized = normalized[1:]
    return normalized


def _serialize_response(response):
    """Convert bot response dict → JSON string for DB storage."""
    if not response:
        return json.dumps({"type": "text", "content": ""})

    msg_type = response.get("type", "text")

    if msg_type == "text":
        return json.dumps({
            "type": "text",
            "content": response.get("content", "")
        })

    elif msg_type == "buttons":
        return json.dumps({
            "type": "buttons",
            "content": response.get("content", ""),
            "buttons": response.get("buttons", []),
            "remaining_buttons": response.get("remaining_buttons", [])
        })

    elif msg_type == "image":
        return json.dumps({
            "type": "image",
            "content": response.get("content", ""),
            "caption": response.get("caption", "")
        })

    elif msg_type == "multi":
        clean_responses = []
        for r in response.get("responses", []):
            sub_type = r.get("type", "text")
            if sub_type == "text":
                clean_responses.append({"type": "text", "content": r.get("content", "")})
            elif sub_type == "buttons":
                clean_responses.append({
                    "type": "buttons",
                    "content": r.get("content", ""),
                    "buttons": r.get("buttons", []),
                    "remaining_buttons": r.get("remaining_buttons", [])
                })
            elif sub_type == "image":
                clean_responses.append({
                    "type": "image",
                    "content": r.get("content", ""),
                    "caption": r.get("caption", "")
                })
            else:
                clean_responses.append({"type": sub_type, "content": r.get("content", "")})
        return json.dumps({
            "type": "multi",
            "responses": clean_responses
        })

    else:
        return json.dumps({
            "type": msg_type,
            "content": response.get("content", "")
        })


def _extract_display_text(response):
    """Extract a human-readable string from a bot response for frontend display."""
    if not response:
        return ""
    msg_type = response.get("type", "text")
    if msg_type == "text":
        return response.get("content", "")
    elif msg_type == "buttons":
        return response.get("content", "")
    elif msg_type == "image":
        return response.get("caption", "") or "[Image]"
    elif msg_type == "multi":
        parts = []
        for r in response.get("responses", []):
            text = r.get("content", "")
            if text:
                parts.append(text)
        return " | ".join(parts) if parts else "[Message]"
    return response.get("content", "")


def process_incoming_message(message_data, sender_phone_number_id=None, emit_fn=None, display_phone_number=None):
    """
    Process incoming WhatsApp message.

    Args:
        message_data: Raw WhatsApp message dict
        sender_phone_number_id: phone_number_id that received the message
        emit_fn: Optional SocketIO emit function to push bot reply to frontend
        display_phone_number: The room key for SocketIO emit
    """
    user_phone = message_data.get('from')
    user_message = ""

    # Extract message text
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

    # Get display_phone_number from sender config if not passed in
    display_phone_number_raw = None

    if display_phone_number:
        # Already provided by webhook (preferred path)
        display_phone_number_raw = normalize_phone_number(display_phone_number)
    elif sender_phone_number_id:
        sender_config = get_whatsapp_config(sender_phone_number_id)
        if sender_config:
            dn = sender_config.get("display_phone_number_raw") or sender_config.get("display_number")
            if dn:
                display_phone_number_raw = normalize_phone_number(dn)
                display_phone_number = display_phone_number_raw

    # Get or create user
    user = get_or_create_user(user_phone, display_phone_number_raw)
    user_id = user["user_id"]

    increment_user_message_count(user_phone)

    if user_message.lower().startswith("my name is") or user_message.lower().startswith("i am"):
        name = user_message.replace("my name is", "").replace("i am", "").strip()
        update_username(user_phone, name)
        print(f"📝 Updated username for {user_phone}: {name}")

    # Save incoming user message
    messages.insert_one({
        "user_phone": user_phone,
        "user_id": user_id,
        "message": user_message,
        "from": "user",
        "timestamp": datetime.utcnow(),
        "sender_phone_number_id": sender_phone_number_id,
        "display_phone_number_raw": display_phone_number_raw
    })

    # Init / restore conversation state
    if user_phone not in conversation_states:
        conversation_states[user_phone] = {
            "step": "greeting",
            "context": {},
            "packages": []
        }

    state = conversation_states[user_phone]
    state["user_phone"] = user_phone
    state["sender_phone_number_id"] = sender_phone_number_id
    state["user_id"] = user_id
    state["display_phone_number_raw"] = display_phone_number_raw

    try:
        response = process_message(user_message, OWNER_PHONE, state)
    except Exception as e:
        print("❌ Bot error:", e)
        import traceback
        traceback.print_exc()
        response = {"type": "text", "content": "⚠️ Something went wrong, please try again."}

    # Apply new_state
    if response.get("new_state"):
        conversation_states[user_phone].update(response["new_state"])
        conversation_states[user_phone]["user_phone"] = user_phone
        conversation_states[user_phone]["sender_phone_number_id"] = sender_phone_number_id
        conversation_states[user_phone]["user_id"] = user_id
        conversation_states[user_phone]["display_phone_number_raw"] = display_phone_number_raw

    # Validate response
    if not response:
        response = {"type": "text", "content": "Something went wrong"}
    elif response.get("type") not in ("multi", "image") and not response.get("content"):
        response = {"type": "text", "content": "Something went wrong"}

    if response.get("notify_agent") and response.get("agent_message"):
        _notify_agent(response["agent_message"])

    # Save bot response
    serialized = _serialize_response(response)
    messages.insert_one({
        "user_phone": user_phone,
        "user_id": user_id,
        "message": serialized,
        "from": "bot",
        "timestamp": datetime.utcnow(),
        "sender_phone_number_id": sender_phone_number_id,
        "display_phone_number_raw": display_phone_number_raw
    })

    print(f"💾 Saved bot msg ({response.get('type')}): {serialized[:120]}…")

    # 🔥 FIX: Emit bot reply to frontend via SocketIO
    if emit_fn and display_phone_number:
        try:
            display_text = _extract_display_text(response)
            emit_fn(
                user_phone=user_phone,
                message_data={
                    "from": "bot",
                    "message": display_text,
                    "timestamp": datetime.utcnow().isoformat()
                },
                display_phone_number=display_phone_number
            )
            print(f"📡 Emitted bot reply to frontend for {user_phone}")
        except Exception as e:
            print(f"⚠️ Failed to emit bot reply: {e}")

    # Send via WhatsApp
    send_whatsapp_message(user_phone, response, sender_phone_number_id)


def _notify_agent(agent_message):
    try:
        from chats.whatsapp_sender import send_whatsapp_message as send_msg
        from database.database import get_all_active_whatsapp_numbers

        numbers = get_all_active_whatsapp_numbers()
        if numbers:
            sender_id = numbers[0]["phone_number_id"]
            send_msg(OWNER_PHONE, {"type": "text", "content": agent_message}, sender_id)
            print(f"✅ Agent notified: {agent_message[:80]}…")
    except Exception as e:
        print(f"❌ Agent notification failed: {e}")