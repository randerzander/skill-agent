#!/usr/bin/env python3
"""
Read URL skill script
Fetches and extracts content from URLs, converting HTML to readable markdown
"""
import requests
import html2text
from readability import Document
from urllib.parse import urlparse


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
    
    # Validate URL scheme (prevent SSRF attacks)
    try:
        parsed = urlparse(url)
        if parsed.scheme not in ['http', 'https']:
            return {"error": f"Invalid URL scheme. Only HTTP and HTTPS are supported."}
        
        # Block private IP ranges to prevent SSRF
        hostname = parsed.hostname
        if hostname:
            # Block localhost and private IPs
            if hostname in ['localhost', '127.0.0.1', '0.0.0.0'] or \
               hostname.startswith('192.168.') or \
               hostname.startswith('10.') or \
               hostname.startswith('172.16.') or hostname.startswith('172.17.') or \
               hostname.startswith('172.18.') or hostname.startswith('172.19.') or \
               hostname.startswith('172.20.') or hostname.startswith('172.21.') or \
               hostname.startswith('172.22.') or hostname.startswith('172.23.') or \
               hostname.startswith('172.24.') or hostname.startswith('172.25.') or \
               hostname.startswith('172.26.') or hostname.startswith('172.27.') or \
               hostname.startswith('172.28.') or hostname.startswith('172.29.') or \
               hostname.startswith('172.30.') or hostname.startswith('172.31.'):
                return {"error": "Access to private IP addresses is not allowed."}
    except Exception as e:
        return {"error": f"Invalid URL format: {str(e)}"}
    
    try:
        # Build headers with User-Agent to avoid being blocked
        headers = {
            'User-Agent': 'Mozilla/5.0 (compatible; SkillAgent/1.0; +https://github.com/randerzander/skill-agent)'
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
