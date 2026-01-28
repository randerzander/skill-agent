# Tests

Test scripts for the Agent Skills Framework.

## Available Tests

### `test_framework.py`
Main test suite for the framework. Tests skill loading, parsing, and basic functionality.

```bash
python tests/test_framework.py
```

### `test_github_token.py`
Comprehensive test for GitHub token authentication. Verifies:
- GitHub URL detection
- Token authentication
- Rate limit verification
- Content reading

```bash
python tests/test_github_token.py
```

Requires `GITHUB_TOKEN` set in `.env` file.

### `example.py`
Example simulation that demonstrates the framework without requiring an API key.

```bash
python tests/example.py
```

### `test_interactive.py`
Interactive testing script for manual testing and debugging.

```bash
python tests/test_interactive.py
```

### `test_tools_flow.py`
Tests the tools workflow and OpenAI function calling integration.

```bash
python tests/test_tools_flow.py
```

### `diagnostic.py`
Diagnostic utilities for troubleshooting issues.

```bash
python tests/diagnostic.py
```

### `debug_messages.py`
Debug script for examining message formats and conversation flow.

```bash
python tests/debug_messages.py
```

## Running All Tests

To run the main test suite:
```bash
cd /home/dev/projects/skill-agent
python tests/test_framework.py
```

## Test Dependencies

All tests use the same dependencies as the main framework. Ensure you have installed:
```bash
pip install -r requirements.txt
```
