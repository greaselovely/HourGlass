# main.py

from vla_config import *
from vla_core import *

# Operation Telescope imports
from vla_loop import create_vla_main_loop
from vla_downloader import EnhancedImageDownloader
from vla_validator import validate_images as validate_images_fast
from config_validator import validate_config_quick, health_check_quick
from memory_optimizer import optimized_create_time_lapse, memory_managed_operation, monitor_resource_usage

# Configuration constants
TEST_DURATION_HOURS = 2

def main_sequence(run_images_folder, video_path, run_audio_folder, run_valid_images_file):
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
        
        # Audio download with monitoring
        message_processor("Downloading Audio")
        audio_result, audio_metrics = monitor_resource_usage(
            audio_download, 
            duration_threshold, 
            run_audio_folder
        )
        
        if not audio_result:
            message_processor("Failed to download audio. Aborting video creation.", "error", ntfy=True)
            if 'health_monitor' in globals():
                health_monitor.update_performance_stats('errors_encountered')
            return
            
        # Prepare final audio
        if len(audio_result) >= 2:
            message_processor("Concatenating multiple audio tracks")
            final_song = concatenate_songs(audio_result)
        else:
            final_song = audio_result[0][0]
        
        # Create time-lapse video with optimized memory management
        message_processor("Creating Time-Lapse Video (Optimized)")
        video_result, video_metrics = monitor_resource_usage(
            optimized_create_time_lapse,
            valid_files, 
            video_path, 
            fps, 
            final_song, 
            crossfade_seconds=3, 
            end_black_seconds=3
        )

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
                daily_stats = process_image_logs(LOGGING_FILE, number_of_valid_files)
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
    parser = argparse.ArgumentParser(description="VLA Time Lapse Creator - Operation Telescope Enhanced")
    parser.add_argument("-m", "--movie", action="store_true", 
                       help="Generate movie only without capturing new images")
    parser.add_argument("--health", action="store_true", 
                       help="Display health status and exit")
    parser.add_argument("--validate", action="store_true", 
                       help="Validate configuration and exit")
    parser.add_argument("--no-time-check", action="store_true",
                       help="Bypass sunrise/sunset time checking (for testing)")
    args = parser.parse_args()
    
    # ===== CONFIGURATION AND VALIDATION =====
    if not load_config():
        message_processor("Failed to load configuration. Exiting.", "error")
        return

    # Validate configuration
    if not validate_config_quick():
        message_processor("Configuration validation failed. Check logs for details.", "warning")
    
    # Note: Full health monitoring will start later and provide detailed status

    # Setup logging with rotation (from vla_config.py)
    if not setup_logging(config):
        message_processor("Failed to set up logging. Exiting.", "error")
        return

    # ===== DIRECTORY SETUP =====
    for folder in [VLA_BASE, VIDEO_FOLDER, IMAGES_FOLDER, LOGGING_FOLDER, AUDIO_FOLDER]:
        os.makedirs(folder, exist_ok=True)

    # ===== HEALTH MONITORING INITIALIZATION =====
    try:
        from health_monitor import create_health_monitor
        health_monitor = create_health_monitor(config, check_interval=300)  # 5 minutes
        health_monitor.start_monitoring(background=True)
        message_processor("Health monitoring started", "info")
    except Exception as e:
        message_processor(f"Failed to start health monitoring: {e}", "warning")
        health_monitor = None

    # Handle utility commands
    if args.health:
        from health_monitor import create_health_monitor
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
        from config_validator import ConfigValidator
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
    run_id = get_or_create_run_id()
    message_processor(f"Run ID: {run_id}", "info")
    
    # Create run-specific folders
    run_images_folder = os.path.join(IMAGES_FOLDER, run_id)
    run_valid_images_file = os.path.join(run_images_folder, VALID_IMAGES_FILE)
    run_audio_folder = os.path.join(AUDIO_FOLDER, run_id)

    video_filename = f"VLA.{datetime.now().strftime('%m%d%Y')}.mp4"
    video_path = os.path.join(VIDEO_FOLDER, video_filename)

    for folder in [run_images_folder, VIDEO_FOLDER, run_audio_folder]:
        os.makedirs(folder, exist_ok=True)
    
    # ===== MOVIE-ONLY MODE =====
    if args.movie:
        message_processor("Movie-only mode: Creating video from existing images", "info", ntfy=True)
        main_sequence(run_images_folder, video_path, run_audio_folder, run_valid_images_file)
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

            now = datetime.now()
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
                sleep(sleep_timer)
                message_processor(f"Awake and Running", ntfy=True, print_me=True)

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
        downloader = EnhancedImageDownloader(
            session=session,
            out_path=run_images_folder,
            config=config,
            user_agents=USER_AGENTS,
            proxies=PROXIES,
            webpage=WEBPAGE
        )
        
        message_processor("Enhanced downloader initialized", "info")

        # ===== ROBUST MAIN LOOP =====
        message_processor("Awake and Running", ntfy=True, print_me=True)
        
        # Create and run the VLA main loop
        vla_loop = create_vla_main_loop(config, USER_AGENTS, PROXIES, WEBPAGE, IMAGE_URL)
        
        # Enhanced main loop with health monitoring integration
        def enhanced_main_sequence_callback(run_images_folder, video_path, run_audio_folder, run_valid_images_file):
            """Wrapper for main_sequence with health monitoring updates."""
            try:
                main_sequence(run_images_folder, video_path, run_audio_folder, run_valid_images_file)
                if health_monitor:
                    health_monitor.update_performance_stats('video_created')
            except Exception as e:
                if health_monitor:
                    health_monitor.update_performance_stats('errors_encountered')
                raise e
        
        # Run the VLA loop
        vla_loop.run_main_loop(
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
            main_sequence(run_images_folder, video_path, run_audio_folder, run_valid_images_file)
        except Exception as e:
            message_processor(f"Error processing images to video: {e}", "error")
            try:
                # Fallback attempt
                main_sequence(run_images_folder, video_path, run_audio_folder, run_valid_images_file)
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