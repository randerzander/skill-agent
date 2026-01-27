---
name: planning
description: "Break down complex queries into sequential sub-tasks. After creating tasks, switch to other skills to complete them."
---

# Planning Skill

Use this skill to break down complex, multi-part queries into sequential tasks. ALWAYS create simple, discrete tasks. Do NOT put multiple questions in a single task.

Identify persons, places, and things mentioned in the user query.
For each entity, ask yourself who or what is this thing? Create separate sub-task to use web to search for detailed information on it.

## Example
**User Query:** "Plan a weekend trip to Paris including flights, accommodation, and sightseeing."
1. Call "list_skills"
2. create_subquestion_task "Use web skills to research and book flights to Paris"
3. create_subquestion_task "Use web skills to find and reserve accommodation in Paris"
4. create_subquestion_task "Use web skills to create a sightseeing itinerary for Paris"

## Workflow

1. Create sub-tasks using `create_subquestion_task(description: str)`
2. Call "list_skills" to learn about the skills (collections of special tools) you can use to solve these tasks.
3. Use global 'skill_switch' tool with appropriate skill_name (e.g., skill_name='web' to search and browse the web for more information) to work on each task
