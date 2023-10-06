import requests
import cv2
from time import sleep
from datetime import datetime
import os
from pathlib import Path
import cursor

from requests.packages.urllib3.exceptions import InsecureRequestWarning
requests.packages.urllib3.disable_warnings(InsecureRequestWarning)

class ImageDownloader:
    def __init__(self, out_path):
        self.out_path = Path(out_path)
        self.prev_image_filename = None
        self.prev_image_size = None

    def download_image(self, img_url):
        TodayShortDate = datetime.now().strftime("%m%d%Y")
        TodayShortTime = datetime.now().strftime("%H%M%S")
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:91.0) Gecko/20100101 Firefox/91.0"}
        r = requests.get(img_url, headers=headers, verify=False)
        
        # Check if a previous image exists and if it's the same as the current one
        if self.prev_image_filename and (self.out_path / self.prev_image_filename).exists():
            prev_image_path = self.out_path / self.prev_image_filename
            self.prev_image_size = prev_image_path.stat().st_size
            current_image_size = len(r.content)

            # Compare sizes and save the new image only if it's different
            if current_image_size != self.prev_image_size:
                FileName = f'vla.{str(TodayShortDate)}.{str(TodayShortTime)}.jpg'
                with open(self.out_path / FileName, 'wb') as f:
                    f.write(r.content)
                # Update the previous image filename and size for the next run
                self.prev_image_filename = FileName
                self.prev_image_size = current_image_size
        else:
            # If there's no previous image or it's different, save the current one
            FileName = f'vla.{str(TodayShortDate)}.{str(TodayShortTime)}.jpg'
            with open(self.out_path / FileName, 'wb') as f:
                f.write(r.content)
            # Update the previous image filename and size for the next run
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
        OutPath = os.path.join(os.path.expanduser('~'), "VLA")
        downloader = ImageDownloader(OutPath)
        while True:
            downloader.download_image("https://public.nrao.edu/wp-content/uploads/temp/vla_webcam_temp.jpg")
            activity(i)
            sleep(15)
            i += 1
    except KeyboardInterrupt:
        TodayShortDate = datetime.now().strftime("%m%d%Y")
        home = os.path.expanduser('~')
        image_folder = f"{home}/VLA"
        output_path = f"{home}/VLA/VLA.{TodayShortDate}.mp4"
        fps = 10
        images_to_video(image_folder, output_path, fps)
        cursor.show()

if __name__ == "__main__":
    main()
