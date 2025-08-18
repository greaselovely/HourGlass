# timelapse_core.py
import re
import os
import cv2
import sys
import json
import uuid
import shutil
import logging
import hashlib
import textwrap
import requests
import cloudscraper
import numpy as np
from time import sleep
from pathlib import Path
from random import choice
from wurlitzer import pipes
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from proglog import ProgressBarLogger
from http.client import IncompleteRead
from datetime import datetime
from moviepy.editor import ImageSequenceClip, AudioFileClip, concatenate_videoclips, concatenate_audioclips


from timelapse_config import *


class CustomLogger(ProgressBarLogger):
    """
    A custom logger class for displaying progress during video creation.

    This class extends ProgressBarLogger to provide custom formatting for progress updates.
    It displays progress as percentages for bar-type updates and as key-value pairs for other updates.

    Methods:
    - bars_callback: Handles updates for progress bars, displaying the progress as a percentage.
    - callback: Handles general updates, displaying them as key-value pairs.

    Both methods use carriage return to overwrite the previous line, creating a dynamic update effect.
    """
    def bars_callback(self, bar, attr, value, old_value=None):
        """
        Callback method for updating progress bars.

        Args:
        bar (str): The name of the progress bar being updated.
        attr (str): The attribute being updated (e.g., 'frame').
        value (int): The current value of the attribute.
        old_value (int, optional): The previous value of the attribute. Defaults to None.

        Displays the progress as a percentage, formatted with the bar name.
        """
        percentage = (value / self.bars[bar]['total']) * 100
        print(f"[i]\t{bar.capitalize()}: {percentage:.2f}%{" " * 100}", end="\r")

    def callback(self, **changes):
        """
        Callback method for general updates.

        Args:
        **changes (dict): Keyword arguments representing the changes to be logged.

        Displays each change as a key-value pair.
        """
        for (name, value) in changes.items():
            print(f"[i]\t{name}: {value}{" " * 100}", end="\r")

class ImageDownloader:
    """
    Enhanced ImageDownloader with session recovery and batched config updates.
    
    Improvements over original:
    - Automatic session recovery on failures
    - Batched config writes to reduce I/O
    - Better error handling and logging
    - Exponential backoff for consecutive failures
    - Health monitoring integration
    """

    def __init__(self, session, out_path, config, user_agents=None, proxies=None, webpage=None, health_monitor=None, time_offset=0):
        self.out_path = Path(out_path)
        self.session = session
        self.config = config
        self.time_offset = time_offset
        self.user_agents = user_agents or []
        self.proxies = proxies or {}
        self.webpage = webpage
        self.health_monitor = health_monitor
        
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
        image_files = sorted(self.out_path.glob(IMAGE_PATTERN))
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
            message_processor("Attempting session recovery...", "warning")
            
            new_session = create_session(self.user_agents, self.proxies, self.webpage)
            if new_session:
                self.session = new_session
                self.session_failures = 0
                message_processor("Session recovery successful", "info")
                if self.health_monitor:
                    self.health_monitor.update_performance_stats('session_recreations')
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
                    if self.health_monitor:
                        self.health_monitor.update_performance_stats('errors_encountered')
                    return None, None

                image_content = r.content
                image_size = len(image_content)
                image_hash = self.compute_hash(image_content)

                if image_size == 0:
                    message_processor(f"{RED_CIRCLE} Code: {r.status_code} Zero Size", "error")
                    self.consecutive_failures += 1
                    if self.health_monitor:
                        self.health_monitor.update_performance_stats('errors_encountered')
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
                        if self.health_monitor:
                            self.health_monitor.update_performance_stats('errors_encountered')
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
                    today_short_time = (datetime.now() + timedelta(hours=self.time_offset)).strftime("%H%M%S")
                    filename = datetime.now().strftime(FILENAME_FORMAT)
                    
                    with open(self.out_path / filename, 'wb') as f:
                        f.write(image_content)
                    
                    # Update tracking variables
                    self.prev_image_filename = filename
                    self.prev_image_size = image_size
                    self.prev_image_hash = image_hash
                    
                    # Update health monitor stats if available
                    if self.health_monitor:
                        self.health_monitor.update_performance_stats('images_captured')
                    
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
                    if self.health_monitor:
                        self.health_monitor.update_performance_stats('errors_encountered')
                    return None, None
                    
            except Exception as e:
                message_processor(f"Unexpected error in download_image: {e}", "error")
                self.consecutive_failures += 1
                if self.health_monitor:
                    self.health_monitor.update_performance_stats('errors_encountered')
                return None, None

        # If we get here, both attempts failed
        if self.health_monitor:
            self.health_monitor.update_performance_stats('errors_encountered')
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


