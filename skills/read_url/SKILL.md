---
name: read_url
description: Read and extract content from any URL. Handles web pages, converting HTML to readable markdown format. Use this for documentation, blog posts, articles, and any web page content.
---

# Read URL Skill

## When to use this skill

Use this skill when you need to:
- Read content from a web page
- Extract text from HTML pages
- Fetch documentation from URLs
- Read blog posts or articles from the web
- Access any web-based content

## How to read URLs

This skill fetches content from web URLs and converts it to a readable markdown format using the Readability algorithm (same approach as Reader Mode in browsers).

### Basic URL reading

Execute the script with a URL parameter to fetch and extract the main content from any web page. The tool will:
1. Fetch the HTML from the URL
2. Use the Readability algorithm to extract the main content
3. Convert the content to clean markdown format
4. Return the formatted content

### Features

- Extracts main content and filters out navigation, ads, and other clutter
- Converts HTML to clean, readable markdown
- Preserves links and formatting
- Handles most modern web pages

## Execution

To execute this skill, run the `scripts/read_url.py` script with JSON parameters:

```bash
python scripts/read_url.py '{"url": "https://example.com/article"}'
```

The script will output a JSON response containing the extracted content in markdown format.
