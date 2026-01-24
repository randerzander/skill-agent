#!/usr/bin/env python3
"""
Example usage of the Agent Skills Framework
Demonstrates how the framework works without requiring an API key
"""
import json
from agent import SkillLoader

def simulate_agent_workflow():
    """Simulate the agent's decision-making and skill execution workflow"""
    print("=" * 70)
    print("Agent Skills Framework - Example Simulation")
    print("=" * 70)
    
    # Step 1: Initialize skill loader
    print("\n[Step 1] Loading available skills...")
    loader = SkillLoader()
    skills = loader.get_skills_metadata()
    print(f"Available skills: {json.dumps(skills, indent=2)}")
    
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
    
    # Step 4: Load skill metadata into context
    print("\n" + "=" * 70)
    print("[Step 4] Loading skill metadata into context")
    skill_metadata = loader.skills.get('greet')
    print(f"Skill metadata: {json.dumps(skill_metadata, indent=2)}")
    
    # Step 5: Execute the skill
    print("\n" + "=" * 70)
    print("[Step 5] Executing skill...")
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
    demonstrate_different_scenarios()
    
    print("\n\n" + "=" * 70)
    print("To run the full agent with LLM integration:")
    print("  1. Set up your .env file with OPENROUTER_API_KEY")
    print("  2. Run: python agent.py")
    print("=" * 70)