def clear():
    """
    Clears the terminal screen.

    This function uses the appropriate command to clear the terminal screen
    based on the operating system ('cls' for Windows, 'clear' for others).
    """
    os.system("cls" if os.name == "nt" else "clear")

def get_or_create_run_id(time_offset=0):
    """
    Get an existing run ID for today or create a new one.

    This function manages run IDs for organizing daily runs of the application. It performs the following steps:
    1. Generates today's date in 'YYYYMMDD' format.
    2. Searches for existing run folders for today.
    3. Based on the number of existing folders:
       - If no folders exist: Creates a new run ID combining today's date and a unique identifier.
       - If one folder exists: Returns the existing run ID.
       - If multiple folders exist: Prompts the user to select one of the existing folders.

    The run ID is used to organize outputs (images, videos, etc.) for each execution of the application.

    Returns:
    str: A run ID string. Format is either 'YYYYMMDD_XXXXXXXX' for new runs 
         (where X is a portion of a UUID), or the basename of an existing folder.

    Note:
    - The function relies on helper functions 'find_today_run_folders()' and 'prompt_user_for_folder_selection()',
      which should be defined elsewhere in the codebase.
    - UUID is used to ensure uniqueness when creating a new run ID.
    """
    today = (datetime.now() + timedelta(hours=time_offset)).strftime("%Y%m%d")
    run_folders = find_today_run_folders(time_offset)
    
    if not run_folders:
        # No existing folders, create a new one
        run_id = f"{today}_{str(uuid.uuid4())[:8]}"
        return run_id
    elif len(run_folders) == 1:
        # One folder exists, use it
        return os.path.basename(run_folders[0])
    else:
        # Multiple folders exist, prompt user to choose
        selected_folder = prompt_user_for_folder_selection(run_folders)
        return os.path.basename(selected_folder)

def find_today_run_folders(time_offset=0):
    """
    Find all run folders for today in the images directory.

    This function performs the following steps:
    1. Gets today's date in 'YYYYMMDD' format.
    2. Searches the IMAGES_FOLDER for subdirectories that start with today's date.

    The function is used to identify existing run folders for the current day,
    which is useful for managing multiple runs on the same day.

    Returns:
    list: A list of full paths to folders in IMAGES_FOLDER that start with today's date.
          Each path is a string representing a run folder for today.
          The list will be empty if no matching folders are found.

    Note:
    - This function assumes that IMAGES_FOLDER is a global variable or constant 
      defined elsewhere in the code, representing the path to the main images directory.
    - The function only considers immediate subdirectories of IMAGES_FOLDER, not nested directories.
    """
    today = (datetime.now() + timedelta(hours=time_offset)).strftime("%Y%m%d")
    return [os.path.join(IMAGES_FOLDER, d) for d in os.listdir(IMAGES_FOLDER) if d.startswith(today)]

def prompt_user_for_folder_selection(folders):
    """
    Prompt the user to select a folder from a list of existing folders.

    This function is used when multiple run folders for the current day are detected.
    It presents the user with a numbered list of folders, including details about each folder,
    and asks the user to select one.

    The function performs the following steps:
    1. Prints a message informing the user of multiple folders.
    2. For each folder, displays:
       - A number for selection
       - The folder name
       - The creation time of the folder
       - The number of JPG images in the folder
    3. Prompts the user to enter the number of their chosen folder.
    4. Validates the user's input and returns the selected folder path.

    Args:
    folders (list): A list of full paths to folders to choose from.

    Returns:
    str: The full path of the folder selected by the user.

    Raises:
    ValueError: If the user enters a non-numeric value.

    Note:
    - The function will continue to prompt the user until a valid selection is made.
    - Only immediate JPG files in each folder are counted; nested directories are not considered.
    """
    print("Multiple image folders detected for today. Please select which one to use:")
    for i, folder in enumerate(folders, 1):
        image_count = len([f for f in os.listdir(folder) if f.endswith('.jpg')])
        folder_name = os.path.basename(folder)
        creation_time = datetime.fromtimestamp(os.path.getctime(folder)).strftime("%H:%M:%S")
        print(f"{i}. {folder_name} (Created at {creation_time}, Contains {image_count} images)")
    
    while True:
        try:
            choice = int(input("Enter the number of the folder you want to use: "))
            if 1 <= choice <= len(folders):
                return folders[choice - 1]
            else:
                print("Invalid choice. Please try again.")
        except ValueError:
            print("Please enter a valid number.")

