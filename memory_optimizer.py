# memory_optimizer.py

import gc
import os
import sys
import psutil
import logging
import numpy as np
from pathlib import Path
from contextlib import contextmanager
from moviepy.editor import ImageSequenceClip, AudioFileClip, concatenate_videoclips, concatenate_audioclips


class MemoryOptimizer:
    """
    Memory management and performance optimization utilities for VLA operations.
    
    Features:
    - Memory usage monitoring
    - Automatic garbage collection
    - Resource cleanup
    - Performance profiling
    - Memory leak detection
    """
    
    def __init__(self, memory_threshold_mb=1000, cleanup_interval=50):
        """
        Initialize memory optimizer.
        
        Args:
            memory_threshold_mb (int): Memory threshold in MB to trigger cleanup
            cleanup_interval (int): Number of operations between automatic cleanups
        """
        self.memory_threshold_mb = memory_threshold_mb
        self.cleanup_interval = cleanup_interval
        self.operation_count = 0
        self.initial_memory = self._get_memory_usage()
        self.peak_memory = self.initial_memory
        
    def _get_memory_usage(self):
        """Get current memory usage in MB."""
        try:
            process = psutil.Process(os.getpid())
            return process.memory_info().rss / 1024 / 1024  # Convert to MB
        except Exception:
            return 0
    
    def _get_system_memory_info(self):
        """Get system memory information."""
        try:
            memory = psutil.virtual_memory()
            return {
                'total_gb': round(memory.total / (1024**3), 2),
                'available_gb': round(memory.available / (1024**3), 2),
                'percent_used': memory.percent,
                'free_gb': round(memory.free / (1024**3), 2)
            }
        except Exception:
            return {}
    
    def check_memory_usage(self, operation_name=""):
        """
        Check current memory usage and trigger cleanup if needed.
        
        Args:
            operation_name (str): Name of the operation for logging
            
        Returns:
            dict: Memory usage information
        """
        current_memory = self._get_memory_usage()
        self.peak_memory = max(self.peak_memory, current_memory)
        
        memory_info = {
            'current_mb': round(current_memory, 2),
            'peak_mb': round(self.peak_memory, 2),
            'increase_mb': round(current_memory - self.initial_memory, 2),
            'operation': operation_name
        }
        
        # Trigger cleanup if memory usage is high
        if current_memory > self.memory_threshold_mb:
            self.force_cleanup(f"Memory threshold exceeded: {current_memory:.1f}MB")
            memory_info['cleanup_triggered'] = True
        
        # Periodic cleanup
        self.operation_count += 1
        if self.operation_count >= self.cleanup_interval:
            self.periodic_cleanup()
            self.operation_count = 0
            memory_info['periodic_cleanup'] = True
            
        return memory_info
    
    def force_cleanup(self, reason="Manual cleanup"):
        """
        Force garbage collection and memory cleanup.
        
        Args:
            reason (str): Reason for cleanup (for logging)
        """
        from vla_core import message_processor
        
        before_memory = self._get_memory_usage()
        
        # Force garbage collection
        gc.collect()
        
        # Additional cleanup for numpy arrays
        try:
            import numpy as np
            # Clear numpy cache if it exists
            if hasattr(np, 'clear_cache'):
                np.clear_cache()
        except ImportError:
            pass
        
        after_memory = self._get_memory_usage()
        freed_mb = before_memory - after_memory
        
        if freed_mb > 5:  # Only log if significant memory was freed
            message_processor(
                f"Memory cleanup: {reason}. Freed {freed_mb:.1f}MB "
                f"({before_memory:.1f}MB → {after_memory:.1f}MB)"
            )
    
    def periodic_cleanup(self):
        """Perform periodic light cleanup."""
        gc.collect()
    
    def get_memory_report(self):
        """
        Generate a comprehensive memory usage report.
        
        Returns:
            dict: Detailed memory report
        """
        current_memory = self._get_memory_usage()
        system_info = self._get_system_memory_info()
        
        return {
            'process_memory': {
                'current_mb': round(current_memory, 2),
                'peak_mb': round(self.peak_memory, 2),
                'initial_mb': round(self.initial_memory, 2),
                'increase_mb': round(current_memory - self.initial_memory, 2)
            },
            'system_memory': system_info,
            'gc_stats': {
                'collections': gc.get_count(),
                'thresholds': gc.get_threshold()
            }
        }


