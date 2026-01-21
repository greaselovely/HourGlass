# audio.py
"""
Audio functionality: song downloading, caching, TTS, and audio processing.
"""
import os
import re
import json
import shutil
import cloudscraper
import requests
from time import sleep
from pathlib import Path
from random import choice
from datetime import datetime, timedelta
from moviepy.editor import AudioFileClip, concatenate_audioclips
from moviepy.audio.fx.all import audio_loop

from .utils import message_processor, check_socks_proxy


# ============================================================================
# Song History Tracking - Prevents song reuse within 180 days
# ============================================================================

SONG_HISTORY_RETENTION_DAYS = 180


def load_song_history(history_file: str | Path) -> dict:
    """
    Loads song history from JSON file, auto-cleaning entries older than 180 days.

    Args:
        history_file: Path to the song_history.json file

    Returns:
        dict: Song history with structure:
            {
                "songs": {
                    "<source_url>": {
                        "name": str,
                        "duration_sec": float,
                        "source_url": str,
                        "first_used": str (ISO datetime),
                        "last_used": str (ISO datetime),
                        "usage_count": int
                    }
                },
                "metadata": {
                    "last_cleanup": str (ISO datetime),
                    "version": str
                }
            }
    """
    history_file = Path(history_file)

    # Default empty history
    default_history = {
        "songs": {},
        "metadata": {
            "last_cleanup": datetime.now().isoformat(),
            "version": "1.0"
        }
    }

    if not history_file.exists():
        message_processor("Song history file not found, starting fresh", "info")
        return default_history

    try:
        with open(history_file, 'r', encoding='utf-8') as f:
            history = json.load(f)

        # Validate structure
        if "songs" not in history:
            history["songs"] = {}
        if "metadata" not in history:
            history["metadata"] = default_history["metadata"]

        # Auto-cleanup old entries
        history = cleanup_song_history(history)

        message_processor(f"Loaded song history: {len(history['songs'])} songs tracked", "info")
        return history

    except (json.JSONDecodeError, IOError) as e:
        message_processor(f"Error loading song history, starting fresh: {e}", "warning")
        return default_history


def save_song_history(history: dict, history_file: str | Path) -> bool:
    """
    Saves song history to JSON file.

    Args:
        history: The song history dictionary
        history_file: Path to save the JSON file

    Returns:
        bool: True if saved successfully, False otherwise
    """
    history_file = Path(history_file)

    try:
        # Ensure parent directory exists
        history_file.parent.mkdir(parents=True, exist_ok=True)

        with open(history_file, 'w', encoding='utf-8') as f:
            json.dump(history, f, indent=2, ensure_ascii=False)

        return True

    except IOError as e:
        message_processor(f"Error saving song history: {e}", "error")
        return False


def cleanup_song_history(history: dict) -> dict:
    """
    Removes songs older than SONG_HISTORY_RETENTION_DAYS from history.

    Args:
        history: The song history dictionary

    Returns:
        dict: Cleaned history
    """
    cutoff_date = datetime.now() - timedelta(days=SONG_HISTORY_RETENTION_DAYS)
    songs_to_remove = []

    for source_url, song_data in history.get("songs", {}).items():
        try:
            last_used = datetime.fromisoformat(song_data.get("last_used", ""))
            if last_used < cutoff_date:
                songs_to_remove.append(source_url)
        except (ValueError, TypeError):
            # Invalid date format, keep the entry
            continue

    for url in songs_to_remove:
        del history["songs"][url]

    if songs_to_remove:
        message_processor(f"Cleaned up {len(songs_to_remove)} expired songs from history", "info")

    history["metadata"]["last_cleanup"] = datetime.now().isoformat()
    return history


def add_song_to_history(history: dict, source_url: str, song_name: str, duration_sec: float) -> dict:
    """
    Adds or updates a song in the history.

    Args:
        history: The song history dictionary
        source_url: Unique URL identifier for the song
        song_name: Human-readable song name
        duration_sec: Duration in seconds

    Returns:
        dict: Updated history
    """
    now = datetime.now().isoformat()

    if source_url in history["songs"]:
        # Update existing entry
        history["songs"][source_url]["last_used"] = now
        history["songs"][source_url]["usage_count"] += 1
        message_processor(
            f"Song used again: {song_name[:30]}... (count: {history['songs'][source_url]['usage_count']})",
            "info"
        )
    else:
        # New entry
        history["songs"][source_url] = {
            "name": song_name,
            "duration_sec": duration_sec,
            "source_url": source_url,
            "first_used": now,
            "last_used": now,
            "usage_count": 1
        }
        message_processor(f"New song added to history: {song_name[:30]}...", "info")

    return history


def is_song_in_history(history: dict, source_url: str) -> bool:
    """
    Checks if a song URL exists in the history (used within retention period).

    Args:
        history: The song history dictionary
        source_url: URL to check

    Returns:
        bool: True if song is in history and should be skipped
    """
    return source_url in history.get("songs", {})


def get_song_usage_count(history: dict, source_url: str) -> int:
    """
    Gets the usage count for a song.

    Args:
        history: The song history dictionary
        source_url: URL to look up

    Returns:
        int: Usage count, or 0 if not found
    """
    return history.get("songs", {}).get(source_url, {}).get("usage_count", 0)


def get_cached_file_usage_count(history: dict, cached_filename: str) -> int:
    """
    Gets usage count for a cached file by matching the song name in the filename.

    Cached files have format: cached_{timestamp}_{song_name}.mp3
    We match by checking if any song name is contained in the filename.

    Args:
        history: The song history dictionary
        cached_filename: The cached file's name (not full path)

    Returns:
        int: Usage count, or 0 if no match found
    """
    # Extract the song name part from cached filename
    # Format: cached_YYYYMMDD_HHMMSS_songname.mp3
    for song_data in history.get("songs", {}).values():
        song_name = song_data.get("name", "")
        # Sanitize song name the same way it's done when caching
        safe_name = re.sub(r'[^\w\s-]', '', song_name)[:50]
        if safe_name and safe_name.lower() in cached_filename.lower():
            return song_data.get("usage_count", 0)

    return 0


