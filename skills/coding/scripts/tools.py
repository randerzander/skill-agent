#!/usr/bin/env python3
"""
Coding skill tools - write and execute Python code
Uses coding model from config.yaml
"""
import os
import sys
from pathlib import Path
from dotenv import load_dotenv
from rich.console import Console
from rich.live import Live
from rich.text import Text
from openai import OpenAI

load_dotenv()

console = Console()

# Add parent directory to path to import utils
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
from utils import load_config, get_scratch_dir, detect_new_files, sanitize_filename


def generate_code(task_description: str, context: str = "") -> str:
    """
    Generate Python code using Qwen coding model, save it, execute it, and return results.
    This is a single-step tool that handles code generation, saving, and execution.
    
    Args:
        task_description: Description of what the code should do
        context: Optional additional context (available files, data structure, etc.)
    
    Returns:
        JSON string with execution results
    """
    import json
    import time
    import subprocess
    
    try:
        config = load_config()
        
        # Get coding model from config
        coding_model = config.get('coding', {}).get('model', 'qwen/qwen3-coder:free')
        
        # Auto-detect base URL based on model
        # If base_url is explicitly set in config, use it
        # Otherwise, detect from model name
        base_url = config.get('coding', {}).get('base_url')
        api_key = os.getenv('OPENROUTER_API_KEY')
        
        if not base_url:
            # Auto-detect based on model name
            if coding_model.startswith('qwen3-') or coding_model.startswith('qwen-coder-'):
                # Qwen direct API (requires qwen CLI auth)
                base_url = 'https://portal.qwen.ai/v1'
                # Use qwen_llm for OAuth-based models
                from qwen_llm import qwen_chat
                use_qwen_llm = True
            else:
                # OpenRouter for all other models (including qwen/qwen3-coder:free)
                base_url = 'https://openrouter.ai/api/v1'
                use_qwen_llm = False
        else:
            # base_url was explicitly configured
            use_qwen_llm = 'portal.qwen.ai' in base_url
        
        prompt = f"""Write Python code to {task_description}.

{context}

Requirements:
- Use relative paths starting with 'scratch/' to read data files
- Print results to stdout
- Use only standard library or commonly available packages (json, pathlib, etc.)
- Include error handling
- Keep it simple and focused

Output only the Python code, no explanations."""

        # Retry with exponential backoff for rate limits
        max_retries = 3
        retry_delay = 2
        
        for attempt in range(max_retries):
            try:
                # Create spinner display
                spinner_frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
                frame_idx = 0
                
                with Live(console=console, refresh_per_second=10, transient=False) as live:
                    # Step 1: Generate code
                    live.update(Text(f"{spinner_frames[frame_idx % len(spinner_frames)]} Generating code...", style="cyan"))
                    gen_start = time.time()
                    
                    # Use appropriate API based on detection
                    if use_qwen_llm:
                        from qwen_llm import qwen_chat
                        code, usage = qwen_chat(
                            prompt=prompt,
                            model=coding_model,
                            base_url=base_url,
                            temperature=0.2
                        )
                    else:
                        # Use OpenAI client for OpenRouter
                        client = OpenAI(
                            base_url=base_url,
                            api_key=api_key
                        )
                        response = client.chat.completions.create(
                            model=coding_model,
                            messages=[{"role": "user", "content": prompt}],
                            temperature=0.2
                        )
                        code = response.choices[0].message.content
                        usage = None
                        if hasattr(response, 'usage') and response.usage:
                            usage = {
                                'prompt_tokens': response.usage.prompt_tokens,
                                'completion_tokens': response.usage.completion_tokens,
                                'total_tokens': response.usage.total_tokens
                            }
                    
                    gen_time = time.time() - gen_start
                    
                    # Extract code from markdown if present
                    if "```python" in code:
                        code = code.split("```python")[1].split("```")[0].strip()
                    elif "```" in code:
                        code = code.split("```")[1].split("```")[0].strip()
                    
                    # Generate filename using base LLM for a meaningful name
                    filename = _generate_script_filename(task_description, config)
                    
                    # Save code to scratch/code/
                    scratch_dir = get_scratch_dir()
                    code_dir = scratch_dir / "code"
                    code_dir.mkdir(parents=True, exist_ok=True)

                    filename = _ensure_unique_filename(code_dir, filename)
                    code_file = code_dir / filename
                    with open(code_file, 'w') as f:
                        f.write(code)
                    
                    # Step 2: Execute code
                    frame_idx += 1
                    live.update(Text(f"{spinner_frames[frame_idx % len(spinner_frames)]} Executing {filename}...", style="cyan"))
                    exec_start = time.time()
                    
                    result = subprocess.run(
                        [sys.executable, str(code_file)],
                        capture_output=True,
                        text=True,
                        timeout=30,
                        cwd=Path.cwd()
                    )
                    exec_time = time.time() - exec_start
                    
                    # Combine stdout and stderr
                    output = result.stdout
                    if result.stderr:
                        output += "\n[STDERR]\n" + result.stderr
                    
                    # Auto-truncate large output to prevent context overflow
                    max_output_chars = 4000
                    truncated = False
                    original_output_len = len(output)
                    if len(output) > max_output_chars:
                        output = output[:max_output_chars] + "\n\n[OUTPUT TRUNCATED - exceeded 4000 characters]\n\nWARNING: The code generated excessive output. When creating the task description, be more explicit about limiting output (e.g., 'print only a summary', 'show first 10 items', 'save to file instead of printing')."
                        truncated = True
                    
                    # Detect new files created during execution
                    new_files = detect_new_files(
                        exec_start,
                        scratch_dir,
                        skip_internal=False,
                        skip_tasks=False,
                        skip_code_py=False
                    )
                    
                    # Build summary with model, timing, and task description
                    summary = Text()
                    summary.append("✓", style="green bold")
                    summary.append(f" coding.generate_code ", style="bold")
                    summary.append(f"[{coding_model}] ", style="cyan")
                    summary.append(f"gen {gen_time:.1f}s + exec {exec_time:.1f}s = {gen_time + exec_time:.1f}s", style="dim")
                    
                    # Add task description preview
                    task_preview = task_description[:50] + "..." if len(task_description) > 50 else task_description
                    summary.append(f" '{task_preview}'", style="dim")
                    
                    if result.returncode != 0:
                        summary.append(f" [exit {result.returncode}]", style="red")
                    if truncated:
                        summary.append(f" [truncated: {original_output_len:,}→{max_output_chars:,} chars]", style="yellow")
                    if new_files:
                        summary.append(f" [{len(new_files)} file(s)]", style="green")
                    
                    live.update(summary)

                    # Emit extra console detail on failures
                    if result.returncode != 0:
                        error_text = result.stderr.strip() if result.stderr else result.stdout.strip()
                        if error_text:
                            max_len = 600
                            tail = error_text[-max_len:]
                            if len(error_text) > max_len:
                                tail = "…" + tail
                            console.print(f"[red]generate_code error tail:[/red] {tail}")
                
                # Build result
                result_data = {
                    "result": {
                        "status": "success" if result.returncode == 0 else "error",
                        "output": output,
                        "exit_code": result.returncode,
                        "code_file": str(code_file),
                        "new_files": new_files,
                        "model_used": coding_model,
                        "output_truncated": truncated
                    }
                }
                
                # Add usage info if available
                if usage:
                    result_data["result"]["usage"] = usage
                
                return json.dumps(result_data)
                
            except subprocess.TimeoutExpired:
                # Show timeout error in final status
                error_text = Text()
                error_text.append("✗", style="red bold")
                error_text.append(f" Code execution timed out after 30s", style="red")
                error_text.append(f" [gen {gen_time:.1f}s]", style="dim")
                console.print(error_text)
                
                return json.dumps({
                    "error": "Code execution timed out after 30 seconds. The generated code is taking too long to run. Simplify the task or add explicit limits (e.g., 'process only first 100 items').",
                    "code_file": str(code_file) if 'code_file' in locals() else None
                })
                
            except Exception as api_error:
                # Check if it's a rate limit error
                error_str = str(api_error)
                if ('429' in error_str or 'rate' in error_str.lower()) and attempt < max_retries - 1:
                    # Wait with exponential backoff
                    time.sleep(retry_delay)
                    retry_delay *= 2
                    continue
                else:
                    # Not a rate limit or final attempt - raise it
                    raise
        
        return json.dumps({
            "error": "Max retries exceeded for rate limit"
        })
    
    except Exception as e:
        return json.dumps({
            "error": f"Failed to generate and execute code: {str(e)}"
        })


