import requests
import cv2
from time import sleep
from datetime import datetime
import os
from pathlib import Path
import cursor

from requests.packages.urllib3.exceptions import InsecureRequestWarning
requests.packages.urllib3.disable_warnings(InsecureRequestWarning)

url = "https://public.nrao.edu/wp-content/uploads/temp/vla_webcam_temp.jpg"
webpage = "https://public.nrao.edu/vla-webcam/"

proxies = {'http': 'None', 'https': 'None'}

class ImageDownloader:
    def __init__(self, out_path):
        self.out_path = Path(out_path)
        self.prev_image_filename = None
        self.prev_image_size = None

    def download_image(self, filename):
        print(proxies)
        TodayShortDate = datetime.now().strftime("%m%d%Y")
        TodayShortTime = datetime.now().strftime("%H%M%S")
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:91.0) Gecko/20100101 Firefox/91.0"}
        r = requests.get(filename, proxies=proxies, headers=headers, verify=False)

        if len(r.content) == 0:
            print(f"\tError: file size = 0.", end='\r')
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

def clear():
    os.system("cls" if os.name == "nt" else "clear")

def activity(char):
    print(char, end="\r", flush=True)

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
        i = 1
        output_path = os.path.join(os.path.expanduser('~'), "VLA")
        downloader = ImageDownloader(output_path)
        while True:
            downloader.download_image(url)
            activity(i)
            sleep(15)
            i += 1
    except KeyboardInterrupt:
        try:
            TodayShortDate = datetime.now().strftime("%m%d%Y")
            home = os.path.expanduser('~')
            image_folder = f"{home}/VLA"
            output_path = f"{home}/VLA/VLA.{TodayShortDate}.mp4"
            fps = 10
            images_to_video(image_folder, output_path, fps)
            cursor.show()
        except:
            print("[!]\t Nothing to process.  Closing.")

if __name__ == "__main__":
    main()
