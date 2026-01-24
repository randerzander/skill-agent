#!/usr/bin/env python3
"""
Example usage of the Agent Skills Framework
Demonstrates how the framework works without requiring an API key
Follows the Agent Skills specification from agentskills.io
"""
import json
from agent import SkillLoader

def simulate_agent_workflow():
    """Simulate the agent's decision-making and skill execution workflow"""
    print("=" * 70)
    print("Agent Skills Framework - Example Simulation")
    print("Following the Agent Skills specification from agentskills.io")
    print("=" * 70)
    
    # Step 1: Initialize skill loader (progressive disclosure)
    print("\n[Step 1] Loading available skills (metadata only)...")
    loader = SkillLoader()
    
    # Show metadata only (name and description)
    skills = loader.get_skills_metadata()
    print(f"Available skills (metadata only): {json.dumps(skills, indent=2)}")
    
    # Show XML format (Claude-compatible)
    print(f"\nSkills in XML format:\n{loader.get_skills_xml()}")
    
    # Step 2: Simulate user input
    print("\n" + "=" * 70)
    print("[Step 2] User Input")
    user_input = "Please greet me, my name is Alice"
    print(f'User: "{user_input}"')
    
    # Step 3: Simulate LLM skill selection
    print("\n" + "=" * 70)
    print("[Step 3] LLM analyzes user input and selects appropriate skill")
    print("LLM thinking: The user wants a greeting with their name...")
    selected_skill = {
        "name": "greet",
        "parameters": {"name": "Alice"}
    }
    print(f"LLM decision: SKILL:greet:{json.dumps(selected_skill['parameters'])}")
    
    # Step 4: Activate skill (load full SKILL.md content)
    print("\n" + "=" * 70)
    print("[Step 4] Activating skill (progressive disclosure)")
    print("Loading full SKILL.md content into context...")
    skill_content = loader.activate_skill(selected_skill['name'])
    print(f"Full SKILL.md content loaded ({len(skill_content)} characters)")
    print(f"\nFirst 300 characters of SKILL.md:\n{skill_content[:300]}...")
    
    # Step 5: Execute the skill
    print("\n" + "=" * 70)
    print("[Step 5] Executing skill script...")
    result = loader.execute_skill(
        selected_skill['name'],
        selected_skill['parameters']
    )
    print(f"Execution result: {json.dumps(result, indent=2)}")
    
    # Step 6: LLM generates final response
    print("\n" + "=" * 70)
    print("[Step 6] LLM generates natural response based on result")
    final_response = result['result']
    print(f'Agent: "{final_response}"')
    
    print("\n" + "=" * 70)
    print("Workflow complete!")
    print("=" * 70)

def demonstrate_progressive_disclosure():
    """Demonstrate the progressive disclosure pattern"""
    print("\n\n" + "=" * 70)
    print("Progressive Disclosure Pattern")
    print("=" * 70)
    
    loader = SkillLoader()
    
    print("\n1. At startup, only name and description are loaded:")
    skill = loader.skills['greet']
    print(f"   Name: {skill['name']}")
    print(f"   Description: {skill['description']}")
    print(f"   Content loaded: {skill['content_loaded']}")
    print(f"   Tokens used: ~50-100 (minimal context usage)")
    
    print("\n2. When skill is activated, full SKILL.md is loaded:")
    content = loader.activate_skill('greet')
    print(f"   Content loaded: {skill['content_loaded']}")
    print(f"   Full content size: {len(content)} characters")
    print(f"   Tokens used: ~{len(content) // 4} (approximate)")
    
    print("\n3. This keeps agents fast while providing context on demand!")

def demonstrate_different_scenarios():
    """Demonstrate different usage scenarios"""
    print("\n\n" + "=" * 70)
    print("Additional Scenarios")
    print("=" * 70)
    
    loader = SkillLoader()
    
    scenarios = [
        {
            "description": "Greet without a name",
            "skill": "greet",
            "params": {}
        },
        {
            "description": "Greet with name 'Bob'",
            "skill": "greet",
            "params": {"name": "Bob"}
        },
        {
            "description": "Greet with name 'Charlie'",
            "skill": "greet",
            "params": {"name": "Charlie"}
        }
    ]
    
    for i, scenario in enumerate(scenarios, 1):
        print(f"\nScenario {i}: {scenario['description']}")
        print(f"Parameters: {json.dumps(scenario['params'])}")
        result = loader.execute_skill(scenario['skill'], scenario['params'])
        print(f"Result: {result['result']}")

if __name__ == "__main__":
    simulate_agent_workflow()
    demonstrate_progressive_disclosure()
    demonstrate_different_scenarios()
    
    print("\n\n" + "=" * 70)
    print("To run the full agent with LLM integration:")
    print("  1. Set up your .env file with OPENROUTER_API_KEY")
    print("  2. Run: python agent.py")
    print("\nLearn more about Agent Skills:")
    print("  https://agentskills.io")
    print("=" * 70)
