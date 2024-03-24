# VLA Webcam Time-Lapse Video Creator

## Overview

This script automatically downloads images from the Very Large Array (VLA) observatory webcam, generates a time-lapse video from these images, and adds a soundtrack to the video. It is designed to run continuously, capturing images at random intervals between 15 to 22 seconds. The script handles image download, avoids duplicates through hash checking, and compiles the final images into a video with an accompanying audio track.

## Features

- **Automated Image Downloads:** Downloads images from the VLA observatory webcam.
- **Duplicate Avoidance:** Uses SHA-256 hashing to prevent saving duplicate images.
- **Time-Lapse Video Creation:** Generates a time-lapse video from the collected images.
- **Audio Track Addition:** Adds a soundtrack to the time-lapse video, ensuring the video has a minimum duration.

## Requirements

- Python 3.6 or newer
- External Python packages: `requests`, `numpy`, `cv2` (OpenCV), `moviepy`, `cursor`, `logging`, `hashlib`, `json`
- Internet connection for downloading images and audio tracks.

## Setup

1. **venv Recommended**

2. **Install Required Packages:** Install the required Python packages by running:

    ```
    pip install -r requirements.txt
    ```

3. **Configuration:** The script uses a `config.json` file for proxy settings (if needed). On the first run, it will attempt to create this file with default settings if it doesn't exist.

## Usage

To run the script, navigate to the script's directory and execute:

```
python vla.py
```

The script will start downloading images, logging its activities, and saving the images in a folder named `VLA/images` within your home directory. Press `Ctrl+C` to stop the image downloading process and start the video creation phase.

### Customization

You can modify the following variables within the script to customize the behavior:

- `IMAGE_URL`: URL of the webcam image to download.
- `SECONDS`: Interval range for image downloads (default is 15 to 22 seconds).
- `fps`: Frames per second for the generated time-lapse video.

## Logging

The script logs its activity, including any errors encountered, to a file named `vla_log.txt` within a `VLA/logging` directory in your home directory.

## Output

The generated time-lapse video will be saved in the `VLA` directory within your home directory, named with the date of creation.

## Note

This script is intended for educational and hobbyist purposes. Please ensure you have the right to download and use images from the VLA observatory webcam.
