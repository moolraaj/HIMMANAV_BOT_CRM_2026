# webhook.py
from flask import Flask, request, jsonify
import json
import os
from dotenv import load_dotenv
from flask_cors import CORS

# Import from chats folder
from chats.routes import register_chat_routes
from chats.delete_routes import register_delete_routes
from chats.message_handler import process_incoming_message

load_dotenv('.env')

ACCESS_TOKEN = os.getenv('ACCESS_TOKEN')
VERIFY_TOKEN = os.getenv('VERIFY_TOKEN')

app = Flask(__name__)

# Configure CORS
CORS(app, 
     resources={r"/*": {"origins": "*"}}, 
     supports_credentials=True,
     allow_headers=["Content-Type", "Authorization", "ngrok-skip-browser-warning", "X-Requested-With"])

@app.after_request
def after_request(response):
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type, Authorization, ngrok-skip-browser-warning, X-Requested-With')
    response.headers.add('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, OPTIONS')
    response.headers.add('Access-Control-Allow-Credentials', 'true')
    return response

# Register all routes from chats folder
register_chat_routes(app)
register_delete_routes(app)

# =========================
# VERIFY WEBHOOK
# =========================
@app.route('/webhook', methods=['GET'])
def verify_webhook():
    mode = request.args.get('hub.mode')
    token = request.args.get('hub.verify_token')
    challenge = request.args.get('hub.challenge')
    
    if mode == 'subscribe' and token == VERIFY_TOKEN:
        return challenge, 200
    return "Verification failed", 403

# =========================
# RECEIVE WHATSAPP MESSAGE
# =========================
@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.get_json()
    print("📨 Incoming:", json.dumps(data)[:500])
    
    if 'entry' in data:
        for entry in data['entry']:
            for change in entry.get('changes', []):
                value = change.get('value', {})
                if 'messages' in value:
                    message_data = value['messages'][0]
                    process_incoming_message(message_data)
    
    return jsonify({"status": "ok"}), 200

# =========================
# HEALTH CHECK
# =========================
@app.route('/health', methods=['GET', 'OPTIONS'])
def health():
    if request.method == 'OPTIONS':
        return '', 200
    return jsonify({"status": "ok", "healthy": True})

# =========================
# RUN APP
# =========================
if __name__ == '__main__':
    print("🚀 WhatsApp Bot Running...")
    print("✅ CORS enabled")
    print("📁 Routes loaded from chats/ folder")
    app.run(port=5000, debug=True, host='0.0.0.0')