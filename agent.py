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
from utils import load_config, get_scratch_dir, detect_new_files

# Load environment variables
load_dotenv()

# Initialize Rich console
console = Console()

# Setup directories
LOGS_DIR = Path("logs")
LOGS_DIR.mkdir(exist_ok=True)

SCRATCH_DIR = get_scratch_dir()
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
                        
                        # Always load finalize skill for automatic link checking and final submission
                        # Check if skill is enabled (if whitelist exists)
                        if self.enabled_skills and skill_name not in self.enabled_skills:
                            # Allow finalize to load even if not in enabled list
                            if skill_name != 'finalize':
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
    

    def _auto_verify_links(self, response: str, live=None) -> tuple[str, bool]:
        """
        Automatically verify links in response if finalize skill is available
        
        Returns:
            tuple: (verified_response, should_retry)
                - verified_response: Response with invalid links removed
                - should_retry: True if agent should try again with better sources
        """
        # Check if finalize skill exists
        if 'finalize' not in self.skills:
            return response, False
        
        try:
            # Import verify_links script
            verify_script_path = Path(self.skills['finalize']['skill_md_path']).parent / 'scripts' / 'verify_links.py'
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
        """Convert skill scripts/tools into OpenAI tool definitions"""
        skill = self.skills.get(skill_name)
        if not skill:
            return []
        
        skill_path = Path(skill['path'])
        tools_file = skill_path / "scripts" / "tools.py"
        
        # If tools.py exists, extract functions from it
        if tools_file.exists():
            return self._extract_tools_from_module(tools_file, skill_name)
        
        # Fallback to old script-based approach for backwards compatibility
        return self._get_tools_from_scripts(skill_name)
    
    def _extract_tools_from_module(self, tools_file: Path, skill_name: str) -> List[Dict[str, Any]]:
        """Extract tool definitions from tools.py by inspecting functions"""
        import inspect
        import importlib.util
        
        try:
            # Import the tools module
            spec = importlib.util.spec_from_file_location(f"{skill_name}.tools", tools_file)
            if spec is None or spec.loader is None:
                return []
            
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            
            tools = []
            
            # Find all functions in the module
            for name, obj in inspect.getmembers(module, inspect.isfunction):
                # Skip private functions and main
                if name.startswith('_') or name == 'main':
                    continue
                
                # Skip functions not defined in this module (i.e., imports)
                if obj.__module__ != module.__name__:
                    continue
                
                # Get function signature
                sig = inspect.signature(obj)
                doc = inspect.getdoc(obj) or f"Execute {name}"
                
                # Build parameters spec from function signature
                properties = {}
                required = []
                
                for param_name, param in sig.parameters.items():
                    # Skip *args, **kwargs
                    if param.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD):
                        continue
                    
                    # Get type hint
                    param_type = "string"  # default
                    if param.annotation != inspect.Parameter.empty:
                        if param.annotation == int:
                            param_type = "integer"
                        elif param.annotation == float:
                            param_type = "number"
                        elif param.annotation == bool:
                            param_type = "boolean"
                        elif param.annotation == list:
                            param_type = "array"
                        elif param.annotation == dict:
                            param_type = "object"
                    
                    properties[param_name] = {
                        "type": param_type,
                        "description": f"The {param_name} parameter"
                    }
                    
                    # Required if no default value
                    if param.default == inspect.Parameter.empty:
                        required.append(param_name)
                
                tool = {
                    "type": "function",
                    "function": {
                        "name": name,
                        "description": doc,
                        "parameters": {
                            "type": "object",
                            "properties": properties,
                            "required": required
                        }
                    }
                }
                tools.append(tool)
            
            return tools
            
        except Exception as e:
            console.print(f"[red]Error extracting tools from {tools_file}: {e}[/red]")
            return []
    
    def _get_tools_from_scripts(self, skill_name: str) -> List[Dict[str, Any]]:
        """Legacy method: Get tools from individual script files and SKILL.md frontmatter"""
        scripts = self.get_skill_scripts(skill_name)
        tools = []
        
        # Get skill metadata which contains parameters
        skill = self.skills.get(skill_name)
        if not skill:
            return tools
        
        # Load full skill data to get frontmatter
        skill_md_path = Path(skill['skill_md_path'])
        skill_data = self.parse_skill_md(skill_md_path)
        
        # Check for scripts-based definition (new format)
        scripts_def = skill_data['frontmatter'].get('scripts', [])
        if scripts_def:
            for script_def in scripts_def:
                properties = {}
                required = []
                
                params = script_def.get('parameters', [])
                for param in params:
                    properties[param['name']] = {
                        "type": param.get('type', 'string'),
                        "description": param.get('description', '')
                    }
                    if param.get('required', False):
                        required.append(param['name'])
                
                tool = {
                    "type": "function",
                    "function": {
                        "name": script_def['name'],
                        "description": script_def.get('description', ''),
                        "parameters": {
                            "type": "object",
                            "properties": properties,
                            "required": required
                        }
                    }
                }
                tools.append(tool)
            return tools
        
        # Fallback to old parameters-based format
        parameters_spec = skill_data['frontmatter'].get('parameters', {})
        
        for script in scripts:
            # Skip tools.py if it exists (already handled above)
            if script['name'] == 'tools':
                continue
                
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
    
    def _find_tool_in_other_skills(self, tool_name: str, exclude_skill: str = None) -> tuple:
        """
        Search for a tool function across all skills.
        
        Args:
            tool_name: Name of the tool/function to find
            exclude_skill: Skill to exclude from search (usually the one that failed)
        
        Returns:
            Tuple of (skill_name, function) if found, else (None, None)
        """
        import importlib.util
        
        for skill_name, skill in self.skills.items():
            if skill_name == exclude_skill:
                continue
            
            skill_path = Path(skill['path'])
            tools_file = skill_path / "scripts" / "tools.py"
            
            if tools_file.exists():
                try:
                    spec = importlib.util.spec_from_file_location(f"{skill_name}.tools", tools_file)
                    if spec and spec.loader:
                        module = importlib.util.module_from_spec(spec)
                        spec.loader.exec_module(module)
                        
                        if hasattr(module, tool_name):
                            return (skill_name, getattr(module, tool_name))
                except Exception:
                    continue
        
        return (None, None)
    
    def execute_skill_script(self, skill_name: str, script_name: str, parameters: Dict[str, Any] = None, live_display = None) -> Dict[str, Any]:
        """Execute a specific skill script/function with given parameters"""
        if skill_name not in self.skills:
            return {"error": f"Skill '{skill_name}' not found"}
        
        skill = self.skills[skill_name]
        skill_path = Path(skill['path'])
        scripts_dir = skill_path / "scripts"
        
        if not scripts_dir.exists():
            return {"error": f"No scripts directory found for skill '{skill_name}'"}
        
        # First, try to find the function in tools.py
        tools_file = scripts_dir / "tools.py"
        if tools_file.exists():
            try:
                # Import tools module
                import importlib.util
                spec = importlib.util.spec_from_file_location(f"{skill_name}.tools", tools_file)
                if spec and spec.loader:
                    module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(module)
                    
                    # Check if the function exists
                    if hasattr(module, script_name):
                        func = getattr(module, script_name)
                        # Call the function directly with parameters
                        result = func(**parameters) if parameters else func()
                        # Ensure result is a dict
                        if not isinstance(result, dict):
                            return {"result": result}
                        return result
            except Exception as e:
                error_details = traceback.format_exc()
                return {"error": f"Function execution failed: {str(e)}", "traceback": error_details}
        
        # Fallback to individual script files (legacy)
        script_path = scripts_dir / f"{script_name}.py"
        if not script_path.exists():
            # Try to find the tool in other skills
            found_skill, found_func = self._find_tool_in_other_skills(script_name, exclude_skill=skill_name)
            
            if found_func:
                try:
                    # Call the function from the other skill
                    result = found_func(**parameters) if parameters else found_func()
                    
                    # Ensure result is a dict
                    if not isinstance(result, dict):
                        result = {"result": result}
                    
                    # Add a note about cross-skill usage
                    if "result" in result:
                        if isinstance(result["result"], dict):
                            result["result"]["_note"] = f"FYI: You used '{script_name}' from the '{found_skill}' skill. Switch to that skill for more context about this tool."
                        else:
                            result["_note"] = f"FYI: You used '{script_name}' from the '{found_skill}' skill. Switch to that skill for more context about this tool."
                    else:
                        result["_note"] = f"FYI: You used '{script_name}' from the '{found_skill}' skill. Switch to that skill for more context about this tool."
                    
                    return result
                except Exception as e:
                    error_details = traceback.format_exc()
                    return {"error": f"Function execution failed: {str(e)}", "traceback": error_details}
            
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
    
    def _initialize_scratch_directory(self):
        """Initialize/reset scratch directory structure"""
        import shutil
        
        # Check if we should preserve scratch/data
        preserve_data = self.config.get('scratch', {}).get('preserve_data', False)
        data_dir = SCRATCH_DIR / "data"
        
        # Backup data directory if preserving
        data_backup = None
        if preserve_data and data_dir.exists():
            import tempfile
            data_backup = tempfile.mkdtemp()
            shutil.copytree(data_dir, Path(data_backup) / "data")
        
        # Remove scratch directory
        if SCRATCH_DIR.exists():
            shutil.rmtree(SCRATCH_DIR)
        
        # Recreate directory structure
        SCRATCH_DIR.mkdir(exist_ok=True)
        (SCRATCH_DIR / "incomplete_tasks").mkdir(exist_ok=True)
        (SCRATCH_DIR / "completed_tasks").mkdir(exist_ok=True)
        
        # Restore data directory if it was backed up
        if data_backup:
            shutil.copytree(Path(data_backup) / "data", data_dir)
            shutil.rmtree(data_backup)
    
    def _get_current_task_info(self) -> str:
        """Get current task info as formatted string, or empty string if none"""
        current_task_file = SCRATCH_DIR / "CURRENT_TASK.txt"
        if not current_task_file.exists():
            return ""
        
        try:
            with open(current_task_file, 'r') as f:
                current_task_data = json.load(f)
            
            if current_task_data.get('status') == 'active':
                return f"\n\n--- CURRENT TASK ---\nTask #{current_task_data['task_number']}: {current_task_data['description']}\n---"
        except:
            pass
        return ""
    
    def _safe_parse_json(self, json_str: str) -> dict:
        """
        Safely parse JSON that might be malformed.
        
        Args:
            json_str: JSON string to parse
        
        Returns:
            Parsed dict or original string on error
        """
        try:
            return json.loads(json_str)
        except json.JSONDecodeError as e:
            # Try to fix common issues
            # Sometimes LLMs return multiple JSON objects or extra text
            try:
                # Try to extract just the first valid JSON object
                import re
                # Find first { and its matching }
                first_brace = json_str.find('{')
                if first_brace != -1:
                    brace_count = 0
                    for i, char in enumerate(json_str[first_brace:], start=first_brace):
                        if char == '{':
                            brace_count += 1
                        elif char == '}':
                            brace_count -= 1
                            if brace_count == 0:
                                # Found matching brace
                                return json.loads(json_str[first_brace:i+1])
            except:
                pass
            
            # If all fixes fail, return the string as-is wrapped in a dict
            console.print(f"[yellow]Warning: Failed to parse tool arguments JSON: {e}[/yellow]")
            console.print(f"[dim]Arguments string: {json_str[:200]}...[/dim]")
            return {"_raw": json_str, "_parse_error": str(e)}
    
    def __init__(self, api_key: str = None, config_path: str = "config.yaml", event_callback=None):
        # Load configuration
        config = load_config(config_path)
        self.config = config  # Store config for later use
        
        # Event callback for real-time updates (used by web UI)
        self.event_callback = event_callback
        
        # Clean scratch directory at the beginning of each run
        self._initialize_scratch_directory()
        
        # Initialize OpenAI client with config
        openai_config = config.get('openai', {})
        
        # Get API key from config or fallback to env var
        api_key_env = openai_config.get('api_key_env', 'OPENROUTER_API_KEY')
        self.api_key = api_key or os.getenv(api_key_env)
        
        if not self.api_key:
            raise ValueError(f"API key not found. Set {api_key_env} environment variable.")
        
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
        self.skill_discovery_tools = []
        for skill_name, skill in self.skill_loader.skills.items():
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
        
        # Global tools that are ALWAYS available regardless of active skill
        global_tools_config = config.get('global_tools', {})
        self.global_tools = [
            {
                "type": "function",
                "function": {
                    "name": "list_skills",
                    "description": global_tools_config.get('list_skills', {}).get('description', 
                        "List all available skills with their descriptions"),
                    "parameters": {
                        "type": "object",
                        "properties": {},
                        "required": []
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "skill_switch",
                    "description": global_tools_config.get('skill_switch', {}).get('description',
                        "Switch from the current skill to a different skill"),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "skill_name": {
                                "type": "string",
                                "description": "The name of the skill to switch to (e.g., 'web', 'planning', 'answer')"
                            }
                        },
                        "required": ["skill_name"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "complete_task",
                    "description": global_tools_config.get('complete_task', {}).get('description',
                        "Mark a task as complete and save its result to completed_tasks directory"),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "task_number": {
                                "type": "integer",
                                "description": "The task number to mark as complete"
                            },
                            "result": {
                                "type": "string",
                                "description": "The result or answer for this task"
                            }
                        },
                        "required": ["task_number", "result"]
                    }
                }
            }
        ]
        
        # Track reasoning traces separately (for display only, not sent to LLM)
        # Map message index -> reasoning trace
        self.reasoning_traces = {}
        
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

    def _activate_skill(
        self,
        skill_name: str,
        *,
        current_task_info: str = "",
        auto_activated: bool = False,
        activation_message_prefix: Optional[str] = None,
    ) -> tuple[str, list, int, str]:
        """Activate a skill and return its content, tools, token estimate, and activation message."""
        skill_content = self.skill_loader.activate_skill(skill_name)
        active_tools = self.skill_loader.get_skill_tools(skill_name)
        token_estimate = len(skill_content) // 4

        activation_prefix = activation_message_prefix or f"Skill '{skill_name}' activated."
        activation_msg = (
            f"{activation_prefix}\n\nInstructions:\n{skill_content}\n\n"
            f"You can access tools from this skill.{current_task_info}"
        )

        log_entry = {
            "type": "skill_activated",
            "skill_name": skill_name,
            "tools_count": len(active_tools),
            "tokens_added": token_estimate,
        }
        if auto_activated:
            log_entry["auto_activated"] = True

        self._log_message(log_entry)

        return skill_content, active_tools, token_estimate, activation_msg

    def _finalize_response(self, user_input: str, response_text: str, query_start_time: float, live=None) -> tuple[str, bool]:
        """Finalize response: verify links, detect files, create report, log, return response."""
        verified_response, should_retry = self.skill_loader._auto_verify_links(response_text, live=live)
        if should_retry:
            return "", True

        new_files = detect_new_files(query_start_time, get_scratch_dir())
        verified_response = self._append_files_list(verified_response, new_files)

        html_report = self._create_html_report(user_input, verified_response, new_files)
        catbox_url = self._upload_to_catbox(html_report)

        if catbox_url:
            verified_response += f"\n\n**Report URL:** {catbox_url}\n"

        self._log_message({
            "type": "final_response",
            "content": verified_response,
            "report_url": catbox_url if catbox_url else None,
            "new_files": new_files if new_files else None
        })

        return verified_response, False
    
    def run(self, user_input: str, max_iterations: int = None) -> str:
        """
        Main agent loop that processes user input through skill selection and execution
        
        Args:
            user_input: The user's request
            max_iterations: Maximum number of iterations to prevent infinite loops (defaults to config value or 30)
        
        Returns:
            The final response from the agent
        """
        # Import conversation history utilities
        from utils import set_conversation_history
        
        # Get max_iterations from config if not provided
        if max_iterations is None:
            agent_config = self.config.get('agent', {})
            max_iterations = agent_config.get('max_iterations', 30)
        
        # Clean scratch directory at the beginning of each run
        self._initialize_scratch_directory()
        
        # Record start time to track new files
        import time
        query_start_time = time.time()
        
        # Reset conversation history for new query
        system_message = self.messages[0]  # Preserve system message
        self.messages = [system_message]
        self.reasoning_traces = {}  # Clear reasoning traces
        
        # Share conversation history with tools
        set_conversation_history(self.messages)
        
        # Write user query to scratch directory for skills to access
        user_query_file = SCRATCH_DIR / "USER_QUERY.txt"
        with open(user_query_file, 'w') as f:
            f.write(user_input)
        
        # Add user message to history
        self.messages.append({"role": "user", "content": user_input})
        
        # Log user input
        self._log_message({
            "type": "user_input",
            "content": user_input
        })
        
        # Auto-activate planning skill at the beginning
        active_skill = "planning"
        current_task_info = self._get_current_task_info()
        skill_content, active_tools, token_estimate, skill_message = self._activate_skill(
            "planning",
            current_task_info=current_task_info,
            auto_activated=True
        )

        console.print(f"[green]✓[/green] Skill auto-activated: [bold]planning[/bold] [dim](~{token_estimate} tokens added)[/dim]")

        # Inject skill content and current task info into messages
        self.messages.append({"role": "assistant", "content": skill_message})
        
        iteration = 0
        rate_limit_retries = 0
        max_rate_limit_retries = 3
        while iteration < max_iterations:
            iteration += 1
            
            # Prepare tools based on active skill
            # Global tools are ALWAYS available
            # If no skill is active, offer the activate_skill tools + global tools
            # If a skill is active, offer that skill's tools + global tools
            if active_skill:
                tools = active_tools + self.global_tools
            else:
                tools = self.skill_discovery_tools + self.global_tools
            
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
                            f"Calling LLM [{model_display}] (Iteration {iteration}/{max_iterations})", 
                            0.0, 
                            spinner_frames[0],
                            f"~{input_tokens:,} tokens in"
                        ))
                        
                        # Make the API call in a way that allows us to update the display
                        response = None
                        api_error = None
                        import threading
                        
                        def make_call():
                            nonlocal response, api_error
                            try:
                                response = self.client.chat.completions.create(
                                    model=self.model,
                                    messages=self.messages,
                                    tools=tools
                                )
                            except Exception as e:
                                api_error = e
                        
                        thread = threading.Thread(target=make_call)
                        thread.start()
                        
                        # Update the display while waiting
                        while thread.is_alive():
                            elapsed = time.time() - start_time
                            live.update(self._create_progress_text(
                                f"Calling LLM [{model_display}] (Iteration {iteration}/{max_iterations})", 
                                elapsed, 
                                spinner_frames[frame_index % len(spinner_frames)],
                                f"~{input_tokens:,} tokens in"
                            ))
                            frame_index += 1
                            time.sleep(0.1)
                        
                        thread.join()
                        
                        # Check for errors
                        if api_error:
                            # Check if it's a rate limit error
                            if isinstance(api_error, Exception):
                                error_str = str(api_error)
                                if '429' in error_str and 'Rate limit exceeded' in error_str:
                                    rate_limit_retries += 1
                                    if rate_limit_retries <= max_rate_limit_retries:
                                        # Show rate limit message
                                        rate_limit_text = Text()
                                        rate_limit_text.append("⚠", style="yellow bold")
                                        rate_limit_text.append(f" Rate limit exceeded. Waiting 60s before retry ({rate_limit_retries}/{max_rate_limit_retries})...", style="yellow")
                                        live.update(rate_limit_text)
                                        
                                        # Wait 60 seconds
                                        time.sleep(60)
                                        
                                        # Retry - decrement iteration so we don't count this against our limit
                                        iteration -= 1
                                        console.print(f"[yellow]⟳[/yellow] Retrying after rate limit wait...")
                                        continue
                                    else:
                                        console.print(f"[red]✗[/red] Max rate limit retries ({max_rate_limit_retries}) exceeded")
                            
                            raise api_error
                        
                        if response is None:
                            raise Exception("API call failed to return a response")
                        
                        # Get actual token counts from response
                        if hasattr(response, 'usage') and response.usage:
                            input_tokens = response.usage.prompt_tokens
                            output_tokens = response.usage.completion_tokens
                            total_tokens = response.usage.total_tokens
                        else:
                            # Fallback to estimates if usage not available
                            message = response.choices[0].message
                            output_text = message.content or ""
                            if message.tool_calls:
                                for tc in message.tool_calls:
                                    output_text += tc.function.name + tc.function.arguments
                            output_tokens = self._estimate_tokens(output_text)
                            total_tokens = input_tokens + output_tokens
                        
                        # Final update with completion time
                        elapsed = time.time() - start_time
                        final_text = Text()
                        final_text.append("✓", style="green bold")
                        final_text.append(f" LLM [{model_display}] ", style="dim")
                        final_text.append(f"{input_tokens:,} prompt + {output_tokens:,} completion = {total_tokens:,} total ", style="blue")
                        final_text.append(f"({elapsed:.1f}s) ", style="green")
                        final_text.append(f"[Iteration {iteration}/{max_iterations}]", style="dim")
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
                
                # Get actual token usage from response
                actual_tokens = None
                if hasattr(response, 'usage') and response.usage:
                    actual_tokens = {
                        'prompt_tokens': response.usage.prompt_tokens,
                        'completion_tokens': response.usage.completion_tokens,
                        'total_tokens': response.usage.total_tokens
                    }
                
                # Log LLM response (including reasoning if present)
                log_data = {
                    "type": "llm_response",
                    "iteration": iteration,
                    "model": self.model,
                    "content": message.content,
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "function": tc.function.name,
                            "arguments": self._safe_parse_json(tc.function.arguments)
                        } for tc in (message.tool_calls or [])
                    ] if message.tool_calls else None
                }
                
                # Add actual token usage if available
                if actual_tokens:
                    log_data['tokens'] = actual_tokens
                
                # Capture reasoning traces if present (some models include this)
                if hasattr(message, 'refusal') and message.refusal:
                    log_data['refusal'] = message.refusal
                
                # Check for reasoning in the raw response
                if hasattr(response, 'choices') and len(response.choices) > 0:
                    choice = response.choices[0]
                    # Some models expose reasoning via message attributes
                    if hasattr(choice.message, 'reasoning_content') and choice.message.reasoning_content:
                        log_data['reasoning'] = choice.message.reasoning_content
                    # Or via the choice itself
                    elif hasattr(choice, 'reasoning') and choice.reasoning:
                        log_data['reasoning'] = choice.reasoning
                
                self._log_message(log_data)
                
                # Check if LLM wants to call a tool
                if message.tool_calls:
                    # First, check if any tool calls have parse errors
                    has_parse_error = False
                    for tc in message.tool_calls:
                        test_parse = self._safe_parse_json(tc.function.arguments)
                        if "_parse_error" in test_parse:
                            has_parse_error = True
                            console.print(f"[red]✗[/red] Tool call has malformed JSON arguments: {tc.function.name}")
                            console.print(f"[dim]Parse error: {test_parse['_parse_error']}[/dim]")
                            break
                    
                    # If there's a parse error, don't add the malformed message to history
                    # Instead, add a generic instruction to retry with valid JSON
                    if has_parse_error:
                        self.messages.append({
                            "role": "assistant",
                            "content": "I need to call a tool but generated invalid JSON."
                        })
                        self.messages.append({
                            "role": "user",
                            "content": "Your tool call had malformed JSON arguments. Please follow the tool argument schema exactly. Ensure all strings are properly escaped, especially code with newlines. Try again with valid JSON."
                        })
                        continue
                    
                    # Add assistant message with tool calls to history
                    assistant_msg = {
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
                    }
                    
                    self.messages.append(assistant_msg)
                    
                    # Log reasoning if present (for visibility, but don't add to messages sent to OpenAI)
                    if hasattr(response, 'choices') and len(response.choices) > 0:
                        choice = response.choices[0]
                        reasoning_trace = None
                        # Check various fields where reasoning might be stored
                        if hasattr(choice.message, 'reasoning') and choice.message.reasoning:
                            reasoning_trace = choice.message.reasoning
                        elif hasattr(choice.message, 'reasoning_content') and choice.message.reasoning_content:
                            reasoning_trace = choice.message.reasoning_content
                        elif hasattr(choice, 'reasoning') and choice.reasoning:
                            reasoning_trace = choice.reasoning
                        
                        if reasoning_trace:
                            # Store separately for chat history display
                            msg_index = len(self.messages) - 1
                            self.reasoning_traces[msg_index] = reasoning_trace
                            
                            # Log to file
                            self._log_message({
                                "type": "reasoning_trace",
                                "iteration": iteration,
                                "trace": reasoning_trace
                            })
                    
                    # Execute each tool call
                    for tool_call in message.tool_calls:
                        function_name = tool_call.function.name
                        function_args = self._safe_parse_json(tool_call.function.arguments)
                        
                        # Note: Parse errors are already handled above - we won't reach here with malformed JSON
                        
                        # Check if this is a skill activation request (new format: activate_SKILLNAME)
                        if function_name.startswith("activate_"):
                            skill_name = function_name.replace("activate_", "")
                            
                            if skill_name in self.skill_loader.skills:
                                # Activate the skill (ignore any arguments passed by LLM)
                                current_task_info = self._get_current_task_info()
                                skill_content, active_tools, token_estimate, activation_msg = self._activate_skill(
                                    skill_name,
                                    current_task_info=current_task_info
                                )
                                active_skill = skill_name

                                console.print(f"[green]✓[/green] Skill activated: [bold]{skill_name}[/bold] [dim](~{token_estimate} tokens added)[/dim]")
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
                        
                        # Handle global tools
                        elif function_name == "list_skills":
                            # List all available skills
                            skills_list = []
                            for skill_name, skill in self.skill_loader.skills.items():
                                skills_list.append(f"- **{skill_name}**: {skill['description']}")
                            
                            skills_message = "Available skills:\n\n" + "\n".join(skills_list)
                            
                            console.print(f"[cyan]ℹ[/cyan] Listed {len(skills_list)} available skill(s)")
                            
                            self._log_message({
                                "type": "tool_execution",
                                "script": "list_skills",
                                "result": {"result": skills_message}
                            })
                            
                            self.messages.append({
                                "role": "tool",
                                "tool_call_id": tool_call.id,
                                "content": skills_message
                            })
                        
                        elif function_name == "skill_switch":
                            # Switch to a different skill
                            new_skill_name = function_args.get('skill_name')
                            
                            if not new_skill_name:
                                self.messages.append({
                                    "role": "tool",
                                    "tool_call_id": tool_call.id,
                                    "content": "Error: skill_name parameter is required"
                                })
                                continue
                            
                            if new_skill_name not in self.skill_loader.skills:
                                available = ", ".join(self.skill_loader.skills.keys())
                                error_msg = f"Error: Skill '{new_skill_name}' not found. Available skills: {available}"
                                
                                console.print(f"[red]✗[/red] Skill not found: [bold]{new_skill_name}[/bold]")
                                
                                self._log_message({
                                    "type": "tool_execution",
                                    "script": "skill_switch",
                                    "result": {"error": error_msg}
                                })
                                
                                self.messages.append({
                                    "role": "tool",
                                    "tool_call_id": tool_call.id,
                                    "content": error_msg
                                })
                                continue
                            
                            # Log deactivation of old skill if one was active and switch to new
                            if active_skill:
                                self._log_message({
                                    "type": "skill_deactivated",
                                    "skill_name": active_skill
                                })
                            
                            # Activate the new skill
                            current_task_info = self._get_current_task_info()
                            skill_content, active_tools, token_estimate, activation_msg = self._activate_skill(
                                new_skill_name,
                                current_task_info=current_task_info,
                                activation_message_prefix=f"Switched to skill '{new_skill_name}'."
                            )
                            active_skill = new_skill_name
                            
                            # Combined log line for skill switch
                            console.print(f"[green]✓[/green] Skill switch: [bold]{new_skill_name}[/bold] [dim](~{token_estimate} tokens added)[/dim]")
                            
                            # Log tool execution result for UI spinner
                            self._log_message({
                                "type": "tool_execution",
                                "skill": None,
                                "script": "skill_switch",
                                "params": {"skill_name": new_skill_name},
                                "result": {"result": f"Switched to {new_skill_name}"}
                            })
                            
                            self.messages.append({
                                "role": "tool",
                                "tool_call_id": tool_call.id,
                                "content": activation_msg
                            })
                        
                        elif function_name == "complete_task":
                            # Complete a task and save its result
                            task_number = function_args.get('task_number')
                            result_text = function_args.get('result', '')
                            
                            incomplete_dir = SCRATCH_DIR / "incomplete_tasks"
                            completed_dir = SCRATCH_DIR / "completed_tasks"
                            completed_dir.mkdir(exist_ok=True)
                            
                            task_file = incomplete_dir / f"task_{task_number}.txt"
                            
                            if task_file.exists():
                                # Save result to completed tasks
                                dest_file = completed_dir / f"task_{task_number}.txt"
                                with open(dest_file, 'w') as f:
                                    f.write(result_text)
                                
                                # Remove from incomplete
                                task_file.unlink()
                                
                                console.print(f"[green]✓[/green] Task {task_number} completed")
                                
                                self._log_message({
                                    "type": "task_completed",
                                    "task_number": task_number
                                })
                                
                                # Log tool execution for UI spinner
                                self._log_message({
                                    "type": "tool_execution",
                                    "script": "complete_task",
                                    "result": {"result": f"Task {task_number} completed"}
                                })
                                
                                # Auto-activate next incomplete task
                                remaining_tasks = sorted([
                                    f for f in os.listdir(incomplete_dir) 
                                    if f.startswith("task_") and f.endswith(".txt")
                                ])
                                
                                current_task_file = SCRATCH_DIR / "CURRENT_TASK.txt"
                                
                                if remaining_tasks:
                                    # Get next task
                                    next_task_file = incomplete_dir / remaining_tasks[0]
                                    next_task_num = remaining_tasks[0].replace("task_", "").replace(".txt", "")
                                    
                                    with open(next_task_file, 'r') as f:
                                        next_task_desc = f.read().strip()
                                    
                                    # Update CURRENT_TASK.txt
                                    current_task_data = {
                                        "task_number": int(next_task_num),
                                        "description": next_task_desc,
                                        "status": "active"
                                    }
                                    
                                    with open(current_task_file, 'w') as f:
                                        f.write(json.dumps(current_task_data, indent=2))
                                    
                                    console.print(f"[cyan]→[/cyan] Auto-activated task {next_task_num}")
                                    
                                    # Log task activation for UI
                                    self._log_message({
                                        "type": "task_activated",
                                        "task_number": int(next_task_num)
                                    })
                                    
                                    response_msg = f"Task {task_number} marked as complete. Task {next_task_num} is now active: {next_task_desc}"
                                else:
                                    # No more tasks - clear CURRENT_TASK and auto-activate answer
                                    current_task_data = {
                                        "task_number": None,
                                        "description": None,
                                        "status": "none"
                                    }
                                    
                                    with open(current_task_file, 'w') as f:
                                        f.write(json.dumps(current_task_data, indent=2))
                                    
                                    console.print(f"[green]✓[/green] All tasks completed!")
                                    
                                    # Auto-activate answer skill
                                    if "answer" in self.skill_loader.skills:
                                        skill_content, active_tools, token_estimate, activation_msg = self._activate_skill(
                                            "answer",
                                            current_task_info="",
                                            auto_activated=True
                                        )
                                        active_skill = "answer"

                                        console.print(f"[green]✓[/green] Skill auto-activated: [bold]answer[/bold] [dim](~{token_estimate} tokens added)[/dim]")

                                        response_msg = (
                                            f"Task {task_number} marked as complete. All tasks completed!\n\n"
                                            f"{activation_msg}\n\nYou can now synthesize results, verify citations, and submit your final answer."
                                        )
                                    else:
                                        response_msg = f"Task {task_number} marked as complete. No more tasks remaining."
                                
                                self.messages.append({
                                    "role": "tool",
                                    "tool_call_id": tool_call.id,
                                    "content": json.dumps({
                                        "status": "success",
                                        "task_number": task_number,
                                        "message": response_msg
                                    })
                                })
                            else:
                                console.print(f"[red]✗[/red] Task {task_number} not found")
                                
                                # Log tool execution for UI spinner (error case)
                                self._log_message({
                                    "type": "tool_execution",
                                    "script": "complete_task",
                                    "result": {"error": f"Task {task_number} not found"}
                                })
                                
                                self.messages.append({
                                    "role": "tool",
                                    "tool_call_id": tool_call.id,
                                    "content": json.dumps({
                                        "status": "error",
                                        "message": f"Task {task_number} not found in incomplete_tasks"
                                    })
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
                                    # Check for errors at multiple levels
                                    has_error = False
                                    error_msg = None
                                    
                                    if "error" in result:
                                        has_error = True
                                        error_msg = result['error']
                                    elif "result" in result and isinstance(result["result"], dict) and "error" in result["result"]:
                                        has_error = True
                                        error_msg = result["result"]["error"]
                                    elif "result" in result and isinstance(result["result"], str):
                                        # Check if result string contains error
                                        try:
                                            result_obj = json.loads(result["result"])
                                            if isinstance(result_obj, dict) and "error" in result_obj:
                                                has_error = True
                                                error_msg = result_obj["error"]
                                        except json.JSONDecodeError:
                                            # Not JSON, check if string contains "error" indicators
                                            result_str = result["result"].lower()
                                            if "error" in result_str or "failed" in result_str or "exception" in result_str:
                                                has_error = True
                                                error_msg = result["result"]
                                        except Exception:
                                            pass
                                    
                                    if has_error:
                                        final_text = Text()
                                        final_text.append("✗ ", style="red bold")
                                        final_text.append(f"{active_skill}.{script_name}", style="bold red")
                                        if error_msg:
                                            error_preview = str(error_msg)[:100]
                                            final_text.append(f": {error_preview}", style="red dim")
                                        live.update(final_text)
                                    else:
                                        # Skip duplicate logging for generate_code - it has its own spinner summary
                                        if script_name != "generate_code":
                                            final_text = Text()
                                            final_text.append("✓ ", style="green")
                                            final_text.append(f"{active_skill}.{script_name}", style="bold")
                                            
                                            # Standard formatting for other tools
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
                                
                                # Check if this was a submit tool call - if so, end execution
                                if isinstance(result, dict) and result.get('status') == 'FINAL_ANSWER_SUBMITTED':
                                    final_answer = result.get('final_answer', '')
                                    final_answer, should_retry = self._finalize_response(
                                        user_input,
                                        final_answer,
                                        query_start_time,
                                        live=live
                                    )
                                    if should_retry:
                                        self.messages.append({
                                            "role": "user",
                                            "content": "Your previous response contained invalid or inaccessible links. Please use the web tool to find valid sources and provide an updated answer with working links."
                                        })
                                        continue

                                    return final_answer
                    
                    # Continue to next iteration
                    continue
                
                # No tool calls - check if there are incomplete tasks before allowing completion
                incomplete_dir = SCRATCH_DIR / "incomplete_tasks"
                incomplete_tasks = []
                
                console.print(f"[dim]Debug: Checking for incomplete tasks in {incomplete_dir}[/dim]")
                console.print(f"[dim]Debug: Directory exists: {incomplete_dir.exists()}[/dim]")
                
                if incomplete_dir.exists():
                    try:
                        all_files = os.listdir(incomplete_dir)
                        console.print(f"[dim]Debug: All files in dir: {all_files}[/dim]")
                        
                        incomplete_tasks = sorted([
                            f for f in all_files 
                            if f.startswith("task_") and f.endswith(".txt")
                        ])
                        console.print(f"[dim]Debug: Filtered incomplete tasks: {incomplete_tasks}[/dim]")
                    except Exception as e:
                        console.print(f"[red]Error listing incomplete tasks: {e}[/red]")
                else:
                    console.print(f"[yellow]Warning: Incomplete tasks directory does not exist![/yellow]")
                
                if incomplete_tasks:
                    # There are incomplete tasks - don't allow completion
                    console.print(f"[yellow]⚠[/yellow] Cannot complete: {len(incomplete_tasks)} incomplete task(s) remaining")
                    
                    # Force LLM to continue by adding a system message
                    reminder_msg = f"""You have {len(incomplete_tasks)} incomplete task(s):
{chr(10).join([f"- Task {t.replace('task_', '').replace('.txt', '')}" for t in incomplete_tasks])}

You must complete all tasks before finishing. Use the skill_switch tool to switch to an appropriate skill (e.g., skill_switch with skill_name='web') to work on these tasks."""
                    
                    self.messages.append({
                        "role": "user",
                        "content": reminder_msg
                    })
                    
                    # Continue to next iteration
                    continue
                
                # No incomplete tasks - check if we need to allow final answer submission
                # If answer skill is active and we just returned tool results, give agent one more turn
                if active_skill == 'answer' and message.content is None:
                    # Agent just called a tool in answer skill, let it continue to formulate response
                    console.print(f"[cyan]ℹ[/cyan] All tasks complete, waiting for final answer submission...")
                    continue
                
                # If not in answer skill, force switch to answer skill
                if active_skill != 'answer':
                    console.print(f"[yellow]⚠[/yellow] All tasks complete but not in answer skill. Forcing switch to answer skill...")
                    
                    # Auto-activate answer skill
                    if "answer" in self.skill_loader.skills:
                        skill_content, active_tools, token_estimate, activation_msg = self._activate_skill(
                            "answer",
                            current_task_info="",
                            auto_activated=True,
                            activation_message_prefix="All tasks are complete.\n\nSkill 'answer' activated."
                        )
                        active_skill = "answer"

                        console.print(f"[green]✓[/green] Skill auto-activated: [bold]answer[/bold] [dim](~{token_estimate} tokens added)[/dim]")

                        # Add activation message to force agent to use answer skill
                        activation_msg = f"{activation_msg}\n\nYou must now synthesize the results and submit your final answer."
                        self.messages.append({
                            "role": "user",
                            "content": activation_msg
                        })
                        
                        # Continue to next iteration
                        continue
                
                # No incomplete tasks - return the response
                final_response = message.content if message.content else "I've completed the task."
                
                # Add final assistant message to history with reasoning if present
                final_msg = {
                    "role": "assistant",
                    "content": final_response
                }
                
                self.messages.append(final_msg)
                
                # Log reasoning if present (for visibility, but don't add to messages sent to OpenAI)
                if hasattr(response, 'choices') and len(response.choices) > 0:
                    choice = response.choices[0]
                    reasoning_trace = None
                    if hasattr(choice.message, 'reasoning') and choice.message.reasoning:
                        reasoning_trace = choice.message.reasoning
                    elif hasattr(choice.message, 'reasoning_content') and choice.message.reasoning_content:
                        reasoning_trace = choice.message.reasoning_content
                    elif hasattr(choice, 'reasoning') and choice.reasoning:
                        reasoning_trace = choice.reasoning
                    
                    if reasoning_trace:
                        # Store separately for chat history display
                        msg_index = len(self.messages) - 1
                        self.reasoning_traces[msg_index] = reasoning_trace
                        
                        # Log to file
                        self._log_message({
                            "type": "reasoning_trace",
                            "iteration": iteration,
                            "trace": reasoning_trace
                        })
                
                verified_response, should_retry = self._finalize_response(
                    user_input,
                    final_response,
                    query_start_time,
                    live=live
                )

                if should_retry:
                    # Add verification feedback as a system message
                    self.messages.append({
                        "role": "user",
                        "content": "Your previous response contained invalid or inaccessible links. Please use the web tool to find valid sources and provide an updated answer with working links."
                    })
                    # Continue loop to let agent try again
                    continue

                return verified_response
                    
            except Exception as e:
                import traceback
                print(f"Error calling LLM: {e}")
                traceback.print_exc()
                return f"Error: {str(e)}"
        
        # Max iterations reached - extract best response from history
        console.print(f"[red]✗[/red] Maximum iterations ({max_iterations}) reached")
        final_response = "Maximum iterations reached. Unable to complete the request."
        
        # Try to find the last assistant message with actual content (not SKILL.md activations)
        for msg in reversed(self.messages):
            if msg.get("role") == "assistant" and msg.get("content"):
                content = msg["content"]
                # Skip SKILL.md activation messages
                if "Skill '" in content and "activated" in content and "Instructions:" in content:
                    continue
                final_response = content
                break
        
        verified_response, _ = self._finalize_response(
            user_input,
            final_response,
            query_start_time
        )

        return verified_response
    
    def _append_files_list(self, response: str, new_files: list) -> str:
        """No longer appends file list - files are handled separately (images displayed, others ignored)"""
        # Don't append any file list text - images are displayed inline, other files ignored
        return response
    
    def _create_html_report(self, query: str, answer: str, new_files: list = None) -> str:
        """Create an HTML report of the conversation"""
        import markdown
        import base64
        from datetime import datetime
        
        # Convert markdown to HTML
        answer_html = markdown.markdown(answer, extensions=['fenced_code', 'tables'])
        
        # Generate image embeds for any image files
        images_html = ""
        if new_files:
            image_extensions = {'.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp'}
            scratch_dir = get_scratch_dir()
            
            for file_info in new_files:
                file_path = scratch_dir / file_info['path']
                if file_path.suffix.lower() in image_extensions and file_path.exists():
                    try:
                        # Read and encode image as base64
                        with open(file_path, 'rb') as img_file:
                            img_data = base64.b64encode(img_file.read()).decode('utf-8')
                        
                        # Determine MIME type
                        mime_type = 'image/png' if file_path.suffix.lower() == '.png' else \
                                   'image/jpeg' if file_path.suffix.lower() in ['.jpg', '.jpeg'] else \
                                   'image/gif' if file_path.suffix.lower() == '.gif' else \
                                   'image/svg+xml' if file_path.suffix.lower() == '.svg' else \
                                   'image/webp'
                        
                        images_html += f'''
    <div class="image-container">
        <h3>{file_info['path']}</h3>
        <img src="data:{mime_type};base64,{img_data}" alt="{file_info['path']}" />
    </div>
'''
                    except Exception as e:
                        console.print(f"[yellow]⚠[/yellow] Failed to embed image {file_info['path']}: {e}")
        
        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Agent Report - {datetime.now().strftime('%Y-%m-%d %H:%M')}</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            max-width: 900px;
            margin: 40px auto;
            padding: 20px;
            line-height: 1.6;
            color: #333;
        }}
        h1 {{ color: #2c3e50; border-bottom: 3px solid #3498db; padding-bottom: 10px; }}
        h2 {{ color: #34495e; margin-top: 30px; }}
        h3 {{ color: #7f8c8d; font-size: 0.9em; margin-bottom: 10px; }}
        .query {{ background: #ecf0f1; padding: 15px; border-left: 4px solid #3498db; margin: 20px 0; }}
        .answer {{ margin: 20px 0; }}
        code {{ background: #f4f4f4; padding: 2px 6px; border-radius: 3px; }}
        pre {{ background: #2c3e50; color: #ecf0f1; padding: 15px; border-radius: 5px; overflow-x: auto; }}
        .timestamp {{ color: #7f8c8d; font-size: 0.9em; }}
        .files {{ background: #e8f5e9; padding: 15px; border-radius: 5px; margin-top: 20px; }}
        .image-container {{ 
            margin: 20px 0; 
            padding: 15px; 
            background: #f8f9fa; 
            border-radius: 8px;
            text-align: center;
        }}
        .image-container img {{ 
            max-width: 100%; 
            height: auto; 
            border-radius: 4px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        }}
    </style>
</head>
<body>
    <h1>🤖 Agent Skills Framework Report</h1>
    <div class="timestamp">Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}</div>
    
    <h2>Query</h2>
    <div class="query">{query}</div>
    
    <h2>Response</h2>
    <div class="answer">{answer_html}</div>
    
    {images_html if images_html else ""}
</body>
</html>"""
        return html
    
    def _upload_to_catbox(self, html_content: str) -> str:
        """Upload HTML content to litterbox.moe (renders in browser) and return URL"""
        import requests
        import tempfile
        
        try:
            # Save HTML to temp file
            with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False, encoding='utf-8') as f:
                f.write(html_content)
                temp_path = f.name
            
            # Upload to litterbox.moe (1 hour expiry)
            # litterbox.moe renders HTML files in the browser unlike catbox.moe
            with open(temp_path, 'rb') as f:
                response = requests.post(
                    'https://litterbox.catbox.moe/resources/internals/api.php',
                    data={
                        'reqtype': 'fileupload',
                        'time': '24h'  # Options: 1h, 12h, 24h, 72h
                    },
                    files={'fileToUpload': f},
                    timeout=30
                )
            
            # Clean up temp file
            import os
            os.unlink(temp_path)
            
            if response.status_code == 200:
                url = response.text.strip()
                console.print(f"[green]✓[/green] Report uploaded: {url} (expires in 1 hour)")
                return url
            else:
                body_preview = response.text.strip()[:500]
                if body_preview:
                    console.print(f"[yellow]⚠[/yellow] Failed to upload report (status {response.status_code}): {body_preview}")
                else:
                    console.print(f"[yellow]⚠[/yellow] Failed to upload report (status {response.status_code})")
                return None
                
        except Exception as e:
            console.print(f"[yellow]⚠[/yellow] Failed to upload report: {e}")
            return None


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
    
    # Print available tools for discovery
    print("\nAvailable skill activation tools:")
    for tool in agent.skill_discovery_tools:
        print(f"  - {tool['function']['name']}: {tool['function']['description']}")
    print()
    
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
