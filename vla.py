import os
import re
import cv2
import sys
import json
import cursor
import shutil
import hashlib
import logging
import textwrap
import requests
import pytesseract
import numpy as np
from sys import exit
from PIL import Image
from time import sleep
from pathlib import Path
from random import choice
from wurlitzer import pipes
from bs4 import BeautifulSoup
from http.client import IncompleteRead
from datetime import datetime, timedelta
from graph import create_time_difference_graph
from moviepy.editor import ImageSequenceClip, AudioFileClip, concatenate_videoclips, concatenate_audioclips

today_short_date = datetime.now().strftime("%m%d%Y")

# Used in the event the actual sunrise / sunset is not 
# retrieved from the timeanddate website.  Change if 
# you want it sooner / later.
SUNRISE = '06:00:00'
SUNSET = '19:00:00'
SUNSET_TIME_ADD = 15 # MINUTES

HOME = Path.home()
VLA_BASE = os.path.join(HOME, "VLA")
VIDEO_FOLDER = os.path.join(VLA_BASE, "video")
IMAGES_FOLDER = os.path.join(VLA_BASE, "images")
LOGGING_FOLDER = os.path.join(VLA_BASE, "logging")
AUDIO_FOLDER = os.path.join(VLA_BASE, "audio")
LOG_FILE_NAME = "vla_log.txt"
LOGGING_FILE = os.path.join(LOGGING_FOLDER, LOG_FILE_NAME)
GRAPH_FOLDER = os.path.expanduser("~/VLA/graphs")

for folder in [VLA_BASE, VIDEO_FOLDER, IMAGES_FOLDER, LOGGING_FOLDER, AUDIO_FOLDER]:
    os.makedirs(folder, exist_ok=True)

video_path = os.path.join(VIDEO_FOLDER,f"VLA.{today_short_date}.mp4")

IMAGE_URL = "https://public.nrao.edu/wp-content/uploads/temp/vla_webcam_temp.jpg"
WEBPAGE = "https://public.nrao.edu/vla-webcam/"

GREEN_CIRCLE = "\U0001F7E2"
RED_CIRCLE = "\U0001F534"


USER_AGENTS = [
    "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:90.0) Firefox/90.0",
    "Mozilla/5.0 (Windows NT 6.1; Win64; x64; rv:88.0) Firefox/88.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:92.0) Firefox/92.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:96.0) Firefox/96.0",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.0 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Android 11; Mobile; rv:100.0) Firefox/100.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/94.0.4606.81 Safari/537.36 Edg/94.0.992.50",
    "Mozilla/5.0 (Linux; Android 12; Pixel 6) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/94.0.4606.81 Mobile Safari/537.36"
]

logging.basicConfig(
    level = logging.INFO,  # Set the logging level (INFO, WARNING, ERROR, etc.)
    filename = LOGGING_FILE,
    format = '%(asctime)s - %(levelname)s - %(message)s'
)

