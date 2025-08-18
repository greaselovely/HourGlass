import os
import hashlib
from datetime import datetime
from pathlib import Path

folder_path = "/path/updated/here"

def compute_hash(file_path):
    """Compute SHA256 hash of a file."""
    sha256_hash = hashlib.sha256()
    with file_path.open("rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()

def check_and_remove_duplicate_images(folder_path):
    """Check for duplicate images based on SHA256 hash and remove the second duplicate."""
    folder_path = Path(folder_path)
    if not folder_path.is_dir():
        print(f"Error: {folder_path} is not a valid directory.")
        return []

    # Get all jpg files in the folder
    from timelapse_config import IMAGE_PATTERN
    image_files = sorted(folder_path.glob(IMAGE_PATTERN))
    
    # Filter and sort files based on the specific naming pattern
    valid_files = []
    for file in image_files:
        try:
            # Parse the date and time from the filename
            # This will need to be adapted based on the project's filename format
            from timelapse_config import PROJECT_NAME
            datetime.strptime(file.stem, f'{PROJECT_NAME}.%d%m%Y.%H%M%S')
            valid_files.append(file)
        except ValueError:
            # Skip files that don't match the expected format
            continue
    
    valid_files.sort()
    
    removed_files = []
    for i in range(len(valid_files) - 1):
        current_file = valid_files[i]
        next_file = valid_files[i + 1]
        
        if not current_file.exists() or not next_file.exists():
            print(f"Warning: File not found - {current_file if not current_file.exists() else next_file}")
            continue

        current_hash = compute_hash(current_file)
        next_hash = compute_hash(next_file)
        
        if current_hash == next_hash:
            # Remove the second file
            next_file.unlink()
            removed_files.append(next_file)
            print(f"Removed duplicate file: {next_file.name}")
    
    return removed_files

def main():
    removed_files = check_and_remove_duplicate_images(folder_path)
    
    if removed_files:
        print(f"\nRemoved {len(removed_files)} duplicate images:")
        for file in removed_files:
            print(f"- {file.name}")
    else:
        print("No duplicate images found.")

if __name__ == "__main__":
    main()