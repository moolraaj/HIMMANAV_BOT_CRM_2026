# chats/whatsapp_sender.py
import requests
import re
import os
import time
from dotenv import load_dotenv

load_dotenv('.env')

ACCESS_TOKEN = os.getenv('ACCESS_TOKEN')
PHONE_NUMBER_ID = os.getenv('PHONE_NUMBER_ID')

def send_whatsapp_message(to_phone, response):
    url = f"https://graph.facebook.com/v18.0/{PHONE_NUMBER_ID}/messages"
    headers = {
        "Authorization": f"Bearer {ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }

    try:
        # Handle multi-response (multiple messages in sequence)
        if response.get("type") == "multi":
            responses = response.get("responses", [])
            print(f"📤 Sending {len(responses)} messages in sequence")
            for i, single_response in enumerate(responses):
                print(f"📤 Sending message {i+1}/{len(responses)}")
                time.sleep(0.5)
                send_single_message(to_phone, single_response, url, headers)
            return None
        
        return send_single_message(to_phone, response, url, headers)

    except Exception as e:
        print(f"❌ Send error: {e}")
        import traceback
        traceback.print_exc()
        return None


def send_single_message(to_phone, response, url, headers):
    """Send a single message (text, image, or buttons)"""
    try:
        msg_type = response.get("type", "text")
        
        # Handle image message
        if msg_type == "image":
            image_url = response.get("content", "")
            caption = response.get("caption", "")
            
            data = {
                "messaging_product": "whatsapp",
                "to": to_phone,
                "type": "image",
                "image": {
                    "link": image_url,
                    "caption": caption
                }
            }
            res = requests.post(url, headers=headers, json=data, timeout=15)
            print(f"📤 Image [{res.status_code}]: {res.text[:200]}")
            return res.json()
        
        # Handle buttons message
        elif msg_type == "buttons":
            content = response.get("content", "")
            buttons = response.get("buttons", [])
            
            if not buttons:
                return None
            
            data = _button_message(to_phone, content, buttons[:3])
            res = requests.post(url, headers=headers, json=data, timeout=15)
            print(f"📤 Buttons [{res.status_code}]: {res.text[:200]}")
            
            remaining_buttons = response.get("remaining_buttons", [])
            if remaining_buttons:
                for i in range(0, len(remaining_buttons), 3):
                    batch = remaining_buttons[i:i+3]
                    more_data = _button_message(to_phone, "More options 👇", batch)
                    requests.post(url, headers=headers, json=more_data, timeout=15)
            
            return res.json()
        
        # Handle text message
        else:
            content = response.get("content", "")
            data = _text_message(to_phone, content)
            res = requests.post(url, headers=headers, json=data, timeout=15)
            print(f"📤 Text [{res.status_code}]: {res.text[:200]}")
            return res.json()
            
    except Exception as e:
        print(f"❌ Send single message error: {e}")
        return None


def _text_message(to, text):
    return {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": text or "Hello 👋"}
    }


def _button_message(to, text, buttons):
    wb = []
    for btn in buttons[:3]:
        title = _clean_button_text(btn["text"], 20)
        wb.append({
            "type": "reply",
            "reply": {"id": btn["value"], "title": title}
        })
    return {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "interactive",
        "interactive": {
            "type": "button",
            "body": {"text": text or " "},
            "action": {"buttons": wb}
        }
    }


def _clean_button_text(text, max_len):
    text = re.sub(r'[^\w\s₹\-\.\/]', '', str(text)).strip()
    if len(text) > max_len:
        text = text[:max_len - 2] + ".."
    return text or "Option"