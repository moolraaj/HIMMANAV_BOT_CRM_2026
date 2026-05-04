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
        # Save hotel context
        state["data"] = copy.deepcopy(_agent.sessions[phone].get("context", {}))

    # Save package context if PackageAgent has a session for this phone
    pkg_agent = getattr(_agent, "package_agent", None)
    if pkg_agent and phone in pkg_agent.sessions:
        state["package_data"] = copy.deepcopy(pkg_agent.sessions[phone].get("context", {}))

    return response


def reset_session(phone: str):
    _agent.reset_session(phone)

    # Also reset package session
    pkg_agent = getattr(_agent, "package_agent", None)
    if pkg_agent:
        pkg_agent.reset_session(phone)