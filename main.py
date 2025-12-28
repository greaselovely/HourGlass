# main.py

import sys
import os
import cursor
import argparse
import subprocess
from pathlib import Path
from datetime import datetime, timedelta
# Don't import timelapse_config yet - it may create default config
# We'll import it after checking if project config exists


# Configuration constants
TEST_DURATION_HOURS = 2

def check_config_needs_setup(config):
    """
    Check if the configuration needs initial setup.
    
    Returns True if config has default/empty critical values.
    """
    critical_empty_fields = []
    
    # Check critical URLs
    urls = config.get('urls', {})
    if not urls.get('IMAGE_URL') or urls.get('IMAGE_URL') == 'https://example.com/webcam.jpg' or urls.get('IMAGE_URL') == '':
        critical_empty_fields.append('IMAGE_URL')
    if not urls.get('WEBPAGE') or urls.get('WEBPAGE') == 'https://example.com' or urls.get('WEBPAGE') == '':
        critical_empty_fields.append('WEBPAGE')
    
    # Check if sun URL is empty (optional but recommended)
    sun = config.get('sun', {})
    if not sun.get('URL'):
        critical_empty_fields.append('sun.URL (optional but recommended)')
    
    return len(critical_empty_fields) > 0, critical_empty_fields

def import_dependencies(config_path=None):
    """Import all the dependencies after config check."""
    global message_processor, load_config, config, validate_config_quick
    global create_timelapse_main_loop, ConfigValidator, create_health_monitor
    global validate_images_fast, memory_managed_operation, monitor_resource_usage
    global ImageSequenceClip, AudioFileClip, audio_loop, CustomLogger, ImageDownloader
    global PROJECT_BASE, VIDEO_FOLDER, IMAGES_FOLDER, LOGGING_FOLDER, AUDIO_FOLDER
    global setup_logging
    
    from lib.timelapse_core import message_processor, CustomLogger, ImageDownloader
    from lib.timelapse_config import load_config, setup_logging
    from lib.timelapse_loop import create_timelapse_main_loop
    
    # Load the specific config
    loaded_config = load_config(config_path)
    if loaded_config:
        # Import the config values globally
        global config
        config = loaded_config
        
        # Update all the global variables from the loaded config
        global SUN_URL, IMAGE_URL, WEBPAGE, SUNRISE, SUNSET, SUNSET_TIME_ADD
        global PROJECT_BASE, VIDEO_FOLDER, IMAGES_FOLDER, LOGGING_FOLDER, AUDIO_FOLDER
        global USER_AGENTS, PROXIES, PROJECT_NAME, VALID_IMAGES_FILE
        global VIDEO_FILENAME_FORMAT, LOGGING_FILE, NTFY_TOPIC, NTFY_URL, ALERTS_ENABLED
        
        # Extract values from loaded config
        SUN_URL = config.get('sun', {}).get('URL', '')
        SUNRISE = config.get('sun', {}).get('SUNRISE', '06:00:00')
        SUNSET = config.get('sun', {}).get('SUNSET', '19:00:00')
        SUNSET_TIME_ADD = config.get('sun', {}).get('SUNSET_TIME_ADD', 60)
        IMAGE_URL = config.get('urls', {}).get('IMAGE_URL', '')
        WEBPAGE = config.get('urls', {}).get('WEBPAGE', '')
        
        # Extract user agents and proxies
        USER_AGENTS = config.get('user_agents', [])
        PROXIES = config.get('proxies', {})
        
        PROJECT_NAME = config.get('project', {}).get('name', 'default')
        PROJECT_BASE = config['files_and_folders'].get('PROJECT_BASE', os.path.join(Path.home(), 'HourGlass', PROJECT_NAME))
        VIDEO_FOLDER = config['files_and_folders'].get('VIDEO_FOLDER', os.path.join(PROJECT_BASE, 'video'))
        IMAGES_FOLDER = config['files_and_folders'].get('IMAGES_FOLDER', os.path.join(PROJECT_BASE, 'images'))
        LOGGING_FOLDER = config['files_and_folders'].get('LOGGING_FOLDER', os.path.join(PROJECT_BASE, 'logging'))
        AUDIO_FOLDER = config['files_and_folders'].get('AUDIO_FOLDER', os.path.join(PROJECT_BASE, 'audio'))
        
        # Extract additional file and format settings
        VALID_IMAGES_FILE = config['files_and_folders'].get('VALID_IMAGES_FILE', 'valid_images.json')
        LOG_FILE_NAME = config['files_and_folders'].get('LOG_FILE_NAME', 'timelapse.log')
        LOGGING_FILE = os.path.join(LOGGING_FOLDER, LOG_FILE_NAME)
        VIDEO_FILENAME_FORMAT = config.get('video', {}).get('VIDEO_FILENAME_FORMAT', f'{PROJECT_NAME}.%m%d%Y.mp4')
        
        # Extract alert settings
        NTFY_TOPIC = config.get('alerts', {}).get('ntfy', '')
        NTFY_URL = config.get('ntfy', 'http://ntfy.sh/')
        ALERTS_ENABLED = config.get('alerts', {}).get('enabled', False)
    
    from lib.config_validator import ConfigValidator, validate_config_quick
    from lib.health_monitor import create_health_monitor
    from moviepy.editor import ImageSequenceClip, AudioFileClip
    from moviepy.audio.fx.all import audio_loop
    from lib.timelapse_validator import validate_images as validate_images_fast
    from lib.memory_optimizer import memory_managed_operation, monitor_resource_usage

    # Import everything else from timelapse_core and timelapse_config
    # BUT don't overwrite the variables we just set from the loaded config
    from lib import timelapse_core
    from lib import timelapse_config
    
    # Variables to preserve (that we just set from the loaded config)
    preserve_vars = {
        'SUN_URL', 'IMAGE_URL', 'WEBPAGE', 'SUNRISE', 'SUNSET', 'SUNSET_TIME_ADD',
        'PROJECT_BASE', 'VIDEO_FOLDER', 'IMAGES_FOLDER', 'LOGGING_FOLDER', 'AUDIO_FOLDER',
        'USER_AGENTS', 'PROXIES', 'PROJECT_NAME', 'VALID_IMAGES_FILE',
        'VIDEO_FILENAME_FORMAT', 'LOGGING_FILE', 'config',
        'NTFY_TOPIC', 'NTFY_URL', 'ALERTS_ENABLED'
    }
    
    for name in dir(timelapse_core):
        if not name.startswith('_') and name not in preserve_vars:
            globals()[name] = getattr(timelapse_core, name)
    for name in dir(timelapse_config):
        if not name.startswith('_') and name not in preserve_vars:
            globals()[name] = getattr(timelapse_config, name)
    
    return loaded_config

