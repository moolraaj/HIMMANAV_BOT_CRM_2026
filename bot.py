# bot.py
import os
from dotenv import load_dotenv
from agent.agent_executor import AgentExecutor

load_dotenv()

# Initialize Agent once
agent_executor = AgentExecutor()

def process_message(user_input: str, phone: str, state: dict) -> dict:
    """
    Process message with Agent
    """
    if not user_input or not user_input.strip():
        return {"type": "text", "content": "Hello! Where would you like to travel?"}
    
    print(f"📨 Processing: {user_input}")
    
    # Call agent executive
    response = agent_executor.execute(phone, user_input)
    
    # Update local state from agent
    agent_state = agent_executor.get_state(phone)
    state["step"] = agent_state.get("step", "greeting")
    state["context"] = {
        "destination": agent_state.get("destination"),
        "start_date": agent_state.get("start_date"),
        "end_date": agent_state.get("end_date")
    }
    
    return response