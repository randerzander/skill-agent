#!/usr/bin/env python3
"""
Diagnostic script to check web UI functionality
"""
import sys
import os

print("=" * 70)
print("Agent Skills Framework - Diagnostic Check")
print("=" * 70)

# Check 1: Python version
print(f"\n1. Python version: {sys.version}")

# Check 2: Required modules
print("\n2. Checking required modules:")
required = ['flask', 'dotenv', 'openai', 'yaml', 'requests', 'rich']
for module in required:
    try:
        __import__(module if module != 'yaml' else 'pyyaml')
        print(f"   ✓ {module}")
    except ImportError:
        print(f"   ✗ {module} - MISSING")

# Check 3: Environment variables
print("\n3. Checking environment:")
api_key = os.getenv('OPENROUTER_API_KEY')
if api_key:
    print(f"   ✓ OPENROUTER_API_KEY: {api_key[:10]}...{api_key[-4:]}")
else:
    print(f"   ✗ OPENROUTER_API_KEY: NOT SET")

# Check 4: File structure
print("\n4. Checking file structure:")
files_to_check = [
    'agent.py',
    'app.py',
    'config.yaml',
    'templates/index.html',
    'skills/planning/SKILL.md',
    'skills/web/SKILL.md',
    'skills/finalize/SKILL.md',
]

for file_path in files_to_check:
    exists = os.path.exists(file_path)
    symbol = "✓" if exists else "✗"
    print(f"   {symbol} {file_path}")

# Check 5: Try importing agent
print("\n5. Testing agent import:")
try:
    from agent import AgentSkillsFramework
    print("   ✓ Agent module imported")
    
    # Try creating agent
    if api_key:
        try:
            agent = AgentSkillsFramework()
            print(f"   ✓ Agent created ({len(agent.skill_loader.skills)} skills loaded)")
        except Exception as e:
            print(f"   ✗ Agent creation failed: {e}")
    else:
        print("   ⚠ Skipping agent creation (no API key)")
        
except ImportError as e:
    print(f"   ✗ Failed to import agent: {e}")

print("\n" + "=" * 70)
print("Diagnostic complete!")
print("=" * 70)
