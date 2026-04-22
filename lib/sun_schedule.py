# sun_schedule.py
"""
Sun schedule fetching functionality for timing captures based on sunrise/sunset.

Uses the sunrise-sunset.org API to get accurate sunrise/sunset times based on
latitude and longitude coordinates.
"""
import re
import requests
from datetime import datetime, timezone
from dateutil import parser as dateutil_parser

from .utils import message_processor


def extract_coords_from_url(url):
    """
    Extract lat/lng from various URL formats.

    Supports:
    - timeanddate.com: https://www.timeanddate.com/sun/@34.0788,-107.6166
    - Google Maps @: https://www.google.com/maps/@34.0788,-107.6166,15z
    - Google Maps place: https://www.google.com/maps/place/.../@34.0788,-107.6166,17z
    - Google Maps query: https://maps.google.com/?q=34.0788,-107.6166
    - Google Maps query with &: https://www.google.com/maps?ll=34.0788,-107.6166&q=...

    Args:
        url (str): URL that may contain coordinates

    Returns:
        tuple: (lat, lng) as floats, or (None, None) if not parseable
    """
    if not url:
        return None, None

    patterns = [
        r'@(-?\d+\.?\d*),(-?\d+\.?\d*)',      # @lat,lng format (timeanddate, Google Maps)
        r'\?q=(-?\d+\.?\d*),(-?\d+\.?\d*)',   # ?q=lat,lng format (Google Maps query)
        r'&q=(-?\d+\.?\d*),(-?\d+\.?\d*)',    # &q=lat,lng format
        r'\?ll=(-?\d+\.?\d*),(-?\d+\.?\d*)',  # ?ll=lat,lng format
        r'&ll=(-?\d+\.?\d*),(-?\d+\.?\d*)',   # &ll=lat,lng format
    ]

    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            try:
                lat = float(match.group(1))
                lng = float(match.group(2))
                # Validate coordinate ranges
                if -90 <= lat <= 90 and -180 <= lng <= 180:
                    return lat, lng
            except (ValueError, IndexError):
                continue

    return None, None


def get_sun_times(lat, lng, date=None, tzid=None):
    """
    Fetch sunrise/sunset times from sunrise-sunset.org API.

    Args:
        lat (float): Latitude coordinate (-90 to 90)
        lng (float): Longitude coordinate (-180 to 180)
        date (str, optional): Date in YYYY-MM-DD format. Defaults to today.
        tzid (str, optional): Timezone ID (e.g., 'America/New_York').
                              If not provided, times are returned in UTC.

    Returns:
        dict: Dictionary with sunrise/sunset times as datetime.time objects:
              {
                  'sunrise': datetime.time,
                  'sunset': datetime.time,
                  'solar_noon': datetime.time,
                  'day_length': int (seconds),
                  'civil_twilight_begin': datetime.time,
                  'civil_twilight_end': datetime.time,
              }
              Returns None on failure.
    """
    if lat is None or lng is None:
        message_processor("No coordinates provided for sun times", "warning")
        return None

    # Validate coordinates
    if not (-90 <= lat <= 90) or not (-180 <= lng <= 180):
        message_processor(f"Invalid coordinates: lat={lat}, lng={lng}", "error")
        return None

    # Build API request
    params = {
        'lat': lat,
        'lng': lng,
        'formatted': 0,  # ISO 8601 format
    }

    if date:
        params['date'] = date

    if tzid:
        params['tzid'] = tzid

    try:
        response = requests.get(
            'https://api.sunrise-sunset.org/json',
            params=params,
            timeout=10
        )
        response.raise_for_status()
        data = response.json()

        if data.get('status') != 'OK':
            message_processor(f"API error: {data.get('status')}", "error")
            return None

        results = data.get('results', {})

        # Parse ISO 8601 times to datetime.time objects
        sun_times = {}

        time_fields = [
            'sunrise', 'sunset', 'solar_noon',
            'civil_twilight_begin', 'civil_twilight_end',
            'nautical_twilight_begin', 'nautical_twilight_end',
            'astronomical_twilight_begin', 'astronomical_twilight_end'
        ]

        for field in time_fields:
            if field in results and results[field]:
                try:
                    # Parse ISO 8601 datetime string (UTC when tzid is not set)
                    # and convert to system local time so comparisons against
                    # datetime.now() work correctly.
                    dt = dateutil_parser.isoparse(results[field])
                    if dt.tzinfo is not None and not tzid:
                        dt = dt.astimezone()
                    sun_times[field] = dt.time()
                except (ValueError, TypeError):
                    pass

        # Day length is in seconds (integer)
        if 'day_length' in results:
            try:
                sun_times['day_length'] = int(results['day_length'])
            except (ValueError, TypeError):
                pass

        return sun_times

    except requests.RequestException as e:
        message_processor(f"Error fetching sun times: {e}", "error")
        return None
    except (ValueError, KeyError) as e:
        message_processor(f"Error parsing sun times response: {e}", "error")
        return None


