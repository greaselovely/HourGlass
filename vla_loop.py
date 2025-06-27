# vla_loop.py

import cursor
import logging
from time import sleep
from random import choice
from datetime import datetime


class VLAMainLoop:
    """
    Enhanced main loop with sophisticated error handling, exponential backoff,
    and resilient session management.
    
    Features:
    - Exponential backoff for consecutive failures
    - Session recovery and recreation
    - Failure pattern detection
    - Graceful degradation under stress
    - Comprehensive error categorization
    """
    
    def __init__(self, config, user_agents, proxies, webpage, image_url):
        self.config = config
        self.user_agents = user_agents
        self.proxies = proxies
        self.webpage = webpage
        self.image_url = image_url
        
        # Failure tracking (for statistics and recovery, not for giving up)
        self.consecutive_failures = 0
        self.session_recreation_count = 0
        self.max_session_recreations = 5
        
        # Timing and backoff
        self.base_sleep_seconds = (15, 22)  # Your original range
        self.current_sleep_range = self.base_sleep_seconds
        self.max_backoff_seconds = 300  # 5 minutes max
        
        # Error categorization
        self.error_counts = {
            'network': 0,
            'session': 0,
            'image': 0,
            'unexpected': 0
        }
        
        # State tracking
        self.last_success_time = datetime.now()
        self.loop_iteration = 0
        
    def run_main_loop(self, downloader, run_images_folder, target_hour, target_minute, 
                     main_sequence_callback, run_valid_images_file, video_path, run_audio_folder,
                     test_mode=False):
        """
        Execute the main image capture loop witherror handling.
        
        Args:
            downloader: Image downloader instance
            run_images_folder: Directory for storing images
            target_hour: Hour to stop capturing
            target_minute: Minute to stop capturing  
            main_sequence_callback: Function to call when creating video
            run_valid_images_file: Path to validation file
            video_path: Path for output video
            run_audio_folder: Directory for audio files
            test_mode: Whether running in test mode (--no-time-check)
        """
        from vla_core import message_processor, activity, clear, RED_CIRCLE
        import os
        
        try:
            clear()
            cursor.hide()
            
            # Count existing images to continue iteration from the right number
            try:
                existing_images = len([f for f in os.listdir(run_images_folder) if f.lower().endswith('.jpg')])
                self.loop_iteration = existing_images + 1  # Start from next number
                message_processor(f"Found {existing_images} existing images, starting iteration at {self.loop_iteration}")
            except Exception:
                self.loop_iteration = 1  # Fallback to 1 if folder doesn't exist yet
            
            # Dynamic message based on mode
            if test_mode:
                message_processor(f"Startingmain loop (test mode until {target_hour:02d}:{target_minute:02d})", "info")
            else:
                message_processor(f"Startingmain loop (runs until sunset)", "info")
            
            while True:
                try:
                    # Apply backoff delay if needed
                    backoff_delay = self._calculate_backoff_delay()
                    if backoff_delay > 0:
                        message_processor(f"Applying backoff: {backoff_delay}s", "warning")
                        sleep(backoff_delay)
                    
                    # Attempt image download
                    image_size, filename = downloader.download_image(self.image_url)
                    
                    if image_size is not None:
                        # Success!
                        self._handle_successful_download(image_size, run_images_folder)
                    else:
                        # Download failed
                        self._handle_failed_download(downloader, run_images_folder)
                    
                    # Check exit conditions - ONLY sunset time, no failure limits
                    now = datetime.now()
                    if now.hour == target_hour and now.minute >= target_minute:
                        message_processor("Target time reached. Creating final video.", "info", ntfy=True)
                        main_sequence_callback(run_images_folder, video_path, run_audio_folder, run_valid_images_file)
                        break
                    
                    # Dynamic sleep based on current state
                    sleep_time = self._calculate_sleep_time()
                    sleep(sleep_time)
                    
                except KeyboardInterrupt:
                    message_processor("Keyboard interrupt received", "warning")
                    self._handle_keyboard_interrupt(
                        main_sequence_callback, run_images_folder, video_path, 
                        run_audio_folder, run_valid_images_file
                    )
                    break
                    
                except Exception as e:
                    self._handle_unexpected_error(e, downloader)
                    
        finally:
            cursor.show()
            self._log_session_summary()
    
    def _handle_successful_download(self, image_size, run_images_folder):
        """Handle successful image download."""
        from vla_core import activity
        
        # Reset failure counters on success
        self.consecutive_failures = 0
        self.session_recreation_count = 0
        self.last_success_time = datetime.now()
        
        # Reset sleep range to normal
        self.current_sleep_range = self.base_sleep_seconds
        
        # Update activity display
        activity(self.loop_iteration, run_images_folder, image_size)
        
        # Increment iteration counter
        self.loop_iteration += 1
    
    def _handle_failed_download(self, downloader, run_images_folder):
        """Handle failed image download with categorized error handling."""
        from vla_core import message_processor, clear, RED_CIRCLE
        
        self.consecutive_failures += 1
        
        # Get failure stats from downloader if available
        if hasattr(downloader, 'get_failure_stats'):
            stats = downloader.get_failure_stats()
            downloader_failures = stats.get('consecutive_failures', 0)
            session_failures = stats.get('session_failures', 0)
            
            # Categorize the error
            if session_failures > 0:
                self.error_counts['session'] += 1
                error_type = 'session'
            elif downloader_failures > 0:
                self.error_counts['network'] += 1
                error_type = 'network'
            else:
                self.error_counts['image'] += 1
                error_type = 'image'
        else:
            self.error_counts['network'] += 1
            error_type = 'network'
        
        # Display failure info
        clear()
        message_processor(
            f"{RED_CIRCLE} Iteration: {self.loop_iteration} "
            f"(Consecutive failures: {self.consecutive_failures}, Type: {error_type})",
            "error"
        )
        
        # Try session recreation if we have too many session failures
        if (error_type == 'session' and 
            self.session_recreation_count < self.max_session_recreations and
            self.consecutive_failures % 3 == 0):  # Every 3rd failure
            
            self._attempt_session_recreation(downloader)
        
        # Extend sleep range for persistent failures
        if self.consecutive_failures > 5:
            min_sleep, max_sleep = self.current_sleep_range
            self.current_sleep_range = (min_sleep * 2, min(max_sleep * 2, 120))
        
        # Increment iteration counter even on failure
        self.loop_iteration += 1
    
    def _attempt_session_recreation(self, downloader):
        """Attempt to recreate the session."""
        from vla_core import message_processor, create_session
        
        try:
            message_processor("Attempting session recreation...", "warning")
            
            new_session = create_session(self.user_agents, self.proxies, self.webpage)
            if new_session:
                downloader.session = new_session
                self.session_recreation_count += 1
                message_processor(
                    f"Session recreated successfully (attempt {self.session_recreation_count})", 
                    "info"
                )
            else:
                message_processor("Session recreation failed", "error")
                
        except Exception as e:
            message_processor(f"Session recreation error: {e}", "error")
    
    def _handle_unexpected_error(self, error, downloader):
        """Handle unexpected errors in the main loop."""
        from vla_core import message_processor, log_jamming
        
        self.consecutive_failures += 1
        self.error_counts['unexpected'] += 1
        
        error_message = f"Unexpected error in main loop (iteration {self.loop_iteration}): {error}"
        message_processor(log_jamming(error_message), "error")
        
        # Try to recover by recreating the downloader
        if self.consecutive_failures % 5 == 0:  # Every 5th unexpected error
            try:
                message_processor("Attempting downloader recovery...", "warning")
                # This would need to be implemented based on your downloader class
                if hasattr(downloader, 'recover_session'):
                    downloader.recover_session()
            except Exception as recovery_error:
                message_processor(f"Recovery attempt failed: {recovery_error}", "error")
        
        # Increment iteration counter
        self.loop_iteration += 1
    
    def _handle_keyboard_interrupt(self, main_sequence_callback, run_images_folder, 
                                 video_path, run_audio_folder, run_valid_images_file):
        """Handle keyboard interrupt gracefully."""
        from vla_core import message_processor
        
        try:
            message_processor("Processing existing images into video...", "info", ntfy=True)
            main_sequence_callback(run_images_folder, video_path, run_audio_folder, run_valid_images_file)
        except Exception as e:
            message_processor(f"Error during interrupt handling: {e}", "error")
            # Fallback attempt
            try:
                main_sequence_callback(run_images_folder, video_path, run_audio_folder, run_valid_images_file)
            except Exception as fallback_error:
                message_processor(f"Fallback video creation also failed: {fallback_error}", "error", ntfy=True)
    
    def _attempt_final_video_creation(self, main_sequence_callback, run_images_folder, 
                                    video_path, run_audio_folder, run_valid_images_file):
        """Attempt to create final video when exiting due to failures."""
        from vla_core import message_processor
        
        try:
            message_processor("Attempting final video creation...", "info")
            main_sequence_callback(run_images_folder, video_path, run_audio_folder, run_valid_images_file)
        except Exception as e:
            message_processor(f"Final video creation failed: {e}", "error", ntfy=True)
    
    def _calculate_backoff_delay(self):
        """Calculate exponential backoff delay based on consecutive failures."""
        if self.consecutive_failures <= 1:
            return 0
        
        # Exponential backoff: 2^(failures-1) seconds, capped at max_backoff_seconds
        delay = min(self.max_backoff_seconds, 2 ** (self.consecutive_failures - 1))
        return delay
    
    def _calculate_sleep_time(self):
        """Calculate sleep time between iterations based on current state."""
        min_sleep, max_sleep = self.current_sleep_range
        return choice(range(int(min_sleep), int(max_sleep) + 1))
    
    def _log_session_summary(self):
        """Log a summary of the session."""
        from vla_core import message_processor
        
        duration = datetime.now() - self.last_success_time
        
        summary = (
            f"Session Summary:\n"
            f"  Total iterations: {self.loop_iteration}\n"
            f"  Session recreations: {self.session_recreation_count}\n"
            f"  Final consecutive failures: {self.consecutive_failures}\n"
            f"  Error breakdown: {self.error_counts}\n"
            f"  Time since last success: {duration}"
        )
        
        message_processor(summary, "info")
        logging.info(summary)


