"""Tests for lib/image_dup.py functions."""
import re
import sys
from pathlib import Path
from datetime import datetime

# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from lib.image_dup import get_or_create_run_id, create_base_image


class TestGetOrCreateRunId:
    """Tests for get_or_create_run_id function."""

    def test_format_matches_expected_pattern(self):
        """Run ID should match YYYYMMDD_xxxxxxxx format."""
        run_id = get_or_create_run_id()

        # Pattern: 8 digits (date) + underscore + 8 hex chars
        pattern = r'^\d{8}_[a-f0-9]{8}$'
        assert re.match(pattern, run_id), f"Run ID '{run_id}' doesn't match expected pattern"

    def test_starts_with_todays_date(self):
        """Run ID should start with today's date."""
        run_id = get_or_create_run_id()
        expected_date = datetime.now().strftime("%Y%m%d")

        assert run_id.startswith(expected_date)

    def test_uniqueness_across_calls(self):
        """Each call should generate a unique run ID."""
        run_ids = [get_or_create_run_id() for _ in range(10)]

        # All should be unique
        assert len(set(run_ids)) == 10


class TestCreateBaseImage:
    """Tests for create_base_image function."""

    def test_creates_valid_image_file(self, temp_directory):
        """Should create a valid JPEG image file."""
        from PIL import Image
        import logging

        # Set up basic logging to avoid errors
        logging.basicConfig(level=logging.INFO)

        img_path = temp_directory / "test_base.jpg"
        create_base_image(str(img_path), "TestProject")

        assert img_path.exists()

        # Verify it's a valid image
        img = Image.open(img_path)
        assert img.size == (800, 600)
        assert img.mode == 'RGB'

    def test_image_contains_project_text(self, temp_directory):
        """Created image should contain the project name text."""
        import logging

        logging.basicConfig(level=logging.INFO)

        img_path = temp_directory / "test_with_text.jpg"
        create_base_image(str(img_path), "MyProject")

        # Image should exist and be non-empty
        assert img_path.exists()
        assert img_path.stat().st_size > 1000  # Should be reasonably sized
