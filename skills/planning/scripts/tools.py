import os
import json
from typing import List, Union

def create_subquestion_tasks(descriptions: Union[str, List[str]]) -> str:
    """
    Save one or more subquestion/task descriptions to the queue.
    
    Args:
        descriptions: A single task description (string) or a list of task descriptions
    
    Returns:
        JSON string with status and details of created tasks
    """
    tasks_dir = "scratch/incomplete_tasks"
    os.makedirs(tasks_dir, exist_ok=True)
    
    # Normalize input to list
    if isinstance(descriptions, str):
        # Check if it's a JSON string representing a list
        if descriptions.strip().startswith('['):
            try:
                descriptions = json.loads(descriptions)
            except json.JSONDecodeError:
                # Not valid JSON, treat as single description
                descriptions = [descriptions]
        else:
            descriptions = [descriptions]
    elif isinstance(descriptions, dict):
        # Handle dict input (legacy compatibility)
        descriptions = [descriptions.get('description', str(descriptions))]
    
    if not descriptions:
        return json.dumps({
            "status": "error",
            "message": "No task descriptions provided"
        })
    
    created_tasks = []
    
    for description in descriptions:
        # Find next task number
        task_num = 1
        while os.path.exists(os.path.join(tasks_dir, f"task_{task_num}.txt")):
            task_num += 1
        
        # Save task
        task_file = os.path.join(tasks_dir, f"task_{task_num}.txt")
        with open(task_file, 'w') as f:
            f.write(str(description))
        
        created_tasks.append({
            "task_number": task_num,
            "task_file": task_file,
            "description": str(description)
        })
    
    # If this was the first batch, initialize CURRENT_TASK.txt with the first task
    current_task_file = "scratch/CURRENT_TASK.txt"
    if created_tasks and created_tasks[0]["task_number"] == 1:
        current_task_data = {
            "task_number": 1,
            "description": created_tasks[0]["description"],
            "status": "active"
        }
        with open(current_task_file, 'w') as f:
            f.write(json.dumps(current_task_data, indent=2))
    
    return json.dumps({
        "status": "success",
        "tasks_created": len(created_tasks),
        "tasks": created_tasks,
        "first_task_active": created_tasks[0]["task_number"] == 1 if created_tasks else False
    })
