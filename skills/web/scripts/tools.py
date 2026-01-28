#!/usr/bin/env python3
"""
Web skill tools - consolidated search and URL reading functionality
"""
import json
import os
import re
import time
import yaml
import requests
import html2text
from pathlib import Path
from pysearx import search as pysearx_search
from readability import Document
from urllib.parse import urlparse, parse_qs
import ipaddress
import sys

# Add parent directory to path to import utils
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
from utils import sanitize_filename, ensure_scratch_dir


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def _save_to_scratch(url, title, content):
    """Save content to scratch directory as JSONL"""
    try:
        scratch_dir = ensure_scratch_dir()
        
        if title:
            filename = sanitize_filename(title)
        else:
            parsed = urlparse(url)
            filename = sanitize_filename(parsed.path.replace('/', '_') or 'content')
        
        filepath = scratch_dir / f"url_{filename}.jsonl"
        
        with open(filepath, 'w') as f:
            data = {
                'url': url,
                'title': title,
                'content': content,
                'timestamp': time.time()
            }
            f.write(json.dumps(data) + '\n')
    except Exception as e:
        print(f"Warning: Failed to save to scratch: {e}")


def _get_user_query_from_context():
    """Get user query from scratch/USER_QUERY.txt if available"""
    try:
        query_file = Path("scratch/USER_QUERY.txt")
        if query_file.exists():
            with open(query_file, 'r') as f:
                return f.read().strip()
    except:
        pass
    return None


def _is_youtube_url(url):
    """Check if URL is a YouTube video"""
    parsed = urlparse(url)
    return 'youtube.com' in parsed.netloc or 'youtu.be' in parsed.netloc


def _is_wikipedia_url(url):
    """Check if URL is a Wikipedia article"""
    parsed = urlparse(url)
    return 'wikipedia.org' in parsed.netloc


def _is_github_url(url):
    """Check if URL is a GitHub URL"""
    parsed = urlparse(url)
    return 'github.com' in parsed.netloc or 'raw.githubusercontent.com' in parsed.netloc


def _is_pdf_url(url):
    """Check if URL points to a PDF"""
    return url.lower().endswith('.pdf')


def _get_youtube_transcript(url):
    """Extract transcript from YouTube video"""
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
        
        parsed = urlparse(url)
        if 'youtu.be' in parsed.netloc:
            video_id = parsed.path.strip('/')
        else:
            query_params = parse_qs(parsed.query)
            video_id = query_params.get('v', [None])[0]
        
        if not video_id:
            return {"error": "Could not extract video ID from URL"}
        
        transcript_list = YouTubeTranscriptApi.get_transcript(video_id)
        transcript = ' '.join([entry['text'] for entry in transcript_list])
        
        title = f"YouTube Video {video_id}"
        _save_to_scratch(url, title, transcript)
        
        return {
            "result": {
                "url": url,
                "title": title,
                "content": transcript,
                "source_type": "youtube"
            }
        }
    except Exception as e:
        return {"error": f"Failed to get YouTube transcript: {str(e)}"}


def _get_wikipedia_content(url):
    """Extract content from Wikipedia article"""
    try:
        import wikipedia
        
        parsed = urlparse(url)
        page_title = parsed.path.split('/')[-1].replace('_', ' ')
        
        page = wikipedia.page(page_title, auto_suggest=False)
        content = page.content
        
        _save_to_scratch(url, page.title, content)
        
        return {
            "result": {
                "url": url,
                "title": page.title,
                "content": content,
                "source_type": "wikipedia"
            }
        }
    except Exception as e:
        return {"error": f"Failed to get Wikipedia content: {str(e)}"}


