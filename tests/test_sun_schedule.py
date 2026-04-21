"""Tests for lib/sun_schedule.py functions."""
import sys
from pathlib import Path
from datetime import time
from unittest.mock import patch, MagicMock
import pytest

# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from lib.sun_schedule import (
    extract_coords_from_url,
    get_sun_times,
    get_sun_time,
    find_time_and_convert,
    sun_schedule,
)


class TestExtractCoordsFromUrl:
    """Tests for extract_coords_from_url function."""

    def test_extracts_from_timeanddate_url(self):
        """Should extract coords from timeanddate.com URL."""
        url = "https://www.timeanddate.com/sun/@34.0788,-107.6166"
        lat, lng = extract_coords_from_url(url)
        assert lat == 34.0788
        assert lng == -107.6166

    def test_extracts_from_google_maps_at_format(self):
        """Should extract coords from Google Maps @ format."""
        url = "https://www.google.com/maps/@34.0788,-107.6166,15z"
        lat, lng = extract_coords_from_url(url)
        assert lat == 34.0788
        assert lng == -107.6166

    def test_extracts_from_google_maps_place_format(self):
        """Should extract coords from Google Maps place format."""
        url = "https://www.google.com/maps/place/Some+Place/@34.0788,-107.6166,17z/data=..."
        lat, lng = extract_coords_from_url(url)
        assert lat == 34.0788
        assert lng == -107.6166

    def test_extracts_from_google_maps_query_format(self):
        """Should extract coords from Google Maps query format."""
        url = "https://maps.google.com/?q=34.0788,-107.6166"
        lat, lng = extract_coords_from_url(url)
        assert lat == 34.0788
        assert lng == -107.6166

    def test_extracts_from_google_maps_ll_format(self):
        """Should extract coords from Google Maps ll format."""
        url = "https://www.google.com/maps?ll=34.0788,-107.6166&q=Some+Place"
        lat, lng = extract_coords_from_url(url)
        assert lat == 34.0788
        assert lng == -107.6166

    def test_handles_negative_coordinates(self):
        """Should handle negative latitude and longitude."""
        url = "https://www.google.com/maps/@-33.8688,151.2093,15z"
        lat, lng = extract_coords_from_url(url)
        assert lat == -33.8688
        assert lng == 151.2093

    def test_returns_none_for_invalid_url(self):
        """Should return None, None for URL without coordinates."""
        url = "https://www.example.com/no-coords-here"
        lat, lng = extract_coords_from_url(url)
        assert lat is None
        assert lng is None

    def test_returns_none_for_empty_url(self):
        """Should return None, None for empty URL."""
        lat, lng = extract_coords_from_url("")
        assert lat is None
        assert lng is None

    def test_returns_none_for_none_input(self):
        """Should return None, None for None input."""
        lat, lng = extract_coords_from_url(None)
        assert lat is None
        assert lng is None

    def test_rejects_invalid_latitude(self):
        """Should reject latitude outside -90 to 90 range."""
        url = "https://www.google.com/maps/@91.0,-107.0,15z"
        lat, lng = extract_coords_from_url(url)
        assert lat is None
        assert lng is None

    def test_rejects_invalid_longitude(self):
        """Should reject longitude outside -180 to 180 range."""
        url = "https://www.google.com/maps/@34.0,181.0,15z"
        lat, lng = extract_coords_from_url(url)
        assert lat is None
        assert lng is None


class TestGetSunTimes:
    """Tests for get_sun_times function."""

    @patch('lib.sun_schedule.requests.get')
    def test_returns_sun_times_on_success(self, mock_get):
        """Should return parsed sun times on successful API call."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            'status': 'OK',
            'results': {
                'sunrise': '2025-01-15T13:30:00+00:00',
                'sunset': '2025-01-16T00:45:00+00:00',
                'solar_noon': '2025-01-15T19:07:30+00:00',
                'day_length': 40500,
            }
        }
        mock_get.return_value = mock_response

        with patch('lib.sun_schedule.message_processor'):
            result = get_sun_times(34.0788, -107.6166)

        assert result is not None
        assert 'sunrise' in result
        assert 'sunset' in result
        assert result['sunrise'] == time(13, 30, 0)
        assert result['sunset'] == time(0, 45, 0)
        assert result['day_length'] == 40500

    @patch('lib.sun_schedule.requests.get')
    def test_returns_none_on_api_error(self, mock_get):
        """Should return None when API returns error status."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            'status': 'INVALID_REQUEST',
            'results': {}
        }
        mock_get.return_value = mock_response

        with patch('lib.sun_schedule.message_processor'):
            result = get_sun_times(34.0788, -107.6166)

        assert result is None

    @patch('lib.sun_schedule.requests.get')
    def test_returns_none_on_request_exception(self, mock_get):
        """Should return None on network error."""
        import requests
        mock_get.side_effect = requests.RequestException("Network error")

        with patch('lib.sun_schedule.message_processor'):
            result = get_sun_times(34.0788, -107.6166)

        assert result is None

    def test_returns_none_for_invalid_coordinates(self):
        """Should return None for out-of-range coordinates."""
        with patch('lib.sun_schedule.message_processor'):
            result = get_sun_times(91.0, -107.0)
        assert result is None

        with patch('lib.sun_schedule.message_processor'):
            result = get_sun_times(34.0, 181.0)
        assert result is None

    def test_returns_none_for_none_coordinates(self):
        """Should return None when coordinates are None."""
        with patch('lib.sun_schedule.message_processor'):
            result = get_sun_times(None, None)
        assert result is None


