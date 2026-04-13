# whatsapp_webhook.py
from flask import Flask, request, jsonify
import requests
import json
import re
from bot import process_message
import os
from dotenv import load_dotenv
load_dotenv('.env')
ACCESS_TOKEN=os.getenv('ACCESS_TOKEN')
PHONE_NUMBER_ID=os.getenv('PHONE_NUMBER_ID')
VERIFY_TOKEN=os.getenv('VERIFY_TOKEN')

app = Flask(__name__)

# ========== STORE CONVERSATIONS BY PHONE NUMBER ==========
# This was missing - causing the NameError
conversation_states = {}  # phone_number -> state dict

# ========== WHATSAPP WEBHOOK VERIFICATION ==========
@app.route('/webhook', methods=['GET'])
def verify_webhook():
    """WhatsApp sends this GET request to verify your webhook"""
    mode = request.args.get('hub.mode')
    token = request.args.get('hub.verify_token')
    challenge = request.args.get('hub.challenge')
    
    print(f"🔐 Verification request - Mode: {mode}, Token: {token}")
    
    if mode and token:
        if mode == 'subscribe' and token == VERIFY_TOKEN:
            print("✅ Webhook verified successfully!")
            return challenge, 200
        else:
            print("❌ Verification failed - Token mismatch")
            return "Verification failed", 403
    
    return "Verification failed", 403

# ========== RECEIVE MESSAGES FROM WHATSAPP ==========
@app.route('/webhook', methods=['POST'])
def webhook():
    """WhatsApp sends user messages here"""
    data = request.get_json()
    
    print("\n" + "="*50)
    print("📨 Received webhook from WhatsApp")
    print(f"📦 Full data: {json.dumps(data, indent=2)[:500]}")  # Print first 500 chars
    
    # Check if it's a WhatsApp message
    if 'entry' in data:
        for entry in data['entry']:
            for change in entry.get('changes', []):
                if 'messages' in change.get('value', {}):
                    message_data = change['value']['messages'][0]
                    process_incoming_message(message_data)
                else:
                    print("ℹ️ No messages in this webhook (maybe status update)")
    
    return jsonify({"status": "ok"}), 200

# ========== PROCESS INCOMING WHATSAPP MESSAGE ==========
def process_incoming_message(message_data):
    """Convert WhatsApp message format to your bot's format"""
    
    # Extract user info
    user_phone = message_data['from']
    
    # Extract message text or button response
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
        # Handle legacy button format
        user_message = message_data['button']['payload']
    
    print(f"📱 From: {user_phone}")
    print(f"💬 Message: {user_message}")
    
    # Get or create conversation state for this user
    if user_phone not in conversation_states:
        conversation_states[user_phone] = {
            "step": "greeting",
            "context": {},
            "packages": []
        }
        print(f"🆕 New conversation started for {user_phone}")
    
    state = conversation_states[user_phone]
    
    # Use your existing bot logic
    try:
        response = process_message(user_message, user_phone, state)
        print(f"🤖 Bot response type: {response.get('type')}")
    except Exception as e:
        print(f"❌ Error in process_message: {e}")
        import traceback
        traceback.print_exc()
        response = {
            "type": "text",
            "content": "⚠️ Sorry, I encountered an error. Please try again later."
        }
    
    # Update state
    if response.get("new_state"):
        conversation_states[user_phone].update(response["new_state"])
        print(f"📝 State updated: {response.get('new_state')}")
    
    # Send response back to WhatsApp
    send_whatsapp_message(user_phone, response)

