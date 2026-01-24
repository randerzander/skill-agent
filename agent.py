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
        
        # Extract YAML frontmatter (more flexible pattern)
        frontmatter_match = re.match(r'^---\s*\n(.*?)\n---\s*(?:\n|$)(.*)', content, re.DOTALL)
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
    
    def get_skill_scripts(self, skill_name: str) -> List[Dict[str, Any]]:
        """Get list of available scripts for a skill"""
        if skill_name not in self.skills:
            return []
        
        skill = self.skills[skill_name]
        skill_path = Path(skill['path'])
        scripts_dir = skill_path / "scripts"
        
        if not scripts_dir.exists():
            return []
        
        scripts = []
        for script_file in scripts_dir.glob("*.py"):
            script_name = script_file.stem
            scripts.append({
                "name": script_name,
                "path": str(script_file)
            })
        
        return scripts
    
    def get_skill_tools(self, skill_name: str) -> List[Dict[str, Any]]:
        """Convert skill scripts into OpenAI tool definitions"""
        scripts = self.get_skill_scripts(skill_name)
        tools = []
        
        for script in scripts:
            # Create a tool definition for each script
            # Use just the script name as the tool name
            tool = {
                "type": "function",
                "function": {
                    "name": script['name'],
                    "description": f"Execute the {script['name']} script from the {skill_name} skill",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "params": {
                                "type": "object",
                                "description": "Parameters to pass to the script as JSON",
                                "additionalProperties": True
                            }
                        },
                        "required": []
                    }
                }
            }
            tools.append(tool)
        
        return tools
    
    def execute_skill_script(self, skill_name: str, script_name: str, parameters: Dict[str, Any] = None) -> Dict[str, Any]:
        """Execute a specific skill script with given parameters"""
        if skill_name not in self.skills:
            return {"error": f"Skill '{skill_name}' not found"}
        
        skill = self.skills[skill_name]
        skill_path = Path(skill['path'])
        scripts_dir = skill_path / "scripts"
        
        if not scripts_dir.exists():
            return {"error": f"No scripts directory found for skill '{skill_name}'"}
        
        script_path = scripts_dir / f"{script_name}.py"
        if not script_path.exists():
            return {"error": f"Script '{script_name}' not found for skill '{skill_name}'"}
        
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
        self.model = "nvidia/nemotron-3-nano-30b-a3b:free"
        
        # Initialize skill loader
        self.skill_loader = SkillLoader()
        
        # Conversation history - start with system message
        skills_xml = self.skill_loader.get_skills_xml()
        system_message = f"""You are a helpful AI assistant with access to skills.

{skills_xml}

When a user needs help with a task that matches a skill's description, mention the skill in your response. The skill will then be activated and you'll have access to tools to execute it."""
        
        self.messages = [{"role": "system", "content": system_message}]
    
    def run(self, user_input: str, max_iterations: int = 10) -> str:
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
        
        # Track active skill and its tools
        active_skill = None
        active_tools = []
        
        iteration = 0
        while iteration < max_iterations:
            iteration += 1
            
            # Prepare tools based on active skill
            tools = active_tools if active_skill else None
            
            # Get LLM response with tools
            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=self.messages,
                    tools=tools if tools else None
                )
                
                message = response.choices[0].message
                
                # Check if LLM wants to call a tool
                if message.tool_calls:
                    # Add assistant message with tool calls to history
                    self.messages.append({
                        "role": "assistant",
                        "content": message.content,
                        "tool_calls": [
                            {
                                "id": tc.id,
                                "type": tc.type,
                                "function": {
                                    "name": tc.function.name,
                                    "arguments": tc.function.arguments
                                }
                            }
                            for tc in message.tool_calls
                        ]
                    })
                    
                    # Execute each tool call
                    for tool_call in message.tool_calls:
                        function_name = tool_call.function.name
                        function_args = json.loads(tool_call.function.arguments)
                        
                        # The function name is just the script name
                        # We know which skill is active
                        if active_skill:
                            script_name = function_name
                            
                            # Execute the script
                            result = self.skill_loader.execute_skill_script(
                                active_skill,
                                script_name,
                                function_args.get("params", {})
                            )
                            
                            # Add tool response to messages
                            self.messages.append({
                                "role": "tool",
                                "tool_call_id": tool_call.id,
                                "content": json.dumps(result)
                            })
                    
                    # After tool execution, clear tools and continue to get final response
                    active_tools = []
                    continue
                
                # Check if we need to activate a skill
                if not active_skill and message.content:
                    # Check if message mentions a skill
                    for skill_name in self.skill_loader.skills.keys():
                        if skill_name.lower() in message.content.lower():
                            # Activate this skill
                            skill_content = self.skill_loader.activate_skill(skill_name)
                            active_skill = skill_name
                            active_tools = self.skill_loader.get_skill_tools(skill_name)
                            
                            # Add skill activation to context
                            skill_message = f"Activating skill '{skill_name}'.\n\nFull skill instructions:\n{skill_content}\n\nYou now have access to the following tools from this skill. Use them to complete the user's request."
                            self.messages.append({"role": "assistant", "content": message.content})
                            self.messages.append({"role": "user", "content": skill_message})
                            
                            # Continue to next iteration with tools available
                            break
                    else:
                        # No skill needed, return response
                        return message.content
                else:
                    # Return final response
                    return message.content if message.content else "I've completed the task."
                    
            except Exception as e:
                print(f"Error calling LLM: {e}")
                return f"Error: {str(e)}"
        
        return "Maximum iterations reached. Unable to complete the request."


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
