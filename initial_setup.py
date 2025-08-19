#!/usr/bin/env python3
# initial_setup.py - First-run configuration wizard for HourGlass

import os
import json
import sys
from pathlib import Path
from datetime import datetime

# Check Python version
if sys.version_info.major != 3 or sys.version_info.minor != 12:
    print(f"\n⚠ Error: Python {sys.version_info.major}.{sys.version_info.minor} detected")
    print("This project requires Python 3.12 specifically")
    print("Python 3.13+ has compatibility issues with some dependencies")
    print("\nPlease install Python 3.12 and try again")
    sys.exit(1)

def get_input_with_default(prompt, default):
    """Get user input with a default value."""
    user_input = input(f"{prompt} [{default}]: ").strip()
    return user_input if user_input else default

def validate_url(url):
    """Basic URL validation."""
    return url.startswith(('http://', 'https://'))

def create_initial_config(existing_config=None):
    """Interactive setup to create initial configuration."""
    print("\n" + "="*60)
    print(" HourGlass Timelapse System - Initial Setup")
    print("="*60 + "\n")
    
    # Start with existing config or create new
    if existing_config:
        config = existing_config.copy()
        print("Updating existing configuration...\n")
    else:
        config = {
            "version": 2.0,
            "project": {},
            "capture": {},
            "video": {},
            "proxies": {},
            "auth": {},
            "alerts": {},
            "sun": {},
            "files_and_folders": {},
            "urls": {},
            "output_symbols": {},
            "user_agents": [],
            "music": {},
            "tmux": {},
            "performance": {}
        }
    
    # Project settings
    print("\n[1/8] Project Configuration")
    print("-" * 40)
    
    if existing_config and config.get("project", {}).get("name"):
        current_name = config["project"]["name"]
        project_name = input(f"Enter project name (current: {current_name}): ").strip()
        if not project_name:
            project_name = current_name
    else:
        project_name = input("Enter project name (used for filenames): ").strip()
        while not project_name:
            print("Project name is required!")
            project_name = input("Enter project name: ").strip()
    
    config["project"]["name"] = project_name
    
    current_desc = config.get("project", {}).get("description", "")
    desc_prompt = f"Project description (current: {current_desc}): " if current_desc else "Project description (optional): "
    new_desc = input(desc_prompt).strip()
    config["project"]["description"] = new_desc if new_desc else current_desc
    
    # File and folder settings
    print("\n[2/8] Storage Configuration")
    print("-" * 40)
    home = Path.home()
    default_base = os.path.join(home, "HourGlass", project_name)
    
    base_dir = get_input_with_default(
        "Base directory for project files",
        default_base
    )
    
    config["files_and_folders"]["PROJECT_BASE"] = base_dir
    config["files_and_folders"]["VIDEO_FOLDER"] = os.path.join(base_dir, "video")
    config["files_and_folders"]["IMAGES_FOLDER"] = os.path.join(base_dir, "images")
    config["files_and_folders"]["LOGGING_FOLDER"] = os.path.join(base_dir, "logging")
    config["files_and_folders"]["AUDIO_FOLDER"] = os.path.join(base_dir, "audio")
    config["files_and_folders"]["LOG_FILE_NAME"] = "timelapse.log"
    config["files_and_folders"]["VALID_IMAGES_FILE"] = "valid_images.json"
    
    # Capture settings
    print("\n[3/8] Webcam Configuration")
    print("-" * 40)
    
    # Get current IMAGE_URL if it exists
    current_image_url = config.get("urls", {}).get("IMAGE_URL", "")
    if current_image_url and current_image_url not in ["", "https://example.com/webcam.jpg"]:
        webcam_url = input(f"Webcam image URL (current: {current_image_url}): ").strip()
        if not webcam_url:
            webcam_url = current_image_url
    else:
        webcam_url = input("Webcam image URL: ").strip()
        while not validate_url(webcam_url):
            print("Please enter a valid URL (starting with http:// or https://)")
            webcam_url = input("Webcam image URL: ").strip()
    
    config["urls"]["IMAGE_URL"] = webcam_url
    
    # Get current WEBPAGE if it exists
    current_webpage = config.get("urls", {}).get("WEBPAGE", "")
    if current_webpage and current_webpage not in ["", "https://example.com"]:
        webpage_url = input(f"Webcam webpage URL (current: {current_webpage}): ").strip()
        if not webpage_url:
            webpage_url = current_webpage
    else:
        webpage_url = input("Webcam webpage URL (optional, press Enter to skip): ").strip()
    
    if webpage_url and not validate_url(webpage_url):
        webpage_url = ""
    config["urls"]["WEBPAGE"] = webpage_url or webcam_url
    
    # Capture parameters
    config["capture"]["IMAGE_PATTERN"] = f"{project_name}.*.jpg"
    config["capture"]["FILENAME_FORMAT"] = f"{project_name}.%m%d%Y.%H%M%S.jpg"
    config["capture"]["CAPTURE_INTERVAL"] = int(get_input_with_default(
        "Capture interval in seconds",
        "30"
    ))
    config["capture"]["MAX_RETRIES"] = 3
    config["capture"]["RETRY_DELAY"] = 5
    
    # Video settings
    print("\n[4/8] Video Output Configuration")
    print("-" * 40)
    
    config["video"]["FPS"] = int(get_input_with_default("Frames per second for video", "10"))
    config["video"]["OUTPUT_FORMAT"] = "mp4"
    config["video"]["CODEC"] = "libx264"
    config["video"]["VIDEO_FILENAME_FORMAT"] = f"{project_name}.%m%d%Y.mp4"
    
    # Sun/daylight settings
    print("\n[5/8] Daylight Hours Configuration")
    print("-" * 40)
    print("Configure automatic sunrise/sunset detection or set manual times.")
    print("")
    
    # Check for existing sun URL
    current_sun_url = config.get("sun", {}).get("URL", "")
    
    # Ask for sun URL first
    print("Option 1: Automatic sunrise/sunset times from timeanddate.com")
    print("Examples:")
    print("  - For New York: https://www.timeanddate.com/sun/usa/new-york")
    print("  - For London: https://www.timeanddate.com/sun/uk/london")
    print("  - For coordinates: https://www.timeanddate.com/sun/@40.7128,-74.0060")
    print("")
    
    if current_sun_url and current_sun_url != "":
        sun_url = input(f"Sun schedule URL (current: {current_sun_url}): ").strip()
        if not sun_url:
            sun_url = current_sun_url
    else:
        sun_url = input("Sun schedule URL (or press Enter to use manual times): ").strip()
    
    # Validate if provided
    if sun_url and not sun_url.startswith("http"):
        # Try to construct URL from location
        if "timeanddate.com" not in sun_url:
            # Assume it's a location like "usa/new-york" or "40.7128,-74.0060"
            sun_url = f"https://www.timeanddate.com/sun/{sun_url}"
    
    config["sun"]["URL"] = sun_url
    
    print("")
    print("Option 2: Manual times (used as fallback if URL unavailable)")
    print("Enter times in 24-hour format (HH:MM:SS)")
    
    config["sun"]["SUNRISE"] = get_input_with_default("Manual sunrise time", "06:00:00")
    config["sun"]["SUNSET"] = get_input_with_default("Manual sunset time", "19:00:00")
    config["sun"]["SUNSET_TIME_ADD"] = int(get_input_with_default(
        "Minutes to add after sunset",
        "60"
    ))
    print("")
    print("Time Zone Configuration:")
    print("This ensures images are saved to the correct day folder based on the webcam's location.")
    print("")
    print("Common timezone offsets from UTC:")
    print("  PST/PDT: -8/-7  |  MST/MDT: -7/-6  |  CST/CDT: -6/-5  |  EST/EDT: -5/-4")
    print("  London: 0/+1    |  Paris: +1/+2    |  Tokyo: +9      |  Sydney: +10/+11")
    print("")
    
    # Get server timezone
    server_tz = input("Server timezone offset from UTC (e.g., -6 for MDT, 0 for UTC): ").strip()
    try:
        server_offset = float(server_tz)
    except:
        print("Invalid input, assuming UTC (0)")
        server_offset = 0
    
    # Get webcam timezone
    webcam_tz = input("Webcam location timezone offset from UTC (e.g., 9 for Japan): ").strip()
    try:
        webcam_offset = float(webcam_tz)
    except:
        print("Invalid input, assuming same as server")
        webcam_offset = server_offset
    
    # Calculate the offset
    time_offset = int(webcam_offset - server_offset)
    
    if time_offset != 0:
        print(f"Calculated offset: {time_offset} hours")
        print(f"(Webcam is {abs(time_offset)} hours {'ahead of' if time_offset > 0 else 'behind'} server)")
    else:
        print("Server and webcam are in the same timezone")
    
    config["sun"]["TIME_OFFSET_HOURS"] = time_offset
    
    # Music/Audio settings
    print("\n[6/8] Audio Configuration (for video creation)")
    print("-" * 40)
    
    use_music = input("Add background music to videos? (y/n) [n]: ").strip().lower() == 'y'
    
    if use_music:
        config["music"]["enabled"] = True
        config["music"]["pixabay_api_key"] = input("Pixabay API key (optional): ").strip()
        # Always use 'background music' as the search term
        config["music"]["search_terms"] = ["background music"]
        config["music"]["min_duration"] = 60
        config["music"]["preferred_genres"] = ["ambient", "classical", "electronic"]
    else:
        config["music"]["enabled"] = False
        config["music"]["pixabay_api_key"] = ""
        config["music"]["search_terms"] = ["background music"]
        config["music"]["min_duration"] = 60
        config["music"]["preferred_genres"] = []
    
    # Alert settings
    print("\n[7/8] Alert Configuration (optional)")
    print("-" * 40)
    
    use_alerts = input("Enable ntfy.sh alerts? (y/n) [n]: ").strip().lower() == 'y'
    
    if use_alerts:
        config["alerts"]["enabled"] = True
        config["alerts"]["ntfy"] = input("ntfy.sh topic name: ").strip()
        config["ntfy"] = "http://ntfy.sh/"
    else:
        config["alerts"]["enabled"] = False
        config["alerts"]["ntfy"] = ""
        config["ntfy"] = "http://ntfy.sh/"
    
    config["alerts"]["repeated_hash_threshold"] = 10
    config["alerts"]["escalation_points"] = [10, 50, 100, 500]
    config["alerts"]["repeated_hash_count"] = 0
    
    # YouTube settings
    print("\n[8/8] YouTube Upload Configuration (optional)")
    print("-" * 40)
    
    use_youtube = input("Configure YouTube upload? (y/n) [n]: ").strip().lower() == 'y'
    
    if use_youtube:
        print("\nYouTube OAuth2 credentials (from Google Cloud Console):")
        config["auth"]["youtube"] = {
            "client_id": input("Client ID: ").strip(),
            "client_secret": input("Client Secret: ").strip(),
            "refresh_token": input("Refresh Token (leave empty, will be set later): ").strip(),
            "playlist_name": get_input_with_default("Default playlist name", project_name)
        }
    else:
        config["auth"]["youtube"] = {
            "client_id": "",
            "client_secret": "",
            "refresh_token": "",
            "playlist_name": project_name
        }
    
    # Proxy settings
    config["proxies"] = {
        "http": "",
        "https": ""
    }
    
    # Tmux settings
    config["tmux"] = {
        "session_name": f"hourglass-{project_name.lower()}",
        "enable_split": True,
        "log_pane_size": 20
    }
    
    # Performance settings
    config["performance"] = {
        "memory_limit_mb": 1024,
        "batch_size": 100,
        "parallel_downloads": 3,
        "cache_images": True
    }
    
    # Output symbols
    config["output_symbols"] = {
        "GREEN_CIRCLE": "\U0001F7E2",
        "RED_CIRCLE": "\U0001F534"
    }
    
    # User agents
    config["user_agents"] = [
        "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:90.0) Firefox/90.0",
        "Mozilla/5.0 (Windows NT 6.1; Win64; x64; rv:88.0) Firefox/88.0",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:92.0) Firefox/92.0",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:96.0) Firefox/96.0",
        "Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.0 Mobile/15E148 Safari/604.1",
        "Mozilla/5.0 (Android 11; Mobile; rv:100.0) Firefox/100.0",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/94.0.4606.81 Safari/537.36 Edg/94.0.992.50",
        "Mozilla/5.0 (Linux; Android 12; Pixel 6) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/94.0.4606.81 Mobile Safari/537.36"
    ]
    
    return config

