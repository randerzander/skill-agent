#!/usr/bin/env python3
"""
Web frontend for Agent Skills Framework using Flask and HTMX
"""
import os
import json
import time
import threading
import queue
from datetime import datetime
from flask import Flask, render_template, request, jsonify, Response, stream_with_context
from agent import AgentSkillsFramework, SkillLoader
from dotenv import load_dotenv
from keepalive import start_keepalive_thread

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


def get_client_ip():
    """Get the real client IP address from X-Forwarded-For header or remote_addr"""
    if request.headers.get('X-Forwarded-For'):
        # X-Forwarded-For can contain multiple IPs, use the first one (original client)
        return request.headers.get('X-Forwarded-For').split(',')[0].strip()
    return request.remote_addr


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
    
    def __init__(self, agent_framework, event_queue=None):
        self.agent = agent_framework
        self.events = []
        self.start_time = None
        self.event_queue = event_queue  # Queue for real-time streaming
        
    def event_callback(self, event_type_or_entry, data=None):
        """Callback for real-time events from the agent"""
        # Skip invalid types
        if isinstance(event_type_or_entry, list):
            return
        if not isinstance(event_type_or_entry, (str, dict)):
            return
            
        elapsed = time.time() - self.start_time if self.start_time else 0
        
        # Handle both signatures
        if data is None and isinstance(event_type_or_entry, dict):
            # Old signature: single log_entry dict
            log_entry = event_type_or_entry
            event_type = log_entry.get('type')
        else:
            # New signature: event_type and data
            event_type = event_type_or_entry
            log_entry = {
                'type': event_type,
                'data': data if data else {},
                'timestamp': datetime.now().isoformat()
            }
        
        # Convert agent log entries to web UI events
        if not event_type:
            return
        
        if event_type == 'user_input':
            content = log_entry.get('content') if isinstance(log_entry, dict) else ''
            self.add_event('user_message', {'content': content}, elapsed)
        elif event_type == 'skill_activated':
            # Skill activation completed successfully
            # Handle both old format (skill_name in log_entry) and new format (in data dict)
            if 'data' in log_entry and isinstance(log_entry['data'], dict):
                skill_name = log_entry['data'].get('skill_name', '')
                tools_count = log_entry['data'].get('tools_count', 0)
            else:
                skill_name = log_entry.get('skill_name', '')
                tools_count = log_entry.get('tools_count', 0)
            self.add_event('skill_activated', {
                'skill_name': skill_name,
                'tools_count': tools_count
            }, elapsed)
        elif event_type == 'skill_deactivated':
            # Skill deactivated
            skill_name = log_entry.get('skill_name') if isinstance(log_entry, dict) else ''
            self.add_event('skill_deactivated', {
                'skill_name': skill_name
            }, elapsed)
        elif event_type == 'skill_activation_failed':
            # Skill activation failed
            skill_name = log_entry.get('skill_name') if isinstance(log_entry, dict) else ''
            self.add_event('skill_activation_failed', {
                'skill_name': skill_name
            }, elapsed)
        elif event_type == 'reasoning_trace':
            # Just store it, don't process
            if isinstance(log_entry, dict) and isinstance(log_entry.get('data'), dict):
                trace = log_entry['data'].get('trace', '')
                if trace:
                    self.add_event('reasoning', {'content': trace}, elapsed)
        elif event_type == 'llm_response':
            tool_calls = log_entry.get('tool_calls', []) if isinstance(log_entry, dict) else []
            
            # Check for skill activations and tool calls
            for tc in tool_calls:
                if not isinstance(tc, dict):
                    continue
                func_name = tc.get('function')
                if func_name and func_name.startswith('activate_'):
                    skill_name = func_name.replace('activate_', '')
                    self.add_event('skill_activation', {'skill_name': skill_name}, elapsed)
                elif func_name:
                    self.add_event('tool_call', {
                        'tool_name': func_name,
                        'arguments': tc.get('arguments', {})
                    }, elapsed)
            
            # Include reasoning traces if present
            content = log_entry.get('content', '') if isinstance(log_entry, dict) else ''
            response_data = {
                'content': content,
                'tool_calls': tool_calls
            }
            if isinstance(log_entry, dict) and 'reasoning' in log_entry:
                response_data['reasoning'] = log_entry['reasoning']
            
            self.add_event('llm_response', response_data, elapsed)
        elif event_type == 'tool_execution':
            # Tool execution result
            result = log_entry.get('result', {}) if isinstance(log_entry, dict) else {}
            is_error = 'error' in result if isinstance(result, dict) else False
            script = log_entry.get('script', '') if isinstance(log_entry, dict) else ''
            
            self.add_event('tool_result', {
                'tool_name': script,
                'result': result,
                'error': is_error
            }, elapsed)
            
            # Check for task creation
            # Result is nested: result.result contains the actual JSON string
            if script in ['create_task', 'create_subquestion_task'] and isinstance(result, dict):
                actual_result = result.get('result', '')
                if isinstance(actual_result, str):
                    try:
                        result_data = json.loads(actual_result)
                        if result_data.get('status') == 'success':
                            task_status = 'active' if result_data.get('is_active') else 'incomplete'
                            self.add_event('task_created', {
                                'task_number': result_data.get('task_number'),
                                'description': result_data.get('description'),
                                'status': task_status
                            }, elapsed)
                    except:
                        pass
                    
        elif event_type == 'task_completed':
            # Task marked as complete
            task_number = log_entry.get('task_number') if isinstance(log_entry, dict) else None
            if task_number:
                self.add_event('task_completed', {'task_number': task_number}, elapsed)
        elif event_type == 'task_activated':
            # Task auto-activated
            task_number = log_entry.get('task_number') if isinstance(log_entry, dict) else None
            if task_number:
                self.add_event('task_activated', {'task_number': task_number}, elapsed)
        elif event_type == 'final_response':
            content = log_entry.get('content', '') if isinstance(log_entry, dict) else ''
            self.add_event('final_response', {'content': content}, elapsed)
        
    def add_event(self, event_type, data, elapsed):
        """Add an event to the events list and optionally to queue for streaming"""
        event_timestamp = datetime.fromtimestamp(self.start_time + elapsed)
        
        event = {
            'type': event_type,
            'data': data,
            'timestamp': event_timestamp.isoformat(),
            'elapsed': elapsed
        }
        
        self.events.append(event)
        
        # If we have a queue, push event for real-time streaming
        if self.event_queue is not None:
            self.event_queue.put(event)
    
    def run(self, user_input):
        """Run the agent with event tracking - delegates to AgentSkillsFramework"""
        self.start_time = time.time()
        self.events = []
        
        # Register callback with agent
        self.agent.event_callback = self.event_callback
        
        # Don't manually add user_message - agent's _log_message will do it
        
        # Use the agent's run method which has all the correct logic
        try:
            response = self.agent.run(user_input, max_iterations=15)
            
            # Don't manually add final_response - agent's _log_message handles it
            
            return response, self.events
        except Exception as e:
            error_msg = f"Error: {str(e)}"
            elapsed = time.time() - self.start_time
            self.add_event('error', {'message': error_msg}, elapsed)
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
    
    client_ip = get_client_ip()
    print(f"[{client_ip}] User query: {user_input}")
    
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
        event_queue = queue.Queue()
        wrapper = WebAgentWrapper(agent, event_queue=event_queue)
        
        # Run agent in background thread
        agent_done = threading.Event()
        agent_error = None
        agent_response = None
        
        def run_agent_thread():
            nonlocal agent_response, agent_error
            try:
                agent_response, _ = wrapper.run(user_input)
            except Exception as e:
                agent_error = e
            finally:
                agent_done.set()
        
        agent_thread = threading.Thread(target=run_agent_thread)
        agent_thread.start()
        
        try:
            # Stream events as they come from the queue
            while not agent_done.is_set() or not event_queue.empty():
                try:
                    # Wait for event with timeout so we can check if agent is done
                    event = event_queue.get(timeout=0.1)
                    
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
                    
                except queue.Empty:
                    # No events available, continue waiting
                    continue
            
            # Wait for agent thread to finish
            agent_thread.join()
            
            # Check for errors
            if agent_error:
                yield f"data: {json.dumps({'type': 'error', 'message': str(agent_error)})}\n\n"
            else:
                # Send completion event
                yield f"data: {json.dumps({'type': 'complete', 'response': agent_response})}\n\n"
            
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
        finally:
            with state_lock:
                agent_state['running'] = False
    
    return Response(stream_with_context(generate()), mimetype='text/event-stream')


