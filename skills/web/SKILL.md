---
name: web
description: Tools for web search and reading URLs. Use to find info online that answer questions.
---

# Web Skill

Use this skill to use web search engines and read web pages to find information online.

## Workflow

1. Check search engines for pages answering the current subquestion/task with `search(query: str)`
2. Load relevant web pages using `read_url(url: str)`
3. Keep searching and loading result URLs until you have enough info to answer the task
4. Use global `complete_task` tool with the result when the task is done
5. Use global `skill_switch` with skill_name='answer' to prepare a final answer when all tasks are complete
