#!/usr/bin/env python3
"""
Read URL skill script
Fetches and extracts content from URLs, converting HTML to readable markdown
Supports special handling for YouTube and Wikipedia URLs
Optional: Chunk and retrieve relevant content using sentence transformers + LanceDB
"""
import os
import json
import time
import yaml
import requests
import html2text
from readability import Document
from urllib.parse import urlparse, parse_qs
import ipaddress
import re
from pathlib import Path


def _sanitize_filename(name):
    """Sanitize a string for use as a filename"""
    # Replace problematic characters with underscores
    name = re.sub(r'[^\w\s-]', '_', name)
    # Replace whitespace with underscores
    name = re.sub(r'\s+', '_', name)
    # Limit length
    return name[:100]


def _save_to_scratch(url, title, content):
    """Save content to scratch directory as JSONL"""
    try:
        scratch_dir = Path("scratch")
        scratch_dir.mkdir(exist_ok=True)
        
        # Use title or URL path as filename
        if title:
            filename = _sanitize_filename(title)
        else:
            parsed = urlparse(url)
            filename = _sanitize_filename(parsed.path.replace('/', '_') or 'content')
        
        filepath = scratch_dir / f"url_{filename}.jsonl"
        
        # Write as JSONL with url, title, and content
        with open(filepath, 'w') as f:
            data = {
                'url': url,
                'title': title,
                'content': content,
                'timestamp': time.time()
            }
            f.write(json.dumps(data) + '\n')
    except Exception as e:
        # Don't fail if saving fails, just log
        print(f"Warning: Failed to save to scratch: {e}")


# Load config for retrieval settings
def _load_config():
    """Load configuration"""
    config_path = Path(__file__).parent.parent.parent.parent / "config.yaml"
    try:
        with open(config_path) as f:
            return yaml.safe_load(f)
    except:
        return {}


def _chunk_text(text, tokens_per_chunk=2048):
    """Split text into chunks by token count using sentence transformers tokenizer"""
    try:
        from sentence_transformers import SentenceTransformer
        
        config = _load_config()
        model_name = config.get('retrieval', {}).get('embedding_model', 'sentence-transformers/all-MiniLM-L6-v2')
        model = SentenceTransformer(model_name)
        
        # Tokenize the full text
        tokens = model.tokenizer.encode(text)
        
        chunks = []
        for i in range(0, len(tokens), tokens_per_chunk):
            chunk_tokens = tokens[i:i + tokens_per_chunk]
            chunk_text = model.tokenizer.decode(chunk_tokens, skip_special_tokens=True)
            chunks.append(chunk_text)
        
        return chunks
    except Exception as e:
        # Fallback: simple character-based chunking (rough estimate: 4 chars per token)
        chars_per_chunk = tokens_per_chunk * 4
        return [text[i:i + chars_per_chunk] for i in range(0, len(text), chars_per_chunk)]


def _embed_and_store(url, text, tokens_per_chunk=2048):
    """Chunk text, embed, and store in LanceDB"""
    import time
    
    timings = {}
    total_start = time.time()
    
    try:
        import lancedb
        from sentence_transformers import SentenceTransformer
        import hashlib
        
        config = _load_config()
        model_name = config.get('retrieval', {}).get('embedding_model', 'sentence-transformers/all-MiniLM-L6-v2')
        model = SentenceTransformer(model_name)
        
        # Create chunks
        chunk_start = time.time()
        chunks = _chunk_text(text, tokens_per_chunk)
        timings['chunking'] = time.time() - chunk_start
        
        # Create URL hash for table name
        url_hash = hashlib.md5(url.encode()).hexdigest()[:16]
        
        # Connect to LanceDB
        db_path = Path(__file__).parent.parent.parent.parent / "data" / "lancedb"
        db_path.mkdir(parents=True, exist_ok=True)
        db = lancedb.connect(str(db_path))
        
        # Prepare data with embeddings
        embed_start = time.time()
        data = []
        for i, chunk in enumerate(chunks):
            embedding = model.encode(chunk).tolist()
            data.append({
                'chunk_id': i,
                'text': chunk,
                'vector': embedding,
                'url': url
            })
        timings['embedding'] = time.time() - embed_start
        
        # Create/overwrite table for this URL
        write_start = time.time()
        table_name = f"url_{url_hash}"
        if table_name in db.table_names():
            db.drop_table(table_name)
        
        table = db.create_table(table_name, data)
        timings['writing_to_lancedb'] = time.time() - write_start
        
        timings['total'] = time.time() - total_start
        
        return table_name, len(chunks), timings
        
    except Exception as e:
        raise Exception(f"Failed to embed and store: {str(e)}")


