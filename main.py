# main.py

import sys
import cursor
import argparse
from timelapse_core import *
from timelapse_config import *
from timelapse_core import CustomLogger, ImageDownloader
from timelapse_loop import create_timelapse_main_loop
from config_validator import ConfigValidator
from health_monitor import create_health_monitor
from config_validator import validate_config_quick
from moviepy.editor import ImageSequenceClip, AudioFileClip
from timelapse_validator import validate_images as validate_images_fast
from memory_optimizer import memory_managed_operation, monitor_resource_usage


# Configuration constants
TEST_DURATION_HOURS = 2

def find_available_run_folders():
    """
    Find all available run folders with images and return friendly info.
    
    Returns:
        list: List of dicts with folder info including friendly dates
    """
    if not os.path.exists(IMAGES_FOLDER):
        return []
    
    folders = []
    for folder_name in os.listdir(IMAGES_FOLDER):
        folder_path = os.path.join(IMAGES_FOLDER, folder_name)
        if os.path.isdir(folder_path):
            # Count JPG files
            jpg_count = len([f for f in os.listdir(folder_path) if f.lower().endswith('.jpg')])
            if jpg_count > 0:
                # Parse date from folder name (YYYYMMDD_xxxxxxxx)
                try:
                    date_part = folder_name.split('_')[0]
                    date_obj = datetime.strptime(date_part, '%Y%m%d')
                    friendly_date = date_obj.strftime('%B %d, %Y')  # e.g., "June 26, 2025"
                    day_name = date_obj.strftime('%A')  # e.g., "Thursday"
                    
                    # Get folder creation time
                    creation_time = datetime.fromtimestamp(os.path.getctime(folder_path))
                    
                    folders.append({
                        'path': folder_path,
                        'run_id': folder_name,
                        'display_name': f"{friendly_date} ({day_name})",
                        'jpg_count': jpg_count,
                        'creation_time': creation_time,
                        'date_obj': date_obj
                    })
                except (ValueError, IndexError):
                    # Skip folders that don't match expected format
                    continue
    
    # Sort by date (newest first)
    folders.sort(key=lambda x: x['date_obj'], reverse=True)
    return folders

def prompt_user_for_run_folder_selection(folders):
    """
    Prompt user to select a run folder from available options.
    
    Args:
        folders (list): List of folder info dicts
        
    Returns:
        dict: Selected folder info
    """
    print("\nAvailable image folders:")
    print("-" * 60)
    
    for i, folder_info in enumerate(folders, 1):
        creation_time = folder_info['creation_time'].strftime("%H:%M")
        print(f"{i}. {folder_info['display_name']}")
        print(f"   Created: {creation_time} | Images: {folder_info['jpg_count']}")
        print()
    
    while True:
        try:
            choice = input("Select folder number (or press Enter for most recent): ").strip()
            
            if choice == "":
                # Default to most recent (first in list)
                selected = folders[0]
                print(f"Using: {selected['display_name']}")
                return selected
            
            choice_num = int(choice)
            if 1 <= choice_num <= len(folders):
                selected = folders[choice_num - 1]
                print(f"Using: {selected['display_name']}")
                return selected
            else:
                print(f"Please enter a number between 1 and {len(folders)}")
        except ValueError:
            print("Please enter a valid number or press Enter for default")

