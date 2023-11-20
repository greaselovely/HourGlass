from random import choice
import requests
import cv2
from time import sleep
from datetime import datetime
import os
from pathlib import Path
import cursor
from http.client import IncompleteRead

from requests.packages.urllib3.exceptions import InsecureRequestWarning
requests.packages.urllib3.disable_warnings(InsecureRequestWarning)

url = "https://public.nrao.edu/wp-content/uploads/temp/vla_webcam_temp.jpg"
webpage = "https://public.nrao.edu/vla-webcam/"

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

proxies = {'http': 'http://10.29.60.103:3128', 'https': 'http://10.29.60.103:3128'}

class ImageDownloader:
    def __init__(self, out_path):
        self.out_path = Path(out_path)
        self.prev_image_filename = None
        self.prev_image_size = None

    def download_image(self, filename):
        global image_size
        TodayShortDate = datetime.now().strftime("%m%d%Y")
        TodayShortTime = datetime.now().strftime("%H%M%S")
        headers = {"User-Agent": choice(user_agents)}

        max_retries = 3
        for retry_count in range(max_retries):
            try:
                r = requests.get(filename, headers=headers, proxies=proxies, verify=False)
                r.raise_for_status()

                image_size = len(r.content)

                if image_size == 0:
                    return

                if self.prev_image_filename and (self.out_path / self.prev_image_filename).exists():
                    prev_image_path = self.out_path / self.prev_image_filename
                    self.prev_image_size = prev_image_path.stat().st_size
                    current_image_size = len(r.content)

                    if current_image_size != self.prev_image_size:
                        FileName = f'vla.{str(TodayShortDate)}.{str(TodayShortTime)}.jpg'
                        with open(self.out_path / FileName, 'wb') as f:
                            f.write(r.content)
                        self.prev_image_filename = FileName
                        self.prev_image_size = current_image_size
                else:
                    FileName = f'vla.{str(TodayShortDate)}.{str(TodayShortTime)}.jpg'
                    with open(self.out_path / FileName, 'wb') as f:
                        f.write(r.content)
                    self.prev_image_filename = FileName
                    self.prev_image_size = len(r.content)
                break
            except IncompleteRead as e:
                print(f"IncompleteRead Error: {e}")
                continue
            except requests.RequestException as e:
                print(f"RequestException Error: {e}")
                break

def clear():
    os.system("cls" if os.name == "nt" else "clear")

def activity(char, images_folder):
    clear()
    files = os.listdir(images_folder)
    jpg_count = sum(1 for file in files if file.lower().endswith('.jpg'))
    print(f"Iter: {char}\nImage Count: {jpg_count}\nImage Size: {image_size}\n" if image_size != 0 else f"{char}\nImage Not Saved: {image_size}\n", end="\r", flush=True)

def images_to_video(image_folder, output_path, fps):
    images = sorted([img for img in os.listdir(image_folder) if img.endswith(".jpg")])
    frame = cv2.imread(os.path.join(image_folder, images[0]))
    height, width, _ = frame.shape

    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    video = cv2.VideoWriter(output_path, fourcc, fps, (width, height))

    for image in images:
        print(image)
        img_path = os.path.join(image_folder, image)
        frame = cv2.imread(img_path)
        video.write(frame)

    cv2.destroyAllWindows()
    video.release()

def main():
    try:
        clear()
        cursor.hide()
        home = os.path.expanduser('~')
        images_folder = os.path.join(home, "VLA/images")
        video_folder = os.path.join(home, "VLA")
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
            TodayShortDate = datetime.now().strftime("%m%d%Y")
            video_path = os.path.join(video_folder, f"VLA.{TodayShortDate}.mp4")

            fps = 10
            images_to_video(images_folder, video_path, fps)
            cursor.show()

        except Exception as e:
            clear()
            print(f"[!]\tError processing images to video: {e}")
        finally:
            cursor.show()


            
if __name__ == "__main__":
    main()