@contextmanager
def memory_managed_operation(operation_name="", force_cleanup_after=True):
    """
    Context manager for memory-managed operations.
    
    Args:
        operation_name (str): Name of the operation for logging
        force_cleanup_after (bool): Whether to force cleanup after operation
        
    Usage:
        with memory_managed_operation("video_creation"):
            create_time_lapse(...)
    """
    optimizer = MemoryOptimizer()
    
    try:
        before_info = optimizer.check_memory_usage(f"Before {operation_name}")
        yield optimizer
    finally:
        if force_cleanup_after:
            optimizer.force_cleanup(f"After {operation_name}")
        
        after_info = optimizer.check_memory_usage(f"After {operation_name}")
        
        # Log significant memory changes
        memory_change = after_info['current_mb'] - before_info['current_mb']
        if abs(memory_change) > 50:  # Log changes > 50MB
            from vla_core import message_processor
            direction = "increased" if memory_change > 0 else "decreased"
            message_processor(
                f"Memory {direction} by {abs(memory_change):.1f}MB during {operation_name}"
            )


def optimized_create_time_lapse(valid_files, video_path, fps, audio_input, 
                              crossfade_seconds=3, end_black_seconds=3, 
                              chunk_size=1000):
    """
    Memory-optimized version of create_time_lapse for large image sets.
    
    Args:
        valid_files (list): List of image file paths
        video_path (str): Output video path
        fps (int): Frames per second
        audio_input: Audio input (file path or AudioClip)
        crossfade_seconds (int): Crossfade duration
        end_black_seconds (int): Black screen duration at end
        chunk_size (int): Number of images to process at once
    """
    from vla_core import CustomLogger, message_processor
    
    with memory_managed_operation("optimized_time_lapse_creation") as optimizer:
        logger = CustomLogger()
        
        try:
            message_processor(f"Creating optimized time-lapse with {len(valid_files)} images")
            
            # Process images in chunks for large datasets
            if len(valid_files) > chunk_size:
                message_processor(f"Large dataset detected, processing in chunks of {chunk_size}")
                video_clips = []
                
                for i in range(0, len(valid_files), chunk_size):
                    chunk_files = valid_files[i:i + chunk_size]
                    message_processor(f"Processing chunk {i//chunk_size + 1}/{(len(valid_files) + chunk_size - 1)//chunk_size}")
                    
                    # Create clip for this chunk
                    chunk_clip = ImageSequenceClip(chunk_files, fps=fps)
                    video_clips.append(chunk_clip)
                    
                    # Check memory after each chunk
                    memory_info = optimizer.check_memory_usage(f"chunk_{i//chunk_size + 1}")
                    if memory_info.get('cleanup_triggered'):
                        message_processor("Memory cleanup triggered during chunk processing")
                
                # Concatenate all chunks
                message_processor("Concatenating video chunks")
                video_clip = concatenate_videoclips(video_clips)
                
                # Clean up individual chunks
                for clip in video_clips:
                    clip.close()
                del video_clips
                gc.collect()
                
            else:
                # Standard processing for smaller datasets
                video_clip = ImageSequenceClip(valid_files, fps=fps)
            
            # Process audio
            message_processor("Processing Audio")
            if isinstance(audio_input, str):
                audio_clip = AudioFileClip(audio_input)
            elif hasattr(audio_input, 'audio_fadein'):
                audio_clip = audio_input
            else:
                raise ValueError("Invalid audio input")
            
            # Check memory after audio loading
            optimizer.check_memory_usage("after_audio_load")
            
            # Sync audio and video
            message_processor(f"Video duration: {video_clip.duration}, Audio duration: {audio_clip.duration}")
            
            if audio_clip.duration < video_clip.duration:
                message_processor("Audio is shorter than video. Looping audio.", "warning")
                audio_clip = audio_clip.loop(duration=video_clip.duration)
            else:
                audio_clip = audio_clip.subclip(0, video_clip.duration)
            
            # Apply effects
            message_processor("Applying Audio and Video Effects")
            audio_clip = audio_clip.audio_fadein(crossfade_seconds).audio_fadeout(crossfade_seconds)
            video_clip = video_clip.set_audio(audio_clip)
            video_clip = video_clip.fadein(crossfade_seconds).fadeout(crossfade_seconds)
            
            # Add end frame
            message_processor("Creating End Frame")
            black_frame = np.zeros((video_clip.h, video_clip.w, 3), dtype=np.uint8)
            black_frame_clip = ImageSequenceClip([black_frame], fps=fps).set_duration(end_black_seconds)
            
            # Final concatenation
            message_processor("Final Video Assembly")
            final_clip = concatenate_videoclips([video_clip, black_frame_clip])
            
            # Check memory before writing
            memory_info = optimizer.check_memory_usage("before_video_write")
            message_processor(f"Memory usage before write: {memory_info['current_mb']:.1f}MB")
            
            # Write video
            message_processor("Writing Video File")
            final_clip.write_videofile(
                video_path, 
                codec="libx264", 
                audio_codec="aac", 
                logger=logger,
                temp_audiofile='temp-audio.m4a',
                remove_temp=True
            )
            
        except Exception as e:
            error_message = f"Error in optimized_create_time_lapse: {str(e)}"
            logging.error(error_message)
            message_processor(error_message, "error", ntfy=True)
            raise
        
        finally:
            # Ensure all clips are properly closed
            message_processor("Cleaning up video resources")
            try:
                if 'video_clip' in locals():
                    video_clip.close()
                if 'audio_clip' in locals():
                    audio_clip.close()
                if 'final_clip' in locals():
                    final_clip.close()
                if 'black_frame_clip' in locals():
                    black_frame_clip.close()
            except Exception as close_error:
                message_processor(f"Error closing clips: {str(close_error)}", "warning")
            
            # Force cleanup
            optimizer.force_cleanup("video_creation_complete")
    
    message_processor(f"Optimized time-lapse saved: {video_path}")


