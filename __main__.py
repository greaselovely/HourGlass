# __main__.py

from vla_config import *
from vla_core import *
from vla_upload import *

def main_sequence(run_images_folder, run_video_folder, run_audio_folder):
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
    run_video_folder (str): Path to the folder where the final video for this run will be saved.
    run_audio_folder (str): Path to the folder for storing temporary audio files for this run.

    Returns:
    None
    """
    
    global config, rename
    fps = 10
    
    message_processor("Validating Images")
    valid_files = create_images_dict(run_images_folder)

    if not valid_files:
        message_processor("No valid images found. Aborting video creation.", "error", ntfy=False)
        return
    
    duration_threshold = calculate_video_duration(len(valid_files), fps)
    message_processor(f"Video Duration: {duration_threshold}", print_me=False)
    
    full_audio_path = audio_download(duration_threshold, run_audio_folder)
    if len(full_audio_path) >= 2:
        final_song = concatenate_songs(full_audio_path)
    else:
        final_song = full_audio_path[0][0]
    
    create_time_lapse(valid_files, run_video_folder, fps, final_song, crossfade_seconds=3, end_black_seconds=3)

    if os.path.exists(run_video_folder):
        message_processor(f"{os.path.basename(run_video_folder)} saved", ntfy=True, print_me=False)
        
        # # Upload to YouTube
        # date_obj = datetime.now()
        # formatted_date = date_obj.strftime("%m/%d/%Y")
        # video_title = f"VLA {formatted_date}"
        # video_description = f"@NRAO Very Large Array Time Lapse for {formatted_date}"
        
        # video_id, youtube_client = upload_to_youtube(video_path, video_title, video_description)
        
        # if video_id and youtube_client:
        #     message_processor(f"Video uploaded to YouTube ID: {video_id}", ntfy=True)
            
        #     # Now, add the video to the playlist
        #     success, message = add_video_to_playlist(youtube_client, video_id, "VLA")
        #     if success:
        #         message_processor(message, ntfy=True)
        #     else:
        #         message_processor(message, ntfy=True)
        # else:
        #     message_processor("Failed to upload video to YouTube", "error", ntfy=True)
        #     message_processor(f"{os.path.basename(video_path)} saved", ntfy=True, print_me=False)

    # Cleanup
    cleanup(run_images_folder)
    cleanup(run_audio_folder)

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
    # run_video_folder = os.path.join(VIDEO_FOLDER, run_id)
    run_video_folder = VIDEO_FOLDER
    run_audio_folder = os.path.join(AUDIO_FOLDER, run_id)

    for folder in [run_images_folder, run_video_folder, run_audio_folder]:
        os.makedirs(folder, exist_ok=True)
    
    video_filename = f"VLA.{datetime.now().strftime('%Y%m%d')}.mp4"
    video_path = os.path.join(run_video_folder, video_filename)

    if args.movie:
        # Generate movie only
        main_sequence(run_images_folder, video_path, run_audio_folder)
    else:
        # Normal operation (capture images and generate movie)
        remove_valid_images_json(run_images_folder)

        try:
            clear()
            cursor.hide()

            video_filename = f"VLA_{datetime.now().strftime('%Y%m%d')}.mp4"
            video_path = os.path.join(run_video_folder, video_filename)
                      
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
                message_processor(f"Starting: {datetime.now().strftime("%H:%M")}.", ntfy=True, print_me=True)

            session = create_session(USER_AGENTS, PROXIES, WEBPAGE)
            
            downloader = ImageDownloader(session, run_images_folder)

            i = 1
            while True:
                try:
                    TARGET_HOUR = sunset_time.hour
                    TARGET_MINUTE = sunset_time.minute
                    SECONDS = choice(range(15, 22))  # sleep timer seconds

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
                        main_sequence(run_images_folder, run_video_folder, run_audio_folder)
                        break  # Exit the loop after generating the video
                except requests.exceptions.RequestException as e:
                    log_message = f"Session timeout or error detected, re-establishing session: {e}"
                    logging.error(log_jamming(log_message))
                    message_processor(f"Session timeout or error detected, re-establishing session...\n{e}\n", log_level="error")
                    session = create_session(USER_AGENTS, PROXIES, WEBPAGE)
                    downloader.download_image(session, IMAGE_URL)
                finally:
                    cursor.show()

        except KeyboardInterrupt:
            try:
                main_sequence(run_images_folder, run_video_folder, run_audio_folder)
            except Exception as e:
                message_processor(f"Error processing images to video: {e}", "error")
                main_sequence(run_images_folder, run_video_folder, run_audio_folder)
            finally:
                cursor.show()

if __name__ == "__main__":
    main()
