# chats/routes.py

from flask import request, jsonify
from datetime import datetime
from database.database import messages, users, get_whatsapp_config, get_all_active_whatsapp_numbers, whatsapp_numbers,get_next_user_id
from chats.whatsapp_sender import send_whatsapp_message
from bson.objectid import ObjectId
import re


def normalize_phone_number(phone_number):
    """
    Normalize phone number for consistent matching
    Converts +91 98164 40734 -> 919816440734
    Converts  91 98164 40734 -> 919816440734
    Converts 919816440734 -> 919816440734
    """
    if not phone_number:
        return None
    normalized = re.sub(r'[^\d]', '', str(phone_number))
    if normalized.startswith('0'):
        normalized = normalized[1:]
    return normalized


def register_chat_routes(app):
    """Register all chat-related routes"""
    
    @app.route('/get-all-users-with-chats', methods=['GET', 'OPTIONS'])
    def get_all_users_with_chats():
        """
        Get ALL users with their complete chat history
        Optional filter by display_phone_number (WhatsApp business number)
        """
        if request.method == 'OPTIONS':
            return '', 200
        
        try:
            display_phone_number = request.args.get("display_phone_number")
            
            print(f"🔍 get-all-users-with-chats called - display: '{display_phone_number}'")
            
            # Build query for users
            user_query = {}
            if display_phone_number:
                normalized = normalize_phone_number(display_phone_number)
                user_query["display_phone_number_raw"] = normalized
            
            # Get all users
            all_users = list(users.find(user_query, {"_id": 0}).sort("last_seen", -1))
            
            result = []
            
            for user in all_users:
                # Build message query for this user
                message_query = {"user_phone": user["user_phone"]}
                if display_phone_number:
                    normalized = normalize_phone_number(display_phone_number)
                    message_query["display_phone_number_raw"] = normalized
                
                # Get ALL messages for this user
                user_messages = list(messages.find(message_query).sort("timestamp", 1))
                
                # Format messages
                formatted_messages = []
                for msg in user_messages:
                    formatted_messages.append({
                        "message_id": str(msg["_id"]),
                        "message": msg.get("message"),
                        "from": msg.get("from"),
                        "timestamp": msg.get("timestamp"),
                        "sender_phone_number_id": msg.get("sender_phone_number_id"),
                        "display_phone_number": msg.get("display_phone_number") or msg.get("display_phone_number_raw")
                    })
                
                # Get last message for summary
                last_msg = user_messages[-1] if user_messages else None
                
                result.append({
                    "user_id": user["user_id"],
                    "user_phone": user["user_phone"],
                    "username": user.get("username"),
                    "whatsapp_number_id": user.get("whatsapp_number_id"),
                    "display_phone_number_raw": user.get("display_phone_number_raw"),
                    "total_messages": user.get("total_messages", 0),
                    "created_at": user.get("created_at"),
                    "last_seen": user.get("last_seen"),
                    "last_message": str(last_msg.get("message", ""))[:100] if last_msg else None,
                    "last_message_time": last_msg.get("timestamp") if last_msg else None,
                    "chats": formatted_messages
                })
            
            return jsonify({
                "success": True,
                "display_phone_number": display_phone_number,
                "total_users": len(result),
                "users": result
            }), 200
            
        except Exception as e:
            print(f"Error in get_all_users_with_chats: {e}")
            import traceback
            traceback.print_exc()
            return jsonify({"error": str(e)}), 500

    @app.route('/get-user-with-chats', methods=['GET', 'OPTIONS'])
    def get_user_with_chats():
        """
        Get specific user with their complete chat history
        Can filter by user_id or user_phone
        """
        if request.method == 'OPTIONS':
            return '', 200
        
        try:
            user_id = request.args.get("user_id")
            user_phone = request.args.get("user_phone")
            display_phone_number = request.args.get("display_phone_number")
            
            if not user_id and not user_phone:
                return jsonify({"error": "user_id or user_phone is required"}), 400
            
            # Build user query
            user_query = {}
            if user_id:
                try:
                    user_query["user_id"] = int(user_id)
                except:
                    return jsonify({"error": "user_id must be number"}), 400
            if user_phone:
                user_query["user_phone"] = user_phone
            
            # Get user
            user = users.find_one(user_query, {"_id": 0})
            if not user:
                return jsonify({"error": "User not found"}), 404
            
            # Build message query
            message_query = {"user_phone": user["user_phone"]}
            if display_phone_number:
                normalized = normalize_phone_number(display_phone_number)
                message_query["display_phone_number_raw"] = normalized
            
            # Get ALL messages for this user
            user_messages = list(messages.find(message_query).sort("timestamp", 1))
            
            # Format messages
            formatted_messages = []
            for msg in user_messages:
                formatted_messages.append({
                    "message_id": str(msg["_id"]),
                    "message": msg.get("message"),
                    "from": msg.get("from"),
                    "timestamp": msg.get("timestamp"),
                    "sender_phone_number_id": msg.get("sender_phone_number_id"),
                    "display_phone_number": msg.get("display_phone_number") or msg.get("display_phone_number_raw")
                })
            
            # Get last message
            last_msg = user_messages[-1] if user_messages else None
            
            result = {
                "user_id": user["user_id"],
                "user_phone": user["user_phone"],
                "username": user.get("username"),
                "whatsapp_number_id": user.get("whatsapp_number_id"),
                "display_phone_number_raw": user.get("display_phone_number_raw"),
                "total_messages": user.get("total_messages", 0),
                "created_at": user.get("created_at"),
                "last_seen": user.get("last_seen"),
                "last_message": str(last_msg.get("message", ""))[:100] if last_msg else None,
                "last_message_time": last_msg.get("timestamp") if last_msg else None,
                "chats": formatted_messages
            }
            
            return jsonify({
                "success": True,
                "user": result
            }), 200
            
        except Exception as e:
            print(f"Error in get_user_with_chats: {e}")
            import traceback
            traceback.print_exc()
            return jsonify({"error": str(e)}), 500

    @app.route('/get-users-by-whatsapp-number', methods=['GET', 'OPTIONS'])
    def get_users_by_whatsapp_number():
        """Get all users who chatted with a specific WhatsApp business number with their chats"""
        if request.method == 'OPTIONS':
            return '', 200
        
        display_phone_number = request.args.get("display_phone_number")
        
        if not display_phone_number:
            return jsonify({"error": "display_phone_number is required"}), 400
        
        try:
            normalized = normalize_phone_number(display_phone_number)
            
            # Get all users who have this display_phone_number_raw
            users_list = list(users.find(
                {"display_phone_number_raw": normalized},
                {"_id": 0}
            ).sort("last_seen", -1))
            
            result = []
            
            for user in users_list:
                # Get ALL messages for this user with this WhatsApp number
                user_messages = list(messages.find({
                    "user_phone": user["user_phone"],
                    "display_phone_number_raw": normalized
                }).sort("timestamp", 1))
                
                # Format messages
                formatted_messages = []
                for msg in user_messages:
                    formatted_messages.append({
                        "message_id": str(msg["_id"]),
                        "message": msg.get("message"),
                        "from": msg.get("from"),
                        "timestamp": msg.get("timestamp"),
                        "sender_phone_number_id": msg.get("sender_phone_number_id")
                    })
                
                # Get last message
                last_msg = user_messages[-1] if user_messages else None
                
                result.append({
                    "user_id": user["user_id"],
                    "user_phone": user["user_phone"],
                    "username": user.get("username"),
                    "total_messages": len(user_messages),
                    "created_at": user.get("created_at"),
                    "last_seen": user.get("last_seen"),
                    "last_message": str(last_msg.get("message", ""))[:100] if last_msg else None,
                    "last_message_time": last_msg.get("timestamp") if last_msg else None,
                    "chats": formatted_messages
                })
            
            return jsonify({
                "success": True,
                "display_phone_number": display_phone_number,
                "total_users": len(result),
                "users": result
            }), 200
            
        except Exception as e:
            print(f"Error in get_users_by_whatsapp_number: {e}")
            import traceback
            traceback.print_exc()
            return jsonify({"error": str(e)}), 500

    @app.route('/get-chats', methods=['GET', 'OPTIONS'])
    def get_chats():
        """Get chat history for a user (simple version)"""
        if request.method == 'OPTIONS':
            return '', 200
            
        user_id = request.args.get("user_id")
        user_phone = request.args.get("user_phone")
        display_phone_number = request.args.get("display_phone_number")

        if not user_id and not user_phone:
            return jsonify({"error": "user_id or user_phone is required"}), 400

        query = {}
        if user_id:
            try:
                query["user_id"] = int(user_id)
            except:
                return jsonify({"error": "user_id must be number"}), 400
        if user_phone:
            query["user_phone"] = user_phone
        if display_phone_number:
            normalized = normalize_phone_number(display_phone_number)
            query["display_phone_number_raw"] = normalized
        
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
        """Get all users (without chats, just user info)"""
        if request.method == 'OPTIONS':
            return '', 200
            
        try:
            display_phone_number = request.args.get("display_phone_number")
            user_id = request.args.get("user_id")
            
            query = {}
            if user_id:
                try:
                    query["user_id"] = int(user_id)
                except:
                    return jsonify({"error": "user_id must be number"}), 400
            if display_phone_number:
                normalized = normalize_phone_number(display_phone_number)
                query["display_phone_number_raw"] = normalized
            
            user_list = list(users.find(query, {"_id": 0}).sort("last_seen", -1))
            
            # Add last message for each user
            for user in user_list:
                last_msg = messages.find_one(
                    {"user_phone": user["user_phone"]},
                    sort=[("timestamp", -1)]
                )
                if last_msg:
                    user["last_message"] = str(last_msg.get("message", ""))[:100]
                    user["last_message_time"] = last_msg.get("timestamp")
                    user["last_message_from"] = last_msg.get("from")
            
            return jsonify({
                "success": True,
                "users": user_list,
                "count": len(user_list)
            }), 200
            
        except Exception as e:
            print(f"Error in get_users: {e}")
            return jsonify({"error": str(e)}), 500

    @app.route('/send-message', methods=['POST', 'OPTIONS'])
    def send_message():
        """Send message from partner to user"""
        if request.method == 'OPTIONS':
            return '', 200
            
        data = request.json
        user_phone = data.get("user_phone")
        message = data.get("message")
        user_id = data.get("user_id")
        display_phone_number = data.get("display_phone_number")
        
        if not user_phone:
            return jsonify({"error": "user_phone is required"}), 400
        
        if not message:
            return jsonify({"error": "message is required"}), 400
        
        user = users.find_one({"user_phone": user_phone})
        if not user:
            return jsonify({"error": f"User {user_phone} not found"}), 404
        
        actual_user_id = user["user_id"]
        
        sender_phone_number_id = None
        if display_phone_number:
            normalized = normalize_phone_number(display_phone_number)
            wa_config = whatsapp_numbers.find_one({
                "$or": [
                    {"display_phone_number_raw": normalized},
                    {"display_number": normalized}
                ]
            })
            if wa_config:
                sender_phone_number_id = wa_config["phone_number_id"]
                display_phone_number = wa_config.get("display_phone_number_raw") or wa_config.get("display_number")
        
        if not sender_phone_number_id:
            active_numbers = get_all_active_whatsapp_numbers()
            if active_numbers:
                sender_phone_number_id = active_numbers[0]["phone_number_id"]
                display_phone_number = active_numbers[0].get("display_phone_number_raw") or active_numbers[0].get("display_number")
            else:
                return jsonify({"error": "No active WhatsApp number found"}), 500
        
        messages.insert_one({
            "user_phone": user_phone,
            "user_id": actual_user_id,
            "message": message,
            "from": "partner",
            "timestamp": datetime.utcnow(),
            "display_phone_number_raw": display_phone_number,
            "sender_phone_number_id": sender_phone_number_id
        })
        
        from chats.whatsapp_sender import send_whatsapp_message
        result = send_whatsapp_message(user_phone, {
            "type": "text",
            "content": message
        }, sender_phone_number_id)
        
        if result:
            return jsonify({"status": "sent", "success": True})
        else:
            return jsonify({"status": "failed", "success": False}), 500

    @app.route('/get-whatsapp-numbers', methods=['GET', 'OPTIONS'])
    def get_whatsapp_numbers():
        """Get all active WhatsApp business numbers from database"""
        if request.method == 'OPTIONS':
            return '', 200
        
        numbers = get_all_active_whatsapp_numbers()
        result = []
        for num in numbers:
            result.append({
                "phone_number_id": num.get("phone_number_id"),
                "display_number": num.get("display_phone_number_raw") or num.get("display_number"),
                "verified_name": num.get("verified_name"),
                "status": num.get("status", "active")
            })
        
        return jsonify({
            "success": True,
            "numbers": result
        }), 200

    @app.route('/user-stats', methods=['GET', 'OPTIONS'])
    def user_stats():
        """Get statistics about users"""
        if request.method == 'OPTIONS':
            return '', 200
        
        total_users = users.count_documents({})
        
        today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        active_today = users.count_documents({
            "last_seen": {"$gte": today_start}
        })
        
        users_per_number = {}
        all_numbers = get_all_active_whatsapp_numbers()
        
        for num in all_numbers:
            display = num.get("display_phone_number_raw") or num.get("display_number")
            if display:
                user_count = users.count_documents({"display_phone_number_raw": display})
                users_per_number[display] = user_count
        
        return jsonify({
            "success": True,
            "total_users": total_users,
            "active_today": active_today,
            "users_per_whatsapp_number": users_per_number
        }), 200

    @app.route('/debug-db', methods=['GET', 'OPTIONS'])
    def debug_db():
        """Debug endpoint to see what's in the database"""
        if request.method == 'OPTIONS':
            return '', 200
        
        all_users = list(users.find({}, {"_id": 0}))
        distinct_display_numbers = messages.distinct("display_phone_number_raw")
        all_whatsapp_numbers = list(whatsapp_numbers.find({}, {"_id": 0}))
        
        return jsonify({
            "success": True,
            "users_count": len(all_users),
            "users": all_users[:10],
            "distinct_display_numbers_in_messages": distinct_display_numbers,
            "whatsapp_numbers_in_db": all_whatsapp_numbers
        }), 200
    @app.route('/create-user-if-not-exists', methods=['POST', 'OPTIONS'])
    def create_user_if_not_exists():
        """Create user ONLY if not exists for THIS SPECIFIC business number"""
        if request.method == 'OPTIONS':
            return '', 200
        
        try:
            data = request.json
            user_phone = data.get('user_phone')
            username = data.get('username')
            display_phone_number = data.get('display_phone_number')
            
            if not user_phone:
                return jsonify({"error": "user_phone is required"}), 400
            
            if not display_phone_number:
                return jsonify({"error": "display_phone_number is required"}), 400
            
            # Clean phone number
            clean_phone = re.sub(r'[^\d]', '', user_phone)
            if len(clean_phone) == 10:
                clean_phone = '91' + clean_phone
            
            # Normalize display number
            normalized_display = normalize_phone_number(display_phone_number)
            
            # CRITICAL: Check if user exists for THIS SPECIFIC business number
            existing_user = users.find_one({
                "user_phone": clean_phone,
                "display_phone_number_raw": normalized_display
            })
            
            if existing_user:
                existing_user.pop('_id', None)
                return jsonify({
                    "success": True,
                    "user": existing_user,
                    "is_new": False,
                    "message": "User already exists for this WhatsApp business number"
                }), 200
            
            # Create new user for THIS business number only
            new_user_id = get_next_user_id()
            new_user = {
                "user_id": new_user_id,
                "user_phone": clean_phone,
                "username": username,
                "whatsapp_number_id": None,
                "display_phone_number_raw": normalized_display,
                "created_at": datetime.utcnow(),
                "last_seen": datetime.utcnow(),
                "total_messages": 0,
                "is_active": True
            }
            users.insert_one(new_user)
            
            new_user.pop('_id', None)
            
            return jsonify({
                "success": True,
                "user": new_user,
                "is_new": True,
                "message": f"User {clean_phone} created for {normalized_display}"
            }), 200
            
        except Exception as e:
            print(f"Error in create_user_if_not_exists: {e}")
            import traceback
            traceback.print_exc()
            return jsonify({"error": str(e)}), 500