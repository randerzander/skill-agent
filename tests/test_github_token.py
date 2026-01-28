#!/usr/bin/env python3
"""
Test script to verify GitHub token authentication is working
"""
import os
import sys
import json
from pathlib import Path
from dotenv import load_dotenv

# Add parent directory to path for imports
parent_dir = Path(__file__).parent.parent
sys.path.insert(0, str(parent_dir))

# Load environment variables from parent directory
load_dotenv(parent_dir / '.env')

# Add skills directory to path
sys.path.insert(0, str(parent_dir / 'skills' / 'web' / 'scripts'))

def test_github_token():
    """Test GitHub token authentication"""
    print("=" * 80)
    print("GITHUB TOKEN AUTHENTICATION TEST")
    print("=" * 80)
    
    # Check if token is set
    github_token = os.getenv('GITHUB_TOKEN')
    if not github_token:
        print("❌ GITHUB_TOKEN not found in environment")
        print("\nPlease add GITHUB_TOKEN to your .env file:")
        print("  GITHUB_TOKEN=ghp_yourTokenHere")
        return False
    
    # Mask token for display
    masked_token = github_token[:7] + "..." + github_token[-4:] if len(github_token) > 11 else "***"
    print(f"✓ GITHUB_TOKEN found: {masked_token}")
    print()
    
    # Import the read_url function
    try:
        from tools import read_url, _is_github_url
        print("✓ Successfully imported tools")
    except ImportError as e:
        print(f"❌ Failed to import tools: {e}")
        return False
    
    print()
    print("-" * 80)
    print("TEST 1: GitHub URL Detection")
    print("-" * 80)
    
    test_urls = [
        ("https://github.com/torvalds/linux", True, "GitHub repo"),
        ("https://raw.githubusercontent.com/torvalds/linux/master/README", True, "Raw GitHub content"),
        ("https://api.github.com/repos/torvalds/linux", True, "GitHub API"),
        ("https://example.com", False, "Non-GitHub URL"),
    ]
    
    for url, expected, description in test_urls:
        result = _is_github_url(url)
        status = "✓" if result == expected else "❌"
        print(f"{status} {description}: {url}")
        print(f"   Detected as GitHub: {result}")
    
    print()
    print("-" * 80)
    print("TEST 2: Authenticated GitHub API Request")
    print("-" * 80)
    
    # Test with GitHub API endpoint to verify authentication
    test_url = "https://api.github.com/user"
    print(f"Requesting: {test_url}")
    print("This endpoint requires authentication and returns your GitHub user info")
    print()
    
    import requests
    
    # Test without auth
    print("→ Testing WITHOUT authentication...")
    response_no_auth = requests.get(test_url, headers={'User-Agent': 'SkillAgent'})
    print(f"  Status: {response_no_auth.status_code}")
    if response_no_auth.status_code == 401:
        print("  ✓ Correctly requires authentication (401 Unauthorized)")
    
    # Test with auth
    print()
    print("→ Testing WITH authentication...")
    response_with_auth = requests.get(
        test_url,
        headers={
            'User-Agent': 'SkillAgent',
            'Authorization': f'token {github_token}'
        }
    )
    print(f"  Status: {response_with_auth.status_code}")
    
    if response_with_auth.status_code == 200:
        user_data = response_with_auth.json()
        print(f"  ✓ Authentication successful!")
        print(f"  GitHub User: {user_data.get('login', 'unknown')}")
        print(f"  Name: {user_data.get('name', 'N/A')}")
        print(f"  Public Repos: {user_data.get('public_repos', 'N/A')}")
        
        # Check rate limit
        rate_limit = response_with_auth.headers.get('X-RateLimit-Remaining')
        rate_limit_total = response_with_auth.headers.get('X-RateLimit-Limit')
        if rate_limit:
            print(f"  Rate Limit: {rate_limit}/{rate_limit_total} remaining")
    else:
        print(f"  ❌ Authentication failed")
        print(f"  Response: {response_with_auth.text[:200]}")
        return False
    
    print()
    print("-" * 80)
    print("TEST 3: read_url() with GitHub Content")
    print("-" * 80)
    
    # Test reading a public GitHub file
    test_file_url = "https://raw.githubusercontent.com/torvalds/linux/master/README"
    print(f"Reading: {test_file_url}")
    print()
    
    result = read_url(test_file_url)
    result_data = json.loads(result)
    
    if "error" in result_data:
        print(f"❌ Error: {result_data['error']}")
        return False
    
    if "result" in result_data:
        content = result_data['result'].get('content', '')
        title = result_data['result'].get('title', '')
        print(f"✓ Successfully read content")
        print(f"  Title: {title}")
        print(f"  Content length: {len(content)} characters")
        print(f"  Preview: {content[:150]}...")
    
    print()
    print("-" * 80)
    print("TEST 4: Rate Limit Check")
    print("-" * 80)
    
    # Check current rate limit
    rate_limit_url = "https://api.github.com/rate_limit"
    response = requests.get(
        rate_limit_url,
        headers={
            'User-Agent': 'SkillAgent',
            'Authorization': f'token {github_token}'
        }
    )
    
    if response.status_code == 200:
        rate_data = response.json()
        core = rate_data.get('resources', {}).get('core', {})
        limit = core.get('limit', 0)
        remaining = core.get('remaining', 0)
        
        print(f"✓ Rate Limit Info:")
        print(f"  Total: {limit} requests/hour")
        print(f"  Remaining: {remaining} requests")
        print(f"  Used: {limit - remaining} requests")
        
        if limit >= 5000:
            print(f"  ✓ Authenticated rate limit active (5000/hour)")
        else:
            print(f"  ⚠ Using lower rate limit ({limit}/hour)")
    
    print()
    print("=" * 80)
    print("✅ ALL TESTS PASSED - GitHub token is working correctly!")
    print("=" * 80)
    
    return True


if __name__ == "__main__":
    try:
        success = test_github_token()
        sys.exit(0 if success else 1)
    except Exception as e:
        print()
        print("=" * 80)
        print(f"❌ TEST FAILED WITH ERROR")
        print("=" * 80)
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
