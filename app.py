#!/usr/bin/env python3
"""
Web frontend for Agent Skills Framework using Flask and HTMX
"""
import os
import json
import time
import threading
from datetime import datetime
from flask import Flask, render_template, request, jsonify, Response, stream_with_context
from agent import AgentSkillsFramework, SkillLoader
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

app = Flask(__name__)

# Generate a secure random secret key if not provided in environment
import secrets
default_secret = secrets.token_hex(32)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', default_secret)

# Global agent instance and state
agent = None
agent_state = {
    'running': False,
    'logs': [],
    'chat_history': [],
    'skills_loaded': [],
    'tools_called': [],
    'start_time': None,
    'elapsed_time': 0
}
state_lock = threading.Lock()


def init_agent():
    """Initialize the agent framework"""
    global agent
    try:
        agent = AgentSkillsFramework()
        with state_lock:
            agent_state['skills_loaded'] = [
                {'name': skill['name'], 'description': skill['description']}
                for skill in agent.skill_loader.skills.values()
            ]
        return True
    except Exception as e:
        print(f"Error initializing agent: {e}")
        return False


class WebAgentWrapper:
    """Wrapper around AgentSkillsFramework to capture execution events"""
    
    def __init__(self, agent_framework):
        self.agent = agent_framework
        self.events = []
        self.start_time = None
        
    def add_event(self, event_type, data):
        """Add an event to the events list"""
        self.events.append({
            'type': event_type,
            'data': data,
            'timestamp': datetime.now().isoformat(),
            'elapsed': time.time() - self.start_time if self.start_time else 0
        })
    
    def run(self, user_input):
        """Run the agent with event tracking - delegates to AgentSkillsFramework"""
        self.start_time = time.time()
        self.events = []
        
        # Add user message event
        self.add_event('user_message', {'content': user_input})
        
        # Use the agent's run method which has all the correct logic
        try:
            response = self.agent.run(user_input, max_iterations=10)
            
            # Extract events from the agent's conversation history
            # Track tool calls to match with results
            pending_tool_calls = {}
            
            for msg in self.agent.messages:
                if msg.get('role') == 'assistant':
                    tool_calls_data = []
                    
                    # Process tool calls if present
                    if msg.get('tool_calls'):
                        for tc in msg.get('tool_calls', []):
                            func_name = tc['function']['name']
                            func_args = tc['function']['arguments']
                            
                            tool_calls_data.append({
                                'id': tc['id'],
                                'function': func_name,
                                'arguments': func_args
                            })
                            
                            # Track for matching with tool results
                            pending_tool_calls[tc['id']] = {
                                'function': func_name,
                                'arguments': func_args
                            }
                            
                            # Check if this is a skill activation or tool call
                            if func_name.startswith('activate_'):
                                skill_name = func_name.replace('activate_', '')
                                self.add_event('skill_activation', {
                                    'skill_name': skill_name
                                })
                            else:
                                # This is a tool execution
                                try:
                                    args = json.loads(func_args) if isinstance(func_args, str) else func_args
                                except:
                                    args = {}
                                    
                                self.add_event('tool_call', {
                                    'tool_name': func_name,
                                    'arguments': args
                                })
                    
                    self.add_event('llm_response', {
                        'content': msg.get('content'),
                        'thinking': None,
                        'tool_calls': tool_calls_data
                    })
                    
                elif msg.get('role') == 'tool':
                    # Parse tool result
                    tool_call_id = msg.get('tool_call_id')
                    content = msg.get('content', '{}')
                    
                    try:
                        result = json.loads(content)
                    except:
                        result = {'content': content}
                    
                    # Match with pending tool call
                    tool_info = pending_tool_calls.get(tool_call_id, {})
                    
                    self.add_event('tool_result', {
                        'tool_name': tool_info.get('function', 'unknown'),
                        'result': result
                    })
            
            # Add final response event
            self.add_event('final_response', {'content': response})
            
            return response, self.events
        except Exception as e:
            error_msg = f"Error: {str(e)}"
            self.add_event('error', {'message': error_msg})
            return error_msg, self.events


@app.route('/')
def index():
    """Main page"""
    return render_template('index.html')


@app.route('/api/status')
def status():
    """Get current status"""
    with state_lock:
        return jsonify({
            'running': agent_state['running'],
            'elapsed_time': agent_state['elapsed_time'],
            'skills_loaded': agent_state['skills_loaded']
        })


@app.route('/api/run', methods=['POST'])
def run_agent():
    """Run the agent with user input"""
    global agent
    
    if not agent:
        if not init_agent():
            return jsonify({'error': 'Failed to initialize agent. Check OPENROUTER_API_KEY.'}), 500
    
    user_input = request.json.get('input', '').strip()
    if not user_input:
        return jsonify({'error': 'No input provided'}), 400
    
    with state_lock:
        if agent_state['running']:
            return jsonify({'error': 'Agent is already running'}), 400
        agent_state['running'] = True
        agent_state['start_time'] = time.time()
        agent_state['logs'] = []
        agent_state['chat_history'] = []
        agent_state['tools_called'] = []
    
    def generate():
        """Generate SSE events for the agent execution"""
        wrapper = WebAgentWrapper(agent)
        
        try:
            # Send initial event
            yield f"data: {json.dumps({'type': 'start', 'input': user_input})}\n\n"
            
            # Run agent
            response, events = wrapper.run(user_input)
            
            # Send all events
            for event in events:
                with state_lock:
                    agent_state['elapsed_time'] = event['elapsed']
                    agent_state['logs'].append(event)
                    
                    # Update chat history
                    if event['type'] == 'user_message':
                        agent_state['chat_history'].append({
                            'role': 'user',
                            'content': event['data']['content'],
                            'timestamp': event['timestamp']
                        })
                    elif event['type'] == 'llm_response':
                        agent_state['chat_history'].append({
                            'role': 'assistant',
                            'content': event['data']['content'],
                            'thinking': event['data'].get('thinking'),
                            'tool_calls': event['data'].get('tool_calls', []),
                            'timestamp': event['timestamp']
                        })
                    elif event['type'] == 'tool_call':
                        agent_state['tools_called'].append(event['data'])
                    elif event['type'] == 'tool_result':
                        agent_state['chat_history'].append({
                            'role': 'tool',
                            'content': json.dumps(event['data']['result']),
                            'tool_name': event['data']['tool_name'],
                            'timestamp': event['timestamp']
                        })
                
                yield f"data: {json.dumps(event)}\n\n"
            
            # Send completion event
            yield f"data: {json.dumps({'type': 'complete', 'response': response})}\n\n"
            
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
        finally:
            with state_lock:
                agent_state['running'] = False
    
    return Response(stream_with_context(generate()), mimetype='text/event-stream')


@app.route('/api/chat_history')
def get_chat_history():
    """Get the full chat history"""
    with state_lock:
        return jsonify({
            'history': agent_state['chat_history'],
            'messages': agent.messages if agent else []
        })


@app.route('/api/tools_called')
def get_tools_called():
    """Get the list of tools called"""
    with state_lock:
        return jsonify({'tools': agent_state['tools_called']})


if __name__ == '__main__':
    # Initialize agent on startup
    init_agent()
    
    # Run the app
    port = int(os.getenv('PORT', 10000))
    debug = os.getenv('FLASK_DEBUG', 'false').lower() == 'true'
    app.run(host='0.0.0.0', port=port, debug=debug, threaded=True)
