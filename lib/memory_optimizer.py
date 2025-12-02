# memory_optimizer.py

import gc
import os
import psutil
import numpy as np
from contextlib import contextmanager
from .timelapse_core import message_processor

class MemoryOptimizer:
    """
    Memory management and performance optimization utilities for timelapse operations.
    
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
        
        
        before_memory = self._get_memory_usage()
        
        # Force garbage collection
        gc.collect()
        
        # Additional cleanup for numpy arrays
        if hasattr(np, 'clear_cache'):
            np.clear_cache()
        
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
            direction = "increased" if memory_change > 0 else "decreased"
            message_processor(
                f"Memory {direction} by {abs(memory_change):.1f}MB during {operation_name}"
            )


def monitor_resource_usage(operation_func, *args, **kwargs):
    """
    Decorator/wrapper to monitor resource usage during operations.
    
    Args:
        operation_func: Function to monitor
        *args, **kwargs: Arguments for the function
        
    Returns:
        tuple: (function_result, resource_usage_report)
    """
    
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