def test_network_connectivity():
    """Test basic network connectivity to Pixabay."""
    import subprocess
    import platform
    
    print("\n" + "-"*40)
    print("Network Connectivity Test")
    print("-"*40)
    
    tests_passed = 0
    tests_total = 0
    
    # Test 1: DNS resolution
    print("\n1. Testing DNS resolution for pixabay.com...")
    tests_total += 1
    try:
        import socket
        ips = socket.gethostbyname_ex('pixabay.com')[2]
        print(f"   SUCCESS: Resolved to IPs: {', '.join(ips)}")
        tests_passed += 1
    except Exception as e:
        print(f"   FAILED: {e}")
    
    # Test 2: Ping test (if available)
    print("\n2. Testing ping to pixabay.com...")
    tests_total += 1
    try:
        ping_cmd = "ping" if platform.system().lower() == "windows" else "ping"
        result = subprocess.run(
            [ping_cmd, "-c", "4", "pixabay.com"],
            capture_output=True,
            text=True,
            timeout=10
        )
        if result.returncode == 0:
            print("   SUCCESS: Ping successful")
            # Extract average ping time if possible
            for line in result.stdout.split('\n'):
                if 'avg' in line or 'Average' in line:
                    print(f"   {line.strip()}")
            tests_passed += 1
        else:
            print(f"   FAILED: Ping failed with return code {result.returncode}")
    except subprocess.TimeoutExpired:
        print("   FAILED: Ping timeout")
    except Exception as e:
        print(f"   WARNING: Could not run ping: {e}")
        tests_total -= 1  # Don't count this test
    
    # Test 3: HTTP connectivity with curl
    print("\n3. Testing HTTP access with curl...")
    tests_total += 1
    try:
        result = subprocess.run(
            ["curl", "-I", "-s", "-o", "/dev/null", "-w", "%{http_code}", "https://pixabay.com"],
            capture_output=True,
            text=True,
            timeout=10
        )
        status_code = result.stdout.strip()
        if status_code == "200":
            print(f"   SUCCESS: HTTP {status_code}")
            tests_passed += 1
        elif status_code == "403":
            print(f"   WARNING: HTTP {status_code} - Possible IP blocking")
        else:
            print(f"   FAILED: HTTP {status_code}")
    except subprocess.TimeoutExpired:
        print("   FAILED: Request timeout")
    except FileNotFoundError:
        print("   SKIPPED: curl not installed")
        tests_total -= 1
    except Exception as e:
        print(f"   FAILED: {e}")
    
    # Test 4: Test with different user agents
    print("\n4. Testing with different User-Agents...")
    tests_total += 1
    user_agents = [
        ("curl", "curl/7.68.0"),
        ("chrome", "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"),
        ("firefox", "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:109.0) Gecko/20100101 Firefox/121.0")
    ]
    
    any_success = False
    for name, ua in user_agents:
        try:
            result = subprocess.run(
                ["curl", "-I", "-s", "-o", "/dev/null", "-w", "%{http_code}", 
                 "-H", f"User-Agent: {ua}", "https://pixabay.com"],
                capture_output=True,
                text=True,
                timeout=10
            )
            status_code = result.stdout.strip()
            status = "OK" if status_code == "200" else f"HTTP {status_code}"
            print(f"   {name:10} -> {status}")
            if status_code == "200":
                any_success = True
        except:
            pass
    
    if any_success:
        print("   SUCCESS: At least one user agent works")
        tests_passed += 1
    else:
        print("   FAILED: All user agents blocked or failed")
    
    # Summary
    print("\n" + "-"*40)
    print(f"Network Test Summary: {tests_passed}/{tests_total} tests passed")
    if tests_passed < tests_total:
        print("\nTroubleshooting suggestions:")
        print("1. Check if your server's IP is blocked by Pixabay")
        print("2. Try using a VPN or proxy")
        print("3. Verify firewall rules allow outbound HTTPS")
        print("4. Consider rate limiting - wait before retrying")
    print("-"*40)
    
    return tests_passed == tests_total