def get_system_performance_info():
    """
    Get comprehensive system performance information.
    
    Returns:
        dict: System performance metrics
    """
    try:
        cpu_percent = psutil.cpu_percent(interval=1)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        
        return {
            'cpu': {
                'percent': cpu_percent,
                'count': psutil.cpu_count(),
                'freq_mhz': psutil.cpu_freq().current if psutil.cpu_freq() else None
            },
            'memory': {
                'total_gb': round(memory.total / (1024**3), 2),
                'available_gb': round(memory.available / (1024**3), 2),
                'percent_used': memory.percent
            },
            'disk': {
                'total_gb': round(disk.total / (1024**3), 2),
                'free_gb': round(disk.free / (1024**3), 2),
                'percent_used': round((disk.used / disk.total) * 100, 2)
            }
        }
    except Exception as e:
        return {'error': f"Failed to get performance info: {e}"}


def monitor_resource_usage(operation_func, *args, **kwargs):
    """
    Decorator/wrapper to monitor resource usage during operations.
    
    Args:
        operation_func: Function to monitor
        *args, **kwargs: Arguments for the function
        
    Returns:
        tuple: (function_result, resource_usage_report)
    """
    from vla_core import message_processor
    
    # Get initial state
    start_time = psutil.time.time()
    start_memory = psutil.Process().memory_info().rss / 1024 / 1024
    start_cpu = psutil.cpu_percent()
    
    try:
        # Execute function
        result = operation_func(*args, **kwargs)
        
        # Get final state
        end_time = psutil.time.time()
        end_memory = psutil.Process().memory_info().rss / 1024 / 1024
        end_cpu = psutil.cpu_percent()
        
        # Calculate metrics
        duration = end_time - start_time
        memory_change = end_memory - start_memory
        
        report = {
            'duration_seconds': round(duration, 2),
            'memory_change_mb': round(memory_change, 2),
            'peak_memory_mb': round(end_memory, 2),
            'avg_cpu_percent': round((start_cpu + end_cpu) / 2, 2),
            'success': True
        }
        
        # Log significant resource usage
        if duration > 60 or abs(memory_change) > 100:
            message_processor(
                f"Resource usage for {operation_func.__name__}: "
                f"{duration:.1f}s, {memory_change:+.1f}MB memory"
            )
        
        return result, report
        
    except Exception as e:
        end_time = psutil.time.time()
        duration = end_time - start_time
        
        report = {
            'duration_seconds': round(duration, 2),
            'error': str(e),
            'success': False
        }
        
        raise e