def manage_audio_cache(cache_folder, max_files):
    """
    Manages the audio cache folder using FIFO (First In, First Out) strategy.
    Ensures the cache doesn't exceed max_files by removing oldest files.

    Args:
        cache_folder (str or Path): Path to the audio cache folder
        max_files (int): Maximum number of files to keep in cache

    Returns:
        int: Number of files removed
    """
    cache_folder = Path(cache_folder)

    # Create cache folder if it doesn't exist
    cache_folder.mkdir(parents=True, exist_ok=True)

    # Get all audio files sorted by modification time (oldest first)
    audio_files = sorted(
        cache_folder.glob('*.mp3'),
        key=lambda x: x.stat().st_mtime
    )

    # Calculate how many files to remove
    files_to_remove = len(audio_files) - max_files

    if files_to_remove <= 0:
        return 0

    # Remove oldest files
    removed_count = 0
    for audio_file in audio_files[:files_to_remove]:
        try:
            audio_file.unlink()
            removed_count += 1
            message_processor(f"Removed old cached audio: {audio_file.name}", "info")
        except Exception as e:
            message_processor(f"Failed to remove cached audio {audio_file.name}: {e}", "error")

    return removed_count


def add_to_audio_cache(audio_path, cache_folder, max_files):
    """
    Adds a downloaded audio file to the cache and manages cache size.

    Args:
        audio_path (str or Path): Path to the audio file to cache
        cache_folder (str or Path): Path to the audio cache folder
        max_files (int): Maximum number of files to keep in cache

    Returns:
        Path: Path to the cached file, or None if caching failed
    """
    try:
        cache_folder = Path(cache_folder)
        audio_path = Path(audio_path)

        # Create cache folder if it doesn't exist
        cache_folder.mkdir(parents=True, exist_ok=True)

        # Generate cache filename with timestamp to avoid collisions
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        cache_filename = f"cached_{timestamp}_{audio_path.name}"
        cache_path = cache_folder / cache_filename

        # Copy file to cache
        shutil.copy2(audio_path, cache_path)
        message_processor(f"Added to cache: {cache_filename}", "info")

        # Manage cache size
        manage_audio_cache(cache_folder, max_files)

        return cache_path

    except Exception as e:
        message_processor(f"Failed to add audio to cache: {e}", "error")
        return None


def get_cached_audio(cache_folder: str | Path, min_duration_sec: float | None = None,
                     target_duration_sec: float | None = None, multiple: bool = False,
                     song_history: dict | None = None, min_files: int = 1):
    """
    Retrieves audio file(s) from the cache.

    When song_history is provided, files are sorted by lowest usage count (least used first).
    This ensures variety when falling back to cached audio.

    Args:
        cache_folder (str or Path): Path to the audio cache folder
        min_duration_sec (float, optional): Minimum duration for single file selection
        target_duration_sec (float, optional): Target total duration for multiple file selection
        multiple (bool): If True, returns list of multiple files to meet target_duration_sec.
                        If False, returns single file meeting min_duration_sec.
        song_history (dict, optional): Song history for sorting by usage count.
        min_files (int): Minimum number of files to return when multiple=True. Default 1.

    Returns:
        If multiple=False: tuple (audio_path, duration_ms) or (None, None) if no suitable file found
        If multiple=True: list of tuples [(audio_path, duration_sec), ...] or empty list
    """
    try:
        cache_folder = Path(cache_folder)

        if not cache_folder.exists():
            message_processor("Audio cache folder does not exist", "warning")
            return [] if multiple else (None, None)

        # Get all cached audio files
        cached_files = list(cache_folder.glob('*.mp3'))

        if not cached_files:
            message_processor("Audio cache is empty", "warning", ntfy=True)
            return [] if multiple else (None, None)

        # Get durations for all valid files
        available_files = []

        for cached_file in cached_files:
            try:
                with AudioFileClip(str(cached_file)) as audio_clip:
                    duration_sec = audio_clip.duration
                available_files.append((cached_file, duration_sec))
            except Exception as e:
                message_processor(f"Error verifying cached audio {cached_file.name}: {e}", "error")
                # Remove corrupted file
                try:
                    cached_file.unlink()
                    message_processor(f"Removed corrupted cached audio: {cached_file.name}", "info")
                except:
                    pass
                continue

        if not available_files:
            message_processor("No valid cached audio files found", "warning")
            return [] if multiple else (None, None)

        # Multiple file selection mode
        if multiple:
            target = target_duration_sec if target_duration_sec else 0

            # Select files until we meet the target duration
            selected_songs = []
            total_duration = 0

            # Sort by usage count (lowest first) if history is available
            # This ensures least-used songs are selected first
            if song_history and song_history.get("songs"):
                # Add usage count to each file for sorting
                files_with_counts = []
                for cached_file, duration_sec in available_files:
                    usage_count = get_cached_file_usage_count(song_history, cached_file.name)
                    files_with_counts.append((cached_file, duration_sec, usage_count))

                # Sort by usage count (ascending), then shuffle within same count for variety
                files_with_counts.sort(key=lambda x: x[2])

                message_processor(
                    f"Sorted {len(files_with_counts)} cached files by usage count (lowest first)",
                    "info"
                )

                available_files_sorted = [(f, d) for f, d, _ in files_with_counts]
            else:
                # No history available - shuffle randomly as fallback
                from random import shuffle
                available_files_sorted = available_files.copy()
                shuffle(available_files_sorted)

            for cached_file, duration_sec in available_files_sorted:
                selected_songs.append((str(cached_file), duration_sec))
                total_duration += duration_sec

                # Need both enough duration AND minimum number of files
                if total_duration >= target and len(selected_songs) >= min_files:
                    break

            if total_duration < target or len(selected_songs) < min_files:
                message_processor(
                    f"Cache exhausted: got {total_duration:.1f}s from {len(selected_songs)} files, "
                    f"needed {target:.1f}s",
                    "warning"
                )
                # Return what we have anyway
            else:
                message_processor(
                    f"Selected {len(selected_songs)} cached audio files ({total_duration:.1f}s total)",
                    "info"
                )

            return selected_songs

        # Single file selection mode
        else:
            # Filter by minimum duration if specified
            suitable_files = []
            for cached_file, duration_sec in available_files:
                if min_duration_sec and duration_sec < min_duration_sec:
                    continue  # Skip files that are too short
                suitable_files.append((cached_file, duration_sec))

            if not suitable_files:
                message_processor(
                    f"No cached audio file meets minimum duration ({min_duration_sec:.1f}s)",
                    "warning"
                )
                return None, None

            # Select file with lowest usage count if history available
            if song_history and song_history.get("songs"):
                files_with_counts = []
                for cached_file, duration_sec in suitable_files:
                    usage_count = get_cached_file_usage_count(song_history, cached_file.name)
                    files_with_counts.append((cached_file, duration_sec, usage_count))

                # Sort by usage count and pick the lowest
                files_with_counts.sort(key=lambda x: x[2])
                selected_file, duration_sec, usage_count = files_with_counts[0]
                message_processor(
                    f"Selected least-used cached audio: {selected_file.name} ({duration_sec:.1f}s, "
                    f"used {usage_count} times) from {len(suitable_files)} suitable files",
                    "info"
                )
            else:
                # Randomly select from suitable files if no history
                selected_file, duration_sec = choice(suitable_files)
                message_processor(
                    f"Randomly selected cached audio: {selected_file.name} ({duration_sec:.1f}s) "
                    f"from {len(suitable_files)} suitable files",
                    "info"
                )
            return str(selected_file), duration_sec * 1000  # Return duration in milliseconds

    except Exception as e:
        message_processor(f"Error retrieving cached audio: {e}", "error")
        return [] if multiple else (None, None)