def get_sun_time(sun_times, field, default_time_str):
    """
    Get a specific sun time from the sun_times dict, with fallback to default.

    Args:
        sun_times (dict or None): Result from get_sun_times()
        field (str): Field to extract ('sunrise' or 'sunset')
        default_time_str (str): Default time in HH:MM:SS format

    Returns:
        datetime.time: The sun time or default
    """
    if sun_times and field in sun_times:
        return sun_times[field]

    # Fall back to default
    message_processor(f"Using default {field} time: {default_time_str}", "warning")
    return datetime.strptime(default_time_str, '%H:%M:%S').time()


# Legacy function for backward compatibility during transition
def sun_schedule(SUN_URL, user_agents=None):
    """
    Legacy function - extracts coordinates from URL and fetches sun times.

    This function is kept for backward compatibility. New code should use
    get_sun_times() directly with lat/lng coordinates.

    Args:
        SUN_URL (str): URL containing coordinates (e.g., timeanddate.com URL)
        user_agents (list, optional): Unused, kept for API compatibility

    Returns:
        dict or None: Sun times dict if coordinates extracted, None otherwise
    """
    lat, lng = extract_coords_from_url(SUN_URL)
    if lat is not None and lng is not None:
        return get_sun_times(lat, lng)
    return None


def find_time_and_convert(sun_times_or_soup, text_or_field, default_time_str):
    """
    Extract time from sun times dict or legacy BeautifulSoup object.

    This function handles both the new API-based dict format and the legacy
    BeautifulSoup format for backward compatibility.

    Args:
        sun_times_or_soup: Either a dict from get_sun_times() or BeautifulSoup object
        text_or_field: For dict: field name ('sunrise', 'sunset')
                       For soup: text to search for (e.g., 'Sunrise Today:')
        default_time_str: Default time in HH:MM:SS format

    Returns:
        datetime.time: The extracted time or default
    """
    # Handle dict format (new API-based approach)
    if isinstance(sun_times_or_soup, dict):
        field = text_or_field.lower().replace(' today:', '').strip()
        return get_sun_time(sun_times_or_soup, field, default_time_str)

    # Handle None
    if sun_times_or_soup is None:
        message_processor(f"No sun data available, using default: {default_time_str}", "warning")
        return datetime.strptime(default_time_str, '%H:%M:%S').time()

    # Legacy BeautifulSoup handling (for backward compatibility)
    try:
        from bs4 import BeautifulSoup
        if isinstance(sun_times_or_soup, BeautifulSoup):
            element = sun_times_or_soup.find('th', string=lambda x: x and text_or_field in x)
            if element and element.find_next_sibling('td'):
                time_text = element.find_next_sibling('td').text
                time_match = re.search(r'\d+:\d+\s(?:am|pm)', time_text)
                if time_match:
                    return datetime.strptime(time_match.group(), '%I:%M %p').time()
    except ImportError:
        pass

    message_processor(f"Could not parse sun time, using default: {default_time_str}", "warning")
    return datetime.strptime(default_time_str, '%H:%M:%S').time()