class ImageDownloader:
    """
    Class to handle downloading images and managing hash collisions, while explicitly using the session passed to each download attempt.
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
        return hashlib.sha256(image_content).hexdigest()

    def download_image(self, session, IMAGE_URL):
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
            """
            uncomment if you want to inspect the images by hand.  
            Also uncomment the hash_collision_path above under __init__.
            """
            # filename = f'{today_short_date}_{today_short_time}.jpg'
            # collision_file_path = self.hash_collisions_path / filename
            # with open(collision_file_path, 'wb') as f:
            #     f.write(image_content)
            # logging.info(f"{time_stamp} {RED_CIRCLE} Code: {r.status_code} Same Hash: {image_hash}")
            logging.info(f"{RED_CIRCLE} Code: {r.status_code} Same Hash: {image_hash}")
            return None, None
        else:
            # logging.info(f"{time_stamp} {RED_CIRCLE} Code: {r.status_code}  New Hash: {image_hash}")
            logging.info(f"{GREEN_CIRCLE} Code: {r.status_code}  New Hash: {image_hash}")

        self.prev_image_filename = filename
        self.prev_image_size = image_size
        self.prev_image_hash = image_hash  # Ensure this is updated only here
        
        return image_size, filename  # Image saved, return size

def load_config():
    """
    Loads configuration settings from a 'config.json' file.

    This function tries to open and read a 'config.json' file located in the same directory as the script.
    If the file is not found, it creates a new one with default proxy settings.
    If the file is found but contains invalid JSON, an error is logged and None is returned.

    Returns:
        dict or None: A dictionary with configuration settings if successful, None otherwise.
    """
    file_name = 'config.json'
    local_path = Path(__file__).resolve().parent
    config_path = Path.joinpath(local_path, file_name)

    try:
        with open(config_path, 'r') as file:
            config = json.load(file)
        return config
    except FileNotFoundError as e:
        """
        We'll build an empty config.json file.
        Edit to use proxies
        ie: "http" : "http://127.0.0.1:8080", "https" : "http://127.0.0.1:8080"
        Edit to use a Dropbox path for file upload
        ie: "dropbox" : "/home/username/Dropbox/Public"
        Edit to change ntfy subscription topic
        """
        logging.error(f"config.json problem; {e}")
        config_init_starter = {"proxies" : {"http" : "", "https": ""}, "ntfy" : "http://ntfy.sh/vla_time_lapse"}
        with open(config_path, 'w') as file:
            json.dump(config_init_starter, file, indent=2)
        # recursion, load the config file since it wasn't found earlier
        return load_config()
    except json.JSONDecodeError as e:
        message_processor(f"Error decoding JSON in '{config_path}'.", log_level="error")
        return None

def clear():
    """
    Clears the terminal screen.

    This function checks the operating system and uses the appropriate command to clear the terminal screen.
    It uses 'cls' for Windows (nt) and 'clear' for other operating systems.
    """
    os.system("cls" if os.name == "nt" else "clear")

def log_jamming(log_message):
    """
    Formats a log message to fit a specified width with indentation.  He fixes the cable.

    This function takes a log message as input and formats it using textwrap to ensure that it fits within a
    width of 90 characters. It adds a uniform indentation after the first line to align subsequent lines with
    the end of the log preface, which is 34 characters long. This indentation applies to all lines following
    the first line of the log message.

    The primary purpose is to enhance the readability of log messages, especially when they contain long strings
    or data structures that would otherwise extend beyond the typical viewing area of a console or log file viewer.

    Parameters:
    - log_message (str): The log message to be formatted.

    Returns:
    - str: A string that has been formatted to meet the specified constraints.

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
    if print_me:
        print(message)
    log_func = getattr(logging, log_level, logging.info)
    log_func(message)
    if ntfy:
        send_to_ntfy(message)

def activity(char, images_folder, image_size, time_stamp=""):
    """
    Displays the current status of the image downloading activity in the terminal.

    This function is called to print the current iteration number, the total count of 
    JPEG images in the specified folder, and the size of the last downloaded image. 
    If the last downloaded image size is zero, it indicates that the image was not saved.

    Args:
        char (int): The current iteration number of the downloading loop.
        images_folder (str): Path to the folder where images are being saved.

    Returns:
        None: This function does not return anything. It only prints to stdout.
    """
    clear()
    files = os.listdir(images_folder)
    jpg_count = sum(1 for file in files if file.lower().endswith('.jpg'))
    print(f"[i]\tIteration: {char}\n[i]\tImage Count: {jpg_count}\n[i]\tImage Size: {image_size}\n", end="\r", flush=True)