def main_sequence(run_images_folder, video_path, run_audio_folder, run_valid_images_file, time_offset=0, debug=False):
    """
    Execute the main sequence of operations for creating a time-lapse video.
    Enhanced with memory management and performance monitoring.

    This function performs the following steps:
    1. Validates images in the specified folder (using fast validation).
    2. Calculates video duration based on the number of valid images.
    3. Downloads and prepares audio for the video.
    4. Creates a time-lapse video with optimized memory management.
    5. Cleans up temporary files after video creation.

    Args:
    run_images_folder (str): Path to the folder containing images for this run.
    video_path (str): Path to the folder where the final video for this run will be saved.
    run_audio_folder (str): Path to the folder for storing temporary audio files for this run.
    run_valid_images_file (str): Path to the validation JSON file.

    Returns:
    None
    """
    
    global config, health_monitor
    fps = 10
    
    try:
        # Image validation with memory management
        message_processor("Validating Images (Fast Mode)")
        with memory_managed_operation("image_validation"):
            valid_files, number_of_valid_files = validate_images_fast(
                run_images_folder, 
                run_valid_images_file, 
                use_fast=True
            )

        if not valid_files:
            message_processor("No valid images found. Aborting video creation.", "error", ntfy=True)
            if 'health_monitor' in globals():
                health_monitor.update_performance_stats('errors_encountered')
            return
        
        message_processor(f"Validated {number_of_valid_files} images successfully")
        
        # Calculate video requirements
        duration_threshold = calculate_video_duration(len(valid_files), fps)
        message_processor(f"Video Duration: {duration_threshold/1000:.1f} seconds", print_me=True)
        
        # Audio download with monitoring (optional) - now using Pixabay
        final_song = None
        try:
            message_processor("Attempting to download audio from Pixabay...", "info")
            audio_result, audio_metrics = monitor_resource_usage(
                audio_download, 
                duration_threshold, 
                run_audio_folder,
                debug
            )
            
            if audio_result:
                # Prepare final audio
                if len(audio_result) >= 2:
                    message_processor("Concatenating multiple audio tracks")
                    final_song = concatenate_songs(audio_result)
                else:
                    # Handle single audio file - check if it's a tuple or just a path
                    if isinstance(audio_result[0], tuple) and len(audio_result[0]) > 0:
                        final_song = audio_result[0][0]  # Extract path from tuple
                    else:
                        final_song = audio_result[0]  # Use the result directly
                    message_processor("Using single audio track")
            else:
                message_processor("Audio download failed. Proceeding without audio.", "warning", ntfy=True)
        except Exception as e:
            message_processor(f"Audio download error: {e}. Proceeding without audio.", "warning", ntfy=True)
            final_song = None
        
        # Create time-lapse video (simplified without black frame for now)
        message_processor("Creating Time-Lapse Video")
        
        # Temporary simple version without black frame
        try:
            logger = CustomLogger()
            
            message_processor("Creating video clip from images")
            video_clip = ImageSequenceClip(valid_files, fps=fps)
            
            # Handle audio if available
            audio_clip = None
            if final_song:
                message_processor("Processing audio")
                if isinstance(final_song, str):
                    audio_clip = AudioFileClip(final_song)
                else:
                    audio_clip = final_song
                
                # Sync audio and video
                if audio_clip.duration < video_clip.duration:
                    message_processor("Looping audio to match video length")
                    audio_clip = audio_clip.loop(duration=video_clip.duration)
                else:
                    audio_clip = audio_clip.subclip(0, video_clip.duration)
                
                # Apply audio effects
                audio_clip = audio_clip.audio_fadein(3).audio_fadeout(3)
                video_clip = video_clip.set_audio(audio_clip)
            else:
                message_processor("Creating video without audio")
            
            # Apply video effects
            video_clip = video_clip.fadein(3).fadeout(3)
            
            # Write video
            message_processor("Writing video file")
            if audio_clip:
                video_clip.write_videofile(video_path, codec="libx264", audio_codec="aac", logger=logger)
            else:
                video_clip.write_videofile(video_path, codec="libx264", logger=logger)
            
            # Cleanup
            video_clip.close()
            if audio_clip:
                audio_clip.close()
            
            video_metrics = {'duration_seconds': 0, 'memory_change_mb': 0}
            
        except Exception as e:
            message_processor(f"Error in video creation: {e}", "error", ntfy=True)
            video_metrics = {'duration_seconds': 0, 'memory_change_mb': 0}

        # Check if video was created successfully
        if os.path.exists(video_path):
            video_size_mb = os.path.getsize(video_path) / (1024 * 1024)
            message_processor(
                f"{video_path.split('/')[-1]} saved successfully ({video_size_mb:.1f}MB)", 
                ntfy=True, 
                print_me=True
            )
            
            # Log performance metrics
            message_processor(f"Video creation took {video_metrics['duration_seconds']:.1f}s, "
                            f"memory change: {video_metrics['memory_change_mb']:+.1f}MB")
            
            try:
                # Display daily statistics
                message_processor("=== Daily Statistics ===")
                daily_stats = process_image_logs(LOGGING_FILE, number_of_valid_files, time_offset)
                message_processor(daily_stats)
                
                # Cleanup with memory management
                message_processor("Cleaning up temporary files")
                with memory_managed_operation("cleanup"):
                    cleanup(run_images_folder)
                    cleanup(run_audio_folder)
                
                message_processor("Main sequence completed successfully", ntfy=True)
                
            except Exception as cleanup_error:
                cleanup_error_message = f"Error during cleanup: {str(cleanup_error)}"
                logging.error(cleanup_error_message)
                message_processor(cleanup_error_message, "error", ntfy=True)
                if 'health_monitor' in globals():
                    health_monitor.update_performance_stats('errors_encountered')
        else:
            error_msg = f"Failed to create video: {video_path.split('/')[-1]}"
            message_processor(error_msg, "error", ntfy=True)
            if 'health_monitor' in globals():
                health_monitor.update_performance_stats('errors_encountered')

    except KeyboardInterrupt:
        message_processor("Keyboard interrupt in main_sequence", "warning")
        sys.exit(0)

    except Exception as e:
        error_message = f"Error in main_sequence: {str(e)}"
        logging.error(error_message)
        message_processor(error_message, "error", ntfy=True)
        if 'health_monitor' in globals():
            health_monitor.update_performance_stats('errors_encountered')
  
