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

output_path = Path.joinpath(Path.home(), "VLA")
if not output_path.exists(): output_path.mkdir(parents=True)

class ImageDownloader:
    def __init__(self, out_path):
        self.out_path = Path(out_path)
        self.prev_image_filename = None
        self.prev_image_size = None

    def download_image(self, img_url):
        today_short_date = datetime.now().strftime("%m%d%Y")
        today_short_time = datetime.now().strftime("%H%M%S")
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:91.0) Gecko/20100101 Firefox/91.0"}
        r = requests.get(img_url, headers=headers, verify=False)
        
        # Check if a previous image exists and if it's the same as the current one
        if self.prev_image_filename and (self.out_path / self.prev_image_filename).exists():
            prev_image_path = self.out_path / self.prev_image_filename
            self.prev_image_size = prev_image_path.stat().st_size
            current_image_size = len(r.content)

            # Compare sizes and save the new image only if it's different
            if current_image_size != self.prev_image_size:
                FileName = f'vla.{str(today_short_date)}.{str(today_short_time)}.jpg'
                with open(self.out_path / FileName, 'wb') as f:
                    f.write(r.content)
                # Update the previous image filename and size for the next run
                self.prev_image_filename = FileName
                self.prev_image_size = current_image_size
        else:
            # If there's no previous image or it's different, save the current one
            FileName = f'vla.{str(today_short_date)}.{str(today_short_time)}.jpg'
            with open(self.out_path / FileName, 'wb') as f:
                f.write(r.content)
            # Update the previous image filename and size for the next run
            self.prev_image_filename = FileName
            self.prev_image_size = len(r.content)

def clear():
    os.system("cls" if os.name == "nt" else "clear")

def activity(char):
    print(char, end="\r", flush=True)

def images_to_video(outputh_path, output_path, fps):
    # images = sorted([img for img in os.listdir(outputh_path) if img.endswith(".jpg")])
    images = sorted([img for img in Path.iterdir(outputh_path) if img.endswith(".jpg")])
    frame = cv2.imread(Path.joinpath(outputh_path, images[0]))
    height, width, _ = frame.shape

    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    video = cv2.VideoWriter(output_path, fourcc, fps, (width, height))

    for image in images:
        print(image)
        img_path = Path.joinpath(outputh_path, image)
        frame = cv2.imread(img_path)
        video.write(frame)

    cv2.destroyAllWindows()
    video.release()

def main():
    try:
        clear()
        cursor.hide()
        i = 1
        downloader = ImageDownloader(output_path)
        while True:
            downloader.download_image(url)
            activity(i)
            sleep(15)
            i += 1
    except KeyboardInterrupt:
        today_short_date = datetime.now().strftime("%m%d%Y")
        video_output_path = Path.joinpath(output_path, f"VLA.{today_short_date}.mp4")
        fps = 10
        images_to_video(output_path, video_output_path, fps)
        cursor.show()

if __name__ == "__main__":
    main()
