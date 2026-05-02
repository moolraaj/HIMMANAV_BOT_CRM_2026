# helpers/helper.py

import re
from datetime import datetime, timedelta

def format_buttons_grid(buttons, columns=2):
    """
    Format buttons in grid layout
    
    Args:
        buttons: List of button dictionaries [{"text": "Option", "value": "option"}]
        columns: Number of columns (default 2)
    
    Returns:
        List of buttons in grid order
    """
    if not buttons:
        return []
    
    # Just return the buttons - frontend will handle grid layout
    return buttons

def extract_number(text: str):
    """Extract number from text"""
    text = text.strip().lower()
    if text.startswith("5+"):
        return 5
    words = text.split()
    for word in words:
        if word.isdigit():
            return int(word)
    try:
        return int(text)
    except ValueError:
        return None

def parse_date(date_str: str):
    """Parse date string to datetime object"""
    try:
        return datetime.strptime(date_str, "%Y-%m-%d")
    except:
        return None

def calculate_nights(start_date: str, end_date: str) -> int:
    """Calculate number of nights between dates"""
    try:
        start = datetime.strptime(start_date, "%Y-%m-%d")
        end = datetime.strptime(end_date, "%Y-%m-%d")
        return max((end - start).days, 0)
    except:
        return 0

def clean_llm_response(response: str) -> str:
    """Clean LLM response by removing markdown code blocks"""
    response = response.strip()
    if response.startswith('```json'):
        response = response.replace('```json', '').replace('```', '').strip()
    elif response.startswith('```'):
        response = response.replace('```', '').strip()
    return response