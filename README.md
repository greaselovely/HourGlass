# HourGlass - Multi-Project Webcam Timelapse System

## Overview
HourGlass is a flexible and robust webcam timelapse system that automatically downloads images from any webcam URL, generates time-lapse videos from these images, and optionally adds soundtracks. The system supports multiple concurrent projects, features enhanced reliability, performance monitoring, and intelligent error handling. It runs continuously, capturing images at configurable intervals, with advanced session recovery and exponential backoff for maximum uptime.

## Features

### Core Functionality
- **Multi-Project Support:** Manage multiple timelapse projects from a single installation
- **Automated Image Downloads:** Downloads images from any configured webcam URL
- **MJPEG Stream Support:** Extracts frames from MJPEG video streams
- **Duplicate Avoidance:** Uses SHA-256 hashing to prevent saving duplicate images
- **Time-Lapse Video Creation:** Generates high-quality time-lapse videos from collected images
- **Audio Track Addition:** Adds dynamic soundtracks to time-lapse videos using Pixabay
- **Even Audio Distribution:** Songs split evenly across video with 5-second crossfades
- **Song History Tracking:** 180-day history prevents song repetition across videos
- **TTS Intro:** Random voice selection from Edge TTS (free) and Google Cloud TTS
- **Daily Narration:** Optional spoken intro segments built from today's spaceflight news and NASA's Astronomy Picture of the Day

### Enhanced Capabilities
- **Robust Error Handling:** Exponential backoff and automatic session recovery
- **Health Monitoring:** Real-time system monitoring with alerts for disk space, memory, CPU, and network
- **Fast Image Validation:** 5-10x faster image processing using optimized validation
- **Memory Management:** Prevents out-of-memory crashes with intelligent cleanup and chunked processing
- **Performance Metrics:** Comprehensive logging and performance tracking
- **Log Rotation:** Automatic log file management preventing huge log files
- **Configuration Validation:** Startup validation of settings and system health
- **Timezone Support:** Automatic timezone handling for remote webcams
- **tmux Integration:** Run captures in background with easy monitoring

## Tested On
- **Ubuntu**
- **Fedora** 
- **Debian**
- **macOS**

## Requirements
- Python 3.12 (specifically - newer versions may have compatibility issues with dependencies)
- tmux (for background operation)
- ffmpeg (for video/audio processing)
- Additional system monitoring capabilities (automatically installed)

## Optional Setup
- **Google Cloud TTS:** For high-quality text-to-speech intros. See [GOOGLE_TTS_SETUP.md](GOOGLE_TTS_SETUP.md) for setup instructions.
- **Edge TTS:** Free alternative that works out of the box with no API key required. The system randomly selects between Edge and Google (if configured) for voice variety.

## Quick Start

### 1. Initial Setup
```bash
# Install dependencies
bash setup.sh

# Configure your first project
python main.py
# Or directly with project name:
python main.py <project_name>
```

### 2. Running a Project
```bash
# Start capture for a project
./hourglass.sh <project_name>

# Or run directly with Python
python main.py <project_name>

# Run with time bypass (for testing)
python main.py <project_name> --no-time-check
```

### 3. Restart a Running Project
```bash
# Cleanly restart: kill the capture tmux session, restart the status API
# service, then relaunch capture the way cron does. Capture resumes today's
# existing image folder, so restarting mid-day does not lose frames.
./restart.sh <project_name>

# Bounce only the capture — skip the (sudo) status-service restart
./restart.sh <project_name> --no-service
```

### 4. Create Video Only
```bash
# Generate video from existing images
python main.py <project_name> --movie
```

### 5. Test Compilation Pipeline
```bash
# Generate test images and run full video compilation without real captures
python main.py <project_name> --test-compile
```

## Project Structure

```
HourGlass/
├── main.py                 # Main entry point
├── hourglass.sh            # Capture launcher (tmux session; run by cron)
├── restart.sh              # Cleanly restart capture + status API service
├── status_api.py           # Status + video download API (runs on server)
├── download.py             # Video download client (runs locally via cron)
├── lib/                    # Library modules
│   ├── timelapse_core.py   # Core functionality
│   ├── timelapse_config.py # Configuration management
│   ├── timelapse_setup.py  # Project setup wizard
│   ├── timelapse_loop.py   # Main capture loop
│   ├── timelapse_validator.py # Image validation
│   ├── timelapse_upload.py # YouTube upload
│   ├── config_validator.py # Config validation
│   ├── health_monitor.py   # System health monitoring
│   ├── memory_optimizer.py # Memory management
│   ├── image_downloader.py # Image capture, hashing, session recovery
│   ├── audio.py            # TTS and background music
│   ├── space_fact.py       # Daily narration segments (news + NASA APOD)
│   └── ...
├── configs/                # Project configurations
│   ├── project1.json
│   ├── project2.json
│   └── ...
├── instructions/           # Generated setup instructions
│   ├── project1_instructions.txt
│   └── ...
└── ~/HourGlass/<project>/  # Project data (configurable)
    ├── images/
    ├── video/
    ├── audio/
    └── logging/
```

## Configuration

Each project has its own configuration file in `configs/<project_name>.json`. Key settings include:

- **Webcam URLs:** Direct image URL or MJPEG stream
- **Capture interval:** Time between image captures
- **Sunrise/sunset times:** Automatic or manual scheduling
- **Timezone offset:** For remote webcam locations
- **Alert settings:** ntfy.sh integration for notifications
- **Audio settings:** Background music configuration

Changes take effect on restart (`./restart.sh <project_name>`).

### Sunrise/Sunset Configuration

HourGlass automatically fetches sunrise and sunset times based on your webcam's location coordinates using the [sunrise-sunset.org](https://sunrise-sunset.org/api) API (no API key required).

