# __main__.py

from vla_config import *
from vla_core import *
# from vla_upload import *

def main_sequence(run_images_folder, video_path, run_audio_folder, run_valid_images_file):
    """
    Execute the main sequence of operations for creating a time-lapse video.

    This function performs the following steps:
    1. Validates images in the specified folder.
    2. Calculates video duration based on the number of valid images.
    3. Downloads and prepares audio for the video.
    4. Creates a time-lapse video with the processed images and audio.
    5. Cleans up temporary files after video creation.

    Args:
    run_images_folder (str): Path to the folder containing images for this run.
    video_path (str): Path to the folder where the final video for this run will be saved.
    run_audio_folder (str): Path to the folder for storing temporary audio files for this run.

    Returns:
    None
    """
    
    global config, rename
    fps = 10
    
    try:
        message_processor("Validating Images")
        valid_files, number_of_valid_files = validate_images(run_images_folder, run_valid_images_file)

        if not valid_files:
            message_processor("No valid images found. Aborting video creation.", "error", ntfy=True)
            return
        
        duration_threshold = calculate_video_duration(len(valid_files), fps)
        message_processor(f"Video Duration: {duration_threshold}", print_me=False)
        
        full_audio_path = audio_download(duration_threshold, run_audio_folder)
        if len(full_audio_path) >= 2:
            final_song = concatenate_songs(full_audio_path)
        else:
            final_song = full_audio_path[0][0]
              
        create_time_lapse(valid_files, video_path, fps, final_song, crossfade_seconds=3, end_black_seconds=3)

        if os.path.exists(video_path):
            message_processor(f"{video_path.split('/')[-1]} saved", ntfy=True, print_me=False)
            try:
                message_processor("Stats for today:")
                message_processor(process_image_logs(LOGGING_FILE, number_of_valid_files))
                cleanup(run_images_folder)
                cleanup(run_audio_folder)
            except Exception as cleanup_error:
                cleanup_error_message = f"Error during cleanup: {str(cleanup_error)}"
                logging.error(cleanup_error_message)
                message_processor(cleanup_error_message, "error", ntfy=True)
        else:
            message_processor(f"Failed to create video: {video_path.split('/')[-1]}", "error", ntfy=True)

    except KeyboardInterrupt:
        sys.exit(0)

    except Exception as e:
        error_message = f"Error in main_sequence: {str(e)}"
        logging.error(error_message)
        message_processor(error_message, "error", ntfy=True)
  


def main():
    """
    Main function to orchestrate the VLA Time Lapse Creator process.

    This function performs the following operations:
    1. Loads configuration and sets up logging.
    2. Creates necessary directories for the process.
    3. Parses command-line arguments for movie-only mode.
    4. Generates a unique run ID and sets up run-specific folders.
    5. Executes either movie-only mode or normal operation (image capture and movie creation).
    6. In normal operation:
       - Retrieves sunrise and sunset times.
       - Waits until sunrise if necessary.
       - Continuously captures images at intervals until sunset.
       - Handles session timeouts and errors.
       - Triggers video creation at sunset.
    7. Handles keyboard interrupts by attempting to create a video with existing images.

    The function runs until interrupted or until the sunset time is reached in normal operation.

    Returns:
    None
    """
    if not load_config():
        message_processor("Failed to load configuration. Exiting.", "error")
        return

    if not setup_logging(config):
        message_processor("Failed to set up logging. Exiting.", "error")
        return

    for folder in [VLA_BASE, VIDEO_FOLDER, IMAGES_FOLDER, LOGGING_FOLDER, AUDIO_FOLDER]:
        os.makedirs(folder, exist_ok=True)

    parser = argparse.ArgumentParser(description="VLA Time Lapse Creator")
    parser.add_argument("-m", "--movie", action="store_true", help="Generate movie only without capturing new images")
    args = parser.parse_args()

    run_id = get_or_create_run_id()
    
    # Create subfolders for this run
    run_images_folder = os.path.join(IMAGES_FOLDER, run_id)
    run_valid_images_file = os.path.join(run_images_folder, VALID_IMAGES_FILE)

    video_filename = f"VLA.{datetime.now().strftime('%m%d%Y')}.mp4"
    video_path = os.path.join(VIDEO_FOLDER, video_filename)
    
    run_audio_folder = os.path.join(AUDIO_FOLDER, run_id)

    for folder in [run_images_folder, VIDEO_FOLDER, run_audio_folder]:
        os.makedirs(folder, exist_ok=True)
    
    if args.movie:
        main_sequence(run_images_folder, video_path, run_audio_folder, run_valid_images_file)
    else:
        remove_valid_images_json(run_valid_images_file)

        try:
            clear()
            cursor.hide()
                      
            soup = sun_schedule(SUN_URL)

            sunrise_time = find_time_and_convert(soup, 'Sunrise Today:', SUNRISE)
            sunset_time = find_time_and_convert(soup, 'Sunset Today:', SUNSET)

            now = datetime.now()
            sunrise_datetime = datetime.combine(now.date(), sunrise_time)
            sunset_datetime = datetime.combine(now.date(), sunset_time)
            sunset_datetime += timedelta(minutes=SUNSET_TIME_ADD)
            
            if now < sunrise_datetime:
                time_diff = (sunrise_datetime - now).total_seconds()
                sleep_timer = int(time_diff)
                message_processor(f"Sleep:\t:{sleep_timer  // 60}\nStart:\t{sunrise_time.strftime('%H:%M')}\nEnd:\t{sunset_datetime.strftime('%H:%M')}", "none", ntfy=True, print_me=True)
                sleep(sleep_timer)
                message_processor(f"Awake and Running", ntfy=True, print_me=True)
            else:
                message_processor(f"Sunset\nHour: {sunset_datetime.hour} Min:{sunset_datetime.minute}", ntfy=True)

            session = create_session(USER_AGENTS, PROXIES, WEBPAGE)
            
            downloader = ImageDownloader(session, run_images_folder)

            i = 1
            TARGET_HOUR = sunset_datetime.hour
            TARGET_MINUTE = sunset_datetime.minute
            while True:
                try:
                    SECONDS = choice(range(15, 22))  # sleep timer seconds
                    
                    downloader.load_web_page(WEBPAGE)
                    image_size, filename = downloader.download_image(session, IMAGE_URL)
                    
                    if image_size is not None:
                        activity(i, run_images_folder, image_size)
                    else:
                        clear()
                        print(f"[!]\t{RED_CIRCLE} Iteration: {i}")

                    sleep(SECONDS)
                    
                    i += 1
                    now = datetime.now()
                    if now.hour == TARGET_HOUR and now.minute >= TARGET_MINUTE:
                        main_sequence(run_images_folder, video_path, run_audio_folder, run_valid_images_file)
                        break  # Exit the loop after generating the video
                except Exception as e:
                    message_processor(log_jamming(f"Error detected, re-establishing session: {e}"), "error")
                    downloader = ImageDownloader(session, run_images_folder)
                finally:
                    cursor.show()
        except KeyboardInterrupt:
            try:
                main_sequence(run_images_folder, video_path, run_audio_folder, run_valid_images_file)
            except Exception as e:
                message_processor(log_jamming(f"Error processing images to video: {e}"), "error")
                main_sequence(run_images_folder, video_path, run_audio_folder, run_valid_images_file)
            finally:
                cursor.show()

if __name__ == "__main__":
    main()
