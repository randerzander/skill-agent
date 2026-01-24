# Web Frontend Usage Guide

This guide will help you get started with the Agent Skills Framework web interface.

## Starting the Web Server

1. Make sure you have set up your `.env` file with your OpenRouter API key:
```bash
cp .env.example .env
# Edit .env and add your OPENROUTER_API_KEY
```

2. Install dependencies (if not already installed):
```bash
pip install -r requirements.txt
```

3. Start the web server:
```bash
python app.py
```

4. Open your browser to: `http://localhost:10000`

## Using the Interface

### Main Features

#### 1. Chat Interface
- Type your request in the input field
- Press Enter or click the "Send" button
- Watch the execution log update in real-time

#### 2. Execution Log
- Shows real-time progress with spinner animations
- Displays elapsed time for each step
- Color-coded log entries:
  - 🔵 Blue: User messages
  - 🟣 Purple: LLM calls and responses
  - 🟢 Green: Tool executions
  - 🟠 Orange: Skill activations
  - 🔴 Red: Errors

#### 3. Skills Panel
Located on the right side, shows:
- All available skills
- Skill descriptions
- When to use each skill

#### 4. Tools Called Panel
Shows in real-time:
- Which tools are being executed
- Arguments passed to each tool
- Results returned

#### 5. Chat History Overlay
Click the 💭 button in the bottom-right corner to view:
- Complete LLM conversation history
- System messages
- Tool calls with arguments
- Tool results
- Thinking traces (for reasoning models)

## Example Requests

Try these example requests to see the agent in action:

### Greeting
```
Greet me please
```
or
```
Say hello to Alice
```

### Web Search (if web_search skill is available)
```
Search for Python web frameworks
```

### URL Reading (if read_url skill is available)
```
Read the content from https://example.com
```

## Environment Variables

You can customize the server with these environment variables:

- `OPENROUTER_API_KEY`: Your OpenRouter API key (required)
- `PORT`: Server port (default: 10000)
- `SECRET_KEY`: Flask secret key (auto-generated if not set)
- `FLASK_DEBUG`: Enable debug mode (set to "true" for development)

Example:
```bash
export FLASK_DEBUG=true
export PORT=8080
python app.py
```

## Troubleshooting

### Server won't start
- Check that port 10000 is not already in use
- Verify your `.env` file has a valid OPENROUTER_API_KEY
- Make sure all dependencies are installed

### Agent execution fails
- Verify your API key is valid
- Check the execution log for error details
- View the chat history overlay for full conversation

### Real-time updates not working
- Check browser console for errors
- Ensure Server-Sent Events (SSE) are not blocked
- Try refreshing the page

## Production Deployment

For production use:

1. Set a secure SECRET_KEY:
```bash
export SECRET_KEY=$(python -c 'import secrets; print(secrets.token_hex(32))')
```

2. Use a production WSGI server like Gunicorn:
```bash
pip install gunicorn
gunicorn -w 4 -b 0.0.0.0:10000 app:app
```

3. Set FLASK_DEBUG to false (or don't set it):
```bash
unset FLASK_DEBUG
```

4. Consider using a reverse proxy like nginx for HTTPS support

## Tips

- The interface updates in real-time - no need to refresh
- You can view the chat history at any time by clicking the 💭 button
- The execution log shows timing information to help debug performance
- All skills are loaded on startup and displayed in the Skills panel
- Tools are only shown after they've been called during execution
