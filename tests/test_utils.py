"""Tests for lib/utils.py functions."""
import os
import sys
from pathlib import Path
from datetime import datetime, timedelta

# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from lib.utils import log_jamming, find_today_run_folders


class TestLogJamming:
    """Tests for log_jamming function."""

    def test_formats_short_message(self):
        """Short messages should be returned with minimal formatting."""
        result = log_jamming("Test message")

        assert "Test message" in result
        assert isinstance(result, str)

    def test_formats_long_message_with_wrapping(self):
        """Long messages should be wrapped at 90 chars with proper indentation."""
        long_message = "A" * 150  # 150 character message
        result = log_jamming(long_message)

        lines = result.split('\n')
        # First line should be at most 90 chars
        assert len(lines[0]) <= 90
        # Should have multiple lines
        assert len(lines) > 1

    def test_empty_message(self):
        """Empty string should be handled gracefully."""
        result = log_jamming("")

        assert result == ""

    def test_message_with_special_characters(self):
        """Messages with special characters should be preserved."""
        message = "Session: {'key': 'value'}, User-Agent: Mozilla/5.0"
        result = log_jamming(message)

        # Content should be preserved across lines
        assert "Session" in result
        assert "Mozilla" in result


class TestFindTodayRunFolders:
    """Tests for find_today_run_folders function."""

    def test_finds_matching_folders(self, temp_directory):
        """Should find folders starting with today's date."""
        today = datetime.now().strftime("%Y%m%d")

        # Create test folders
        matching_folder = temp_directory / f"{today}_abc123"
        matching_folder.mkdir()

        old_folder = temp_directory / "20200101_old"
        old_folder.mkdir()

        result = find_today_run_folders(time_offset=0, images_folder=str(temp_directory))

        assert len(result) == 1
        assert today in result[0]

    def test_returns_empty_when_no_matches(self, temp_directory):
        """Should return empty list when no folders match today's date."""
        # Create only old folders
        old_folder = temp_directory / "20200101_old"
        old_folder.mkdir()

        result = find_today_run_folders(time_offset=0, images_folder=str(temp_directory))

        assert result == []

    def test_returns_empty_when_folder_missing(self, temp_directory):
        """Should return empty list when images folder doesn't exist."""
        nonexistent = temp_directory / "does_not_exist"

        result = find_today_run_folders(time_offset=0, images_folder=str(nonexistent))

        assert result == []

    def test_time_offset_changes_date(self, temp_directory):
        """Time offset should adjust which date is considered 'today'."""
        # Create folder for "tomorrow"
        tomorrow = (datetime.now() + timedelta(hours=24)).strftime("%Y%m%d")
        tomorrow_folder = temp_directory / f"{tomorrow}_future"
        tomorrow_folder.mkdir()

        # With +24 hour offset, tomorrow's folder should be found
        result = find_today_run_folders(time_offset=24, images_folder=str(temp_directory))

        assert len(result) == 1
        assert tomorrow in result[0]