def create_session(webpage):
    """
    Initializes a session and verifies its ability to connect to a given webpage.
    
    Args:
        webpage (str): The URL to test the session's connectivity.
        verify (bool): Whether to verify the SSL certificate.

    Returns:
        A requests.Session object if successful, None otherwise.
    """
    session = requests.Session()
    session.headers.update({
        "User-Agent": choice(USER_AGENTS),
        "Cache-Control": "no-cache, no-store, must-revalidate",
        "Pragma": "no-cache",
        "Expires": "0"
    })

    # Configure proxies if they are set in config
    proxies = config.get('proxies', {})
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

    This function attempts to make a GET request using the given session. 
    If proxies are configured, they are used in the request. The function retries 
    the request up to a maximum number of times in case of connection errors.

    Args:
        session (requests.Session): The session object to be used for making the request.
        verify (bool): Flag to determine whether to verify the server's TLS certificate.

    Returns:
        requests.Response or None: The response object if the request is successful, 
                                None if there are connection errors or exceptions.
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
    Creates a dictionary of image file paths from the specified folder, filtered by the provided date.
    This function first checks if 'valid_images.json' exists in the folder and reads from it if it does.
    If it does not exist, it filters images by the date included in their filenames, processes each image using cv2 
    to check for errors, and compiles a list of valid image file paths. Images with errors detected by cv2 are excluded.
    The valid images are then saved to 'valid_images.json' in the same directory.

    Args:
        images_folder (str): The directory where the images are stored.

    Returns:
        list: A list of valid image file paths, excluding any that cv2 identifies as having errors.
    """
    valid_images_path = Path(images_folder) / "valid_images.json"
    
    # Check if the valid_images.json file exists and is not empty
    if valid_images_path.exists() and valid_images_path.stat().st_size > 0:
        try:
            with open(valid_images_path, 'r') as file:
                valid_files = json.load(file)
                message = f"[i]\tExisting Validation Used"
                message_processor(message, 'info')
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
        num_images (int): The number of images to be included in the time-lapse video.
        fps (int): The frames per second rate for the time-lapse video.

    Returns:
        int: The expected duration of the time-lapse video in milliseconds.
    """
    duration_sec = num_images / fps
    duration_ms = int(duration_sec * 1000)
    return duration_ms

def single_song_download():
    """
    Downloads a random song from a specified URL, meeting a minimum duration criterion.

    This function randomly selects a song from the "soundtracks.loudly.com/songs" API,
    ensuring the song's duration exceeds a specified threshold. If the first chosen song
    does not meet the duration threshold, the function retries up to three times to find
    a suitable song. If a song meeting the criteria is found, it is downloaded and saved
    in a specified subdirectory.

    Parameters:
    - duration_threshold (int): The minimum duration (in milliseconds) required for the song to be considered for download. 
                                Default value is 150,000 milliseconds (2 minutes and 30 seconds).

    Returns:
    - tuple: A tuple containing the name of the downloaded audio file and its full path. 
            Returns None if no song meeting the criteria could be found or if an error occurs.

    Raises:
    - requests.RequestException: If an HTTP request error occurs during the song selection or download process.

    Note:
    The function prints messages to the console indicating the status of the download or any errors encountered.
    """
    try:
        user_agent = choice(USER_AGENTS)
        headers = {"User-Agent": user_agent}
        url = "https://soundtracks.loudly.com/songs"
        r = requests.get(url, headers=headers)
        r.raise_for_status()  # Raises stored HTTPError, if one occurred.
        
        last_page = r.json().get('pagination_data', {}).get('last_page', 20)
        page = choice(range(1, last_page + 1))
        url = f"https://soundtracks.loudly.com/songs?page={page}"
        r = requests.get(url, headers=headers)
        r.raise_for_status()
        
        data = r.json()
        songs = data.get('items', [])
        if not songs:
            print("No songs found.")
            return
        
        song = choice(songs)
        song_duration = song.get('duration', 0)
        
        # If the song duration is less than the duration_threshold, retry fetching a song

        # song = choice(songs)
        # song_duration = song.get('duration', 0)

        song_download_path = song.get('music_file_path')
        if not song_download_path:
            print("Song download path not found.")
            return
        
        # Download song content
        r = requests.get(song_download_path)
        r.raise_for_status()
        
        # Prepare filename and save
        song_name = song.get('title', 'Unknown Song').replace('/', '_')  # Replace slashes to avoid path issues
        audio_name = f"{song_name}.mp3"

        full_audio_path = os.path.join(AUDIO_FOLDER, audio_name)
        
        with open(full_audio_path, 'wb') as f:
            f.write(r.content)
            
        print(f"[>]\tDownloaded: {audio_name}")

        return full_audio_path, song_duration
    
    except requests.RequestException as e:
        print(f"[!]\tAn error occurred:\n[!]\t{e}")