**Setting up coordinates:**

During setup, you can provide location in several ways:
- **Direct coordinates:** Enter latitude and longitude (e.g., `34.0788, -107.6166`)
- **Google Maps URL:** Copy a Google Maps link - coordinates will be extracted automatically
- **Legacy timeanddate.com URL:** For existing users with URL-based configs

**Finding your coordinates:**
1. Go to [Google Maps](https://maps.google.com)
2. Right-click on the webcam location
3. Click "What's here?" to see coordinates
4. Or use [latlong.net](https://www.latlong.net/) to look up any location

**Configuration fields:**
```json
"sun": {
    "lat": 34.0788,
    "lng": -107.6166,
    "SUNRISE": "06:00:00",
    "SUNSET": "19:00:00",
    "SUNSET_TIME_ADD": 60,
    "TIME_OFFSET_HOURS": 0
}
```

| Field | Description |
|-------|-------------|
| `lat` | Latitude coordinate (-90 to 90) |
| `lng` | Longitude coordinate (-180 to 180) |
| `SUNRISE` | Fallback sunrise time if API unavailable |
| `SUNSET` | Fallback sunset time if API unavailable |
| `SUNSET_TIME_ADD` | Minutes to continue capture after sunset |
| `TIME_OFFSET_HOURS` | Timezone offset from server to webcam location |

**Migration:** Existing configs with timeanddate.com URLs containing `@lat,lng` will be automatically migrated to use coordinates on next run.

### Daily Narration (TTS Intro)

When `music.tts_intro.daily_fact.enabled` is true, the spoken intro adds up to two segments after the project title: today's top spaceflight news story, then a fact drawn from NASA's Astronomy Picture of the Day.

```json
"daily_fact": {
    "enabled": true,
    "nasa_api_key": "",
    "anthropic_api_key": "",
    "max_words": 30,
    "news_enabled": true,
    "pause_seconds": 3
}
```

| Field | Description |
|-------|-------------|
| `enabled` | Master switch. When false the intro is just the project description |
| `nasa_api_key` | api.nasa.gov key. Blank uses `DEMO_KEY` (30/hr, 50/day per IP). Free key at [api.nasa.gov](https://api.nasa.gov) |
| `anthropic_api_key` | Blank falls back to the `ANTHROPIC_API_KEY` environment variable |
| `max_words` | Word cap per spoken segment |
| `news_enabled` | Include the spaceflight-news segment before the NASA fact |
| `pause_seconds` | Silence inserted between spoken segments |

If a source is unavailable that segment is skipped. If neither is reachable the intro is the project description alone. Results are cached per day in `cache/daily_fact.json`.

A 403 response from api.nasa.gov indicates an invalid key; 429 indicates the rate limit.

## Managing Multiple Projects

### List Projects
```bash
ls configs/
```

### Create New Project
```bash
python timelapse_setup.py
# Select "Create new project"
```

### Update Existing Project
```bash
python timelapse_setup.py
# Select the project to update
```

## tmux Session Management

HourGlass automatically creates tmux sessions for background operation:

```bash
# Attach to running session
tmux attach -t hourglass-<project_name>

# List all sessions
tmux list-sessions

# Kill a session
tmux kill-session -t hourglass-<project_name>
```

## Video Download (download.py)

`download.py` downloads the completed timelapse video from the remote server over HTTP via the status API. No SSH keys or firewall scripts needed — just Tailscale.

```bash
# Usage
python download.py -p <PROJECT> [-f] [-d MMDDYYYY] [-o N] [-y]

# Cron: waits for video to finish building, then downloads
python download.py -p VLA

# Manual re-run: skip wait/poll, just download
python download.py -p VLA -f

# Download yesterday's video
python download.py -p VLA -f -y

# Download a specific date
python download.py -p VLA -d 09222025
```

**Cron path:** smart wait (based on end time from status API) → poll status API for `video_saved` → HTTP download → ffprobe validation → notify

**Manual path (`-f`):** skip wait/polling → resolve filename via API → HTTP download → ffprobe validation → notify

**Requirements:**
- `ffprobe` (validates downloaded video; optional but recommended)
- Status API running on the server (`status_api.py`)
- Tailscale connectivity to the server

## Cron Scheduling

Each project's instructions file contains customized cron entries. Example:

```bash
# Start capture at sunrise
0 6 * * * cd /path/to/HourGlass && ./hourglass.sh project_name

# Stop capture after sunset
0 20 * * * pkill -f 'python main.py project_name'

# Download video daily at 17:00
0 17 * * * /path/to/HourGlass/venv/bin/python /path/to/HourGlass/download.py -p project_name >> ~/v.log 2>&1
```

## Advanced Features

### Health Monitoring
```bash
python main.py <project_name> --health
```

### Configuration Validation
```bash
python main.py <project_name> --validate
```

### Debug Mode
```bash
python main.py <project_name> --debug
```

## Troubleshooting

### Common Issues

1. **No project found:** Ensure the project config exists in `configs/`
2. **Session creation failed:** Check USER_AGENTS and PROXIES in config
3. **Images not saving:** Verify the webcam URL is accessible
4. **MJPEG streams:** The system automatically detects and handles MJPEG streams
5. **Intro missing news/NASA segments:** Source APIs were unreachable. Check the log for `Fetch failed`

### Logs

Check project-specific logs:
```bash
tail -f ~/HourGlass/<project_name>/logging/timelapse.log
```

## Performance Notes

- Optimized for long-running captures with automatic recovery
- Memory-efficient processing for large image collections
- Automatic cleanup of temporary files
- Intelligent backoff for network failures

## Contributing

Contributions are welcome! Please ensure any changes maintain backward compatibility with existing project configurations.

## License

Just make sure you're wearing pants.