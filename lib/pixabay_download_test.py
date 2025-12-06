#!/usr/bin/env python3
"""
Interactive Pixabay audio download troubleshooting script.
Runs in a loop, pausing after each step to show status codes and allow inspection.

Usage:
    python lib/pixabay_download_test.py [config_name]

    config_name: Name of config file in configs/ (default: VLA)
"""

import sys
import os
import re
import json
from pathlib import Path
from time import sleep
from random import choice

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

try:
    import cloudscraper
except ImportError:
    print("ERROR: cloudscraper not installed. Run: pip install cloudscraper")
    sys.exit(1)

try:
    import requests
except ImportError:
    print("ERROR: requests not installed. Run: pip install requests")
    sys.exit(1)


def load_config(config_name="VLA"):
    """Load configuration from configs/ directory."""
    config_path = project_root / "configs" / f"{config_name}.json"
    if not config_path.exists():
        print(f"ERROR: Config file not found: {config_path}")
        sys.exit(1)

    with open(config_path, 'r') as f:
        return json.load(f)


def pause(message="Press Enter to continue (or 'q' to quit)..."):
    """Pause execution and wait for user input."""
    print(f"\n{'='*60}")
    response = input(f"{message} ")
    if response.lower() == 'q':
        print("Exiting...")
        sys.exit(0)
    print()


def print_response_info(response, step_name):
    """Print detailed response information."""
    print(f"\n--- {step_name} ---")
    print(f"  Status Code: {response.status_code}")
    print(f"  URL: {response.url}")
    print(f"  Content-Type: {response.headers.get('Content-Type', 'N/A')}")
    print(f"  Content-Length: {response.headers.get('Content-Length', 'N/A')}")

    # Check for common issues
    if response.status_code == 403:
        print("  WARNING: 403 Forbidden - likely blocked or rate limited")
        if 'cloudflare' in response.text.lower():
            print("  WARNING: Cloudflare challenge detected")
    elif response.status_code == 429:
        print("  WARNING: 429 Too Many Requests - rate limited")
    elif response.status_code >= 500:
        print("  WARNING: Server error")
    elif response.status_code == 200:
        print("  SUCCESS: Request successful")


def create_session(config):
    """Create a cloudscraper session with proxy config."""
    session = cloudscraper.create_scraper(
        browser={
            'browser': 'chrome',
            'platform': 'darwin',
            'desktop': True
        }
    )

    # Configure proxy if available
    if config and 'proxies' in config:
        socks5_hostname = config['proxies'].get('socks5_hostname', '')
        socks5 = config['proxies'].get('socks5', '')

        if socks5_hostname:
            proxy_url = f"socks5h://{socks5_hostname}"
            session.proxies = {'http': proxy_url, 'https': proxy_url}
            print(f"  Using SOCKS5 proxy (hostname resolution): {socks5_hostname}")
        elif socks5:
            proxy_url = f"socks5://{socks5}"
            session.proxies = {'http': proxy_url, 'https': proxy_url}
            print(f"  Using SOCKS5 proxy: {socks5}")
        elif config['proxies'].get('http') or config['proxies'].get('https'):
            session.proxies = {}
            if config['proxies'].get('http'):
                session.proxies['http'] = config['proxies']['http']
            if config['proxies'].get('https'):
                session.proxies['https'] = config['proxies']['https']
            print("  Using HTTP/HTTPS proxy")
        else:
            print("  No proxy configured")
    else:
        print("  No proxy configured")

    return session


