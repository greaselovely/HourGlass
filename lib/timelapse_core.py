# timelapse_core.py
"""
Core timelapse functionality - re-exports from modular components.

This module serves as the main entry point and re-exports all functions
from the split modules for backwards compatibility.

Modules:
- utils: Logging, notifications, session management, and helper functions
- image_downloader: Image downloading with session recovery
- audio: Song downloading, caching, TTS, and audio processing
- video: Time-lapse creation and video processing
- sun_schedule: Sun schedule fetching for timing captures
"""

# Re-export everything from sub-modules for backwards compatibility
from .utils import (
    clear,
    log_jamming,
    message_processor,
    send_to_ntfy,
    activity,
    create_session,
    make_request,
    process_image_logs,
    check_socks_proxy,
    get_or_create_run_id,
    find_today_run_folders,
    prompt_user_for_folder_selection,
    remove_valid_images_json,
    cleanup,
)

from .image_downloader import (
    ImageDownloader,
)

from .audio import (
    # Song history tracking
    SONG_HISTORY_RETENTION_DAYS,
    load_song_history,
    save_song_history,
    cleanup_song_history,
    add_song_to_history,
    is_song_in_history,
    get_song_usage_count,
    get_cached_file_usage_count,
    # Audio cache management
    manage_audio_cache,
    add_to_audio_cache,
    get_cached_audio,
    get_cache_stats,
    # Song downloading
    single_song_download,
    audio_download,
    # TTS functions
    create_tts_intro,
    combine_tts_with_music,
    # Audio processing
    distribute_songs_evenly,
    concatenate_songs,
)

from .video import (
    CustomLogger,
    validate_images,
    calculate_video_duration,
    create_time_lapse,
)

from .sun_schedule import (
    sun_schedule,
    find_time_and_convert,
)

# Also import from timelapse_config for convenience
from .timelapse_config import *
