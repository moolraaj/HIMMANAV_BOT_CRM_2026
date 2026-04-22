
# chats/message_handler.py
import json
from datetime import datetime
from database.database import messages, mapping
from bot import process_message
from chats.whatsapp_sender import send_whatsapp_message
import os
from dotenv import load_dotenv

load_dotenv('.env')

OWNER_PHONE = os.getenv('OWNER_PHONE')

conversation_states = {}


def _serialize_response(response):
    """
    Convert bot response dict → JSON string for DB storage.
    Strips new_state (too large / internal) and notify_agent fields.
    Keeps: type, content, buttons, responses, caption, remaining_buttons.
    """
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
        # Each sub-response in responses[] — strip new_state from sub-items too
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
        # Fallback — dump whatever content exists
        return json.dumps({
            "type": msg_type,
            "content": response.get("content", "")
        })


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

    # ── Save incoming user message ──────────────────────────
    messages.insert_one({
        "user_phone": user_phone,
        "user_id": partner_id,
        "message": user_message,
        "from": "user",
        "timestamp": datetime.utcnow()
    })

    # ── Init / restore conversation state ───────────────────
    if user_phone not in conversation_states:
        conversation_states[user_phone] = {
            "step": "greeting",
            "context": {},
            "packages": []
        }

    state = conversation_states[user_phone]
    state["user_phone"] = user_phone

    try:
        response = process_message(user_message, OWNER_PHONE, state)
    except Exception as e:
        print("❌ Bot error:", e)
        import traceback
        traceback.print_exc()
        response = {"type": "text", "content": "⚠️ Something went wrong, please try again."}

    # ── Apply new_state ─────────────────────────────────────
    if response.get("new_state"):
        conversation_states[user_phone].update(response["new_state"])
        conversation_states[user_phone]["user_phone"] = user_phone

    # ── Validate response ───────────────────────────────────
    if not response:
        response = {"type": "text", "content": "Something went wrong"}
    elif response.get("type") not in ("multi", "image") and not response.get("content"):
        response = {"type": "text", "content": "Something went wrong"}

    # ── Notify agent if booking/inquiry ─────────────────────
    if response.get("notify_agent") and response.get("agent_message"):
        _notify_agent(response["agent_message"])

    # ── Save bot response as proper JSON ────────────────────
    serialized = _serialize_response(response)
    messages.insert_one({
        "user_phone": user_phone,
        "user_id": partner_id,
        "message": serialized,          # ← full JSON, not truncated text
        "from": "bot",
        "timestamp": datetime.utcnow()
    })

    print(f"💾 Saved bot msg ({response.get('type')}): {serialized[:120]}…")

    # ── Send via WhatsApp ────────────────────────────────────
    send_whatsapp_message(user_phone, response)


def _notify_agent(agent_message):
    try:
        from chats.whatsapp_sender import send_whatsapp_message as send_msg
        send_msg(OWNER_PHONE, {"type": "text", "content": agent_message})
        print(f"✅ Agent notified: {agent_message[:80]}…")
    except Exception as e:
        print(f"❌ Agent notification failed: {e}")