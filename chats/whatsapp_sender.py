# chats/whatsapp_sender.py — with rate limiting + retry logic + fixed button handling

import requests
import re
import os
import time
import logging
from dotenv import load_dotenv
from chats.queue_manager import rate_limiter   # ← import the singleton

load_dotenv('.env')
logger = logging.getLogger(__name__)

ACCESS_TOKEN = os.getenv('ACCESS_TOKEN')
PHONE_NUMBER_ID = os.getenv('PHONE_NUMBER_ID')


# ══════════════════════════════════════════════════════════════
# RETRY WRAPPER
# ══════════════════════════════════════════════════════════════

def safe_post(url: str, headers: dict, data: dict, retries: int = 3):
    """POST with exponential backoff retry. Returns response or None."""
    for attempt in range(1, retries + 1):
        try:
            rate_limiter.acquire()   # ← enforce global rate limit before every send
            res = requests.post(url, headers=headers, json=data, timeout=15)

            if res.status_code == 200:
                logger.info(f"✅ POST successful (attempt {attempt})")
                return res

            # 429 = rate limited by Meta — back off longer
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
            time.sleep(attempt)   # 1s, 2s backoff

    logger.error(f"❌ All {retries} attempts failed")
    return None


# ══════════════════════════════════════════════════════════════
# PUBLIC API
# ══════════════════════════════════════════════════════════════

def send_whatsapp_message(to_phone: str, response: dict):
    """Main entry point for sending WhatsApp messages"""
    url = f"https://graph.facebook.com/v18.0/{PHONE_NUMBER_ID}/messages"
    headers = {
        "Authorization": f"Bearer {ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }

    try:
        # Handle multi-message responses
        if response.get("type") == "multi":
            responses = response.get("responses", [])
            logger.info(f"📤 Sending {len(responses)} messages to {to_phone}")
            
            for i, single_response in enumerate(responses):
                logger.debug(f"  → Message {i+1}/{len(responses)}")
                result = send_single_message(to_phone, single_response, url, headers)
                
                # Small delay between messages to avoid rate limiting
                if i < len(responses) - 1:
                    time.sleep(0.5)
            
            return True

        # Handle single message
        return send_single_message(to_phone, response, url, headers)

    except Exception as e:
        logger.exception(f"❌ send_whatsapp_message error: {e}")
        return None


def send_single_message(to_phone: str, response: dict, url: str, headers: dict):
    """Send a single message (text, image, or buttons)"""
    try:
        msg_type = response.get("type", "text")
        
        logger.info(f"📨 Sending {msg_type} message to {to_phone}")

        # ──────────────────────────────────────────────────────────
        # IMAGE MESSAGE
        # ──────────────────────────────────────────────────────────
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
            
            if res and res.status_code == 200:
                logger.info(f"🖼️  Image sent successfully to {to_phone}")
                return res.json()
            else:
                logger.error(f"❌ Failed to send image to {to_phone}")
                return None

        # ──────────────────────────────────────────────────────────
        # BUTTONS MESSAGE (Interactive)
        # ──────────────────────────────────────────────────────────
        elif msg_type == "buttons":
            content = response.get("content", "")
            buttons = response.get("buttons", [])
            
            if not buttons:
                logger.warning("⚠️ No buttons provided in buttons message")
                # Fallback to text message
                return send_single_message(to_phone, {"type": "text", "content": content}, url, headers)
            
            # WhatsApp only allows up to 3 buttons per message
            # Split buttons into batches of 3
            button_batches = [buttons[i:i+3] for i in range(0, len(buttons), 3)]
            
            # Send first batch with the main content
            first_batch = button_batches[0]
            logger.info(f"🔘 Sending first button batch ({len(first_batch)} buttons) to {to_phone}")
            
            data = _button_message(to_phone, content, first_batch)
            res = safe_post(url, headers, data)
            
            if res and res.status_code == 200:
                logger.info(f"✅ Buttons message sent successfully to {to_phone}")
                
                # Send additional batches if there are more buttons
                if len(button_batches) > 1:
                    time.sleep(0.5)  # Small delay between button messages
                    
                    for idx, batch in enumerate(button_batches[1:], 2):
                        logger.info(f"🔘 Sending additional button batch {idx} ({len(batch)} buttons)")
                        extra_data = _button_message(to_phone, "📋 More options:", batch)
                        extra_res = safe_post(url, headers, extra_data)
                        
                        if extra_res and extra_res.status_code != 200:
                            logger.warning(f"⚠️ Failed to send additional button batch {idx}")
                        
                        time.sleep(0.3)  # Small delay between batches
                
                return res.json()
            else:
                logger.error(f"❌ Failed to send buttons message to {to_phone}")
                # Fallback to text message
                return send_single_message(to_phone, {"type": "text", "content": content}, url, headers)

       
        else:  # text message
            text_content = response.get("content", "")
            if not text_content:
                logger.warning("⚠️ Empty text message content")
                return None
                
            data = _text_message(to_phone, text_content)
            res = safe_post(url, headers, data)
            
            if res and res.status_code == 200:
                logger.info(f"💬 Text message sent successfully to {to_phone}")
                return res.json()
            else:
                logger.error(f"❌ Failed to send text message to {to_phone}")
                return None

    except Exception as e:
        logger.exception(f"❌ send_single_message error: {e}")
        return None


def _text_message(to: str, text: str) -> dict:
    """Create text message payload"""
     
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
    """Create interactive button message payload"""
    
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
    
   
    body_text = text.strip()
    if not body_text:
        body_text = "Choose an option:"
    
    
    if not wb:
        logger.error("❌ No valid buttons to send")
        return _text_message(to, body_text)
    
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "interactive",
        "interactive": {
            "type": "button",
            "body": {"text": body_text},
            "action": {"buttons": wb}
        }
    }
    
    logger.debug(f"Button payload: {payload}")
    return payload


def _clean_button_text(text: str, max_len: int) -> str:
    """Clean button text for WhatsApp (no emojis in button titles, max length)"""
     
    text = re.sub(r'[^\w\s₹\-\.\/\?\!]', '', str(text))
    
     
    text = re.sub(r'\s+', ' ', text).strip()
    
 
    if len(text) > max_len:
        text = text[:max_len - 2] + ".."
    
   
    if not text:
        text = "Option"
    
    return text


 

def send_raw_text(to_phone: str, text: str):
    """Simple helper to send raw text message"""
    url = f"https://graph.facebook.com/v18.0/{PHONE_NUMBER_ID}/messages"
    headers = {
        "Authorization": f"Bearer {ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }
    
    data = _text_message(to_phone, text)
    res = safe_post(url, headers, data)
    
    if res and res.status_code == 200:
        logger.info(f"✅ Raw text sent to {to_phone}")
        return True
    else:
        logger.error(f"❌ Failed to send raw text to {to_phone}")
        return False


def send_raw_buttons(to_phone: str, text: str, buttons: list):
    """Simple helper to send raw buttons"""
    url = f"https://graph.facebook.com/v18.0/{PHONE_NUMBER_ID}/messages"
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