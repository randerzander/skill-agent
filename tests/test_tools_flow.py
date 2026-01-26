#!/usr/bin/env python3
"""
Standalone test script showing the complete OpenAI tools flow:
1. Send initial prompt to LLM with tool definition
2. Parse LLM response for tool calls
3. Execute the tool function
4. Send tool result back to LLM
5. Get final natural language response
"""
import os
import json
import sys
import importlib.util
from pathlib import Path
from openai import OpenAI
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Initialize OpenAI client with OpenRouter
client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=os.getenv("OPENROUTER_API_KEY")
)

MODEL = "nvidia/nemotron-3-nano-30b-a3b:free"

# Define the greet tool in OpenAI format
GREET_TOOL = {
    "type": "function",
    "function": {
        "name": "greet",
        "description": "Greets a person with a friendly message including the current date and time",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "The name of the person to greet"
                }
            },
            "required": ["name"]
        }
    }
}


def execute_greet_tool(name: str) -> dict:
    """
    Execute the greet tool by importing and running the script.
    This shows how to dynamically load and execute skill scripts.
    """
    print(f"\n[TOOL EXECUTION] Calling greet tool with name='{name}'")
    
    # Dynamically import the greet script
    script_path = Path("skills/greet/scripts/greet.py")
    
    spec = importlib.util.spec_from_file_location("greet", script_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    
    # Call the execute function
    result = module.execute({"name": name})
    
    print(f"[TOOL RESULT] {result}")
    return result


def main():
    print("=" * 80)
    print("OpenAI Tools API Flow Test - Complete Walkthrough")
    print("=" * 80)
    
    # Step 1: Initial user prompt
    user_prompt = "Please greet Randy"
    print(f"\n[STEP 1] User Prompt:")
    print(f"  '{user_prompt}'")
    
    # Initialize conversation history
    messages = [
        {"role": "user", "content": user_prompt}
    ]
    
    # Step 2: Call LLM with tool definition
    print(f"\n[STEP 2] Calling LLM with tool definition")
    print(f"  Model: {MODEL}")
    print(f"  Available tools: {GREET_TOOL['function']['name']}")
    
    response = client.chat.completions.create(
        model=MODEL,
        messages=messages,
        tools=[GREET_TOOL]
    )
    
    message = response.choices[0].message
    
    # Check for reasoning traces
    if hasattr(response.choices[0], 'message') and hasattr(response.choices[0].message, 'reasoning'):
        print(f"\n[REASONING TRACE]:")
        print(f"  {response.choices[0].message.reasoning}")
    
    # Step 3: Parse LLM response
    print(f"\n[STEP 3] LLM Response Analysis:")
    print(f"  Content: {message.content}")
    print(f"  Tool calls: {len(message.tool_calls) if message.tool_calls else 0}")
    
    # Print raw response for debugging
    print(f"\n[DEBUG] Raw response object:")
    print(f"  {response}")
    
    if message.tool_calls:
        # Add assistant's message with tool calls to history
        messages.append({
            "role": "assistant",
            "content": message.content,
            "tool_calls": [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments
                    }
                } for tc in message.tool_calls
            ]
        })
        
        # Step 4: Process each tool call
        for tool_call in message.tool_calls:
            function_name = tool_call.function.name
            function_args = json.loads(tool_call.function.arguments)
            
            print(f"\n[STEP 4] Tool Call Details:")
            print(f"  Tool ID: {tool_call.id}")
            print(f"  Function: {function_name}")
            print(f"  Arguments: {json.dumps(function_args, indent=2)}")
            
            # Execute the tool
            if function_name == "greet":
                result = execute_greet_tool(function_args.get("name"))
            else:
                result = {"error": f"Unknown function: {function_name}"}
            
            # Step 5: Add tool result to conversation
            print(f"\n[STEP 5] Adding tool result to conversation")
            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": json.dumps(result)
            })
        
        # Step 6: Call LLM again with tool results
        print(f"\n[STEP 6] Calling LLM again with tool results")
        
        final_response = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            tools=[GREET_TOOL]
        )
        
        final_message = final_response.choices[0].message
        
        # Check for reasoning traces in final response
        if hasattr(final_response.choices[0], 'message') and hasattr(final_response.choices[0].message, 'reasoning'):
            print(f"\n[FINAL REASONING TRACE]:")
            print(f"  {final_response.choices[0].message.reasoning}")
        
        print(f"\n[STEP 7] Final LLM Response:")
        print(f"  {final_message.content}")
        
    else:
        print("\n[RESULT] LLM responded directly without using tools:")
        print(f"  {message.content}")
    
    print("\n" + "=" * 80)
    print("Complete conversation history:")
    print("=" * 80)
    for i, msg in enumerate(messages, 1):
        print(f"\nMessage {i} [{msg['role']}]:")
        if msg['role'] == 'tool':
            print(f"  Tool result: {msg['content'][:100]}...")
        else:
            print(f"  {json.dumps(msg, indent=2)}")
    
    print("\n" + "=" * 80)
    print("Test Complete!")
    print("=" * 80)


if __name__ == "__main__":
    main()
