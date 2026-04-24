# webhook.py — FIXED: bot messages now emitted to frontend

# ✅ MUST BE FIRST
import eventlet
eventlet.monkey_patch()

from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_socketio import SocketIO, join_room
import json, os, logging
from dotenv import load_dotenv
from datetime import datetime

from chats.routes import register_chat_routes
from chats.delete_routes import register_delete_routes
from chats.message_handler import process_incoming_message
from chats.queue_manager import user_queue_manager
from database.database import (
    save_or_update_whatsapp_number,
    get_whatsapp_config,
    update_whatsapp_metadata,
    get_all_active_whatsapp_numbers
)
from services.meta_api import get_whatsapp_number_metadata

load_dotenv('.env')

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s"
)
logger = logging.getLogger(__name__)

ACCESS_TOKEN = os.getenv('ACCESS_TOKEN')
VERIFY_TOKEN = os.getenv('VERIFY_TOKEN')

app = Flask(__name__)

CORS(app, resources={r"/*": {"origins": "*"}}, supports_credentials=True,
     allow_headers=["Content-Type", "Authorization", "ngrok-skip-browser-warning"])

socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet')

# Make socketio globally accessible for message_handler
app.socketio = socketio


# ================= SOCKET JOIN =================
@socketio.on('join')
def handle_join(data):
    room = data.get('room')
    if room:
        join_room(room)
        logger.info(f"🔗 Client joined room: {room}")


# ================= SOCKET EMIT =================
def emit_new_message(user_phone, message_data, display_phone_number):
    """
    Emit a message (user, bot, or partner) to the frontend room.
    display_phone_number is the room key — must match what frontend joins.
    """
    socketio.emit('new_message', {
        'user_phone': user_phone,
        'message': message_data
    }, room=display_phone_number)
    logger.info(f"📡 Emitted [{message_data.get('from')}] message to room {display_phone_number} for {user_phone}")


# Attach emit helper to app so message_handler can use it
app.emit_new_message = emit_new_message


# ================= HEADERS =================
@app.after_request
def after_request(response):
    response.headers.update({
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Headers': 'Content-Type, Authorization, ngrok-skip-browser-warning',
        'Access-Control-Allow-Methods': 'GET, POST, PUT, DELETE, OPTIONS',
        'Access-Control-Allow-Credentials': 'true',
    })
    return response


# ================= ROUTES =================
register_chat_routes(app)
register_delete_routes(app)


# ================= WEBHOOK VERIFY =================
@app.route('/webhook', methods=['GET'])
def verify_webhook():
    mode = request.args.get('hub.mode')
    token = request.args.get('hub.verify_token')
    challenge = request.args.get('hub.challenge')

    if mode == 'subscribe' and token == VERIFY_TOKEN:
        return challenge, 200

    return "Verification failed", 403


# ================= WEBHOOK RECEIVE =================
@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.get_json()
    logger.info("📨 Incoming webhook")

    if 'entry' in data:
        for entry in data['entry']:
            for change in entry.get('changes', []):
                value = change.get('value', {})

                metadata = value.get('metadata', {})
                phone_number_id = metadata.get('phone_number_id')

                if phone_number_id:
                    try:
                        config, is_new = save_or_update_whatsapp_number(phone_number_id)

                        if is_new:
                            logger.info(f"📱 New number: {phone_number_id}")
                            meta_metadata = get_whatsapp_number_metadata(phone_number_id, ACCESS_TOKEN)
                            if meta_metadata:
                                update_whatsapp_metadata(phone_number_id, meta_metadata)
                        else:
                            logger.info(f"🔄 Existing number: {phone_number_id}")

                    except Exception as e:
                        logger.error(f"❌ Phone number error: {e}")

                for message_data in value.get('messages', []):
                    phone = message_data.get('from', 'unknown')

                    # Extract message text for frontend emit
                    text_body = ""
                    if message_data.get("text"):
                        text_body = message_data.get("text", {}).get("body", "")
                    elif message_data.get("button"):
                        text_body = message_data.get("button", {}).get("text", "")
                    elif message_data.get("interactive"):
                        text_body = json.dumps(message_data.get("interactive"))

                    # Get the display phone number (room key) for this sender
                    display_phone_number = phone_number_id  # fallback
                    if phone_number_id:
                        sender_config = get_whatsapp_config(phone_number_id)
                        if sender_config:
                            display_phone_number = sender_config.get("display_phone_number_raw") or sender_config.get("display_number") or phone_number_id

                    # 1️⃣ Emit USER message to frontend immediately
                    emit_new_message(
                        user_phone=phone,
                        message_data={
                            "from": "user",
                            "message": text_body,
                            "timestamp": datetime.now().isoformat()
                        },
                        display_phone_number=display_phone_number
                    )

                    # 2️⃣ Queue processing (AI / DB) — bot response emitted inside handler
                    user_queue_manager.enqueue(
                        phone=phone,
                        message_data=message_data,
                        handler_fn=process_incoming_message,
                        sender_phone_number_id=phone_number_id,
                        # Pass emit function and display number so handler can emit bot reply
                        emit_fn=emit_new_message,
                        display_phone_number=display_phone_number
                    )

    return jsonify({"status": "ok"}), 200


# ================= PHONE APIs =================
@app.route('/phone-numbers', methods=['GET'])
def list_phone_numbers():
    numbers = get_all_active_whatsapp_numbers()
    return jsonify({"numbers": numbers}), 200


@app.route('/phone-number/<phone_number_id>', methods=['GET'])
def get_phone_number(phone_number_id):
    config = get_whatsapp_config(phone_number_id)
    if config:
        return jsonify(config), 200
    return jsonify({"error": "Not found"}), 404


@app.route('/sync-number-metadata/<phone_number_id>', methods=['POST'])
def sync_number_metadata(phone_number_id):
    metadata = get_whatsapp_number_metadata(phone_number_id, ACCESS_TOKEN)
    if metadata:
        update_whatsapp_metadata(phone_number_id, metadata)
        return jsonify({"status": "success", "metadata": metadata}), 200
    return jsonify({"error": "Failed"}), 400


# ================= HEALTH =================
@app.route('/health', methods=['GET', 'OPTIONS'])
def health():
    if request.method == 'OPTIONS':
        return '', 200
    stats = user_queue_manager.stats()
    return jsonify({"status": "ok", "queue": stats})


@app.route('/queue/stats', methods=['GET'])
def queue_stats():
    return jsonify(user_queue_manager.stats())


# ================= START SERVER =================
if __name__ == '__main__':
    logger.info("🚀 WhatsApp Bot starting with REALTIME...")
    socketio.run(
        app,
        port=5000,
        host='0.0.0.0',
        debug=False
    )