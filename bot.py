
# bot.py
import os
import copy
from dotenv import load_dotenv
from agent.ai_agent import AIHotelAgent

load_dotenv()

_agent = AIHotelAgent()

def process_message(user_input: str, phone: str, state: dict) -> dict:
    if not user_input or not user_input.strip():
        return {"type": "text", "content": "Hi! Are you looking for hotels or travel packages?"}
    
    response = _agent.execute(phone, user_input, state)
    
    if phone in _agent.sessions:
        # Deep copy so the persisted state is fully serializable
        # and not affected by future in-memory mutations
        state["data"] = copy.deepcopy(_agent.sessions[phone].get("context", {}))
    
    return response

def reset_session(phone: str):
    _agent.reset_session(phone)