def _retrieve_relevant_chunks(table_name, query, top_k=2):
    """Retrieve most relevant chunks for a query"""
    try:
        import lancedb
        from sentence_transformers import SentenceTransformer
        
        config = _load_config()
        model_name = config.get('retrieval', {}).get('embedding_model', 'sentence-transformers/all-MiniLM-L6-v2')
        model = SentenceTransformer(model_name)
        
        # Connect to DB
        db_path = Path(__file__).parent.parent.parent.parent / "data" / "lancedb"
        db = lancedb.connect(str(db_path))
        table = db.open_table(table_name)
        
        # Embed query
        query_embedding = model.encode(query).tolist()
        
        # Search
        results = table.search(query_embedding).limit(top_k).to_list()
        
        # Extract text chunks
        chunks = [r['text'] for r in results]
        
        return chunks
        
    except Exception as e:
        raise Exception(f"Failed to retrieve chunks: {str(e)}")


def _get_user_query_from_context():
    """Get the original user query from scratch/user_query.txt"""
    try:
        query_file = Path(__file__).parent.parent.parent.parent / "scratch" / "user_query.txt"
        if query_file.exists():
            with open(query_file, 'r') as f:
                return f.read().strip()
        return None
    except Exception as e:
        return None


def _is_pdf_url(url):
    """Check if URL is a PDF"""
    return url.lower().endswith('.pdf')


def _get_pdf_content(url):
    """Extract text from PDF URL using pypdfium2"""
    try:
        import pypdfium2 as pdfium
        import io
        
        # Fetch PDF
        headers = {'User-Agent': 'Mozilla/5.0 (compatible; SkillAgent/1.0)'}
        response = requests.get(url, timeout=30, headers=headers)
        response.raise_for_status()
        
        # Save raw PDF to scratch
        try:
            scratch_dir = Path("scratch")
            scratch_dir.mkdir(exist_ok=True)
            
            # Extract filename from URL or use generic name
            parsed = urlparse(url)
            pdf_filename = _sanitize_filename(parsed.path.split('/')[-1] or 'document')
            if not pdf_filename.endswith('.pdf'):
                pdf_filename += '.pdf'
            
            pdf_path = scratch_dir / f"pdf_{pdf_filename}"
            with open(pdf_path, 'wb') as f:
                f.write(response.content)
        except Exception as e:
            print(f"Warning: Failed to save PDF to scratch: {e}")
        
        # Load PDF from bytes
        pdf = pdfium.PdfDocument(io.BytesIO(response.content))
        
        # Extract text from all pages
        text_parts = []
        for page_num in range(len(pdf)):
            page = pdf[page_num]
            textpage = page.get_textpage()
            text = textpage.get_text_range()
            text_parts.append(text)
            textpage.close()
            page.close()
        
        pdf.close()
        
        full_text = "\n\n".join(text_parts)
        
        if not full_text.strip():
            return {"error": "PDF contains no extractable text"}
        
        content = f"""# PDF Document

**URL:** {url}
**Pages:** {len(text_parts)}

## Content

{full_text}"""
        
        # Save extracted text to scratch
        pdf_title = pdf_filename.replace('.pdf', '')
        _save_to_scratch(url, pdf_title, content)
        
        return {"result": content}
        
    except Exception as e:
        return {"error": f"Failed to extract PDF content: {str(e)}"}