def _get_pdf_content(url):
    """Extract text from PDF URL"""
    try:
        import PyPDF2
        from io import BytesIO
        
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        
        pdf_file = BytesIO(response.content)
        reader = PyPDF2.PdfReader(pdf_file)
        
        text = ""
        for page in reader.pages:
            text += page.extract_text() + "\n\n"
        
        title = url.split('/')[-1]
        _save_to_scratch(url, title, text)
        
        return {
            "result": {
                "url": url,
                "title": title,
                "content": text,
                "source_type": "pdf"
            }
        }
    except Exception as e:
        return {"error": f"Failed to get PDF content: {str(e)}"}


# ============================================================================
# PUBLIC TOOL FUNCTIONS
# ============================================================================

def search(query: str) -> str:
    """Search the web using multiple search engines and return results"""
    if not query:
        return json.dumps({"error": "Query parameter is required"})
    
    try:
        # Use pysearx to search across multiple engines
        raw_results = pysearx_search(query, max_results=10, parallel=True)
        
        # Convert to expected format
        results = []
        for i, result in enumerate(raw_results, 1):
            results.append({
                'index': i,
                'title': result.get('title', 'N/A'),
                'href': result.get('url', 'N/A'),
                'body': result.get('description', '')
            })
        
        if len(results) == 0:
            return json.dumps({
                "error": "No results found. The search service may be rate limited or temporarily unavailable."
            })
        
        # Save results to scratch directory
        scratch_dir = ensure_scratch_dir()
        
        filename = sanitize_filename(query)
        filepath = scratch_dir / f"query_{filename}.jsonl"
        
        with open(filepath, 'w') as f:
            for result in results:
                f.write(json.dumps(result) + '\n')
        
        return json.dumps({"result": results})
        
    except Exception as e:
        return json.dumps({"error": f"Error during search: {str(e)}"})


def read_url(url: str) -> str:
    """Fetch and extract readable content from a URL (handles web pages, YouTube, Wikipedia, PDFs)"""
    if not url:
        return json.dumps({"error": "URL parameter is required"})
    
    # Validate URL scheme (prevent SSRF attacks)
    try:
        parsed = urlparse(url)
        if parsed.scheme not in ['http', 'https']:
            return json.dumps({"error": f"Invalid URL scheme. Only HTTP and HTTPS are supported."})
        
        # Block private IP ranges to prevent SSRF
        hostname = parsed.hostname
        if hostname:
            try:
                ip = ipaddress.ip_address(hostname)
                if ip.is_private or ip.is_loopback or ip.is_link_local:
                    return json.dumps({"error": "Access to private IP addresses is not allowed."})
            except ValueError:
                if hostname.lower() in ['localhost']:
                    return json.dumps({"error": "Access to localhost is not allowed."})
    except Exception as e:
        return json.dumps({"error": f"Invalid URL format: {str(e)}"})
    
    # Handle special URL types
    if _is_youtube_url(url):
        result = _get_youtube_transcript(url)
        return json.dumps(result)
    
    if _is_wikipedia_url(url):
        result = _get_wikipedia_content(url)
        return json.dumps(result)
    
    if _is_pdf_url(url):
        result = _get_pdf_content(url)
        return json.dumps(result)
    
    # Handle regular web pages
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (compatible; SkillAgent/1.0)'}
        
        # Add GitHub token if URL is from GitHub and token is available
        if _is_github_url(url):
            github_token = os.getenv('GITHUB_TOKEN')
            if github_token:
                headers['Authorization'] = f'token {github_token}'
        
        response = requests.get(url, timeout=30, headers=headers)
        response.raise_for_status()
        
        # Use readability to extract main content
        doc = Document(response.text)
        title = doc.title()
        html_content = doc.summary()
        
        # Convert HTML to markdown
        h = html2text.HTML2Text()
        h.ignore_links = False
        h.ignore_images = True
        markdown_content = h.handle(html_content)
        
        # Save to scratch
        _save_to_scratch(url, title, markdown_content)
        
        return json.dumps({
            "result": {
                "url": url,
                "title": title,
                "content": markdown_content,
                "source_type": "webpage"
            }
        })
        
    except Exception as e:
        return json.dumps({"error": f"Failed to fetch URL: {str(e)}"})