def test_audio_download(config, duration_seconds=60, debug=False, test_network=False, user_agent_override=None):
    """
    Test audio download functionality independently.
    
    Args:
        config: The loaded configuration
        duration_seconds: Target duration in seconds for audio
        debug: Enable debug mode to save HTML/JSON responses
        test_network: Run network connectivity tests first
        user_agent_override: Override the user agent for testing
    """
    from datetime import datetime
    from lib.timelapse_core import audio_download, concatenate_songs, distribute_songs_evenly, message_processor, create_tts_intro, combine_tts_with_music
    from moviepy.editor import AudioFileClip
    import os
    
    print("\n" + "="*60)
    print(" Audio Download Test Mode")
    print("="*60)
    
    # Run network tests if requested
    if test_network:
        network_ok = test_network_connectivity()
        if not network_ok:
            print("\nNetwork tests indicate potential connectivity issues.")
            response = input("Continue with audio download test anyway? (y/n): ")
            if response.lower() != 'y':
                return False
    
    # Get project name and create test audio folder
    project_name = config.get('project', {}).get('name', 'default')
    project_base = config['files_and_folders'].get('PROJECT_BASE', 
                    os.path.join(Path.home(), 'HourGlass', project_name))
    audio_folder = config['files_and_folders'].get('AUDIO_FOLDER', 
                    os.path.join(project_base, 'audio'))
    
    # Create test subfolder with timestamp
    test_timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    test_audio_folder = os.path.join(audio_folder, f'test_{test_timestamp}')
    os.makedirs(test_audio_folder, exist_ok=True)
    
    print(f"\nProject: {project_name}")
    print(f"Test folder: {test_audio_folder}")
    print(f"Target duration: {duration_seconds} seconds")
    print(f"Debug mode: {'ON' if debug else 'OFF'}")
    
    # Convert duration to milliseconds (as expected by audio_download)
    duration_ms = duration_seconds * 1000
    
    print("\n" + "-"*40)
    print("Starting audio download test...")
    print("-"*40 + "\n")
    
    try:
        # Call the audio download function
        audio_result = audio_download(duration_ms, test_audio_folder, debug, config)
        
        if audio_result and len(audio_result) > 0:
            print(f"\nSuccessfully downloaded {len(audio_result)} audio file(s)")
            
            # Display info about each downloaded file
            total_duration = 0
            for i, (file_path, duration_sec) in enumerate(audio_result, 1):
                file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
                file_name = os.path.basename(file_path)
                print(f"\n  File {i}: {file_name}")
                print(f"    Duration: {duration_sec:.2f} seconds")
                print(f"    Size: {file_size_mb:.2f} MB")
                print(f"    Path: {file_path}")
                total_duration += duration_sec
            
            print(f"\n  Total duration: {total_duration:.2f} seconds")
            
            # Test concatenation if multiple files
            if len(audio_result) > 1:
                print("\n" + "-"*40)
                print("Testing audio concatenation...")
                print("-"*40)
                
                try:
                    final_song = concatenate_songs(audio_result)
                    if final_song:
                        # Save concatenated audio for testing
                        concat_path = os.path.join(test_audio_folder, "concatenated_test.mp3")
                        final_song.write_audiofile(concat_path, logger=None)
                        concat_size_mb = os.path.getsize(concat_path) / (1024 * 1024)
                        
                        print(f"\nConcatenation successful")
                        print(f"  Output file: concatenated_test.mp3")
                        print(f"  Duration: {final_song.duration:.2f} seconds")
                        print(f"  Size: {concat_size_mb:.2f} MB")
                        
                        # Clean up MoviePy object
                        final_song.close()
                    else:
                        print("\nConcatenation failed")
                except Exception as e:
                    print(f"\nConcatenation error: {e}")
            
            # Test audio playback capability
            print("\n" + "-"*40)
            print("Testing audio file integrity...")
            print("-"*40)
            
            for i, (file_path, _) in enumerate(audio_result, 1):
                try:
                    audio_clip = AudioFileClip(file_path)
                    print(f"\nFile {i} is valid and can be loaded by MoviePy")
                    print(f"    Sample rate: {audio_clip.fps} Hz")
                    print(f"    Channels: {audio_clip.nchannels}")
                    audio_clip.close()
                except Exception as e:
                    print(f"\nFile {i} failed integrity check: {e}")
            
            print("\n" + "="*60)
            print(" Audio Test Complete - SUCCESS")
            print("="*60)
            print(f"\nTest files saved in: {test_audio_folder}")
            print("\nYou can manually review the downloaded audio files.")
            
            if debug:
                print("\nDebug files saved in: pixabay_debug/")
            
            return True
            
        else:
            print("\nFailed to download any audio files")
            print("\nPossible issues:")
            print("  1. Network connectivity problems")
            print("  2. Pixabay API rate limiting")
            print("  3. Changes to Pixabay website structure")
            
            if debug:
                print("\nCheck pixabay_debug/ folder for HTML/JSON responses")
            
            print("\n" + "="*60)
            print(" Audio Test Complete - FAILED")
            print("="*60)
            
            return False
            
    except Exception as e:
        print(f"\nAudio test failed with error: {e}")
        import traceback
        traceback.print_exc()
        
        print("\n" + "="*60)
        print(" Audio Test Complete - ERROR")
        print("="*60)
        
        return False

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

