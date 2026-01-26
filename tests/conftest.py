"""Shared fixtures for HourGlass tests."""
import pytest
import tempfile
import shutil
from pathlib import Path
from PIL import Image


@pytest.fixture
def temp_directory():
    """Create a temporary directory that is cleaned up after the test."""
    temp_dir = tempfile.mkdtemp()
    yield Path(temp_dir)
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def sample_config():
    """Return a sample valid configuration dict."""
    return {
        'project': {
            'name': 'TestProject'
        },
        'files_and_folders': {
            'PROJECT_BASE': '/tmp/hourglass_test',
            'VIDEO_FOLDER': '/tmp/hourglass_test/videos',
            'IMAGES_FOLDER': '/tmp/hourglass_test/images',
            'LOGGING_FOLDER': '/tmp/hourglass_test/logs',
            'AUDIO_FOLDER': '/tmp/hourglass_test/audio'
        },
        'urls': {
            'IMAGE_URL': 'https://example.com/webcam.jpg',
            'WEBPAGE': 'https://example.com'
        },
        'sun': {
            'URL': 'https://example.com/sun',
            'SUNRISE': '06:00:00',
            'SUNSET': '18:00:00',
            'SUNSET_TIME_ADD': 30
        },
        'alerts': {
            'ntfy': 'https://ntfy.sh/test',
            'escalation_points': [5, 10, 20]
        },
        'user_agents': [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)',
            'Mozilla/5.0 (X11; Linux x86_64)'
        ],
        'output_symbols': {
            'success': '[+]',
            'error': '[-]'
        }
    }


@pytest.fixture
def default_config():
    """Return a config with default/empty values that needs setup."""
    return {
        'urls': {
            'IMAGE_URL': 'https://example.com/webcam.jpg',
            'WEBPAGE': 'https://example.com'
        },
        'sun': {
            'URL': ''
        }
    }


@pytest.fixture
def valid_image_file(temp_directory):
    """Create a valid test image file that's large enough (>1KB)."""
    img_path = temp_directory / "valid_image.jpg"
    # Create a larger image with more detail to ensure file size > 1KB
    img = Image.new('RGB', (800, 600), color='red')
    # Add some variation to increase file size
    for x in range(0, 800, 10):
        for y in range(0, 600, 10):
            img.putpixel((x, y), (x % 256, y % 256, (x + y) % 256))
    img.save(img_path, 'JPEG', quality=85)
    return img_path


@pytest.fixture
def corrupt_image_file(temp_directory):
    """Create a corrupt image file (invalid JPEG data)."""
    img_path = temp_directory / "corrupt_image.jpg"
    with open(img_path, 'wb') as f:
        f.write(b'not a valid jpeg file content here')
    return img_path


@pytest.fixture
def tiny_image_file(temp_directory):
    """Create a tiny file that's too small to be a valid image."""
    img_path = temp_directory / "tiny.jpg"
    with open(img_path, 'wb') as f:
        f.write(b'tiny')
    return img_path