def get_cache_stats(cache_folder):
    """
    Get statistics about the audio cache.

    Args:
        cache_folder (str or Path): Path to the audio cache folder

    Returns:
        dict: Cache statistics (count, total_size_mb, oldest_date, newest_date)
    """
    try:
        cache_folder = Path(cache_folder)

        if not cache_folder.exists():
            return {'count': 0, 'total_size_mb': 0, 'oldest_date': None, 'newest_date': None}

        cached_files = list(cache_folder.glob('*.mp3'))

        if not cached_files:
            return {'count': 0, 'total_size_mb': 0, 'oldest_date': None, 'newest_date': None}

        total_size = sum(f.stat().st_size for f in cached_files)
        oldest = min(cached_files, key=lambda x: x.stat().st_mtime)
        newest = max(cached_files, key=lambda x: x.stat().st_mtime)

        return {
            'count': len(cached_files),
            'total_size_mb': total_size / (1024 * 1024),
            'oldest_date': datetime.fromtimestamp(oldest.stat().st_mtime),
            'newest_date': datetime.fromtimestamp(newest.stat().st_mtime)
        }

    except Exception as e:
        message_processor(f"Error getting cache stats: {e}", "error")
        return {'count': 0, 'total_size_mb': 0, 'oldest_date': None, 'newest_date': None}


