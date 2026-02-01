"""Utility functions for the agent framework."""
import re
import yaml
from pathlib import Path
from typing import Dict, Any, Optional


def load_config(config_path: str = "config.yaml") -> Dict[str, Any]:
    """
    Load configuration from YAML file.
    
    Args:
        config_path: Path to config file (default: config.yaml)
    
    Returns:
        Configuration dictionary, or empty dict if file not found
    """
    config_file = Path(config_path)
    if not config_file.exists():
        return {}
    
    try:
        with open(config_file, 'r') as f:
            config = yaml.safe_load(f)
            return config or {}
    except Exception:
        return {}


def sanitize_filename(name: str, max_length: int = 100) -> str:
    """
    Sanitize a string for use as a filename.
    
    Args:
        name: String to sanitize
        max_length: Maximum length of result
    
    Returns:
        Sanitized filename-safe string
    """
    # Replace problematic characters with underscores
    name = re.sub(r'[^\w\s-]', '_', name)
    # Replace whitespace with underscores
    name = re.sub(r'\s+', '_', name)
    # Limit length
    return name[:max_length]


def get_scratch_dir() -> Path:
    """Get the scratch directory path."""
    return Path("scratch")


def ensure_scratch_dir() -> Path:
    """Ensure scratch directory exists and return path."""
    scratch_dir = get_scratch_dir()
    scratch_dir.mkdir(exist_ok=True)
    return scratch_dir


def detect_new_files(
    since_timestamp: float,
    scratch_dir: Optional[Path] = None,
    *,
    skip_internal: bool = True,
    skip_tasks: bool = True,
    skip_code_py: bool = True,
) -> list[dict]:
    """Detect files in scratch/ modified at or after a given timestamp."""
    new_files = []
    base_dir = scratch_dir or get_scratch_dir()
    if base_dir.exists():
        for file_path in base_dir.rglob('*'):
            if not file_path.is_file():
                continue
            if skip_internal and file_path.name in ['USER_QUERY.txt', 'CURRENT_TASK.txt']:
                continue
            if skip_tasks and ('incomplete_tasks' in file_path.parts or 'completed_tasks' in file_path.parts):
                continue
            if skip_code_py and file_path.suffix == '.py' and 'code' in file_path.parts:
                continue

            file_mtime = file_path.stat().st_mtime
            if file_mtime >= since_timestamp:
                rel_path = file_path.relative_to(base_dir)
                new_files.append({
                    'path': str(rel_path),
                    'size': file_path.stat().st_size
                })
    return new_files


# Conversation history management for tools
_conversation_history = None
_history_modified_callback = None

def set_conversation_history(messages: list, modified_callback=None):
    """
    Set the conversation history for tools to access.
    Called by the agent to share its message history.
    
    Args:
        messages: List of conversation messages
        modified_callback: Optional callback to notify agent when history is modified
    """
    global _conversation_history, _history_modified_callback
    _conversation_history = messages
    _history_modified_callback = modified_callback


def get_conversation_history() -> list:
    """
    Get the current conversation history.
    Returns empty list if not set.
    """
    return _conversation_history if _conversation_history is not None else []


def remove_last_tool_exchange(tool_name: str, log_message: str = None):
    """
    Remove the last assistant + tool message exchange for a specific tool.
    Useful for deduplicating repeated tool calls.
    
    Args:
        tool_name: Name of the tool to remove
        log_message: Optional message to log about the removal
    
    Returns:
        True if removed, False if not found
    """
    global _conversation_history, _history_modified_callback
    
    if not _conversation_history:
        return False
    
    # Look backwards through history for the last tool call
    assistant_idx = None
    tool_idx = None
    
    for i in range(len(_conversation_history) - 1, -1, -1):
        msg = _conversation_history[i]
        
        # Find tool response
        if msg.get("role") == "tool" and tool_idx is None:
            # Check if this matches our tool
            # We need to find the corresponding assistant message
            tool_idx = i
            
        # Find assistant message with tool calls
        elif msg.get("role") == "assistant" and msg.get("tool_calls") and assistant_idx is None:
            # Check if any tool call matches our tool name
            for tc in msg.get("tool_calls", []):
                if tc.get("function", {}).get("name") == tool_name:
                    assistant_idx = i
                    break
            
            # If we found both, remove them
            if assistant_idx is not None and tool_idx is not None:
                # Remove in reverse order to maintain indices
                del _conversation_history[tool_idx]
                del _conversation_history[assistant_idx]
                
                if log_message:
                    print(f"[History] {log_message}")
                
                # Notify agent if callback is set
                if _history_modified_callback:
                    _history_modified_callback()
                
                return True
    
    return False
