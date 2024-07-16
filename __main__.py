from vla_config import *
from vla_core import *

def main_sequence(IMAGES_FOLDER, NTFY_TOPIC, video_path, AUDIO_FOLDER):
    """
    Execute the main sequence of operations for creating a time-lapse video.

    This function performs the following steps:
    1. Validates images in the specified folder.
    2. Calculates video duration based on the number of valid images.
    3. Downloads and prepares audio for the video.
    4. Creates a time-lapse video with the processed images and audio.
    5. Cleans up temporary files after video creation.

    Args:
    IMAGES_FOLDER (str): Path to the folder containing images for the time-lapse.
    NTFY_TOPIC (str): URL for sending notifications about the process.
    video_path (str): Path where the final video will be saved.
    AUDIO_FOLDER (str): Path to the folder for storing temporary audio files.

    Returns:
    None
    """
        
    global config, rename
    fps = 10
    message_processor("[i]\tValidating Images...")
    valid_files = create_images_dict(IMAGES_FOLDER)
    duration_threshold = calculate_video_duration(len(valid_files), fps)
    message_processor(f"[i]\tVideo Duration: {duration_threshold}", print_me=False)
    full_audio_path = audio_download(duration_threshold, AUDIO_FOLDER)
    if len(full_audio_path) >= 2:
        final_song = concatenate_songs(full_audio_path)
    else:
        final_song = full_audio_path[0][0]
    create_time_lapse(valid_files, video_path, fps, final_song, crossfade_seconds=3, end_black_seconds=3)
    if video_path and os.path.exists(video_path):
        message_processor(f"[i]\t{os.path.basename(video_path)} saved", ntfy=True, print_me=False)
        cleanup(NTFY_TOPIC, IMAGES_FOLDER)
        cleanup(NTFY_TOPIC, AUDIO_FOLDER)

def main():
    """
    Orchestrate the entire process of creating a time-lapse video.

    This function performs the following operations:
    1. Sets up logging for the script.
    2. Creates necessary directories for the process.
    3. Retrieves sunrise and sunset times.
    4. Waits until sunrise if necessary.
    5. Continuously downloads images at set intervals until sunset.
    6. Handles session timeouts and errors by re-establishing the connection.
    7. Triggers the main sequence for video creation at sunset.
    8. Handles keyboard interrupts by attempting to create a video with existing images.

    The function runs in a loop, downloading images until interrupted or until sunset time is reached.
    It uses various helper functions and classes defined elsewhere in the script.

    Returns:
    None
    """

    logging.basicConfig(
        level = logging.INFO,  # Set the logging level (INFO, WARNING, ERROR, etc.)
        filename = LOGGING_FILE,
        format = '%(asctime)s - %(levelname)s - %(message)s'
        )

    try:
        clear()
        cursor.hide()

        for folder in [VLA_BASE, VIDEO_FOLDER, IMAGES_FOLDER, LOGGING_FOLDER, AUDIO_FOLDER]:
            os.makedirs(folder, exist_ok=True)

        video_path = os.path.join(VIDEO_FOLDER,f"VLA.{today_short_date}.mp4")
                  
        soup = sun_schedule(SUN_URL)

        sunrise_time = find_time_and_convert(soup, 'Sunrise Today:', SUNRISE)
        sunset_time = find_time_and_convert(soup, 'Sunset Today:', SUNSET)

        now = datetime.now()
        sunrise_datetime = datetime.combine(now.date(), sunrise_time)
        sunset_datetime = datetime.combine(now.date(), sunset_time)
        sunset_datetime += timedelta(minutes=SUNSET_TIME_ADD)

        if now < sunrise_datetime:
            time_diff = (sunrise_datetime - now).total_seconds()
            sleep_timer = time_diff
            message_processor(f"Sleeping for {sleep_timer} seconds / {sleep_timer  / 60} minutes until the sunrise at {sunrise_time}.", ntfy=True, print_me=True)
            sleep(sleep_timer)
            message_processor(f"Woke up! The current time is {datetime.now().time()}.", ntfy=True, print_me=True)
        else:
            message_processor("[i]\tSunrise time has already passed for today.", ntfy=True, print_me=True)

        session = create_session(USER_AGENTS, PROXIES, WEBPAGE)
        
        downloader = ImageDownloader(session, IMAGES_FOLDER)

        i = 1
        while True:
            try:
                # print("[i]\tPause for break...")
                # sleep(7)
                TARGET_HOUR = sunset_time.hour
                TARGET_MINUTE = sunset_time.minute
                SECONDS = choice(range(15, 22))  # sleep timer seconds

                image_size, filename = downloader.download_image(session, IMAGE_URL)
                
                if image_size is not None:
                    activity(i, IMAGES_FOLDER, image_size)
                    # rename_images(IMAGES_FOLDER, filename)
                else:
                    clear()
                    print(f"[!]\t{RED_CIRCLE} Iteration: {i}")

                sleep(SECONDS)
                
                i += 1
                now = datetime.now()
                if now.hour == TARGET_HOUR and now.minute >= TARGET_MINUTE:
                    main_sequence(IMAGES_FOLDER, NTFY_TOPIC, video_path, AUDIO_FOLDER)
                    cursor.show()
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
            main_sequence(IMAGES_FOLDER, NTFY_TOPIC, video_path, AUDIO_FOLDER)
        except Exception as e:
            message_processor(f"[!]\tError processing images to video:\n[i]\t{e}")
            main_sequence(IMAGES_FOLDER, NTFY_TOPIC, video_path, AUDIO_FOLDER)
        finally:
            cursor.show()

if __name__ == "__main__":
    main()
