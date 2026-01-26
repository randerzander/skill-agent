#!/usr/bin/env python3
"""Debug script to show what messages are being sent to OpenAI"""
import json
import sys

# Read the last conversation log
import os
from pathlib import Path

logs_dir = Path("logs")
log_files = sorted(logs_dir.glob("conversation_*.jsonl"))

if not log_files:
    print("No conversation logs found")
    sys.exit(1)

latest_log = log_files[-1]
print(f"Reading: {latest_log}")
print("=" * 80)

with open(latest_log, 'r') as f:
    for line in f:
        try:
            entry = json.loads(line)
            if entry.get('type') == 'llm_response':
                iteration = entry.get('iteration', '?')
                tokens = entry.get('tokens', {})
                
                print(f"\nIteration {iteration}:")
                if tokens:
                    print(f"  Tokens: {tokens['prompt_tokens']} in, {tokens['completion_tokens']} out, {tokens['total_tokens']} total")
                
                # Check for thinking field (shouldn't exist)
                if 'thinking' in entry:
                    print(f"  ⚠️  WARNING: 'thinking' field found in log entry!")
                
                # Check for reasoning traces
                if entry.get('reasoning'):
                    print(f"  💭 Reasoning trace present: {len(entry['reasoning'])} chars")
                    
        except json.JSONDecodeError:
            continue

print("\n" + "=" * 80)
print("\nTo see actual messages sent to OpenAI, check self.messages in debugger")
print("Reasoning traces should ONLY be in reasoning_traces dict, NOT in messages")
