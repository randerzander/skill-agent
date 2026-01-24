#!/usr/bin/env python3
"""
Read URL skill script
Fetches and extracts content from URLs, converting HTML to readable markdown
"""
import requests
import html2text
from readability import Document


def execute(params):
    """
    Execute the read_url skill
    
    Args:
        params: Dictionary of parameters (e.g., {"url": "https://example.com"})
    
    Returns:
        Dictionary with result containing the extracted content
    """
    url = params.get("url")
    
    if not url:
        return {"error": "URL parameter is required"}
    
    try:
        # Build headers with User-Agent to avoid being blocked
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
        
        # Fetch the URL content
        response = requests.get(url, timeout=10, headers=headers)
        response.raise_for_status()
        
        # Use readability to parse HTML and extract main content
        doc = Document(response.text)
        
        # Get title and content
        title = doc.title()
        content_html = doc.summary()
        
        if not content_html:
            return {"error": f"Failed to parse content from {url}. The page might be empty or not contain extractable text."}
        
        # Convert HTML content to markdown using html2text
        h = html2text.HTML2Text()
        h.body_width = 0  # Don't wrap lines
        h.ignore_links = False
        markdown_content = h.handle(content_html)
        
        # Add title if available
        if title:
            markdown_content = f"# {title}\n\n{markdown_content}"
        
        return {"result": markdown_content}
        
    except requests.exceptions.RequestException as e:
        return {"error": f"Failed to fetch URL: {str(e)}"}
    except Exception as e:
        return {"error": f"Error processing URL: {str(e)}"}
