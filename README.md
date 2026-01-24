# Agent Skills Framework

A basic framework that enables AI agents to discover, select, and execute skills based on user requests. This framework uses OpenAI's client library with OpenRouter to access the Nemotron Nano 70B free model.

## Features

- **Skill Discovery**: Automatically loads skills from the `skills/` directory
- **LLM-Driven Selection**: Uses an LLM to intelligently select appropriate skills based on user input
- **Dynamic Execution**: Executes skill scripts and passes results back to the LLM
- **Metadata-Based Context**: Loads skill metadata into context for informed decision-making
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

1. **User Input**: User provides a request to the agent
2. **Skill Selection**: The LLM analyzes available skills and selects an appropriate one (if needed)
3. **Metadata Loading**: The selected skill's metadata is loaded into context
4. **Execution Decision**: The LLM decides whether to execute the skill
5. **Skill Execution**: The skill script is executed with provided parameters
6. **Result Processing**: The execution result is passed back to the LLM
7. **Response Generation**: The LLM generates a natural language response based on the result

## Creating New Skills

Skills are stored in the `skills/` directory. Each skill is a subdirectory containing:

1. `metadata.json`: Describes the skill, its parameters, and script location
2. `script.py`: The executable script that performs the skill's function

### Example Skill Structure

```
skills/
└── greet/
    ├── metadata.json
    └── script.py
```

### metadata.json Format

```json
{
  "name": "skill_name",
  "description": "What this skill does",
  "parameters": {
    "param_name": {
      "type": "string",
      "description": "Parameter description",
      "required": false
    }
  },
  "script": "script.py"
}
```

### script.py Format

Skills should:
- Accept parameters as a JSON string in `sys.argv[1]`
- Output results as JSON to stdout
- Follow this basic structure:

```python
#!/usr/bin/env python3
import json
import sys

def skill_function(param1=None):
    # Your skill logic here
    return "result"

if __name__ == "__main__":
    params = {}
    if len(sys.argv) > 1:
        params = json.loads(sys.argv[1])
    
    result = skill_function(params.get("param1"))
    print(json.dumps({"result": result}))
```

## Architecture

The framework consists of three main components:

1. **SkillLoader**: Manages skill discovery and execution
   - Loads skills from the filesystem
   - Provides skill metadata
   - Executes skill scripts

2. **AgentSkillsFramework**: Main agent loop
   - Manages conversation with the LLM
   - Orchestrates skill selection and execution
   - Handles the flow between user input and responses

3. **OpenAI Client**: Interfaces with the LLM
   - Configured to use OpenRouter as the base URL
   - Uses the Nemotron Nano 70B free model

## Configuration

Environment variables (set in `.env`):
- `OPENROUTER_API_KEY`: Your OpenRouter API key (required)

## License

MIT