def download_iteration(config, session, iteration, audio_cache_folder):
    """Run a single download iteration with pauses."""
    print(f"\n{'#'*60}")
    print(f"# ITERATION {iteration}")
    print(f"{'#'*60}")

    # Get config values
    music_config = config.get('music', {})
    base_url = music_config.get('pixabay_base_url', 'https://pixabay.com/music/search/')
    search_terms = music_config.get('search_terms', ['no copyright music'])
    search_term = search_terms[0] if search_terms else 'no copyright music'

    print(f"\nConfig values:")
    print(f"  Base URL: {base_url}")
    print(f"  Search term: {search_term}")
    print(f"  Audio cache folder: {audio_cache_folder}")

    pause("Ready to fetch page 1 HTML?")

    # Step 1: Fetch page 1 HTML
    page1_url = f"{base_url.rstrip('/')}/{search_term.replace(' ', '%20')}/"
    print(f"\nSTEP 1: Fetching page 1 HTML")
    print(f"  URL: {page1_url}")

    try:
        r = session.get(page1_url, timeout=30)
        print_response_info(r, "Page 1 HTML Response")

        if r.status_code != 200:
            print(f"\n  Response preview (first 500 chars):")
            print(f"  {r.text[:500]}")
            pause("Request failed. Continue to retry?")
            return False

    except Exception as e:
        print(f"  ERROR: {type(e).__name__}: {e}")
        pause("Request failed. Continue to retry?")
        return False

    pause("Page 1 fetched. Ready to extract bootstrap URL?")

    # Step 2: Extract bootstrap URL
    print(f"\nSTEP 2: Extracting bootstrap URL from HTML")
    html_content = r.text
    bootstrap_match = re.search(r"window\.__BOOTSTRAP_URL__\s*=\s*'([^']+)'", html_content)

    if not bootstrap_match:
        print("  ERROR: Could not find bootstrap URL in HTML")
        print(f"\n  Searching for alternative patterns...")

        # Try to find any JSON data URLs
        alt_matches = re.findall(r'https://pixabay\.com/[^"\']+\.json[^"\']*', html_content)
        if alt_matches:
            print(f"  Found {len(alt_matches)} potential JSON URLs:")
            for url in alt_matches[:5]:
                print(f"    - {url}")

        pause("Bootstrap URL not found. Continue to retry?")
        return False

    bootstrap_path = bootstrap_match.group(1)
    bootstrap_url = f"https://pixabay.com{bootstrap_path}"
    print(f"  Found bootstrap URL: {bootstrap_url}")

    pause("Ready to fetch bootstrap JSON?")

    # Step 3: Fetch bootstrap JSON
    print(f"\nSTEP 3: Fetching bootstrap JSON (waiting 5s first...)")
    sleep(5)

    try:
        r = session.get(bootstrap_url, timeout=30)
        print_response_info(r, "Bootstrap JSON Response")

        if r.status_code != 200:
            print(f"\n  Response preview (first 500 chars):")
            print(f"  {r.text[:500]}")
            pause("Request failed. Continue to retry?")
            return False

    except Exception as e:
        print(f"  ERROR: {type(e).__name__}: {e}")
        pause("Request failed. Continue to retry?")
        return False

    pause("Bootstrap JSON fetched. Ready to parse?")

    # Step 4: Parse JSON and get song list
    print(f"\nSTEP 4: Parsing bootstrap JSON")
    try:
        data = r.json()
        page_info = data.get('page', {})
        total_pages = page_info.get('pages', 1)
        results = page_info.get('results', [])

        print(f"  Total pages available: {total_pages}")
        print(f"  Songs on this page: {len(results)}")

        if not results:
            print("  ERROR: No songs found in results")
            pause("No songs found. Continue to retry?")
            return False

        # Show first few songs
        print(f"\n  Sample songs:")
        for i, song in enumerate(results[:3]):
            name = song.get('name', 'Unknown')
            duration = song.get('duration', 0)
            has_src = 'sources' in song and 'src' in song.get('sources', {})
            print(f"    {i+1}. {name[:40]}... ({duration}s) [has_src: {has_src}]")

    except json.JSONDecodeError as e:
        print(f"  ERROR: Failed to parse JSON: {e}")
        print(f"\n  Response preview (first 500 chars):")
        print(f"  {r.text[:500]}")
        pause("JSON parse failed. Continue to retry?")
        return False

    pause("Ready to select and download a random song?")

    # Step 5: Select random song
    print(f"\nSTEP 5: Selecting random song")
    song = choice(results)
    song_src = song.get('sources', {}).get('src')
    song_duration = song.get('duration', 0)
    song_name = song.get('name', 'Unknown Song')

    print(f"  Selected: {song_name}")
    print(f"  Duration: {song_duration} seconds")
    print(f"  Download URL: {song_src}")

    if not song_src:
        print("  ERROR: No source URL found for song")
        pause("No source URL. Continue to retry?")
        return False

    pause("Ready to download the audio file?")

    # Step 6: Download audio file
    print(f"\nSTEP 6: Downloading audio file (waiting 5s first...)")
    sleep(5)

    try:
        r = session.get(song_src, timeout=60)
        print_response_info(r, "Audio Download Response")

        if r.status_code != 200:
            pause("Download failed. Continue to retry?")
            return False

        # Check content type
        content_type = r.headers.get('Content-Type', '')
        if 'audio' not in content_type and 'octet-stream' not in content_type:
            print(f"  WARNING: Unexpected content type: {content_type}")

        print(f"  Downloaded {len(r.content)} bytes")

    except Exception as e:
        print(f"  ERROR: {type(e).__name__}: {e}")
        pause("Download failed. Continue to retry?")
        return False

    pause("Download complete. Ready to save file?")

    # Step 7: Save file
    print(f"\nSTEP 7: Saving audio file")

    # Ensure cache folder exists
    Path(audio_cache_folder).mkdir(parents=True, exist_ok=True)

    # Clean filename
    safe_name = re.sub(r'[^\w\s-]', '', song_name)[:50]
    audio_name = f"{safe_name}.mp3"
    full_path = Path(audio_cache_folder) / audio_name

    print(f"  Saving to: {full_path}")

    with open(full_path, 'wb') as f:
        f.write(r.content)

    file_size = full_path.stat().st_size
    print(f"  File saved! Size: {file_size} bytes ({file_size/1024:.1f} KB)")

    # Verify it's a valid MP3
    with open(full_path, 'rb') as f:
        header = f.read(3)
        if header == b'ID3' or header[:2] == b'\xff\xfb':
            print("  File appears to be valid MP3 (correct header)")
        else:
            print(f"  WARNING: File header doesn't look like MP3: {header}")

    print(f"\n{'='*60}")
    print(f"SUCCESS! Audio file downloaded and saved.")
    print(f"{'='*60}")

    return True


