#!/usr/bin/env python3
"""
Coding skill tools - write and execute Python code
Uses coding model from config.yaml (default: qwen/qwen3-coder:free)
"""
import os
import subprocess
import sys
from pathlib import Path
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

# Add parent directory to path to import utils
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
from utils import load_config, get_scratch_dir


def write_code(filename: str, code: str) -> str:
    """
    Write Python code to a file in scratch/code/ directory.
    Use this BEFORE run_code to create the script file.
    
    Args:
        filename: Name of the Python file (e.g., 'analyze.py')
        code: Complete Python code content to write
    
    Returns:
        JSON string with status and file path
    """
    import json
    
    try:
        # Ensure code directory exists
        scratch_dir = get_scratch_dir()
        code_dir = scratch_dir / "code"
        code_dir.mkdir(parents=True, exist_ok=True)
        
        # Ensure filename ends with .py
        if not filename.endswith('.py'):
            filename = filename + '.py'
        
        # Write code to file
        code_file = code_dir / filename
        with open(code_file, 'w') as f:
            f.write(code)
        
        return json.dumps({
            "result": {
                "status": "success",
                "message": f"Code written to {code_file}",
                "filepath": str(code_file),
                "filename": filename
            }
        })
    
    except Exception as e:
        return json.dumps({
            "error": f"Failed to write code: {str(e)}"
        })


def run_code(filename: str) -> str:
    """
    Execute a previously written Python script from scratch/code/ directory.
    
    IMPORTANT: The file must already exist (created with write_code). 
    This function only accepts a filename, not code content.
    
    Args:
        filename: Name of the Python file to execute (e.g., 'analyze.py')
                 File must exist in scratch/code/ directory
    
    Returns:
        JSON string with execution output, new files created, or error
    """
    import json
    import time
    
    try:
        # Get code file path
        scratch_dir = get_scratch_dir()
        code_dir = scratch_dir / "code"
        
        # Ensure filename ends with .py
        if not filename.endswith('.py'):
            filename = filename + '.py'
        
        code_file = code_dir / filename
        
        if not code_file.exists():
            return json.dumps({
                "error": f"Code file not found: {code_file}"
            })
        
        # Record timestamp before execution to detect new files
        start_time = time.time()
        
        # Execute the Python script
        # Run from project root so scripts can access scratch/ directory
        result = subprocess.run(
            [sys.executable, str(code_file)],
            capture_output=True,
            text=True,
            timeout=30,  # 30 second timeout
            cwd=Path.cwd()  # Run from project root
        )
        
        # Combine stdout and stderr
        output = result.stdout
        if result.stderr:
            output += "\n[STDERR]\n" + result.stderr
        
        # Detect new files in scratch directory created during execution
        new_files = []
        if scratch_dir.exists():
            for file_path in scratch_dir.rglob('*'):
                if file_path.is_file():
                    # Check if file was created/modified after script started
                    file_mtime = file_path.stat().st_mtime
                    if file_mtime >= start_time:
                        # Make path relative to scratch dir
                        rel_path = file_path.relative_to(scratch_dir)
                        new_files.append({
                            'path': str(rel_path),
                            'size': file_path.stat().st_size,
                            'modified': file_mtime
                        })
        
        if result.returncode != 0:
            return json.dumps({
                "result": {
                    "status": "error",
                    "exit_code": result.returncode,
                    "output": output,
                    "message": f"Script exited with code {result.returncode}",
                    "new_files": new_files
                }
            })
        
        return json.dumps({
            "result": {
                "status": "success",
                "output": output,
                "exit_code": 0,
                "new_files": new_files,
                "new_files_count": len(new_files)
            }
        })
    
    except subprocess.TimeoutExpired:
        return json.dumps({
            "error": "Script execution timed out (30 seconds)"
        })
    
    except Exception as e:
        return json.dumps({
            "error": f"Failed to execute code: {str(e)}"
        })


def generate_code_with_llm(task_description: str, context: str = "") -> str:
    """
    Helper function to generate Python code using coding model from config.
    This is an internal helper, not exposed as a tool.
    
    Args:
        task_description: What the code should do
        context: Additional context (e.g., available files, data structure)
    
    Returns:
        Generated Python code as string
    """
    try:
        config = load_config()
        api_key = os.getenv(config.get('openai', {}).get('api_key_env', 'OPENROUTER_API_KEY'))
        
        if not api_key:
            raise ValueError("API key not found")
        
        # Get coding model from config
        coding_model = config.get('coding', {}).get('model', 'qwen/qwen3-coder:free')
        
        client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=api_key
        )
        
        prompt = f"""Write Python code to {task_description}.

{context}

Requirements:
- Use relative paths starting with 'scratch/' to read data files
- Print results to stdout
- Use only standard library or commonly available packages (json, pathlib, etc.)
- Include error handling
- Keep it simple and focused

Output only the Python code, no explanations."""

        response = client.chat.completions.create(
            model=coding_model,
            messages=[
                {"role": "user", "content": prompt}
            ],
            temperature=0.2
        )
        
        code = response.choices[0].message.content
        
        # Extract code from markdown if present
        if "```python" in code:
            code = code.split("```python")[1].split("```")[0].strip()
        elif "```" in code:
            code = code.split("```")[1].split("```")[0].strip()
        
        return code
    
    except Exception as e:
        return f"# Error generating code: {str(e)}\nprint('Code generation failed')"