def single_song_download(AUDIO_FOLDER, max_attempts=3, debug=False, config=None, song_history=None):
    """
    Downloads a random song from Pixabay and tests its usability.

    This function attempts to download a song up to 'max_attempts' times,
    testing each download to ensure it can be used by MoviePy.

    Songs that have been used within the last 180 days (tracked in song_history)
    are automatically skipped to ensure variety.

    Parameters:
    - AUDIO_FOLDER (str): Path to the folder where audio files will be saved.
    - max_attempts (int): Maximum number of download attempts. Defaults to 3.
    - debug (bool): If True, save HTML/JSON responses for debugging.
    - config (dict): Configuration dictionary with proxy and music settings.
    - song_history (dict): Song history dictionary for tracking used songs.
                          If provided, songs already in history will be skipped.

    Returns:
    - tuple: A tuple containing (path, duration_ms, source_url) for the downloaded file,
             or (None, None, None) if all attempts fail.

    Note:
    The function prints messages to the console indicating the status of each download
    and any errors encountered.
    """
    if song_history is None:
        song_history = {"songs": {}}
    # Create temp folder for debugging HTML responses if debug mode is enabled
    if debug:
        temp_folder = Path("pixabay_debug")
        temp_folder.mkdir(exist_ok=True)

    for attempt in range(max_attempts):
        try:
            # Add delay between attempts to avoid rate limiting
            if attempt > 0:
                delay = 10 + attempt * 5  # Progressive delay: 15s, 20s
                message_processor(f"Waiting {delay} seconds before retry...", "info")
                sleep(delay)

            # Use cloudscraper to bypass Cloudflare
            # It handles user agents and headers automatically
            session = cloudscraper.create_scraper(
                browser={
                    'browser': 'chrome',
                    'platform': 'darwin',
                    'desktop': True
                }
            )

            # Configure SOCKS proxy if available in config
            if config and 'proxies' in config:
                socks5 = config['proxies'].get('socks5', '')
                socks5_hostname = config['proxies'].get('socks5_hostname', '')

                # Use socks5_hostname if available (for DNS resolution through proxy)
                # Format: socks5h://hostname:port or socks5://hostname:port
                if socks5_hostname:
                    proxy_url = f"socks5h://{socks5_hostname}"
                    session.proxies = {
                        'http': proxy_url,
                        'https': proxy_url
                    }
                    message_processor(f"Using SOCKS5 proxy (with hostname resolution): {socks5_hostname}", "info")
                elif socks5:
                    proxy_url = f"socks5://{socks5}"
                    session.proxies = {
                        'http': proxy_url,
                        'https': proxy_url
                    }
                    message_processor(f"Using SOCKS5 proxy: {socks5}", "info")
                # Also check for regular HTTP/HTTPS proxies
                elif config['proxies'].get('http') or config['proxies'].get('https'):
                    session.proxies = {}
                    if config['proxies'].get('http'):
                        session.proxies['http'] = config['proxies']['http']
                    if config['proxies'].get('https'):
                        session.proxies['https'] = config['proxies']['https']
                    message_processor("Using HTTP/HTTPS proxy", "info")

            # Step 1: Get page 1 HTML to extract bootstrap URL and total pages
            # Get base URL and search term from config if available
            if config and 'music' in config:
                base_url = config['music'].get('pixabay_base_url', 'https://pixabay.com/music/search/')
                search_terms = config['music'].get('search_terms', ['no copyright music'])
                search_term = search_terms[0] if search_terms else 'no copyright music'
            else:
                base_url = 'https://pixabay.com/music/search/'
                search_term = 'no copyright music'

            page1_url = f"{base_url.rstrip('/')}/{search_term.replace(' ', '%20')}/"

            message_processor(f"Fetching Pixabay music catalog for '{search_term}' (attempt {attempt + 1})", "info")
            message_processor(f"URL: {page1_url}", "info")
            r = session.get(page1_url)

            # Save HTML response for debugging if enabled
            if debug:
                html_file = temp_folder / f"page1_attempt{attempt + 1}_{r.status_code}.html"
                # r.text should handle decompression automatically
                with open(html_file, 'w', encoding='utf-8') as f:
                    f.write(r.text)
                message_processor(f"Saved HTML to: {html_file}", "info")

            r.raise_for_status()

            # Extract the bootstrap URL from the HTML
            html_content = r.text
            bootstrap_match = re.search(r"window\.__BOOTSTRAP_URL__\s*=\s*'([^']+)'", html_content)

            if not bootstrap_match:
                message_processor("Could not find bootstrap URL in HTML", "error")
                continue

            bootstrap_path = bootstrap_match.group(1)
            bootstrap_url = f"https://pixabay.com{bootstrap_path}"

            # Step 2: Fetch the bootstrap JSON to get total pages
            message_processor("Fetching catalog metadata", "info")
            message_processor(f"URL: {bootstrap_url}", "info")
            sleep(10)  # 10 second delay between requests
            r = session.get(bootstrap_url)

            # Save JSON response for debugging if enabled
            if debug:
                json_file = temp_folder / f"bootstrap_page1_attempt{attempt + 1}_{r.status_code}.json"
                with open(json_file, 'w', encoding='utf-8') as f:
                    f.write(r.text)
                message_processor(f"Saved JSON to: {json_file}", "info")

            r.raise_for_status()

            initial_data = r.json()
            total_pages = initial_data.get('page', {}).get('pages', 1)
            message_processor(f"Found {total_pages} pages of music available", "info")

            # Step 3: Select a random page
            selected_page = choice(range(1, min(total_pages + 1, 1000)))  # Cap at 1000 for safety

            # Step 4: If not page 1, fetch the selected page
            if selected_page > 1:
                page_url = f"{base_url.rstrip('/')}/{search_term.replace(' ', '%20')}/?pagi={selected_page}"
                message_processor(f"Fetching page {selected_page} of {total_pages}", "info")
                message_processor(f"URL: {page_url}", "info")

                sleep(10)  # 10 second delay between requests
                r = session.get(page_url)

                # Save HTML response for debugging if enabled
                if debug:
                    html_file = temp_folder / f"page{selected_page}_attempt{attempt + 1}_{r.status_code}.html"
                    with open(html_file, 'w', encoding='utf-8') as f:
                        f.write(r.text)
                    message_processor(f"Saved HTML to: {html_file}", "info")

                r.raise_for_status()

                # Extract bootstrap URL from this page
                html_content = r.text
                bootstrap_match = re.search(r"window\.__BOOTSTRAP_URL__\s*=\s*'([^']+)'", html_content)

                if bootstrap_match:
                    bootstrap_path = bootstrap_match.group(1)
                    bootstrap_url = f"https://pixabay.com{bootstrap_path}"

                    # Fetch the bootstrap JSON for this page
                    message_processor(f"Fetching page {selected_page} bootstrap data", "info")
                    message_processor(f"URL: {bootstrap_url}", "info")
                    sleep(10)  # 10 second delay between requests
                    r = session.get(bootstrap_url)

                    # Save JSON response for debugging if enabled
                    if debug:
                        json_file = temp_folder / f"bootstrap_page{selected_page}_attempt{attempt + 1}_{r.status_code}.json"
                        with open(json_file, 'w', encoding='utf-8') as f:
                            f.write(r.text)
                        message_processor(f"Saved JSON to: {json_file}", "info")

                    r.raise_for_status()
                    page_data = r.json()
                    results = page_data.get('page', {}).get('results', [])
                else:
                    message_processor(f"Could not find bootstrap URL for page {selected_page}, using page 1", "warning")
                    results = initial_data.get('page', {}).get('results', [])
            else:
                results = initial_data.get('page', {}).get('results', [])
                message_processor("Using page 1", "info")

            if not results:
                message_processor("No songs found in response.", "error")
                continue

            # Filter out songs that have been used within retention period
            available_songs = []
            skipped_count = 0
            for song in results:
                song_src = song.get('sources', {}).get('src')
                if song_src and not is_song_in_history(song_history, song_src):
                    available_songs.append(song)
                elif song_src:
                    skipped_count += 1

            if skipped_count > 0:
                message_processor(
                    f"Skipped {skipped_count} previously used songs, {len(available_songs)} available",
                    "info"
                )

            if not available_songs:
                message_processor(
                    f"All {len(results)} songs on this page have been used recently. Trying another page...",
                    "warning"
                )
                continue  # Try another attempt (which will select a different page)

            # Select a random song from available (unused) songs
            song = choice(available_songs)

            # Extract song information
            song_src = song.get('sources', {}).get('src')
            song_duration = song.get('duration', 0)  # Duration in seconds
            song_name = song.get('name', 'Unknown Song')

            if not song_src:
                message_processor("Song source URL not found.", "error")
                continue

            # Extract unique ID from URL for unique filenames
            # URL format: https://cdn.pixabay.com/audio/2025/07/29/audio_2a1b68d9d9.mp3
            url_filename = os.path.basename(song_src).replace('.mp3', '')  # e.g., "audio_2a1b68d9d9"

            message_processor(f"Downloading: {url_filename} ({song_duration}s)", "download")
            message_processor(f"URL: {song_src}", "info")

            # Download the audio file
            sleep(10)  # 10 second delay before downloading
            r = session.get(song_src)
            r.raise_for_status()

            # Use URL filename for unique naming (avoids duplicate "No Copyright Music" names)
            audio_name = f"{url_filename}.mp3"
            full_audio_path = os.path.join(AUDIO_FOLDER, audio_name)

            with open(full_audio_path, 'wb') as f:
                f.write(r.content)

            message_processor(f"Downloaded: {audio_name}", "download")

            # Test the audio file
            try:
                with AudioFileClip(full_audio_path) as audio_clip:
                    # If we can read the duration, the file is likely usable
                    actual_duration = audio_clip.duration
                message_processor(f"Audio file verified. Duration: {actual_duration:.2f} seconds")
                # Return path, duration in ms, and source URL for history tracking
                return full_audio_path, actual_duration * 1000, song_src
            except Exception as e:
                message_processor(f"Error verifying audio file: {e}", "error")
                os.remove(full_audio_path)  # Remove the unusable file
                message_processor(f"Removed unusable file: {audio_name}")
                continue  # Try downloading again

        except requests.HTTPError as e:
            if e.response.status_code == 403:
                message_processor(f"Access forbidden (403). Pixabay may be rate limiting. Retrying...", "warning")
            else:
                message_processor(f"HTTP error occurred:\n[!]\t{e}", "error")
        except requests.RequestException as e:
            message_processor(f"An error occurred during download:\n[!]\t{e}", "error")
        except (KeyError, ValueError) as e:
            message_processor(f"Error parsing response data: {e}", "error")

    message_processor(f"Failed to download a usable audio file after {max_attempts} attempts.", "error")
    return None, None, None


