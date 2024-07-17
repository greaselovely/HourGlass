# vla_core.py

import re
import os
import cv2
import sys
import json
import cursor
import shutil
import logging
import hashlib
import textwrap
import requests
import numpy as np
from sys import exit
from PIL import Image
from time import sleep
from pathlib import Path
from random import choice
from wurlitzer import pipes
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from proglog import ProgressBarLogger
from http.client import IncompleteRead
from datetime import datetime, timedelta
from moviepy.editor import ImageSequenceClip, AudioFileClip, concatenate_videoclips, concatenate_audioclips

from vla_config import *


class CustomLogger(ProgressBarLogger):
    def bars_callback(self, bar, attr, value, old_value=None):
        percentage = (value / self.bars[bar]['total']) * 100
        print(f"[i]\t{bar.capitalize()}: {percentage:.2f}%{" " * 100}", end="\r")

    def callback(self, **changes):
        for (name, value) in changes.items():
            print(f"[i]\t{name}: {value}{" " * 20}", end="\r")

class ImageDownloader:
    """
    A class to handle downloading images and managing hash collisions.

    This class provides methods for downloading images, computing their hash,
    and handling potential hash collisions. It keeps track of the previously
    downloaded image to avoid duplicates.

    Attributes:
        out_path (Path): The directory where images will be saved.
        hash_collisions_path (Path): The directory for storing hash collisions.
        session (requests.Session): The session object used for making HTTP requests.
        prev_image_filename (str): The filename of the previously downloaded image.
        prev_image_size (int): The size of the previously downloaded image.
        prev_image_hash (str): The hash of the previously downloaded image.
    """

    def __init__(self, session, out_path):
        self.out_path = Path(out_path)
        self.hash_collisions_path = self.out_path / "hash_collisions"  # Directory for hash collisions
        self.session = session
        self.prev_image_filename = None
        self.prev_image_size = None
        self.prev_image_hash = None
        # self.hash_collisions_path.mkdir(exist_ok=True)  # Ensure the directory exists

    def compute_hash(self, image_content):
        """
        Computes the SHA-256 hash of the given image content.

        Args:
            image_content (bytes): The binary content of the image.

        Returns:
            str: The hexadecimal representation of the SHA-256 hash.
        """
        return hashlib.sha256(image_content).hexdigest()

    def download_image(self, session, IMAGE_URL, retry_delay=5):
        """
        Downloads an image from the specified URL and saves it to the output path.

        This method handles potential hash collisions and updates the previous image information.
        If a hash collision is detected, it will retry the download once after a delay.

        Args:
            session (requests.Session): The session object to use for the HTTP request.
            IMAGE_URL (str): The URL of the image to download.
            retry_delay (int): Delay in seconds before retrying if a hash collision occurs.

        Returns:
            tuple: A tuple containing the image size and filename if successful, or (None, None) if unsuccessful.
        """
        for attempt in range(2):  # We'll try twice at most: initial attempt + one retry
            r = session.get(IMAGE_URL)
            if r is None or r.status_code != 200:
                logging.error(f"{RED_CIRCLE} Code: {r.status_code} r = None or Not 200")
                return None, None

            image_content = r.content
            image_size = len(image_content)
            image_hash = self.compute_hash(image_content)

            if image_size == 0:
                logging.error(f"[!]\t{RED_CIRCLE} Code: {r.status_code} Zero Size")
                return None, None

            today_short_time = datetime.now().strftime("%H%M%S")
            filename = f'vla.{today_short_date}.{today_short_time}.jpg'
            with open(self.out_path / filename, 'wb') as f:
                f.write(image_content)

            if self.prev_image_hash == image_hash:
                if attempt == 0:  # If it's the first attempt
                    logging.info(f"{RED_CIRCLE} Code: {r.status_code} Same Hash: {image_hash}")
                    sleep(retry_delay)
                    continue  # Try again
                else:
                    logging.info(f"{RED_CIRCLE} Code: {r.status_code} Same Hash: {image_hash} after retry. Skipping.")
                    return None, None
            else:
                logging.info(f"{GREEN_CIRCLE} Code: {r.status_code}  New Hash: {image_hash}")
                self.prev_image_filename = filename
                self.prev_image_size = image_size
                self.prev_image_hash = image_hash
                return image_size, filename

        # This line should never be reached, but it's here for completeness
        return None, None
    
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
    log_jamming("Session Created: {'mailchimp_landing_site': 'https%3A%2F%2Fpublic.nrao.edu%2Fvla-webcam%2F'}, ValuesView({...})")

    This will return a formatted string that looks like this in the output (example):
    2024-03-30 19:36:24,025 - INFO - Session Created: {'mailchimp_landing_site': 'https%3A%2F%2Fpublic.nrao.edu%2Fvla-
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
    if print_me:
        print(message)
    log_func = getattr(logging, log_level, logging.info)
    log_func(message)
    if ntfy:
        send_to_ntfy(NTFY_TOPIC, message)

def activity(char, images_folder, image_size, time_stamp=""):
    """
    Displays the current status of the image downloading activity in the terminal.

    Args:
        char (int): The current iteration number of the downloading loop.
        images_folder (str): Path to the folder where images are being saved.
        image_size (int): Size of the last downloaded image.
        time_stamp (str, optional): A timestamp for the activity. Defaults to "".
    """
    clear()
    files = os.listdir(images_folder)
    jpg_count = sum(1 for file in files if file.lower().endswith('.jpg'))
    print(f"[i]\tIteration: {char}\n[i]\tImage Count: {jpg_count}\n[i]\tImage Size: {image_size}\n", end="\r", flush=True)

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

def create_images_dict(images_folder) -> list:
    """
    Creates a dictionary of valid image file paths from the specified folder.

    This function checks for existing valid images, processes new images,
    and saves the list of valid image paths to a JSON file.

    Args:
        images_folder (str): The directory where the images are stored.

    Returns:
        list: A list of valid image file paths.
    """
    valid_images_path = Path(images_folder) / "valid_images.json"
    
    # Check if the valid_images.json file exists and is not empty
    if valid_images_path.exists() and valid_images_path.stat().st_size > 0:
        try:
            with open(valid_images_path, 'r') as file:
                valid_files = json.load(file)
                message = f"[i]\tExisting Validation Used"
                message_processor(message, 'info', print_me=True)
                return valid_files
        except json.JSONDecodeError:
            message = f"[!]\tError decoding JSON, possibly corrupted file."
            message_processor(message, 'error')
    
    # images = sorted([os.path.join(images_folder, img) for img in os.listdir(images_folder) if img.endswith(".jpg")])
    images = sorted([img for img in os.listdir(images_folder) if img.endswith(".jpg")])
    images_dict = {}
    
    for n, image in enumerate(images, 1):
        print(f"[i]\t{n}", end='\r')
        full_image = Path(images_folder) / image
        with pipes() as (out, err):
            img = cv2.imread(str(full_image))
        err.seek(0)
        error_message = err.read()
        if error_message == "":
            images_dict[str(full_image)] = error_message

    valid_files = list(images_dict.keys())
    
    # Save the valid image paths to a JSON file
    with open(valid_images_path, 'w') as file:
        json.dump(valid_files, file)

    return valid_files

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

def single_song_download(AUDIO_FOLDER, max_attempts=3):
    """
    Downloads a random song and tests its usability.

    This function attempts to download a song up to 'max_attempts' times,
    testing each download to ensure it can be used by MoviePy.

    Parameters:
    - AUDIO_FOLDER (str): Path to the folder where audio files will be saved.
    - max_attempts (int): Maximum number of download attempts. Defaults to 3.

    Returns:
    - tuple: A tuple containing the path to the downloaded audio file and its duration,
             or (None, None) if all attempts fail.

    Note:
    The function prints messages to the console indicating the status of each download
    and any errors encountered.
    """
    for attempt in range(max_attempts):
        try:
            user_agent = choice(USER_AGENTS)
            headers = {"User-Agent": user_agent}
            url = "https://soundtracks.loudly.com/songs"
            r = requests.get(url, headers=headers)
            r.raise_for_status()
            
            last_page = r.json().get('pagination_data', {}).get('last_page', 20)
            page = choice(range(1, last_page + 1))
            url = f"https://soundtracks.loudly.com/songs?page={page}"
            r = requests.get(url, headers=headers)
            r.raise_for_status()
            
            data = r.json()
            songs = data.get('items', [])
            if not songs:
                message_processor("No songs found.", "error")
                continue
            
            song = choice(songs)
            song_duration = song.get('duration', 0)
            song_download_path = song.get('music_file_path')
            if not song_download_path:
                message_processor("Song download path not found.", "error")
                continue
            
            r = requests.get(song_download_path)
            r.raise_for_status()
            
            song_name = song.get('title', 'Unknown Song').replace('/', '_')
            audio_name = f"{song_name}.mp3"
            full_audio_path = os.path.join(AUDIO_FOLDER, audio_name)
            
            with open(full_audio_path, 'wb') as f:
                f.write(r.content)
            
            message_processor(f"[>]\tDownloaded: {audio_name}")
            
            # Test the audio file
            try:
                with AudioFileClip(full_audio_path) as audio_clip:
                    # If we can read the duration, the file is likely usable
                    actual_duration = audio_clip.duration
                message_processor(f"[>]\tAudio file verified. Duration: {actual_duration:.2f} seconds")
                return full_audio_path, actual_duration * 1000  # Return duration in milliseconds
            except Exception as e:
                message_processor(f"[!]\tError verifying audio file: {e}", "error")
                os.remove(full_audio_path)  # Remove the unusable file
                message_processor(f"[>]\tRemoved unusable file: {audio_name}")
                continue  # Try downloading again
        
        except requests.RequestException as e:
            message_processor(f"[!]\tAn error occurred during download:\n[!]\t{e}", "error")
    
    message_processor(f"[!]\tFailed to download a usable audio file after {max_attempts} attempts.", "error")
    return None, None

def audio_download(video_duration, AUDIO_FOLDER) -> list:
    """
    Downloads multiple songs, ensuring their total duration covers the video duration.

    Args:
        video_duration (int): Required total audio duration in milliseconds.
        AUDIO_FOLDER (str or Path): Directory to save the downloaded audio files.

    Returns:
        list: List of tuples, each containing the path to a downloaded audio file and its duration in seconds.
              Returns None if unsuccessful in downloading sufficient audio.
    """
    songs = []
    total_duration = 0  # total duration in seconds
    attempts = 0
    max_attempts = 10
    
    message_processor(f"[i]\tAttempting to download audio for {video_duration/1000:.2f} seconds of video", print_me=False)

    while total_duration < video_duration / 1000 and attempts < max_attempts:
        song_path, song_duration_ms = single_song_download(AUDIO_FOLDER)
        if song_path and song_duration_ms:
            song_duration_sec = song_duration_ms / 1000
            songs.append((song_path, song_duration_sec))
            total_duration += song_duration_sec
        else:
            message_processor(f"Failed to download a valid song on attempt {attempts + 1}", "warning")
        
        attempts += 1

    if total_duration < video_duration / 1000:
        message_processor(f"[!]\tFailed to download sufficient audio length. Got {total_duration:.2f}s, needed {video_duration/1000:.2f}s")
        return None
    
    message_processor(f"[i]\tSuccessfully downloaded {len(songs)} songs, total duration: {total_duration:.2f}s")
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
        message_processor("[!]\tNo songs provided for concatenation.", log_level="error")
        return None
    
    clips = []
    for song in songs:
        if isinstance(song, tuple) and len(song) > 0:
            song_path = song[0]  # Assuming the file path is the first element in the tuple
            try:
                clip = AudioFileClip(song_path)
                clips.append(clip)
            except Exception as e:
                message_processor(f"[!]\tError loading audio from {song_path}:\n[!]\t{e}\n[!]\tFix This!", log_level="error", ntfy=True)
                sys.exit(1)
                
        else:
            message_processor("[!]\tInvalid song data format.", log_level="error", ntfy=True)

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

def create_time_lapse(valid_files, video_path, fps, audio_input, crossfade_seconds=3, end_black_seconds=3):
    """
    Creates a time-lapse video from a list of image files with audio.

    Args:
        valid_files (list): List of paths to image files.
        video_path (str): Path where the final video will be saved.
        fps (int): Frames per second for the video.
        audio_input (str or AudioFileClip): Path to the audio file or an AudioFileClip object.
        crossfade_seconds (int, optional): Duration of crossfade effect. Defaults to 3.
        end_black_seconds (int, optional): Duration of black screen at the end. Defaults to 3.
    """
    logger = CustomLogger()
    
    message_processor("[i]\tCreating Time Lapse...")
    video_clip = ImageSequenceClip(valid_files, fps=fps)
    
    print("[i]\tProcessing Audio...")
    if isinstance(audio_input, str):
        audio_clip = AudioFileClip(audio_input).subclip(0, video_clip.duration)
    elif hasattr(audio_input, 'audio_fadein'):
        audio_clip = audio_input.subclip(0, video_clip.duration)
    else:
        raise ValueError("Invalid audio input: must be a file path or an AudioClip")
    
    print("[i]\tApplying Audio Effects...")
    audio_clip = audio_clip.audio_fadein(crossfade_seconds).audio_fadeout(crossfade_seconds)
    video_clip = video_clip.set_audio(audio_clip)
    video_clip = video_clip.fadein(crossfade_seconds).fadeout(crossfade_seconds)

    print("[i]\tCreating End Frame...")
    black_frame_clip = ImageSequenceClip([np.zeros((video_clip.h, video_clip.w, 3))], fps=fps).set_duration(end_black_seconds)
    
    print("[i]\tConcatenating Video Clips...")
    final_clip = concatenate_videoclips([video_clip, black_frame_clip])
    
    print("[i]\tWriting Video File...")
    final_clip.write_videofile(video_path, codec="libx264", audio_codec="aac", logger=logger)

    print("[i]\tClosing Clips...")
    video_clip.close()
    audio_clip.close()
    final_clip.close()

    message_processor(f"[i]\tTime Lapse Saved: {video_path}")

def cleanup(NTFY_TOPIC, path):
    """
    Removes a directory along with all its contents.

    Args:
        directory_path (str or Path): The path to the directory to remove.
    """
    directory_path = Path(path)  # Ensure it's a Path object for consistency
    try:
        if directory_path.is_dir():  # Check if it's a directory
            shutil.rmtree(directory_path)
            message_processor(f"[i]\tAll contents of {directory_path} have been removed.")
        else:
            message_processor(f"[i]\tNo directory found at {directory_path}. Nothing to remove.")
    except Exception as e:
        message_processor(f"[!]\tFailed to remove {directory_path}: {e}")

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
        logging.warning("No NTFY topic provided. Skipping notification.")
        return False

    try:
        NTFY_BASE_URL = "http://ntfy.sh/"
        NTFY_TOPIC = urljoin(NTFY_BASE_URL, NTFY_TOPIC)
        message = str(message)  # cast to str in case we receive something else that won't process
        headers = {'Content-Type': 'application/x-www-form-urlencoded'}
        response = requests.post(NTFY_TOPIC, headers=headers, data=message)
        response.raise_for_status()
        message_processor(f"[i]\tNotification sent to {NTFY_TOPIC}")
        return True
    except requests.RequestException as e:
        message_processor(f"Failed to send notification: {e}", "eeorr")
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
        response = requests.get(SUN_URL)
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
    return datetime.strptime(default_time_str, '%H:%M:%S').time()
