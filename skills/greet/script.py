#!/usr/bin/env python3
"""
Greet skill script
Provides a friendly greeting to the user
"""
import json
import sys

def greet(name=None):
    """Generate a greeting message"""
    if name:
        return f"Hello, {name}! It's wonderful to meet you. How can I help you today?"
    else:
        return "Hello! It's great to meet you. How can I help you today?"

if __name__ == "__main__":
    # Read parameters from stdin if provided
    params = {}
    if len(sys.argv) > 1:
        try:
            params = json.loads(sys.argv[1])
        except:
            pass
    
    # Execute the greeting
    name = params.get("name")
    result = greet(name)
    
    # Output the result as JSON
    print(json.dumps({"result": result}))
