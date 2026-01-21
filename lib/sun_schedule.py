# sun_schedule.py
"""
Sun schedule fetching functionality for timing captures based on sunrise/sunset.
"""
import re
import requests
from random import choice
from datetime import datetime
from bs4 import BeautifulSoup

from .timelapse_config import USER_AGENTS
from .utils import message_processor


def sun_schedule(SUN_URL, user_agents=None):
    """
    Fetches and parses the HTML content from the specified URL.

    Args:
        SUN_URL (str): The URL to fetch the sun schedule from.
        user_agents (list, optional): List of user agent strings. If None, uses global USER_AGENTS.

    Returns:
        BeautifulSoup object or None: Parsed HTML content if successful, None otherwise.
    """
    try:
        if user_agents is None:
            user_agents = USER_AGENTS
        if not user_agents:
            # Fallback user agent if list is empty
            user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        else:
            user_agent = choice(user_agents)
        headers = {"User-Agent": user_agent}
        response = requests.get(SUN_URL, headers=headers)
        response.raise_for_status()  # Raise an HTTPError for bad responses
        html_content = response.text
    except requests.RequestException as e:
        print(f"Error fetching the HTML content from {SUN_URL}: {e}")
        return None
    if html_content:
        return BeautifulSoup(html_content, 'html.parser')
    else:
        return


def find_time_and_convert(soup, text, default_time_str):
    """
    Finds a specific time in the parsed HTML content and converts it to a time object.

    Args:
        soup (BeautifulSoup): The parsed HTML content.
        text (str): The text to search for in the HTML.
        default_time_str (str): The default time string to use if the search fails.

    Returns:
        datetime.time: The found time or the default time.
    """
    if soup is not None:
        element = soup.find('th', string=lambda x: x and text in x)
        if element and element.find_next_sibling('td'):
            time_text = element.find_next_sibling('td').text
            time_match = re.search(r'\d+:\d+\s(?:am|pm)', time_text)
            if time_match:
                return datetime.strptime(time_match.group(), '%I:%M %p').time()
    message_processor(datetime.strptime(default_time_str, '%H:%M:%S').time())
    return datetime.strptime(default_time_str, '%H:%M:%S').time()
