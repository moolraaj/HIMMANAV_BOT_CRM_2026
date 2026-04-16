# chats/delete_routes.py
from flask import request, jsonify
from bson.objectid import ObjectId
from database.database import messages, mapping

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
            
            if not user_phone:
                return jsonify({"error": "user_phone is required"}), 400
            
            if not user_id:
                return jsonify({"error": "user_id is required"}), 400
            
            # Delete ONLY messages, not the user mapping
            query = {
                "user_phone": user_phone,
                "user_id": int(user_id)
            }
            
            result = messages.delete_many(query)
            
            return jsonify({
                "success": True,
                "deleted_count": result.deleted_count,
                "user_kept": True,
                "message": f"Cleared {result.deleted_count} messages for user {user_phone}. User remains in system."
            }), 200
            
        except Exception as e:
            print(f"Error clearing user chats: {e}")
            return jsonify({"error": str(e)}), 500

    @app.route('/delete-user-completely', methods=['DELETE', 'OPTIONS'])
    def delete_user_completely():
        """Delete user completely: ALL messages AND remove from mapping"""
        if request.method == 'OPTIONS':
            return '', 200
        
        try:
            data = request.json
            user_phone = data.get('user_phone')
            user_id = data.get('user_id')
            
            if not user_phone:
                return jsonify({"error": "user_phone is required"}), 400
            
            if not user_id:
                return jsonify({"error": "user_id is required"}), 400
            
            # Delete all messages for this user
            messages_result = messages.delete_many({
                "user_phone": user_phone,
                "user_id": int(user_id)
            })
            
            # Delete user from mapping
            mapping_result = mapping.delete_one({
                "user_phone": user_phone,
                "partner_id": int(user_id)
            })
            
            return jsonify({
                "success": True,
                "messages_deleted": messages_result.deleted_count,
                "mapping_deleted": mapping_result.deleted_count,
                "user_deleted": True,
                "message": f"User {user_phone} completely deleted with {messages_result.deleted_count} messages"
            }), 200
            
        except Exception as e:
            print(f"Error deleting user completely: {e}")
            return jsonify({"error": str(e)}), 500

    @app.route('/delete-multiple-users-completely', methods=['DELETE', 'OPTIONS'])
    def delete_multiple_users_completely():
        """Delete multiple users completely: messages + mapping"""
        if request.method == 'OPTIONS':
            return '', 200
        
        try:
            data = request.json
            user_phones = data.get('user_phones', [])
            user_id = data.get('user_id')
            
            if not user_phones or len(user_phones) == 0:
                return jsonify({"error": "user_phones array is required"}), 400
            
            if not user_id:
                return jsonify({"error": "user_id is required"}), 400
            
            # Delete all messages for these users
            messages_result = messages.delete_many({
                "user_phone": {"$in": user_phones},
                "user_id": int(user_id)
            })
            
            # Delete users from mapping
            mapping_result = mapping.delete_many({
                "user_phone": {"$in": user_phones},
                "partner_id": int(user_id)
            })
            
            return jsonify({
                "success": True,
                "messages_deleted": messages_result.deleted_count,
                "mapping_deleted": mapping_result.deleted_count,
                "users_deleted": len(user_phones),
                "message": f"Deleted {len(user_phones)} users completely with {messages_result.deleted_count} messages"
            }), 200
            
        except Exception as e:
            print(f"Error deleting multiple users: {e}")
            return jsonify({"error": str(e)}), 500

    @app.route('/clear-all-chats-only', methods=['DELETE', 'OPTIONS'])
    def clear_all_chats_only():
        """Clear ALL messages for partner BUT keep all users"""
        if request.method == 'OPTIONS':
            return '', 200
        
        try:
            data = request.json
            user_id = data.get('user_id')
            confirmation = data.get('confirmation', False)
            
            if not user_id:
                return jsonify({"error": "user_id is required"}), 400
            
            if not confirmation or confirmation != 'CLEAR_ALL':
                return jsonify({
                    "error": "Confirmation required. Set confirmation='CLEAR_ALL'"
                }), 400
            
            # Delete ONLY messages, keep users in mapping
            result = messages.delete_many({"user_id": int(user_id)})
            
            return jsonify({
                "success": True,
                "deleted_count": result.deleted_count,
                "users_kept": True,
                "message": f"Cleared ALL {result.deleted_count} messages. All users remain in system."
            }), 200
            
        except Exception as e:
            print(f"Error clearing all chats: {e}")
            return jsonify({"error": str(e)}), 500

    @app.route('/delete-all-users-completely', methods=['DELETE', 'OPTIONS'])
    def delete_all_users_completely():
        """Delete EVERYTHING: all messages AND all users from mapping"""
        if request.method == 'OPTIONS':
            return '', 200
        
        try:
            data = request.json
            user_id = data.get('user_id')
            confirmation = data.get('confirmation', False)
            
            if not user_id:
                return jsonify({"error": "user_id is required"}), 400
            
            if not confirmation or confirmation != 'DELETE_EVERYTHING':
                return jsonify({
                    "error": "Confirmation required. Set confirmation='DELETE_EVERYTHING'"
                }), 400
            
            # Delete all messages for this partner
            messages_result = messages.delete_many({"user_id": int(user_id)})
            
            # Delete all user mappings for this partner
            mapping_result = mapping.delete_many({"partner_id": int(user_id)})
            
            return jsonify({
                "success": True,
                "messages_deleted": messages_result.deleted_count,
                "mapping_deleted": mapping_result.deleted_count,
                "message": f"Deleted EVERYTHING: {messages_result.deleted_count} messages and {mapping_result.deleted_count} users"
            }), 200
            
        except Exception as e:
            print(f"Error deleting everything: {e}")
            return jsonify({"error": str(e)}), 500

    @app.route('/get-user-message-count', methods=['GET', 'OPTIONS'])
    def get_user_message_count():
        """Get unread message count for each user"""
        if request.method == 'OPTIONS':
            return '', 200
        
        try:
            user_id = request.args.get('user_id')
            
            if not user_id:
                return jsonify({"error": "user_id is required"}), 400
            
            user_id = int(user_id)
            
            # Get all users
            users = messages.distinct("user_phone", {"user_id": user_id})
            
            # Get message count for each user
            user_counts = {}
            for user in users:
                # Count messages from user (unread = messages from user that are not replied?)
                count = messages.count_documents({
                    "user_id": user_id,
                    "user_phone": user,
                    "from": "user"
                })
                user_counts[user] = count
            
            return jsonify({
                "success": True,
                "counts": user_counts
            }), 200
            
        except Exception as e:
            print(f"Error getting message counts: {e}")
            return jsonify({"error": str(e)}), 500