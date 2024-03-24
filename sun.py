import requests
from bs4 import BeautifulSoup
import re
from datetime import datetime

# Function to fetch HTML content from a URL
def fetch_html(url):
    response = requests.get(url)
    if response.status_code == 200:
        return response.text
    else:
        return None

# Function to find and extract just the time, and convert it to a datetime object
def find_time_and_convert(soup, text):
    element = soup.find('th', string=lambda x: x and text in x)
    if element and element.find_next_sibling('td'):
        time_text = element.find_next_sibling('td').text
        # Use regex to extract just the time part
        time_match = re.search(r'\d+:\d+\s(?:am|pm)', time_text)
        if time_match:
            # Convert the time string into a datetime object
            return datetime.strptime(time_match.group(), '%I:%M %p').time()
    return None

# URL to fetch
url = "https://www.timeanddate.com/sun/@5481136"

# Fetch HTML content from the URL
html_content = fetch_html(url)

if html_content:
    # Parse the HTML
    soup = BeautifulSoup(html_content, 'html.parser')

    # Extract and convert times
    sunrise_time = find_time_and_convert(soup, 'Sunrise Today:')
    sunset_time = find_time_and_convert(soup, 'Sunset Today:')

    # Get the current time
    now = datetime.now().time()

    # Check if the current time is between sunrise and sunset
    if sunrise_time and sunset_time and sunrise_time < now < sunset_time:
        print(f"The current time ({now}) is between {sunrise_time} and {sunset_time}.")
    else:
        print(f"The current time ({now}) is between {sunrise_time} and {sunset_time}.")
else:
    print("Failed to fetch the webpage.")
