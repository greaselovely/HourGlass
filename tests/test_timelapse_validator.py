"""Tests for lib/timelapse_validator.py functions."""
import json
import sys
from pathlib import Path
from unittest.mock import patch

# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))


class TestValidateImagesFast:
    """Tests for validate_images_fast function."""

    def test_validates_good_images(self, temp_directory, valid_image_file):
        """Should identify valid images correctly."""
        from lib.timelapse_validator import validate_images_fast

        # Create a folder with the valid image
        images_folder = temp_directory / "images"
        images_folder.mkdir()

        # Copy valid image to folder
        import shutil
        dest_image = images_folder / "valid.jpg"
        shutil.copy(valid_image_file, dest_image)

        validation_file = temp_directory / "valid_images.json"

        with patch('lib.timelapse_validator.message_processor'):
            valid_files, count = validate_images_fast(
                str(images_folder),
                str(validation_file),
                force_revalidate=True
            )

        assert count == 1
        assert len(valid_files) == 1
        assert "valid.jpg" in valid_files[0]

    def test_rejects_corrupt_images(self, temp_directory, corrupt_image_file):
        """Should reject corrupted image files."""
        from lib.timelapse_validator import validate_images_fast

        # Create a folder with the corrupt image
        images_folder = temp_directory / "images"
        images_folder.mkdir()

        import shutil
        dest_image = images_folder / "corrupt.jpg"
        shutil.copy(corrupt_image_file, dest_image)

        validation_file = temp_directory / "valid_images.json"

        with patch('lib.timelapse_validator.message_processor'):
            valid_files, count = validate_images_fast(
                str(images_folder),
                str(validation_file),
                force_revalidate=True
            )

        assert count == 0
        assert len(valid_files) == 0

    def test_skips_tiny_files(self, temp_directory, tiny_image_file):
        """Should skip files smaller than 1KB."""
        from lib.timelapse_validator import validate_images_fast

        images_folder = temp_directory / "images"
        images_folder.mkdir()

        import shutil
        dest_image = images_folder / "tiny.jpg"
        shutil.copy(tiny_image_file, dest_image)

        validation_file = temp_directory / "valid_images.json"

        with patch('lib.timelapse_validator.message_processor'):
            valid_files, count = validate_images_fast(
                str(images_folder),
                str(validation_file),
                force_revalidate=True
            )

        assert count == 0

    def test_uses_cached_validation(self, temp_directory, valid_image_file):
        """Should use cached validation results when available."""
        from lib.timelapse_validator import validate_images_fast

        images_folder = temp_directory / "images"
        images_folder.mkdir()

        import shutil
        dest_image = images_folder / "cached.jpg"
        shutil.copy(valid_image_file, dest_image)

        validation_file = temp_directory / "valid_images.json"

        # Pre-populate the validation cache
        with open(validation_file, 'w') as f:
            json.dump([str(dest_image)], f)

        with patch('lib.timelapse_validator.message_processor') as mock_msg:
            valid_files, count = validate_images_fast(
                str(images_folder),
                str(validation_file),
                force_revalidate=False
            )

        assert count == 1
        # Should have used existing validation (fast path)
        assert any('Existing validation' in str(call) for call in mock_msg.call_args_list)
