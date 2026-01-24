#!/usr/bin/env python3
"""
Web search skill script
Searches the web using pysearx across multiple search engines
"""
from pysearx import search


def execute(params):
    """
    Execute the web_search skill
    
    Args:
        params: Dictionary of parameters (e.g., {"query": "AI news", "max_results": 10})
    
    Returns:
        Dictionary with result containing list of search results
    """
    query = params.get("query")
    max_results = params.get("max_results", 10)
    
    if not query:
        return {"error": "Query parameter is required"}
    
    try:
        # Validate max_results
        if not isinstance(max_results, int) or max_results < 1:
            max_results = 10
        
        # Use pysearx to search across multiple engines
        # Returns: title, url, description, engine
        raw_results = search(query, max_results=max_results, parallel=True)
        
        # Convert to expected format with index, title, href, body
        results = []
        for i, result in enumerate(raw_results, 1):
            results.append({
                'index': i,
                'title': result.get('title', 'N/A'),
                'href': result.get('url', 'N/A'),
                'body': result.get('description', '')
            })
        
        # Check for no results
        if len(results) == 0:
            return {
                "error": "No results found. The search service may be rate limited or temporarily unavailable. Try waiting a moment or rephrasing your query."
            }
        
        return {"result": results}
        
    except Exception as e:
        return {"error": f"Error during search: {str(e)}"}