def _is_youtube_url(url):
    """Check if URL is a YouTube URL"""
    return 'youtube.com' in url or 'youtu.be' in url


def _is_wikipedia_url(url):
    """Check if URL is a Wikipedia URL"""
    return 'wikipedia.org' in url


def _extract_video_id(url):
    """Extract YouTube video ID from URL"""
    # Handle youtu.be links
    if 'youtu.be' in url:
        return url.split('/')[-1].split('?')[0]
    
    # Handle youtube.com links
    parsed = urlparse(url)
    if parsed.hostname in ['www.youtube.com', 'youtube.com', 'm.youtube.com']:
        if parsed.path == '/watch':
            query_params = parse_qs(parsed.query)
            return query_params.get('v', [None])[0]
        elif parsed.path.startswith('/shorts/'):
            return parsed.path.split('/shorts/')[-1].split('?')[0]
    
    return None


def _get_youtube_transcript(url):
    """Fetch YouTube transcript using youtube-transcript-api"""
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
        
        video_id = _extract_video_id(url)
        if not video_id:
            return {"error": "Could not extract video ID from YouTube URL"}
        
        # Initialize API and fetch transcript
        api = YouTubeTranscriptApi()
        fetched_transcript = api.fetch(video_id)
        
        # Combine all transcript snippets
        transcript = "\n".join([snippet.text for snippet in fetched_transcript.snippets])
        
        full_content = f"""# YouTube Video Transcript

**Video ID:** {video_id}
**URL:** {url}
**Language:** {fetched_transcript.language} ({fetched_transcript.language_code})
**Auto-generated:** {'Yes' if fetched_transcript.is_generated else 'No'}

## Transcript

{transcript}"""
        
        # Save to scratch
        _save_to_scratch(url, f"YouTube_{video_id}", full_content)
        
        return {"result": full_content}
        
    except Exception as e:
        return {"error": f"Failed to fetch YouTube transcript: {str(e)}"}


def _extract_wikipedia_title(url):
    """Extract Wikipedia article title from URL"""
    # Handle various Wikipedia URL formats
    match = re.search(r'/wiki/([^?#]+)', url)
    if match:
        # URL decode and replace underscores with spaces
        import urllib.parse
        title = urllib.parse.unquote(match.group(1))
        return title.replace('_', ' ')
    return None


def _extract_wikipedia_language(url):
    """Extract language code from Wikipedia URL"""
    match = re.search(r'https?://([a-z]+)\.wikipedia\.org', url)
    return match.group(1) if match else 'en'


