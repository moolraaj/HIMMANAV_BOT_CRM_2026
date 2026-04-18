# app.py
from flask import Flask, request, jsonify, render_template, session
from bot import process_message
import os
from dotenv import load_dotenv
load_dotenv('.env')
SECRET_KEY =os.getenv('SECRET_KEY')
OWNER_PHONE=os.getenv('OWNER_PHONE')
DEBUG_MODE=os.getenv('DEBUG_MODE')
import uuid

app = Flask(__name__)
app.secret_key = SECRET_KEY

 
conversation_states = {}

@app.route("/")
def home():
    if "session_id" not in session:
        session["session_id"] = str(uuid.uuid4())
        conversation_states[session["session_id"]] = {
            "step": "greeting",
            "context": {},
            "packages": []
        }
    return render_template("index.html")

@app.route("/chat", methods=["POST"])
def chat():
    try:
        data = request.get_json()
        user_message = data.get("message", "").strip()
        session_id = session.get("session_id", "default")
        
       
        if session_id not in conversation_states:
            conversation_states[session_id] = {
                "step": "greeting",
                "context": {},
                "packages": []
            }
        
        state = conversation_states[session_id]
        
        print("\n" + "="*50)
        print(f"💬 Session: {session_id}")
        print(f"👤 User: {user_message}")
        print(f"📍 Step: {state.get('step')}")
        
       
        response = process_message(user_message, OWNER_PHONE, state)
        
         
        if response.get("new_state"):
            conversation_states[session_id].update(response["new_state"])
        
        print(f"🤖 Bot: {response.get('content', '')[:100]}")
        print("="*50 + "\n")
        
        return jsonify({
            "success": True,
            "type": response.get("type", "text"),
            "content": response.get("content", ""),
            "buttons": response.get("buttons", [])
        })
        
    except Exception as e:
        print(f"❌ Chat Error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            "success": False,
            "type": "text",
            "content": "⚠️ Sorry, something went wrong. Please try again."
        }), 500

@app.route("/clear", methods=["POST"])
def clear_history():
    session_id = session.get("session_id", "default")
    if session_id in conversation_states:
        conversation_states[session_id] = {
            "step": "greeting",
            "context": {},
            "packages": []
        }
    return jsonify({"success": True})

if __name__ == "__main__":
    print("🚀 Travel Bot Starting...")

    port = int(os.environ.get("PORT", 5000))  
    debug = str(DEBUG_MODE).lower() == "true"

    app.run(host="0.0.0.0", port=port, debug=debug)



 
 