def save_config(config, filepath="config.json"):
    """Save configuration to file."""
    try:
        with open(filepath, 'w') as f:
            json.dump(config, f, indent=2)
        print(f"\n✓ Configuration saved to {filepath}")
        return True
    except Exception as e:
        print(f"\n✗ Error saving configuration: {e}")
        return False

def create_directories(config):
    """Create necessary directories."""
    dirs_to_create = [
        config["files_and_folders"]["PROJECT_BASE"],
        config["files_and_folders"]["VIDEO_FOLDER"],
        config["files_and_folders"]["IMAGES_FOLDER"],
        config["files_and_folders"]["LOGGING_FOLDER"],
        config["files_and_folders"]["AUDIO_FOLDER"]
    ]
    
    print("\nCreating directories...")
    for directory in dirs_to_create:
        try:
            os.makedirs(directory, exist_ok=True)
            print(f"  ✓ {directory}")
        except Exception as e:
            print(f"  ✗ Failed to create {directory}: {e}")
            return False
    
    return True

def main():
    """Main setup function."""
    # Check if config already exists
    update_mode = False
    existing_config = None
    if os.path.exists("config.json"):
        print("\n⚠ config.json already exists!")
        print("Would you like to:")
        print("  1. Update missing/empty fields only")
        print("  2. Overwrite completely")
        print("  3. Cancel")
        choice = input("Enter your choice (1/2/3) [1]: ").strip() or "1"
        
        if choice == "3":
            print("Setup cancelled.")
            sys.exit(0)
        elif choice == "1":
            update_mode = True
            # Load existing config
            try:
                with open("config.json", "r") as f:
                    existing_config = json.load(f)
            except:
                print("Error reading existing config. Starting fresh.")
                update_mode = False
        elif choice != "2":
            print("Invalid choice. Defaulting to update mode.")
            update_mode = True
    
    # Run interactive setup
    config = create_initial_config(existing_config if update_mode else None)
    
    # Save configuration
    if not save_config(config):
        sys.exit(1)
    
    # Create directories
    if not create_directories(config):
        print("\n⚠ Some directories could not be created, but configuration was saved.")
    
    print("\n" + "="*60)
    print(" Setup Complete!")
    print("="*60)
    print(f"\nProject '{config['project']['name']}' has been configured.")
    print("\nNext steps:")
    print("  1. Run ./setup.sh to install dependencies")
    print("  2. Test with: python main.py")
    print("  3. For continuous capture: ./hourglass.sh")
    
    # Calculate cron scheduling times
    time_offset = config.get('sun', {}).get('TIME_OFFSET_HOURS', 0)
    sunrise_time = config.get('sun', {}).get('SUNRISE', '06:00:00')
    sunset_time = config.get('sun', {}).get('SUNSET', '19:00:00')
    
    # Parse sunrise hour
    try:
        sunrise_hour = int(sunrise_time.split(':')[0])
        sunset_hour = int(sunset_time.split(':')[0])
        
        # Calculate server time for webcam's sunrise
        server_sunrise_hour = (sunrise_hour - time_offset) % 24
        server_sunset_hour = (sunset_hour - time_offset + 1) % 24  # +1 for after sunset
        
        print("\nScheduling with cron:")
        print("  IMPORTANT: Cron uses YOUR SERVER'S local time.")
        
        if time_offset != 0:
            print(f"\n  Your configuration:")
            print(f"  - Webcam sunrise: {sunrise_time} (webcam local time)")
            print(f"  - Server should start at: {server_sunrise_hour:02d}:00 (server local time)")
            print(f"  - Server should stop at: {server_sunset_hour:02d}:00 (server local time)")
            
            print(f"\n  Suggested cron entries:")
            print(f"  # Start capturing at webcam's sunrise")
            print(f"  0 {server_sunrise_hour} * * * cd /path/to/HourGlass && ./hourglass.sh")
            print(f"  # Stop capturing after webcam's sunset")
            print(f"  0 {server_sunset_hour} * * * pkill -f 'python main.py'")
            
            if server_sunrise_hour > sunrise_hour:
                print("\n  Note: Due to timezone difference, this starts the previous day on your server!")
        else:
            print(f"\n  Server and webcam are in the same timezone.")
            print(f"  Suggested cron entries:")
            print(f"  # Start at sunrise ({sunrise_time})")
            print(f"  0 {sunrise_hour} * * * cd /path/to/HourGlass && ./hourglass.sh")
            print(f"  # Stop after sunset")
            print(f"  0 {sunset_hour + 1} * * * pkill -f 'python main.py'")
            
    except:
        print("\nScheduling with cron:")
        print("  Schedule based on YOUR SERVER'S local time.")
        print("  Example: 0 6 * * * cd /path/to/HourGlass && ./hourglass.sh")
    
    print("\nYou can edit config.json manually to fine-tune settings.")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nSetup interrupted by user. Exiting gracefully.")
        sys.exit(1)
    except Exception as e:
        print(f"\nUnexpected error during setup: {e}")
        sys.exit(1)