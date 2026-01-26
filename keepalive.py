#!/usr/bin/env python3
"""
Background task to keep the Render service alive using rotating proxies
Runs every 9 minutes to prevent the free tier from spinning down
"""
import sys
import time
import requests
import threading
from datetime import datetime, timedelta
from pathlib import Path

# Target URLs
PROXY_LIST_URL = "https://raw.githubusercontent.com/TheSpeedX/SOCKS-List/master/http.txt"
TARGET_URL = "https://skill-agent.onrender.com/health"
TEST_URL = "https://www.google.com"

# Task configuration
INTERVAL_SECONDS = 9 * 60  # 9 minutes
REQUEST_TIMEOUT = 10  # seconds for testing proxies
PING_TIMEOUT = 30  # seconds for pinging Render (longer for slower proxies)
MAX_PING_RETRIES = 3  # Retry pinging with same proxy if it fails

# Spinner characters
SPINNER_CHARS = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏']

# Data directory for persistent proxy cache
DATA_DIR = Path("data")
PROXY_LIST_FILE = DATA_DIR / "proxy_list.txt"
LAST_PROXY_FILE = DATA_DIR / "proxy_ip.txt"


def fetch_proxy_list():
    """Download the latest proxy list or load from cache"""
    # Try to load from cache first
    if PROXY_LIST_FILE.exists():
        try:
            with open(PROXY_LIST_FILE, 'r') as f:
                proxies = [line.strip() for line in f if line.strip() and ':' in line]
            if proxies:
                print(f"[Keepalive] ✓ Loaded {len(proxies)} proxies from cache")
                return proxies
        except Exception as e:
            print(f"[Keepalive] ⚠ Failed to load cached proxy list: {e}")
    
    # Download fresh list
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
        
        # Save to cache
        DATA_DIR.mkdir(exist_ok=True)
        with open(PROXY_LIST_FILE, 'w') as f:
            f.write('\n'.join(proxies))
        
        print(f"[Keepalive] ✓ Fetched and cached {len(proxies)} proxies")
        return proxies
    except Exception as e:
        print(f"[Keepalive] ✗ Failed to fetch proxy list: {e}")
        return []


def get_last_working_proxy():
    """Load the last working proxy from cache"""
    if LAST_PROXY_FILE.exists():
        try:
            with open(LAST_PROXY_FILE, 'r') as f:
                proxy = f.read().strip()
            if proxy and ':' in proxy:
                return proxy
        except Exception as e:
            print(f"[Keepalive] ⚠ Failed to load last proxy: {e}")
    return None


def save_last_working_proxy(proxy):
    """Save the working proxy to cache"""
    try:
        DATA_DIR.mkdir(exist_ok=True)
        with open(LAST_PROXY_FILE, 'w') as f:
            f.write(proxy)
    except Exception as e:
        print(f"[Keepalive] ⚠ Failed to save last proxy: {e}")


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


def find_working_proxy(proxies, start_index=0):
    """Find a working proxy starting from the given index"""
    max_proxies_to_test = 500
    proxies_tested = 0
    
    print(f"[Keepalive] Searching for working proxy (starting at index {start_index})...")
    
    for i in range(start_index, min(len(proxies), start_index + max_proxies_to_test)):
        proxy = proxies[i]
        proxies_tested += 1
        
        if test_proxy(proxy):
            print(f"[Keepalive] ✓ WORKS: {proxy} (index {i}, tested {proxies_tested} proxies)", flush=True)
            return proxy, i
    
    print(f"[Keepalive] ✗ No working proxy found after testing {proxies_tested} proxies", flush=True)
    return None, -1


def keepalive_task():
    """Main keepalive task - finds working proxy and pings service"""
    start_time = datetime.now()
    print(f"\n{'='*80}")
    print(f"[Keepalive] Task started at {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*80}")
    
    # Fetch proxy list (from cache or download)
    proxies = fetch_proxy_list()
    if not proxies:
        print("[Keepalive] ✗ No proxies available, skipping this run")
        return False
    
    # Try the last working proxy first
    last_proxy = get_last_working_proxy()
    working_proxy = None
    
    if last_proxy:
        print(f"[Keepalive] Trying last working proxy: {last_proxy}")
        success = ping_service_via_proxy(last_proxy)
        
        if success:
            print(f"[Keepalive] ✓ Last proxy still works!")
            working_proxy = last_proxy
        else:
            print(f"[Keepalive] ✗ Last proxy failed after {MAX_PING_RETRIES} retries, searching for new one...")
            
            # Find position of failed proxy in list
            try:
                last_index = proxies.index(last_proxy)
                print(f"[Keepalive] Last proxy was at index {last_index}, starting search after that...")
                working_proxy, _ = find_working_proxy(proxies, start_index=last_index + 1)
            except ValueError:
                # Last proxy not in current list, start from beginning
                print(f"[Keepalive] Last proxy not in current list, starting from beginning...")
                working_proxy, _ = find_working_proxy(proxies, start_index=0)
    else:
        print(f"[Keepalive] No cached proxy, searching for working one...")
        working_proxy, _ = find_working_proxy(proxies, start_index=0)
    
    if not working_proxy:
        print(f"[Keepalive] ✗ No working proxy found")
        return False
    
    # If we found a new proxy, ping the service
    if working_proxy != last_proxy:
        success = ping_service_via_proxy(working_proxy)
        if not success:
            return False
    
    # Save the working proxy
    save_last_working_proxy(working_proxy)
    
    elapsed = datetime.now() - start_time
    print(f"[Keepalive] Task completed in {elapsed.total_seconds():.1f}s")
    print(f"{'='*80}\n")
    
    return True


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
