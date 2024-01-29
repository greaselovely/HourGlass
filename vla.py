import os
import sys
import cv2
import json
import cursor
import hashlib
import logging
import requests
from sys import exit
from time import sleep
from pathlib import Path
from random import choice
from wurlitzer import pipes
from datetime import datetime
from http.client import IncompleteRead

from requests.packages.urllib3.exceptions import InsecureRequestWarning
requests.packages.urllib3.disable_warnings(InsecureRequestWarning)

"""
TO DO
-clean up function
    wait to allow the video to be reviewed
    asking if we want to remove the images

"""

IMAGE_URL = "https://public.nrao.edu/wp-content/uploads/temp/vla_webcam_temp.jpg"
WEBPAGE = "https://public.nrao.edu/vla-webcam/"

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

home = Path.home()
LOGGING_FOLDER = os.path.join(home, "VLA/logging")
os.makedirs(LOGGING_FOLDER, exist_ok=True)
LOGGING_FILE = os.path.join(LOGGING_FOLDER, "vla_log.txt")
logging.basicConfig(
    level=logging.INFO,  # Set the logging level (INFO, WARNING, ERROR, etc.)
    filename=LOGGING_FILE,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

class ImageDownloader:
    """
    A class to download images from a specified URL and manage the download process.

    This class handles downloading images, checking for duplicates based on file size,
    and saving new images to a specified output path.

    Attributes:
        out_path (Path): The file path where images will be saved.
        session (requests.Session): The session object used for HTTP requests.
        prev_image_filename (str): The filename of the previously downloaded image.
        prev_image_size (int): The file size of the previously downloaded image.
    """

    def __init__(self, session, out_path):
        """
        Initialize the ImageDownloader class with a session and output path.

        Args:
            session (requests.Session): The session object for HTTP requests.
            out_path (str): The file path where images will be saved.
        """
        self.out_path = Path(out_path)
        self.session = session
        self.prev_image_filename = None
        self.prev_image_size = None
        self.prev_image_hash = None
    
    def compute_md5(self, image_content):
        return hashlib.md5(image_content).hexdigest()

    def download_image(self, session, IMAGE_URL):
        logging.info(f"Download Image Func: {session}")
        global image_size
        today_short_date = datetime.now().strftime("%m%d%Y")
        today_short_time = datetime.now().strftime("%H%M%S")
        
        r = make_request(IMAGE_URL, verify=False)
        if r is None:
            logging.error("Image was not downloaded; r = None")
            return None

        image_size = len(r.content)
        image_hash = self.compute_md5(r.content)

        if image_size == 0:
            logging.error("Image was not downloaded; zero size")
            return None

        if self.prev_image_filename and (self.out_path / self.prev_image_filename).exists():
            prev_image_path = self.out_path / self.prev_image_filename
            self.prev_image_size = prev_image_path.stat().st_size
            current_image_size = len(r.content)

            with open(prev_image_path, 'rb') as f:
                prev_image_hash = self.compute_md5(f.read())

            if image_hash != prev_image_hash:
                FileName = f'vla.{today_short_date}.{today_short_time}.jpg'
                with open(self.out_path / FileName, 'wb') as f:
                    f.write(r.content)
                self.prev_image_filename = FileName
                self.prev_image_size = current_image_size
                # print(f"New Image Hash: {self.prev_image_hash}")
                return image_size  # Image saved, return size
            else:
                logging.error(f"Image was not saved; same hash as previous {self.prev_image_hash}")
                return None  # Image not saved due to being the same size
        else:
            FileName = f'vla.{today_short_date}.{today_short_time}.jpg'
            with open(self.out_path / FileName, 'wb') as f:
                f.write(r.content)
            self.prev_image_filename = FileName
            self.prev_image_size = len(r.content)
            self.prev_image_hash = image_hash
            return image_size  # Image saved, return size

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
        """
        logging.error(f"config.json problem; {e}")
        config_init_starter = {"proxies" : {"http" : "", "https": ""}}
        with open(config_path, 'w') as file:
            json.dump(config_init_starter, file, indent=2)
         # recursion, load the config file since it wasn't found earlier
        return load_config()
    except json.JSONDecodeError as e:
        logging.error(f"JSON Decode error: {e}")
        print(f"Error decoding JSON in '{config_path}'.")
        return None

def clear():
    """
    Clears the terminal screen.

    This function checks the operating system and uses the appropriate command to clear the terminal screen.
    It uses 'cls' for Windows (nt) and 'clear' for other operating systems.
    """
    os.system("cls" if os.name == "nt" else "clear")

def activity(char, images_folder, image_size):
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
    print(f"Iter: {char}\nImage Count: {jpg_count}\nImage Size: {image_size}\n", end="\r", flush=True)

def create_session(WEBPAGE, verify=False):
    """
    Creates and returns a new session for making HTTP requests.

    This function initializes a session with headers including a randomly chosen user agent.
    It attempts to connect to the specified webpage up to a maximum number of retries.
    If proxies are configured, it uses them for the connection.

    Args:
        WEBPAGE (str): The URL to which the session will connect.
        verify (bool): Flag to determine whether to verify the server's TLS certificate.

    Returns:
        requests.Session or None: A session object if the connection is successful, None otherwise.

    Raises:
        SystemExit: If an IncompleteRead or RequestException error occurs during session creation.
    """
    global config
    proxies = config.get('proxies', {})
    http_proxy = proxies.get('http', '')
    https_proxy = proxies.get('https', '')
    max_retries = 3
    headers = {
        "User-Agent": choice(USER_AGENTS),
        "Cache-Control": "no-cache, no-store, must-revalidate",
        "Pragma": "no-cache",
        "Expires": "0"
    }
    for _ in range(max_retries):
        try:
            if http_proxy and https_proxy:
                session = requests.get(WEBPAGE, headers=headers, proxies=proxies, verify=verify)
                session.raise_for_status()
                logging.info(f"Session Created: {session.cookies.get_dict()}, {session.headers.values()}")
                return session
            else:
                requests.get(WEBPAGE, headers=headers, verify=verify)
                session = requests.get(WEBPAGE, headers=headers, verify=verify)
                session.raise_for_status()
                logging.info(f"Session Created: {session.cookies.get_dict()}, {session.headers.values()}")
                return session
        except IncompleteRead as e:
            logging.error(f"Incomplete Read (create_session()): {e}")
            print(f"IncompleteRead Error:\n{e}\nExiting.")
            sys.exit()
        except requests.RequestException as e:
            logging.error(f"Request Exception (create_session()): {e}")
            print(f"RequestException Error:\n{e}\nExiting.")
            sys.exit()
    return None

def make_request(session, verify=False):
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
                response = requests.get(session, proxies=proxies, verify=verify)
                response.raise_for_status()
                return response
            else:
                response = requests.get(session, verify=verify)
                response.raise_for_status()
                return response
        except IncompleteRead as e:
            logging.error(f"Incomplete Read (make_request()): {e}")
            print(f"IncompleteRead Error: {e}")
            return None
        except requests.RequestException as e:
            logging.error(f"Request Exception (make_request()): {e}")
            print(f"RequestException Error: {e}")
            return None
    return None

def create_images_dict(images_folder, today_short_date) -> list:
    """
    Creates a dictionary of image file paths from the specified folder, filtered by the provided date.

    This function filters images by the date included in their filenames, processes each image using cv2 
    to check for errors, and compiles a list of valid image file paths. It uses wurlitzer pipes to capture 
    any error messages from cv2. Images with errors detected by cv2 are excluded from the returned list.

    Args:
        images_folder (str): The directory where the images are stored.
        today_short_date (str): The date string used to filter images relevant to the current day.

    Returns:
        list: A list of valid image file paths, excluding any that cv2 identifies as having errors.
    """
    images = sorted([img for img in os.listdir(images_folder) if img.endswith(".jpg") and today_short_date in img]) 
    images_dict = {}

    for image in images:
        full_image = os.path.join(images_folder, image)
        with pipes() as (out, err):
            cv2.imread(full_image)
        err.seek(0)
        error_message = err.read()
        images_dict[full_image] = error_message

    valid_files = [file_path for file_path, error_message in images_dict.items() if error_message == ""]
    return valid_files

def create_time_lapse(valid_files, output_path, fps) -> None:
    """
    Creates a time-lapse video from a list of valid image files.

    This function reads the first image file to determine the frame size for the video. 
    It then iterates over all the valid image files, adding each as a frame to the video. 
    The function uses OpenCV to handle image reading and video writing.

    Args:
        valid_files (list): A list of file paths for the images to be included in the time-lapse.
        output_path (str): The file path where the generated time-lapse video will be saved.
        fps (int): The frames per second rate for the time-lapse video.

    Returns:
        None: This function does not return anything. It saves the time-lapse video at the specified output path.
    """

    frame = cv2.imread(valid_files[0])  # Read the frame shape from the first file in the list.
    height, width, _ = frame.shape  # unpack the frame shape

    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    video = cv2.VideoWriter(output_path, fourcc, fps, (width, height))

    for n, image in enumerate(valid_files):
        print(f"[i]\t{n}", end='\r')
        frame = cv2.imread(image)
        video.write(frame)

    cv2.destroyAllWindows()
    video.release()



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
        IMAGES_FOLDER = os.path.join(home, "VLA/images")
        VIDEO_FOLDER = os.path.join(home, "VLA")
        global config
        config = load_config()
        
        os.makedirs(IMAGES_FOLDER, exist_ok=True)
        
        session = create_session(WEBPAGE)
        
        downloader = ImageDownloader(session, IMAGES_FOLDER)

        i = 1
        while True:
            try:
                SECONDS = choice(range(15,22))
                image_size = downloader.download_image(session, IMAGE_URL)
                # If we don't save the image because the hash is the same
                # then the image_size is None.  This is strictly console
                # notification and probably should be deprecated.
                if image_size is not None: 
                    activity(i, IMAGES_FOLDER, image_size)
                else:
                    clear()
                    print(f"Error downloading image at iteration: {i}")
                sleep(SECONDS)
                
                i += 1
            except requests.exceptions.RequestException as e:
                logging.error(f"Session timeout or error detect, re-establishing session: {e}")
                print(f"Session timeout or error detect, re-establishing session...\n{e}\n")
                session = create_session(WEBPAGE)
                downloader.download_image(session, IMAGE_URL)

    except KeyboardInterrupt:
        try:
            fps = 10
            today_short_date = datetime.now().strftime("%m%d%Y")
            video_path = os.path.join(VIDEO_FOLDER, f"VLA.{today_short_date}.mp4")
            logging.info(f"Validating Images")
            print("\n[i]\tValidating Images...")
            valid_files = create_images_dict(IMAGES_FOLDER, today_short_date)
            logging.info(f"Creating Time Lapse")
            print("[i]\tCreating Time Lapse Video")
            create_time_lapse(valid_files, video_path, fps)
            logging.info(f"Time Lapse Saved: {video_path}")
            print(f"\n[i]\tTime Lapse Saved:\n[>]\t{video_path}")

        except Exception as e:
            logging.error(f"Keyboard Interrupt; Image Processing Problem: {e}")
            print(f"\n\n[!]\tError processing images to video:\n[i]\t{e}")
        finally:
            cursor.show()


            
if __name__ == "__main__":
    main()
