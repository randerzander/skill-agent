---
name: greet
description: Greets the user with a friendly message including the current date and time. Can personalize the greeting with the user's name if provided.
---

# Greet Skill

## When to use this skill

Use this skill when the user wants to be greeted or when you want to provide a friendly welcome message to someone with the current date and time.

## How to greet

This skill provides friendly greeting functionality with timestamp information. You can greet users in two ways:

### Greet without a name

Simply execute the greeting script without parameters to provide a general greeting with the current date and time.

### Greet with a name

When you know the user's name, provide it as a parameter to personalize the greeting. The script will use the name to create a warm, personalized welcome message along with the current date and time.

## Execution

To execute this skill, run the `scripts/greet.py` script with optional JSON parameters:

```bash
python scripts/greet.py '{"name": "Alice"}'
```

Or without a name:

```bash
python scripts/greet.py '{}'
```

The script will output a JSON response containing the greeting message with the current date and time.
