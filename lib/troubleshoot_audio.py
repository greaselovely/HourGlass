#!/usr/bin/env python3
"""
Troubleshooting script for audio download issues on Ubuntu/Linux servers.
This script tests various methods to access Pixabay to diagnose 403 errors.
"""

import sys
import time
import json
import requests
import subprocess
from pathlib import Path

def test_with_curl():
    """Test Pixabay access using curl command."""
    print("\n" + "="*60)
    print("Testing with CURL")
    print("="*60)
    
    test_urls = [
        "https://pixabay.com",
        "https://pixabay.com/music/",
        "https://pixabay.com/music/search/background%20music/"
    ]
    
    for url in test_urls:
        print(f"\nTesting: {url}")
        try:
            result = subprocess.run(
                ["curl", "-I", "-s", "-o", "/dev/null", "-w", "%{http_code}\\n%{url_effective}\\n", url],
                capture_output=True,
                text=True,
                timeout=10
            )
            lines = result.stdout.strip().split('\n')
            status_code = lines[0] if lines else "Unknown"
            effective_url = lines[1] if len(lines) > 1 else url
            
            print(f"  Status: {status_code}")
            if effective_url != url:
                print(f"  Redirected to: {effective_url}")
                
        except Exception as e:
            print(f"  Error: {e}")

def test_with_requests():
    """Test Pixabay access using Python requests library."""
    print("\n" + "="*60)
    print("Testing with Python Requests")
    print("="*60)
    
    headers_list = [
        {
            "name": "Default",
            "headers": {}
        },
        {
            "name": "Chrome Linux",
            "headers": {
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            }
        },
        {
            "name": "Firefox Ubuntu",
            "headers": {
                "User-Agent": "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:109.0) Gecko/20100101 Firefox/121.0"
            }
        },
        {
            "name": "Curl",
            "headers": {
                "User-Agent": "curl/7.68.0"
            }
        }
    ]
    
    url = "https://pixabay.com/music/"
    
    for header_set in headers_list:
        print(f"\nTesting with {header_set['name']} headers:")
        try:
            response = requests.get(url, headers=header_set['headers'], timeout=10, allow_redirects=True)
            print(f"  Status: {response.status_code}")
            print(f"  Final URL: {response.url}")
            
            # Check for Cloudflare challenge
            if "cloudflare" in response.text.lower() and response.status_code == 403:
                print("  Cloudflare Challenge Detected!")
            elif response.status_code == 200:
                print("  Success! This configuration works.")
                
        except requests.exceptions.Timeout:
            print("  Timeout!")
        except Exception as e:
            print(f"  Error: {e}")

def test_with_cloudscraper():
    """Test using cloudscraper to bypass Cloudflare."""
    print("\n" + "="*60)
    print("Testing with CloudScraper")
    print("="*60)
    
    try:
        import cloudscraper
    except ImportError:
        print("CloudScraper not installed. Install with: pip install cloudscraper")
        return
    
    browsers = [
        {'browser': 'chrome', 'platform': 'linux', 'desktop': True},
        {'browser': 'firefox', 'platform': 'linux', 'desktop': True},
        {'browser': 'chrome', 'platform': 'darwin', 'desktop': True},
    ]
    
    url = "https://pixabay.com/music/search/background%20music/"
    
    for browser_config in browsers:
        print(f"\nTesting with {browser_config}:")
        try:
            scraper = cloudscraper.create_scraper(browser=browser_config)
            response = scraper.get(url, timeout=15)
            print(f"  Status: {response.status_code}")
            
            if response.status_code == 200:
                print("  Success! This configuration works.")
                # Check if we can find the bootstrap URL
                if "window.__BOOTSTRAP_URL__" in response.text:
                    print("  Bootstrap URL found - full functionality available")
            elif response.status_code == 403:
                print("  Still blocked (403)")
                # Save response for analysis
                debug_file = f"debug_403_{browser_config['browser']}_{browser_config['platform']}.html"
                with open(debug_file, 'w') as f:
                    f.write(response.text)
                print(f"  Response saved to: {debug_file}")
                
        except Exception as e:
            print(f"  Error: {e}")

def check_ip_reputation():
    """Check if the server's IP might be blocked."""
    print("\n" + "="*60)
    print("IP Reputation Check")
    print("="*60)
    
    try:
        # Get public IP
        ip_response = requests.get('https://api.ipify.org?format=json', timeout=5)
        public_ip = ip_response.json()['ip']
        print(f"\nPublic IP: {public_ip}")
        
        # Check IP info
        info_response = requests.get(f'https://ipapi.co/{public_ip}/json/', timeout=5)
        ip_info = info_response.json()
        
        print(f"Location: {ip_info.get('city', 'Unknown')}, {ip_info.get('country_name', 'Unknown')}")
        print(f"ISP: {ip_info.get('org', 'Unknown')}")
        
        # Check if it's a known VPS/Cloud provider
        org = ip_info.get('org', '').lower()
        cloud_providers = ['amazon', 'aws', 'digitalocean', 'linode', 'vultr', 'google', 'azure', 'ovh']
        
        for provider in cloud_providers:
            if provider in org:
                print(f"\nWARNING: IP belongs to {provider.upper()} - may be blocked by Pixabay")
                print("Consider using residential proxy or VPN")
                break
                
    except Exception as e:
        print(f"Could not check IP: {e}")

def suggest_solutions():
    """Provide solution suggestions based on test results."""
    print("\n" + "="*60)
    print("Troubleshooting Suggestions")
    print("="*60)
    
    print("""
1. **If getting 403 errors:**
   - Your server IP may be blocked by Pixabay
   - Try using a proxy or VPN
   - Consider using a residential IP proxy service
   
2. **Configure proxy in HourGlass:**
   Edit your project config file and add:
   ```json
   "proxies": {
     "http": "http://proxy-server:port",
     "https": "http://proxy-server:port"
   }
   ```
   
3. **Use SOCKS proxy with proxychains:**
   ```bash
   # Install proxychains
   sudo apt-get install proxychains4
   
   # Configure /etc/proxychains4.conf
   # Add your SOCKS proxy at the end
   
   # Run HourGlass through proxy
   proxychains4 python main.py <project> --test-audio
   ```
   
4. **Alternative: Use a different audio source**
   Consider implementing fallback to other royalty-free music sources:
   - Freesound.org API
   - YouTube Audio Library
   - Free Music Archive
   
5. **Rate limiting workaround:**
   - Add longer delays between requests
   - Implement exponential backoff
   - Cache successful downloads for reuse
""")

def main():
    """Run all tests."""
    print("="*60)
    print("Pixabay Audio Download Troubleshooter")
    print("="*60)
    
    # Check Python version
    print(f"\nPython version: {sys.version}")
    
    # Run tests
    test_with_curl()
    test_with_requests()
    test_with_cloudscraper()
    check_ip_reputation()
    suggest_solutions()
    
    print("\n" + "="*60)
    print("Troubleshooting Complete")
    print("="*60)

if __name__ == "__main__":
    main()