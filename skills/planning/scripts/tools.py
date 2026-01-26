import os
import json

def create_subquestion_task(description: str) -> str:
    """Save a subquestion/task description to the queue"""
    # Handle both string and dict inputs
    if isinstance(description, dict):
        description = description.get('description', str(description))
    
    tasks_dir = "scratch/incomplete_tasks"
    os.makedirs(tasks_dir, exist_ok=True)
    
    # Find next task number
    task_num = 1
    while os.path.exists(os.path.join(tasks_dir, f"task_{task_num}.txt")):
        task_num += 1
    
    # Save task
    task_file = os.path.join(tasks_dir, f"task_{task_num}.txt")
    with open(task_file, 'w') as f:
        f.write(str(description))
    
    # If this is the first task, initialize CURRENT_TASK.txt
    current_task_file = "scratch/CURRENT_TASK.txt"
    is_first_task = (task_num == 1)
    if is_first_task:
        current_task_data = {
            "task_number": 1,
            "description": description,
            "status": "active"
        }
        with open(current_task_file, 'w') as f:
            f.write(json.dumps(current_task_data, indent=2))
    
    return json.dumps({
        "status": "success",
        "task_number": task_num,
        "task_file": task_file,
        "description": description,
        "is_active": is_first_task
    })
