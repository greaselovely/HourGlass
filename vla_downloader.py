# vla_downloader.py

import re
import json
import hashlib
import requests
from time import sleep
from datetime import datetime
from pathlib import Path


class EnhancedImageDownloader:
    """
    Enhanced ImageDownloader with session recovery and batched config updates.
    
    Improvements over original:
    - Automatic session recovery on failures
    - Batched config writes to reduce I/O
    - Better error handling and logging
    - Exponential backoff for consecutive failures
    """

    def __init__(self, session, out_path, config, user_agents=None, proxies=None, webpage=None):
        self.out_path = Path(out_path)
        self.session = session
        self.config = config
        self.user_agents = user_agents or []
        self.proxies = proxies or {}
        self.webpage = webpage
        
        # Session recovery tracking
        self.session_failures = 0
        self.max_session_failures = 3
        
        # Config batching
        self.config_write_counter = 0
        self.config_write_interval = 10  # Write config every 10 updates instead of every update
        
        # Initialize image tracking
        self.prev_image_filename = self.get_last_image_filename()
        self.prev_image_size = None
        self.prev_image_hash = self.get_last_image_hash()
        self.repeated_hash_count = self.config['alerts'].get('repeated_hash_count', 0)
        
        # Failure tracking for exponential backoff
        self.consecutive_failures = 0
        self.max_consecutive_failures = 5

    def get_last_image_filename(self):
        """Get the filename of the most recent image."""
        image_files = sorted(self.out_path.glob('vla.*.jpg'))
        return image_files[-1].name if image_files else None

    def get_last_image_hash(self):
        """Get the hash of the most recent image."""
        if self.prev_image_filename:
            with open(self.out_path / self.prev_image_filename, 'rb') as f:
                return self.compute_hash(f.read())
        return None

    def compute_hash(self, image_content):
        """Compute SHA-256 hash of image content."""
        return hashlib.sha256(image_content).hexdigest()

    def recover_session(self):
        """
        Attempt to recover the session when it fails.
        Returns True if recovery successful, False otherwise.
        """
        try:
            from vla_core import create_session, message_processor
            from random import choice
            
            message_processor("Attempting session recovery...", "warning")
            
            new_session = create_session(self.user_agents, self.proxies, self.webpage)
            if new_session:
                self.session = new_session
                self.session_failures = 0
                message_processor("Session recovery successful", "info")
                return True
            else:
                self.session_failures += 1
                message_processor(f"Session recovery failed (attempt {self.session_failures})", "error")
                return False
                
        except Exception as e:
            message_processor(f"Session recovery error: {e}", "error")
            self.session_failures += 1
            return False

    def update_config(self, force_write=False):
        """
        Update config with batched writes to reduce I/O.
        Only writes to disk every config_write_interval updates or when forced.
        """
        self.config_write_counter += 1
        
        # Write to disk if interval reached, forced, or on significant milestones
        escalation_points = self.config.get('alerts', {}).get('escalation_points', [10, 50, 100, 500])
        should_write = (
            force_write or 
            self.config_write_counter >= self.config_write_interval or
            self.repeated_hash_count in escalation_points
        )
        
        if should_write:
            try:
                self.config['alerts']['repeated_hash_count'] = self.repeated_hash_count
                with open('config.json', 'w') as file:
                    json.dump(self.config, file, indent=2)
                self.config_write_counter = 0  # Reset counter after write
            except Exception as e:
                from vla_core import message_processor
                message_processor(f"Failed to update config: {e}", "error")

    def calculate_backoff_delay(self):
        """Calculate exponential backoff delay based on consecutive failures."""
        if self.consecutive_failures == 0:
            return 0
        
        # Exponential backoff: 2^failures seconds, capped at 300 seconds (5 minutes)
        delay = min(300, 2 ** self.consecutive_failures)
        return delay

    def download_image(self, image_url, retry_delay=5):
        """
        Enhanced image download with session recovery and exponential backoff.
        
        Args:
            image_url (str): URL of the image to download
            retry_delay (int): Base retry delay in seconds
            
        Returns:
            tuple: (image_size, filename) or (None, None) if failed
        """
        from vla_core import message_processor, GREEN_CIRCLE, RED_CIRCLE
        
        # Check if we need to apply exponential backoff
        backoff_delay = self.calculate_backoff_delay()
        if backoff_delay > 0:
            message_processor(f"Applying backoff delay: {backoff_delay} seconds", "warning")
            sleep(backoff_delay)
        
        escalation_points = self.config.get('alerts', {}).get('escalation_points', [10, 50, 100, 500])
        
        for attempt in range(2):
            try:
                # Attempt download
                r = self.session.get(image_url, timeout=30)
                
                if r is None or r.status_code != 200:
                    message_processor(f"{RED_CIRCLE} Code: {r.status_code if r else 'None'} - Request failed", "error")
                    
                    # Try session recovery if this looks like a session issue
                    if r is None or r.status_code in [403, 429, 502, 503, 504]:
                        if self.session_failures < self.max_session_failures:
                            if self.recover_session():
                                continue  # Retry with new session
                    
                    self.consecutive_failures += 1
                    return None, None

                image_content = r.content
                image_size = len(image_content)
                image_hash = self.compute_hash(image_content)

                if image_size == 0:
                    message_processor(f"{RED_CIRCLE} Code: {r.status_code} Zero Size", "error")
                    self.consecutive_failures += 1
                    return None, None

                # Check for hash collision
                if self.prev_image_hash == image_hash:
                    self.repeated_hash_count += 1

                    # Check escalation points for alerts
                    if self.repeated_hash_count in escalation_points:
                        message_processor(
                            f"Alert: Hash repeated {self.repeated_hash_count} times.",
                            "alert",
                            print_me=True,
                            ntfy=True
                        )

                    message_processor(
                        f"{RED_CIRCLE} Code: {r.status_code} Same Hash: {image_hash} "
                        f"(Repeated: {self.repeated_hash_count} times)",
                        "error",
                        print_me=True
                    )

                    # Update config (batched)
                    self.update_config()
                    
                    # Retry on first attempt
                    if attempt == 0:
                        self.consecutive_failures += 1
                        sleep(retry_delay)
                        continue
                    else:
                        return None, None
                else:
                    # Success! Reset failure counters
                    self.consecutive_failures = 0
                    self.session_failures = 0
                    
                    # Reset repeated hash count for new hash
                    self.repeated_hash_count = 0
                    message_processor(
                        f"{GREEN_CIRCLE} Code: {r.status_code} New Hash: {image_hash} "
                        f"(Repeated: {self.repeated_hash_count} times)"
                    )
                    
                    # Save the image
                    today_short_time = datetime.now().strftime("%H%M%S")
                    today_short_date = datetime.now().strftime("%m%d%Y")
                    filename = f'vla.{today_short_date}.{today_short_time}.jpg'
                    
                    with open(self.out_path / filename, 'wb') as f:
                        f.write(image_content)
                    
                    # Update tracking variables
                    self.prev_image_filename = filename
                    self.prev_image_size = image_size
                    self.prev_image_hash = image_hash
                    
                    # Update config (batched)
                    self.update_config()
                    
                    return image_size, filename

            except requests.RequestException as e:
                message_processor(f"Request exception: {e}", "error")
                self.consecutive_failures += 1
                
                # Try session recovery
                if self.session_failures < self.max_session_failures:
                    if self.recover_session():
                        continue  # Retry with new session
                
                if attempt == 0:
                    sleep(retry_delay)
                    continue
                else:
                    return None, None
                    
            except Exception as e:
                message_processor(f"Unexpected error in download_image: {e}", "error")
                self.consecutive_failures += 1
                return None, None

        # If we get here, both attempts failed
        return None, None

    def get_failure_stats(self):
        """Get current failure statistics for monitoring."""
        return {
            'consecutive_failures': self.consecutive_failures,
            'session_failures': self.session_failures,
            'repeated_hash_count': self.repeated_hash_count
        }

    def __del__(self):
        """Ensure config is written when object is destroyed."""
        self.update_config(force_write=True)