def remove_valid_images_json(run_valid_images_file):
    """
    Remove the 'valid_images.json' file from the specified folder if it exists.

    This function is typically used to clean up previous run data before starting a new image capture session.
    It performs the following steps:
    1. Constructs the full path to the 'valid_images.json' file in the given folder.
    2. Checks if the file exists.
    3. If the file exists, it is removed.
    4. Logs an info message about the removal.

    Args:
    folder (str): The path to the folder from which to remove the 'valid_images.json' file.

    Returns:
    None

    Side Effects:
    - Removes the 'valid_images.json' file from the specified folder if it exists.
    - Logs an info message using the logging module.

    Note:
    - This function assumes that it has write permissions in the specified folder.
    - It silently succeeds if the file doesn't exist, without raising any errors.
    """
    if os.path.exists(run_valid_images_file):
        os.remove(run_valid_images_file)
        message_processor(f"Removed {run_valid_images_file}")

def process_image_logs(LOGGING_FILE, number_of_valid_files, time_offset=0):
    """
    Process image logs for the current day and generate a summary of image download attempts.

    This function reads a log file, filters entries for the current date, and counts
    the number of successful and failed image downloads. It also reads a JSON file
    containing valid images and provides a count of those.

    Parameters:
    LOGGING_FILE (str): Path to the log file containing image download attempts.
    run_valid_images_file (str): Path to the JSON file containing valid images.
    time_offset (int): Hour offset for date calculations.

    Returns:
    str: A formatted summary string containing:
        - Total image download attempts
        - Number of failed attempts (Same Hash)
        - Number of successful attempts (New Hash)
        - Number of valid images

    The function performs the following steps:
    1. Filters log entries for the current date.
    2. Counts occurrences of "Same Hash" (failed) and "New Hash" (successful) in today's logs.
    3. Reads the valid images JSON file and counts the number of entries.
    4. Calculates the total number of download attempts.
    5. Generates and returns a formatted summary string.

    Note: This function assumes that the log file contains date information and
    that "Same Hash" and "New Hash" are indicators for failed and successful
    downloads respectively.
    """
    today = (datetime.now() + timedelta(hours=time_offset)).strftime("%Y-%m-%d")
    with open(LOGGING_FILE, "r") as log_file:
        today_lines = [line for line in log_file if today in line]
    today_log = ''.join(today_lines)
    failed_saved_images = len(re.findall(r"Same Hash", today_log))
    successful_saved_images = len(re.findall(r"New Hash", today_log))
    total_attempts = failed_saved_images + successful_saved_images
    summary = (
        f"Total image download attempts: {total_attempts}\n"
        f"\tFailed: {failed_saved_images}\n"
        f"\tSuccessful: {successful_saved_images}\n"
        f"\tValid images: {number_of_valid_files}\n"
    )
    return summary


def log_jamming(log_message):
    """
    Formats a log message to fit a specified width with indentation.  He fixes the cable.

    This function wraps the log message to a width of 90 characters and adds
    indentation to align subsequent lines with the end of the log preface.
    Don't be fatuous Jeffery.

    Args:
        log_message (str): The log message to be formatted.

    Returns:
        str: The formatted log message.

    Example of use:
    log_jamming("Session Created: {'mailchimp_landing_site': 'webcam_url'}, ValuesView({...})")

    This will return a formatted string that looks like this in the output (example):
    2024-03-30 19:36:24,025 - INFO - Session Created: {'mailchimp_landing_site': 'webcam_url
                                webcam%2F'}, ValuesView({'User-Agent': 'Mozilla/5.0
                                (iPhone; CPU iPhone OS 15_0 like Mac OS X)
                                AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.0
                                Mobile/15E148 Safari/604.1', 'Accept-Encoding': 'gzip,
                                deflate', 'Accept': '*/*', 'Connection': 'keep-alive',
                                'Cache-Control': 'no-cache, no-store, must-revalidate',
                                'Pragma': 'no-cache', 'Expires': '0'})
    """
    log_preface = 34  # This is the length of the date, time, and info log preface
    return textwrap.fill(log_message, width=90, initial_indent='', subsequent_indent=' ' * log_preface)

