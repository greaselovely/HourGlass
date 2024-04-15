import os
from datetime import datetime, timedelta
from shutil import copyfile
from pathlib import Path

# Base configuration
fps = 10
video_length_seconds = 255  # 4 minutes and 15 seconds
number_of_images = fps * video_length_seconds

# Set the directories under the user's home directory
home_directory = Path.home()
images_folder = home_directory / 'VLA' / 'images'
source_image = images_folder / 'base_image.jpg'  # Replace this path with the path to your source image
images_folder.mkdir(parents=True, exist_ok=True)

# Starting time
current_time = datetime.now()

today_short_date = current_time.strftime("%m%d%Y")

for i in range(1, number_of_images + 1):
    today_short_time = current_time.strftime("%H%M%S")
    filename = f'vla.{today_short_date}.{today_short_time}.jpg'
    destination_path = images_folder / filename
    copyfile(source_image, destination_path)
    current_time += timedelta(seconds=15)
