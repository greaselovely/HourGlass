"""Tests for main.py functions."""
import sys
from pathlib import Path

# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from main import check_config_needs_setup


class TestCheckConfigNeedsSetup:
    """Tests for check_config_needs_setup function."""

    def test_with_default_values_returns_true(self, default_config):
        """Config with default/example values should need setup."""
        needs_setup, fields = check_config_needs_setup(default_config)

        assert needs_setup is True
        assert 'IMAGE_URL' in fields
        assert 'WEBPAGE' in fields

    def test_with_valid_config_returns_false(self):
        """Config with real URLs should not need setup."""
        config = {
            'urls': {
                'IMAGE_URL': 'https://mywebcam.com/live.jpg',
                'WEBPAGE': 'https://mywebcam.com'
            },
            'sun': {
                'URL': 'https://sunrise-sunset.org/api'
            }
        }

        needs_setup, fields = check_config_needs_setup(config)

        assert needs_setup is False
        assert len(fields) == 0

    def test_partial_config_identifies_missing_fields(self):
        """Partially configured should identify specific missing fields."""
        config = {
            'urls': {
                'IMAGE_URL': 'https://real-camera.com/feed.jpg',
                'WEBPAGE': ''  # Empty - should be flagged
            },
            'sun': {
                'URL': ''  # Empty - should be flagged as optional
            }
        }

        needs_setup, fields = check_config_needs_setup(config)

        assert needs_setup is True
        assert 'WEBPAGE' in fields
        assert 'IMAGE_URL' not in fields  # This one is valid