class TestGetSunTime:
    """Tests for get_sun_time function."""

    def test_returns_time_from_dict(self):
        """Should return time from sun_times dict."""
        sun_times = {
            'sunrise': time(6, 30, 0),
            'sunset': time(19, 45, 0),
        }

        with patch('lib.sun_schedule.message_processor'):
            result = get_sun_time(sun_times, 'sunrise', '06:00:00')

        assert result == time(6, 30, 0)

    def test_returns_default_when_field_missing(self):
        """Should return default time when field not in dict."""
        sun_times = {'sunrise': time(6, 30, 0)}

        with patch('lib.sun_schedule.message_processor'):
            result = get_sun_time(sun_times, 'sunset', '19:00:00')

        assert result == time(19, 0, 0)

    def test_returns_default_when_sun_times_none(self):
        """Should return default time when sun_times is None."""
        with patch('lib.sun_schedule.message_processor'):
            result = get_sun_time(None, 'sunrise', '07:00:00')

        assert result == time(7, 0, 0)


class TestFindTimeAndConvert:
    """Tests for find_time_and_convert function."""

    def test_handles_dict_format(self):
        """Should extract time from dict format."""
        sun_times = {
            'sunrise': time(6, 30, 0),
            'sunset': time(19, 45, 0),
        }

        with patch('lib.sun_schedule.message_processor'):
            result = find_time_and_convert(sun_times, 'sunrise', '06:00:00')

        assert result == time(6, 30, 0)

    def test_handles_legacy_text_format_in_dict_mode(self):
        """Should strip 'Today:' suffix when using dict format."""
        sun_times = {
            'sunrise': time(6, 30, 0),
            'sunset': time(19, 45, 0),
        }

        with patch('lib.sun_schedule.message_processor'):
            result = find_time_and_convert(sun_times, 'Sunrise Today:', '06:00:00')

        assert result == time(6, 30, 0)

    def test_returns_default_when_none(self):
        """Should return default time when sun_times is None."""
        with patch('lib.sun_schedule.message_processor'):
            result = find_time_and_convert(None, 'sunrise', '08:30:00')

        assert result == time(8, 30, 0)

    def test_returns_default_when_field_missing(self):
        """Should return default time when field not found."""
        sun_times = {'sunrise': time(6, 30, 0)}

        with patch('lib.sun_schedule.message_processor'):
            result = find_time_and_convert(sun_times, 'sunset', '19:00:00')

        assert result == time(19, 0, 0)


class TestSunScheduleLegacy:
    """Tests for legacy sun_schedule function."""

    @patch('lib.sun_schedule.get_sun_times')
    def test_extracts_coords_and_calls_api(self, mock_get_sun_times):
        """Should extract coords from URL and call API."""
        mock_get_sun_times.return_value = {'sunrise': time(6, 30, 0)}

        url = "https://www.timeanddate.com/sun/@34.0788,-107.6166"
        result = sun_schedule(url)

        mock_get_sun_times.assert_called_once_with(34.0788, -107.6166)
        assert result == {'sunrise': time(6, 30, 0)}

    def test_returns_none_for_url_without_coords(self):
        """Should return None when URL has no extractable coords."""
        url = "https://www.timeanddate.com/sun/usa/new-york"
        result = sun_schedule(url)
        assert result is None

    def test_returns_none_for_empty_url(self):
        """Should return None for empty URL."""
        result = sun_schedule("")
        assert result is None
