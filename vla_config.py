import json
import logging
import os, sys
from pathlib import Path
from datetime import datetime

def load_config():
    """
    Loads configuration settings from a 'config.json' file, creating it if it doesn't exist,
    and updating it if a newer version is available.

    This function performs the following steps:
    1. Attempts to read the 'config.json' file from the same directory as the script.
    2. If the file doesn't exist, creates a new one with default settings.
    3. If the file exists but has an older version, updates it to the current version.
    4. Handles JSON decoding errors and logs appropriate messages.

    Returns:
        dict or None: A dictionary with configuration settings if successful, None otherwise.
    """

    CONFIG_FILE = 'config.json'
    LOCAL_PATH = Path(__file__).resolve().parent
    CONFIG_PATH = Path.joinpath(LOCAL_PATH, CONFIG_FILE)

    CURRENT_VERSION = 1.2  # Increment this when making changes to the config structure

    def create_default_config():
        """
        Creates a default configuration dictionary with predefined settings.

        This function sets up default values for various configuration parameters including:
        - Proxy settings
        - Notification URL
        - Sun-related times
        - File and folder paths
        - URLs for image and webpage
        - Output symbols
        - User agent strings

        Returns:
            dict: A dictionary containing the default configuration settings.
        """

        home = Path.home()
        vla_base = os.path.join(home, "VLA")
        return {
            "version": CURRENT_VERSION,
            "proxies": {
                "http": "",
                "https": ""
            },
            "alerts": {
                "comment" : "This is just the topic subscription name, not the entire URL",
                "ntfy": ""
            },
            "sun": {
                "SUNRISE": "06:00:00",
                "SUNSET": "19:00:00",
                "SUNSET_TIME_ADD": 60
            },
            "files_and_folders": {
                "LOG_FILE_NAME": "time_lapse.log",
                "VLA_BASE": str(vla_base),
                "VIDEO_FOLDER": os.path.join(vla_base, "video"),
                "IMAGES_FOLDER": os.path.join(vla_base, "images"),
                "LOGGING_FOLDER": os.path.join(vla_base, "logging"),
                "AUDIO_FOLDER": os.path.join(vla_base, "audio"),
            },
            "urls": {
                "IMAGE_URL": "https://public.nrao.edu/wp-content/uploads/temp/vla_webcam_temp.jpg",
                "WEBPAGE": "https://public.nrao.edu/vla-webcam/"
            },
            "output_symbols": {
                "GREEN_CIRCLE": "\U0001F7E2",
                "RED_CIRCLE": "\U0001F534"
            },
            "user_agents": [
                "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:90.0) Firefox/90.0",
                "Mozilla/5.0 (Windows NT 6.1; Win64; x64; rv:88.0) Firefox/88.0",
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:92.0) Firefox/92.0",
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:96.0) Firefox/96.0",
                "Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.0 Mobile/15E148 Safari/604.1",
                "Mozilla/5.0 (Android 11; Mobile; rv:100.0) Firefox/100.0",
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/94.0.4606.81 Safari/537.36 Edg/94.0.992.50",
                "Mozilla/5.0 (Linux; Android 12; Pixel 6) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/94.0.4606.81 Mobile Safari/537.36"
            ]
        }

    def update_config(config):
        """
        Updates an existing configuration to the current version.

        This function performs the following steps:
        1. Checks if the provided config is outdated.
        2. If outdated, merges the existing config with the default config.
        3. Updates the version number to the current version.
        4. Writes the updated config back to the file.

        Args:
            config (dict): The existing configuration dictionary.

        Returns:
            dict: The updated configuration dictionary.
        """
        if 'version' not in config or config['version'] < CURRENT_VERSION:
            default_config = create_default_config()
            updated_config = default_config.copy()
            
            # Merge existing config with default config
            for key, value in config.items():
                if key in updated_config and isinstance(updated_config[key], dict):
                    updated_config[key].update(value)
                else:
                    updated_config[key] = value
            
            updated_config['version'] = CURRENT_VERSION
            
            with open(CONFIG_PATH, 'w') as file:
                json.dump(updated_config, file, indent=2)
            
            logging.info(f"Updated config file to version {CURRENT_VERSION}")
            return updated_config
        return config

    try:
        with open(CONFIG_PATH, 'r') as file:
            config = json.load(file)
        return update_config(config)
    except FileNotFoundError:
        logging.warning(f"config.json not found at {CONFIG_PATH}; creating with default values.")
        default_config = create_default_config()
        with open(CONFIG_PATH, 'w') as file:
            json.dump(default_config, file, indent=2)
        return default_config
    except json.JSONDecodeError as e:
        logging.error(f"Error decoding JSON in '{CONFIG_PATH}': {e}")
        return None
    

"""
This section loads the configuration using the load_config() function and applies
the settings to global variables. It performs the following steps:
1. Calls load_config() to get the configuration dictionary.
2. If successful, extracts various settings from the config and assigns them to global variables.
3. Sets up logging with the specified file and format.
4. If loading fails, logs an error message and exits the script.

The global variables set include:
- Proxy settings
- Sun-related times
- File and folder paths
- URLs for image and webpage
- Output symbols
- User agents
- Notification URL
- Current date in short format

Logging is configured to write to a file specified in the config.
"""

config = load_config()

if config:
    PROXIES = config['proxies']
    SUNRISE = config['sun']['SUNRISE']
    SUNSET = config['sun']['SUNSET']
    SUNSET_TIME_ADD = config['sun']['SUNSET_TIME_ADD']
    SUN_URL = config['sun']['URL']
    
    VLA_BASE = config['files_and_folders']['VLA_BASE']
    VIDEO_FOLDER = config['files_and_folders']['VIDEO_FOLDER']
    IMAGES_FOLDER = config['files_and_folders']['IMAGES_FOLDER']
    LOGGING_FOLDER = config['files_and_folders']['LOGGING_FOLDER']
    AUDIO_FOLDER = config['files_and_folders']['AUDIO_FOLDER']
    LOG_FILE_NAME = config['files_and_folders']['LOG_FILE_NAME']
    LOGGING_FILE = os.path.join(LOGGING_FOLDER, LOG_FILE_NAME)
    
    IMAGE_URL = config['urls']['IMAGE_URL']
    WEBPAGE = config['urls']['WEBPAGE']
    
    global GREEN_CIRCLE, RED_CIRCLE
    GREEN_CIRCLE = config['output_symbols']['GREEN_CIRCLE']
    RED_CIRCLE = config['output_symbols']['RED_CIRCLE']
    
    global USER_AGENTS
    USER_AGENTS = config['user_agents']

    NTFY_TOPIC = config['alerts']['ntfy']
    
    global today_short_date
    today_short_date = datetime.now().strftime("%m%d%Y")

    logging.basicConfig(
        level = logging.INFO,  # Set the logging level (INFO, WARNING, ERROR, etc.)
        filename = LOGGING_FILE,
        format = '%(asctime)s - %(levelname)s - %(message)s'
    )
else:
    logging.error("Failed to load configuration. Exiting.")
    sys.exit(1)