def audio_download(video_duration) -> list:
    """
    Downloads multiple songs, ensuring their total duration covers the video duration. Splits playtime evenly.
    
    Args:
        video_duration (int): Required total audio duration in milliseconds.
        audio_folder (str or Path): Directory to save the downloaded audio files.
        user_agents (list): List of user agent strings to use for requests.
        
    Returns:
        str: Path to the concatenated audio file that meets the video duration, or None if unsuccessful.
    """
    songs = []
    total_duration = 0  # total duration in seconds
    attempts = 0
    max_attempts = 10
    while total_duration < video_duration / 1000 and attempts < max_attempts:
        song_path, song_duration_ms = single_song_download()
        if song_path:
            songs.append((song_path, song_duration_ms / 1000))  # Store duration in seconds
            total_duration += song_duration_ms / 1000

        attempts += 1

    if total_duration < video_duration / 1000:  # Check if the combined duration is sufficient
        print("Failed to download sufficient audio length.")
        return None
    
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
    video_clip = ImageSequenceClip(valid_files, fps=fps)
    
    # Check if audio_input is a string (path) or an AudioClip
    if isinstance(audio_input, str):
        audio_clip = AudioFileClip(audio_input).subclip(0, video_clip.duration)
    elif hasattr(audio_input, 'audio_fadein'):
        # Assume audio_input is already an AudioClip if it has audio_fadein method
        audio_clip = audio_input.subclip(0, video_clip.duration)
    else:
        raise ValueError("Invalid audio input: must be a file path or an AudioClip")
    
    audio_clip = audio_clip.audio_fadein(crossfade_seconds).audio_fadeout(crossfade_seconds)
    video_clip = video_clip.set_audio(audio_clip)
    video_clip = video_clip.fadein(crossfade_seconds).fadeout(crossfade_seconds)

    black_frame_clip = ImageSequenceClip([np.zeros((video_clip.h, video_clip.w, 3))], fps=fps).set_duration(end_black_seconds)
    final_clip = concatenate_videoclips([video_clip, black_frame_clip])
    final_clip.write_videofile(video_path, codec="libx264", audio_codec="aac")

    video_clip.close()
    audio_clip.close()
    final_clip.close()

def rename_images(IMAGES_FOLDER, filename):
    # Regex pattern to extract the date and time
    pattern = re.compile(r'\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}')

    file_path = os.path.join(IMAGES_FOLDER, filename)
    
    try:
        img = Image.open(file_path)
        
        left, top, right, bottom = 0, 0, 800, 50 
        
        cropped_img = img.crop((left, top, right, bottom))
        text = pytesseract.image_to_string(cropped_img, config='--psm 6')
        
        match = pattern.search(text)
        if match:
            date_time = match.group(0)
            date_part, time_part = date_time.split()
            date_part = date_part.replace('-', '')  # Format as YYYYMMDD
            time_part = time_part.replace(':', '')  # Format as HHMMSS
            new_date = date_part[4:] + date_part[:4]  # Convert YYYYMMDD to MMDDYYYY
            
            new_filename = f"vla.{new_date}.{time_part}.jpg"
            new_file_path = os.path.join(IMAGES_FOLDER, new_filename)
            
            os.rename(file_path, new_file_path)
            message_processor(f"[i]\t{filename} -> {new_filename}")
        else:
            message_processor(f"[!]\tDate and time not found in {filename}")
    
    except Exception as e:
        os.remove(file_path)
        message_processor(f"[!]\tError processing file {filename}: {e}")

def cleanup(path):
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

def send_to_ntfy(message="Incomplete Message"):
    global config
    message = str(message) # cast it to str in case we receive something else that won't process
    ntfy_url = config.get("ntfy")
    headers = {'Content-Type': 'application/x-www-form-urlencoded',}
    requests.post(ntfy_url, headers=headers, data=message)

def sun_schedule():
    time_url = "https://www.timeanddate.com/sun/@5481136"
    try:
        response = requests.get(time_url)
        response.raise_for_status()  # Raise an HTTPError for bad responses
        html_content = response.text
    except requests.RequestException as e:
        print(f"Error fetching the HTML content from {time_url}: {e}")
        return None
    if html_content:
        return BeautifulSoup(html_content, 'html.parser')
    else:
        return

def find_time_and_convert(soup, text, default_time_str):
    if soup is not None:
        element = soup.find('th', string=lambda x: x and text in x)
        if element and element.find_next_sibling('td'):
            time_text = element.find_next_sibling('td').text
            time_match = re.search(r'\d+:\d+\s(?:am|pm)', time_text)
            if time_match:
                return datetime.strptime(time_match.group(), '%I:%M %p').time()
    return datetime.strptime(default_time_str, '%H:%M:%S').time()


