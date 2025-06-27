# EVLA Webcam Time-Lapse Video Creator

## Overview
This script automatically downloads images from the Expanded Very Large Array (EVLA) observatory webcam, generates a time-lapse video from these images, and adds a soundtrack to the video. The system features enhanced reliability, performance monitoring, and intelligent error handling. It runs continuously, capturing images at random intervals between 15 to 22 seconds, with advanced session recovery and exponential backoff for maximum uptime.

## Features

### Core Functionality
- **Automated Image Downloads:** Downloads images from the EVLA observatory webcam
- **Duplicate Avoidance:** Uses SHA-256 hashing to prevent saving duplicate images
- **Time-Lapse Video Creation:** Generates high-quality time-lapse videos from collected images
- **Audio Track Addition:** Adds dynamic soundtracks to time-lapse videos

### Enhanced Capabilities
- **Robust Error Handling:** Exponential backoff and automatic session recovery
- **Health Monitoring:** Real-time system monitoring with alerts for disk space, memory, CPU, and network
- **Fast Image Validation:** 5-10x faster image processing using optimized validation
- **Memory Management:** Prevents out-of-memory crashes with intelligent cleanup and chunked processing
- **Performance Metrics:** Comprehensive logging and performance tracking
- **Log Rotation:** Automatic log file management preventing huge log files
- **Configuration Validation:** Startup validation of settings and system health

## Tested On
- **Ubuntu**
- **Fedora** 
- **Debian**
- **macOS** (with Homebrew)

## Requirements
- Python 3.12 or newer
- Additional system monitoring capabilities (automatically installed)

## Setup

### Automated Setup
The easiest way to get started:

```bash
bash setup.sh
```

This will automatically:
- Detect your operating system
- Install required system packages
- Create a Python virtual environment
- Install all Python dependencies