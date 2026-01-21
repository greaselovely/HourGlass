# utils.py
"""
Utility functions for logging, notifications, session management, and helpers.
"""
import os
import re
import uuid
import shutil
import logging
import textwrap
import requests
from random import choice
from pathlib import Path
from datetime import datetime, timedelta
from urllib.parse import urljoin

from .timelapse_config import NTFY_URL, USER_AGENTS, IMAGES_FOLDER


def clear():
    """
    Clears the terminal screen.

    This function uses the appropriate command to clear the terminal screen
    based on the operating system ('cls' for Windows, 'clear' for others).
    """
    os.system("cls" if os.name == "nt" else "clear")


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
        # Get NTFY_TOPIC from global namespace
        import sys
        main_module = sys.modules.get('__main__')
        if main_module and hasattr(main_module, 'NTFY_TOPIC'):
            NTFY_TOPIC = main_module.NTFY_TOPIC
        else:
            from .timelapse_config import NTFY_TOPIC
        send_to_ntfy(NTFY_TOPIC, message)


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
    if not USER_AGENTS:
        message_processor("No user agents provided to create_session", "error")
        return None

    session = requests.Session()
    session.headers.update({
        "User-Agent": choice(USER_AGENTS),
        "Cache-Control": "no-cache, no-store, must-revalidate",
        "Pragma": "no-cache",
        "Expires": "0"
    })

    if proxies:
        session.proxies.update(proxies)

    # Check if webpage appears to be a direct image/video stream
    # Common patterns: .jpg, .jpeg, .png, .mjpg, .mjpeg, video.mjpg, etc.
    image_extensions = ('.jpg', '.jpeg', '.png', '.gif', '.bmp', '.mjpg', '.mjpeg', 'video.mjpg', 'video.mjpeg')
    is_direct_image = any(webpage.lower().endswith(ext) or ext in webpage.lower() for ext in image_extensions)

    if is_direct_image:
        # Skip connectivity test for direct image URLs
        message_processor("Direct image/stream URL detected - skipping session verification", "info")
        log_message = f"Session Created (direct image): {session.headers.values()}"
        logging.info(log_jamming(log_message))
        return session

    # Perform an initial request to verify connectivity for regular webpages
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
    from http.client import IncompleteRead
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
    from datetime import datetime, timedelta
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


def check_socks_proxy(config):
    """
    Check SOCKS proxy connectivity and DNS resolution.

    Args:
        config (dict): Configuration containing proxy settings

    Returns:
        dict: Status information with keys:
            - 'reachable': bool
            - 'method': str (hostname, ip, or none)
            - 'error': str (if not reachable)
    """
    import socket

    if not config or 'proxies' not in config:
        return {'reachable': True, 'method': 'none', 'error': None}

    proxies = config['proxies']
    socks5_hostname = proxies.get('socks5_hostname', '')
    socks5 = proxies.get('socks5', '')

    # Try socks5_hostname first
    if socks5_hostname:
        proxy_str = socks5_hostname
        try:
            # Parse hostname:port
            if ':' in proxy_str:
                host, port = proxy_str.rsplit(':', 1)
                port = int(port)
            else:
                host = proxy_str
                port = 1080  # Default SOCKS port

            # Try to resolve hostname
            try:
                ip = socket.gethostbyname(host)
                message_processor(f"SOCKS proxy hostname resolved: {host} -> {ip}", "info")

                # Try to connect to the proxy
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(5)
                sock.connect((host, port))
                sock.close()
                message_processor(f"SOCKS proxy reachable at {host}:{port}", "info")
                return {'reachable': True, 'method': 'hostname', 'error': None}
            except socket.gaierror as e:
                error_msg = f"SOCKS proxy hostname DNS resolution failed: {host} - {e}"
                message_processor(error_msg, "error", ntfy=True)
                return {'reachable': False, 'method': 'hostname', 'error': str(e)}
            except (socket.timeout, ConnectionRefusedError, OSError) as e:
                error_msg = f"SOCKS proxy not responding at {host}:{port} - {e}"
                message_processor(error_msg, "error", ntfy=True)
                return {'reachable': False, 'method': 'hostname', 'error': str(e)}
        except Exception as e:
            error_msg = f"Error checking SOCKS proxy (hostname): {e}"
            message_processor(error_msg, "error")
            return {'reachable': False, 'method': 'hostname', 'error': str(e)}

    # Try socks5 (IP) if hostname not available
    if socks5:
        proxy_str = socks5
        try:
            if ':' in proxy_str:
                host, port = proxy_str.rsplit(':', 1)
                port = int(port)
            else:
                host = proxy_str
                port = 1080

            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5)
            sock.connect((host, port))
            sock.close()
            message_processor(f"SOCKS proxy reachable at {host}:{port}", "info")
            return {'reachable': True, 'method': 'ip', 'error': None}
        except (socket.timeout, ConnectionRefusedError, OSError) as e:
            error_msg = f"SOCKS proxy not responding at {host}:{port} - {e}"
            message_processor(error_msg, "error", ntfy=True)
            return {'reachable': False, 'method': 'ip', 'error': str(e)}
        except Exception as e:
            error_msg = f"Error checking SOCKS proxy (IP): {e}"
            message_processor(error_msg, "error")
            return {'reachable': False, 'method': 'ip', 'error': str(e)}

    return {'reachable': True, 'method': 'none', 'error': None}


def get_or_create_run_id(time_offset=0, images_folder=None):
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
    if images_folder is None:
        images_folder = IMAGES_FOLDER
    today = (datetime.now() + timedelta(hours=time_offset)).strftime("%Y%m%d")
    run_folders = find_today_run_folders(time_offset, images_folder)

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


def find_today_run_folders(time_offset=0, images_folder=None):
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
    if images_folder is None:
        images_folder = IMAGES_FOLDER

    # Check if the images folder exists
    if not os.path.exists(images_folder):
        return []  # Return empty list if folder doesn't exist

    today = (datetime.now() + timedelta(hours=time_offset)).strftime("%Y%m%d")
    return [os.path.join(images_folder, d) for d in os.listdir(images_folder) if d.startswith(today)]


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
            user_choice = int(input("Enter the number of the folder you want to use: "))
            if 1 <= user_choice <= len(folders):
                return folders[user_choice - 1]
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
