# chats/message_handler.py - FIXED: background threading, serializer, error handling

import json
import re
import threading
from datetime import datetime
from database.database import (
    messages, get_or_create_user, increment_user_message_count,
    get_whatsapp_config, update_username
)
from bot import process_message
from chats.whatsapp_sender import send_whatsapp_message
import os
import logging
from dotenv import load_dotenv

load_dotenv('.env')

logger = logging.getLogger(__name__)

# Agent active sessions (for human takeover)
agent_active_sessions = {}


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

    elif msg_type in ("buttons", "buttons_grid"):
        return json.dumps({
            "type": msg_type,
            "content": response.get("content", ""),
            "buttons": response.get("buttons", [])
        })

    # FIX: was missing — caused crash → 502 when no_hotels_found triggered
    elif msg_type == "buttons_grid_with_separate_button":
        return json.dumps({
            "type": msg_type,
            "content": response.get("content", ""),
            "buttons": response.get("buttons", []),
            "separate_button": response.get("separate_button", {})
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
                clean_responses.append({
                    "type": "text",
                    "content": r.get("content", "")
                })
            elif sub_type in ("buttons", "buttons_grid"):
                clean_responses.append({
                    "type": sub_type,
                    "content": r.get("content", ""),
                    "buttons": r.get("buttons", [])
                })
            elif sub_type == "buttons_grid_with_separate_button":
                clean_responses.append({
                    "type": sub_type,
                    "content": r.get("content", ""),
                    "buttons": r.get("buttons", []),
                    "separate_button": r.get("separate_button", {})
                })
            elif sub_type == "image":
                clean_responses.append({
                    "type": "image",
                    "content": r.get("content", ""),
                    "caption": r.get("caption", "")
                })
            else:
                clean_responses.append({
                    "type": sub_type,
                    "content": r.get("content", "")
                })
        return json.dumps({"type": "multi", "responses": clean_responses})

    else:
        return json.dumps({
            "type": msg_type,
            "content": response.get("content", "")
        })


def _do_bot_processing(
    user_phone,
    user_message,
    sender_phone_number_id,
    display_phone_number,
    display_phone_number_raw,
    user_id,
    emit_fn
):
    """
    All heavy bot logic runs here — called in a background thread so the
    webhook handler can return 200 to WhatsApp immediately.
    """
    try:
        state = {
            "user_phone": user_phone,
            "step": "greeting",
            "context": {},
            "sender_phone_number_id": sender_phone_number_id,
            "user_id": user_id,
            "display_phone_number_raw": display_phone_number_raw
        }

        try:
            response = process_message(user_message, user_phone, state)
        except Exception as e:
            logger.error(f"❌ Bot process_message error for {user_phone}: {e}", exc_info=True)
            response = {"type": "text", "content": "Sorry, something went wrong. Please try again."}

        # Save bot response to DB
        serialized = _serialize_response(response)
        try:
            messages.insert_one({
                "user_phone": user_phone,
                "user_id": user_id,
                "message": serialized,
                "from": "bot",
                "timestamp": datetime.utcnow(),
                "sender_phone_number_id": sender_phone_number_id,
                "display_phone_number_raw": display_phone_number_raw
            })
            logger.info(f"💾 Saved bot msg ({response.get('type')}): {serialized[:120]}…")
        except Exception as e:
            logger.error(f"❌ DB save error for bot response: {e}", exc_info=True)

        # Emit bot response to frontend
        if emit_fn and display_phone_number:
            try:
                emit_fn(
                    user_phone=user_phone,
                    message_data={
                        "from": "bot",
                        "message": response,
                        "timestamp": datetime.utcnow().isoformat() + 'Z'
                    },
                    display_phone_number=display_phone_number
                )
                logger.info(f"📡 Emitted bot reply to frontend for {user_phone}")
            except Exception as e:
                logger.warning(f"⚠️ Failed to emit bot reply: {e}")

        # Send via WhatsApp API
        try:
            send_whatsapp_message(user_phone, response, sender_phone_number_id)
        except Exception as e:
            logger.error(f"❌ WhatsApp send error for {user_phone}: {e}", exc_info=True)

    except Exception as e:
        logger.error(f"❌ Unhandled error in _do_bot_processing for {user_phone}: {e}", exc_info=True)


def process_incoming_message(
    message_data,
    sender_phone_number_id=None,
    emit_fn=None,
    display_phone_number=None
):
    """
    Process incoming WhatsApp message.

    FIX: Acknowledges immediately (returns fast) and does all heavy
    processing in a background thread — prevents 502 caused by
    WhatsApp's 5-second timeout killing the connection.
    """
    try:
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

        if not user_phone or not user_message:
            logger.warning(f"⚠️ Empty phone or message, skipping. data={message_data}")
            return

        logger.info(f"📱 {user_phone} → {user_message}")

        # Resolve display phone number
        display_phone_number_raw = None
        if display_phone_number:
            display_phone_number_raw = normalize_phone_number(display_phone_number)
        elif sender_phone_number_id:
            sender_config = get_whatsapp_config(sender_phone_number_id)
            if sender_config:
                dn = sender_config.get("display_phone_number_raw") or sender_config.get("display_number")
                if dn:
                    display_phone_number_raw = normalize_phone_number(dn)
                    display_phone_number = display_phone_number_raw

        # ── AGENT IN CONTROL — save message, emit, skip bot ──────────────────
        if is_agent_active(user_phone):
            logger.info(f"👤 Agent is in control for {user_phone} - bot disabled")
            try:
                user = get_or_create_user(user_phone, display_phone_number_raw)
                user_id = user["user_id"]
                messages.insert_one({
                    "user_phone": user_phone,
                    "user_id": user_id,
                    "message": user_message,
                    "from": "user",
                    "timestamp": datetime.utcnow(),
                    "sender_phone_number_id": sender_phone_number_id,
                    "display_phone_number_raw": display_phone_number_raw
                })
                if emit_fn and display_phone_number:
                    emit_fn(
                        user_phone=user_phone,
                        message_data={
                            "from": "user",
                            "message": user_message,
                            "timestamp": datetime.utcnow().isoformat() + 'Z'
                        },
                        display_phone_number=display_phone_number
                    )
            except Exception as e:
                logger.error(f"❌ Agent-mode DB/emit error: {e}", exc_info=True)
            return

        # ── NORMAL BOT FLOW ───────────────────────────────────────────────────
        try:
            user = get_or_create_user(user_phone, display_phone_number_raw)
            user_id = user["user_id"]
            increment_user_message_count(user_phone)

            # Auto-update username if user introduces themselves
            lower_msg = user_message.lower()
            if lower_msg.startswith("my name is") or lower_msg.startswith("i am"):
                name = user_message.replace("my name is", "").replace("i am", "").strip()
                update_username(user_phone, name)
                logger.info(f"📝 Updated username for {user_phone}: {name}")

            # Save incoming user message to DB
            messages.insert_one({
                "user_phone": user_phone,
                "user_id": user_id,
                "message": user_message,
                "from": "user",
                "timestamp": datetime.utcnow(),
                "sender_phone_number_id": sender_phone_number_id,
                "display_phone_number_raw": display_phone_number_raw
            })

            # Emit user message to frontend immediately
            if emit_fn and display_phone_number:
                try:
                    emit_fn(
                        user_phone=user_phone,
                        message_data={
                            "from": "user",
                            "message": user_message,
                            "timestamp": datetime.utcnow().isoformat() + 'Z'
                        },
                        display_phone_number=display_phone_number
                    )
                except Exception as e:
                    logger.warning(f"⚠️ Failed to emit user message: {e}")

        except Exception as e:
            logger.error(f"❌ DB/user setup error for {user_phone}: {e}", exc_info=True)
            # Still try to get user_id for the background thread
            user_id = None

        # ── FIRE BACKGROUND THREAD — webhook returns immediately after this ──
        thread = threading.Thread(
            target=_do_bot_processing,
            args=(
                user_phone,
                user_message,
                sender_phone_number_id,
                display_phone_number,
                display_phone_number_raw,
                user_id,
                emit_fn
            ),
            daemon=True
        )
        thread.start()
        logger.info(f"🚀 Background thread started for {user_phone}")

    except Exception as e:
        logger.error(f"❌ Fatal error in process_incoming_message: {e}", exc_info=True)


def agent_takeover_chat(user_phone, agent_phone=None):
    """Agent takes over the chat."""
    agent_active_sessions[user_phone] = {
        "active": True,
        "agent_phone": agent_phone,
        "taken_over_at": datetime.utcnow()
    }
    logger.info(f"👤 Agent took over chat for {user_phone}")
    return True


def agent_release_chat(user_phone):
    """Release chat back to bot."""
    if user_phone in agent_active_sessions:
        del agent_active_sessions[user_phone]
        logger.info(f"🤖 Bot released for {user_phone}")
        return True
    return False


def is_agent_active(user_phone):
    """Check if agent is actively handling this chat."""
    session = agent_active_sessions.get(user_phone)
    return bool(session and session.get("active"))