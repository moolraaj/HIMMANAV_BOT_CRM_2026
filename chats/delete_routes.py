# chats/delete_routes.py

from flask import request, jsonify
from bson.objectid import ObjectId
from database.database import messages, users


def register_delete_routes(app):
    """Register all DELETE routes"""
    
    @app.route('/delete-message', methods=['DELETE', 'OPTIONS'])
    def delete_message():
        """Delete single message only (keep user)"""
        if request.method == 'OPTIONS':
            return '', 200
        
        try:
            data = request.json
            message_id = data.get('message_id')
            
            if not message_id:
                return jsonify({"error": "message_id is required"}), 400
            
            result = messages.delete_one({"_id": ObjectId(message_id)})
            
            if result.deleted_count > 0:
                return jsonify({
                    "success": True,
                    "deleted_count": result.deleted_count,
                    "message": "Message deleted successfully"
                }), 200
            else:
                return jsonify({
                    "success": False,
                    "error": "Message not found"
                }), 404
                
        except Exception as e:
            print(f"Error deleting message: {e}")
            return jsonify({"error": str(e)}), 500

    @app.route('/delete-user-chats-only', methods=['DELETE', 'OPTIONS'])
    def delete_user_chats_only():
        """Delete ALL messages for a user BUT keep the user (clear chat only)"""
        if request.method == 'OPTIONS':
            return '', 200
        
        try:
            data = request.json
            user_phone = data.get('user_phone')
            user_id = data.get('user_id')
            
            if not user_phone and not user_id:
                return jsonify({"error": "user_phone or user_id is required"}), 400
            
            query = {}
            if user_phone:
                query["user_phone"] = user_phone
            if user_id:
                query["user_id"] = int(user_id)
            
            result = messages.delete_many(query)
            
            # Reset message count for user
            if user_phone:
                users.update_one(
                    {"user_phone": user_phone},
                    {"$set": {"total_messages": 0}}
                )
            
            return jsonify({
                "success": True,
                "deleted_count": result.deleted_count,
                "user_kept": True,
                "message": f"Cleared {result.deleted_count} messages. User remains in system."
            }), 200
            
        except Exception as e:
            print(f"Error clearing user chats: {e}")
            return jsonify({"error": str(e)}), 500

    @app.route('/delete-user-completely', methods=['DELETE', 'OPTIONS'])
    def delete_user_completely():
        """Delete user completely: ALL messages AND remove from users collection"""
        if request.method == 'OPTIONS':
            return '', 200
        
        try:
            data = request.json
            user_phone = data.get('user_phone')
            user_id = data.get('user_id')
            
            if not user_phone and not user_id:
                return jsonify({"error": "user_phone or user_id is required"}), 400
            
            query = {}
            if user_phone:
                query["user_phone"] = user_phone
            if user_id:
                query["user_id"] = int(user_id)
            
            # Delete all messages
            messages_result = messages.delete_many(query)
            
            # Delete user from users collection
            users_result = users.delete_one(query)
            
            return jsonify({
                "success": True,
                "messages_deleted": messages_result.deleted_count,
                "user_deleted": users_result.deleted_count > 0,
                "message": f"User deleted completely with {messages_result.deleted_count} messages"
            }), 200
            
        except Exception as e:
            print(f"Error deleting user completely: {e}")
            return jsonify({"error": str(e)}), 500

    @app.route('/delete-users-by-whatsapp-number', methods=['DELETE', 'OPTIONS'])
    def delete_users_by_whatsapp_number():
        """Delete all users who chatted with a specific WhatsApp business number"""
        if request.method == 'OPTIONS':
            return '', 200
        
        try:
            data = request.json
            display_phone_number = data.get('display_phone_number')
            
            if not display_phone_number:
                return jsonify({"error": "display_phone_number is required"}), 400
            
            # Get all users for this WhatsApp number
            user_phones = messages.distinct("user_phone", {"display_phone_number": display_phone_number})
            
            # Delete all messages for these users
            messages_result = messages.delete_many({"display_phone_number": display_phone_number})
            
            # Delete users from users collection
            users_result = users.delete_many({"user_phone": {"$in": user_phones}})
            
            return jsonify({
                "success": True,
                "messages_deleted": messages_result.deleted_count,
                "users_deleted": users_result.deleted_count,
                "message": f"Deleted {users_result.deleted_count} users with {messages_result.deleted_count} messages"
            }), 200
            
        except Exception as e:
            print(f"Error deleting users by WhatsApp number: {e}")
            return jsonify({"error": str(e)}), 500

    @app.route('/clear-all-chats-only', methods=['DELETE', 'OPTIONS'])
    def clear_all_chats_only():
        """Clear ALL messages BUT keep all users"""
        if request.method == 'OPTIONS':
            return '', 200
        
        try:
            data = request.json
            confirmation = data.get('confirmation', False)
            
            if not confirmation or confirmation != 'CLEAR_ALL':
                return jsonify({
                    "error": "Confirmation required. Set confirmation='CLEAR_ALL'"
                }), 400
            
            result = messages.delete_many({})
            
            # Reset all user message counts
            users.update_many({}, {"$set": {"total_messages": 0}})
            
            return jsonify({
                "success": True,
                "deleted_count": result.deleted_count,
                "users_kept": True,
                "message": f"Cleared ALL {result.deleted_count} messages. All users remain."
            }), 200
            
        except Exception as e:
            print(f"Error clearing all chats: {e}")
            return jsonify({"error": str(e)}), 500

    @app.route('/delete-all-users-completely', methods=['DELETE', 'OPTIONS'])
    def delete_all_users_completely():
        """Delete EVERYTHING: all messages AND all users"""
        if request.method == 'OPTIONS':
            return '', 200
        
        try:
            data = request.json
            confirmation = data.get('confirmation', False)
            
            if not confirmation or confirmation != 'DELETE_EVERYTHING':
                return jsonify({
                    "error": "Confirmation required. Set confirmation='DELETE_EVERYTHING'"
                }), 400
            
            messages_result = messages.delete_many({})
            users_result = users.delete_many({})
            
            return jsonify({
                "success": True,
                "messages_deleted": messages_result.deleted_count,
                "users_deleted": users_result.deleted_count,
                "message": f"Deleted EVERYTHING: {messages_result.deleted_count} messages and {users_result.deleted_count} users"
            }), 200
            
        except Exception as e:
            print(f"Error deleting everything: {e}")
            return jsonify({"error": str(e)}), 500

    @app.route('/get-user-message-count', methods=['GET', 'OPTIONS'])
    def get_user_message_count():
        """Get message count for each user"""
        if request.method == 'OPTIONS':
            return '', 200
        
        try:
            display_phone_number = request.args.get('display_phone_number')
            
            query = {}
            if display_phone_number:
                query["display_phone_number"] = display_phone_number
            
            # Get all users
            users_list = list(users.find({}, {"_id": 0}))
            
            # Get message count for each user
            user_counts = {}
            for user in users_list:
                user_query = {"user_phone": user["user_phone"]}
                if display_phone_number:
                    user_query["display_phone_number"] = display_phone_number
                
                count = messages.count_documents(user_query)
                user_counts[user["user_phone"]] = {
                    "user_id": user["user_id"],
                    "username": user.get("username"),
                    "message_count": count,
                    "last_seen": user.get("last_seen")
                }
            
            return jsonify({
                "success": True,
                "counts": user_counts
            }), 200
            
        except Exception as e:
            print(f"Error getting message counts: {e}")
            return jsonify({"error": str(e)}), 500