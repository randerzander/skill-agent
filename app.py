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
from agent import AgentSkillsFramework
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

# Session management - store state per session ID
sessions = {}  # session_id -> session_state
sessions_lock = threading.Lock()

# Session cleanup - remove sessions older than 1 hour
SESSION_TIMEOUT = 3600  # 1 hour in seconds

def cleanup_old_sessions():
    """Remove sessions that haven't been active for SESSION_TIMEOUT seconds"""
    with sessions_lock:
        current_time = time.time()
        expired_sessions = []
        for session_id, session_state in sessions.items():
            if session_state.get('start_time'):
                age = current_time - session_state['start_time']
                if age > SESSION_TIMEOUT:
                    expired_sessions.append(session_id)
        
        for session_id in expired_sessions:
            del sessions[session_id]
            print(f"Cleaned up expired session: {session_id}")
        
        if expired_sessions:
            print(f"Removed {len(expired_sessions)} expired session(s)")

# Run cleanup periodically in background
def session_cleanup_thread():
    while True:
        time.sleep(600)  # Run every 10 minutes
        cleanup_old_sessions()

threading.Thread(target=session_cleanup_thread, daemon=True).start()


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
    
    def __init__(self, agent_framework, event_queue=None, persist_event=None):
        self.agent = agent_framework
        self.events = []
        self.start_time = None
        self.event_queue = event_queue  # Queue for real-time streaming
        self.persist_event = persist_event
        
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
            
            # Check for errors at multiple levels
            is_error = False
            if isinstance(result, dict):
                if 'error' in result:
                    is_error = True
                elif 'result' in result:
                    nested = result['result']
                    if isinstance(nested, dict) and 'error' in nested:
                        is_error = True
                    elif isinstance(nested, str):
                        # Try parsing JSON string
                        try:
                            import json as json_module
                            parsed = json_module.loads(nested)
                            if isinstance(parsed, dict) and 'error' in parsed:
                                is_error = True
                        except:
                            # Check for error keywords in string
                            if 'error' in nested.lower() or 'failed' in nested.lower():
                                is_error = True
            
            script = log_entry.get('script', '') if isinstance(log_entry, dict) else ''
            
            self.add_event('tool_result', {
                'tool_name': script,
                'result': result,
                'error': is_error
            }, elapsed)
            
            # Check for task creation
            # Result is nested: result.result contains the actual JSON string
            if script in ['create_task', 'create_subquestion_task', 'create_subquestion_tasks'] and isinstance(result, dict):
                actual_result = result.get('result', '')
                if isinstance(actual_result, str):
                    try:
                        result_data = json.loads(actual_result)
                        if result_data.get('status') == 'success':
                            # Handle new format with multiple tasks
                            if 'tasks' in result_data:
                                for task in result_data.get('tasks', []):
                                    task_status = 'active' if task.get('task_number') == 1 else 'incomplete'
                                    self.add_event('task_created', {
                                        'task_number': task.get('task_number'),
                                        'description': task.get('description'),
                                        'status': task_status
                                    }, elapsed)
                            # Handle old format with single task
                            elif 'task_number' in result_data:
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
            new_files = log_entry.get('new_files', []) if isinstance(log_entry, dict) else []
            
            # Filter to only include image files
            image_extensions = {'.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp'}
            image_files = [
                f for f in new_files 
                if any(f.get('path', '').lower().endswith(ext) for ext in image_extensions)
            ]
            
            self.add_event('final_response', {
                'content': content,
                'new_files': image_files
            }, elapsed)
        
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
        if self.persist_event:
            self.persist_event(event)
        
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
            response = self.agent.run(user_input)  # Will use config value
            
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
    
    # Get or create session ID
    session_id = request.json.get('session_id', None)
    if not session_id:
        # Return error if no session ID provided - client should always provide one
        return jsonify({'error': 'No session_id provided. Client must generate and provide a session ID.'}), 400
    
    client_ip = get_client_ip()
    pid = os.getpid()
    print(f"[{client_ip}] User query: {user_input} (session: {session_id}, pid: {pid})")
    
    # Initialize session state
    with sessions_lock:
        if session_id not in sessions:
            sessions[session_id] = {
                'running': False,
                'logs': [],
                'chat_history': [],
                'tools_called': [],
                'start_time': None,
                'elapsed_time': 0,
                'completed': False
            }
        session_state = sessions[session_id]
        
        if session_state['running']:
            print(f"[{client_ip}] Reject run: session already running (session: {session_id}, pid: {pid})")
            return jsonify({'error': 'Agent is already running for this session'}), 400
        session_state['running'] = True
        session_state['start_time'] = time.time()
        session_state['logs'] = []
        session_state['chat_history'] = []
        session_state['tools_called'] = []
        session_state['completed'] = False
        print(
            f"[{client_ip}] Session started (session: {session_id}, pid: {pid}, "
            f"start_time: {session_state['start_time']})"
        )
    
    # Also update global state for backward compatibility
    with state_lock:
        agent_state['running'] = True
        agent_state['start_time'] = session_state['start_time']
        agent_state['logs'] = []
        agent_state['chat_history'] = []
        agent_state['tools_called'] = []

    def apply_event_to_state(target_state, event):
        target_state['elapsed_time'] = event['elapsed']
        target_state['logs'].append(event)

        if event['type'] == 'user_message':
            target_state['chat_history'].append({
                'role': 'user',
                'content': event['data']['content'],
                'timestamp': event['timestamp']
            })
        elif event['type'] == 'llm_response':
            target_state['chat_history'].append({
                'role': 'assistant',
                'content': event['data']['content'],
                'thinking': event['data'].get('thinking'),
                'tool_calls': event['data'].get('tool_calls', []),
                'timestamp': event['timestamp']
            })
        elif event['type'] == 'tool_call':
            target_state['tools_called'].append(event['data'])
        elif event['type'] == 'tool_result':
            target_state['chat_history'].append({
                'role': 'tool',
                'content': json.dumps(event['data']['result']),
                'tool_name': event['data']['tool_name'],
                'timestamp': event['timestamp']
            })

    def update_state_from_event(event):
        """Persist event to session state and global agent state"""
        with sessions_lock:
            apply_event_to_state(session_state, event)

        with state_lock:
            apply_event_to_state(agent_state, event)
    
    def generate():
        """Generate SSE events for the agent execution"""
        event_queue = queue.Queue()
        wrapper = WebAgentWrapper(
            agent,
            event_queue=event_queue,
            persist_event=update_state_from_event
        )
        
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
                with sessions_lock:
                    session_state['running'] = False
                    session_state['completed'] = True
                    print(
                        f"[{client_ip}] Session run ended (session: {session_id}, pid: {pid}, "
                        f"completed: {session_state.get('completed')}, "
                        f"log_count: {len(session_state.get('logs', []))})"
                    )
                with state_lock:
                    agent_state['running'] = False
                agent_done.set()
        
        agent_thread = threading.Thread(target=run_agent_thread)
        agent_thread.start()
        
        try:
            # Stream events as they come from the queue
            while not agent_done.is_set() or not event_queue.empty():
                try:
                    # Wait for event with timeout so we can check if agent is done
                    event = event_queue.get(timeout=0.1)
                    
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
    
    return Response(stream_with_context(generate()), mimetype='text/event-stream')


