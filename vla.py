import os
import sys
import cv2
import json
import cursor
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
LOGGING_FILE = os.path.join(LOGGING_FOLDER, "vla_log.txt")
logging.basicConfig(
    level=logging.INFO,  # Set the logging level (INFO, WARNING, ERROR, etc.)
    filename=LOGGING_FILE,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

class ImageDownloader:
    def __init__(self, session, out_path):
        self.out_path = Path(out_path)
        self.session = session
        self.prev_image_filename = None
        self.prev_image_size = None

    def download_image(self, session, IMAGE_URL):
        logging.info(f"Download Image Func: {session}")
        global image_size
        today_short_date = datetime.now().strftime("%m%d%Y")
        today_short_time = datetime.now().strftime("%H%M%S")

        
        r = make_request(IMAGE_URL, verify=False)
        if r is None:
            logging.error(f"Image was not downloaded; r = None")
            return

        image_size = len(r.content)

        if image_size == 0:
            logging.error(f"Image was not downloaded; zero size")
            return

        if self.prev_image_filename and (self.out_path / self.prev_image_filename).exists():
            prev_image_path = self.out_path / self.prev_image_filename
            self.prev_image_size = prev_image_path.stat().st_size
            current_image_size = len(r.content)

            if current_image_size != self.prev_image_size:
                FileName = f'vla.{str(today_short_date)}.{str(today_short_time)}.jpg'
                with open(self.out_path / FileName, 'wb') as f:
                    f.write(r.content)
                self.prev_image_filename = FileName
                self.prev_image_size = current_image_size
        else:
            FileName = f'vla.{str(today_short_date)}.{str(today_short_time)}.jpg'
            with open(self.out_path / FileName, 'wb') as f:
                f.write(r.content)
            self.prev_image_filename = FileName
            self.prev_image_size = len(r.content)

def load_config():
    """
    Used to reference an external json file for
    custom config items, in this first round
    the use of proxy servers so that it wasn't
    static in the original script
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
    os.system("cls" if os.name == "nt" else "clear")

def activity(char, images_folder):
    """
    Just prints to stdout the iterator number 
    (resets if the script starts over), 
    the image count in the images directory,
    and the current file size.  This is referenced 
    so that if the file size doesn't change, the 
    image isn't saved in the class above.
    """
    clear()
    files = os.listdir(images_folder)
    jpg_count = sum(1 for file in files if file.lower().endswith('.jpg'))
    print(f"Iter: {char}\nImage Count: {jpg_count}\nImage Size: {image_size}\n" if image_size != 0 else f"{char}\nImage Not Saved: {image_size}\n", end="\r", flush=True)

def create_session(WEBPAGE, verify=False):
    global config
    proxies = config.get('proxies', {})
    http_proxy = proxies.get('http', '')
    https_proxy = proxies.get('https', '')
    max_retries = 3
    headers = {"User-Agent": choice(USER_AGENTS)}
    for _ in range(max_retries):
        try:
            if http_proxy and https_proxy:
                session = requests.get(WEBPAGE, headers=headers, proxies=proxies, verify=verify)
                session.raise_for_status()
                return session
            else:
                requests.get(WEBPAGE, headers=headers, verify=verify)
                session = requests.get(WEBPAGE, headers=headers, verify=verify)
                session.raise_for_status()
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
    This was implemented so that we can make requests
    and check for the use of proxies or not.
    We moved the retry_count from the class to here
    and it works to avoid connection errors that 
    sometimes occur.
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
    We are creating a dict of all of todays images 
    so that we don't include files from yesterday or 
    other days into the time lapse.  We process each image
    with cv2, and capture the output using wurlitzer pipes
    and send that to a dictionary.  If cv2 detects an error
    in the image processing, it will send to stderr and is
    entered into the dict as a value that we will ignore 
    when we iterate over the dict at the end and return a list
    of paths to each image
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
    Create the time lapse video. 
    Grab the first file, create the frame, unpack it,
    and then iterate over the valid images (that aren't corrupt)
    and write each frame.
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
    try:
        clear()
        cursor.hide()
        IMAGES_FOLDER = os.path.join(home, "VLA/images")
        VIDEO_FOLDER = os.path.join(home, "VLA")
        global config
        config = load_config()
        
        os.makedirs(IMAGES_FOLDER, exist_ok=True)
        os.makedirs(LOGGING_FOLDER, exist_ok=True)
        
        session = create_session(WEBPAGE)
        
        downloader = ImageDownloader(session, IMAGES_FOLDER)

        i = 1
        while True:
            try:
                downloader.download_image(session, IMAGE_URL)
                activity(i, IMAGES_FOLDER)
                sleep(15)
                i += 1
            except requests.exceptions.RequestException as e:
                logging.error(f"Error: {e}")
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
            logging.info(f"Video Saved: {video_path}")
            print(f"\n[i]\tTime Lapse Saved:\n[>]\t{video_path}")

        except Exception as e:
            logging.error(f"Keyboard Interrupt; Image Processing Problem: {e}")
            print(f"\n\n[!]\tError processing images to video:\n[i]\t{e}")
        finally:
            cursor.show()


            
if __name__ == "__main__":
    main()
