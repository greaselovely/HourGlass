# video.py
"""
Video creation functionality: time-lapse creation and video processing.
"""
import os
import json
import logging
import cv2
import numpy as np
from pathlib import Path
from wurlitzer import pipes
from datetime import datetime, timedelta
from proglog import ProgressBarLogger
from moviepy.editor import ImageSequenceClip, AudioFileClip, concatenate_videoclips
from moviepy.audio.fx.all import audio_loop

from .utils import message_processor


class CustomLogger(ProgressBarLogger):
    """
    A custom logger class for displaying progress during video creation.

    This class extends ProgressBarLogger to provide custom formatting for progress updates.
    It displays progress as percentages for bar-type updates and as key-value pairs for other updates.

    Methods:
    - bars_callback: Handles updates for progress bars, displaying the progress as a percentage.
    - callback: Handles general updates, displaying them as key-value pairs.

    Both methods use carriage return to overwrite the previous line, creating a dynamic update effect.
    """
    def bars_callback(self, bar, attr, value, old_value=None):
        """
        Callback method for updating progress bars.

        Args:
        bar (str): The name of the progress bar being updated.
        attr (str): The attribute being updated (e.g., 'frame').
        value (int): The current value of the attribute.
        old_value (int, optional): The previous value of the attribute. Defaults to None.

        Displays the progress as a percentage, formatted with the bar name.
        """
        percentage = (value / self.bars[bar]['total']) * 100
        print(f"[i]\t{bar.capitalize()}: {percentage:.2f}%{' ' * 100}", end="\r")

    def callback(self, **changes):
        """
        Callback method for general updates.

        Args:
        **changes (dict): Keyword arguments representing the changes to be logged.

        Displays each change as a key-value pair.
        """
        for (name, value) in changes.items():
            print(f"[i]\t{name}: {value}{' ' * 100}", end="\r")


def validate_images(run_images_folder, run_images_valid_file) -> tuple:
    """
    Creates a dictionary of valid image file paths from the specified folder.

    This function checks for existing valid images, processes new images,
    and saves the list of valid image paths to a JSON file.

    Args:
        images_folder (str): The directory where the images are stored.
        run_images_valid_file (str): The path to the JSON file storing valid image paths.

    Returns:
        tuple: A tuple containing a list of valid image file paths and the count of valid images.
    """

    run_images_valid_file = Path(run_images_valid_file)
    run_images_folder = Path(run_images_folder)

    if run_images_valid_file.exists() and run_images_valid_file.stat().st_size > 0:
        try:
            with open(run_images_valid_file, 'r') as file:
                valid_files = json.load(file)
                message_processor("Existing Validation Used", print_me=True)
                return valid_files, len(valid_files)
        except json.JSONDecodeError:
            message_processor("Error decoding JSON, possibly corrupted file.", "error")

    else:
        images = sorted([img for img in os.listdir(run_images_folder) if img.endswith(".jpg")])
        images_dict = {}

        for n, image in enumerate(images, 1):
            print(f"[i]\t{n}", end='\r')
            full_image = Path(run_images_folder) / image
            with pipes() as (out, err):
                img = cv2.imread(str(full_image))
            err.seek(0)
            error_message = err.read()
            if error_message == "":
                images_dict[str(full_image)] = error_message

        valid_files = list(images_dict.keys())

        # Save the valid image paths to a JSON file
        with open(run_images_valid_file, 'w') as file:
            json.dump(valid_files, file)

        return valid_files, len(valid_files)


def calculate_video_duration(num_images, fps) -> int:
    """
    Calculates the expected duration of a time-lapse video.

    Args:
        num_images (int): The number of images in the time-lapse.
        fps (int): The frames per second rate for the video.

    Returns:
        int: The expected duration of the video in milliseconds.
    """
    duration_sec = num_images / fps
    duration_ms = int(duration_sec * 1000)
    return duration_ms


def create_time_lapse(valid_files, video_path, fps, audio_input=None, crossfade_seconds=3, end_black_seconds=3):
    """
    Creates a time-lapse video from a list of image files with optional audio.

    Args:
        valid_files (list): List of paths to image files.
        video_path (str): Path where the final video will be saved.
        fps (int): Frames per second for the video.
        audio_input (str or AudioFileClip, optional): Path to the audio file or an AudioFileClip object. Defaults to None.
        crossfade_seconds (int, optional): Duration of crossfade effect. Defaults to 3.
        end_black_seconds (int, optional): Duration of black screen at the end. Defaults to 3.
    """
    logger = CustomLogger()

    try:
        message_processor("Creating Time Lapse")
        message_processor(f"Creating time-lapse with {len(valid_files)} images at {fps} fps")
        video_clip = ImageSequenceClip(valid_files, fps=fps)

        audio_clip = None
        if audio_input:
            message_processor("Processing Audio")
            if isinstance(audio_input, str):
                audio_clip = AudioFileClip(audio_input)
            elif hasattr(audio_input, 'audio_fadein'):
                audio_clip = audio_input
            else:
                raise ValueError("Invalid audio input: must be a file path or an AudioClip")

            message_processor(f"Video duration: {video_clip.duration}, Audio duration: {audio_clip.duration}")

            if audio_clip.duration < video_clip.duration:
                message_processor("Audio is shorter than video. Looping audio.", "warning")
                audio_clip = audio_loop(audio_clip, duration=video_clip.duration)
            else:
                audio_clip = audio_clip.subclip(0, video_clip.duration)

            message_processor("Applying Audio Effects")
            audio_clip = audio_clip.audio_fadein(crossfade_seconds).audio_fadeout(crossfade_seconds)
            video_clip = video_clip.set_audio(audio_clip)
        else:
            message_processor("Creating video without audio")

        video_clip = video_clip.fadein(crossfade_seconds).fadeout(crossfade_seconds)

        message_processor("Creating End Frame")
        black_frame_clip = ImageSequenceClip([np.zeros((video_clip.h, video_clip.w, 3), dtype=np.uint8)], fps=fps).set_duration(end_black_seconds)

        message_processor("Concatenating Video Clips")
        final_clip = concatenate_videoclips([video_clip, black_frame_clip])

        message_processor("Writing Video File")
        logging.info(f"Writing video file to {video_path}")
        if audio_clip:
            final_clip.write_videofile(video_path, codec="libx264", audio_codec="aac", logger=logger)
        else:
            final_clip.write_videofile(video_path, codec="libx264", logger=logger)

    except Exception as e:
        error_message = f"Error in create_time_lapse: {str(e)}"
        logging.error(error_message)
        message_processor(error_message, "error", ntfy=True)
        raise  # Re-raise the exception to be caught by the calling function

    finally:
        message_processor("Closing Clips")
        try:
            if 'video_clip' in locals():
                video_clip.close()
            if 'audio_clip' in locals():
                audio_clip.close()
            if 'final_clip' in locals():
                final_clip.close()
        except Exception as close_error:
            message_processor(f"Error while closing clips: {str(close_error)}", "error")

    message_processor(f"Time Lapse Saved: {video_path}", ntfy=False)
