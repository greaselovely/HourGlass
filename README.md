# VLA Webcam Time-Lapse Video Creator

## Overview

This script automatically downloads images from the Very Large Array (VLA) observatory webcam, generates a time-lapse video from these images, and adds a soundtrack to the video. It is designed to run continuously, capturing images at random intervals between 15 to 22 seconds. The script handles image download, avoids duplicates through hash checking, and compiles the final images into a video with an accompanying audio track.

## Features

- **Automated Image Downloads:** Downloads images from the VLA observatory webcam.
- **Duplicate Avoidance:** Uses SHA-256 hashing to prevent saving duplicate images.
- **Time-Lapse Video Creation:** Generates a time-lapse video from the collected images.
- **Audio Track Addition:** Adds a soundtrack to the time-lapse video.


## Tested On

- **Ubuntu**
- **Fedora**
- **Debian**

## Requirements

- Python 3.12 or newer

## Setup

1. **Virtual Environment (Recommended):** It's recommended to use a virtual environment for this project.

2. **Install Required Packages:** Install the required Python packages by running:

    ```
    bash setup.sh
    ```

3. **Configuration:** The script uses a `config.json` file for settings such as proxy configuration (if needed) and the ntfy.sh topic for notifications. On the first run, it will create this file with default settings if it doesn't exist.

## Usage

To run the script, navigate to the script's directory and execute:

```
python __main__.py
```

or

```
python ../vla
```

or

```
bash vla.sh
```

The script will start downloading images, logging its activities, and saving the images in a folder named `VLA/images` within your home directory. Press `Ctrl+C` to stop the image downloading process and start the video creation phase.

### Customization

You can modify the following in the `config.json` file to customize the behavior:

- Image download URL
- Download interval range
- Frames per second for the time-lapse video
- Notification settings

## Logging

The script logs its activity, including any errors encountered, to a file named `time_lapse.log` within a `VLA/logging` directory in your home directory.

## Output

The generated time-lapse video will be saved in the `VLA/video` directory within your home directory, named with the date of creation.

## Contributing

Contributions to improve the script are welcome. Please feel free to submit issues or pull requests on the project repository.

## File Descriptions

- `README.md`: This file, containing project documentation and usage instructions.
- `__main__.py`: The main entry point of the script. It orchestrates the overall process of image downloading and video creation.
- `config.json`: Configuration file storing settings such as URLs, paths, and notification preferences.
- `image_dup.py`: Utility script to create duplicate images for testing.
- `requirements.txt`: Lists all Python package dependencies required for the project.
- `setup.sh`: Shell script to set up the project environment and install dependencies.
- `vla.sh`: Shell script to run the main Python script, using tmux.
- `vla_config.py`: Manages loading and parsing of the configuration from `config.json`.
- `vla_core.py`: Contains core functionality for image processing, video creation, and audio handling.