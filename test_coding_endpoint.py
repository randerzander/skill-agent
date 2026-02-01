#!/usr/bin/env python3
"""
Test script for the coding model endpoint
"""
import os
import sys
from pathlib import Path
from openai import OpenAI
from dotenv import load_dotenv

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))
from utils import load_config

load_dotenv()

def test_coding_endpoint():
    """Test if the coding model endpoint is accessible"""
    
    print("=" * 60)
    print("Testing Coding Model Endpoint")
    print("=" * 60)
    
    # Load config
    config = load_config()
    api_key = os.getenv(config.get('openai', {}).get('api_key_env', 'OPENROUTER_API_KEY'))
    
    if not api_key:
        print("❌ Error: API key not found")
        return False
    
    print(f"✓ API key found (length: {len(api_key)})")
    
    # Get coding model from config
    coding_model = config.get('coding', {}).get('model', 'qwen/qwen3-coder:free')
    print(f"✓ Coding model: {coding_model}")
    
    # Create client
    client = OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=api_key
    )
    print(f"✓ OpenAI client created")
    
    # Test prompt
    prompt = """Write a simple Python function that adds two numbers.
    
Requirements:
- Function name: add_numbers
- Takes two parameters: a, b
- Returns their sum

Output only the Python code, no explanations."""
    
    print("\n" + "=" * 60)
    print("Sending test request to coding model...")
    print("=" * 60)
    
    try:
        response = client.chat.completions.create(
            model=coding_model,
            messages=[
                {"role": "user", "content": prompt}
            ],
            temperature=0.2
        )
        
        code = response.choices[0].message.content
        
        # Get token usage
        if hasattr(response, 'usage') and response.usage:
            print(f"\n✓ Success!")
            print(f"  Prompt tokens: {response.usage.prompt_tokens}")
            print(f"  Completion tokens: {response.usage.completion_tokens}")
            print(f"  Total tokens: {response.usage.total_tokens}")
        else:
            print(f"\n✓ Success! (no usage data)")
        
        print(f"\nGenerated code:")
        print("-" * 60)
        print(code)
        print("-" * 60)
        
        return True
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        error_str = str(e)
        
        # Parse specific errors
        if '402' in error_str:
            print("\n💡 Error 402: Payment Required / Spending Limit Exceeded")
            print("   Your API key has hit its spending limit.")
            print("   Solutions:")
            print("   1. Wait for the limit to reset (usually daily/monthly)")
            print("   2. Use a different API key")
            print("   3. Switch to a different model in config.yaml")
        elif '429' in error_str:
            print("\n💡 Error 429: Rate Limit Exceeded")
            print("   Too many requests. Wait a moment and try again.")
        elif '401' in error_str:
            print("\n💡 Error 401: Unauthorized")
            print("   Invalid API key. Check your OPENROUTER_API_KEY in .env")
        
        return False

if __name__ == "__main__":
    success = test_coding_endpoint()
    sys.exit(0 if success else 1)
