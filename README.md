# Agent Skills Framework

A framework that implements the [Agent Skills specification](https://agentskills.io) for enabling AI agents to discover, select, and execute skills based on user requests. Uses OpenAI's client library with OpenRouter to access the Nemotron Nano 70B free model.

## What are Agent Skills?

Agent Skills are a lightweight, open format for extending AI agent capabilities with specialized knowledge and workflows. This framework follows the specification from [agentskills.io](https://agentskills.io).

## Features

- **Progressive Disclosure**: Load only skill names and descriptions at startup, full content on demand
- **SKILL.md Format**: Skills defined using YAML frontmatter and Markdown instructions
- **LLM-Driven Selection**: Uses an LLM to intelligently select appropriate skills based on user input
- **Dynamic Activation**: Loads full skill instructions into context when needed
- **Script Execution**: Execute bundled scripts with JSON parameters
- **XML Format Support**: Claude-compatible skill metadata format
- **Extensible**: Easy to add new skills by following the skill structure

## Installation

1. Clone the repository:
```bash
git clone https://github.com/randerzander/skill-agent.git
cd skill-agent
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Configure your OpenRouter API key:
```bash
cp .env.example .env
# Edit .env and add your OPENROUTER_API_KEY
```

## Usage

Run the agent framework:
```bash
python agent.py
```

This will start an interactive session where you can chat with the agent. The agent will automatically select and execute appropriate skills based on your requests.

Example interaction:
```
You: Greet me please
Agent: [Uses the greet skill] Hello! It's great to meet you. How can I help you today?

You: Greet John
Agent: [Uses the greet skill with name parameter] Hello, John! It's wonderful to meet you. How can I help you today?
```

## How It Works

The framework implements **progressive disclosure** to manage context efficiently:

1. **Discovery**: At startup, agents load only the name and description of each available skill
2. **Selection**: The LLM analyzes user input and selects an appropriate skill
3. **Activation**: When a skill is selected, the full `SKILL.md` content is loaded into context
4. **Execution**: The agent follows the instructions, optionally executing bundled scripts
5. **Response**: Results are passed back to the LLM for natural language response generation

This approach keeps agents fast while giving them access to more context on demand.

## Skill Structure

Skills follow the Agent Skills specification. Each skill is a directory containing:

```
my-skill/
├── SKILL.md          # Required: instructions + metadata
├── scripts/          # Optional: executable code
├── references/       # Optional: documentation
└── assets/           # Optional: templates, resources
```

### The SKILL.md File

Every skill starts with a `SKILL.md` file containing YAML frontmatter and Markdown instructions:

```markdown
---
name: skill-name
description: When to use this skill
---

# Skill Name

## When to use this skill
Use this skill when...

## How to use
Instructions for the agent...
```

**Required frontmatter:**
- `name`: A short identifier
- `description`: When to use this skill

**Markdown body:** Contains the actual instructions (no specific restrictions)

### Example: Greet Skill

```
skills/greet/
├── SKILL.md
└── scripts/
    └── greet.py
```

The greet skill demonstrates:
- YAML frontmatter with name and description
- Markdown instructions for when and how to use the skill
- An optional script for execution

## Creating New Skills

To create a new skill:

1. Create a directory in `skills/` with your skill name
2. Create a `SKILL.md` file with:
   - YAML frontmatter (name and description)
   - Markdown instructions
3. Optionally add a `scripts/` directory with executable code
4. Scripts should accept JSON parameters via `sys.argv[1]` and output JSON to stdout

Example script structure:

```python
#!/usr/bin/env python3
import json
import sys

def my_skill_function(param1=None):
    # Your skill logic here
    return "result"

if __name__ == "__main__":
    params = {}
    if len(sys.argv) > 1:
        params = json.loads(sys.argv[1])
    
    result = my_skill_function(params.get("param1"))
    print(json.dumps({"result": result}))
```

## Architecture

The framework consists of three main components:

### 1. SkillLoader

Manages skill discovery and execution following the Agent Skills specification:
- Parses `SKILL.md` files to extract frontmatter and content
- Implements progressive disclosure (loads metadata at startup, full content on demand)
- Provides skill metadata in XML format for Claude-compatible prompts
- Executes skill scripts with JSON parameters

### 2. AgentSkillsFramework

Main agent loop orchestrating the workflow:
- Manages conversation with the LLM
- Uses XML format for skill metadata injection
- Activates skills by loading full SKILL.md content
- Handles the flow between user input and responses

### 3. OpenAI Client

Interfaces with the LLM:
- Configured to use OpenRouter as the base URL
- Uses the Nemotron Nano 70B free model

## Configuration

Environment variables (set in `.env`):
- `OPENROUTER_API_KEY`: Your OpenRouter API key (required)

## Testing

Run the test suite:
```bash
python test_framework.py
```

Run the example simulation (works without API key):
```bash
python example.py
```

## Learn More

- [Agent Skills Specification](https://agentskills.io)
- [Example Skills on GitHub](https://github.com/anthropics/skills)
- [Best Practices for Authoring Skills](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices)

## License

MIT