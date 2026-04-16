# chats/routes.py
from flask import request, jsonify
from datetime import datetime
from database.database import messages
from chats.whatsapp_sender import send_whatsapp_message

def register_chat_routes(app):
    """Register all chat-related routes"""
    
    @app.route('/get-chats', methods=['GET', 'OPTIONS'])
    def get_chats():
        if request.method == 'OPTIONS':
            return '', 200
            
        user_id = request.args.get("user_id")
        user_phone = request.args.get("user_phone")

        print("🔥 user_id received:", user_id)
        print("📱 user_phone received:", user_phone)

        if user_id is None:
            return jsonify({
                "error": "user_id missing",
                "hint": "Use ?user_id=13"
            }), 400

        try:
            user_id = int(user_id)
        except:
            return jsonify({"error": "user_id must be number"}), 400

        query = {"user_id": user_id}
        if user_phone:
            query["user_phone"] = user_phone
        
        chats = list(messages.find(query).sort("timestamp", 1))

        for c in chats:
            c["_id"] = str(c["_id"])

        return jsonify({
            "success": True,
            "chats": chats,
            "count": len(chats)
        })

    @app.route('/get-users', methods=['GET', 'OPTIONS'])
    def get_users():
        if request.method == 'OPTIONS':
            return '', 200
            
        try:
            partner_id = request.args.get("partner_id")
            user_id = request.args.get("user_id")
            
            target_id = partner_id or user_id
            
            if not target_id:
                return jsonify({"error": "partner_id or user_id is required"}), 400
            
            target_id = int(target_id)
            
            users = messages.distinct("user_phone", {"user_id": target_id})
            
            return jsonify({
                "success": True,
                "partner_id": target_id,
                "users": users,
                "count": len(users)
            }), 200
            
        except Exception as e:
            print(f"Error in get_users: {e}")
            return jsonify({"error": str(e)}), 500

    @app.route('/send-message', methods=['POST', 'OPTIONS'])
    def send_message():
        if request.method == 'OPTIONS':
            return '', 200
            
        data = request.json
        user_phone = data.get("user_phone")
        message = data.get("message")
        user_id = data.get("user_id")
        partner_id = data.get("partner_id")
        
        target_id = user_id or partner_id

        messages.insert_one({
            "user_phone": user_phone,
            "user_id": target_id,
            "message": message,
            "from": "partner",
            "timestamp": datetime.utcnow()
        })

        send_whatsapp_message(user_phone, {
            "type": "text",
            "content": message
        })

        return jsonify({"status": "sent", "success": True})