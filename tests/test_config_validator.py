"""Tests for lib/config_validator.py."""
import sys
from pathlib import Path

# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from lib.config_validator import ConfigValidator


class TestValidateUrls:
    """Tests for URL validation in ConfigValidator."""

    def test_valid_urls_accepted(self, sample_config):
        """Valid URLs should pass validation without errors."""
        validator = ConfigValidator()
        validator.validation_errors = []
        validator.validation_warnings = []

        validator._validate_urls(sample_config)

        # Should have no URL-related errors
        url_errors = [e for e in validator.validation_errors if 'URL' in e]
        assert len(url_errors) == 0

    def test_empty_url_generates_warning(self):
        """Empty URLs should generate warnings."""
        validator = ConfigValidator()
        validator.validation_errors = []
        validator.validation_warnings = []

        config = {'urls': {'IMAGE_URL': '', 'WEBPAGE': 'https://example.com'}}
        validator._validate_urls(config)

        assert any('empty' in w.lower() for w in validator.validation_warnings)

    def test_invalid_url_format_generates_error(self):
        """Malformed URLs should generate errors."""
        validator = ConfigValidator()
        validator.validation_errors = []
        validator.validation_warnings = []

        config = {'urls': {'IMAGE_URL': 'not-a-valid-url', 'WEBPAGE': 'also invalid'}}
        validator._validate_urls(config)

        assert len(validator.validation_errors) >= 2
        assert any('Invalid URL format' in e for e in validator.validation_errors)

    def test_missing_urls_section_handled(self):
        """Missing urls section should be handled gracefully."""
        validator = ConfigValidator()
        validator.validation_errors = []
        validator.validation_warnings = []

        config = {}  # No urls section
        validator._validate_urls(config)

        # Should not crash, just return
        assert True


class TestValidateSunSettings:
    """Tests for sun settings validation in ConfigValidator."""

    def test_valid_time_format_accepted(self, sample_config):
        """Valid HH:MM:SS times should pass validation."""
        validator = ConfigValidator()
        validator.validation_errors = []
        validator.validation_warnings = []

        validator._validate_sun_settings(sample_config)

        time_errors = [e for e in validator.validation_errors if 'time format' in e.lower()]
        assert len(time_errors) == 0

    def test_invalid_time_format_generates_error(self):
        """Invalid time formats should generate errors."""
        validator = ConfigValidator()
        validator.validation_errors = []
        validator.validation_warnings = []

        config = {
            'sun': {
                'SUNRISE': '6:00',  # Missing seconds
                'SUNSET': '25:00:00'  # Invalid hour
            }
        }
        validator._validate_sun_settings(config)

        assert len(validator.validation_errors) >= 1
        assert any('Invalid time format' in e for e in validator.validation_errors)

    def test_unusual_sunset_add_generates_warning(self):
        """Unusual SUNSET_TIME_ADD values should generate warnings."""
        validator = ConfigValidator()
        validator.validation_errors = []
        validator.validation_warnings = []

        config = {
            'sun': {
                'SUNSET_TIME_ADD': 500  # Way too high
            }
        }
        validator._validate_sun_settings(config)

        assert any('unusual' in w.lower() for w in validator.validation_warnings)