def message_processor(message, log_level="info", ntfy=False, print_me=True):
    """
    Processes and distributes a message across different output channels.

    This function can print the message, log it, and send it as a notification.

    Args:
        NTFY_TOPIC (str): The URL for sending notifications.
        message (str): The message to be processed.
        log_level (str, optional): The logging level. Defaults to "info".
        ntfy (bool, optional): Whether to send a notification. Defaults to False.
        print_me (bool, optional): Whether to print the message. Defaults to True.
    """
    MESSAGE_PREFIXES = {
        "info": "[i]\t",
        "warning": "[!?]\t",
        "error": "[!]\t",
        "download" : "[>]\t",
        "none" : ""
    }
    if print_me:
        prefix = MESSAGE_PREFIXES.get(log_level, MESSAGE_PREFIXES.get("info"))
        formatted_message = f"{prefix}{message}"
        print(formatted_message)

    log_func = getattr(logging, log_level, logging.info)
    log_func(message)

    if ntfy:
        send_to_ntfy(NTFY_TOPIC, message)

def activity(char, run_images_folder, image_size, time_stamp=""):
    """
    Displays the current status of the image downloading activity in the terminal.

    Args:
        char (int): The current iteration number of the downloading loop.
        images_folder (str): Path to the folder where images are being saved.
        image_size (int): Size of the last downloaded image.
        time_stamp (str, optional): A timestamp for the activity. Defaults to "".
    """
    clear()
    files = os.listdir(run_images_folder)
    jpg_count = sum(1 for file in files if file.lower().endswith('.jpg'))
    print(f"Iteration: {char}\nImage Count: {jpg_count}\nImage Size: {image_size}\n", end="\r", flush=True)

def create_session(USER_AGENTS, proxies, webpage):
    """
    Initializes a session and verifies its ability to connect to a given webpage.

    Args:
        USER_AGENTS (list): List of user agent strings to choose from.
        proxies (dict): Proxy settings for the session.
        webpage (str): The URL to test the session's connectivity.

    Returns:
        requests.Session or None: A session object if successful, None otherwise.
    """
    session = requests.Session()
    session.headers.update({
        "User-Agent": choice(USER_AGENTS),
        "Cache-Control": "no-cache, no-store, must-revalidate",
        "Pragma": "no-cache",
        "Expires": "0"
    })

    if proxies:
        session.proxies.update(proxies)

    # Perform an initial request to verify connectivity
    try:
        response = session.get(webpage, timeout=10)
        response.raise_for_status()  # Raises a HTTPError for bad responses
        log_message = f"Session Created: {session.cookies.get_dict()}, {session.headers.values()}"
        logging.info(log_jamming(log_message))
        return session
    except (requests.RequestException, requests.HTTPError) as e:
        logging.error(f"Failed to connect to {webpage} with session: {e}")
        return None

def make_request(session):
    """
    Makes an HTTP request using the specified session and handles retries.

    Args:
        session (requests.Session): The session object to be used for making the request.

    Returns:
        requests.Response or None: The response object if successful, None otherwise.
    """
    global config
    proxies = config.get('proxies', {})
    http_proxy = proxies.get('http', '')
    https_proxy = proxies.get('https', '')
    max_retries = 3
    for _ in range(max_retries):
        try:
            if http_proxy and https_proxy:
                response = requests.get(session, proxies=proxies)
                response.raise_for_status()
                return response
            else:
                response = requests.get(session)
                response.raise_for_status()
                return response
        except IncompleteRead as e:
            log_message = f"Incomplete Read (make_request()): {e}"
            message = log_jamming(log_message)
            message_processor(message, log_level="error")
            return None
        except requests.RequestException as e:
            log_message = f"Incomplete Read (make_request()): {e}"
            logging.error(log_jamming(log_message))
            print(f"RequestException Error: {e}")
            return None
    return None

def validate_images(run_images_folder, run_images_valid_file) -> tuple:
    """
    Creates a dictionary of valid image file paths from the specified folder.

    This function checks for existing valid images, processes new images,
    and saves the list of valid image paths to a JSON file.

    Args:
        images_folder (str): The directory where the images are stored.
        run_images_valid_file (str): The path to the JSON file storing valid image paths.

    Returns:
        tuple: A tuple containing a list of valid image file paths and the count of valid images.
    """
       
    run_images_valid_file = Path(run_images_valid_file)
    run_images_folder = Path(run_images_folder)

    if run_images_valid_file.exists() and run_images_valid_file.stat().st_size > 0:
        try:
            with open(run_images_valid_file, 'r') as file:
                valid_files = json.load(file)
                message_processor("Existing Validation Used", print_me=True)
                return valid_files, len(valid_files)
        except json.JSONDecodeError:
            message_processor("Error decoding JSON, possibly corrupted file.", "error")
    
    else:
        images = sorted([img for img in os.listdir(run_images_folder) if img.endswith(".jpg")])
        images_dict = {}
        
        for n, image in enumerate(images, 1):
            print(f"[i]\t{n}", end='\r')
            full_image = Path(run_images_folder) / image
            with pipes() as (out, err):
                img = cv2.imread(str(full_image))
            err.seek(0)
            error_message = err.read()
            if error_message == "":
                images_dict[str(full_image)] = error_message

        valid_files = list(images_dict.keys())
        
        # Save the valid image paths to a JSON file
        with open(run_images_valid_file, 'w') as file:
            json.dump(valid_files, file)

        return valid_files, len(valid_files)