# ========== SEND MESSAGE TO WHATSAPP ==========
def send_whatsapp_message(to_phone, response):
    """Send message to WhatsApp (supports text and buttons)"""
    
    url = f"https://graph.facebook.com/v18.0/{PHONE_NUMBER_ID}/messages"
    
    headers = {
        "Authorization": f"Bearer {ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }
    
    # Handle different response types
    if response.get("type") == "buttons" and response.get("buttons"):
        # WhatsApp max 3 buttons, take first 3
        buttons = response["buttons"][:3]
        
        whatsapp_buttons = []
        for btn in buttons:
            # Clean button text (max 20 chars for WhatsApp)
            button_text = btn["text"]
            # Remove emojis and clean up
            button_text = re.sub(r'[📦🔙🏠🎯💰📍✅❌]', '', button_text)
            button_text = button_text.strip()
            if len(button_text) > 20:
                button_text = button_text[:17] + "..."
            
            whatsapp_buttons.append({
                "type": "reply",
                "reply": {
                    "id": btn["value"],
                    "title": button_text
                }
            })
        
        # Ensure content is not too long
        content = response["content"]
        if len(content) > 1024:
            content = content[:1021] + "..."
        
        data = {
            "messaging_product": "whatsapp",
            "to": to_phone,
            "type": "interactive",
            "interactive": {
                "type": "button",
                "body": {"text": content},
                "action": {"buttons": whatsapp_buttons}
            }
        }
        print(f"📤 Sending {len(whatsapp_buttons)} buttons to {to_phone}")
    else:
        # Send plain text message
        content = response.get("content", "I'm here to help!")
        if len(content) > 4096:
            content = content[:4093] + "..."
        
        data = {
            "messaging_product": "whatsapp",
            "to": to_phone,
            "type": "text",
            "text": {"body": content}
        }
        print(f"📤 Sending text to {to_phone}")
    
    try:
        api_response = requests.post(url, headers=headers, json=data, timeout=10)
        print(f"✅ API Response Status: {api_response.status_code}")
        if api_response.status_code == 200:
            print("✅ Message sent successfully!")
            response_data = api_response.json()
            print(f"📨 Message ID: {response_data.get('messages', [{}])[0].get('id', 'N/A')}")
        else:
            print(f"❌ Error: {api_response.text}")
        return api_response.json()
    except Exception as e:
        print(f"❌ Send error: {e}")
        return None

# ========== HEALTH CHECK ==========
@app.route('/health', methods=['GET'])
def health():
    return jsonify({
        "status": "ok", 
        "conversations": len(conversation_states),
        "active_sessions": list(conversation_states.keys()),
        "bot_status": "running"
    })

@app.route('/', methods=['GET'])
def home():
    return jsonify({
        "message": "WhatsApp Bot is running!",
        "webhook_url": "/webhook",
        "health_check": "/health",
        "verify_token": VERIFY_TOKEN,
        "active_conversations": len(conversation_states)
    })

# ========== DEBUG ENDPOINT (for testing without WhatsApp) ==========
@app.route('/test', methods=['POST'])
def test():
    """Test endpoint to simulate WhatsApp messages"""
    test_data = request.get_json()
    user_message = test_data.get('message', 'hi')
    test_phone = test_data.get('phone', 'TEST_USER')
    
    print("\n🧪 TEST MODE")
    print(f"💬 Test message: {user_message}")
    
    # Create test state
    if test_phone not in conversation_states:
        conversation_states[test_phone] = {
            "step": "greeting",
            "context": {},
            "packages": []
        }
    
    state = conversation_states[test_phone]
    response = process_message(user_message, test_phone, state)
    
    if response.get("new_state"):
        conversation_states[test_phone].update(response["new_state"])
    
    return jsonify({
        "success": True,
        "response": response
    })

if __name__ == '__main__':
    print("="*50)
    print("🚀 WhatsApp Bot Starting...")
    print("="*50)
    print(f"📍 Webhook URL: https://YOUR_NGROK_URL/webhook")
    print(f"🔑 Verify Token: {VERIFY_TOKEN}")
    print(f"📞 Phone Number ID: {PHONE_NUMBER_ID}")
    print("⚠️  Make sure PHONE_NUMBER_ID is correct!")
    print("="*50)
    app.run(debug=True, port=5000)