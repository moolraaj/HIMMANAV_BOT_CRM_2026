# webhook.py  — clean final version

from flask import Flask, request, jsonify
import json, os, logging
from dotenv import load_dotenv
from flask_cors import CORS

from chats.routes import register_chat_routes
from chats.delete_routes import register_delete_routes
from chats.message_handler import process_incoming_message
from chats.queue_manager import user_queue_manager

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

@app.after_request
def after_request(response):
    response.headers.update({
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Headers': 'Content-Type, Authorization, ngrok-skip-browser-warning',
        'Access-Control-Allow-Methods': 'GET, POST, PUT, DELETE, OPTIONS',
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


@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.get_json()
    logger.debug(f"📨 Incoming: {json.dumps(data)[:300]}")

    if 'entry' in data:
        for entry in data['entry']:
            for change in entry.get('changes', []):
                value = change.get('value', {})

                # FIX: iterate ALL messages, not just [0]
                for message_data in value.get('messages', []):
                    phone = message_data.get('from', 'unknown')
                    user_queue_manager.enqueue(
                        phone=phone,
                        message_data=message_data,
                        handler_fn=process_incoming_message
                    )

    return jsonify({"status": "ok"}), 200


@app.route('/health', methods=['GET', 'OPTIONS'])
def health():
    if request.method == 'OPTIONS':
        return '', 200
    stats = user_queue_manager.stats()
    return jsonify({"status": "ok", "healthy": True, "queue": stats})


@app.route('/queue/stats', methods=['GET'])
def queue_stats():
    """Monitoring endpoint — see active users + queue depths"""
    return jsonify(user_queue_manager.stats())


if __name__ == '__main__':
    logger.info("🚀 WhatsApp Bot starting...")
    app.run(port=5000, debug=False, host='0.0.0.0')