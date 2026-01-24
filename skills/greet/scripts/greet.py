#!/usr/bin/env python3
"""
Greet skill script
Provides a friendly greeting to the user with current date and time
"""
import json
import sys
from datetime import datetime

def greet(name=None):
    """Generate a greeting message with current date and time"""
    # Get current date and time
    now = datetime.now()
    current_time = now.strftime("%A, %B %d, %Y at %I:%M %p")
    
    if name:
        return f"Hello, {name}! It's wonderful to meet you. Today is {current_time}. How can I help you today?"
    else:
        return f"Hello! It's great to meet you. Today is {current_time}. How can I help you today?"

if __name__ == "__main__":
    # Read parameters from stdin if provided
    params = {}
    if len(sys.argv) > 1:
        try:
            params = json.loads(sys.argv[1])
        except json.JSONDecodeError:
            pass
    
    # Execute the greeting
    name = params.get("name")
    result = greet(name)
    
    # Output the result as JSON
    print(json.dumps({"result": result}))