def create_vla_main_loop(config, user_agents, proxies, webpage, image_url):
    """
    Factory function to create a configured VLAMainLoop instance.
    
    Args:
        config: Application configuration
        user_agents: List of user agent strings
        proxies: Proxy configuration
        webpage: Webpage URL for session validation
        image_url: Image URL for downloading
        
    Returns:
        VLAMainLoop: Configured main loop instance
    """
    return VLAMainLoop(config, user_agents, proxies, webpage, image_url)


def enhanced_main_loop_simple(downloader, run_images_folder, target_hour, target_minute,
                             main_sequence_callback, run_valid_images_file, video_path, 
                             run_audio_folder):
    """
    Simplified enhanced main loop for drop-in replacement.
    Runs until sunset time - no failure limits.
    """
    from vla_core import message_processor, activity, clear, RED_CIRCLE
    from random import choice
    import cursor
    import os
    
    consecutive_failures = 0
    
    # Count existing images to continue iteration from the right number
    try:
        existing_images = len([f for f in os.listdir(run_images_folder) if f.lower().endswith('.jpg')])
        iteration = existing_images + 1  # Start from next number
        message_processor(f"Found {existing_images} existing images, starting iteration at {iteration}")
    except Exception:
        iteration = 1  # Fallback to 1 if folder doesn't exist yet
    
    try:
        clear()
        cursor.hide()
        
        while True:
            try:
                # Apply exponential backoff if needed
                if consecutive_failures > 0:
                    backoff_delay = min(300, 2 ** consecutive_failures)
                    if backoff_delay > 5:  # Only log significant delays
                        message_processor(f"Applying backoff: {backoff_delay}s", "warning")
                        sleep(backoff_delay)
                
                # Attempt download (no failure limit - keep trying until sunset)
                image_size, filename = downloader.download_image()
                
                if image_size is not None:
                    consecutive_failures = 0  # Reset on success
                    activity(iteration, run_images_folder, image_size)
                else:
                    consecutive_failures += 1
                    clear()
                    print(f"[!]\t{RED_CIRCLE} Iteration: {iteration} (Consecutive failures: {consecutive_failures})")
                
                iteration += 1
                
                # Check exit condition - ONLY sunset time
                now = datetime.now()
                if now.hour == target_hour and now.minute >= target_minute:
                    main_sequence_callback(run_images_folder, video_path, run_audio_folder, run_valid_images_file)
                    break
                
                # Dynamic sleep - longer delays during failure periods
                base_sleep = choice(range(15, 22))
                sleep_time = base_sleep + (consecutive_failures * 2)  # Add 2 seconds per failure
                sleep(min(sleep_time, 120))  # Cap at 2 minutes
                
            except KeyboardInterrupt:
                try:
                    main_sequence_callback(run_images_folder, video_path, run_audio_folder, run_valid_images_file)
                except Exception as e:
                    message_processor(f"Error processing images to video: {e}", "error")
                    main_sequence_callback(run_images_folder, video_path, run_audio_folder, run_valid_images_file)
                break
                
    finally:
        cursor.show()