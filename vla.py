from sys import exit
from random import choice
from wurlitzer import pipes
import requests
import cv2
from time import sleep
from datetime import datetime
import os
from pathlib import Path
import cursor
import json
from http.client import IncompleteRead

from requests.packages.urllib3.exceptions import InsecureRequestWarning
requests.packages.urllib3.disable_warnings(InsecureRequestWarning)

# image_size = 0

"""
TO DO
-clean up function
    wait to allow the video to be reviewed
    asking if we want to remove the images
-config json file
    used to import proxies list
    
"""



url = "https://public.nrao.edu/wp-content/uploads/temp/vla_webcam_temp.jpg"
webpage = "https://public.nrao.edu/vla-webcam/"
stdout_log = "images.json"

user_agents = [
    "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:90.0) Firefox/90.0",
    "Mozilla/5.0 (Windows NT 6.1; Win64; x64; rv:88.0) Firefox/88.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:92.0) Firefox/92.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:96.0) Firefox/96.0",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.0 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Android 11; Mobile; rv:100.0) Firefox/100.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/94.0.4606.81 Safari/537.36 Edg/94.0.992.50",
    "Mozilla/5.0 (Linux; Android 12; Pixel 6) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/94.0.4606.81 Mobile Safari/537.36"
]

class ImageDownloader:
    def __init__(self, out_path):
        self.out_path = Path(out_path)
        self.prev_image_filename = None
        self.prev_image_size = None

    def download_image(self, url):
        global image_size
        today_short_date = datetime.now().strftime("%m%d%Y")
        today_short_time = datetime.now().strftime("%H%M%S")

        headers = {"User-Agent": choice(user_agents)}
        r = make_request(url, headers, config, verify=False)

        image_size = len(r.content)

        if image_size == 0:
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
    file_name = 'config.json'
    local_path = Path(__file__).resolve().parent
    config_path = Path.joinpath(local_path, file_name)

    try:
        with open(config_path, 'r') as file:
            config = json.load(file)
        return config
    except FileNotFoundError:
        """
        We'll build an empty config.json file.
        Edit to use proxies
        ie: "http" : "http://127.0.0.1:8080", "https" : "http://127.0.0.1:8080"
        """
        config_init_starter = {"proxies" : {"http" : "", "https": ""}}
        with open(config_path, 'w') as file:
            json.dump(config_init_starter, file, indent=2)
        load_config()
    except json.JSONDecodeError:
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

def make_request(url, headers, config, verify=False):
    proxies = config.get('proxies', {})
    http_proxy = proxies.get('http', '')
    https_proxy = proxies.get('https', '')
    max_retries = 3
    for retry_count in range(max_retries):
        try:
            if http_proxy and https_proxy:
                requests.get(webpage, headers=headers, proxies=proxies, verify=verify)
                response = requests.get(url, headers=headers, proxies=proxies, verify=verify)
                response.raise_for_status()
            else:
                requests.get(webpage, headers=headers, verify=verify)
                response = requests.get(url, headers=headers, verify=verify)
                response.raise_for_status()
        except IncompleteRead as e:
            print(f"IncompleteRead Error: {e}")
            continue
        except requests.RequestException as e:
            print(f"RequestException Error: {e}")
            break


    return response

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

    return

def main():
    try:
        clear()
        cursor.hide()
        home = Path.home()
        images_folder = os.path.join(home, "VLA/images")
        video_folder = os.path.join(home, "VLA")
        global config
        config = load_config()
        
        os.makedirs(images_folder, exist_ok=True)
                
        downloader = ImageDownloader(images_folder)

        i = 1
        while True:
            downloader.download_image(url)
            activity(i, images_folder)
            sleep(15)
            i += 1

    except KeyboardInterrupt:
        try:
            fps = 10
            today_short_date = datetime.now().strftime("%m%d%Y")
            video_path = os.path.join(video_folder, f"VLA.{today_short_date}.mp4")
            
            print("\n[i]\tValidating Images...")
            valid_files = create_images_dict(images_folder, today_short_date)
                        
            print("[i]\tCreating Time Lapse Video")
            create_time_lapse(valid_files, video_path, fps)

            print(f"\n[i]\tTime Lapse Saved:\n[>]\t{video_path}")

        except Exception as e:
            print(f"\n\n[!]\tError processing images to video:\n[i]\t{e}")
        finally:
            cursor.show()


            
if __name__ == "__main__":
    main()