def main_sequence(run_images_folder, video_path, run_audio_folder, run_valid_images_file, time_offset=0, debug=False, use_cache=False):
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
        tts_intro_path = None
        audio_source = "NONE"  # Track audio source: PIXABAY, CACHED, TTS, or NONE

        try:
            # If --cache flag is set, try cached audio first
            if use_cache:
                message_processor("Using cached audio (--cache flag set)...", "info")
                from lib.timelapse_core import get_cached_audio
                from lib.timelapse_config import AUDIO_CACHE_FOLDER
                cache_folder = config.get('files_and_folders', {}).get('AUDIO_CACHE_FOLDER', AUDIO_CACHE_FOLDER)
                cached_audio_path, cached_duration_ms = get_cached_audio(
                    cache_folder,
                    min_duration_sec=duration_threshold / 1000
                )
                if cached_audio_path and cached_duration_ms:
                    cached_duration_sec = cached_duration_ms / 1000
                    audio_result = [(cached_audio_path, cached_duration_sec)]
                    audio_metrics = {'duration_seconds': 0, 'memory_change_mb': 0}
                    message_processor(f"Using cached audio ({cached_duration_sec:.1f}s)", "info")
                else:
                    message_processor("No suitable cached audio found, falling back to download...", "warning")
                    audio_result, audio_metrics = monitor_resource_usage(
                        audio_download,
                        duration_threshold,
                        run_audio_folder,
                        debug,
                        config
                    )
            else:
                message_processor("Attempting to download audio from Pixabay...", "info")
                audio_result, audio_metrics = monitor_resource_usage(
                    audio_download,
                    duration_threshold,
                    run_audio_folder,
                    debug,
                    config
                )

            if audio_result:
                # Prepare final audio - distribute songs evenly across video
                video_duration_sec = duration_threshold / 1000
                message_processor(f"Distributing {len(audio_result)} audio track(s) across {video_duration_sec:.1f}s video")

                # Use distribute_songs_evenly for smooth, even audio distribution
                final_song = distribute_songs_evenly(
                    audio_result,
                    video_duration_sec,
                    crossfade_seconds=5,
                    fadeout_seconds=3
                )

                # Determine audio source for logging
                if isinstance(audio_result[0], tuple) and len(audio_result[0]) > 0:
                    song_path = audio_result[0][0]
                    if 'cached_' in os.path.basename(song_path):
                        audio_source = "CACHED"
                    else:
                        audio_source = "PIXABAY"
                else:
                    audio_source = "PIXABAY"

                # Add TTS intro if enabled
                from lib.timelapse_config import TTS_INTRO_ENABLED, TTS_INTRO_RATE, TTS_INTRO_VOLUME
                if TTS_INTRO_ENABLED:
                    # Get TTS text from project description
                    project_description = config.get('project', {}).get('description', '')
                    if project_description:
                        tts_text = f"{project_description} for {{date}}"
                    else:
                        message_processor("Project description is empty - skipping TTS intro", "warning")
                        tts_text = None

                    if tts_text:
                        tts_output = os.path.join(run_audio_folder, "tts_intro.mp3")
                        tts_result, tts_duration = create_tts_intro(
                            tts_text,
                            tts_output,
                            rate=TTS_INTRO_RATE,
                            volume=TTS_INTRO_VOLUME
                        )
                        if tts_result:
                            tts_intro_path = tts_result
                            message_processor("TTS intro will be added to video", "info")
            else:
                message_processor("Audio download failed. Proceeding without audio.", "warning", ntfy=True)
                audio_source = "NONE"
        except Exception as e:
            message_processor(f"Audio download error: {e}. Proceeding without audio.", "warning", ntfy=True)
            final_song = None
            audio_source = "NONE"
        
        # Create time-lapse video
        message_processor("Creating Time-Lapse Video")

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

                # Sync audio and video - must loop BEFORE combining with TTS
                # because CompositeAudioClip (from TTS+music) doesn't support looping
                if audio_clip.duration < video_clip.duration:
                    message_processor("Looping audio to match video length")
                    audio_clip = audio_loop(audio_clip, duration=video_clip.duration)
                else:
                    audio_clip = audio_clip.subclip(0, video_clip.duration)

                # Add TTS intro if we have one (after looping/trimming music)
                if tts_intro_path:
                    message_processor("Combining TTS intro with music")
                    audio_clip = combine_tts_with_music(tts_intro_path, audio_clip)

                # Apply audio effects
                audio_clip = audio_clip.audio_fadein(3).audio_fadeout(3)
                video_clip = video_clip.set_audio(audio_clip)
            else:
                message_processor("Creating video without audio", "warning")

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

            # Rename file if no audio was added
            if audio_source == "NONE" and os.path.exists(video_path):
                # Insert .NO_AUDIO before the extension
                base_name = os.path.basename(video_path)
                name_without_ext = os.path.splitext(base_name)[0]
                ext = os.path.splitext(base_name)[1]
                new_name = f"{name_without_ext}.NO_AUDIO{ext}"
                new_path = os.path.join(os.path.dirname(video_path), new_name)

                os.rename(video_path, new_path)
                video_path = new_path  # Update video_path for subsequent logging
                message_processor(f"Video renamed to indicate NO AUDIO: {new_name}", "warning", ntfy=True)

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
    parser.add_argument("project", nargs='?', default=None,
                       help="Project name (uses configs/<project>.json). If not provided, runs setup.")
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
    parser.add_argument("--test-audio", action="store_true",
                       help="Test audio download functionality without capturing images")
    parser.add_argument("--audio-duration", type=int, default=60,
                       help="Duration in seconds for audio test (default: 60)")
    parser.add_argument("--test-network", action="store_true",
                       help="Include network connectivity tests in audio test mode")
    parser.add_argument("--user-agent", type=str, default=None,
                       help="Override user agent for testing (use 'curl' for curl UA, 'chrome' for Chrome, etc.)")
    parser.add_argument("--cache", action="store_true",
                       help="Use cached audio instead of downloading (for testing)")
    parser.add_argument("--test-compile", action="store_true",
                       help="Generate test images and compile video (tests full pipeline without image downloads)")
    args = parser.parse_args()
    
    # ===== AUTO-SETUP WHEN NO PROJECT OR CONFIG MISSING =====
    # If no project specified, run setup
    if args.project is None:
        print("\n" + "="*60)
        print(" HourGlass - No Project Specified")
        print("="*60)
        
        # Check if stdin is interactive
        if sys.stdin.isatty():
            print("\nStarting setup wizard...")
            
            # Import and run setup
            try:
                from lib.timelapse_setup import main as setup_main
                setup_main()
                print("\nSetup complete. Please run HourGlass again with your project name.")
                sys.exit(0)
            except (KeyboardInterrupt, EOFError):
                print("\n\nSetup cancelled by user.")
                sys.exit(1)
            except Exception as e:
                print(f"\nError running setup: {e}")
                print("Please run: python timelapse_setup.py")
                sys.exit(1)
        else:
            # Non-interactive mode
            print("\nNo project specified. Available options:")
            print("  python main.py <project_name>    # Run existing project")
            print("  python timelapse_setup.py         # Create new project")
            
            # Check for existing configs
            config_dir = Path("configs")
            if config_dir.exists():
                configs = list(config_dir.glob("*.json"))
                if configs:
                    print("\nExisting projects:")
                    for config_file in configs:
                        print(f"  - {config_file.stem}")
            sys.exit(1)
    
    # ===== CONFIGURATION AND VALIDATION =====
    config_path = f"configs/{args.project}.json"
    
    # Check if config exists
    if not os.path.exists(config_path):
        print("\n" + "="*60)
        print(f" HourGlass - Project '{args.project}' Not Found")
        print("="*60)
        print(f"\nConfiguration file not found: {config_path}")
        
        # Check if stdin is interactive (terminal) or not (piped/redirected)
        if sys.stdin.isatty():
            print("Starting setup wizard for new project...")
            
            # Import and run setup for this specific project
            try:
                from lib.timelapse_setup import create_initial_config, save_config, create_instructions_file
                
                # Create new config for this project
                config = create_initial_config(project_name=args.project)
                
                if config:
                    # Save the configuration
                    if save_config(config, args.project):
                        create_instructions_file(config, args.project)
                        print("\n" + "="*60)
                        print(f" Project '{args.project}' setup complete!")
                        print("="*60)
                        print(f"\nYou can now run: python main.py {args.project}")
                        sys.exit(0)
                    else:
                        print("\nFailed to save configuration.")
                        sys.exit(1)
                else:
                    print("\nSetup cancelled.")
                    sys.exit(1)
            except (KeyboardInterrupt, EOFError):
                print("\n\nSetup cancelled by user.")
                sys.exit(1)
            except Exception as e:
                print(f"\nError running setup: {e}")
                print("Please run: python timelapse_setup.py")
                sys.exit(1)
        else:
            # Non-interactive mode - just show instructions
            print("\nTo create a new project, run interactively:")
            print(f"  python main.py {args.project}")
            print("\nOr use the setup wizard:")
            print("  python timelapse_setup.py")
            sys.exit(1)
    
    # Import dependencies and load config
    config = import_dependencies(config_path)
    if not config:
        print(f"Failed to load configuration from {config_path}. Exiting.")
        sys.exit(1)
    
    # Check if the existing configuration needs setup
    needs_setup, missing_fields = check_config_needs_setup(config)
    if needs_setup:
        print("\n" + "="*60)
        print(" Configuration Error")
        print("="*60)
        print("\nThe configuration is missing critical values:")
        for field in missing_fields:
            print(f"  - {field}")
        print(f"\nPlease run: python timelapse_setup.py")
        print(f"Then select option to update project: {args.project}")
        sys.exit(1)
    
    time_offset = 0
    if "sun" in config and "TIME_OFFSET_HOURS" in config["sun"]:
        time_offset = config["sun"]["TIME_OFFSET_HOURS"]

    # Validate configuration
    if not validate_config_quick(config_path):
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

    # Handle audio test mode
    if args.test_audio:
        message_processor(f"Audio test mode for project: {args.project}", "info")
        test_result = test_audio_download(
            config,
            args.audio_duration,
            args.debug,
            args.test_network,
            args.user_agent
        )
        sys.exit(0 if test_result else 1)

    # Handle test-compile mode: generate test images and compile video
    if args.test_compile:
        message_processor(f"Test compile mode for project: {args.project}", "info", ntfy=True)

        try:
            # Import image_dup functions
            from lib.image_dup import generate_images, get_or_create_run_id as get_test_run_id

            # Generate a unique run_id for this test
            test_run_id = get_test_run_id()
            message_processor(f"Test Run ID: {test_run_id}", "info")

            # Generate test images using image_dup defaults (10fps * 120s = 1200 images)
            message_processor("Generating test images...", "info")
            generate_images(
                fps=config.get('video', {}).get('fps', 10),
                duration=120,  # 2 minute video worth of images
                interval=15,   # 15 second intervals (simulated time)
                source_filename="base_image.jpg",
                run_id=test_run_id,
                config=config
            )

            # Set up paths for the test run
            test_images_folder = os.path.join(IMAGES_FOLDER, test_run_id)
            test_valid_images_file = os.path.join(test_images_folder, VALID_IMAGES_FILE)
            test_audio_folder = os.path.join(AUDIO_FOLDER, test_run_id)
            os.makedirs(test_audio_folder, exist_ok=True)

            # Generate video filename with test prefix
            test_video_filename = f"TEST_{datetime.now().strftime(VIDEO_FILENAME_FORMAT)}"
            test_video_path = os.path.join(VIDEO_FOLDER, test_video_filename)

            message_processor(f"Test images folder: {test_images_folder}", "info")
            message_processor(f"Test video output: {test_video_path}", "info")

            # Run the full compilation pipeline
            main_sequence(
                test_images_folder,
                test_video_path,
                test_audio_folder,
                test_valid_images_file,
                time_offset,
                args.debug,
                args.cache
            )

            message_processor("Test compile completed successfully!", "info", ntfy=True)

        except Exception as e:
            message_processor(f"Test compile failed: {e}", "error", ntfy=True)
            import traceback
            traceback.print_exc()
            sys.exit(1)
        finally:
            if health_monitor:
                health_monitor.stop_monitoring()

        sys.exit(0)

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
        validator = ConfigValidator(config_path)
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
    run_id = get_or_create_run_id(time_offset, IMAGES_FOLDER)
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
        
        main_sequence(run_images_folder, video_path, run_audio_folder, run_valid_images_file, time_offset, args.debug, args.cache)
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
            soup = sun_schedule(SUN_URL, USER_AGENTS)

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
            time_offset=time_offset,
            config_path=config_path  # Pass the config file path
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
                main_sequence(run_images_folder, video_path, run_audio_folder, run_valid_images_file, time_offset, args.debug, args.cache)
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
            main_sequence(run_images_folder, video_path, run_audio_folder, run_valid_images_file, time_offset, args.debug, args.cache)
        except Exception as e:
            message_processor(f"Error processing images to video: {e}", "error")
            try:
                # Fallback attempt
                main_sequence(run_images_folder, video_path, run_audio_folder, run_valid_images_file, time_offset, args.debug, args.cache)
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