#!/usr/bin/env python3
"""
Web search script
Searches the web using pysearx across multiple search engines
"""
import json
import os
import re
from pathlib import Path
from pysearx import search


def sanitize_filename(name):
    """Sanitize a string for use as a filename"""
    # Replace problematic characters with underscores
    name = re.sub(r'[^\w\s-]', '_', name)
    # Replace whitespace with underscores
    name = re.sub(r'\s+', '_', name)
    # Limit length
    return name[:100]


def execute(params):
    """
    Execute the search tool
    
    Args:
        params: Dictionary of parameters (e.g., {"query": "AI news"})
    
    Returns:
        Dictionary with result containing list of search results
    """
    query = params.get("query")
    
    if not query:
        return {"error": "Query parameter is required"}
    
    try:
        # Use pysearx to search across multiple engines with default max_results
        raw_results = search(query, max_results=10, parallel=True)
        
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
                "error": "No results found. The search service may be rate limited or temporarily unavailable."
            }
        
        # Save results to scratch directory
        scratch_dir = Path("scratch")
        scratch_dir.mkdir(exist_ok=True)
        
        filename = sanitize_filename(query)
        filepath = scratch_dir / f"query_{filename}.jsonl"
        
        # Write results as JSONL (one JSON object per line)
        with open(filepath, 'w') as f:
            for result in results:
                f.write(json.dumps(result) + '\n')
        
        return {"result": results}
        
    except Exception as e:
        return {"error": f"Error during search: {str(e)}"}