def _generate_script_filename(task_description: str, config: dict) -> str:
    """Use the base LLM to generate a meaningful Python filename."""
    import os
    from openai import OpenAI

    openai_config = config.get('openai', {})
    base_url = openai_config.get('base_url', 'https://openrouter.ai/api/v1')
    model = openai_config.get('model')
    api_key_env = openai_config.get('api_key_env', 'OPENROUTER_API_KEY')
    api_key = os.getenv(api_key_env)

    if not model or not api_key:
        return _fallback_filename(task_description)

    prompt = (
        "Create a short, meaningful Python filename for this task. "
        "Return only the filename without extension. "
        "Use lowercase letters, numbers, and underscores only.\n\n"
        f"Task: {task_description}"
    )

    try:
        client = OpenAI(base_url=base_url, api_key=api_key)
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2
        )
        raw_name = (response.choices[0].message.content or "").strip()
        # Remove code fences or extra lines if present
        if "```" in raw_name:
            raw_name = raw_name.split("```")[1].strip()
        raw_name = raw_name.splitlines()[0].strip()
        if raw_name.lower().endswith(".py"):
            raw_name = raw_name[:-3]

        sanitized = sanitize_filename(raw_name, max_length=60).strip("_")
        if not sanitized:
            return _fallback_filename(task_description)
        return f"{sanitized}.py"
    except Exception:
        return _fallback_filename(task_description)


