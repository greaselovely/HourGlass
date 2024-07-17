# vla_config.py

import json
import logging
import os, sys
import stat
from pathlib import Path
from datetime import datetime

def ensure_config_readonly(config_path):
    """
    Checks if the config.json file is read-only for the current user,
    and sets it to read-only if it isn't.
    """
    if not config_path.exists():
        logging.error("config.json does not exist")
        return False

    try:
        config_path.chmod(0o600)
        logging.info("config.json set to 600")
    except PermissionError:
        logging.error("Failed to set config.json to read-only. Check your permissions.")
        return False

    return True

def load_config():
    """
    Loads configuration settings from a 'config.json' file, creating it if it doesn't exist,
    and updating it if a newer version is available.

    Returns:
        dict or None: A dictionary with configuration settings if successful, None otherwise.
    """
    CONFIG_FILE = 'config.json'
    LOCAL_PATH = Path(__file__).resolve().parent
    CONFIG_PATH = Path.joinpath(LOCAL_PATH, CONFIG_FILE)

    CURRENT_VERSION = 1.3  # Increment this when making changes to the config structure

    def create_default_config():
        home = Path.home()
        vla_base = os.path.join(home, "VLA")
        return {
            "version": CURRENT_VERSION,
            "proxies": {
                "http": "",
                "https": ""
            },
            "auth": {
                "youtube" : {
                    "client_id" : "",
                    "client_secret" : "",
                    "refresh_token" : ""
                }
            },
            "alerts": {
                "comment" : "This is just the topic subscription name, not the entire URL",
                "ntfy": ""
            },
            "sun": {
                "SUNRISE": "06:00:00",
                "SUNSET": "19:00:00",
                "SUNSET_TIME_ADD": 60,
                "URL": "https://www.timeanddate.com/sun/@5481136"
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
        if not ensure_config_readonly(CONFIG_PATH):
            logging.warning("Proceeding with potentially writable config file")

        with open(CONFIG_PATH, 'r') as file:
            config = json.load(file)
        return update_config(config)
    except FileNotFoundError:
        logging.warning(f"config.json not found at {CONFIG_PATH}; creating with default values.")
        default_config = create_default_config()
        with open(CONFIG_PATH, 'w') as file:
            json.dump(default_config, file, indent=2)
        ensure_config_readonly(CONFIG_PATH)
        return default_config
    except json.JSONDecodeError as e:
        logging.error(f"Error decoding JSON in '{CONFIG_PATH}': {e}")
        return None

def update_config(new_config):
    """
    Updates the configuration in config.json.
    Temporarily changes permissions to allow writing, then restores read-only.
    """
    CONFIG_FILE = 'config.json'
    LOCAL_PATH = Path(__file__).resolve().parent
    CONFIG_PATH = Path.joinpath(LOCAL_PATH, CONFIG_FILE)
    
    # Temporarily make the file writable
    current_mode = CONFIG_PATH.stat().st_mode
    writable_mode = current_mode | stat.S_IWUSR

    try:
        CONFIG_PATH.chmod(writable_mode)
        with open(CONFIG_PATH, 'w') as f:
            json.dump(new_config, f, indent=2)
        logging.info("config.json updated successfully")
    except IOError:
        logging.error("Error writing to config.json")
        return False
    finally:
        # Restore read-only permissions
        ensure_config_readonly(CONFIG_PATH)

    return True

# Load the configuration
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

def reload_config():
    global config, PROXIES, SUNRISE, SUNSET, SUNSET_TIME_ADD, SUN_URL, VLA_BASE, VIDEO_FOLDER, IMAGES_FOLDER
    global LOGGING_FOLDER, AUDIO_FOLDER, LOG_FILE_NAME, LOGGING_FILE, IMAGE_URL, WEBPAGE, GREEN_CIRCLE
    global RED_CIRCLE, USER_AGENTS, NTFY_TOPIC, today_short_date

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
        
        GREEN_CIRCLE = config['output_symbols']['GREEN_CIRCLE']
        RED_CIRCLE = config['output_symbols']['RED_CIRCLE']
        
        USER_AGENTS = config['user_agents']

        NTFY_TOPIC = config['alerts']['ntfy']
        
        today_short_date = datetime.now().strftime("%m%d%Y")

        logging.info("Configuration reloaded successfully")
    else:
        logging.error("Failed to reload configuration.")