def main():
    print("="*60)
    print("Pixabay Audio Download - Interactive Troubleshooter")
    print("="*60)

    # Get config name from args
    config_name = sys.argv[1] if len(sys.argv) > 1 else "VLA"
    print(f"\nLoading config: {config_name}")

    config = load_config(config_name)
    print("  Config loaded successfully")

    # Get audio cache folder
    audio_cache_folder = config.get('files_and_folders', {}).get('AUDIO_CACHE_FOLDER', '')
    if not audio_cache_folder:
        audio_cache_folder = project_root / "audio_cache"
        print(f"  No AUDIO_CACHE_FOLDER in config, using: {audio_cache_folder}")

    print(f"\nCreating session...")
    session = create_session(config)

    iteration = 1
    successes = 0
    failures = 0

    while True:
        print(f"\n{'='*60}")
        print(f"Starting iteration {iteration} (Success: {successes}, Failed: {failures})")
        print(f"{'='*60}")

        pause(f"Ready to start iteration {iteration}?")

        try:
            success = download_iteration(config, session, iteration, audio_cache_folder)
            if success:
                successes += 1
            else:
                failures += 1
        except KeyboardInterrupt:
            print("\n\nInterrupted by user")
            break
        except Exception as e:
            print(f"\nUnexpected error: {type(e).__name__}: {e}")
            failures += 1

        iteration += 1

        print(f"\n{'='*60}")
        print(f"Iteration {iteration-1} complete.")
        print(f"Total: {successes} successes, {failures} failures")
        print(f"{'='*60}")

        response = input("\nContinue to next iteration? (Enter=yes, q=quit, n=new session): ")
        if response.lower() == 'q':
            break
        elif response.lower() == 'n':
            print("\nCreating new session...")
            session = create_session(config)

    print(f"\n{'='*60}")
    print(f"Session complete!")
    print(f"Total iterations: {iteration-1}")
    print(f"Successes: {successes}")
    print(f"Failures: {failures}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