def _fallback_filename(task_description: str) -> str:
    """Fallback filename if LLM naming fails."""
    base = sanitize_filename(task_description, max_length=40).strip("_")
    if not base:
        base = "generated_script"
    return f"{base}.py"


def _ensure_unique_filename(code_dir: Path, filename: str) -> str:
    """Ensure filename is unique within the code directory."""
    import time
    if not (code_dir / filename).exists():
        return filename

    stem = filename[:-3] if filename.endswith(".py") else filename
    for i in range(1, 1000):
        candidate = f"{stem}_{i}.py"
        if not (code_dir / candidate).exists():
            return candidate

    return f"{stem}_{int(time.time())}.py"

def grep_file(filepath: str, pattern: str, case_sensitive: bool = True, max_results: int = 100) -> str:
    """
    Search for a pattern in a file from the scratch directory.
    Automatically deduplicates if called multiple times in a row.
    
    Args:
        filepath: Path to file relative to project root (e.g., 'scratch/data/models.html')
        pattern: String or regex pattern to search for
        case_sensitive: Whether the search should be case sensitive (default: True)
        max_results: Maximum number of matching lines to return (default: 100)
    
    Returns:
        JSON string with matching lines and line numbers
    """
    import json
    import re
    from utils import get_conversation_history, remove_last_tool_exchange
    
    # Check if the last tool call was also grep_file - if so, remove it to prevent bloat
    history = get_conversation_history()
    if history:
        # Look for the last assistant message with tool calls
        for msg in reversed(history):
            if msg.get("role") == "assistant" and msg.get("tool_calls"):
                for tc in msg.get("tool_calls", []):
                    if tc.get("function", {}).get("name") == "grep_file":
                        # Remove the previous grep call
                        removed = remove_last_tool_exchange(
                            "grep_file",
                            log_message="⚠ Removed previous grep_file call to prevent context bloat"
                        )
                        break
                break
    
    try:
        scratch_dir = get_scratch_dir()
        project_root = Path.cwd()
        
        # Convert to Path object and resolve relative to project root
        file_path = Path(filepath)
        if not file_path.is_absolute():
            file_path = project_root / filepath
        
        # Security check: ensure file is within scratch directory
        try:
            rel_to_scratch = file_path.resolve().relative_to(scratch_dir.resolve())
        except ValueError:
            return json.dumps({
                "error": f"Access denied: file must be within scratch/ directory"
            })
        
        if not file_path.exists():
            return json.dumps({
                "error": f"File not found: {filepath}"
            })
        
        # Compile regex pattern
        flags = 0 if case_sensitive else re.IGNORECASE
        try:
            regex = re.compile(pattern, flags)
        except re.error as e:
            return json.dumps({
                "error": f"Invalid regex pattern: {str(e)}"
            })
        
        # Search file
        matches = []
        total_chars = 0
        max_total_chars = 4000  # Limit total output size
        
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            for line_num, line in enumerate(f, 1):
                if regex.search(line):
                    line_content = line.rstrip('\n\r')
                    
                    # Check if adding this line would exceed our limit
                    if total_chars + len(line_content) > max_total_chars:
                        break
                    
                    matches.append({
                        "line_number": line_num,
                        "content": line_content
                    })
                    total_chars += len(line_content)
                    
                    if len(matches) >= max_results:
                        break
        
        # Check if we hit limits
        hit_char_limit = total_chars >= max_total_chars
        hit_count_limit = len(matches) >= max_results
        
        result = {
            "result": {
                "filepath": str(rel_to_scratch),
                "pattern": pattern,
                "case_sensitive": case_sensitive,
                "matches": matches,
                "match_count": len(matches),
                "truncated": hit_count_limit or hit_char_limit
            }
        }
        
        # Add warning if truncated
        if hit_char_limit:
            result["result"]["warning"] = f"Output truncated at {max_total_chars} characters. Pattern '{pattern}' matched too much data. Use a more specific pattern or generate_code to process the file."
        elif hit_count_limit:
            result["result"]["warning"] = f"Limited to {max_results} matches. Use a more specific pattern to reduce results."
        
        return json.dumps(result)
    
    except Exception as e:
        return json.dumps({
            "error": f"Failed to search file: {str(e)}"
        })
