# timelapse_validator.py

import os
import cv2
import json
import logging
from PIL import Image
from pathlib import Path
from wurlitzer import pipes
from vla_core import message_processor

def validate_images_fast(run_images_folder, run_valid_images_file, force_revalidate=False):
    """
    Fast image validation with proper corruption detection.
    
    Enhanced to maintain speed while properly detecting corrupted images:
    - Quick file size and format checks
    - PIL integrity verification (detects corruption)
    - Actual image data loading test
    - Basic dimension validation
    
    Args:
        run_images_folder (str): Directory containing images to validate
        run_valid_images_file (str): Path to JSON file storing valid image paths
        force_revalidate (bool): If True, ignore existing validation and reprocess all images
        
    Returns:
        tuple: (list of valid image paths, count of valid images)
    """
    
    run_valid_images_file = Path(run_valid_images_file)
    run_images_folder = Path(run_images_folder)

    # Check if we can use existing validation
    if not force_revalidate and run_valid_images_file.exists() and run_valid_images_file.stat().st_size > 0:
        try:
            with open(run_valid_images_file, 'r') as file:
                valid_files = json.load(file)
                
                # Verify that the files still exist (quick check)
                existing_files = [f for f in valid_files if Path(f).exists()]
                if len(existing_files) == len(valid_files):
                    message_processor("Existing validation used (fast)", print_me=True)
                    return existing_files, len(existing_files)
                else:
                    message_processor(f"Some validated files missing, revalidating ({len(valid_files) - len(existing_files)} missing)")
        except json.JSONDecodeError:
            message_processor("Error decoding validation JSON, revalidating", "warning")

    # Get all JPG files and sort them
    images = sorted([img for img in os.listdir(run_images_folder) if img.lower().endswith(('.jpg', '.jpeg'))])
    
    if not images:
        message_processor("No image files found to validate", "warning")
        return [], 0

    valid_files = []
    processed_count = 0
    skipped_count = 0
    corruption_count = 0
    
    message_processor(f"Enhanced fast validating {len(images)} images...")
    
    for n, image in enumerate(images, 1):
        # Progress indicator every 100 images
        if n % 100 == 0:
            print(f"[i]\tValidated {n}/{len(images)}", end='\r')
        
        full_image_path = run_images_folder / image
        
        try:
            # Quick size check - skip tiny files
            file_size = full_image_path.stat().st_size
            if file_size < 1024:  # Less than 1KB is probably not a valid image
                skipped_count += 1
                continue
            
            # Enhanced PIL validation with corruption detection
            try:
                # First, verify the image integrity
                with Image.open(full_image_path) as img:
                    img.verify()  # This checks the image data integrity
                
                # If verify() passes, reopen and test actual loading
                # (verify() consumes the image, so we need to reopen)
                with Image.open(full_image_path) as img:
                    # Force loading of image data to catch corruption
                    img.load()
                    width, height = img.size
                    
                    # Validate reasonable dimensions
                    if width > 0 and height > 0 and width < 20000 and height < 20000:
                        # Additional check: try to get a pixel to ensure data is accessible
                        try:
                            _ = img.getpixel((0, 0))  # Test pixel access
                            valid_files.append(str(full_image_path))
                            processed_count += 1
                        except Exception:
                            # Pixel access failed - image is corrupted
                            corruption_count += 1
                            logging.debug(f"Corrupted image data (pixel access failed): {image}")
                    else:
                        skipped_count += 1
                        logging.debug(f"Invalid dimensions {width}x{height}: {image}")
                        
            except (OSError, IOError, Image.UnidentifiedImageError) as e:
                # PIL couldn't open/process the image or detected corruption
                corruption_count += 1
                logging.debug(f"PIL validation failed for {image}: {e}")
                continue
                
        except (OSError, IOError) as e:
            # File system error
            skipped_count += 1
            logging.debug(f"File system error for {image}: {e}")
            continue
        except Exception as e:
            # Unexpected error
            corruption_count += 1
            logging.warning(f"Unexpected validation error for {image}: {e}")
            continue

    # Clear progress line
    print(" " * 50, end='\r')
    
    # Save the valid image paths to JSON file
    try:
        with open(run_valid_images_file, 'w') as file:
            json.dump(valid_files, file, indent=2)
        message_processor(f"Enhanced validation complete: {processed_count} valid, {skipped_count} skipped, {corruption_count} corrupted")
    except Exception as e:
        message_processor(f"Error saving validation results: {e}", "error")

    return valid_files, len(valid_files)


