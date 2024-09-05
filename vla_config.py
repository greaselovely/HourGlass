# vla_config.py

import json
import logging
import os, sys
import stat
from pathlib import Path
from datetime import datetime

CURRENT_VERSION = 1.5  # Increment this when making changes to the config structure

def ensure_config_readonly(config_path):
    """
    Ensure the config.json file is read-only for the current user.

    This function checks the permissions of the config.json file and sets it to read-only 
    (mode 600) if it isn't already. This helps protect sensitive configuration data.

    The function performs the following steps:
    1. Checks if the config file exists at the given path.
    2. If it exists, attempts to set its permissions to read-only (600).
    3. Logs the result of the operation.

    Args:
    config_path (Path): A Path object representing the location of the config.json file.

    Returns:
    bool: True if the file exists and was successfully set to read-only (or already was),
          False if the file doesn't exist or if there was a permission error.

    Side Effects:
    - Modifies the permissions of the config.json file if successful.
    - Logs info or error messages using the logging module.

    Raises:
    PermissionError: If the function lacks the necessary permissions to modify the file.
                     This error is caught and logged, and the function returns False.

    Note:
    - This function assumes the use of a Unix-like permissions system (mode 600).
    - It requires the 'logging' module to be properly configured.
    - The function will return True even if the file was already read-only.
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
    Load, create, or update configuration settings from a 'config.json' file.

    This function manages the configuration file for the application. It performs the following operations:
    1. Attempts to load an existing 'config.json' file.
    2. If the file doesn't exist, creates a new one with default settings.
    3. If the file exists but has an older version, updates it to the current version.
    4. Ensures the config file is set to read-only for security.

    The function uses several internal helper functions:
    - create_default_config(): Creates a dictionary with default configuration settings.
    - update_config(config): Updates an existing config to the current version, preserving existing values where possible.

    Global Constants:
    - CONFIG_FILE: Name of the configuration file ('config.json').
    - LOCAL_PATH: Path to the directory containing this script.
    - CONFIG_PATH: Full path to the config file.
    - CURRENT_VERSION: Current version number of the configuration structure.

    Returns:
    dict or None: A dictionary containing the configuration settings if successful.
                  None if there was an error in loading or parsing the config file.

    Side Effects:
    - May create or modify the 'config.json' file.
    - Logs information about config file updates or errors.
    - Prints messages to the console in case of file creation or errors.

    Raises:
    FileNotFoundError: Caught internally if the config file doesn't exist.
    json.JSONDecodeError: Caught internally if there's an error parsing the JSON.

    Note:
    - The function attempts to set the config file to read-only but will proceed even if this fails.
    - The configuration includes settings for proxies, authentication, file paths, URLs, and other application-specific data.
    - User agents list is included in the config for web scraping purposes.
    """
    global CURRENT_VERSION

    CONFIG_FILE = 'config.json'
    LOCAL_PATH = Path(__file__).resolve().parent
    CONFIG_PATH = Path.joinpath(LOCAL_PATH, CONFIG_FILE)
    
    def create_default_config():
        """
        Create and return a dictionary containing default configuration settings.

        This function generates a default configuration structure for the application.
        It sets up various parameters including file paths, URLs, authentication settings,
        and other application-specific data.

        The function performs the following steps:
        1. Determines the user's home directory.
        2. Creates a base path for VLA (Very Large Array) related files and folders.
        3. Constructs a dictionary with default values for all configuration settings.

        Returns:
        dict: A dictionary containing the default configuration settings. Key sections include:
            - version: Current version of the configuration structure.
            - proxies: HTTP and HTTPS proxy settings (empty by default).
            - auth: YouTube authentication credentials (empty by default).
            - alerts: Notification settings for the application.
            - sun: Default sunrise and sunset times, and related URL.
            - files_and_folders: Paths for various folders used by the application.
            - urls: URLs for image source and webpage.
            - output_symbols: Unicode symbols used for output formatting.
            - user_agents: A list of user agent strings for web requests.

        Note:
        - The function uses the global CURRENT_VERSION constant to set the configuration version.
        - File paths are constructed relative to the user's home directory.
        - Sensitive fields (like authentication credentials) are left empty by default.
        - The sun URL is set to a specific location (5481136) which may need to be adjusted for different geographical areas.
        - The user_agents list includes a variety of browser and device combinations for web scraping purposes.
        """
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
                "URL": "https://www.timeanddate.com/sun/@34.0788,-107.6166"
            },
            "files_and_folders": {
                "LOG_FILE_NAME": "time_lapse.log",
                "VALID_IMAGES_FILE": "valid_images.json",
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
        Update an existing configuration to the current version while preserving existing settings.
        """
        def recursive_update(existing, default):
            for key, value in default.items():
                if key not in existing:
                    logging.info(f"Adding new key: {key}")
                    existing[key] = value
                elif isinstance(value, dict) and isinstance(existing[key], dict):
                    recursive_update(existing[key], value)
                elif existing[key] == "" or existing[key] is None:
                    logging.info(f"Updating empty value for key: {key}")
                    existing[key] = value
                elif key == 'URL' and 'sun' in existing and 'sun' in default:
                    logging.info(f"Forcing update of sun URL from {existing[key]} to {value}")
                    existing[key] = value
            return existing

        if 'version' not in config or config['version'] < CURRENT_VERSION:
            logging.info(f"Updating config from version {config.get('version', 'unversioned')} to {CURRENT_VERSION}")
            default_config = create_default_config()
            updated_config = recursive_update(config, default_config)
            
            # Force update of sun URL
            if 'sun' in updated_config and 'URL' in updated_config['sun']:
                updated_config['sun']['URL'] = default_config['sun']['URL']
                logging.info(f"Forced update of sun URL to {updated_config['sun']['URL']}")
            
            updated_config['version'] = CURRENT_VERSION
            
            try:
                with open(CONFIG_PATH, 'w') as file:
                    json.dump(updated_config, file, indent=2)
                logging.info(f"Successfully wrote updated config to {CONFIG_PATH}")
            except Exception as e:
                logging.error(f"Failed to write updated config: {str(e)}")
            
            return updated_config
        else:
            logging.info(f"Config is already at version {CURRENT_VERSION}, no update needed")
        return config


    try:
        if not ensure_config_readonly(CONFIG_PATH):
            print("Proceeding with potentially writable config file")

        with open(CONFIG_PATH, 'r') as file:
            config = json.load(file)
        config = update_config(config)

    except FileNotFoundError:
        print(f"config.json not found at {CONFIG_PATH}; creating with default values.")
        config = create_default_config()
        with open(CONFIG_PATH, 'w') as file:
            json.dump(config, file, indent=2)
        ensure_config_readonly(CONFIG_PATH)
    
    except json.JSONDecodeError as e:
        print(f"Error decoding JSON in '{CONFIG_PATH}': {e}")
        return None
    
    return config

def update_config(new_config):
    """
    Update the configuration in config.json with new settings.

    This function updates the configuration file (config.json) with the provided new configuration.
    It handles file permissions to ensure the file is writable during the update process and
    is set back to read-only afterwards for security.

    The function performs the following steps:
    1. Identifies the location of the config.json file.
    2. Temporarily changes the file permissions to make it writable.
    3. Writes the new configuration to the file.
    4. Restores the file to read-only status.

    Args:
    new_config (dict): A dictionary containing the new configuration settings to be written to the file.

    Returns:
    bool: True if the update was successful, False if there was an error writing to the file.

    Side Effects:
    - Modifies the contents of the config.json file.
    - Temporarily changes file permissions.
    - Logs information about the update process.

    Raises:
    IOError: Caught internally if there's an error writing to the file.

    Global Constants:
    CONFIG_FILE (str): Name of the configuration file ('config.json').
    LOCAL_PATH (Path): Path to the directory containing this script.
    CONFIG_PATH (Path): Full path to the config file.

    Note:
    - This function assumes the existence of an `ensure_config_readonly()` function to set read-only permissions.
    - The function uses a 'try-except-finally' block to ensure permissions are restored even if an error occurs.
    - Logging is used to record the success or failure of the update process.
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
    VALID_IMAGES_FILE = config['files_and_folders']['VALID_IMAGES_FILE']
    
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

else:
    logging.error("Failed to load configuration. Exiting.")
    sys.exit(1)

def reload_config():
    global config, PROXIES, SUNRISE, SUNSET, SUNSET_TIME_ADD, SUN_URL, VLA_BASE, VIDEO_FOLDER, IMAGES_FOLDER
    global LOGGING_FOLDER, AUDIO_FOLDER, LOG_FILE_NAME, LOGGING_FILE, IMAGE_URL, WEBPAGE, GREEN_CIRCLE
    global RED_CIRCLE, USER_AGENTS, NTFY_TOPIC, NTFY_URL, today_short_date

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
        NTFY_URL = config['ntfy']
        
        today_short_date = datetime.now().strftime("%m%d%Y")

        logging.info("Configuration reloaded successfully")
    else:
        logging.error("Failed to reload configuration.")