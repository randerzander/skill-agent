#!/usr/bin/env python3
"""
Agent Skills Framework
A framework for AI agents to discover and execute skills based on user requests.
Implements the Agent Skills specification from agentskills.io
"""
import os
import sys
import json
import subprocess
import re
from pathlib import Path
from typing import List, Dict, Any, Optional
from openai import OpenAI
from dotenv import load_dotenv
import yaml

# Load environment variables
load_dotenv()

class SkillLoader:
    """Loads and manages agent skills following the Agent Skills specification"""
    
    def __init__(self, skills_dir: str = "skills"):
        self.skills_dir = Path(skills_dir)
        self.skills = {}
        self.load_skills()
    
    def parse_skill_md(self, skill_md_path: Path) -> Dict[str, Any]:
        """Parse a SKILL.md file to extract frontmatter and content"""
        with open(skill_md_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Extract YAML frontmatter
        frontmatter_match = re.match(r'^---\s*\n(.*?)\n---\s*\n(.*)', content, re.DOTALL)
        if not frontmatter_match:
            raise ValueError(f"No valid YAML frontmatter found in {skill_md_path}")
        
        frontmatter_text = frontmatter_match.group(1)
        markdown_content = frontmatter_match.group(2)
        
        # Parse YAML frontmatter
        metadata = yaml.safe_load(frontmatter_text)
        
        if 'name' not in metadata or 'description' not in metadata:
            raise ValueError(f"SKILL.md must have 'name' and 'description' in frontmatter")
        
        return {
            'name': metadata['name'],
            'description': metadata['description'],
            'frontmatter': metadata,
            'content': markdown_content.strip(),
            'full_content': content
        }
    
    def load_skills(self):
        """Load all skills from the skills directory (progressive disclosure - metadata only)"""
        if not self.skills_dir.exists():
            print(f"Skills directory {self.skills_dir} does not exist")
            return
        
        for skill_path in self.skills_dir.iterdir():
            if skill_path.is_dir():
                skill_md_file = skill_path / "SKILL.md"
                if skill_md_file.exists():
                    try:
                        skill_data = self.parse_skill_md(skill_md_file)
                        skill_name = skill_data['name']
                        
                        # Store only metadata for progressive disclosure
                        self.skills[skill_name] = {
                            'name': skill_data['name'],
                            'description': skill_data['description'],
                            'path': str(skill_path),
                            'skill_md_path': str(skill_md_file),
                            'content_loaded': False,
                            'content': None,
                            'full_content': None
                        }
                        print(f"Loaded skill: {skill_name}")
                    except Exception as e:
                        print(f"Error loading skill {skill_path.name}: {e}")
    
    def get_skills_metadata(self) -> List[Dict[str, Any]]:
        """Get metadata for all available skills (name and description only)"""
        return [
            {
                "name": skill["name"],
                "description": skill["description"]
            }
            for skill in self.skills.values()
        ]
    
    def get_skills_xml(self) -> str:
        """Generate XML format for available skills (Claude-compatible)"""
        xml_parts = ["<available_skills>"]
        for skill in self.skills.values():
            xml_parts.append(f"  <skill>")
            xml_parts.append(f"    <name>{skill['name']}</name>")
            xml_parts.append(f"    <description>{skill['description']}</description>")
            xml_parts.append(f"  </skill>")
        xml_parts.append("</available_skills>")
        return "\n".join(xml_parts)
    
    def activate_skill(self, skill_name: str) -> Optional[str]:
        """Activate a skill by loading its full SKILL.md content"""
        if skill_name not in self.skills:
            return None
        
        skill = self.skills[skill_name]
        
        # Load full content if not already loaded
        if not skill['content_loaded']:
            skill_md_path = Path(skill['skill_md_path'])
            skill_data = self.parse_skill_md(skill_md_path)
            skill['content'] = skill_data['content']
            skill['full_content'] = skill_data['full_content']
            skill['content_loaded'] = True
        
        return skill['full_content']
    
    def execute_skill(self, skill_name: str, parameters: Dict[str, Any] = None) -> Dict[str, Any]:
        """Execute a skill with given parameters"""
        if skill_name not in self.skills:
            return {"error": f"Skill '{skill_name}' not found"}
        
        skill = self.skills[skill_name]
        skill_path = Path(skill['path'])
        
        # Look for scripts in the scripts directory
        scripts_dir = skill_path / "scripts"
        if not scripts_dir.exists():
            return {"error": f"No scripts directory found for skill '{skill_name}'"}
        
        # Try to find a script with the skill name
        script_path = scripts_dir / f"{skill_name}.py"
        if not script_path.exists():
            # Try script.py as fallback
            script_path = scripts_dir / "script.py"
            if not script_path.exists():
                return {"error": f"No script found for skill '{skill_name}'"}
        
        try:
            # Execute the skill script with parameters
            params_json = json.dumps(parameters or {})
            result = subprocess.run(
                [sys.executable, str(script_path), params_json],
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
        # Use XML format for skills as per Agent Skills specification
        skills_xml = self.skill_loader.get_skills_xml()
        
        system_message = f"""You are a helpful AI assistant with access to skills.

{skills_xml}

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
        """Activate skill by loading full SKILL.md content"""
        skill_name = skill_info["name"]
        
        if skill_name not in self.skill_loader.skills:
            return {"execute": False, "response": f"Skill '{skill_name}' not found"}
        
        # Activate the skill (load full SKILL.md content)
        skill_content = self.skill_loader.activate_skill(skill_name)
        
        if not skill_content:
            return {"execute": False, "response": f"Could not load skill '{skill_name}'"}
        
        # Add skill instructions to context
        activation_message = f"""Activating skill '{skill_name}'.

Full skill instructions:
{skill_content}

Parameters you want to use: {json.dumps(skill_info.get('parameters', {}))}
"""
        
        self.messages.append({"role": "assistant", "content": activation_message})
        
        # Auto-execute after activation (following progressive disclosure pattern)
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
