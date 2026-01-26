import os
import json

def check_subtask_responses() -> dict:
    """
    Read all completed subquestions/tasks.
    """
    completed_dir = "scratch/completed_tasks"
    
    if not os.path.exists(completed_dir):
        return {
            "status": "error",
            "message": "No completed tasks found. Complete tasks before synthesizing."
        }
    
    # Read all completed task files
    task_files = sorted([f for f in os.listdir(completed_dir) if f.startswith("task_") and f.endswith(".txt")])
    
    if not task_files:
        return {
            "status": "error",
            "message": "No completed tasks found in completed_tasks directory."
        }
    
    # Collect all task contents
    responses = {}
    for task_file in task_files:
        task_path = os.path.join(completed_dir, task_file)
        with open(task_path, 'r') as f:
            content = f.read().strip()
            task_num = task_file.replace("task_", "").replace(".txt", "")
            responses[task_num] = content
    
    return responses
