# timelapse_setup.py - Configuration wizard for HourGlass projects

import os
import json
import sys
import glob
from pathlib import Path
from datetime import datetime

# Check Python version
if sys.version_info.major != 3 or sys.version_info.minor != 12:
    print(f"\nError: Python {sys.version_info.major}.{sys.version_info.minor} detected")
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

def list_existing_projects():
    """List all existing project configurations."""
    configs_dir = Path("configs")
    if not configs_dir.exists():
        return []
    
    config_files = list(configs_dir.glob("*.json"))
    projects = []
    for config_file in config_files:
        project_name = config_file.stem
        projects.append(project_name)
    return sorted(projects)

def create_initial_config(existing_config=None, project_name=None):
    """Interactive setup to create initial configuration."""
    print("\n" + "="*60)
    print(f" HourGlass Timelapse System - {'Update' if existing_config else 'New'} Project Setup")
    if project_name:
        print(f" Project: {project_name}")
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
    
    # If project_name was passed as parameter, use it directly
    if project_name:
        print(f"Project name: {project_name}")
        config["project"]["name"] = project_name
    elif existing_config and config.get("project", {}).get("name"):
        current_name = config["project"]["name"]
        new_name = input(f"Enter project name (current: {current_name}): ").strip()
        project_name = new_name if new_name else current_name
        config["project"]["name"] = project_name
    else:
        project_name = input("Enter project name (used for filenames): ").strip()
        while not project_name:
            print("Project name is required!")
            project_name = input("Enter project name: ").strip()
        config["project"]["name"] = project_name
    
    current_desc = config.get("project", {}).get("description", "")
    if current_desc:
        desc_prompt = f"Project description (current: {current_desc}): "
        new_desc = input(desc_prompt).strip()
        config["project"]["description"] = new_desc if new_desc else current_desc
    else:
        desc_prompt = "Project description (required, used for TTS intro): "
        new_desc = input(desc_prompt).strip()
        while not new_desc:
            print("Project description is required for TTS intro!")
            new_desc = input("Enter project description: ").strip()
        config["project"]["description"] = new_desc
    
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
        print("Enter the direct URL to the webcam image or stream")
        print("Examples:")
        print("  - Static image: https://example.com/webcam.jpg")
        print("  - MJPEG stream: http://192.168.1.100:8080/video.mjpg")
        webcam_url = input("Webcam image URL: ").strip()
        while not validate_url(webcam_url):
            print("Please enter a valid URL (starting with http:// or https://)")
            webcam_url = input("Webcam image URL: ").strip()
    
    config["urls"]["IMAGE_URL"] = webcam_url
    
    # Get current WEBPAGE if it exists
    current_webpage = config.get("urls", {}).get("WEBPAGE", "")
    
    # Check if IMAGE_URL is a direct image/stream
    image_extensions = ('.jpg', '.jpeg', '.png', '.gif', '.bmp', '.mjpg', '.mjpeg', 'video.mjpg', 'video.mjpeg')
    is_direct_image = any(webcam_url.lower().endswith(ext) or ext in webcam_url.lower() for ext in image_extensions)
    
    if is_direct_image:
        print("\nDirect image/stream detected.")
        print("For direct streams, the webpage URL is optional.")
        if current_webpage and current_webpage not in ["", "https://example.com", webcam_url]:
            webpage_url = input(f"Webcam webpage URL (current: {current_webpage}, Enter to use image URL): ").strip()
            if not webpage_url:
                webpage_url = webcam_url
        else:
            webpage_url = input("Webcam webpage URL (press Enter to use image URL): ").strip()
    else:
        print("\nWebcam webpage URL (the page containing the webcam)")
        print("This helps with session management for protected webcams.")
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
    
    use_music = input("Add no copyright music to videos? (y/n) [n]: ").strip().lower() == 'y'

    if use_music:
        config["music"]["enabled"] = True
        config["music"]["pixabay_base_url"] = "https://pixabay.com/music/search/"
        config["music"]["pixabay_api_key"] = input("Pixabay API key (optional): ").strip()
        # Always use 'no copyright music' as the search term
        config["music"]["search_terms"] = ["no copyright music"]
        config["music"]["min_duration"] = 60
    else:
        config["music"]["enabled"] = False
        config["music"]["pixabay_base_url"] = "https://pixabay.com/music/search/"
        config["music"]["pixabay_api_key"] = ""
        config["music"]["search_terms"] = ["no copyright music"]
        config["music"]["min_duration"] = 60
    
    # Proxy settings
    print("\n[7/8] Proxy Configuration (optional)")
    print("-" * 40)
    print("Configure proxy settings for network requests")
    
    use_proxy = input("Do you need to use a proxy? (y/n) [n]: ").strip().lower() == 'y'
    
    if use_proxy:
        print("\nProxy types:")
        print("1. SOCKS5 proxy")
        print("2. HTTP/HTTPS proxy")
        print("3. Both")
        
        proxy_choice = input("Select proxy type (1-3) [1]: ").strip() or "1"
        
        if proxy_choice in ["1", "3"]:
            print("\nSOCKS5 Proxy Configuration:")
            print("Format: hostname:port or IP:port")
            print("Example: proxy.example.com:1080 or 192.168.1.10:1080")
            
            socks_input = input("SOCKS5 proxy (leave empty to skip): ").strip()
            if socks_input:
                # Check if hostname resolution through proxy is needed
                use_hostname_resolution = input("Resolve DNS through proxy? (y/n) [y]: ").strip().lower() != 'n'
                
                if use_hostname_resolution:
                    config["proxies"]["socks5_hostname"] = socks_input
                    config["proxies"]["socks5"] = ""
                else:
                    config["proxies"]["socks5"] = socks_input
                    config["proxies"]["socks5_hostname"] = ""
        
        if proxy_choice in ["2", "3"]:
            print("\nHTTP/HTTPS Proxy Configuration:")
            print("Format: http://hostname:port or http://username:password@hostname:port")
            
            http_proxy = input("HTTP proxy (leave empty to skip): ").strip()
            config["proxies"]["http"] = http_proxy
            
            https_proxy = input("HTTPS proxy (leave empty to use same as HTTP): ").strip()
            config["proxies"]["https"] = https_proxy if https_proxy else http_proxy
    else:
        # Keep default empty proxy settings
        config["proxies"] = {
            "http": "",
            "https": "",
            "socks5": "",
            "socks5_hostname": ""
        }
    
    # Alert settings
    print("\n[8/8] Alert Configuration (optional)")
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
    print("\n[9/9] YouTube Upload Configuration (optional)")
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

