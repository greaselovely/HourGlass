# vla_config.py

import json
import logging
import os
import stat
from pathlib import Path
from datetime import datetime

CURRENT_VERSION = 1.8  # Increment this when making changes to the config structure

def setup_logging(config):
    """
    Set up logging based on the provided configuration.

    This function sets up logging using the settings from the provided configuration dictionary.
    It performs the following operations:
    1. Extracts logging folder and file name from the config.
    2. Creates the logging directory if it doesn't exist.
    3. Configures a file handler for logging.
    4. Sets the logging level to INFO.
    5. Removes any existing handlers to avoid duplicate logging.
    6. Formats log messages with timestamp, level, and message.

    Args:
        config (dict): The configuration dictionary containing logging settings.

    Returns:
        bool: True if logging setup was successful, False otherwise.

    Side Effects:
        - Creates a directory for logs if it doesn't exist.
        - Configures the Python logging system.
        - Creates or appends to a log file.
    """
    try:
        logging_folder = config['files_and_folders']['LOGGING_FOLDER']
        log_file_name = config['files_and_folders']['LOG_FILE_NAME']
        
        os.makedirs(logging_folder, exist_ok=True)
        logging_file = os.path.join(logging_folder, log_file_name)
        
        logger = logging.getLogger()
        logger.setLevel(logging.INFO)
        
        # Remove any existing handlers to avoid duplicate logging
        for handler in logger.handlers[:]:
            logger.removeHandler(handler)
        
        file_handler = logging.FileHandler(logging_file, mode='a')
        file_handler.setLevel(logging.INFO)
        
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        file_handler.setFormatter(formatter)
        
        logger.addHandler(file_handler)

        logging.info("Logging initialized")
        return True

    except Exception as e:
        print(f"Error setting up logging: {str(e)}")
        return False

# Set up logging with default values before loading config
DEFAULT_CONFIG = {
    "files_and_folders": {
        "LOGGING_FOLDER": os.path.join(Path.home(), "VLA", "logging"),
        "LOG_FILE_NAME": "time_lapse.log"
    }
}
setup_logging(DEFAULT_CONFIG)

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
    CONFIG_FILE = 'config.json'
    LOCAL_PATH = Path(__file__).resolve().parent
    CONFIG_PATH = Path.joinpath(LOCAL_PATH, CONFIG_FILE)
    
    def create_default_config():
        """
        Create and return a dictionary containing default configuration settings.

        This function generates a default configuration structure for the application.
        It sets up various parameters including file paths, URLs, authentication settings,
        and other application-specific data.

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
        - The sun URL is set to a specific location which may need to be adjusted for different geographical areas.
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
                "comment": "This is just the topic subscription name, not the entire URL",
                "ntfy": "",
                "repeated_hash_threshold": 10,
                "escalation_points": [10, 50, 100, 500]
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
            ],
            "ntfy": "http://ntfy.sh/"
        }

    def update_config(config):
        """
        Update an existing configuration to the current version while preserving existing settings.

        This function checks if the provided configuration is up-to-date and updates it if necessary.
        It ensures that new configuration options are added while preserving existing user settings.

        The function performs the following steps:
        1. Checks if the provided config has a version and if it's less than the current version.
        2. If an update is needed:
            a. Creates a new default configuration.
            b. Recursively merges the existing configuration with the default, prioritizing existing non-blank values.
            c. Updates the version number to the current version.
            d. Writes the updated configuration back to the config file.
            e. Logs the update action.

        Args:
        config (dict): The existing configuration dictionary to be updated.

        Returns:
        dict: The updated configuration dictionary. If no update was needed, returns the original config.

        Side Effects:
        - May modify the config.json file on disk if an update is performed.
        - Logs an info message when the configuration is updated.

        Note:
        - This function uses a recursive dictionary update strategy, allowing for updates of nested structures.
        - The function assumes that `create_default_config()` and `logging` are available in the scope.
        - JSON serialization is used for writing the updated config to file, with indentation for readability.
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
            
            return updated_config
        return config

    try:
        logging.info(f"Attempting to load configuration from {CONFIG_PATH}")
        with open(CONFIG_PATH, 'r') as file:
            config = json.load(file)
        config = update_config(config)

        # Write updated config back to file
        with open(CONFIG_PATH, 'w') as file:
            json.dump(config, file, indent=2)
        logging.info("Updated configuration written to file")

    except FileNotFoundError:
        logging.warning(f"config.json not found at {CONFIG_PATH}; creating with default values.")
        config = create_default_config()
        with open(CONFIG_PATH, 'w') as file:
            json.dump(config, file, indent=2)
    
    except json.JSONDecodeError as e:
        logging.error(f"Error decoding JSON in '{CONFIG_PATH}': {e}")
        return None
    
    # Update logging configuration if needed
    if config:
        if config['files_and_folders']['LOGGING_FOLDER'] != DEFAULT_CONFIG['files_and_folders']['LOGGING_FOLDER'] or \
        config['files_and_folders']['LOG_FILE_NAME'] != DEFAULT_CONFIG['files_and_folders']['LOG_FILE_NAME']:
            setup_logging(config)
            logging.info("Logging configuration updated based on loaded config")

        return config

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
    
    GREEN_CIRCLE = config['output_symbols']['GREEN_CIRCLE']
    RED_CIRCLE = config['output_symbols']['RED_CIRCLE']
    
    USER_AGENTS = config['user_agents']

    NTFY_TOPIC = config['alerts']['ntfy']
    NTFY_URL = config['ntfy']

    
    today_short_date = datetime.now().strftime("%m%d%Y")

    logging.info("Configuration loaded successfully")
else:
    logging.error("Failed to load configuration. Exiting.")
    import sys
    sys.exit(1)

def reload_config():
    """
    Reload the configuration settings from the config file.

    This function reloads the configuration from the config file and updates all global variables.
    It's useful for refreshing the configuration during runtime without restarting the application.

    The function performs the following steps:
    1. Calls load_config() to reload the configuration from file.
    2. If successful, updates all global variables with the new configuration values.
    3. If unsuccessful, logs an error message.

    Global Variables Updated:
    - All global variables defined in the main configuration loading section.

    Returns:
    None

    Side Effects:
    - Updates global variables if successful.
    - Logs information about the reloading process.

    Note:
    - This function assumes that all global variables are already defined.
    - It uses the same load_config() function used for initial configuration loading.
    """
    global config, PROXIES, SUNRISE, SUNSET, SUNSET_TIME_ADD, SUN_URL, VLA_BASE, VIDEO_FOLDER, IMAGES_FOLDER
    global LOGGING_FOLDER, AUDIO_FOLDER, LOG_FILE_NAME, LOGGING_FILE, IMAGE_URL, WEBPAGE, GREEN_CIRCLE
    global RED_CIRCLE, USER_AGENTS, NTFY_TOPIC, NTFY_URL, today_short_date

    logging.info("Reloading configuration")
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
        logging.error("Failed to reload configuration")