def audio_download(video_duration, AUDIO_FOLDER, debug=False, config=None) -> list:
    """
    Downloads multiple songs with fallback to cached audio, ensuring their total duration covers the video duration.

    Enhanced with:
    - Pre-flight checks for SOCKS proxy and Pixabay connectivity
    - Automatic caching of successfully downloaded songs
    - Fallback to cached audio if Pixabay fails
    - Song history tracking to prevent reuse within 180 days
    - Better error reporting with emojis

    Args:
        video_duration (int): Required total audio duration in milliseconds.
        AUDIO_FOLDER (str or Path): Directory to save the downloaded audio files.
        debug (bool): If True, save HTML/JSON responses for debugging.
        config (dict): Configuration dictionary containing proxy, cache, and music settings.

    Returns:
        list: List of tuples, each containing the path to a downloaded audio file and its duration in seconds.
              Returns None if unsuccessful in downloading sufficient audio and cache is empty.
    """
    from .timelapse_config import AUDIO_CACHE_FOLDER, AUDIO_CACHE_MAX_FILES, SONG_HISTORY_FILE

    songs = []
    total_duration = 0  # total duration in seconds
    attempts = 0
    max_attempts = 10
    pixabay_success = False

    # Get cache settings from config
    cache_folder = config.get('files_and_folders', {}).get('AUDIO_CACHE_FOLDER', AUDIO_CACHE_FOLDER) if config else AUDIO_CACHE_FOLDER
    max_cache_files = config.get('music', {}).get('cache_max_files', AUDIO_CACHE_MAX_FILES) if config else AUDIO_CACHE_MAX_FILES

    # Get song history file path (lives in project folder alongside other data files)
    project_base = config.get('files_and_folders', {}).get('PROJECT_BASE', '') if config else ''
    history_filename = config.get('files_and_folders', {}).get('SONG_HISTORY_FILE', SONG_HISTORY_FILE) if config else SONG_HISTORY_FILE
    history_file = os.path.join(project_base, history_filename) if project_base else history_filename

    # Load song history (auto-cleans entries older than 180 days)
    song_history = load_song_history(history_file)

    message_processor(f"Attempting to download audio for {video_duration/1000:.2f} seconds of video")

    # Display cache stats
    cache_stats = get_cache_stats(cache_folder)
    if cache_stats['count'] > 0:
        message_processor(
            f"Audio cache: {cache_stats['count']} files ({cache_stats['total_size_mb']:.1f}MB)",
            "info"
        )

    # Pre-flight check: SOCKS proxy (if configured)
    if config and 'proxies' in config:
        socks_status = check_socks_proxy(config)
        if not socks_status['reachable']:
            message_processor(
                f"SOCKS proxy check failed - will attempt Pixabay anyway",
                "warning"
            )

    # Minimum number of songs to ensure variety and even distribution
    MIN_SONGS = 2

    # Try downloading from Pixabay
    # Continue until we have enough duration AND at least MIN_SONGS
    while (total_duration < video_duration / 1000 or len(songs) < MIN_SONGS) and attempts < max_attempts:
        song_path, song_duration_ms, song_src = single_song_download(
            AUDIO_FOLDER, debug=debug, config=config, song_history=song_history
        )
        if song_path and song_duration_ms and song_src:
            song_duration_sec = song_duration_ms / 1000
            songs.append((song_path, song_duration_sec))
            total_duration += song_duration_sec
            pixabay_success = True

            # Add to song history and save immediately
            song_name = os.path.basename(song_path).replace('.mp3', '')
            song_history = add_song_to_history(song_history, song_src, song_name, song_duration_sec)
            save_song_history(song_history, history_file)

            # Add successful download to cache
            try:
                add_to_audio_cache(song_path, cache_folder, max_cache_files)
            except Exception as e:
                message_processor(f"Failed to cache audio: {e}", "warning")
        else:
            message_processor(f"Failed to download song on attempt {attempts + 1}/{max_attempts}", "warning")

        attempts += 1

    # Check if we got enough audio from Pixabay (need duration AND minimum songs)
    if total_duration >= video_duration / 1000 and len(songs) >= MIN_SONGS:
        message_processor(f"Successfully downloaded {len(songs)} songs from Pixabay, total: {total_duration:.2f}s", "info")
        return songs

    # Pixabay failed or didn't get enough songs - try cached audio as fallback
    if not pixabay_success or total_duration < video_duration / 1000 or len(songs) < MIN_SONGS:
        message_processor(
            f"Pixabay download failed. Got {total_duration:.2f}s, needed {video_duration/1000:.2f}s",
            "warning",
            ntfy=True
        )
        message_processor("Attempting to use cached audio as fallback...", "info")

        # Try to get multiple cached audio files, sorted by lowest usage count
        # Require at least MIN_SONGS for even distribution
        cached_songs = get_cached_audio(
            cache_folder,
            target_duration_sec=video_duration / 1000,
            multiple=True,
            song_history=song_history,
            min_files=MIN_SONGS
        )

        if cached_songs:
            total_cached_duration = sum(duration for _, duration in cached_songs)
            message_processor(
                f"Using {len(cached_songs)} cached audio file(s) ({total_cached_duration:.1f}s total)",
                "info",
                ntfy=True
            )

            # Update history for cached songs used (increment usage count)
            for cached_path, cached_duration in cached_songs:
                cached_filename = os.path.basename(cached_path)
                # Try to find matching song in history to update count
                for src_url, song_data in song_history.get("songs", {}).items():
                    safe_name = re.sub(r'[^\w\s-]', '', song_data.get("name", ""))[:50]
                    if safe_name and safe_name.lower() in cached_filename.lower():
                        song_history = add_song_to_history(
                            song_history, src_url, song_data.get("name", ""), cached_duration
                        )
                        break
            save_song_history(song_history, history_file)

            return cached_songs
        else:
            message_processor(
                f"No suitable cached audio found. Cache has {cache_stats['count']} files",
                "error",
                ntfy=True
            )
            return None

    message_processor(f"Downloaded {len(songs)} songs, total duration: {total_duration:.2f}s")
    return songs


