# timelapse_config.py

import os
import sys
import glob
import json
import logging
import logging.handlers
from pathlib import Path
from datetime import datetime, timedelta

CURRENT_VERSION = 2.1  # HourGlass version with TTS intro support

def setup_logging(config):
    """
    Set up logging with rotation based on the provided configuration.

    This function sets up logging using the settings from the provided configuration dictionary.
    It now includes log rotation to prevent huge log files and automatic cleanup of old logs.
    
    Features:
    - Rotates log files when they reach 50MB
    - Keeps 14 backup files (roughly 2 weeks of logs)
    - Automatically cleans up logs older than 14 days
    
    Args:
        config (dict): The configuration dictionary containing logging settings.

    Returns:
        bool: True if logging setup was successful, False otherwise.
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
        
        # Use RotatingFileHandler instead of regular FileHandler
        file_handler = logging.handlers.RotatingFileHandler(
            filename=logging_file,
            maxBytes=50*1024*1024,  # 50MB per file
            backupCount=14,         # Keep 14 backup files
            encoding='utf-8'
        )
        file_handler.setLevel(logging.INFO)
        
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        file_handler.setFormatter(formatter)
        
        logger.addHandler(file_handler)

        # Clean up old log files as backup safety measure
        _cleanup_old_logs(logging_folder, days_to_keep=14)

        logging.info("Logging initialized with rotation")
        return True

    except Exception as e:
        print(f"Error setting up logging: {str(e)}")
        return False

def _cleanup_old_logs(log_directory, days_to_keep=14):
    """
    Helper function to clean up log files older than specified days.
    This is a backup cleanup in case the rotating handler misses anything.
    """
    try:
        cutoff_date = datetime.now() - timedelta(days=days_to_keep)
        
        for log_file in glob.glob(os.path.join(log_directory, "*.log*")):
            try:
                file_time = datetime.fromtimestamp(os.path.getmtime(log_file))
                if file_time < cutoff_date:
                    os.remove(log_file)
            except (OSError, IOError):
                pass  # Silently ignore cleanup errors
    except Exception:
        pass  # Don't let cleanup errors break logging setup

# Set up logging with default values before loading config
DEFAULT_CONFIG = {
    "files_and_folders": {
        "LOGGING_FOLDER": os.path.join(Path.home(), "HourGlass", "logging"),
        "LOG_FILE_NAME": "timelapse.log"
    }
}
setup_logging(DEFAULT_CONFIG)

def load_config(config_path=None):
    """
    Load, create, or update configuration settings from a config file.

    This function manages the configuration file for the application. It performs the following operations:
    1. Attempts to load an existing config file.
    2. If the file doesn't exist, returns None (configs should be created via timelapse_setup.py).
    3. If the file exists but has an older version, updates it to the current version.

    Parameters:
    config_path (str, optional): Path to the configuration file. Must be provided.

    The function uses several internal helper functions:
    - create_default_config(): Creates a dictionary with default configuration settings.
    - update_config(config): Updates an existing config to the current version, preserving existing values where possible.

    Returns:
    dict or None: A dictionary containing the configuration settings if successful.
                  None if there was an error in loading or parsing the config file.

    Side Effects:
    - May modify the config file if updating to a new version.
    - Logs information about config file updates or errors.

    Raises:
    FileNotFoundError: Caught internally if the config file doesn't exist.
    json.JSONDecodeError: Caught internally if there's an error parsing the JSON.

    Note:
    - The configuration includes settings for proxies, authentication, file paths, URLs, and other application-specific data.
    - User agents list is included in the config for web scraping purposes.
    """
    if not config_path:
        logging.error("No config path provided to load_config")
        return None

    CONFIG_PATH = Path(config_path)

    def normalize_paths(config):
        """
        Normalize paths in config to use ~ for home directory.
        This makes configs portable across different systems and users.

        - Detects hardcoded home paths like /home/user or /Users/user
        - Replaces them with ~ in the stored config
        - Expands ~ to current user's home when returning config
        """
        import re

        current_home = str(Path.home())

        # Pattern to match common home directory formats
        # Matches /home/username, /Users/username, C:\Users\username
        home_pattern = re.compile(r'^(/home/[^/]+|/Users/[^/]+|[A-Z]:\\Users\\[^\\]+)')

        def replace_home_with_tilde(path_str):
            """Replace any home directory path with ~"""
            if not path_str or not isinstance(path_str, str):
                return path_str

            # Check if it starts with current home
            if path_str.startswith(current_home):
                return path_str.replace(current_home, '~', 1)

            # Check for other home patterns (from different systems)
            match = home_pattern.match(path_str)
            if match:
                return path_str.replace(match.group(1), '~', 1)

            return path_str

        def expand_tilde(path_str):
            """Expand ~ to current user's home directory"""
            if not path_str or not isinstance(path_str, str):
                return path_str
            return os.path.expanduser(path_str)

        # Normalize paths in files_and_folders section
        if 'files_and_folders' in config:
            for key, value in config['files_and_folders'].items():
                if isinstance(value, str) and ('/' in value or '\\' in value):
                    # First normalize to use ~
                    normalized = replace_home_with_tilde(value)
                    config['files_and_folders'][key] = normalized

        return config

    def cleanup_deprecated_fields(config):
        """
        Remove deprecated fields from config that are no longer used.
        This keeps config files clean and removes obsolete settings.
        """
        # Remove preferred_genres from music section (unused feature)
        if 'music' in config and 'preferred_genres' in config['music']:
            del config['music']['preferred_genres']
            logging.info("Removed deprecated 'preferred_genres' from config")

        return config

    def expand_config_paths(config):
        """
        Expand ~ to actual home directory for use in the application.
        This is called after loading and normalizing, before returning config.
        """
        if 'files_and_folders' in config:
            for key, value in config['files_and_folders'].items():
                if isinstance(value, str):
                    config['files_and_folders'][key] = os.path.expanduser(value)

        return config
    
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
        # Return minimal default config - full config should be created via initial_setup.py
        home = Path.home()
        project_base = os.path.join(home, "HourGlass", "default")
        return {
            "version": CURRENT_VERSION,
            "project": {
                "name": "default",
                "description": "Default HourGlass project"
            },
            "capture": {
                "IMAGE_PATTERN": "default.*.jpg",
                "FILENAME_FORMAT": "default.%m%d%Y.%H%M%S.jpg",
                "CAPTURE_INTERVAL": 30,
                "MAX_RETRIES": 3,
                "RETRY_DELAY": 5
            },
            "video": {
                "FPS": 10,
                "OUTPUT_FORMAT": "mp4",
                "CODEC": "libx264",
                "VIDEO_FILENAME_FORMAT": "default.%m%d%Y.mp4"
            },
            "proxies": {
                "http": "",
                "https": ""
            },
            "auth": {
                "youtube": {
                    "client_id": "",
                    "client_secret": "",
                    "refresh_token": "",
                    "playlist_name": "default"
                }
            },
            "alerts": {
                "enabled": False,
                "ntfy": "",
                "repeated_hash_threshold": 10,
                "escalation_points": [10, 50, 100, 500],
                "repeated_hash_count": 0
            },
            "sun": {
                "SUNRISE": "06:00:00",
                "SUNSET": "19:00:00",
                "SUNSET_TIME_ADD": 60,
                "TIME_OFFSET_HOURS": 0,
                "URL": ""
            },
            "files_and_folders": {
                "LOG_FILE_NAME": "timelapse.log",
                "VALID_IMAGES_FILE": "valid_images.json",
                "PROJECT_BASE": str(project_base),
                "VIDEO_FOLDER": os.path.join(project_base, "video"),
                "IMAGES_FOLDER": os.path.join(project_base, "images"),
                "LOGGING_FOLDER": os.path.join(project_base, "logging"),
                "AUDIO_FOLDER": os.path.join(project_base, "audio"),
                "AUDIO_CACHE_FOLDER": os.path.join(project_base, "audio_cache")
            },
            "urls": {
                "IMAGE_URL": "",
                "WEBPAGE": ""
            },
            "music": {
                "enabled": False,
                "pixabay_api_key": "",
                "pixabay_base_url": "https://pixabay.com/music/search/",
                "search_terms": ["no copyright music"],
                "min_duration": 60,
                "cache_max_files": 50,
                "tts_intro": {
                    "enabled": False,
                    "voice_gender": "female",
                    "rate": 150,
                    "volume": 0.9
                }
            },
            "tmux": {
                "session_name": "hourglass-default",
                "enable_split": True,
                "log_pane_size": 20
            },
            "performance": {
                "memory_limit_mb": 1024,
                "batch_size": 100,
                "parallel_downloads": 3,
                "cache_images": True
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
            return existing

        if 'version' not in config or config['version'] < CURRENT_VERSION:
            logging.info(f"Updating config from version {config.get('version', 'unversioned')} to {CURRENT_VERSION}")
            default_config = create_default_config()
            updated_config = recursive_update(config, default_config)
            updated_config['version'] = CURRENT_VERSION
            
            return updated_config
        return config

    try:
        logging.info(f"Attempting to load configuration from {CONFIG_PATH}")
        with open(CONFIG_PATH, 'r') as file:
            config = json.load(file)

        # Normalize paths to use ~ (for portability)
        config = normalize_paths(config)

        # Clean up deprecated fields
        config = cleanup_deprecated_fields(config)

        config = update_config(config)

        # Write updated config back to file (with ~ paths for portability)
        with open(CONFIG_PATH, 'w') as file:
            json.dump(config, file, indent=2)
        logging.info("Updated configuration written to file")

        # Expand ~ to actual home directory for use in the application
        config = expand_config_paths(config)

    except FileNotFoundError:
        logging.warning(f"Configuration file not found at {CONFIG_PATH}")
        return None

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

# Don't load any configuration on module import
# Configuration will be loaded by main.py with specific project path
# Set placeholder values that will be overwritten when config is loaded

# Project settings
PROJECT_NAME = 'default'
PROJECT_DESCRIPTION = ''

# Capture settings
IMAGE_PATTERN = 'default.*.jpg'
FILENAME_FORMAT = 'default.%m%d%Y.%H%M%S.jpg'
CAPTURE_INTERVAL = 30
MAX_RETRIES = 3
RETRY_DELAY = 5

# Video settings
VIDEO_FPS = 10
VIDEO_FORMAT = 'mp4'
VIDEO_CODEC = 'libx264'
VIDEO_FILENAME_FORMAT = 'default.%m%d%Y.mp4'

# Network settings
PROXIES = {}

# Sun/time settings
SUNRISE = '06:00:00'
SUNSET = '19:00:00'
SUNSET_TIME_ADD = 60
SUN_URL = ''
TIME_OFFSET_HOURS = 0

# File and folder settings
PROJECT_BASE = os.path.join(Path.home(), 'HourGlass', 'default')
VIDEO_FOLDER = os.path.join(PROJECT_BASE, 'video')
IMAGES_FOLDER = os.path.join(PROJECT_BASE, 'images')
VALID_IMAGES_FILE = 'valid_images.json'
LOGGING_FOLDER = os.path.join(PROJECT_BASE, 'logging')
AUDIO_FOLDER = os.path.join(PROJECT_BASE, 'audio')
AUDIO_CACHE_FOLDER = os.path.join(PROJECT_BASE, 'audio_cache')
LOG_FILE_NAME = 'timelapse.log'
LOGGING_FILE = os.path.join(LOGGING_FOLDER, LOG_FILE_NAME)

# URL settings
IMAGE_URL = ''
WEBPAGE = ''

# Output symbols
GREEN_CIRCLE = '\U0001F7E2'
RED_CIRCLE = '\U0001F534'

# User agents
USER_AGENTS = []

# Alert settings
ALERTS_ENABLED = False
NTFY_TOPIC = ''
NTFY_URL = 'http://ntfy.sh/'

# Music settings
MUSIC_ENABLED = False
PIXABAY_API_KEY = ''
PIXABAY_BASE_URL = 'https://pixabay.com/music/search/'
MUSIC_SEARCH_TERMS = ['no copyright music']
MUSIC_MIN_DURATION = 60
AUDIO_CACHE_MAX_FILES = 50

# TTS Intro settings
TTS_INTRO_ENABLED = True
TTS_INTRO_VOICE_GENDER = 'female'
TTS_INTRO_RATE = 150
TTS_INTRO_VOLUME = 0.9

# YouTube settings
YOUTUBE_CLIENT_ID = ''
YOUTUBE_CLIENT_SECRET = ''
YOUTUBE_REFRESH_TOKEN = ''
YOUTUBE_PLAYLIST_NAME = PROJECT_NAME

# Tmux settings
TMUX_SESSION_NAME = f'hourglass-{PROJECT_NAME.lower()}'
TMUX_ENABLE_SPLIT = True
TMUX_LOG_PANE_SIZE = 20

# Performance settings
MEMORY_LIMIT_MB = 1024
BATCH_SIZE = 100
PARALLEL_DOWNLOADS = 3
CACHE_IMAGES = True

today_short_date = datetime.now().strftime("%m%d%Y")

