#!/usr/bin/env python3
"""
Read URL skill script
Fetches and extracts content from URLs, converting HTML to readable markdown
"""
import requests
import html2text
from readability import Document
from urllib.parse import urlparse
import ipaddress


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
            # Check if it's an IP address
            try:
                ip = ipaddress.ip_address(hostname)
                if ip.is_private or ip.is_loopback or ip.is_link_local:
                    return {"error": "Access to private IP addresses is not allowed."}
            except ValueError:
                # Not an IP address, check for localhost
                if hostname.lower() in ['localhost']:
                    return {"error": "Access to localhost is not allowed."}
    except Exception as e:
        return {"error": f"Invalid URL format: {str(e)}"}
    
    try:
        # Build headers with User-Agent to avoid being blocked
        headers = {
            'User-Agent': 'Mozilla/5.0 (compatible; SkillAgent/1.0)'
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
