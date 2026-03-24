# status.py
"""
Atomic status file writer for HourGlass project state tracking.
Writes status.json to the project's data directory so the status API can serve it.
"""

import json
import logging
import os
import tempfile
from datetime import datetime


def write_status(project_base, project_name, state, detail="",
                 video_filename=None, video_size_mb=None, target_time=None):
    """
    Atomically write project status to {project_base}/status.json.

    Fire-and-forget: catches all exceptions internally so it never
    disrupts the main application flow.

    Args:
        project_base: Path to the project data directory (e.g. ~/HourGlass/VLA)
        project_name: Project name (e.g. "VLA")
        state: One of: idle, sleeping, capturing, creating_video, video_saved, error
        detail: Human-readable detail string
        video_filename: Set when state is video_saved
        video_size_mb: Set when state is video_saved
        target_time: Capture end time in HH:MM format
    """
    try:
        status = {
            "state": state,
            "timestamp": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
            "project": project_name,
            "detail": detail,
            "video": {
                "filename": video_filename,
                "size_mb": video_size_mb,
            },
            "capture": {
                "target_time": target_time,
            },
        }

        os.makedirs(project_base, exist_ok=True)
        status_path = os.path.join(project_base, "status.json")

        # Atomic write: write to temp file in same directory, then rename
        fd, tmp_path = tempfile.mkstemp(dir=project_base, suffix=".tmp")
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(status, f, indent=2)
            os.rename(tmp_path, status_path)
        except Exception:
            # Clean up temp file if rename fails
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

        logging.info(f"Status updated: {state}")

    except Exception as e:
        logging.warning(f"Failed to write status: {e}")
