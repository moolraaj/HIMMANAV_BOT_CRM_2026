"""
bot.py

Thin entry point. All logic lives in agent/agent_executor.py.
"""

import os
from dotenv import load_dotenv
from agent.agent_executor import AgentExecutor

load_dotenv()

# Single shared instance
_agent = AgentExecutor()

def process_message(user_input: str, phone: str, state: dict) -> dict:
    """
    Called by chats/message_handler.py for every incoming message.
    
    Args:
        user_input: Raw text from the user
        phone: User's phone number (used as session key)
        state: Shared state dict from message_handler (kept in sync below)
    
    Returns:
        Response dict with keys: type, content, and optionally buttons
    """
    if not user_input or not user_input.strip():
        return {"type": "text", "content": "Hello! Where would you like to travel? 🌍"}
    
    # Delegate to the agent
    response = _agent.execute(phone, user_input)
    
    # Sync agent state back into the caller's state dict
    agent_state = _agent.get_state(phone)
    state["step"] = agent_state.get("step", "start")
    state["data"] = agent_state.get("data", {})
    
    return response