# chats/whatsapp_sender.py — with dynamic phone number from database

import requests
import re
import os
import time
import logging
from dotenv import load_dotenv
from chats.queue_manager import rate_limiter
from database.database import get_whatsapp_config

load_dotenv('.env')
logger = logging.getLogger(__name__)

ACCESS_TOKEN = os.getenv('ACCESS_TOKEN')


def safe_post(url: str, headers: dict, data: dict, retries: int = 3):
    """POST with exponential backoff retry."""
    for attempt in range(1, retries + 1):
        try:
            rate_limiter.acquire()
            res = requests.post(url, headers=headers, json=data, timeout=15)

            if res.status_code == 200:
                logger.info(f"✅ POST successful (attempt {attempt})")
                return res

            if res.status_code == 429:
                wait = 2 ** attempt
                logger.warning(f"⚠️ Meta 429 rate limit — waiting {wait}s (attempt {attempt})")
                time.sleep(wait)
                continue

            logger.warning(f"⚠️ HTTP {res.status_code} on attempt {attempt}: {res.text[:200]}")

        except requests.exceptions.Timeout:
            logger.warning(f"⏰ Timeout on attempt {attempt}")
        except requests.exceptions.ConnectionError:
            logger.warning(f"🔌 Connection error on attempt {attempt}")
        except Exception as e:
            logger.warning(f"❓ Unexpected error on attempt {attempt}: {e}")

        if attempt < retries:
            time.sleep(attempt)

    logger.error(f"❌ All {retries} attempts failed")
    return None


def send_whatsapp_message(to_phone: str, response: dict, sender_phone_number_id: str):
    """Main entry point - requires sender_phone_number_id"""
    sender_config = get_whatsapp_config(sender_phone_number_id)
    
    if not sender_config:
        logger.error(f"❌ No active config found for sender: {sender_phone_number_id}")
        return None
    
    url = f"https://graph.facebook.com/v18.0/{sender_config['phone_number_id']}/messages"
    headers = {
        "Authorization": f"Bearer {ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }

    try:
        if response.get("type") == "multi":
            responses = response.get("responses", [])
            logger.info(f"📤 Sending {len(responses)} messages from {sender_config.get('display_number', sender_phone_number_id)} to {to_phone}")
            
            for i, single_response in enumerate(responses):
                send_single_message(to_phone, single_response, url, headers)
                if i < len(responses) - 1:
                    time.sleep(0.5)
            return True

        return send_single_message(to_phone, response, url, headers)

    except Exception as e:
        logger.exception(f"❌ send_whatsapp_message error: {e}")
        return None


def send_single_message(to_phone: str, response: dict, url: str, headers: dict):
    """Send a single message"""
    try:
        msg_type = response.get("type", "text")
        logger.info(f"📨 Sending {msg_type} message to {to_phone}")

        if msg_type == "image":
            data = {
                "messaging_product": "whatsapp",
                "to": to_phone,
                "type": "image",
                "image": {
                    "link": response.get("content", ""),
                    "caption": response.get("caption", "")
                }
            }
            res = safe_post(url, headers, data)
            return res.json() if res and res.status_code == 200 else None

        elif msg_type == "buttons":
            content = response.get("content", "")
            buttons = response.get("buttons", [])
            
            if not buttons:
                return send_single_message(to_phone, {"type": "text", "content": content}, url, headers)
            
            button_batches = [buttons[i:i+3] for i in range(0, len(buttons), 3)]
            first_batch = button_batches[0]
            
            data = _button_message(to_phone, content, first_batch)
            res = safe_post(url, headers, data)
            
            if res and res.status_code == 200:
                if len(button_batches) > 1:
                    time.sleep(0.5)
                    for batch in button_batches[1:]:
                        extra_data = _button_message(to_phone, "📋 More options:", batch)
                        safe_post(url, headers, extra_data)
                        time.sleep(0.3)
                return res.json()
            else:
                return send_single_message(to_phone, {"type": "text", "content": content}, url, headers)

        else:
            text_content = response.get("content", "")
            if not text_content:
                return None
            data = _text_message(to_phone, text_content)
            res = safe_post(url, headers, data)
            return res.json() if res and res.status_code == 200 else None

    except Exception as e:
        logger.exception(f"❌ send_single_message error: {e}")
        return None


def _text_message(to: str, text: str) -> dict:
    text = text.strip()
    if len(text) > 4000:
        text = text[:3997] + "..."
    return {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": text or "Hello 👋"}
    }


def _button_message(to: str, text: str, buttons: list) -> dict:
    wb = []
    for btn in buttons[:3]:
        button_title = _clean_button_text(btn["text"], 20)
        button_value = str(btn["value"])
        wb.append({
            "type": "reply",
            "reply": {
                "id": button_value,
                "title": button_title
            }
        })
    
    body_text = text.strip() or "Choose an option:"
    
    if not wb:
        return _text_message(to, body_text)
    
    return {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "interactive",
        "interactive": {
            "type": "button",
            "body": {"text": body_text},
            "action": {"buttons": wb}
        }
    }


def _clean_button_text(text: str, max_len: int) -> str:
    text = re.sub(r'[^\w\s₹\-\.\/\?\!]', '', str(text))
    text = re.sub(r'\s+', ' ', text).strip()
    if len(text) > max_len:
        text = text[:max_len - 2] + ".."
    if not text:
        text = "Option"
    return text


def send_raw_text(to_phone: str, text: str, sender_phone_number_id: str):
    sender_config = get_whatsapp_config(sender_phone_number_id)
    if not sender_config:
        return False
    
    url = f"https://graph.facebook.com/v18.0/{sender_config['phone_number_id']}/messages"
    headers = {
        "Authorization": f"Bearer {ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }
    
    data = _text_message(to_phone, text)
    res = safe_post(url, headers, data)
    return res and res.status_code == 200


def send_raw_buttons(to_phone: str, text: str, buttons: list, sender_phone_number_id: str):
    sender_config = get_whatsapp_config(sender_phone_number_id)
    if not sender_config:
        return False
    
    url = f"https://graph.facebook.com/v18.0/{sender_config['phone_number_id']}/messages"
    headers = {
        "Authorization": f"Bearer {ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }
    
    button_batches = [buttons[i:i+3] for i in range(0, len(buttons), 3)]
    if not button_batches:
        return False
    
    data = _button_message(to_phone, text, button_batches[0])
    res = safe_post(url, headers, data)
    
    if not res or res.status_code != 200:
        return False
    
    for batch in button_batches[1:]:
        time.sleep(0.3)
        extra_data = _button_message(to_phone, "📋 More options:", batch)
        safe_post(url, headers, extra_data)
    
    return True