def main():
    """
    Enhanced main function with Operation Telescope improvements:
    - Configuration validation
    - Health monitoring
    - Robust error handling
    - Performance monitoring
    - Memory management
    """
    global health_monitor
    
    # ===== COMMAND LINE ARGUMENTS - MOVED UP FIRST =====
    parser = argparse.ArgumentParser(description="HourGlass Timelapse System - Automated Webcam Capture")
    parser.add_argument("-m", "--movie", action="store_true", 
                       help="Generate movie only without capturing new images")
    parser.add_argument("--health", action="store_true", 
                       help="Display health status and exit")
    parser.add_argument("--validate", action="store_true", 
                       help="Validate configuration and exit")
    parser.add_argument("--no-time-check", action="store_true",
                       help="Bypass sunrise/sunset time checking (for testing)")
    parser.add_argument("--force-prompt", action="store_true",
                       help="Force folder selection prompt in movie mode")
    parser.add_argument("--debug", action="store_true",
                       help="Enable debug mode (saves Pixabay HTML/JSON responses)")
    args = parser.parse_args()
    
    # ===== CONFIGURATION AND VALIDATION =====
    if not load_config():
        message_processor("Failed to load configuration. Exiting.", "error")
        return
    
    time_offset = 0
    if "sun" in config and "TIME_OFFSET_HOURS" in config["sun"]:
        time_offset = config["sun"]["TIME_OFFSET_HOURS"]

    # Validate configuration
    if not validate_config_quick():
        message_processor("Configuration validation failed. Check logs for details.", "warning")
    
    # Note: Full health monitoring will start later and provide detailed status

    # Setup logging with rotation (from timelapse_config.py)
    if not setup_logging(config):
        message_processor("Failed to set up logging. Exiting.", "error")
        return

    # ===== DIRECTORY SETUP =====
    for folder in [PROJECT_BASE, VIDEO_FOLDER, IMAGES_FOLDER, LOGGING_FOLDER, AUDIO_FOLDER]:
        os.makedirs(folder, exist_ok=True)

    # ===== HEALTH MONITORING INITIALIZATION =====
    try:
        health_monitor = create_health_monitor(config, check_interval=300)  # 5 minutes
        health_monitor.start_monitoring(background=True)
        message_processor("Health monitoring started", "info")
        
        # Make health_monitor globally accessible for other modules
        sys.modules[__name__].health_monitor = health_monitor
        
    except Exception as e:
        message_processor(f"Failed to start health monitoring: {e}", "warning")
        health_monitor = None

    # Handle utility commands
    if args.health:
        health_monitor = create_health_monitor(config)
        detailed_health = health_monitor.perform_health_check()
        
        print(f"Overall Status: {detailed_health['overall_status']}")
        print(f"Uptime: {detailed_health['uptime_hours']:.2f} hours")
        print("\nDetailed Metrics:")
        
        for metric in detailed_health['metrics']:
            status_icon = "✅" if metric['status'] == 'healthy' else "⚠️" if metric['status'] == 'warning' else "❌"
            print(f"  {status_icon} {metric['name']}: {metric['message']}")
        
        return
    
    if args.validate:
        validator = ConfigValidator()
        result = validator.validate_config(config)
        health_result = validator.health_check(config)
        
        print(f"Configuration Valid: {result['valid']}")
        print(f"Health Status: {health_result['overall_status']}")
        if result['errors']:
            print("Errors:", result['errors'])
        if result['warnings']:
            print("Warnings:", result['warnings'])
        return

    # ===== RUN SETUP =====
    run_id = get_or_create_run_id(time_offset)
    message_processor(f"Run ID: {run_id}", "info")
    
    # Create run-specific folders
    run_images_folder = os.path.join(IMAGES_FOLDER, run_id)
    run_valid_images_file = os.path.join(run_images_folder, VALID_IMAGES_FILE)
    run_audio_folder = os.path.join(AUDIO_FOLDER, run_id)

    video_filename = datetime.now().strftime(VIDEO_FILENAME_FORMAT)
    video_path = os.path.join(VIDEO_FOLDER, video_filename)

    for folder in [run_images_folder, VIDEO_FOLDER, run_audio_folder]:
        os.makedirs(folder, exist_ok=True)
    
    # ===== MOVIE-ONLY MODE =====
    if args.movie:
        message_processor("Movie-only mode: Creating video from existing images", "info", ntfy=True)
        
        # Always prompt for folder selection in movie mode, or if only one folder but --force-prompt
        available_folders = find_available_run_folders()
        if not available_folders:
            message_processor("No image folders found. Nothing to process.", "error")
            return
        elif len(available_folders) == 1 and not args.force_prompt:
            selected_folder_info = available_folders[0]
            message_processor(f"Using only available folder: {selected_folder_info['display_name']}")
        else:
            selected_folder_info = prompt_user_for_run_folder_selection(available_folders)
        
        # Update paths for selected folder
        run_images_folder = selected_folder_info['path']
        run_valid_images_file = os.path.join(run_images_folder, VALID_IMAGES_FILE)
        # Use current run_id for audio folder (fresh audio download)
        run_audio_folder = os.path.join(AUDIO_FOLDER, run_id)  # Use today's audio folder
        
        # Use the date from the selected folder for the video filename
        folder_date = selected_folder_info['date_obj'].strftime('%m%d%Y')
        video_filename = f"{PROJECT_NAME}.{folder_date}.mp4"
        video_path = os.path.join(VIDEO_FOLDER, video_filename)
        
        main_sequence(run_images_folder, video_path, run_audio_folder, run_valid_images_file, time_offset, args.debug)
        if health_monitor:
            health_monitor.stop_monitoring()
        return

    # ===== IMAGE CAPTURE MODE =====
    message_processor("Starting image capture mode", "info", ntfy=True)
    
    # Clean up previous validation
    remove_valid_images_json(run_valid_images_file)

    try:
        clear()
        cursor.hide()
        
        # ===== SUN SCHEDULE CALCULATION =====
        if not args.no_time_check:
            message_processor("Fetching sun schedule")
            soup = sun_schedule(SUN_URL)

            sunrise_time = find_time_and_convert(soup, 'Sunrise Today:', SUNRISE)
            sunset_time = find_time_and_convert(soup, 'Sunset Today:', SUNSET)

            now = datetime.now() + timedelta(hours=time_offset)
            sunrise_datetime = datetime.combine(now.date(), sunrise_time)
            sunset_datetime = datetime.combine(now.date(), sunset_time)
            sunset_datetime += timedelta(minutes=SUNSET_TIME_ADD)

            # Check if we're past sunset
            if now > sunset_datetime:
                message_processor("Current time is after sunset. Exiting script.", "info")
                if health_monitor:
                    health_monitor.stop_monitoring()
                sys.exit(0)
            
            # Sleep until sunrise if needed
            if now < sunrise_datetime:
                sleep_timer = int((sunrise_datetime - now).total_seconds())
                hours, minutes = divmod(sleep_timer // 60, 60)

                message_processor(
                    f"Sleep:\t{hours:02d}:{minutes:02d}\nStart:\t{sunrise_time.strftime('%H:%M')}\nEnd:\t{sunset_datetime.strftime('%H:%M')}",
                    "none",
                    ntfy=True,
                    print_me=True
                )
                if health_monitor:
                    health_monitor.set_sleep_status(True)
                sleep(sleep_timer)
                if health_monitor:
                    health_monitor.set_sleep_status(False)

            TARGET_HOUR = sunset_datetime.hour
            TARGET_MINUTE = sunset_datetime.minute
        else:
            message_processor("Bypassing time checks (--no-time-check mode)", "info")
            # Set a target time based on configurable test duration
            now = datetime.now()
            target_time = now + timedelta(hours=TEST_DURATION_HOURS)
            TARGET_HOUR = target_time.hour
            TARGET_MINUTE = target_time.minute
            
            # Display the same format as normal mode
            message_processor(
                f"Sleep:\t00:00\nStart:\t{now.strftime('%H:%M')}\nEnd:\t{target_time.strftime('%H:%M')}",
                "none",
                ntfy=True,
                print_me=True
            )

        # ===== SESSION CREATION =====
        message_processor("Creating session")
        session = create_session(USER_AGENTS, PROXIES, WEBPAGE)
        
        if not session:
            message_processor("Failed to create initial session. Exiting.", "error", ntfy=True)
            if health_monitor:
                health_monitor.stop_monitoring()
            return

        # ===== ENHANCED DOWNLOADER SETUP =====
        downloader = ImageDownloader(
            session=session,
            out_path=run_images_folder,
            config=config,
            user_agents=USER_AGENTS,
            proxies=PROXIES,
            webpage=WEBPAGE,
            health_monitor=health_monitor,  # Pass health monitor
            time_offset=time_offset
        )
        
        message_processor("Enhanced downloader initialized", "info")

        # ===== ROBUST MAIN LOOP =====
        message_processor("Awake and Running", ntfy=True, print_me=True)
        
        # Create and run the HourGlass main loop
        timelapse_loop = create_timelapse_main_loop(config, USER_AGENTS, PROXIES, WEBPAGE, IMAGE_URL, time_offset=time_offset)
        
        # Enhanced main loop with health monitoring integration
        def enhanced_main_sequence_callback(run_images_folder, video_path, run_audio_folder, run_valid_images_file):
            """Wrapper for main_sequence with health monitoring updates."""
            try:
                main_sequence(run_images_folder, video_path, run_audio_folder, run_valid_images_file, time_offset, args.debug)
                if health_monitor:
                    health_monitor.update_performance_stats('video_created')
            except Exception as e:
                if health_monitor:
                    health_monitor.update_performance_stats('errors_encountered')
                raise e
        
        # Run the timelapse loop
        timelapse_loop.run_main_loop(
            downloader=downloader,
            run_images_folder=run_images_folder,
            target_hour=TARGET_HOUR,
            target_minute=TARGET_MINUTE,
            main_sequence_callback=enhanced_main_sequence_callback,
            run_valid_images_file=run_valid_images_file,
            video_path=video_path,
            run_audio_folder=run_audio_folder,
            test_mode=args.no_time_check  # Pass the test mode flag
        )

    except KeyboardInterrupt:
        message_processor("Keyboard interrupt received", "warning", ntfy=True)
        try:
            message_processor("Processing existing images into video...")
            main_sequence(run_images_folder, video_path, run_audio_folder, run_valid_images_file, time_offset, args.debug)
        except Exception as e:
            message_processor(f"Error processing images to video: {e}", "error")
            try:
                # Fallback attempt
                main_sequence(run_images_folder, video_path, run_audio_folder, run_valid_images_file, time_offset, args.debug)
            except Exception as fallback_error:
                message_processor(f"Fallback video creation failed: {fallback_error}", "error", ntfy=True)
        finally:
            cursor.show()
            if health_monitor:
                health_monitor.stop_monitoring()

    except Exception as e:
        error_message = f"Unexpected error in main: {str(e)}"
        message_processor(error_message, "error", ntfy=True)
        logging.error(error_message)
        
    finally:
        cursor.show()
        if health_monitor:
            message_processor("Stopping health monitoring")
            health_monitor.stop_monitoring()
        
        message_processor("Application shutdown complete", "info")

if __name__ == "__main__":
    main()