@app.route('/api/reconnect', methods=['POST'])
def reconnect_session():
    """Reconnect to an existing session and get missed events"""
    session_id = request.json.get('session_id', None)
    last_event_index = request.json.get('last_event_index', -1)
    
    if not session_id:
        return jsonify({'error': 'No session_id provided'}), 400
    
    with sessions_lock:
        if session_id not in sessions:
            return jsonify({'error': 'Session not found'}), 404
        
        session_state = sessions[session_id]
        log_count = len(session_state.get('logs', []))
        is_running = session_state.get('running')
        is_completed = session_state.get('completed')
        
        # Copy missed events outside the lock to avoid blocking
        missed_events = session_state['logs'][last_event_index + 1:]

    client_ip = get_client_ip()
    pid = os.getpid()
    print(
        f"[{client_ip}] Reconnect requested (session: {session_id}, "
        f"last_event_index: {last_event_index}, "
        f"running: {is_running}, completed: {is_completed}, log_count: {log_count}, pid: {pid})"
    )
        
    def generate():
        """Generate SSE events for reconnection and keep streaming if still running"""
        current_index = last_event_index

        # Send any missed events first
        for event in missed_events:
            current_index += 1
            yield f"data: {json.dumps(event)}\n\n"

        while True:
            with sessions_lock:
                current_state = sessions.get(session_id)
                if current_state is None:
                    break
                logs = list(current_state.get('logs', []))
                still_running = current_state.get('running')
                now_completed = current_state.get('completed')

            # Send any new events since the last index
            while current_index + 1 < len(logs):
                current_index += 1
                yield f"data: {json.dumps(logs[current_index])}\n\n"

            # If session is completed and no more events, send completion event and stop
            if now_completed and current_index + 1 >= len(logs):
                yield f"data: {json.dumps({'type': 'complete', 'response': 'Session resumed'})}\n\n"
                break

            # If not running and not completed, stop streaming
            if not still_running and not now_completed:
                break

            time.sleep(0.2)
    
    return Response(stream_with_context(generate()), mimetype='text/event-stream')


