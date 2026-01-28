"""Utility functions for the agent framework."""
import os
import re
import yaml
from pathlib import Path
from typing import Dict, Any, Optional
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()


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


def get_openai_client(config_path: str = "config.yaml", api_key: Optional[str] = None) -> OpenAI:
    """
    Get a configured OpenAI client instance.
    
    Args:
        config_path: Path to config file
        api_key: Optional API key override
    
    Returns:
        Configured OpenAI client
    """
    config = load_config(config_path)
    openai_config = config.get('openai', {})
    
    # Get API key from parameter, env var, or config
    api_key_env = openai_config.get('api_key_env', 'OPENROUTER_API_KEY')
    final_api_key = api_key or os.getenv(api_key_env)
    
    if not final_api_key:
        raise ValueError(f"API key not found. Set {api_key_env} environment variable.")
    
    return OpenAI(
        base_url=openai_config.get('base_url', 'https://openrouter.ai/api/v1'),
        api_key=final_api_key
    )


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


def get_task_dir(task_type: str = "incomplete") -> Path:
    """
    Get task directory path.
    
    Args:
        task_type: 'incomplete' or 'completed'
    
    Returns:
        Path to task directory
    """
    return get_scratch_dir() / f"{task_type}_tasks"


def ensure_scratch_dir() -> Path:
    """Ensure scratch directory exists and return path."""
    scratch_dir = get_scratch_dir()
    scratch_dir.mkdir(exist_ok=True)
    return scratch_dir
