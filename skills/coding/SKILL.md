---
name: coding
description: Write and execute Python code to process data, analyze scraped content, or perform computations
---

# Coding Skill

Use this skill to write and execute Python code for data processing, analysis, or computation tasks.

Most often the code result should produce an image of a plot or a textual output that answers the user's question. Those artifacts should be saved in scratch/

## When to use this skill

- Process or analyze scraped web content from `scratch/` directory
- Perform calculations or data transformations
- Parse JSON/JSONL files from search results or URL content
- Generate reports or visualizations
- Any task requiring programmatic data processing

## Available scraped data

The web skill saves content to the scratch directory:
- `scratch/query_*.jsonl` - Search results (one JSON object per line)
- `scratch/url_*.jsonl` - Scraped web page content with URL, title, and markdown content
- `scratch/USER_QUERY.txt` - Original user question

## Workflow

1. Use `generate_code` to have the coding model (qwen3-coder) write Python code for you
2. Use `write_code` to save the generated (or hand-written) code to `scratch/code/`
3. Use `run_code` to execute the script and get results
4. Scripts can read files from `scratch/` to process scraped data
5. Results are returned as text output

## Tools

- `generate_code(task_description: str, context: str)` - Use coding model to generate Python code
- `write_code(filename: str, code: str)` - Save Python code to scratch/code/
- `run_code(filename: str)` - Execute a previously written script (file must exist)

**Recommended**: Use `generate_code` first to let the specialized coding model write the code,
then use `write_code` to save it, and `run_code` to execute it.

## Tips

- Always use relative paths starting with `scratch/` to read data files
- Scripts run with the project root as working directory
- Use standard libraries (json, pathlib, etc.) without installation
- For data analysis, you can use pandas, numpy if needed
- Print results to stdout - they will be captured and returned
