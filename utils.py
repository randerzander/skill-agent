"""Utility functions for the agent framework."""
import yaml
from openai import OpenAI


def get_openai_client():
    """Get a configured OpenAI client instance."""
    with open('config.yaml', 'r') as f:
        config = yaml.safe_load(f)
    
    return OpenAI(
        base_url=config['openai_base_url'],
        api_key=config.get('openai_api_key', 'not-needed')
    )


def get_config():
    """Load and return the config.yaml."""
    with open('config.yaml', 'r') as f:
        return yaml.safe_load(f)