def calculate_video_duration(num_images, fps) -> int:
    """
    Calculates the expected duration of a time-lapse video.

    Args:
        num_images (int): The number of images in the time-lapse.
        fps (int): The frames per second rate for the video.

    Returns:
        int: The expected duration of the video in milliseconds.
    """
    duration_sec = num_images / fps
    duration_ms = int(duration_sec * 1000)
    return duration_ms

def single_song_download(AUDIO_FOLDER, max_attempts=3, debug=False):
    """
    Downloads a random song from Pixabay and tests its usability.

    This function attempts to download a song up to 'max_attempts' times,
    testing each download to ensure it can be used by MoviePy.

    Parameters:
    - AUDIO_FOLDER (str): Path to the folder where audio files will be saved.
    - max_attempts (int): Maximum number of download attempts. Defaults to 3.
    - debug (bool): If True, save HTML/JSON responses for debugging.

    Returns:
    - tuple: A tuple containing the path to the downloaded audio file and its duration,
             or (None, None) if all attempts fail.

    Note:
    The function prints messages to the console indicating the status of each download
    and any errors encountered.
    """
    # Create temp folder for debugging HTML responses if debug mode is enabled
    if debug:
        temp_folder = Path("pixabay_debug")
        temp_folder.mkdir(exist_ok=True)
    
    for attempt in range(max_attempts):
        try:
            # Add delay between attempts to avoid rate limiting
            if attempt > 0:
                delay = 10 + attempt * 5  # Progressive delay: 15s, 20s
                message_processor(f"Waiting {delay} seconds before retry...", "info")
                sleep(delay)
            
            # Use cloudscraper to bypass Cloudflare
            # It handles user agents and headers automatically
            session = cloudscraper.create_scraper(
                browser={
                    'browser': 'chrome',
                    'platform': 'darwin',
                    'desktop': True
                }
            )
            
            # Step 1: Get page 1 HTML to extract bootstrap URL and total pages
            search_term = "background music"
            page1_url = f"https://pixabay.com/music/search/{search_term.replace(' ', '%20')}/"
            
            message_processor(f"Fetching Pixabay music catalog for '{search_term}' (attempt {attempt + 1})", "info")
            message_processor(f"URL: {page1_url}", "info")
            r = session.get(page1_url)
            
            # Save HTML response for debugging if enabled
            if debug:
                html_file = temp_folder / f"page1_attempt{attempt + 1}_{r.status_code}.html"
                # r.text should handle decompression automatically
                with open(html_file, 'w', encoding='utf-8') as f:
                    f.write(r.text)
                message_processor(f"Saved HTML to: {html_file}", "info")
            
            r.raise_for_status()
            
            # Extract the bootstrap URL from the HTML
            html_content = r.text
            bootstrap_match = re.search(r"window\.__BOOTSTRAP_URL__\s*=\s*'([^']+)'", html_content)
            
            if not bootstrap_match:
                message_processor("Could not find bootstrap URL in HTML", "error")
                continue
                
            bootstrap_path = bootstrap_match.group(1)
            bootstrap_url = f"https://pixabay.com{bootstrap_path}"
            
            # Step 2: Fetch the bootstrap JSON to get total pages
            message_processor("Fetching catalog metadata", "info")
            message_processor(f"URL: {bootstrap_url}", "info")
            sleep(10)  # 10 second delay between requests
            r = session.get(bootstrap_url)
            
            # Save JSON response for debugging if enabled
            if debug:
                json_file = temp_folder / f"bootstrap_page1_attempt{attempt + 1}_{r.status_code}.json"
                with open(json_file, 'w', encoding='utf-8') as f:
                    f.write(r.text)
                message_processor(f"Saved JSON to: {json_file}", "info")
            
            r.raise_for_status()
            
            initial_data = r.json()
            total_pages = initial_data.get('page', {}).get('pages', 1)
            message_processor(f"Found {total_pages} pages of music available", "info")
            
            # Step 3: Select a random page
            selected_page = choice(range(1, min(total_pages + 1, 1000)))  # Cap at 1000 for safety
            
            # Step 4: If not page 1, fetch the selected page
            if selected_page > 1:
                page_url = f"https://pixabay.com/music/search/{search_term.replace(' ', '%20')}/?pagi={selected_page}"
                message_processor(f"Fetching page {selected_page} of {total_pages}", "info")
                message_processor(f"URL: {page_url}", "info")
                
                sleep(10)  # 10 second delay between requests
                r = session.get(page_url)
                
                # Save HTML response for debugging if enabled
                if debug:
                    html_file = temp_folder / f"page{selected_page}_attempt{attempt + 1}_{r.status_code}.html"
                    with open(html_file, 'w', encoding='utf-8') as f:
                        f.write(r.text)
                    message_processor(f"Saved HTML to: {html_file}", "info")
                
                r.raise_for_status()
                
                # Extract bootstrap URL from this page
                html_content = r.text
                bootstrap_match = re.search(r"window\.__BOOTSTRAP_URL__\s*=\s*'([^']+)'", html_content)
                
                if bootstrap_match:
                    bootstrap_path = bootstrap_match.group(1)
                    bootstrap_url = f"https://pixabay.com{bootstrap_path}"
                    
                    # Fetch the bootstrap JSON for this page
                    message_processor(f"Fetching page {selected_page} bootstrap data", "info")
                    message_processor(f"URL: {bootstrap_url}", "info")
                    sleep(10)  # 10 second delay between requests
                    r = session.get(bootstrap_url)
                    
                    # Save JSON response for debugging if enabled
                    if debug:
                        json_file = temp_folder / f"bootstrap_page{selected_page}_attempt{attempt + 1}_{r.status_code}.json"
                        with open(json_file, 'w', encoding='utf-8') as f:
                            f.write(r.text)
                        message_processor(f"Saved JSON to: {json_file}", "info")
                    
                    r.raise_for_status()
                    page_data = r.json()
                    results = page_data.get('page', {}).get('results', [])
                else:
                    message_processor(f"Could not find bootstrap URL for page {selected_page}, using page 1", "warning")
                    results = initial_data.get('page', {}).get('results', [])
            else:
                results = initial_data.get('page', {}).get('results', [])
                message_processor("Using page 1", "info")
            
            if not results:
                message_processor("No songs found in response.", "error")
                continue
            
            # Select a random song from the results
            song = choice(results)
            
            # Extract song information
            song_src = song.get('sources', {}).get('src')
            song_duration = song.get('duration', 0)  # Duration in seconds
            song_name = song.get('name', 'Unknown Song')
            
            if not song_src:
                message_processor("Song source URL not found.", "error")
                continue
            
            message_processor(f"Downloading: {song_name[:50]}... ({song_duration}s)", "download")
            message_processor(f"URL: {song_src}", "info")
            
            # Download the audio file
            sleep(10)  # 10 second delay before downloading
            r = session.get(song_src)
            r.raise_for_status()
            
            # Clean filename for saving
            safe_name = re.sub(r'[^\w\s-]', '', song_name)[:50]
            audio_name = f"{safe_name}.mp3"
            full_audio_path = os.path.join(AUDIO_FOLDER, audio_name)
            
            with open(full_audio_path, 'wb') as f:
                f.write(r.content)
            
            message_processor(f"Downloaded: {audio_name}", "download")
            
            # Test the audio file
            try:
                with AudioFileClip(full_audio_path) as audio_clip:
                    # If we can read the duration, the file is likely usable
                    actual_duration = audio_clip.duration
                message_processor(f"Audio file verified. Duration: {actual_duration:.2f} seconds")
                return full_audio_path, actual_duration * 1000  # Return duration in milliseconds
            except Exception as e:
                message_processor(f"Error verifying audio file: {e}", "error")
                os.remove(full_audio_path)  # Remove the unusable file
                message_processor(f"Removed unusable file: {audio_name}")
                continue  # Try downloading again
        
        except requests.HTTPError as e:
            if e.response.status_code == 403:
                message_processor(f"Access forbidden (403). Pixabay may be rate limiting. Retrying...", "warning")
            else:
                message_processor(f"HTTP error occurred:\n[!]\t{e}", "error")
        except requests.RequestException as e:
            message_processor(f"An error occurred during download:\n[!]\t{e}", "error")
        except (KeyError, ValueError) as e:
            message_processor(f"Error parsing response data: {e}", "error")
    
    message_processor(f"Failed to download a usable audio file after {max_attempts} attempts.", "error")
    return None, None