def _get_wikipedia_content(url):
    """Fetch Wikipedia article using Wikipedia API"""
    try:
        import wikipediaapi
        
        title = _extract_wikipedia_title(url)
        if not title:
            return {"error": "Could not extract article title from Wikipedia URL"}
        
        lang = _extract_wikipedia_language(url)
        
        # Create Wikipedia API object
        wiki = wikipediaapi.Wikipedia(
            user_agent='SkillAgent/1.0',
            language=lang,
            timeout=30.0
        )
        
        page = wiki.page(title)
        
        if not page.exists():
            return {"error": f"Wikipedia article not found: {title}"}
        
        # Build markdown content
        content = f"# {page.title}\n\n"
        
        # Add summary
        if page.summary:
            content += f"## Summary\n\n{page.summary}\n\n"
        
        # Add full content
        content += f"## Full Article\n\n{page.text}\n\n"
        
        # Add metadata
        content += f"---\n\n**URL:** {page.fullurl}\n\n"
        
        if page.categories:
            cats = [cat.replace('Category:', '') for cat in list(page.categories.keys())[:10]]
            content += f"**Categories:** {', '.join(cats)}\n\n"
        
        # Save to scratch
        _save_to_scratch(url, page.title, content)
        
        return {"result": content}
        
    except ImportError:
        return {"error": "Wikipedia functionality not available. Missing dependency: wikipedia-api"}
    except Exception as e:
        return {"error": f"Error fetching Wikipedia article: {str(e)}"}


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
    
    # Get user query from conversation context for retrieval
    user_query = _get_user_query_from_context()
    
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
    
    # Handle YouTube URLs
    if _is_youtube_url(url):
        return _get_youtube_transcript(url)
    
    # Handle Wikipedia URLs
    if _is_wikipedia_url(url):
        return _get_wikipedia_content(url)
    
    # Handle PDF URLs
    if _is_pdf_url(url):
        return _get_pdf_content(url)
    
    # Handle regular web pages
    try:
        # Build headers with User-Agent to avoid being blocked
        headers = {
            'User-Agent': 'Mozilla/5.0 (compatible; SkillAgent/1.0)',
            'Accept-Encoding': 'gzip, deflate, br'
        }
        
        # Fetch the URL content - requests handles gzip automatically
        response = requests.get(url, timeout=10, headers=headers)
        response.raise_for_status()
        
        # Force decode if needed (requests should do this automatically)
        try:
            content = response.text
        except Exception as decode_error:
            # Fallback: try to decode manually
            import gzip
            try:
                content = gzip.decompress(response.content).decode('utf-8', errors='ignore')
            except:
                content = response.content.decode('utf-8', errors='ignore')
        
        # Use readability to parse HTML and extract main content
        doc = Document(content)
        
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
        
        # Check if retrieval is enabled
        config = _load_config()
        retrieval_config = config.get('retrieval', {})
        retrieval_enabled = retrieval_config.get('enabled', False)
        
        if retrieval_enabled and user_query:
            try:
                # Chunk, embed, and store
                tokens_per_chunk = retrieval_config.get('tokens_per_chunk', 2048)
                top_k = retrieval_config.get('top_k', 2)
                
                table_name, num_chunks, timings = _embed_and_store(url, markdown_content, tokens_per_chunk)
                
                # Retrieve relevant chunks based on user query
                retrieve_start = time.time()
                relevant_chunks = _retrieve_relevant_chunks(table_name, user_query, top_k)
                timings['retrieval'] = time.time() - retrieve_start
                
                # Combine chunks into filtered result
                filtered_content = f"# {title}\n\n" if title else ""
                filtered_content += "**Relevant content extracted from URL:**\n\n"
                
                for i, chunk in enumerate(relevant_chunks, 1):
                    filtered_content += f"## Excerpt {i}\n\n{chunk}\n\n"
                
                filtered_content += f"\n---\n**Source:** {url}\n"
                filtered_content += f"**Retrieved:** {len(relevant_chunks)} most relevant chunks out of {num_chunks} total chunks\n"
                filtered_content += f"**Timings:** Chunking: {timings['chunking']:.2f}s, Embedding: {timings['embedding']:.2f}s, Writing: {timings['writing_to_lancedb']:.2f}s, Retrieval: {timings['retrieval']:.2f}s, Total: {timings['total']:.2f}s\n"
                
                # Save to scratch
                _save_to_scratch(url, title, markdown_content)
                
                return {
                    "result": filtered_content,
                    "_metadata": {
                        "retrieval_enabled": True,
                        "table_name": table_name,
                        "num_chunks": num_chunks,
                        "chunks_returned": len(relevant_chunks),
                        "tokens_per_chunk": tokens_per_chunk,
                        "query": user_query,
                        "timings": timings
                    }
                }
            except Exception as e:
                # Fall back to returning full content if retrieval fails
                _save_to_scratch(url, title, markdown_content)
                return {
                    "result": markdown_content,
                    "_metadata": {
                        "retrieval_error": str(e),
                        "note": "Retrieval failed, returning full content"
                    }
                }
        
        # Save to scratch and return full content if retrieval is disabled or no query provided
        _save_to_scratch(url, title, markdown_content)
        return {"result": markdown_content}
        
    except requests.exceptions.RequestException as e:
        return {"error": f"Failed to fetch URL: {str(e)}"}
    except Exception as e:
        return {"error": f"Error processing URL: {str(e)}"}
