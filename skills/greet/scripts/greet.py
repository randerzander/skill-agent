#!/usr/bin/env python3
"""
Greet skill script
Provides a friendly greeting to the user with current date and time
"""
from datetime import datetime

def execute(params):
    """
    Execute the greet skill
    
    Args:
        params: Dictionary of parameters (e.g., {"name": "Alice"})
    
    Returns:
        Dictionary with result
    """
    name = params.get("name")
    
    # Get current date and time in UTC
    now = datetime.utcnow()
    current_time = now.strftime("%A, %B %d, %Y at %I:%M %p UTC")
    
    if name:
        greeting = f"Hello, {name}! It's wonderful to meet you. Today is {current_time}. How can I help you today?"
    else:
        greeting = f"Hello! It's great to meet you. Today is {current_time}. How can I help you today?"
    
    return {"result": greeting}