def audio_download(video_duration, AUDIO_FOLDER, debug=False) -> list:
    """
    Downloads multiple songs, ensuring their total duration covers the video duration.

    Args:
        video_duration (int): Required total audio duration in milliseconds.
        AUDIO_FOLDER (str or Path): Directory to save the downloaded audio files.
        debug (bool): If True, save HTML/JSON responses for debugging.

    Returns:
        list: List of tuples, each containing the path to a downloaded audio file and its duration in seconds.
              Returns None if unsuccessful in downloading sufficient audio.
    """
    songs = []
    total_duration = 0  # total duration in seconds
    attempts = 0
    max_attempts = 10
    
    message_processor(f"Attempting to download audio for {video_duration/1000:.2f} seconds of video", print_me=False)

    while total_duration < video_duration / 1000 and attempts < max_attempts:
        song_path, song_duration_ms = single_song_download(AUDIO_FOLDER, debug=debug)
        if song_path and song_duration_ms:
            song_duration_sec = song_duration_ms / 1000
            songs.append((song_path, song_duration_sec))
            total_duration += song_duration_sec
        else:
            message_processor(f"Failed to download a valid song on attempt {attempts + 1}", "warning")
        
        attempts += 1

    if total_duration < video_duration / 1000:
        message_processor(f"Failed to download sufficient audio length. Got {total_duration:.2f}s, needed {video_duration/1000:.2f}s")
        return None
    
    message_processor(f"Successfully downloaded {len(songs)} songs, total duration: {total_duration:.2f}s")
    return songs

