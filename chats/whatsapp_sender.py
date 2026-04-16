# chats/whatsapp_sender.py
# import requests
# import re
# import os
# from dotenv import load_dotenv

# load_dotenv('.env')

# ACCESS_TOKEN = os.getenv('ACCESS_TOKEN')
# PHONE_NUMBER_ID = os.getenv('PHONE_NUMBER_ID')

# def send_whatsapp_message(to_phone, response):
#     """Send message to WhatsApp"""
#     url = f"https://graph.facebook.com/v18.0/{PHONE_NUMBER_ID}/messages"
    
#     headers = {
#         "Authorization": f"Bearer {ACCESS_TOKEN}",
#         "Content-Type": "application/json"
#     }
    
#     try:
#         if response.get("type") == "buttons" and response.get("buttons"):
#             buttons = response["buttons"][:3]
#             whatsapp_buttons = []
            
#             for btn in buttons:
#                 text = re.sub(r'[^\w\s₹-]', '', btn["text"]).strip()
#                 if len(text) > 20:
#                     text = text[:17] + "..."
                
#                 whatsapp_buttons.append({
#                     "type": "reply",
#                     "reply": {
#                         "id": btn["value"],
#                         "title": text
#                     }
#                 })
            
#             data = {
#                 "messaging_product": "whatsapp",
#                 "to": to_phone,
#                 "type": "interactive",
#                 "interactive": {
#                     "type": "button",
#                     "body": {"text": response.get("content", "")},
#                     "action": {"buttons": whatsapp_buttons}
#                 }
#             }
#         else:
#             data = {
#                 "messaging_product": "whatsapp",
#                 "to": to_phone,
#                 "type": "text",
#                 "text": {"body": response.get("content", "Hello")}
#             }
        
#         res = requests.post(url, headers=headers, json=data)
#         print("📤 Sent:", res.status_code, res.text)
#         return res.json()
        
#     except Exception as e:
#         print("❌ Send error:", e)
#         return None




# chats/whatsapp_sender.py
import requests
import re
import os
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
        msg_type = response.get("type", "text")
        content = response.get("content", "")
        buttons = response.get("buttons", [])

        # ── Text only ──
        if msg_type != "buttons" or not buttons:
            data = _text_message(to_phone, content)

        # ── 1–3 buttons → interactive button ──
        elif len(buttons) <= 3:
            data = _button_message(to_phone, content, buttons)

        # ── 4–10 buttons → list message ──
        else:
            data = _list_message(to_phone, content, buttons)

        res = requests.post(url, headers=headers, json=data, timeout=10)
        print(f"📤 WhatsApp [{res.status_code}]: {res.text[:200]}")
        return res.json()

    except Exception as e:
        print(f"❌ Send error: {e}")
        return None


# ─────────────────────────────────────────
# Message builders
# ─────────────────────────────────────────

def _text_message(to, text):
    return {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": text or "Hello 👋"}
    }


def _button_message(to, text, buttons):
    """Max 3 buttons, title max 20 chars"""
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


def _list_message(to, text, buttons):
    """Up to 10 items in a list, row title max 24 chars"""
    rows = []
    for btn in buttons[:10]:
        title = _clean_button_text(btn["text"], 24)
        rows.append({
            "id": btn["value"],
            "title": title
        })
    return {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "interactive",
        "interactive": {
            "type": "list",
            "body": {"text": text or " "},
            "action": {
                "button": "View Options 👇",
                "sections": [{"title": "Options", "rows": rows}]
            }
        }
    }


def _clean_button_text(text, max_len):
    """Remove unsupported chars and truncate"""
    text = re.sub(r'[^\w\s₹\-\.\/]', '', str(text)).strip()
    if len(text) > max_len:
        text = text[:max_len - 2] + ".."
    return text or "Option"