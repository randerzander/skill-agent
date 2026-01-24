---
name: web_search
description: Search the web for information using multiple search engines (DuckDuckGo, Yahoo, Mojeek). Returns a list of search results with titles, URLs, and descriptions.
---

# Web Search Skill

## When to use this skill

Use this skill when you need to:
- Find current information from the web
- Search for news, articles, or documentation
- Discover websites related to a topic
- Get multiple perspectives on a subject

## How to search the web

The web_search skill uses pysearx to search across multiple engines simultaneously for fast, reliable results.

### Basic search

When you need to search the web, call the `web_search` script with a query:

```python
result = execute({
    'query': 'latest developments in AI'
})
```

### Customizing result count

You can control how many results to return (default is 10):

```python
result = execute({
    'query': 'Python programming tutorials',
    'max_results': 5
})
```

### Response format

The skill returns a list of search results, each containing:
- `index`: Result number (1-indexed)
- `title`: Page title
- `href`: URL of the page
- `body`: Brief description/snippet

Example response:
```python
[
    {
        'index': 1,
        'title': 'Example Article',
        'href': 'https://example.com/article',
        'body': 'A brief description of the article content...'
    },
    ...
]
```

## Search engines used

The skill uses multiple reliable search engines by default:
- **DuckDuckGo API**: Fast, API-based search (always enabled)
- **Yahoo**: Reliable HTML scraping (always enabled)
- **Mojeek**: Privacy-focused search (always enabled)
- **Brave**: Auto-enabled when proxy configuration is available

All searches run in parallel for fast results.

## Best practices

- Use specific, clear search queries
- Consider using quotes for exact phrase matching
- Adjust max_results based on how comprehensive you need the information
- The skill is designed to avoid rate limiting by using multiple engines
