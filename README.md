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

### 3. Create Video Only
```bash
# Generate video from existing images
python main.py <project_name> --movie
```

### 4. Test Compilation Pipeline
```bash
# Generate test images and run full video compilation without real captures
python main.py <project_name> --test-compile
```

## Project Structure

```
HourGlass/
├── main.py                 # Main entry point
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

## Video Download (v.sh)

`v.sh` downloads the completed timelapse video from the remote server to your local machine. It can run via cron or manually.

```bash
# Usage
./v.sh -p <PROJECT> [-f] [-d MMDDYYYY] [-o N] [-y] [-h]

# Cron: waits for video to finish building, then downloads
./v.sh -p VLA

# Manual re-run: skip checks, just download
./v.sh -p VLA -f

# Download yesterday's video
./v.sh -p VLA -f -y

# Download a specific date
./v.sh -p VLA -d 09222025
```

**Cron path:** smart wait (based on End time from ntfy) → poll ntfy for "saved successfully" → resolve actual filename → SCP download → ffprobe validation → notify

**Manual path (`-f`):** skip file check/wait/polling → SSH check for file (both standard and NO_AUDIO variants) → SCP download → ffprobe validation → notify

**Requirements:**
- `jq` (reads ntfy config from `configs/<PROJECT>.json`)
- `ffprobe` (validates downloaded video; optional but recommended)
- SSH key access to the remote server
- `~/.linode_config` with `LINODE_IP` set

## Cron Scheduling

Each project's instructions file contains customized cron entries. Example:

```bash
# Start capture at sunrise
0 6 * * * cd /path/to/HourGlass && ./hourglass.sh project_name

# Stop capture after sunset
0 20 * * * pkill -f 'python main.py project_name'

# Download video daily at 17:00
0 17 * * * /path/to/HourGlass/v.sh -p project_name >> ~/v.log 2>&1
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

[Your License Here]