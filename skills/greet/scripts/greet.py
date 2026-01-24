#!/usr/bin/env python3
"""Simple greet script for testing"""
from datetime import datetime


def execute(params):
    """Execute the greet skill"""
    name = params.get("name", "friend")
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    greeting = f"Hello, {name}! Welcome to the Agent Skills Framework. The current time is {current_time}."
    
    return {"result": greeting}