def concatenate_songs(songs, crossfade_seconds=3):
    """
    Concatenates multiple AudioFileClip objects with manual crossfade.
    
    Args:
        songs (list of tuples): List of tuples, each containing the path to an audio file and its duration.
        crossfade_seconds (int): Duration of crossfade between clips.
    
    Returns:
        AudioFileClip or None: The concatenated audio clip.
    """
    if not songs:
        message_processor("No songs provided for concatenation.", log_level="error")
        return None
    
    clips = []
    for song in songs:
        if isinstance(song, tuple) and len(song) > 0:
            song_path = song[0]  # Assuming the file path is the first element in the tuple
            try:
                clip = AudioFileClip(song_path)
                clips.append(clip)
            except Exception as e:
                message_processor(f"Error loading audio from {song_path}: {e}", "error", ntfy=True)
                sys.exit(1)
                
        else:
            message_processor("Invalid song data format.", "error", ntfy=True)

    if clips:
        # Manually handle crossfade
        if len(clips) > 1:
            # Adjust the start time of each subsequent clip to create overlap for crossfade
            for i in range(1, len(clips)):
                clips[i] = clips[i].set_start(clips[i-1].end - crossfade_seconds)
            final_clip = concatenate_audioclips(clips)
        else:
            final_clip = clips[0]

        return final_clip

    return None

def create_time_lapse(valid_files, video_path, fps, audio_input=None, crossfade_seconds=3, end_black_seconds=3):
    """
    Creates a time-lapse video from a list of image files with optional audio.

    Args:
        valid_files (list): List of paths to image files.
        video_path (str): Path where the final video will be saved.
        fps (int): Frames per second for the video.
        audio_input (str or AudioFileClip, optional): Path to the audio file or an AudioFileClip object. Defaults to None.
        crossfade_seconds (int, optional): Duration of crossfade effect. Defaults to 3.
        end_black_seconds (int, optional): Duration of black screen at the end. Defaults to 3.
    """
    logger = CustomLogger()
    
    try:
        message_processor("Creating Time Lapse")
        message_processor(f"Creating time-lapse with {len(valid_files)} images at {fps} fps")
        video_clip = ImageSequenceClip(valid_files, fps=fps)
        
        audio_clip = None
        if audio_input:
            message_processor("Processing Audio")
            if isinstance(audio_input, str):
                audio_clip = AudioFileClip(audio_input)
            elif hasattr(audio_input, 'audio_fadein'):
                audio_clip = audio_input
            else:
                raise ValueError("Invalid audio input: must be a file path or an AudioClip")
            
            message_processor(f"Video duration: {video_clip.duration}, Audio duration: {audio_clip.duration}")
            
            if audio_clip.duration < video_clip.duration:
                message_processor("Audio is shorter than video. Looping audio.", "warning")
                audio_clip = audio_clip.loop(duration=video_clip.duration)
            else:
                audio_clip = audio_clip.subclip(0, video_clip.duration)
            
            message_processor("Applying Audio Effects")
            audio_clip = audio_clip.audio_fadein(crossfade_seconds).audio_fadeout(crossfade_seconds)
            video_clip = video_clip.set_audio(audio_clip)
        else:
            message_processor("Creating video without audio")
        
        video_clip = video_clip.fadein(crossfade_seconds).fadeout(crossfade_seconds)

        message_processor("Creating End Frame")
        black_frame_clip = ImageSequenceClip([np.zeros((video_clip.h, video_clip.w, 3), dtype=np.uint8)], fps=fps).set_duration(end_black_seconds)
        
        message_processor("Concatenating Video Clips")
        final_clip = concatenate_videoclips([video_clip, black_frame_clip])
        
        message_processor("Writing Video File")
        logging.info(f"Writing video file to {video_path}")
        if audio_clip:
            final_clip.write_videofile(video_path, codec="libx264", audio_codec="aac", logger=logger)
        else:
            final_clip.write_videofile(video_path, codec="libx264", logger=logger)

    except Exception as e:
        error_message = f"Error in create_time_lapse: {str(e)}"
        logging.error(error_message)
        message_processor(error_message, "error", ntfy=True)
        raise  # Re-raise the exception to be caught by the calling function

    finally:
        message_processor("Closing Clips")
        try:
            if 'video_clip' in locals():
                video_clip.close()
            if 'audio_clip' in locals():
                audio_clip.close()
            if 'final_clip' in locals():
                final_clip.close()
        except Exception as close_error:
            message_processor(f"Error while closing clips: {str(close_error)}", "error")

    message_processor(f"Time Lapse Saved: {video_path}", ntfy=False)