@app.route('/api/chat_history')
def get_chat_history():
    """Get the full chat history with reasoning traces injected"""
    with state_lock:
        messages_with_thinking = []
        if agent and agent.messages:
            for idx, msg in enumerate(agent.messages):
                msg_copy = dict(msg)
                # Inject thinking trace if available for this message
                if idx in agent.reasoning_traces:
                    msg_copy['thinking'] = agent.reasoning_traces[idx]
                messages_with_thinking.append(msg_copy)
        
        return jsonify({
            'history': agent_state['chat_history'],
            'messages': messages_with_thinking
        })


@app.route('/api/tools_called')
def get_tools_called():
    """Get the list of tools called"""
    with state_lock:
        return jsonify({'tools': agent_state['tools_called']})


@app.route('/health')
def health():
    """Health check endpoint for keepalive monitoring"""
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'uptime': time.time() - agent_state.get('start_time', time.time()) if agent_state.get('start_time') else 0
    }), 200


if __name__ == '__main__':
    # Initialize agent on startup
    init_agent()
    
    # Start keepalive background task
    start_keepalive_thread()
    
    # Run the app
    port = int(os.getenv('PORT', 10000))
    debug = os.getenv('FLASK_DEBUG', 'false').lower() == 'true'
    app.run(host='0.0.0.0', port=port, debug=debug, threaded=True)
