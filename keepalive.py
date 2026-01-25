#!/usr/bin/env python3
"""
Background task to keep the Render service alive using rotating proxies
Runs every 10 minutes to prevent the free tier from spinning down
"""
import sys
import time
import requests
import threading
from datetime import datetime, timedelta

# Target URLs
PROXY_LIST_URL = "https://raw.githubusercontent.com/TheSpeedX/SOCKS-List/master/http.txt"
TARGET_URL = "https://skill-agent.onrender.com/health"
TEST_URL = "https://www.google.com"

# Task configuration
INTERVAL_SECONDS = 10 * 60  # 10 minutes
REQUEST_TIMEOUT = 10  # seconds for testing proxies
PING_TIMEOUT = 30  # seconds for pinging Render (longer for slower proxies)
MAX_PING_RETRIES = 2  # Retry pinging with same proxy if it fails

# Spinner characters
SPINNER_CHARS = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏']


def fetch_proxy_list():
    """Download the latest proxy list"""
    try:
        print(f"[Keepalive] Downloading proxy list from {PROXY_LIST_URL}...")
        response = requests.get(PROXY_LIST_URL, timeout=30)
        response.raise_for_status()
        
        # Parse proxies (format: IP:PORT)
        proxies = []
        for line in response.text.strip().split('\n'):
            line = line.strip()
            if line and ':' in line:
                proxies.append(line)
        
        print(f"[Keepalive] ✓ Fetched {len(proxies)} proxies")
        return proxies
    except Exception as e:
        print(f"[Keepalive] ✗ Failed to fetch proxy list: {e}")
        return []


def test_proxy(proxy):
    """Test if a proxy works by trying to load Google"""
    try:
        proxy_dict = {
            'http': f'http://{proxy}',
            'https': f'http://{proxy}'
        }
        
        response = requests.get(
            TEST_URL,
            proxies=proxy_dict,
            timeout=REQUEST_TIMEOUT,
            headers={'User-Agent': 'Mozilla/5.0'}
        )
        
        return response.status_code == 200
    except:
        return False


def ping_service_via_proxy(proxy):
    """Ping the Render service using a working proxy"""
    for attempt in range(MAX_PING_RETRIES):
        try:
            proxy_dict = {
                'http': f'http://{proxy}',
                'https': f'http://{proxy}'
            }
            
            retry_msg = f" (retry {attempt + 1}/{MAX_PING_RETRIES})" if attempt > 0 else ""
            print(f"[Keepalive] Pinging {TARGET_URL} via proxy {proxy}{retry_msg}...")
            
            response = requests.get(
                TARGET_URL,
                proxies=proxy_dict,
                timeout=PING_TIMEOUT,
                headers={'User-Agent': 'Mozilla/5.0'}
            )
            
            print(f"[Keepalive] ✓ Successfully pinged {TARGET_URL} - Status: {response.status_code}")
            return True
            
        except Exception as e:
            if attempt < MAX_PING_RETRIES - 1:
                print(f"[Keepalive] ⚠ Attempt {attempt + 1} failed, retrying...")
                continue
            else:
                print(f"[Keepalive] ✗ Failed to ping via {proxy} after {MAX_PING_RETRIES} attempts: {e}")
                return False
    
    return False


def keepalive_task():
    """Main keepalive task - finds working proxy and pings service"""
    start_time = datetime.now()
    print(f"\n{'='*80}")
    print(f"[Keepalive] Task started at {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*80}")
    
    # Fetch proxy list
    proxies = fetch_proxy_list()
    if not proxies:
        print("[Keepalive] ✗ No proxies available, skipping this run")
        return False
    
    # Try proxies until one works
    working_proxy = None
    proxies_tested = 0
    max_proxies_to_test = 500
    
    print(f"[Keepalive] Testing up to {max_proxies_to_test} proxies to find a working one...")
    
    for proxy in proxies[:max_proxies_to_test]:
        proxies_tested += 1
        
        # Show spinner with progress
        spinner_char = SPINNER_CHARS[proxies_tested % len(SPINNER_CHARS)]
        sys.stdout.write(f"\r[Keepalive] {spinner_char} Testing proxies... {proxies_tested}/{max_proxies_to_test}")
        sys.stdout.flush()
        
        if test_proxy(proxy):
            # Clear the spinner line and show success
            sys.stdout.write(f"\r\x1b[2K")  # Clear line
            sys.stdout.flush()
            print(f"[Keepalive] ✓ WORKS: {proxy} (found after testing {proxies_tested} proxies)")
            working_proxy = proxy
            break
    
    if not working_proxy:
        # Clear the spinner line and show failure
        sys.stdout.write(f"\r\x1b[2K")  # Clear line
        sys.stdout.flush()
        print(f"[Keepalive] ✗ No working proxy found after testing {proxies_tested} proxies")
        return False
    
    # Use the working proxy to ping the service
    success = ping_service_via_proxy(working_proxy)
    
    elapsed = datetime.now() - start_time
    print(f"[Keepalive] Task completed in {elapsed.total_seconds():.1f}s")
    print(f"{'='*80}\n")
    
    return success


def run_keepalive_loop():
    """Run the keepalive task in a loop"""
    print(f"\n{'='*80}")
    print(f"[Keepalive] Background keepalive service starting")
    print(f"[Keepalive] Interval: {INTERVAL_SECONDS} seconds ({INTERVAL_SECONDS//60} minutes)")
    print(f"{'='*80}\n")
    
    # Run immediately on startup
    print(f"[Keepalive] Running initial keepalive task at startup...")
    try:
        keepalive_task()
    except Exception as e:
        print(f"[Keepalive] ✗ Error in initial task: {e}")
    
    # Calculate and display next run time
    next_run = datetime.now() + timedelta(seconds=INTERVAL_SECONDS)
    print(f"[Keepalive] ⏰ Next run scheduled for: {next_run.strftime('%Y-%m-%d %H:%M:%S')}")
    
    while True:
        # Wait for next interval
        time.sleep(INTERVAL_SECONDS)
        
        try:
            keepalive_task()
        except Exception as e:
            print(f"[Keepalive] ✗ Error in task: {e}")
        
        # Calculate and display next run time
        next_run = datetime.now() + timedelta(seconds=INTERVAL_SECONDS)
        print(f"[Keepalive] ⏰ Next run scheduled for: {next_run.strftime('%Y-%m-%d %H:%M:%S')}")


def start_keepalive_thread():
    """Start the keepalive task in a background thread"""
    thread = threading.Thread(target=run_keepalive_loop, daemon=True)
    thread.start()
    print("[Keepalive] ✓ Background thread started\n")


if __name__ == "__main__":
    # For testing: run once
    keepalive_task()
