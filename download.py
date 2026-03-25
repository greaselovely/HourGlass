#!/usr/bin/env python3
"""
HourGlass Video Download — polls the status API and downloads the video over HTTP.

Runs locally (e.g. via cron), talks to the status API.

Usage:
    python3 download.py -p VLA              # cron: smart wait + poll + download
    python3 download.py -p VLA -f           # force: skip wait/poll, just download
    python3 download.py -p VLA -f -y        # force download yesterday's video
    python3 download.py -p VLA -d 09222025  # specific date
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen, Request

SCRIPT_DIR = Path(__file__).resolve().parent
LOG_FILE = Path.home() / "v.log"
LOG_MAX_SIZE = 1024 * 1024  # 1MB
SAVE_BUFFER_MIN = 18  # 13 min avg save time + 5 min buffer


# ============================================================================
# Logging
# ============================================================================

def rotate_log():
    if LOG_FILE.exists() and LOG_FILE.stat().st_size > LOG_MAX_SIZE:
        LOG_FILE.rename(LOG_FILE.with_suffix(".log.1"))


def log(msg):
    line = f"{datetime.now():%Y-%m-%d %H:%M:%S} | {msg}"
    print(line, flush=True)
    try:
        with open(LOG_FILE, "a") as f:
            f.write(line + "\n")
    except OSError:
        pass


# ============================================================================
# Notifications (ntfy + Pushover)
# ============================================================================

def _url_post(url, data, headers=None):
    """Fire-and-forget POST."""
    try:
        req = Request(url, data=data.encode() if isinstance(data, str) else data,
                      headers=headers or {}, method="POST")
        urlopen(req, timeout=10)
    except Exception:
        pass


class Notifier:
    def __init__(self, config):
        self.ntfy_topic = None
        self.po_token = None
        self.po_user = None

        ntfy_base = config.get("ntfy", "")
        alerts = config.get("alerts", {}).get("services", {})
        ntfy_cfg = alerts.get("ntfy", {})
        if ntfy_cfg.get("enabled") and ntfy_base and ntfy_cfg.get("topic"):
            self.ntfy_topic = f"{ntfy_base.rstrip('/')}/{ntfy_cfg['topic']}"

        po_cfg = alerts.get("pushover", {})
        if po_cfg.get("enabled") and po_cfg.get("api_token") and po_cfg.get("user_key"):
            self.po_token = po_cfg["api_token"]
            self.po_user = po_cfg["user_key"]

    def send(self, msg, priority="default"):
        log(msg)
        if self.ntfy_topic:
            _url_post(self.ntfy_topic, f"[download] {msg}",
                      {"Priority": priority})
        if self.po_token:
            po_pri = {"low": "-1", "high": "1", "urgent": "1"}.get(priority, "0")
            from urllib.parse import urlencode
            _url_post("https://api.pushover.net/1/messages.json",
                      urlencode({"token": self.po_token, "user": self.po_user,
                                 "message": f"[download] {msg}", "priority": po_pri}),
                      {"Content-Type": "application/x-www-form-urlencoded"})


# ============================================================================
# Status API client
# ============================================================================

def api_get(url):
    """GET JSON from status API. Returns dict or None."""
    try:
        with urlopen(url, timeout=10) as resp:
            return json.loads(resp.read())
    except Exception:
        return None


def get_end_time(api_url):
    status = api_get(api_url)
    if status:
        return (status.get("capture") or {}).get("target_time")
    return None


def calculate_sleep_seconds(end_time_str):
    try:
        end_h, end_m = map(int, end_time_str.split(":"))
    except (ValueError, AttributeError):
        return 0
    target = end_h * 60 + end_m + SAVE_BUFFER_MIN
    now = datetime.now()
    now_total = now.hour * 60 + now.minute
    diff = target - now_total
    return max(diff * 60, 0)


def poll_for_video(api_url, max_attempts=60, interval=60):
    """
    Poll status API for video_saved state.
    Returns filename on success, None on timeout/error.
    Falls through (returns None) on idle/Completed so caller can try SSH-style resolution.
    """
    log(f"Polling status API for video completion ({max_attempts}x{interval}s)...")

    for attempt in range(1, max_attempts + 1):
        status = api_get(api_url)

        if not status:
            log(f"API unreachable (attempt {attempt}/{max_attempts}). Waiting {interval}s...")
            if attempt < max_attempts:
                time.sleep(interval)
            continue

        state = status.get("state", "")

        if state == "video_saved":
            filename = (status.get("video") or {}).get("filename")
            log(f"Video saved: {filename} (attempt {attempt}/{max_attempts})")
            return filename

        if state == "error":
            detail = status.get("detail", "unknown")
            log(f"HourGlass reported error: {detail}")
            return None

        if state == "idle" and status.get("detail") == "Completed":
            log("Status is idle/Completed, resolving filename from status...")
            filename = (status.get("video") or {}).get("filename")
            return filename  # May be None — caller handles resolution

        log(f"State: {state or 'unknown'} (attempt {attempt}/{max_attempts}). Waiting {interval}s...")
        if attempt < max_attempts:
            time.sleep(interval)

    log(f"Timed out waiting for video after {max_attempts * interval // 60}min")
    return None


# ============================================================================
# Download + validation
# ============================================================================

def download_video(base_url, project, filename, dest_dir):
    """Download video file over HTTP. Returns local path or None."""
    url = f"{base_url}/download/{project}/{filename}"
    dest = dest_dir / filename
    log(f"Downloading {url} -> {dest}")

    try:
        with urlopen(url, timeout=300) as resp:
            with open(dest, "wb") as f:
                while chunk := resp.read(1024 * 1024):
                    f.write(chunk)
    except Exception as e:
        log(f"Download failed: {e}")
        dest.unlink(missing_ok=True)
        return None

    if not dest.exists() or dest.stat().st_size == 0:
        log("Downloaded file is empty")
        dest.unlink(missing_ok=True)
        return None

    return dest


def try_download(base_url, project, filename, dest_dir):
    """Try download with one retry after 60s."""
    path = download_video(base_url, project, filename, dest_dir)
    if path:
        return path
    log("Retrying download in 60s...")
    time.sleep(60)
    return download_video(base_url, project, filename, dest_dir)


def validate_video(filepath):
    """Validate with ffprobe. Returns duration string or None on failure."""
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "csv=p=0", str(filepath)],
            capture_output=True, text=True, timeout=30)
        duration = result.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        log("WARNING: ffprobe not found or timed out, skipping validation")
        return "unknown"

    if not duration or duration in ("0", "0.000000", "N/A"):
        log(f"FAILED: ffprobe validation — corrupt (duration: {duration or 'empty'})")
        filepath.unlink(missing_ok=True)
        return None

    dur_int = int(float(duration))
    return f"{dur_int // 60}m{dur_int % 60}s"


def resolve_filename_from_api(base_url, project, date_str):
    """Try both filename variants via the download endpoint (HEAD-style check)."""
    candidates = [f"{project}.{date_str}.mp4", f"{project}.{date_str}.NO_AUDIO.mp4"]
    for candidate in candidates:
        url = f"{base_url}/download/{project}/{candidate}"
        try:
            req = Request(url, method="HEAD")
            with urlopen(req, timeout=10):
                return candidate
        except Exception:
            continue
    return None


# ============================================================================
# Main
# ============================================================================

def resolve_date(date_str, offset_days, yesterday):
    if date_str:
        return date_str
    if yesterday:
        offset_days = 1
    d = datetime.now() - timedelta(days=offset_days)
    return d.strftime("%m%d%Y")


def main():
    parser = argparse.ArgumentParser(description="HourGlass Video Download")
    parser.add_argument("-p", "--project", required=True, help="Project name (e.g. VLA)")
    parser.add_argument("-f", "--force", action="store_true", help="Skip wait/poll, just download")
    parser.add_argument("-d", "--date", default="", help="Specific date (MMDDYYYY)")
    parser.add_argument("-o", "--offset", type=int, default=0, help="N days ago")
    parser.add_argument("-y", "--yesterday", action="store_true", help="Yesterday (same as -o 1)")
    args = parser.parse_args()

    if args.date and not re.match(r"^[01]\d[0-3]\d\d{4}$", args.date):
        print("Error: Invalid -d format. Use MMDDYYYY.")
        sys.exit(1)

    rotate_log()

    # Load config
    config_path = SCRIPT_DIR / "configs" / f"{args.project}.json"
    if not config_path.is_file():
        print(f"Error: Config not found: {config_path}")
        sys.exit(1)

    with open(config_path) as f:
        config = json.load(f)

    notifier = Notifier(config)

    # Build API base URL
    ts_ip = config.get("status_api", {}).get("tailscale_ip", "")
    port = config.get("status_api", {}).get("port", 8321)
    if not ts_ip:
        notifier.send("No status_api.tailscale_ip configured. Cannot proceed.", "high")
        sys.exit(1)

    base_url = f"http://{ts_ip}:{port}"
    api_url = f"{base_url}/status/{args.project}"

    date_str = resolve_date(args.date, args.offset, args.yesterday)
    filename = f"{args.project}.{date_str}.mp4"

    # Pre-flight: check if local file already exists (unless force)
    dest_dir = Path.home()
    if not args.force:
        for variant in [f"{args.project}.{date_str}.mp4", f"{args.project}.{date_str}.NO_AUDIO.mp4"]:
            if (dest_dir / variant).exists():
                notifier.send(f"File {variant} already exists. Use -f to override.", "low")
                sys.exit(0)

    log(f"=== download.py -p {args.project} | PID: {os.getpid()} ===")
    log(f"API: {base_url}")
    log(f"Project: {args.project}")
    log(f"Target date: {date_str}")

    if not args.force:
        # Cron path: smart wait -> poll -> download
        end_time = get_end_time(api_url)
        if end_time:
            log(f"Capture end time: {end_time}")
            sleep_secs = calculate_sleep_seconds(end_time)
            if sleep_secs > 0:
                wake = (datetime.now() + timedelta(seconds=sleep_secs)).strftime("%H:%M")
                log(f"Video not ready yet. Sleeping {sleep_secs}s (until ~{wake})...")
                notifier.send(f"Waiting until ~{wake} for video to be ready", "low")
                time.sleep(sleep_secs)
                log("Waking up, polling for completion.")
            else:
                log("Target time already passed, polling for completion.")
        else:
            log("Could not determine end time, polling for completion.")

        result = poll_for_video(api_url)
        if result:
            filename = result
    else:
        log("Force mode: skipping smart wait and polling.")

    # Resolve filename if we don't have one from polling (or force mode)
    if filename == f"{args.project}.{date_str}.mp4":
        resolved = resolve_filename_from_api(base_url, args.project, date_str)
        if not resolved:
            notifier.send(f"Video file not found for {args.project}.{date_str}", "high")
            sys.exit(1)
        filename = resolved

    # Download
    local_path = try_download(base_url, args.project, filename, dest_dir)
    if not local_path:
        notifier.send(f"Download failed for {filename}", "high")
        sys.exit(1)

    file_size = f"{local_path.stat().st_size / (1024 * 1024):.1f}MB"
    log(f"File {filename} transferred. Size: {file_size}")

    # Validate
    duration = validate_video(local_path)
    if not duration:
        notifier.send(f"Downloaded file is corrupt (ffprobe failed). Deleted {filename}.", "high")
        sys.exit(1)

    notifier.send(f"Video Downloaded: {filename} ({file_size}, {duration})", "low")


if __name__ == "__main__":
    main()