def main_sequence():
    global config, rename
    fps = 10
    message_processor("\n[i]\tValidating Images...")
    valid_files = create_images_dict(IMAGES_FOLDER)
    duration_threshold = calculate_video_duration(len(valid_files), fps)
    message_processor(f"Video Duration: {duration_threshold}", print_me=False)
    full_audio_path = audio_download(duration_threshold)
    if len(full_audio_path) >= 2:
        final_song = concatenate_songs(full_audio_path)
    else:
        final_song = full_audio_path[0][0]
    message_processor(f"[i]\tCreating Time Lapse Video\n{'#' * 50}")
    create_time_lapse(valid_files, video_path, fps, final_song, crossfade_seconds=3, end_black_seconds=3)
    message_processor(f"{'#' * 50}\n[i]\tTime Lapse Saved:\n[>]\t{video_path}")
    if video_path and os.path.exists(video_path):
        message_processor(f"{os.path.basename(video_path)} saved", ntfy=True, print_me=False)
        # create_time_difference_graph(IMAGES_FOLDER, GRAPH_FOLDER)
        cleanup(IMAGES_FOLDER)
        cleanup(AUDIO_FOLDER)

def main():
    """
    The main function of the script. It orchestrates the process of downloading images,
    creating a time-lapse video, and handling exceptions.

    This function sets up the necessary folders, initializes a session, and continuously
    downloads images at a set interval. In case of a keyboard interrupt, it proceeds to 
    validate the downloaded images and create a time-lapse video from them. Any errors 
    encountered during image processing or video creation are logged and displayed.
    """
    try:
        clear()
        cursor.hide()
        global config
        config = load_config()
                  
        soup = sun_schedule()

        sunrise_time = find_time_and_convert(soup, 'Sunrise Today:', SUNRISE)
        sunset_time = find_time_and_convert(soup, 'Sunset Today:', SUNSET)

        now = datetime.now()
        sunrise_datetime = datetime.combine(now.date(), sunrise_time)
        sunset_datetime = datetime.combine(now.date(), sunset_time)
        sunset_datetime += timedelta(minutes=SUNSET_TIME_ADD)

        if now < sunrise_datetime:
            time_diff = (sunrise_datetime - now).total_seconds()
            sleep_timer = time_diff
            message_processor(f"Sleeping for {sleep_timer} seconds / {sleep_timer  / 60} minutes until the sunrise at {sunrise_time}.", ntfy=True, print_me=True)
            sleep(sleep_timer)
            message_processor(f"Woke up! The current time is {datetime.now().time()}.", ntfy=True, print_me=True)
        else:
            message_processor("Sunrise time has already passed for today.", ntfy=True, print_me=True)

        session = create_session(WEBPAGE)
        
        downloader = ImageDownloader(session, IMAGES_FOLDER)

        i = 1
        while True:
            try:
                TARGET_HOUR = sunset_time.hour
                TARGET_MINUTE = sunset_time.minute
                SECONDS = choice(range(15, 22))  # sleep timer seconds

                image_size, filename = downloader.download_image(session, IMAGE_URL)
                
                if image_size is not None:
                    activity(i, IMAGES_FOLDER, image_size)
                    # rename_images(IMAGES_FOLDER, filename)
                else:
                    clear()
                    print(f"[!]\t{RED_CIRCLE} Iteration: {i}")

                sleep(SECONDS)
                
                i += 1
                now = datetime.now()
                if now.hour == TARGET_HOUR and now.minute >= TARGET_MINUTE:
                    main_sequence()
                    cursor.show()
            except requests.exceptions.RequestException as e:
                log_message = f"Session timeout or error detected, re-establishing session: {e}"
                logging.error(log_jamming(log_message))
                message_processor(f"Session timeout or error detected, re-establishing session...\n{e}\n", log_level="error")
                session = create_session(WEBPAGE)
                downloader.download_image(session, IMAGE_URL)
            finally:
                cursor.show()

    except KeyboardInterrupt:
        try:
            main_sequence()
        except Exception as e:
            message_processor(f"\n\n[!]\tError processing images to video:\n[i]\t{e}")
            main_sequence()
        finally:
            cursor.show()

if __name__ == "__main__":
    main()
