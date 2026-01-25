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
from datetime import datetime
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

# Setup directories
LOGS_DIR = Path("logs")
LOGS_DIR.mkdir(exist_ok=True)

SCRATCH_DIR = Path("scratch")
SCRATCH_DIR.mkdir(exist_ok=True)

class SkillLoader:
    """Loads and manages agent skills following the Agent Skills specification"""
    
    def __init__(self, skills_dir: str = "skills", enabled_skills: List[str] = None):
        self.skills_dir = Path(skills_dir)
        self.skills = {}
        self.enabled_skills = enabled_skills  # Whitelist of enabled skills
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
                        
                        # Always load verify skill for automatic link checking
                        # Check if skill is enabled (if whitelist exists)
                        if self.enabled_skills and skill_name not in self.enabled_skills:
                            # Allow verify to load even if not in enabled list
                            if skill_name != 'verify':
                                continue
                        
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
    
    def _auto_verify_links(self, response: str, live=None) -> tuple[str, bool]:
        """
        Automatically verify links in response if verify skill is available
        
        Returns:
            tuple: (verified_response, should_retry)
                - verified_response: Response with invalid links removed
                - should_retry: True if agent should try again with better sources
        """
        # Check if verify skill exists
        if 'verify' not in self.skills:
            return response, False
        
        try:
            # Import verify_links script
            verify_script_path = Path(self.skills['verify']['skill_md_path']).parent / 'scripts' / 'verify_links.py'
            if not verify_script_path.exists():
                return response, False
            
            # Load and execute verify_links
            import importlib.util
            spec = importlib.util.spec_from_file_location("verify_links", verify_script_path)
            verify_module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(verify_module)
            
            # Call verify_links with spinner if available
            if live:
                with live.console.status("[cyan]⚙ Verifying links...[/cyan]", spinner="dots") as status:
                    result = verify_module.execute({"response_text": response})
            else:
                result = verify_module.execute({"response_text": response})
            
            if "error" in result:
                # If verification fails, just return original response
                return response, False
            
            verification_data = result.get("result", {})
            verify_status = verification_data.get("status")
            
            if verify_status == "invalid_links_found":
                # Log verification warning
                console.print("\n[yellow]⚠ Link verification detected invalid URLs[/yellow]")
                console.print(f"[dim]Invalid: {verification_data.get('invalid_urls', 0)}/{verification_data.get('total_urls', 0)} URLs[/dim]")
                console.print("[dim]Asking agent to retry with valid sources...[/dim]")
                
                # Return modified response and signal to retry
                should_retry = verification_data.get("should_research_again", False)
                return verification_data.get("modified_response", response), should_retry
            elif verify_status == "all_valid":
                console.print(f"[green]✓ All {verification_data.get('total_urls', 0)} links verified[/green]")
                return response, False
            else:
                # No links or other status - return original
                return response, False
                
        except Exception as e:
            # If verification fails for any reason, just return original response
            console.print(f"[dim]Note: Link verification skipped ({str(e)})[/dim]")
            return response, False
    
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
        
        # Get skill metadata which contains parameters
        skill = self.skills.get(skill_name)
        if not skill:
            return tools
        
        # Load full skill data to get frontmatter
        skill_md_path = Path(skill['skill_md_path'])
        skill_data = self.parse_skill_md(skill_md_path)
        parameters_spec = skill_data['frontmatter'].get('parameters', {})
        
        for script in scripts:
            # Get parameters for this specific script
            script_params = parameters_spec.get(script['name'], {})
            
            # Convert SKILL.md parameter format to OpenAI tool format
            tool_params = self._convert_parameters_to_tool_spec(script_params)
            
            tool = {
                "type": "function",
                "function": {
                    "name": script['name'],
                    "description": skill_data.get('description', f"Execute the {script['name']} script"),
                    "parameters": tool_params
                }
            }
            tools.append(tool)
        
        return tools
    
    def _convert_parameters_to_tool_spec(self, params_def: Dict[str, Any]) -> Dict[str, Any]:
        """Convert SKILL.md parameters format to OpenAI tool parameters format"""
        if not params_def:
            # No parameters defined - return generic object
            return {
                "type": "object",
                "properties": {},
                "required": []
            }
        
        properties = {}
        required = []
        
        for param_name, param_config in params_def.items():
            prop = {
                "type": param_config.get("type", "string"),
                "description": param_config.get("description", "")
            }
            
            if "default" in param_config:
                prop["default"] = param_config["default"]
            
            properties[param_name] = prop
            
            if param_config.get("required", False):
                required.append(param_name)
        
        return {
            "type": "object",
            "properties": properties,
            "required": required
        }
    
    def execute_skill_script(self, skill_name: str, script_name: str, parameters: Dict[str, Any] = None, live_display = None) -> Dict[str, Any]:
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
    
    def _load_config(self, config_path: str) -> Dict[str, Any]:
        """Load configuration from YAML file"""
        config_file = Path(config_path)
        if not config_file.exists():
            console.print(f"[yellow]Warning: Config file {config_path} not found, using defaults[/yellow]")
            return {}
        
        try:
            with open(config_file, 'r') as f:
                config = yaml.safe_load(f)
                return config or {}
        except Exception as e:
            console.print(f"[red]Error loading config: {e}[/red]")
            return {}
    
    def __init__(self, api_key: str = None, config_path: str = "config.yaml", event_callback=None):
        # Load configuration
        config = self._load_config(config_path)
        
        # Event callback for real-time updates (used by web UI)
        self.event_callback = event_callback
        
        self.api_key = api_key or os.getenv("OPENROUTER_API_KEY")
        if not self.api_key:
            raise ValueError("OpenRouter API key not found. Set OPENROUTER_API_KEY environment variable.")
        
        # Initialize OpenAI client with config
        openai_config = config.get('openai', {})
        self.client = OpenAI(
            base_url=openai_config.get('base_url', 'https://openrouter.ai/api/v1'),
            api_key=self.api_key
        )
        
        # Model configuration from config
        self.model = openai_config.get('model', 'nvidia/nemotron-3-nano-30b-a3b:free')
        
        # Initialize skill loader with enabled skills filter
        skills_config = config.get('skills', {})
        enabled_skills = skills_config.get('enabled', None)  # None = all enabled
        self.skill_loader = SkillLoader(enabled_skills=enabled_skills)
        
        # Setup conversation log file
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.log_file = LOGS_DIR / f"conversation_{timestamp}.jsonl"
        
        # Conversation history - start with simple system message
        # Get system message from config or use default
        system_message = config.get('system_message', """You are a helpful AI assistant with access to various skills.

Activate available skills to complete tasks. After each skill, consider whether you need to activate another skill to complete the user's request.""")
        
        self.messages = [{"role": "system", "content": system_message}]
        
        # Create tool definitions for each skill (discovery phase)
        # Exclude verify skill from discovery - it runs automatically
        self.skill_discovery_tools = []
        for skill_name, skill in self.skill_loader.skills.items():
            if skill_name == 'verify':
                continue  # Don't expose verify to agent
            
            self.skill_discovery_tools.append({
                "type": "function",
                "function": {
                    "name": f"activate_{skill_name}",
                    "description": skill['description'],
                    "parameters": {
                        "type": "object",
                        "properties": {},
                        "required": []
                    }
                }
            })
        
        # Keep the old activate_skill tool as fallback (shouldn't be needed)
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
    
    def _log_message(self, entry: Dict[str, Any]):
        """Log a message to the conversation log file and call event callback"""
        try:
            log_entry = {
                "timestamp": datetime.now().isoformat(),
                **entry
            }
            
            # Write to log file
            with open(self.log_file, 'a') as f:
                f.write(json.dumps(log_entry) + "\n")
            
            # Call event callback if registered (for web UI)
            if self.event_callback:
                try:
                    self.event_callback(log_entry)
                except Exception as cb_err:
                    # Don't let callback errors break the agent
                    pass
                    
        except Exception as e:
            # Don't fail on logging errors
            console.print(f"[dim red]Warning: Failed to log: {e}[/dim red]")
    
    def run(self, user_input: str, max_iterations: int = 15) -> str:
        """
        Main agent loop that processes user input through skill selection and execution
        
        Args:
            user_input: The user's request
            max_iterations: Maximum number of iterations to prevent infinite loops
        
        Returns:
            The final response from the agent
        """
        # Write user query to scratch directory for skills to access
        user_query_file = SCRATCH_DIR / "user_query.txt"
        with open(user_query_file, 'w') as f:
            f.write(user_input)
        
        # Add user message to history
        self.messages.append({"role": "user", "content": user_input})
        
        # Log user input
        self._log_message({
            "type": "user_input",
            "content": user_input
        })
        
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
                tools = self.skill_discovery_tools
            
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
                
                # Log LLM response
                self._log_message({
                    "type": "llm_response",
                    "iteration": iteration,
                    "model": self.model,
                    "content": message.content,
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "function": tc.function.name,
                            "arguments": json.loads(tc.function.arguments)
                        } for tc in (message.tool_calls or [])
                    ] if message.tool_calls else None
                })
                
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
                        
                        # Check if this is a skill activation request (new format: activate_SKILLNAME)
                        if function_name.startswith("activate_"):
                            skill_name = function_name.replace("activate_", "")
                            
                            if skill_name in self.skill_loader.skills:
                                # Activate the skill
                                skill_content = self.skill_loader.activate_skill(skill_name)
                                active_skill = skill_name
                                active_tools = self.skill_loader.get_skill_tools(skill_name)
                                
                                # Calculate approximate token count (rough estimate: ~4 chars per token)
                                token_estimate = len(skill_content) // 4
                                
                                console.print(f"[green]✓[/green] Skill activated: [bold]{skill_name}[/bold] [dim](~{token_estimate} tokens added)[/dim]")
                                
                                # Log skill activation completion
                                self._log_message({
                                    "type": "skill_activated",
                                    "skill_name": skill_name,
                                    "tools_count": len(active_tools),
                                    "tokens_added": token_estimate
                                })
                                
                                # Add tool response confirming activation
                                activation_msg = f"Skill '{skill_name}' activated.\n\nInstructions:\n{skill_content}\n\nYou can access tools from this skill."
                                self.messages.append({
                                    "role": "tool",
                                    "tool_call_id": tool_call.id,
                                    "content": activation_msg
                                })
                            else:
                                # Skill not found
                                console.print(f"[red]✗[/red] Skill not found: [bold]{skill_name}[/bold]")
                                
                                # Log skill activation failure
                                self._log_message({
                                    "type": "skill_activation_failed",
                                    "skill_name": skill_name
                                })
                                
                                self.messages.append({
                                    "role": "tool",
                                    "tool_call_id": tool_call.id,
                                    "content": f"Error: Skill '{skill_name}' not found."
                                })
                        else:
                            # This is a skill script execution
                            if active_skill:
                                script_name = function_name
                                # Parameters are now passed directly (not wrapped in 'params')
                                params = function_args
                                
                                # Create a status line that will be updated
                                status_text = Text()
                                status_text.append("⠋ ", style="cyan")
                                status_text.append(f"Executing {active_skill}.{script_name}", style="bold")
                                
                                # Show params preview (truncated)
                                params_str = str(params)
                                if len(params_str) > 60:
                                    params_str = params_str[:57] + "..."
                                status_text.append(f" {params_str}", style="dim")
                                
                                with Live(status_text, console=console, refresh_per_second=10) as live:
                                    # Execute the script
                                    result = self.skill_loader.execute_skill_script(
                                        active_skill,
                                        script_name,
                                        params,
                                        live  # Pass live display for updates
                                    )
                                    
                                    # Log tool execution
                                    self._log_message({
                                        "type": "tool_execution",
                                        "skill": active_skill,
                                        "script": script_name,
                                        "params": params,
                                        "result": result
                                    })
                                    
                                    # Update with final status
                                    if "error" in result:
                                        final_text = Text()
                                        final_text.append("✗ ", style="red")
                                        final_text.append(f"{active_skill}.{script_name}", style="bold")
                                        final_text.append(f": {result['error'][:100]}", style="red dim")
                                        live.update(final_text)
                                    else:
                                        final_text = Text()
                                        final_text.append("✓ ", style="green")
                                        final_text.append(f"{active_skill}.{script_name}", style="bold")
                                        
                                        # Show params
                                        params_str = str(params)
                                        if len(params_str) > 60:
                                            params_str = params_str[:57] + "..."
                                        final_text.append(f" {params_str}", style="dim")
                                        
                                        # Add result size if available
                                        if "result" in result:
                                            result_len = len(str(result["result"]))
                                            final_text.append(f" → {result_len:,} chars", style="dim")
                                        
                                        live.update(final_text)
                                
                                # Add tool response to messages
                                self.messages.append({
                                    "role": "tool",
                                    "tool_call_id": tool_call.id,
                                    "content": json.dumps(result)
                                })
                    
                    # Continue to next iteration
                    continue
                
                # No tool calls - return the response
                final_response = message.content if message.content else "I've completed the task."
                
                # Automatically verify links in final response
                verified_response, should_retry = self.skill_loader._auto_verify_links(final_response, live=live)
                
                if should_retry:
                    # Add verification feedback as a system message
                    self.messages.append({
                        "role": "user",
                        "content": "Your previous response contained invalid or inaccessible links. Please use the web tool to find valid sources and provide an updated answer with working links."
                    })
                    # Continue loop to let agent try again
                    continue
                
                # Log final response
                self._log_message({
                    "type": "final_response",
                    "content": verified_response
                })
                
                return verified_response
                    
            except Exception as e:
                print(f"Error calling LLM: {e}")
                return f"Error: {str(e)}"
        
        # Max iterations reached - extract best response from history
        final_response = "Maximum iterations reached. Unable to complete the request."
        
        # Try to find the last assistant message with content
        for msg in reversed(self.messages):
            if msg.get("role") == "assistant" and msg.get("content"):
                final_response = msg["content"]
                break
        
        # Verify links in the response if enabled
        verified_response, _ = self.skill_loader._auto_verify_links(final_response)
        
        # Log final response
        self._log_message({
            "type": "final_response",
            "content": verified_response
        })
        
        return verified_response


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
            
            if user_input.lower() == 'clear':
                agent.messages = []
                console.print("[green]✓[/green] Chat history cleared")
                continue
            
            response = agent.run(user_input)
            print(f"\nAgent: {response}")
            
        except KeyboardInterrupt:
            print("\n\nGoodbye!")
            break
        except Exception as e:
            print(f"Error: {e}")


if __name__ == "__main__":
    main()
