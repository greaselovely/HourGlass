import os
from datetime import datetime, timedelta
from shutil import copyfile
from pathlib import Path
import logging
import argparse
from PIL import Image, ImageDraw, ImageFont
import uuid

def setup_logging():
    # Set up the log directory in the user's home directory
    from timelapse_config import LOGGING_FOLDER
    log_dir = Path(LOGGING_FOLDER)
    log_dir.mkdir(parents=True, exist_ok=True)

    # Set the log file path
    log_file = log_dir / 'image_testing.log'

    # Set up logging to both file and console
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler()
        ]
    )

    logging.info(f"Logging to file: {log_file}")
    
def parse_arguments():
    parser = argparse.ArgumentParser(description="Generate a series of timestamped images.")
    parser.add_argument("--fps", type=int, default=10, help="Frames per second")
    parser.add_argument("--duration", type=int, default=120, help="Video length in seconds")
    parser.add_argument("--interval", type=int, default=15, help="Time interval between frames in seconds")
    parser.add_argument("--source", type=str, default="base_image.jpg", help="Source image filename")
    return parser.parse_args()

def create_base_image(path):
    # Create a new image with white background
    img_width, img_height = 800, 600
    img = Image.new('RGB', (img_width, img_height), color='white')
    d = ImageDraw.Draw(img)
    
    # Use the default font
    font = ImageFont.load_default()

    from timelapse_config import PROJECT_NAME
    text = f"{PROJECT_NAME} Base Test Image"
    target_width = img_width * 2/3  # Target width is 2/3 of the image width

    # Find the right font size
    font_size = 1
    while True:
        font = font.font_variant(size=font_size)
        bbox = d.textbbox((0, 0), text, font=font)
        text_width = bbox[2] - bbox[0]
        if text_width > target_width:
            font_size -= 1
            font = font.font_variant(size=font_size)
            break
        font_size += 1

    # Get the final text dimensions
    bbox = d.textbbox((0, 0), text, font=font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]

    # Calculate position to center the text
    position = ((img_width - text_width) / 2, (img_height - text_height) / 2)

    # Draw the text
    d.text(position, text, fill=(0, 0, 0), font=font)

    # Save the image
    img.save(path)
    logging.info(f"Created base image: {path}")
    logging.info(f"Text width: {text_width}/{img_width} pixels, Font size: {font_size}")
def get_or_create_run_id():
    today = datetime.now().strftime("%Y%m%d")
    run_id = f"{today}_{str(uuid.uuid4())[:8]}"
    return run_id

def generate_images(fps, duration, interval, source_filename, run_id):
    # Set the directories under the user's home directory
    home_directory = Path.home()
    images_folder = home_directory / 'VLA' / 'images' / run_id
    source_image = home_directory / 'VLA' / 'images' / source_filename

    # Ensure the images folder exists
    images_folder.mkdir(parents=True, exist_ok=True)

    # Check if the source image exists, if not, create it
    if not source_image.exists():
        logging.warning(f"Source image not found: {source_image}. Creating a base test image.")
        create_base_image(source_image)

    # Calculate the number of images
    number_of_images = fps * duration

    # Starting time
    current_time = datetime.now()

    for i in range(1, number_of_images + 1):
        try:
            today_short_date = current_time.strftime("%m%d%Y")
            today_short_time = current_time.strftime("%H%M%S")
            filename = f'vla.{today_short_date}.{today_short_time}.jpg'
            destination_path = images_folder / filename
            copyfile(source_image, destination_path)
            logging.info(f"Created image: {filename} in run_id: {run_id}")
            current_time += timedelta(seconds=interval)
        except Exception as e:
            logging.error(f"Error creating image {i}: {str(e)}")

def main():
    setup_logging()
    args = parse_arguments()
    
    run_id = get_or_create_run_id()
    logging.info(f"Starting image generation process for run_id: {run_id}")
    generate_images(args.fps, args.duration, args.interval, args.source, run_id)
    logging.info(f"Image generation process completed for run_id: {run_id}")

if __name__ == "__main__":
    main()


