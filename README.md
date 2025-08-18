# HourGlass - Webcam Timelapse System

## Overview
HourGlass is a flexible and robust webcam timelapse system that automatically downloads images from any webcam URL, generates time-lapse videos from these images, and optionally adds soundtracks. The system features enhanced reliability, performance monitoring, and intelligent error handling. It runs continuously, capturing images at configurable intervals, with advanced session recovery and exponential backoff for maximum uptime.

## Features

### Core Functionality
- **Automated Image Downloads:** Downloads images from any configured webcam URL
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
- Python 3.12 (specifically - newer versions may have compatibility issues with dependencies)
- Additional system monitoring capabilities (automatically installed)

## Setup

### Automated Setup
The easiest way to get started:

1. Install dependencies:
```bash
bash setup.sh
```

2. Configure your project:
```bash
python initial_setup.py
```

3. Start capturing:
```bash
./hourglass.sh
```

This will automatically:
- Detect your operating system
- Install required system packages
- Create a Python virtual environment
- Install all Python dependencies