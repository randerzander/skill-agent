---
name: answer
description: Return a final answer to the user's query
---

# Answer Skill

Use this skill to reflect on all gathered information and provide a final answer to the user's query.

Cite relevant source URLs you used to formulate the answer.

## Workflow

1. Review subquestions/tasks with `check_subtask_responses(query: str)`
2. Determine whether to synthesize a final answer based on all subtask responses

OR

3. Use the global skill_switch tool with skill_name='planning' to create more subquestions or tasks
