# chats/message_handler.py
from datetime import datetime
from database.database import messages, mapping
from bot import process_message
from chats.whatsapp_sender import send_whatsapp_message
import os
from dotenv import load_dotenv

load_dotenv('.env')

OWNER_PHONE = os.getenv('OWNER_PHONE')

# Store conversation states
conversation_states = {}

def process_incoming_message(message_data):
    """Process incoming WhatsApp message"""
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
    
    if user_phone not in conversation_states:
        conversation_states[user_phone] = {
            "step": "greeting",
            "context": {},
            "packages": []
        }
    
    state = conversation_states[user_phone]
    
    try:
        response = process_message(user_message, OWNER_PHONE, state)
    except Exception as e:
        print("❌ Bot error:", e)
        response = {
            "type": "text",
            "content": "⚠️ Error occurred"
        }
    
    if response.get("new_state"):
        conversation_states[user_phone].update(response["new_state"])
    
    if not response or not response.get("content"):
        response = {
            "type": "text",
            "content": "Something went wrong"
        }
    
    messages.insert_one({
        "user_phone": user_phone,
        "user_id": partner_id,
        "message": response.get("content", ""),
        "from": "bot",
        "timestamp": datetime.utcnow()
    })
    
    send_whatsapp_message(user_phone, response)