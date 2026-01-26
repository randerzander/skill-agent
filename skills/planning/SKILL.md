---
name: planning
description: "Break down complex queries into sequential sub-tasks. After creating tasks, deactivate and use other skills to complete them."
---

# Planning Skill

Use this skill to break down complex, multi-part queries into sequential tasks.

## Workflow

1. Create sub-tasks using `create_subquestion_task(description: str)`
2. Call global 'deactivate' tool
3. Activate appropriate skill (e.g., activate_web to search and browse the web for more information) to work on each task