def save_config(config, project_name=None):
    """Save configuration to file."""
    # Ensure configs directory exists
    configs_dir = Path("configs")
    configs_dir.mkdir(exist_ok=True)
    
    # Determine filepath - always use configs directory
    if not project_name:
        print("Error: Project name is required")
        return False
    filepath = configs_dir / f"{project_name}.json"
    
    try:
        with open(filepath, 'w') as f:
            json.dump(config, f, indent=2)
        print(f"\nConfiguration saved to {filepath}")
        return True
    except Exception as e:
        print(f"\nError saving configuration: {e}")
        return False

def create_instructions_file(config, project_name=None):
    """Create instructions.txt with setup information and cron scheduling."""
    try:
        config_project_name = config.get('project', {}).get('name', 'HourGlass')
        # Use the project_name parameter if provided, otherwise fall back to config
        actual_project_name = project_name or config_project_name
        time_offset = config.get('sun', {}).get('TIME_OFFSET_HOURS', 0)
        sunrise_time = config.get('sun', {}).get('SUNRISE', '06:00:00')
        sunset_time = config.get('sun', {}).get('SUNSET', '19:00:00')
        base_dir = config.get('files_and_folders', {}).get('PROJECT_BASE', '/path/to/HourGlass')
        
        instructions = []
        instructions.append("=" * 60)
        instructions.append(f" HourGlass Project: {actual_project_name}")
        instructions.append("=" * 60)
        instructions.append(f"\nSetup completed on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        instructions.append(f"Base directory: {base_dir}")
        
        instructions.append("\n" + "=" * 60)
        instructions.append(" NEXT STEPS")
        instructions.append("=" * 60)
        instructions.append("\n1. Install dependencies (if not already done):")
        instructions.append("   ./setup.sh")
        instructions.append("\n2. Test the capture script:")
        if project_name:
            instructions.append(f"   python main.py {project_name}")
        else:
            instructions.append("   python main.py")
        instructions.append("\n3. For continuous capture in tmux:")
        if project_name:
            instructions.append(f"   ./hourglass.sh {project_name}")
        else:
            instructions.append("   ./hourglass.sh")
        
        instructions.append("\n" + "=" * 60)
        instructions.append(" CRON SCHEDULING")
        instructions.append("=" * 60)
        instructions.append("\nIMPORTANT: Cron uses YOUR SERVER'S local time.")
        
        # Get HourGlass directory (current working directory)
        hourglass_dir = os.getcwd()
        
        try:
            sunrise_hour = int(sunrise_time.split(':')[0])
            sunset_hour = int(sunset_time.split(':')[0])
            
            # Calculate server time for webcam's sunrise
            server_sunrise_hour = (sunrise_hour - time_offset) % 24
            server_sunset_hour = (sunset_hour - time_offset + 1) % 24  # +1 for after sunset
            
            if time_offset != 0:
                instructions.append(f"\nYour configuration:")
                instructions.append(f"  - Webcam sunrise: {sunrise_time} (webcam local time)")
                instructions.append(f"  - Webcam sunset: {sunset_time} (webcam local time)")
                instructions.append(f"  - Timezone offset: {time_offset} hours")
                instructions.append(f"\nServer times (for cron):")
                instructions.append(f"  - Start capturing at: {server_sunrise_hour:02d}:00 (server local time)")
                instructions.append(f"  - Stop capturing at: {server_sunset_hour:02d}:00 (server local time)")
                
                instructions.append(f"\nAdd these lines to your crontab (crontab -e):")
                instructions.append(f"\n# Start HourGlass capture at webcam's sunrise")
                if project_name:
                    instructions.append(f"0 {server_sunrise_hour} * * * cd {hourglass_dir} && ./hourglass.sh {project_name}")
                else:
                    instructions.append(f"0 {server_sunrise_hour} * * * cd {hourglass_dir} && ./hourglass.sh")
                instructions.append(f"\n# Stop HourGlass capture after webcam's sunset")
                instructions.append(f"0 {server_sunset_hour} * * * pkill -f 'python main.py'")
                
                if server_sunrise_hour > sunrise_hour:
                    instructions.append(f"\nNote: Due to timezone difference, capture starts the")
                    instructions.append(f"      previous day on your server!")
            else:
                instructions.append(f"\nServer and webcam are in the same timezone.")
                instructions.append(f"  - Webcam sunrise: {sunrise_time}")
                instructions.append(f"  - Webcam sunset: {sunset_time}")
                
                instructions.append(f"\nAdd these lines to your crontab (crontab -e):")
                instructions.append(f"\n# Start HourGlass capture at sunrise")
                if project_name:
                    instructions.append(f"0 {sunrise_hour} * * * cd {hourglass_dir} && ./hourglass.sh {project_name}")
                else:
                    instructions.append(f"0 {sunrise_hour} * * * cd {hourglass_dir} && ./hourglass.sh")
                instructions.append(f"\n# Stop HourGlass capture after sunset")
                instructions.append(f"0 {sunset_hour + 1} * * * pkill -f 'python main.py'")
        except:
            instructions.append("\nManual scheduling:")
            instructions.append("Schedule based on YOUR SERVER'S local time.")
            instructions.append(f"\nExample crontab entries:")
            instructions.append(f"# Start at 6 AM")
            if project_name:
                instructions.append(f"0 6 * * * cd {hourglass_dir} && ./hourglass.sh {project_name}")
            else:
                instructions.append(f"0 6 * * * cd {hourglass_dir} && ./hourglass.sh")
            instructions.append(f"# Stop at 8 PM")
            instructions.append(f"0 20 * * * pkill -f 'python main.py'")
        
        instructions.append("\n" + "=" * 60)
        instructions.append(" MANUAL COMMANDS")
        instructions.append("=" * 60)
        instructions.append("\nStart capture manually:")
        instructions.append(f"  cd {hourglass_dir}")
        if project_name:
            instructions.append(f"  ./hourglass.sh {project_name}")
        else:
            instructions.append("  ./hourglass.sh")
        instructions.append("\nStop capture:")
        instructions.append("  pkill -f 'python main.py'")
        instructions.append("\nView logs:")
        instructions.append("  tmux attach -t hourglass-" + config_project_name.lower())
        instructions.append("\nCreate daily video:")
        if project_name:
            instructions.append(f"  python main.py {project_name} --video-only")
        else:
            instructions.append("  python main.py --video-only")
        
        instructions.append("\n" + "=" * 60)
        instructions.append(" CONFIGURATION")
        instructions.append("=" * 60)
        instructions.append(f"\nConfiguration file: configs/{project_name}.json" if project_name else "\nConfiguration file: configs/<project>.json")
        instructions.append("You can edit the configuration file manually to fine-tune settings.")
        instructions.append("\nTo re-run setup:")
        instructions.append("  python timelapse_setup.py")
        
        # Write to file with project-specific name in instructions folder
        os.makedirs("instructions", exist_ok=True)
        if project_name:
            instructions_file = os.path.join("instructions", f"{project_name}_instructions.txt")
        else:
            instructions_file = os.path.join("instructions", "instructions.txt")
            
        with open(instructions_file, 'w') as f:
            f.write('\n'.join(instructions))
        
        print(f"\nInstructions saved to {instructions_file}")
        return True
        
    except Exception as e:
        print(f"\nWarning: Could not create instructions.txt: {e}")
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
            print(f"  {directory}")
        except Exception as e:
            print(f"  Failed to create {directory}: {e}")
            return False
    
    return True

def main(preset_project_name=None):
    """Main setup function.
    
    Args:
        preset_project_name: Optional project name to create directly without prompting
    """
    print("\n" + "="*60)
    print(" HourGlass Timelapse Configuration")
    print("="*60)
    
    # List existing projects
    existing_projects = list_existing_projects()
    
    # If preset_project_name is provided, create that project directly
    if preset_project_name:
        if preset_project_name in existing_projects:
            print(f"\nUpdating existing project: {preset_project_name}")
            project_name = preset_project_name
            update_mode = True
        else:
            print(f"\nCreating new project: {preset_project_name}")
            project_name = preset_project_name
            update_mode = False
    # Otherwise, show menu
    elif existing_projects:
        print("\nExisting projects found:")
        for i, proj in enumerate(existing_projects, 1):
            print(f"  {i}. {proj}")
        
        print(f"\n  {len(existing_projects)+1}. Create new project")
        
        choice = input(f"\nSelect option (1-{len(existing_projects)+1}): ").strip()
        
        try:
            choice_idx = int(choice) - 1
            if choice_idx < len(existing_projects):
                # Update existing project
                project_name = existing_projects[choice_idx]
                update_mode = True
            elif choice_idx == len(existing_projects):
                # Create new project
                project_name = input("\nEnter new project name: ").strip()
                while not project_name or ' ' in project_name:
                    print("Project name must not be empty and cannot contain spaces")
                    project_name = input("Enter new project name: ").strip()
                update_mode = False
            else:
                print("Invalid choice. Exiting.")
                sys.exit(1)
        except (ValueError, IndexError):
            print("Invalid choice. Exiting.")
            sys.exit(1)
    else:
        # No existing projects - ask for project name
        print("\nNo existing projects found.")
        choice = input("Create new project? (y/n) [y]: ").strip().lower() or 'y'
        if choice != 'y':
            print("Setup cancelled.")
            sys.exit(0)
        
        project_name = input("\nEnter project name: ").strip()
        while not project_name or ' ' in project_name:
            print("Project name must not be empty and cannot contain spaces")
            project_name = input("Enter project name: ").strip()
        update_mode = False
    
    # Load existing config if updating
    existing_config = None
    if update_mode:
        if not project_name:
            print("Error: Project name is required")
            sys.exit(1)
        config_path = Path("configs") / f"{project_name}.json"
        if config_path.exists():
            try:
                with open(config_path, "r") as f:
                    existing_config = json.load(f)
                print(f"\nLoaded existing configuration for {project_name or 'default'}")
            except Exception as e:
                print(f"Error reading existing config: {e}")
                print("Starting fresh configuration.")
                update_mode = False
    
    # Run interactive setup
    config = create_initial_config(existing_config if update_mode else None, project_name)
    
    # Save configuration
    if not save_config(config, project_name):
        sys.exit(1)
    
    # Create directories
    if not create_directories(config):
        print("\nSome directories could not be created, but configuration was saved.")
    
    # Create instructions file with all the setup information
    create_instructions_file(config, project_name)
    
    print("\n" + "="*60)
    print(" Setup Complete!")
    print("="*60)
    print(f"\nProject '{project_name or config['project']['name']}' has been configured.")
    
    instructions_file = os.path.join("instructions", f"{project_name}_instructions.txt") if project_name else os.path.join("instructions", "instructions.txt")
    print(f"\nIMPORTANT: Refer to '{instructions_file}' for:")
    print("   - Next steps and quick start guide")
    print("   - Complete cron scheduling examples")
    print("   - Manual commands reference")
    print("   - Configuration details")
    print("\nQuick start:")
    print("  1. Run ./setup.sh to install dependencies")
    if project_name:
        print(f"  2. Test with: python main.py {project_name}")
        print(f"  3. See {instructions_file} for cron setup")
    else:
        print("  2. Test with: python main.py")
        print(f"  3. See {instructions_file} for cron setup")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nSetup interrupted by user. Exiting gracefully.")
        sys.exit(1)
    except Exception as e:
        print(f"\nUnexpected error during setup: {e}")
        sys.exit(1)