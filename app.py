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
        """Run the agent with event tracking"""
        self.start_time = time.time()
        self.events = []
        
        # Add user message event
        self.add_event('user_message', {'content': user_input})
        
        # Add user message to agent history
        self.agent.messages.append({"role": "user", "content": user_input})
        
        # Track active skill and tools
        active_skill = None
        active_tools = []
        
        iteration = 0
        max_iterations = 10
        
        while iteration < max_iterations:
            iteration += 1
            
            # Prepare tools based on active skill
            if active_skill:
                tools = active_tools
            else:
                tools = [self.agent.activate_skill_tool]
            
            try:
                # Add LLM call start event
                self.add_event('llm_call_start', {
                    'model': self.agent.model,
                    'iteration': iteration
                })
                
                # Make LLM call
                response = self.agent.client.chat.completions.create(
                    model=self.agent.model,
                    messages=self.agent.messages,
                    tools=tools
                )
                
                message = response.choices[0].message
                
                # Extract thinking/reasoning if available (for models that support it)
                thinking = None
                try:
                    if hasattr(message, 'reasoning_content') and message.reasoning_content:
                        thinking = message.reasoning_content
                    elif hasattr(message, 'thinking') and message.thinking:
                        thinking = message.thinking
                except Exception:
                    # Silently ignore if thinking extraction fails
                    pass
                
                # Add LLM response event
                self.add_event('llm_response', {
                    'content': message.content,
                    'thinking': thinking,
                    'tool_calls': [
                        {
                            'id': tc.id,
                            'function': tc.function.name,
                            'arguments': tc.function.arguments
                        }
                        for tc in (message.tool_calls or [])
                    ]
                })
                
                # Check if LLM wants to call a tool
                if message.tool_calls:
                    # Add assistant message with tool calls to history
                    self.agent.messages.append({
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
                    })
                    
                    # Execute each tool call
                    for tool_call in message.tool_calls:
                        function_name = tool_call.function.name
                        function_args = json.loads(tool_call.function.arguments)
                        
                        # Check if this is a skill activation request
                        if function_name == "activate_skill":
                            skill_name = function_args.get("skill_name")
                            
                            self.add_event('skill_activation', {
                                'skill_name': skill_name
                            })
                            
                            if skill_name in self.agent.skill_loader.skills:
                                # Activate the skill
                                skill_content = self.agent.skill_loader.activate_skill(skill_name)
                                active_skill = skill_name
                                active_tools = self.agent.skill_loader.get_skill_tools(skill_name)
                                
                                # Add tool response confirming activation
                                activation_msg = f"Skill '{skill_name}' activated successfully.\n\nFull skill instructions:\n{skill_content}\n\nYou now have access to tools from this skill."
                                self.agent.messages.append({
                                    "role": "tool",
                                    "tool_call_id": tool_call.id,
                                    "content": activation_msg
                                })
                                
                                self.add_event('skill_activated', {
                                    'skill_name': skill_name,
                                    'tools_count': len(active_tools)
                                })
                            else:
                                # Skill not found
                                self.agent.messages.append({
                                    "role": "tool",
                                    "tool_call_id": tool_call.id,
                                    "content": f"Error: Skill '{skill_name}' not found."
                                })
                                
                                self.add_event('skill_activation_failed', {
                                    'skill_name': skill_name
                                })
                        else:
                            # This is a skill script execution
                            if active_skill:
                                script_name = function_name
                                
                                self.add_event('tool_call', {
                                    'tool_name': script_name,
                                    'skill': active_skill,
                                    'arguments': function_args
                                })
                                
                                # Execute the script
                                result = self.agent.skill_loader.execute_skill_script(
                                    active_skill,
                                    script_name,
                                    function_args.get("params", {})
                                )
                                
                                # Add tool response to messages
                                self.agent.messages.append({
                                    "role": "tool",
                                    "tool_call_id": tool_call.id,
                                    "content": json.dumps(result)
                                })
                                
                                self.add_event('tool_result', {
                                    'tool_name': script_name,
                                    'result': result
                                })
                    
                    # Continue to next iteration
                    continue
                
                # No tool calls - return the response
                final_response = message.content if message.content else "I've completed the task."
                self.add_event('final_response', {'content': final_response})
                return final_response, self.events
                    
            except Exception as e:
                self.add_event('error', {'message': str(e)})
                return f"Error: {str(e)}", self.events
        
        self.add_event('max_iterations', {})
        return "Maximum iterations reached. Unable to complete the request.", self.events


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
