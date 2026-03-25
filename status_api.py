#!/usr/bin/env python3
"""
HourGlass Status API — lightweight HTTP server for project status and video downloads.

Serves status.json files written by HourGlass at key milestones, and provides
video file downloads over HTTP (replacing SCP-based transfers).
Intended to run as a systemd service, queried over Tailscale.

Usage:
    python3 status_api.py [--port 8321] [--bind 0.0.0.0]

Endpoints:
    GET /status/{PROJECT}              — returns project status JSON (or 404)
    GET /download/{PROJECT}/{FILENAME} — streams video file for download
    GET /health                        — returns {"ok": true}
"""

import argparse
import json
import os
import logging
import logging.handlers
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path

HOURGLASS_BASE = Path.home() / "HourGlass"
LOG_FILE = Path.home() / ".hourglass-status-api.log"


def setup_logging():
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    handler = logging.handlers.RotatingFileHandler(
        LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=2
    )
    handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
    logger.addHandler(handler)


class StatusHandler(BaseHTTPRequestHandler):

    def do_HEAD(self):
        """Support HEAD requests for file existence checks."""
        path = self.path.rstrip("/")
        if path.startswith("/download/"):
            parts = path[len("/download/"):].split("/", 1)
            if len(parts) == 2 and parts[0] and parts[1]:
                filename = parts[1]
                if ".." not in filename and "/" not in filename:
                    video_path = HOURGLASS_BASE / parts[0] / "video" / filename
                    if video_path.is_file():
                        self.send_response(200)
                        self.send_header("Content-Length", str(video_path.stat().st_size))
                        self.end_headers()
                        return
        self.send_response(404)
        self.end_headers()

    def do_GET(self):
        path = self.path.rstrip("/")

        if path == "/health":
            self._json_response(200, {"ok": True})
            return

        # /status/{PROJECT}
        if path.startswith("/status/"):
            project = path[len("/status/"):]
            if not project or "/" in project:
                self._json_response(400, {"error": "Invalid project name"})
                return
            self._serve_status(project)
            return

        # /download/{PROJECT}/{FILENAME}
        if path.startswith("/download/"):
            parts = path[len("/download/"):].split("/", 1)
            if len(parts) != 2 or not parts[0] or not parts[1]:
                self._json_response(400, {"error": "Use /download/{PROJECT}/{FILENAME}"})
                return
            project, filename = parts
            self._serve_download(project, filename)
            return

        self._json_response(404, {"error": "Not found"})

    def _serve_status(self, project):
        status_path = HOURGLASS_BASE / project / "status.json"
        if not status_path.is_file():
            self._json_response(404, {"error": f"No status for project '{project}'"})
            return
        try:
            with open(status_path, "r") as f:
                data = json.load(f)
            self._json_response(200, data)
        except (json.JSONDecodeError, OSError) as e:
            logging.error(f"Error reading {status_path}: {e}")
            self._json_response(500, {"error": "Failed to read status file"})

    def _serve_download(self, project, filename):
        # Sanitize: no path traversal
        if ".." in filename or "/" in filename:
            self._json_response(400, {"error": "Invalid filename"})
            return

        video_path = HOURGLASS_BASE / project / "video" / filename
        if not video_path.is_file():
            self._json_response(404, {"error": f"File not found: {filename}"})
            return

        try:
            file_size = video_path.stat().st_size
            self.send_response(200)
            self.send_header("Content-Type", "video/mp4")
            self.send_header("Content-Length", str(file_size))
            self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
            self.end_headers()

            with open(video_path, "rb") as f:
                while chunk := f.read(1024 * 1024):  # 1MB chunks
                    self.wfile.write(chunk)

            logging.info(f"Served download: {project}/{filename} ({file_size} bytes)")
        except (OSError, BrokenPipeError) as e:
            logging.error(f"Download failed for {video_path}: {e}")

    def _json_response(self, code, data):
        body = json.dumps(data).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        logging.info(f"{self.client_address[0]} - {format % args}")


def main():
    parser = argparse.ArgumentParser(description="HourGlass Status API")
    parser.add_argument("--port", type=int, default=8321, help="Port (default: 8321)")
    parser.add_argument("--bind", default="0.0.0.0", help="Bind address (default: 0.0.0.0)")
    args = parser.parse_args()

    setup_logging()

    server = HTTPServer((args.bind, args.port), StatusHandler)
    logging.info(f"Status API listening on {args.bind}:{args.port}")
    print(f"HourGlass Status API on {args.bind}:{args.port}")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logging.info("Shutting down")
        server.shutdown()


if __name__ == "__main__":
    main()