def cleanup(path):
    """
    Removes a directory along with all its contents.

    Args:
        directory_path (str or Path): The path to the directory to remove.
    """
    try:
        if os.path.exists(path):
            shutil.rmtree(path)
            message_processor(f"All contents of {path} have been removed.")
        else:
            message_processor(f"No directory found at {path}. Nothing to remove.")
    except Exception as e:
        message_processor(f"Failed to remove {path}: {e}", "error")

def send_to_ntfy(NTFY_TOPIC, message="Incomplete Message"):
    """
    Sends a notification message to the specified NTFY topic.

    Args:
        NTFY_TOPIC (str): The topic name for the NTFY notification.
        message (str, optional): The message to send. Defaults to "Incomplete Message".

    Returns:
        bool: True if the message was sent successfully, False otherwise.
    """
    if not NTFY_TOPIC:
        message_processor("No NTFY topic provided. Skipping notification.", "warning")
        return False

    try:
        NTFY_TOPIC = urljoin(NTFY_URL, NTFY_TOPIC)
        message = str(message)  # cast to str in case we receive something else that won't process
        headers = {'Content-Type': 'application/x-www-form-urlencoded'}
        response = requests.post(NTFY_TOPIC, headers=headers, data=message)
        response.raise_for_status()
        message_processor(f"Notification sent to {NTFY_TOPIC}")
        return True
    except requests.RequestException as e:
        message_processor(f"Failed to send notification: {e}", "error")
        return False

def sun_schedule(SUN_URL):
    """
    Fetches and parses the HTML content from the specified URL.

    Args:
        SUN_URL (str): The URL to fetch the sun schedule from.

    Returns:
        BeautifulSoup object or None: Parsed HTML content if successful, None otherwise.
    """
    try:
        user_agent = choice(USER_AGENTS)
        headers = {"User-Agent": user_agent}
        response = requests.get(SUN_URL, headers=headers)
        response.raise_for_status()  # Raise an HTTPError for bad responses
        html_content = response.text
    except requests.RequestException as e:
        print(f"Error fetching the HTML content from {SUN_URL}: {e}")
        return None
    if html_content:
        return BeautifulSoup(html_content, 'html.parser')
    else:
        return

def find_time_and_convert(soup, text, default_time_str):
    """
    Finds a specific time in the parsed HTML content and converts it to a time object.

    Args:
        soup (BeautifulSoup): The parsed HTML content.
        text (str): The text to search for in the HTML.
        default_time_str (str): The default time string to use if the search fails.

    Returns:
        datetime.time: The found time or the default time.
    """
    if soup is not None:
        element = soup.find('th', string=lambda x: x and text in x)
        if element and element.find_next_sibling('td'):
            time_text = element.find_next_sibling('td').text
            time_match = re.search(r'\d+:\d+\s(?:am|pm)', time_text)
            if time_match:
                return datetime.strptime(time_match.group(), '%I:%M %p').time()
    message_processor(datetime.strptime(default_time_str, '%H:%M:%S').time())
    return datetime.strptime(default_time_str, '%H:%M:%S').time()