# ============================================================================
# TTS (Text-to-Speech) Functions
# ============================================================================

def create_tts_intro(
    text: str,
    output_path: str | Path,
    rate: int = 150,
    volume: float = 0.9
) -> tuple[str | None, float | None]:
    """
    Creates a TTS (Text-to-Speech) audio file with random engine and voice.

    Randomly selects between Edge TTS (free) and Google Cloud TTS (if configured).
    Voice is randomly selected from a pool for variety across videos.

    Args:
        text (str): The text to convert to speech. Can include {date} placeholder.
        output_path (str or Path): Path where the TTS audio file will be saved.
        rate (int): Speech rate (words per minute). Default 150.
        volume (float): Volume level (0.0 to 1.0). Default 0.9.

    Returns:
        tuple: (audio_path, duration_seconds) or (None, None) if failed
    """
    # Replace placeholders in text
    today = datetime.now().strftime("%B %d, %Y")  # e.g., "December 19, 2025"
    narration_text = text.replace('{date}', today)

    message_processor(f"Generating TTS intro: \"{narration_text}\"", "info")

    # Save to file
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Randomly choose between Edge and Google TTS, and randomize voices
    import random
    script_dir = Path(__file__).parent.parent
    credentials_path = script_dir / 'tts.json'

    # Voice pools for each engine
    edge_voices = [
        'en-US-AriaNeural',
        'en-US-JennyNeural',
        'en-US-GuyNeural',
        'en-US-ChristopherNeural',
        'en-GB-SoniaNeural',
        'en-GB-RyanNeural',
    ]
    google_voices = [
        'en-US-Neural2-A',  # Male
        'en-US-Neural2-C',  # Female
        'en-US-Neural2-D',  # Male
        'en-US-Neural2-E',  # Female
        'en-US-Neural2-F',  # Female
        'en-US-Neural2-J',  # Male
    ]

    # Check if Google is available (tts.json exists)
    google_available = credentials_path.exists()

    # Pick engine randomly (Edge always available, Google only if configured)
    if google_available:
        use_google = random.choice([True, False])
    else:
        use_google = False

    result = (None, None)

    if use_google:
        voice = random.choice(google_voices)
        result = _create_tts_google(narration_text, output_path, voice, rate)
        if result[0] is None:
            # Google failed, fall back to Edge with retries
            message_processor("Google TTS failed, falling back to Edge TTS", "warning")
            result = _create_tts_with_retry(
                narration_text, output_path, edge_voices, rate, max_retries=3
            )
    else:
        # Try Edge TTS with retries
        result = _create_tts_with_retry(
            narration_text, output_path, edge_voices, rate, max_retries=3
        )
        if result[0] is None and google_available:
            # Edge failed, fall back to Google
            message_processor("Edge TTS failed after retries, falling back to Google TTS", "warning")
            voice = random.choice(google_voices)
            result = _create_tts_google(narration_text, output_path, voice, rate)

    # If all TTS attempts failed, send ntfy alert
    if result[0] is None:
        message_processor(
            "TTS generation failed completely - no voice intro will be added",
            "error",
            ntfy=True
        )

    return result


def _create_tts_with_retry(
    text: str,
    output_path: Path,
    voices: list,
    rate: int,
    max_retries: int = 3,
    retry_delay: float = 2.0
) -> tuple[str | None, float | None]:
    """
    Attempts Edge TTS with retries, trying different voices on failure.

    Args:
        text: Text to synthesize
        output_path: Where to save the audio
        voices: List of voice names to try
        rate: Speech rate (WPM)
        max_retries: Maximum number of retry attempts
        retry_delay: Seconds to wait between retries

    Returns:
        tuple: (audio_path, duration_ms) or (None, None) if all attempts fail
    """
    import time
    import random

    available_voices = voices.copy()
    random.shuffle(available_voices)  # Randomize order for variety

    for attempt in range(max_retries):
        # Pick a different voice for each attempt if possible
        voice = available_voices[attempt % len(available_voices)]

        message_processor(f"TTS attempt {attempt + 1}/{max_retries} with voice: {voice}", "info")

        result = _create_tts_edge(text, output_path, voice, rate)
        if result[0] is not None:
            return result

        if attempt < max_retries - 1:
            message_processor(f"TTS attempt failed, waiting {retry_delay}s before retry...", "warning")
            time.sleep(retry_delay)
            # Increase delay for subsequent retries (exponential backoff)
            retry_delay = min(retry_delay * 1.5, 10.0)

    return (None, None)


def _create_tts_edge(text: str, output_path: Path, voice: str, rate: int) -> tuple[str | None, float | None]:
    """Create TTS using Microsoft Edge TTS (free, no API key)."""
    try:
        import asyncio
        import edge_tts

        # Convert rate (WPM) to edge-tts rate string
        # edge-tts uses percentage: +0% is normal, +50% is faster, -50% is slower
        rate_percent = int((rate - 150) / 150 * 100)
        rate_str = f"{rate_percent:+d}%"

        message_processor(f"Using Edge TTS voice: {voice} (rate: {rate_str})", "info")

        async def generate():
            communicate = edge_tts.Communicate(text, voice, rate=rate_str)
            await communicate.save(str(output_path))

        # Run the async function
        asyncio.run(generate())

        # Verify and get duration
        if output_path.exists():
            try:
                with AudioFileClip(str(output_path)) as audio_clip:
                    duration_sec = audio_clip.duration
                message_processor(f"TTS intro created: {duration_sec:.1f}s", "info")
                return str(output_path), duration_sec * 1000
            except Exception as e:
                message_processor(f"Error verifying TTS file: {e}", "error")
                return None, None
        else:
            message_processor("TTS file was not created", "error")
            return None, None

    except ImportError:
        message_processor("edge-tts not installed. Run: pip install edge-tts", "error")
        return None, None
    except Exception as e:
        message_processor(f"Error creating Edge TTS: {e}", "error")
        return None, None


