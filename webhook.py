# webhook.py — FIXED:  
import eventlet
eventlet.monkey_patch()
from flask import render_template

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

 
app.socketio = socketio


 
@socketio.on('join')
def handle_join(data):
    room = data.get('room')
    if room:
        join_room(room)
        logger.info(f"🔗 Client joined room: {room}")


 
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


 
app.emit_new_message = emit_new_message


 
@app.after_request
def after_request(response):
    response.headers.update({
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Headers': 'Content-Type, Authorization, ngrok-skip-browser-warning',
        'Access-Control-Allow-Methods': 'GET, POST, PUT, PATCH, DELETE, OPTIONS',
        'Access-Control-Allow-Credentials': 'true',
    })
    return response


 
register_chat_routes(app)
register_delete_routes(app)


 
@app.route('/webhook', methods=['GET'])
def verify_webhook():
    mode = request.args.get('hub.mode')
    token = request.args.get('hub.verify_token')
    challenge = request.args.get('hub.challenge')

    if mode == 'subscribe' and token == VERIFY_TOKEN:
        return challenge, 200

    return "Verification failed", 403

@app.route('/')
def home():
    return render_template('index.html')

 
@app.route('/status')
def status():
    return jsonify({"ok": True})
 
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

                    text_body = ""
                    if message_data.get("text"):
                        text_body = message_data.get("text", {}).get("body", "")
                    elif message_data.get("button"):
                        text_body = message_data.get("button", {}).get("text", "")
                    elif message_data.get("interactive"):
                        text_body = json.dumps(message_data.get("interactive"))

                    display_phone_number = phone_number_id
                    if phone_number_id:
                        sender_config = get_whatsapp_config(phone_number_id)
                        if sender_config:
                            display_phone_number = sender_config.get("display_phone_number_raw") or sender_config.get("display_number") or phone_number_id

                    # Enqueue for bot processing
                    # NOTE: user message emit is handled inside message_handler
                    # to avoid duplicates — do NOT emit here
                    user_queue_manager.enqueue(
                        phone=phone,
                        message_data=message_data,
                        handler_fn=process_incoming_message,
                        sender_phone_number_id=phone_number_id,
                        emit_fn=emit_new_message,
                        display_phone_number=display_phone_number
                    )

    return jsonify({"status": "ok"}), 200


 
@app.route('/agent/takeover', methods=['POST'])
def agent_takeover():
    """Agent takes over a chat"""
    data = request.get_json()
    user_phone = data.get('user_phone')
    agent_phone = data.get('agent_phone', 'Agent')
    agent_name = data.get('agent_name', agent_phone)
    display_phone_number = data.get('display_phone_number')

    if not user_phone:
        return jsonify({"error": "user_phone required"}), 400

    from chats.message_handler import agent_takeover_chat
    agent_takeover_chat(user_phone, agent_phone)

     
    try:
        config = get_whatsapp_config(display_phone_number) if display_phone_number else None
        phone_number_id = config.get('phone_number_id') if config else None

        if phone_number_id:
            from chats.whatsapp_sender import send_whatsapp_message
            send_whatsapp_message(
                user_phone,
                {
                    "type": "text",
                    "content": f"👤 You are now connected with a live agent ({agent_name}). The bot has been paused."
                },
                phone_number_id
            )
    except Exception as e:
        logger.error(f"❌ Failed to send WhatsApp takeover message: {e}")

   
    emit_new_message(
        user_phone=user_phone,
        message_data={
            "from": "system",
            "message": {
                "type": "text",
                "content": f"👤 Agent {agent_name} has taken over the chat. Bot responses are now disabled."
            },
            "timestamp": datetime.utcnow().isoformat() + 'Z'
        },
        display_phone_number=display_phone_number
    )

    return jsonify({"success": True, "message": "Agent has taken over"}), 200


 
@app.route('/agent/release', methods=['POST'])
def agent_release():
    """Release chat back to bot"""
    data = request.get_json()
    user_phone = data.get('user_phone')
    display_phone_number = data.get('display_phone_number')

    if not user_phone:
        return jsonify({"error": "user_phone required"}), 400

    from chats.message_handler import agent_release_chat
    agent_release_chat(user_phone)

     
    try:
        config = get_whatsapp_config(display_phone_number) if display_phone_number else None
        phone_number_id = config.get('phone_number_id') if config else None

        if phone_number_id:
            from chats.whatsapp_sender import send_whatsapp_message
            send_whatsapp_message(
                user_phone,
                {
                    "type": "text",
                    "content": "🤖 You have been reconnected with our bot. How can I help you?"
                },
                phone_number_id
            )
    except Exception as e:
        logger.error(f"❌ Failed to send WhatsApp release message: {e}")

     
    emit_new_message(
        user_phone=user_phone,
        message_data={
            "from": "system",
            "message": {
                "type": "text",
                "content": "🤖 Bot has resumed control. You can now use bot features again."
            },
            "timestamp": datetime.utcnow().isoformat() + 'Z'
        },
        display_phone_number=display_phone_number
    )

    return jsonify({"success": True, "message": "Bot resumed"}), 200


 
@app.route('/agent/status/<user_phone>', methods=['GET'])
def agent_status(user_phone):
    """Check if agent is active for this chat"""
    from chats.message_handler import is_agent_active
    return jsonify({
        "agent_active": is_agent_active(user_phone),
        "user_phone": user_phone
    }), 200


 
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


 
@app.route('/health', methods=['GET', 'OPTIONS'])
def health():
    if request.method == 'OPTIONS':
        return '', 200
    stats = user_queue_manager.stats()
    return jsonify({"status": "ok", "queue": stats})


@app.route('/queue/stats', methods=['GET'])
def queue_stats():
    return jsonify(user_queue_manager.stats())


 
if __name__ == '__main__':
    logger.info("🚀 WhatsApp Bot starting with REALTIME...")
    socketio.run(
        app,
        port=5000,
        host='0.0.0.0',
        debug=False
    )