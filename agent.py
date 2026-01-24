#!/usr/bin/env python3
"""
Agent Skills Framework
A framework for AI agents to discover and execute skills based on user requests.
Implements the Agent Skills specification from agentskills.io
"""
import os
import sys
import json
import re
import importlib.util
import traceback
import time
from pathlib import Path
from typing import List, Dict, Any, Optional
from openai import OpenAI
from dotenv import load_dotenv
import yaml
from rich.console import Console
from rich.live import Live
from rich.spinner import Spinner
from rich.text import Text

# Load environment variables
load_dotenv()

# Initialize Rich console
console = Console()

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
            # Import the script module dynamically
            spec = importlib.util.spec_from_file_location(f"{skill_name}.{script_name}", script_path)
            if spec is None or spec.loader is None:
                return {"error": f"Failed to load script '{script_name}'"}
            
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            
            # Look for an execute function in the module
            if hasattr(module, 'execute'):
                # Call the execute function with parameters
                result = module.execute(parameters or {})
                # Ensure result is a dict
                if not isinstance(result, dict):
                    return {"result": result}
                return result
            else:
                return {"error": f"Script '{script_name}' does not have an 'execute' function"}
        
        except Exception as e:
            error_details = traceback.format_exc()
            return {"error": f"Script execution failed: {str(e)}", "traceback": error_details}


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

When a user needs help with a task that matches a skill's description, you can activate that skill by using the activate_skill function. Once activated, you'll have access to tools to execute it.

If the user is just asking about available skills or general questions, answer normally without activating any skills."""
        
        self.messages = [{"role": "system", "content": system_message}]
        
        # Define the activate_skill tool
        self.activate_skill_tool = {
            "type": "function",
            "function": {
                "name": "activate_skill",
                "description": "Activate a skill to gain access to its tools and functionality",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "skill_name": {
                            "type": "string",
                            "description": "The name of the skill to activate"
                        }
                    },
                    "required": ["skill_name"]
                }
            }
        }
    
    def _create_progress_text(self, message: str, elapsed: float, spinner_char: str = "⠋", extra_info: str = "") -> Text:
        """Create a formatted progress text with spinner and elapsed time"""
        text = Text()
        text.append(spinner_char, style="cyan bold")
        text.append(f" {message} ", style="dim")
        if extra_info:
            text.append(extra_info, style="blue")
            text.append(" ", style="dim")
        text.append(f"({elapsed:.1f}s)", style="yellow")
        return text
    
    def _estimate_tokens(self, text: str) -> int:
        """Estimate token count from text length"""
        return int(len(text) / 4.5)
    
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
            # If no skill is active, offer the activate_skill tool
            # If a skill is active, offer that skill's tools
            if active_skill:
                tools = active_tools
            else:
                tools = [self.activate_skill_tool]
            
            # Get LLM response with tools
            try:
                # Create a live display for the LLM call
                spinner_frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
                start_time = time.time()
                frame_index = 0
                
                # Calculate input tokens
                messages_text = json.dumps(self.messages)
                input_tokens = self._estimate_tokens(messages_text)
                model_display = self.model.split('/')[-1] if '/' in self.model else self.model
                
                # Check if we're in an interactive terminal
                if sys.stdout.isatty():
                    with Live(console=console, refresh_per_second=10, transient=False) as live:
                        # Start the spinner
                        live.update(self._create_progress_text(
                            f"Calling LLM [{model_display}]", 
                            0.0, 
                            spinner_frames[0],
                            f"~{input_tokens:,} tokens in"
                        ))
                        
                        # Make the API call in a way that allows us to update the display
                        response = None
                        import threading
                        
                        def make_call():
                            nonlocal response
                            response = self.client.chat.completions.create(
                                model=self.model,
                                messages=self.messages,
                                tools=tools
                            )
                        
                        thread = threading.Thread(target=make_call)
                        thread.start()
                        
                        # Update the display while waiting
                        while thread.is_alive():
                            elapsed = time.time() - start_time
                            live.update(self._create_progress_text(
                                f"Calling LLM [{model_display}]", 
                                elapsed, 
                                spinner_frames[frame_index % len(spinner_frames)],
                                f"~{input_tokens:,} tokens in"
                            ))
                            frame_index += 1
                            time.sleep(0.1)
                        
                        thread.join()
                        
                        # Calculate output tokens
                        message = response.choices[0].message
                        output_text = message.content or ""
                        if message.tool_calls:
                            for tc in message.tool_calls:
                                output_text += tc.function.name + tc.function.arguments
                        output_tokens = self._estimate_tokens(output_text)
                        
                        # Final update with completion time
                        elapsed = time.time() - start_time
                        final_text = Text()
                        final_text.append("✓", style="green bold")
                        final_text.append(f" LLM call completed [{model_display}] ", style="dim")
                        final_text.append(f"~{input_tokens:,} in / ~{output_tokens:,} out ", style="blue")
                        final_text.append(f"({elapsed:.1f}s)", style="green")
                        live.update(final_text)
                else:
                    # Non-interactive mode - just make the call without spinner
                    response = self.client.chat.completions.create(
                        model=self.model,
                        messages=self.messages,
                        tools=tools
                    )
                    message = response.choices[0].message
                
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
                        
                        # Check if this is a skill activation request
                        if function_name == "activate_skill":
                            skill_name = function_args.get("skill_name")
                            
                            console.print(f"[cyan]→[/cyan] Activating skill: [bold]{skill_name}[/bold]")
                            
                            if skill_name in self.skill_loader.skills:
                                # Activate the skill
                                skill_content = self.skill_loader.activate_skill(skill_name)
                                active_skill = skill_name
                                active_tools = self.skill_loader.get_skill_tools(skill_name)
                                
                                console.print(f"[green]✓[/green] Skill activated: [bold]{skill_name}[/bold]")
                                
                                # Add tool response confirming activation
                                activation_msg = f"Skill '{skill_name}' activated successfully.\n\nFull skill instructions:\n{skill_content}\n\nYou now have access to tools from this skill."
                                self.messages.append({
                                    "role": "tool",
                                    "tool_call_id": tool_call.id,
                                    "content": activation_msg
                                })
                            else:
                                # Skill not found
                                console.print(f"[red]✗[/red] Skill not found: [bold]{skill_name}[/bold]")
                                self.messages.append({
                                    "role": "tool",
                                    "tool_call_id": tool_call.id,
                                    "content": f"Error: Skill '{skill_name}' not found."
                                })
                        else:
                            # This is a skill script execution
                            if active_skill:
                                script_name = function_name
                                
                                console.print(f"[cyan]→[/cyan] Executing script: [bold]{script_name}[/bold] from skill [bold]{active_skill}[/bold]")
                                
                                # Execute the script
                                result = self.skill_loader.execute_skill_script(
                                    active_skill,
                                    script_name,
                                    function_args.get("params", {})
                                )
                                
                                if "error" in result:
                                    console.print(f"[red]✗[/red] Script execution failed: {result['error']}")
                                else:
                                    console.print(f"[green]✓[/green] Script executed: [bold]{script_name}[/bold]")
                                
                                # Add tool response to messages
                                self.messages.append({
                                    "role": "tool",
                                    "tool_call_id": tool_call.id,
                                    "content": json.dumps(result)
                                })
                    
                    # Continue to next iteration
                    continue
                
                # No tool calls - return the response
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