def _create_tts_google(text: str, output_path: Path, voice: str, rate: int) -> tuple[str | None, float | None]:
    """Create TTS using Google Cloud TTS (requires tts.json credentials)."""
    try:
        import os

        # Check for tts.json credentials file in project root
        script_dir = Path(__file__).parent.parent
        credentials_path = script_dir / 'tts.json'

        if not credentials_path.exists():
            message_processor("Google TTS: tts.json not found. Falling back to Edge TTS.", "warning")
            return _create_tts_edge(text, output_path, 'en-US-AriaNeural', rate)

        os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = str(credentials_path)

        from google.cloud import texttospeech

        message_processor(f"Using Google TTS voice: {voice}", "info")

        client = texttospeech.TextToSpeechClient()
        synthesis_input = texttospeech.SynthesisInput(text=text)

        # Determine gender from voice name
        if 'Female' in voice or voice.endswith(('C', 'E', 'F', 'G', 'H')):
            ssml_gender = texttospeech.SsmlVoiceGender.FEMALE
        else:
            ssml_gender = texttospeech.SsmlVoiceGender.MALE

        # Extract language code from voice name (e.g., 'en-US' from 'en-US-Neural2-F')
        language_code = '-'.join(voice.split('-')[:2]) if '-' in voice else 'en-US'

        voice_params = texttospeech.VoiceSelectionParams(
            language_code=language_code,
            name=voice,
            ssml_gender=ssml_gender
        )

        speaking_rate = rate / 150.0
        audio_config = texttospeech.AudioConfig(
            audio_encoding=texttospeech.AudioEncoding.MP3,
            speaking_rate=speaking_rate
        )

        response = client.synthesize_speech(
            input=synthesis_input,
            voice=voice_params,
            audio_config=audio_config
        )

        with open(output_path, 'wb') as out:
            out.write(response.audio_content)

        if output_path.exists():
            try:
                with AudioFileClip(str(output_path)) as audio_clip:
                    duration_sec = audio_clip.duration
                message_processor(f"TTS intro created: {duration_sec:.1f}s", "info")
                return str(output_path), duration_sec * 1000
            except Exception as e:
                message_processor(f"Error verifying TTS file: {e}", "error")
                return None, None
        else:
            message_processor("TTS file was not created", "error")
            return None, None

    except Exception as e:
        message_processor(f"Error creating Google TTS: {e}", "error")
        return None, None


def combine_tts_with_music(
    tts_audio_path: str,
    music_audio: str | AudioFileClip,
    start_delay: float = 3,
    duck_volume: float = 0.3,
    fade_duration: float = 1.5
) -> AudioFileClip:
    """
    Combines TTS with background music, playing TTS over ducked music with smooth fades.

    Args:
        tts_audio_path (str): Path to the TTS audio file
        music_audio: AudioFileClip or str path to music file
        start_delay (float): Seconds to wait before TTS starts (default 3)
        duck_volume (float): Volume level for music during TTS (0.0 to 1.0, default 0.3)
        fade_duration (float): Duration of fade down/up transitions in seconds (default 1.5)

    Returns:
        AudioFileClip: Combined audio with TTS overlaid on music
    """
    try:
        import numpy as np
        from moviepy.audio.AudioClip import CompositeAudioClip

        # Load TTS audio
        tts_clip = AudioFileClip(tts_audio_path)
        tts_duration = tts_clip.duration

        # Load music audio
        if isinstance(music_audio, str):
            music_clip = AudioFileClip(music_audio)
        else:
            music_clip = music_audio

        music_duration = music_clip.duration

        # Set TTS to start after delay
        tts_clip = tts_clip.set_start(start_delay)

        # Calculate fade timing
        # Fade down starts before TTS, fade up starts after TTS ends
        fade_down_start = start_delay - fade_duration  # Start fading down before TTS
        fade_down_end = start_delay  # Fully ducked when TTS starts
        fade_up_start = start_delay + tts_duration  # Start fading up when TTS ends
        fade_up_end = fade_up_start + fade_duration  # Fully restored after fade

        # Create volume envelope for music ducking with smooth fades
        def volume_envelope(get_frame, t):
            frame = get_frame(t)

            if isinstance(t, (int, float)):
                # Single time value
                if t < fade_down_start:
                    # Before fade - full volume
                    return frame
                elif t < fade_down_end:
                    # During fade down - interpolate from 1.0 to duck_volume
                    progress = (t - fade_down_start) / fade_duration
                    volume = 1.0 - (progress * (1.0 - duck_volume))
                    return frame * volume
                elif t < fade_up_start:
                    # During TTS - ducked volume
                    return frame * duck_volume
                elif t < fade_up_end:
                    # During fade up - interpolate from duck_volume to 1.0
                    progress = (t - fade_up_start) / fade_duration
                    volume = duck_volume + (progress * (1.0 - duck_volume))
                    return frame * volume
                else:
                    # After fade up - full volume
                    return frame
            else:
                # Array of time values - vectorized processing
                result = frame.copy()

                # Create volume multiplier array
                volume = np.ones_like(t, dtype=float)

                # Fade down region
                fade_down_mask = (t >= fade_down_start) & (t < fade_down_end)
                if np.any(fade_down_mask):
                    progress = (t[fade_down_mask] - fade_down_start) / fade_duration
                    volume[fade_down_mask] = 1.0 - (progress * (1.0 - duck_volume))

                # Ducked region (during TTS)
                ducked_mask = (t >= fade_down_end) & (t < fade_up_start)
                volume[ducked_mask] = duck_volume

                # Fade up region
                fade_up_mask = (t >= fade_up_start) & (t < fade_up_end)
                if np.any(fade_up_mask):
                    progress = (t[fade_up_mask] - fade_up_start) / fade_duration
                    volume[fade_up_mask] = duck_volume + (progress * (1.0 - duck_volume))

                # Apply volume to all channels
                if len(result.shape) == 1:
                    result = result * volume
                else:
                    result = result * volume[:, np.newaxis]

                return result

        # Apply ducking with fades to music
        music_clip = music_clip.fl(volume_envelope, apply_to=['audio'])

        # Composite the audio
        combined = CompositeAudioClip([music_clip, tts_clip])

        message_processor(
            f"Combined TTS ({tts_duration:.1f}s) with music "
            f"(smooth {fade_duration}s fades, ducked to {int(duck_volume*100)}%)",
            "info"
        )
        return combined

    except Exception as e:
        message_processor(f"Error combining TTS with music: {e}", "error")
        # Return just the music if combining fails
        if isinstance(music_audio, str):
            return AudioFileClip(music_audio)
        return music_audio