def validate_images_thorough(run_images_folder, run_valid_images_file):
    """
    Thorough image validation using OpenCV (original method).
    Use this if fast validation is giving false positives.
    
    Args:
        run_images_folder (str): Directory containing images to validate
        run_valid_images_file (str): Path to JSON file storing valid image paths
        
    Returns:
        tuple: (list of valid image paths, count of valid images)
    """

    
    run_valid_images_file = Path(run_valid_images_file)
    run_images_folder = Path(run_images_folder)

    # Check existing validation
    if run_valid_images_file.exists() and run_valid_images_file.stat().st_size > 0:
        try:
            with open(run_valid_images_file, 'r') as file:
                valid_files = json.load(file)
                message_processor("Existing thorough validation used", print_me=True)
                return valid_files, len(valid_files)
        except json.JSONDecodeError:
            message_processor("Error decoding JSON, revalidating with OpenCV", "error")
    
    images = sorted([img for img in os.listdir(run_images_folder) if img.endswith(".jpg")])
    images_dict = {}
    
    message_processor(f"Thorough validation of {len(images)} images using OpenCV...")
    
    for n, image in enumerate(images, 1):
        print(f"[i]\t{n}/{len(images)}", end='\r')
        full_image = Path(run_images_folder) / image
        
        with pipes() as (out, err):
            img = cv2.imread(str(full_image))
        err.seek(0)
        error_message = err.read()
        
        if error_message == "":
            images_dict[str(full_image)] = error_message

    valid_files = list(images_dict.keys())
    
    # Save validation results
    with open(run_valid_images_file, 'w') as file:
        json.dump(valid_files, file, indent=2)

    message_processor(f"Thorough validation complete: {len(valid_files)} valid images")
    return valid_files, len(valid_files)


def get_validation_stats(run_images_folder):
    """
    Get statistics about images in a folder without full validation.
    Useful for quick health checks.
    
    Args:
        run_images_folder (str): Directory to analyze
        
    Returns:
        dict: Statistics about the image folder
    """
    folder_path = Path(run_images_folder)
    
    if not folder_path.exists():
        return {"error": "Folder does not exist"}
    
    all_files = list(folder_path.iterdir())
    jpg_files = [f for f in all_files if f.suffix.lower() in ['.jpg', '.jpeg']]
    
    total_size = sum(f.stat().st_size for f in jpg_files if f.is_file())
    
    size_stats = {
        'total_files': len(all_files),
        'jpg_files': len(jpg_files),
        'total_size_mb': round(total_size / (1024 * 1024), 2),
        'avg_size_kb': round((total_size / len(jpg_files)) / 1024, 2) if jpg_files else 0
    }
    
    if jpg_files:
        file_sizes = [f.stat().st_size for f in jpg_files]
        size_stats.update({
            'min_size_kb': round(min(file_sizes) / 1024, 2),
            'max_size_kb': round(max(file_sizes) / 1024, 2)
        })
    
    return size_stats


# Compatibility function to maintain API
def validate_images(run_images_folder, run_valid_images_file, use_fast=True):
    """
    Main validation function with option to use fast or thorough validation.
    Drop-in replacement for the original validate_images function.
    
    Args:
        run_images_folder (str): Directory containing images
        run_valid_images_file (str): Path to validation JSON file
        use_fast (bool): If True, use fast validation; if False, use thorough OpenCV validation
        
    Returns:
        tuple: (list of valid image paths, count of valid images)
    """
    if use_fast:
        return validate_images_fast(run_images_folder, run_valid_images_file)
    else:
        return validate_images_thorough(run_images_folder, run_valid_images_file)