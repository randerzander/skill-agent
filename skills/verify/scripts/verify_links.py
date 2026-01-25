#!/usr/bin/env python3
"""
Verify links skill script
Checks all URLs in a response to ensure they are valid and accessible
"""
import re
import requests
from urllib.parse import urlparse


def _extract_urls(text):
    """Extract all URLs from text (markdown links and bare URLs)"""
    urls = set()
    
    # Extract markdown links: [text](url)
    markdown_pattern = r'\[([^\]]+)\]\(([^)]+)\)'
    for match in re.finditer(markdown_pattern, text):
        urls.add(match.group(2))
    
    # Extract bare URLs
    url_pattern = r'https?://[^\s\)>\]"]+'
    for match in re.finditer(url_pattern, text):
        urls.add(match.group(0))
    
    return list(urls)


def _check_url(url, timeout=10):
    """
    Check if a URL is valid and accessible
    
    Returns:
        dict with 'valid' (bool), 'status_code' (int), 'error' (str), 'content_preview' (str)
    """
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (compatible; SkillAgent/1.0)'}
        response = requests.get(url, timeout=timeout, headers=headers, allow_redirects=True)
        
        status_code = response.status_code
        
        # Check for error status codes
        if status_code >= 400:
            return {
                'valid': False,
                'status_code': status_code,
                'error': f'HTTP {status_code}',
                'content_preview': ''
            }
        
        # Check content for common error indicators
        content_lower = response.text.lower()
        error_indicators = [
            'page not found',
            'article not found',
            'content moved',
            'content has been removed',
            '404',
            'does not exist',
            'no longer available',
            'this page doesn\'t exist',
            'page cannot be found'
        ]
        
        for indicator in error_indicators:
            if indicator in content_lower[:2000]:  # Check first 2000 chars
                return {
                    'valid': False,
                    'status_code': status_code,
                    'error': f'Content indicates error: "{indicator}"',
                    'content_preview': content_lower[:200]
                }
        
        # URL appears valid
        return {
            'valid': True,
            'status_code': status_code,
            'error': None,
            'content_preview': content_lower[:200]
        }
        
    except requests.exceptions.Timeout:
        return {
            'valid': False,
            'status_code': None,
            'error': 'Request timeout',
            'content_preview': ''
        }
    except requests.exceptions.ConnectionError:
        return {
            'valid': False,
            'status_code': None,
            'error': 'Connection error',
            'content_preview': ''
        }
    except Exception as e:
        return {
            'valid': False,
            'status_code': None,
            'error': str(e),
            'content_preview': ''
        }


def _remove_url_from_text(text, url):
    """Remove a URL from text (both markdown links and bare URLs)"""
    # Remove markdown links containing this URL
    markdown_pattern = r'\[([^\]]+)\]\(' + re.escape(url) + r'\)'
    text = re.sub(markdown_pattern, r'[\1](REMOVED)', text)
    
    # Remove bare URL
    text = text.replace(url, '(REMOVED)')
    
    return text


def execute(params):
    """
    Execute the verify_links tool
    
    Args:
        params: Dictionary of parameters (e.g., {"response_text": "Check this link..."})
    
    Returns:
        Dictionary with verification results
    """
    response_text = params.get("response_text")
    
    if not response_text:
        return {"error": "response_text parameter is required"}
    
    # Extract all URLs from the response
    urls = _extract_urls(response_text)
    
    if not urls:
        return {
            "result": {
                "status": "no_links",
                "message": "No URLs found in response to verify",
                "verified_response": response_text
            }
        }
    
    # Check each URL
    results = {}
    invalid_urls = []
    
    for url in urls:
        check_result = _check_url(url)
        results[url] = check_result
        
        if not check_result['valid']:
            invalid_urls.append(url)
    
    # Build report
    total_urls = len(urls)
    valid_urls = total_urls - len(invalid_urls)
    
    if invalid_urls:
        # Remove invalid URLs from response
        modified_response = response_text
        for url in invalid_urls:
            modified_response = _remove_url_from_text(modified_response, url)
        
        report = f"""# Link Verification Results

**Total URLs checked:** {total_urls}
**Valid URLs:** {valid_urls}
**Invalid URLs:** {len(invalid_urls)}

## Invalid URLs Detected:

"""
        for url in invalid_urls:
            result = results[url]
            report += f"- `{url}`\n"
            report += f"  - Status: {result['status_code'] or 'N/A'}\n"
            report += f"  - Error: {result['error']}\n\n"
        
        report += """
## Recommendation

**The response contains invalid or inaccessible links.** These have been removed (marked as REMOVED).

You should use the web tool to search for better, valid sources before providing this answer to the user.
"""
        
        return {
            "result": {
                "status": "invalid_links_found",
                "total_urls": total_urls,
                "valid_urls": valid_urls,
                "invalid_urls": len(invalid_urls),
                "invalid_url_list": invalid_urls,
                "verification_details": results,
                "report": report,
                "modified_response": modified_response,
                "should_research_again": True
            }
        }
    else:
        # All URLs are valid
        report = f"""# Link Verification Results

**Total URLs checked:** {total_urls}
**All URLs are valid and accessible!** ✓

The response is ready to present to the user.
"""
        
        return {
            "result": {
                "status": "all_valid",
                "total_urls": total_urls,
                "valid_urls": valid_urls,
                "invalid_urls": 0,
                "verification_details": results,
                "report": report,
                "verified_response": response_text,
                "should_research_again": False
            }
        }
