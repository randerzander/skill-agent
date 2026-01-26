#!/usr/bin/env python3
"""
Verify links skill script
Checks all URLs in a response to ensure they are valid, accessible, and actually support the claims made
"""
import re
import os
import json
import requests
import yaml
from urllib.parse import urlparse
from pathlib import Path
from openai import OpenAI


def _load_config():
    """Load config.yaml to get OpenAI settings"""
    try:
        with open('config.yaml', 'r') as f:
            return yaml.safe_load(f)
    except:
        return {}


def _extract_urls_with_context(text):
    """
    Extract all URLs from text along with surrounding context
    Returns: [(url, context_sentence), ...]
    """
    results = []
    
    # Split into sentences (simple approach)
    sentences = re.split(r'[.!?]\s+', text)
    
    for sentence in sentences:
        # Extract markdown links: [text](url)
        markdown_pattern = r'\[([^\]]+)\]\(([^)]+)\)'
        for match in re.finditer(markdown_pattern, sentence):
            url = match.group(2)
            claim = sentence.strip()
            results.append((url, claim))
        
        # Extract bare URLs
        url_pattern = r'https?://[^\s\)>\]"]+'
        for match in re.finditer(url_pattern, sentence):
            url = match.group(0)
            claim = sentence.strip()
            results.append((url, claim))
    
    # Deduplicate while preserving order
    seen = set()
    unique_results = []
    for url, claim in results:
        if url not in seen:
            seen.add(url)
            unique_results.append((url, claim))
    
    return unique_results


def _find_cached_content(url):
    """
    Find cached web content from scratch/ directory
    Returns: (title, content) or (None, None) if not found
    """
    scratch_dir = Path("scratch")
    if not scratch_dir.exists():
        return None, None
    
    # Look for url_*.jsonl files
    for file in scratch_dir.glob("url_*.jsonl"):
        try:
            with open(file, 'r') as f:
                data = json.loads(f.read())
                if data.get('url') == url:
                    return data.get('title'), data.get('content')
        except:
            continue
    
    return None, None


def _verify_citation_with_llm(url, claim, content):
    """
    Use LLM to verify if the web content actually supports the claim
    
    Returns:
        dict with 'supports' (bool), 'explanation' (str), 'confidence' (str)
    """
    if not content:
        return {
            'supports': False,
            'explanation': 'No cached content available for this URL',
            'confidence': 'N/A'
        }
    
    # Truncate content if too long (keep first 8000 chars)
    if len(content) > 8000:
        content = content[:8000] + "\n\n[Content truncated...]"
    
    config = _load_config()
    api_key = os.getenv("OPENROUTER_API_KEY")
    base_url = config.get('openai', {}).get('base_url', 'https://openrouter.ai/api/v1')
    model = config.get('openai', {}).get('model', 'nvidia/nemotron-3-nano-30b-a3b:free')
    
    if not api_key:
        return {
            'supports': False,
            'explanation': 'No API key available for verification',
            'confidence': 'N/A'
        }
    
    client = OpenAI(api_key=api_key, base_url=base_url)
    
    prompt = f"""You are evaluating whether a web source supports a claim made in an answer.

CLAIM MADE IN ANSWER:
{claim}

SOURCE URL:
{url}

CONTENT FROM SOURCE:
{content}

TASK: Does the content from this source actually support the claim made in the answer?

Respond with ONLY a JSON object in this exact format:
{{
  "supports": true or false,
  "explanation": "Brief explanation of why the content does or does not support the claim",
  "confidence": "high" or "medium" or "low"
}}"""

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1
        )
        
        result_text = response.choices[0].message.content.strip()
        
        # Try to extract JSON from response
        # Look for JSON block
        json_match = re.search(r'\{[^}]+\}', result_text, re.DOTALL)
        if json_match:
            result = json.loads(json_match.group(0))
            return result
        else:
            # Fallback if no valid JSON
            return {
                'supports': False,
                'explanation': 'Failed to parse LLM verification response',
                'confidence': 'N/A'
            }
    
    except Exception as e:
        return {
            'supports': False,
            'explanation': f'LLM verification error: {str(e)}',
            'confidence': 'N/A'
        }


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
    
    # Extract all URLs with context from the response
    url_claims = _extract_urls_with_context(response_text)
    
    if not url_claims:
        return {
            "result": {
                "status": "no_links",
                "message": "No URLs found in response to verify",
                "verified_response": response_text
            }
        }
    
    # Check each URL
    results = {}
    unsupported_urls = []
    
    for url, claim in url_claims:
        # Try to find cached content
        title, content = _find_cached_content(url)
        
        if content:
            # Verify with LLM
            verification = _verify_citation_with_llm(url, claim, content)
            results[url] = {
                'claim': claim,
                'cached': True,
                'title': title,
                **verification
            }
            
            if not verification['supports']:
                unsupported_urls.append(url)
        else:
            # No cached content - mark as unverifiable
            results[url] = {
                'claim': claim,
                'cached': False,
                'supports': False,
                'explanation': 'Content not cached - cannot verify',
                'confidence': 'N/A'
            }
            unsupported_urls.append(url)
    
    # Build report
    total_urls = len(url_claims)
    supported_urls = total_urls - len(unsupported_urls)
    
    if unsupported_urls:
        report = f"""# Citation Verification Results

**Total citations checked:** {total_urls}
**Supported citations:** {supported_urls}
**Unsupported/Unverifiable citations:** {len(unsupported_urls)}

## Problematic Citations:

"""
        for url in unsupported_urls:
            result = results[url]
            report += f"### `{url}`\n"
            report += f"**Claim:** {result['claim']}\n\n"
            report += f"**Issue:** {result['explanation']}\n"
            report += f"**Confidence:** {result['confidence']}\n\n"
        
        report += """
## Recommendation

**The answer contains citations that do not support the claims.** You must either:
1. Remove the unsupported claims from your answer
2. Use the web skill to find better sources that actually support your claims
3. Revise the claims to match what the sources actually say

Do NOT submit an answer with unsupported or unverifiable citations.
"""
        
        return {
            "result": {
                "status": "unsupported_citations",
                "total_urls": total_urls,
                "supported_urls": supported_urls,
                "unsupported_urls": len(unsupported_urls),
                "unsupported_url_list": unsupported_urls,
                "verification_details": results,
                "report": report,
                "should_research_again": True
            }
        }
    else:
        # All citations are supported
        report = f"""# Citation Verification Results

**Total citations checked:** {total_urls}
**All citations are verified and support the claims!** ✓

The response is ready to submit.
"""
        
        return {
            "result": {
                "status": "all_verified",
                "total_urls": total_urls,
                "supported_urls": supported_urls,
                "unsupported_urls": 0,
                "verification_details": results,
                "report": report,
                "verified_response": response_text,
                "should_research_again": False
            }
        }