@app.route('/api/session_status', methods=['POST'])
def get_session_status():
    """Check if a session exists and get its status"""
    session_id = request.json.get('session_id', None)
    
    if not session_id:
        return jsonify({'error': 'No session_id provided'}), 400
    
    client_ip = get_client_ip()
    pid = os.getpid()

    with sessions_lock:
        if session_id not in sessions:
            print(f"[{client_ip}] Session status: not found (session: {session_id}, pid: {pid})")
            return jsonify({'exists': False}), 200
        
        session_state = sessions[session_id]
        print(
            f"[{client_ip}] Session status (session: {session_id}, pid: {pid}, "
            f"running: {session_state.get('running')}, completed: {session_state.get('completed')}, "
            f"log_count: {len(session_state.get('logs', []))}, "
            f"start_time: {session_state.get('start_time')}, "
            f"elapsed_time: {session_state.get('elapsed_time')})"
        )
        return jsonify({
            'exists': True,
            'running': session_state['running'],
            'completed': session_state['completed'],
            'event_count': len(session_state['logs']),
            'elapsed_time': session_state['elapsed_time']
        })


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


@app.route('/health')
def health():
    """Health check endpoint for keepalive monitoring"""
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'uptime': time.time() - agent_state.get('start_time', time.time()) if agent_state.get('start_time') else 0
    }), 200


@app.route('/scratch/<path:filename>')
def serve_scratch_file(filename):
    """Serve files from scratch directory (for image display)"""
    from flask import send_from_directory
    from pathlib import Path
    
    scratch_dir = Path.cwd() / 'scratch'
    file_path = scratch_dir / filename
    
    print(f"[Scratch] Serving file: {filename}")
    print(f"[Scratch] Full path: {file_path}")
    print(f"[Scratch] Exists: {file_path.exists()}")
    
    if not file_path.exists():
        return jsonify({'error': 'File not found'}), 404
    
    return send_from_directory(scratch_dir, filename)


if __name__ == '__main__':
    # Initialize agent on startup
    init_agent()
    
    # Start keepalive background task
    start_keepalive_thread()
    
    # Run the app
    port = int(os.getenv('PORT', 10000))
    debug = os.getenv('FLASK_DEBUG', 'false').lower() == 'true'
    app.run(host='0.0.0.0', port=port, debug=debug, threaded=True)
