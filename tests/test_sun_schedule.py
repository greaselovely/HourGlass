"""Tests for lib/sun_schedule.py functions."""
import sys
from pathlib import Path
from datetime import time
from unittest.mock import patch, MagicMock

# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from bs4 import BeautifulSoup
from lib.sun_schedule import find_time_and_convert


class TestFindTimeAndConvert:
    """Tests for find_time_and_convert function."""

    def test_parses_time_from_valid_html(self):
        """Should correctly parse time from valid HTML structure."""
        html = """
        <table>
            <tr>
                <th>Sunrise</th>
                <td>6:30 am</td>
            </tr>
        </table>
        """
        soup = BeautifulSoup(html, 'html.parser')

        with patch('lib.sun_schedule.message_processor'):
            result = find_time_and_convert(soup, "Sunrise", "06:00:00")

        assert result == time(6, 30)

    def test_returns_default_when_element_missing(self):
        """Should return default time when search text not found."""
        html = "<table><tr><th>Other</th><td>data</td></tr></table>"
        soup = BeautifulSoup(html, 'html.parser')

        with patch('lib.sun_schedule.message_processor'):
            result = find_time_and_convert(soup, "Sunrise", "07:00:00")

        assert result == time(7, 0, 0)

    def test_handles_none_soup_gracefully(self):
        """Should return default time when soup is None."""
        with patch('lib.sun_schedule.message_processor'):
            result = find_time_and_convert(None, "Sunrise", "08:30:00")

        assert result == time(8, 30, 0)

    def test_parses_pm_times_correctly(self):
        """Should correctly handle PM times."""
        html = """
        <table>
            <tr>
                <th>Sunset</th>
                <td>7:45 pm</td>
            </tr>
        </table>
        """
        soup = BeautifulSoup(html, 'html.parser')

        with patch('lib.sun_schedule.message_processor'):
            result = find_time_and_convert(soup, "Sunset", "18:00:00")

        assert result == time(19, 45)  # 7:45 PM = 19:45
