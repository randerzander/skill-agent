#!/usr/bin/env python3
"""
Agent Skills Framework
A framework for AI agents to discover and execute skills based on user requests.
"""
import os
import json
import subprocess
from pathlib import Path
from typing import List, Dict, Any, Optional
from openai import OpenAI
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

class SkillLoader:
    """Loads and manages agent skills"""
    
    def __init__(self, skills_dir: str = "skills"):
        self.skills_dir = Path(skills_dir)
        self.skills = {}
        self.load_skills()
    
    def load_skills(self):
        """Load all skills from the skills directory"""
        if not self.skills_dir.exists():
            print(f"Skills directory {self.skills_dir} does not exist")
            return
        
        for skill_path in self.skills_dir.iterdir():
            if skill_path.is_dir():
                metadata_file = skill_path / "metadata.json"
                if metadata_file.exists():
                    try:
                        with open(metadata_file, 'r') as f:
                            metadata = json.load(f)
                            skill_name = metadata.get('name', skill_path.name)
                            metadata['path'] = str(skill_path)
                            self.skills[skill_name] = metadata
                            print(f"Loaded skill: {skill_name}")
                    except Exception as e:
                        print(f"Error loading skill {skill_path.name}: {e}")
    
    def get_skills_metadata(self) -> List[Dict[str, Any]]:
        """Get metadata for all available skills"""
        return [
            {
                "name": skill["name"],
                "description": skill["description"],
                "parameters": skill.get("parameters", {})
            }
            for skill in self.skills.values()
        ]
    
    def execute_skill(self, skill_name: str, parameters: Dict[str, Any] = None) -> Dict[str, Any]:
        """Execute a skill with given parameters"""
        if skill_name not in self.skills:
            return {"error": f"Skill '{skill_name}' not found"}
        
        skill = self.skills[skill_name]
        script_path = Path(skill['path']) / skill.get('script', 'script.py')
        
        if not script_path.exists():
            return {"error": f"Script not found for skill '{skill_name}'"}
        
        try:
            # Execute the skill script with parameters
            params_json = json.dumps(parameters or {})
            result = subprocess.run(
                ['python3', str(script_path), params_json],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode != 0:
                return {"error": f"Script execution failed: {result.stderr}"}
            
            # Parse the output
            try:
                return json.loads(result.stdout)
            except json.JSONDecodeError:
                return {"result": result.stdout.strip()}
        
        except subprocess.TimeoutExpired:
            return {"error": "Script execution timed out"}
        except Exception as e:
            return {"error": f"Execution error: {str(e)}"}


class AgentSkillsFramework:
    """Main framework for agent skills execution"""
    
    def __init__(self, api_key: str = None):
        self.api_key = api_key or os.getenv("OPENROUTER_API_KEY")
        if not self.api_key:
            raise ValueError("OpenRouter API key not found. Set OPENROUTER_API_KEY environment variable.")
        
        # Initialize OpenAI client with OpenRouter configuration
        self.client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=self.api_key
        )
        
        # Model configuration
        self.model = "nvidia/llama-3.1-nemotron-70b-instruct:free"
        
        # Initialize skill loader
        self.skill_loader = SkillLoader()
        
        # Conversation history
        self.messages = []
    
    def run(self, user_input: str, max_iterations: int = 5) -> str:
        """
        Main agent loop that processes user input through skill selection and execution
        
        Args:
            user_input: The user's request
            max_iterations: Maximum number of iterations to prevent infinite loops
        
        Returns:
            The final response from the agent
        """
        # Add user message to history
        self.messages.append({"role": "user", "content": user_input})
        
        iteration = 0
        while iteration < max_iterations:
            iteration += 1
            
            # Step 1: Get available skills and ask LLM to select one
            response = self._get_skill_selection()
            
            if not response:
                break
            
            # Step 2: Check if LLM wants to execute a skill
            skill_to_execute = self._parse_skill_selection(response)
            
            if not skill_to_execute:
                # LLM decided not to execute any skill, return the response
                return response
            
            # Step 3: Load skill metadata into context and ask if LLM wants to execute
            execution_decision = self._get_execution_decision(skill_to_execute)
            
            if not execution_decision.get("execute", False):
                # LLM decided not to execute, return the response
                return execution_decision.get("response", response)
            
            # Step 4: Execute the skill
            result = self.skill_loader.execute_skill(
                skill_to_execute["name"],
                skill_to_execute.get("parameters", {})
            )
            
            # Step 5: Pass result back to LLM
            result_message = f"Skill '{skill_to_execute['name']}' executed. Result: {json.dumps(result)}"
            self.messages.append({"role": "assistant", "content": result_message})
            
            # Get final response from LLM based on execution result
            final_response = self._get_final_response()
            
            return final_response
        
        return "Maximum iterations reached. Unable to complete the request."
    
    def _get_skill_selection(self) -> str:
        """Ask LLM to select a skill to use"""
        skills_metadata = self.skill_loader.get_skills_metadata()
        
        system_message = f"""You are a helpful AI assistant with access to skills. 
Available skills: {json.dumps(skills_metadata, indent=2)}

When a user asks you to do something, you can:
1. Select a skill to use by responding with: SKILL:<skill_name>:<parameters_json>
2. Or respond directly if no skill is needed

For example:
- To use the greet skill with a name: SKILL:greet:{{"name":"Alice"}}
- To use the greet skill without a name: SKILL:greet:{{}}
- To respond directly: Just provide your response
"""
        
        messages = [{"role": "system", "content": system_message}] + self.messages
        
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages
            )
            return response.choices[0].message.content
        except Exception as e:
            print(f"Error calling LLM: {e}")
            return None
    
    def _parse_skill_selection(self, response: str) -> Optional[Dict[str, Any]]:
        """Parse LLM response to extract skill selection"""
        if not response or not response.startswith("SKILL:"):
            return None
        
        try:
            # Format: SKILL:<skill_name>:<parameters_json>
            parts = response[6:].split(":", 1)
            skill_name = parts[0].strip()
            parameters = {}
            
            if len(parts) > 1 and parts[1].strip():
                parameters = json.loads(parts[1].strip())
            
            return {
                "name": skill_name,
                "parameters": parameters
            }
        except Exception as e:
            print(f"Error parsing skill selection: {e}")
            return None
    
    def _get_execution_decision(self, skill_info: Dict[str, Any]) -> Dict[str, Any]:
        """Ask LLM if it wants to execute the skill"""
        skill_name = skill_info["name"]
        
        if skill_name not in self.skill_loader.skills:
            return {"execute": False, "response": f"Skill '{skill_name}' not found"}
        
        skill_metadata = self.skill_loader.skills[skill_name]
        
        decision_prompt = f"""You selected the skill '{skill_name}'. 
Skill metadata: {json.dumps(skill_metadata, indent=2)}
Parameters you want to use: {json.dumps(skill_info.get('parameters', {}))}

Do you want to execute this skill? Respond with YES to execute or NO to cancel."""
        
        self.messages.append({"role": "assistant", "content": decision_prompt})
        
        # For this implementation, we'll automatically execute if skill was selected
        # In a more complex system, this could involve another LLM call
        return {"execute": True}
    
    def _get_final_response(self) -> str:
        """Get final response from LLM after skill execution"""
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=self.messages + [
                    {"role": "user", "content": "Based on the skill execution result above, provide a natural response to the user."}
                ]
            )
            return response.choices[0].message.content
        except Exception as e:
            print(f"Error getting final response: {e}")
            return "I encountered an error processing the result."


def main():
    """Main entry point"""
    print("Agent Skills Framework")
    print("=" * 50)
    
    # Initialize the framework
    try:
        agent = AgentSkillsFramework()
    except ValueError as e:
        print(f"Error: {e}")
        print("Please set your OPENROUTER_API_KEY in a .env file")
        return
    
    print(f"Loaded {len(agent.skill_loader.skills)} skill(s)")
    print("=" * 50)
    
    # Interactive loop
    while True:
        try:
            user_input = input("\nYou: ").strip()
            if not user_input:
                continue
            
            if user_input.lower() in ['exit', 'quit', 'q']:
                print("Goodbye!")
                break
            
            response = agent.run(user_input)
            print(f"\nAgent: {response}")
            
        except KeyboardInterrupt:
            print("\n\nGoodbye!")
            break
        except Exception as e:
            print(f"Error: {e}")


if __name__ == "__main__":
    main()