def distribute_songs_evenly(songs, video_duration_sec, crossfade_seconds=5, fadeout_seconds=3):
    """
    Distributes songs evenly across the video duration with crossfades.

    Each song gets an equal segment of the video. Songs are trimmed to fit their
    allocated segment, with crossfades at transition points and a fade-out at the end.

    Args:
        songs (list of tuples): List of tuples (path, duration_sec) for each song.
        video_duration_sec (float): Total video duration in seconds.
        crossfade_seconds (int): Duration of crossfade between songs. Default 5.
        fadeout_seconds (int): Duration of fade-out at the end. Default 3.

    Returns:
        AudioFileClip or None: The combined audio clip with even distribution.
    """
    from moviepy.editor import CompositeAudioClip

    if not songs:
        message_processor("No songs provided for distribution.", log_level="error")
        return None

    num_songs = len(songs)
    segment_duration = video_duration_sec / num_songs

    message_processor(
        f"Distributing {num_songs} songs evenly across {video_duration_sec:.1f}s video "
        f"({segment_duration:.1f}s per song, {crossfade_seconds}s crossfade)",
        "info"
    )

    # Load and process all clips
    processed_clips = []
    for i, song in enumerate(songs):
        if not isinstance(song, tuple) or len(song) == 0:
            message_processor("Invalid song data format.", "error", ntfy=True)
            return None

        song_path = song[0]
        try:
            clip = AudioFileClip(song_path)
            message_processor(
                f"  Song {i+1}: {os.path.basename(song_path)[:30]}... ({clip.duration:.1f}s)",
                "info"
            )

            # Calculate timing for this clip
            # Each song starts at: i * (segment_duration - crossfade_seconds)
            # This creates overlap during crossfade periods
            if i == 0:
                start_time = 0
                # First clip: play for segment_duration, fade out at end
                clip_duration = min(clip.duration, segment_duration)
                clip = clip.subclip(0, clip_duration)
                clip = clip.audio_fadeout(crossfade_seconds)
            elif i == num_songs - 1:
                # Last clip: starts at overlap point, plays to end of video
                start_time = (segment_duration - crossfade_seconds) * i
                remaining_duration = video_duration_sec - start_time

                # If the song is shorter than remaining duration, loop it to fill the gap
                if clip.duration < remaining_duration:
                    message_processor(
                        f"    Last song ({clip.duration:.1f}s) shorter than remaining time ({remaining_duration:.1f}s). Looping to fill.",
                        "info"
                    )
                    clip = audio_loop(clip, duration=remaining_duration)
                    clip_duration = remaining_duration
                else:
                    clip_duration = remaining_duration
                    clip = clip.subclip(0, clip_duration)

                clip = clip.audio_fadein(crossfade_seconds)
                clip = clip.audio_fadeout(fadeout_seconds)
            else:
                # Middle clips: fade in and out
                start_time = (segment_duration - crossfade_seconds) * i
                clip_duration = min(clip.duration, segment_duration)
                clip = clip.subclip(0, clip_duration)
                clip = clip.audio_fadein(crossfade_seconds)
                clip = clip.audio_fadeout(crossfade_seconds)

            # Set when this clip starts playing
            clip = clip.set_start(start_time)
            processed_clips.append(clip)

            message_processor(
                f"    Placed at {start_time:.1f}s-{start_time + clip_duration:.1f}s",
                "info"
            )

        except Exception as e:
            message_processor(f"Error loading audio from {song_path}: {e}", "error", ntfy=True)
            return None

    if not processed_clips:
        return None

    # Combine all clips - CompositeAudioClip mixes overlapping audio
    if len(processed_clips) == 1:
        final_clip = processed_clips[0]
    else:
        final_clip = CompositeAudioClip(processed_clips)

    # Trim to exact video duration
    if final_clip.duration and final_clip.duration > video_duration_sec:
        final_clip = final_clip.subclip(0, video_duration_sec)

    message_processor(f"Audio distributed evenly. Final duration: {final_clip.duration:.1f}s", "info")
    return final_clip


def concatenate_songs(songs, crossfade_seconds=3):
    """
    Concatenates multiple AudioFileClip objects with manual crossfade.

    Args:
        songs (list of tuples): List of tuples, each containing the path to an audio file and its duration.
        crossfade_seconds (int): Duration of crossfade between clips.

    Returns:
        AudioFileClip or None: The concatenated audio clip.
    """
    import sys

    if not songs:
        message_processor("No songs provided for concatenation.", log_level="error")
        return None

    clips = []
    for song in songs:
        if isinstance(song, tuple) and len(song) > 0:
            song_path = song[0]  # Assuming the file path is the first element in the tuple
            try:
                clip = AudioFileClip(song_path)
                clips.append(clip)
            except Exception as e:
                message_processor(f"Error loading audio from {song_path}: {e}", "error", ntfy=True)
                sys.exit(1)

        else:
            message_processor("Invalid song data format.", "error", ntfy=True)

    if clips:
        # Manually handle crossfade
        if len(clips) > 1:
            # Adjust the start time of each subsequent clip to create overlap for crossfade
            for i in range(1, len(clips)):
                clips[i] = clips[i].set_start(clips[i-1].end - crossfade_seconds)
            final_clip = concatenate_audioclips(clips)
        else:
            final_clip = clips[0]

        return final_clip

    return None
