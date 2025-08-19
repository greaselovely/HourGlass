# health_monitor.py

import time
import psutil
import requests
import logging
from typing import Dict, List
from datetime import datetime
from threading import Thread, Event
from timelapse_core import message_processor
from dataclasses import dataclass, asdict


@dataclass
class HealthMetric:
    """Data class for health metrics."""
    name: str
    value: float
    threshold: float
    status: str  # 'healthy', 'warning', 'critical'
    message: str
    timestamp: datetime
    unit: str = ""


class HealthMonitor:
    """
    Comprehensive system health monitoring for timelapse operations.
    
    Monitors:
    - Disk space
    - Memory usage
    - CPU usage
    - Network connectivity
    - Process health
    - Image capture rate
    - Error rates
    """
    
    def __init__(self, config, check_interval=300):  # 5 minutes default
        """
        Initialize health monitor.
        
        Args:
            config: Timelapse configuration dictionary
            check_interval: Seconds between health checks
        """
        self.config = config
        self.check_interval = check_interval
        self.running = False
        self.stop_event = Event()
        self.monitor_thread = None
        
        # Health thresholds
        self.thresholds = {
            'disk_space_gb': 5.0,           # Warn if less than 5GB free
            'disk_space_percent': 90.0,      # Warn if more than 90% used
            'memory_percent': 85.0,          # Warn if more than 85% used
            'cpu_percent': 80.0,            # Warn if more than 80% used over time
            'error_rate_percent': 10.0,      # Warn if error rate > 10%
            'capture_rate_min': 0.5,        # Warn if < 2 images per minute
        }
        
        # Health history
        self.health_history = []
        self.max_history_size = 288  # 24 hours of 5-minute checks
        
        # Alert tracking
        self.last_alerts = {}
        self.alert_cooldown = 1800  # 30 minutes between same alerts
        
        # Performance tracking
        self.performance_stats = {
            'images_captured': 0,
            'errors_encountered': 0,
            'session_recreations': 0,
            'start_time': datetime.now(),
            'last_image_time': None
        }
        
        # Sleep status tracking
        self.is_sleeping = False
    
    def start_monitoring(self, background=True):
        """
        Start health monitoring.
        
        Args:
            background (bool): If True, run in background thread
        """
        if self.running:
            return
        
        self.running = True
        self.stop_event.clear()
        
        if background:
            self.monitor_thread = Thread(target=self._monitoring_loop, daemon=True)
            self.monitor_thread.start()
            logging.info("Health monitoring started in background")
        else:
            self._monitoring_loop()
    
    def stop_monitoring(self):
        """Stop health monitoring."""
        self.running = False
        self.stop_event.set()
        
        if self.monitor_thread and self.monitor_thread.is_alive():
            self.monitor_thread.join(timeout=5)
        
        logging.info("Health monitoring stopped")
    
    def set_sleep_status(self, is_sleeping: bool):
        """Set whether the system is in sleep mode."""
        self.is_sleeping = is_sleeping
        if is_sleeping:
            logging.info("Health monitor: System entering sleep mode")
        else:
            logging.info("Health monitor: System waking from sleep mode")
    
    def _monitoring_loop(self):
        """Main monitoring loop."""
        while self.running and not self.stop_event.is_set():
            try:
                health_report = self.perform_health_check()
                self._process_health_report(health_report)
                
                # Wait for next check or stop signal
                self.stop_event.wait(self.check_interval)
                
            except Exception as e:
                logging.error(f"Error in health monitoring loop: {e}")
                # Continue monitoring even if one check fails
                self.stop_event.wait(60)  # Wait 1 minute before retry
    
    def perform_health_check(self) -> Dict:
        """
        Perform comprehensive health check.
        
        Returns:
            Dict: Complete health report
        """
        metrics = []
        overall_status = 'healthy'
        
        # Check each health aspect
        metrics.extend(self._check_disk_space())
        metrics.extend(self._check_memory_usage())
        metrics.extend(self._check_cpu_usage())
        metrics.extend(self._check_network_connectivity())
        metrics.extend(self._check_process_health())
        metrics.extend(self._check_capture_performance())
        
        # Determine overall status
        if any(m.status == 'critical' for m in metrics):
            overall_status = 'critical'
        elif any(m.status == 'warning' for m in metrics):
            overall_status = 'warning'
        
        health_report = {
            'timestamp': datetime.now(),
            'overall_status': overall_status,
            'metrics': [asdict(m) for m in metrics],
            'performance_stats': self.performance_stats.copy(),
            'uptime_hours': self._get_uptime_hours()
        }
        
        return health_report
    
    def _check_disk_space(self) -> List[HealthMetric]:
        """Check disk space for project directories."""
        metrics = []
        
        try:
            project_base = self.config.get('files_and_folders', {}).get('PROJECT_BASE', '/')
            disk_usage = psutil.disk_usage(project_base)
            
            free_gb = disk_usage.free / (1024**3)
            used_percent = (disk_usage.used / disk_usage.total) * 100
            
            # Free space check
            if free_gb < 1.0:
                status = 'critical'
                message = f"Critical: Only {free_gb:.1f}GB free space remaining"
            elif free_gb < self.thresholds['disk_space_gb']:
                status = 'warning'
                message = f"Warning: Low disk space ({free_gb:.1f}GB free)"
            else:
                status = 'healthy'
                message = f"Disk space adequate ({free_gb:.1f}GB free)"
            
            metrics.append(HealthMetric(
                name='disk_free_space',
                value=free_gb,
                threshold=self.thresholds['disk_space_gb'],
                status=status,
                message=message,
                timestamp=datetime.now(),
                unit='GB'
            ))
            
            # Usage percentage check
            if used_percent > 95:
                status = 'critical'
                message = f"Critical: Disk {used_percent:.1f}% full"
            elif used_percent > self.thresholds['disk_space_percent']:
                status = 'warning'
                message = f"Warning: Disk {used_percent:.1f}% full"
            else:
                status = 'healthy'
                message = f"Disk usage normal ({used_percent:.1f}% used)"
            
            metrics.append(HealthMetric(
                name='disk_usage_percent',
                value=used_percent,
                threshold=self.thresholds['disk_space_percent'],
                status=status,
                message=message,
                timestamp=datetime.now(),
                unit='%'
            ))
            
        except Exception as e:
            metrics.append(HealthMetric(
                name='disk_space_check',
                value=0,
                threshold=0,
                status='critical',
                message=f"Failed to check disk space: {e}",
                timestamp=datetime.now()
            ))
        
        return metrics
    
    def _check_memory_usage(self) -> List[HealthMetric]:
        """Check system and process memory usage."""
        metrics = []
        
        try:
            # System memory
            memory = psutil.virtual_memory()
            
            if memory.percent > 95:
                status = 'critical'
                message = f"Critical: System memory {memory.percent:.1f}% used"
            elif memory.percent > self.thresholds['memory_percent']:
                status = 'warning'
                message = f"Warning: High memory usage ({memory.percent:.1f}%)"
            else:
                status = 'healthy'
                message = f"Memory usage normal ({memory.percent:.1f}%)"
            
            metrics.append(HealthMetric(
                name='system_memory',
                value=memory.percent,
                threshold=self.thresholds['memory_percent'],
                status=status,
                message=message,
                timestamp=datetime.now(),
                unit='%'
            ))
            
            # Process memory
            process = psutil.Process()
            process_memory_mb = process.memory_info().rss / (1024**2)
            
            if process_memory_mb > 2000:  # 2GB
                status = 'warning'
                message = f"High process memory usage: {process_memory_mb:.1f}MB"
            else:
                status = 'healthy'
                message = f"Process memory normal: {process_memory_mb:.1f}MB"
            
            metrics.append(HealthMetric(
                name='process_memory',
                value=process_memory_mb,
                threshold=2000,
                status=status,
                message=message,
                timestamp=datetime.now(),
                unit='MB'
            ))
            
        except Exception as e:
            metrics.append(HealthMetric(
                name='memory_check',
                value=0,
                threshold=0,
                status='critical',
                message=f"Failed to check memory: {e}",
                timestamp=datetime.now()
            ))
        
        return metrics
    
    def _check_cpu_usage(self) -> List[HealthMetric]:
        """Check CPU usage."""
        metrics = []
        
        try:
            cpu_percent = psutil.cpu_percent(interval=1)
            
            if cpu_percent > 95:
                status = 'critical'
                message = f"Critical: CPU usage {cpu_percent:.1f}%"
            elif cpu_percent > self.thresholds['cpu_percent']:
                status = 'warning'
                message = f"Warning: High CPU usage ({cpu_percent:.1f}%)"
            else:
                status = 'healthy'
                message = f"CPU usage normal ({cpu_percent:.1f}%)"
            
            metrics.append(HealthMetric(
                name='cpu_usage',
                value=cpu_percent,
                threshold=self.thresholds['cpu_percent'],
                status=status,
                message=message,
                timestamp=datetime.now(),
                unit='%'
            ))
            
        except Exception as e:
            metrics.append(HealthMetric(
                name='cpu_check',
                value=0,
                threshold=0,
                status='critical',
                message=f"Failed to check CPU: {e}",
                timestamp=datetime.now()
            ))
        
        return metrics
    
    def _check_network_connectivity(self) -> List[HealthMetric]:
        """Check network connectivity to HourGlass services."""
        metrics = []
        
        urls_to_check = {
            'image_url': self.config.get('urls', {}).get('IMAGE_URL'),
            'webpage': self.config.get('urls', {}).get('WEBPAGE'),
            'sun_url': self.config.get('sun', {}).get('URL')
        }
        
        for name, url in urls_to_check.items():
            if not url:
                continue
                
            try:
                start_time = time.time()
                response = requests.head(url, timeout=10, allow_redirects=True)
                response_time = (time.time() - start_time) * 1000  # ms
                
                if response.status_code == 200:
                    if response_time > 5000:  # 5 seconds
                        status = 'warning'
                        message = f"Slow response from {name}: {response_time:.0f}ms"
                    else:
                        status = 'healthy'
                        message = f"{name} accessible ({response_time:.0f}ms)"
                elif response.status_code == 405:
                    # 405 Method Not Allowed is common for webcam URLs that don't support HEAD
                    # Try a quick GET request to check actual connectivity
                    try:
                        get_start = time.time()
                        get_response = requests.get(url, timeout=10, stream=True)
                        get_response.close()  # Close immediately, we just wanted to check connectivity
                        get_time = (time.time() - get_start) * 1000
                        
                        if get_response.status_code == 200:
                            status = 'healthy'
                            message = f"{name} accessible (GET check: {get_time:.0f}ms)"
                        else:
                            status = 'warning'
                            message = f"{name} returned status {get_response.status_code} on GET"
                    except:
                        # If GET also fails, just note that HEAD isn't supported
                        status = 'info'
                        message = f"{name} doesn't support HEAD requests (405)"
                else:
                    status = 'warning'
                    message = f"{name} returned status {response.status_code}"
                
            except Exception as e:
                status = 'critical'
                message = f"Cannot reach {name}: {str(e)}"
                response_time = 0
            
            metrics.append(HealthMetric(
                name=f'network_{name}',
                value=response_time,
                threshold=5000,
                status=status,
                message=message,
                timestamp=datetime.now(),
                unit='ms'
            ))
        
        return metrics
    
    def _check_process_health(self) -> List[HealthMetric]:
        """Check process health indicators."""
        metrics = []
        
        try:
            process = psutil.Process()
            
            # Check if process is responsive
            status = 'healthy'
            message = f"Process healthy (PID: {process.pid})"
            
            metrics.append(HealthMetric(
                name='process_status',
                value=1,
                threshold=1,
                status=status,
                message=message,
                timestamp=datetime.now()
            ))
            
        except Exception as e:
            metrics.append(HealthMetric(
                name='process_status',
                value=0,
                threshold=1,
                status='critical',
                message=f"Process health check failed: {e}",
                timestamp=datetime.now()
            ))
        
        return metrics
    
    def _check_capture_performance(self) -> List[HealthMetric]:
        """Check image capture performance."""
        metrics = []
        
        # Skip capture performance checks during sleep mode
        if self.is_sleeping:
            return metrics
        
        try:
            uptime_hours = self._get_uptime_hours()
            
            # Don't check capture performance if we've been running for less than 30 minutes
            if uptime_hours < 0.5:  # Less than 30 minutes
                metrics.append(HealthMetric(
                    name='capture_rate',
                    value=0,
                    threshold=self.thresholds['capture_rate_min'] * 60,
                    status='healthy',
                    message=f"Startup period - capture rate check skipped (uptime: {uptime_hours*60:.0f} minutes)",
                    timestamp=datetime.now(),
                    unit='images/hour'
                ))
                return metrics
            
            if uptime_hours > 0:
                images_per_hour = self.performance_stats['images_captured'] / uptime_hours
                error_rate = 0
                
                total_attempts = self.performance_stats['images_captured'] + self.performance_stats['errors_encountered']
                if total_attempts > 0:
                    error_rate = (self.performance_stats['errors_encountered'] / total_attempts) * 100
                
                # Capture rate check (only after startup period)
                if images_per_hour < self.thresholds['capture_rate_min'] * 60:  # Convert to per hour
                    status = 'warning'
                    message = f"Low capture rate: {images_per_hour:.1f} images/hour"
                else:
                    status = 'healthy'
                    message = f"Capture rate normal: {images_per_hour:.1f} images/hour"
                
                metrics.append(HealthMetric(
                    name='capture_rate',
                    value=images_per_hour,
                    threshold=self.thresholds['capture_rate_min'] * 60,
                    status=status,
                    message=message,
                    timestamp=datetime.now(),
                    unit='images/hour'
                ))
                
                # Error rate check
                if error_rate > self.thresholds['error_rate_percent']:
                    status = 'warning'
                    message = f"High error rate: {error_rate:.1f}%"
                else:
                    status = 'healthy'
                    message = f"Error rate normal: {error_rate:.1f}%"
                
                metrics.append(HealthMetric(
                    name='error_rate',
                    value=error_rate,
                    threshold=self.thresholds['error_rate_percent'],
                    status=status,
                    message=message,
                    timestamp=datetime.now(),
                    unit='%'
                ))
            
        except Exception as e:
            metrics.append(HealthMetric(
                name='capture_performance',
                value=0,
                threshold=0,
                status='warning',
                message=f"Failed to check capture performance: {e}",
                timestamp=datetime.now()
            ))
        
        return metrics
    
    def _process_health_report(self, health_report):
        """Process health report and trigger alerts if needed."""
        # Add to history
        self.health_history.append(health_report)
        if len(self.health_history) > self.max_history_size:
            self.health_history.pop(0)
        
        # Check for alerts
        critical_metrics = [m for m in health_report['metrics'] if m['status'] == 'critical']
        warning_metrics = [m for m in health_report['metrics'] if m['status'] == 'warning']
        
        # Send critical alerts immediately
        for metric in critical_metrics:
            self._send_alert(metric, 'critical')
        
        # Send warning alerts with cooldown
        for metric in warning_metrics:
            self._send_alert(metric, 'warning')
        
        # Log overall status
        if health_report['overall_status'] != 'healthy':
            logging.warning(f"Health check: {health_report['overall_status']} status detected")
    
    def _send_alert(self, metric, severity):
        """Send alert for a metric."""
        alert_key = f"{metric['name']}_{severity}"
        now = datetime.now()
        
        # Check cooldown
        if alert_key in self.last_alerts:
            time_since_last = (now - self.last_alerts[alert_key]).total_seconds()
            if time_since_last < self.alert_cooldown:
                return  # Still in cooldown period
        
        # Send alert
        try:
            message_processor(
                f"Health Alert [{severity.upper()}]: {metric['message']}", 
                "error" if severity == 'critical' else "warning",
                ntfy=True
            )
            self.last_alerts[alert_key] = now
            
        except Exception as e:
            logging.error(f"Failed to send health alert: {e}")
    
    def _get_uptime_hours(self):
        """Get application uptime in hours."""
        uptime = datetime.now() - self.performance_stats['start_time']
        return uptime.total_seconds() / 3600
    
    def update_performance_stats(self, stat_name, increment=1):
        """
        Update performance statistics.
        
        Args:
            stat_name (str): Name of the statistic to update
            increment (int): Amount to increment by
        """
        if stat_name in self.performance_stats:
            self.performance_stats[stat_name] += increment
        
        if stat_name == 'images_captured':
            self.performance_stats['last_image_time'] = datetime.now()
    
    def get_health_summary(self) -> Dict:
        """Get a summary of recent health status."""
        if not self.health_history:
            return {"status": "no_data", "message": "No health data available"}
        
        latest = self.health_history[-1]
        
        return {
            "overall_status": latest['overall_status'],
            "timestamp": latest['timestamp'].isoformat(),
            "uptime_hours": round(latest['uptime_hours'], 2),
            "critical_issues": len([m for m in latest['metrics'] if m['status'] == 'critical']),
            "warnings": len([m for m in latest['metrics'] if m['status'] == 'warning']),
            "performance": latest['performance_stats']
        }


def create_health_monitor(config, check_interval=300):
    """
    Factory function to create a health monitor.
    
    Args:
        config: HourGlass configuration
        check_interval: Seconds between checks
        
    Returns:
        HealthMonitor: Configured health monitor instance
    """
    return HealthMonitor(config, check_interval)


# Quick health check functions for integration
def quick_health_check(config) -> str:
    """
    Perform a quick health check and return status.
    
    Returns:
        str: 'healthy', 'warning', or 'critical'
    """
    monitor = HealthMonitor(config)
    report = monitor.perform_health_check()
    return report['overall_status']


def log_health_summary(config):
    """Log a health summary for monitoring."""
    monitor = HealthMonitor(config)
    report = monitor.perform_health_check()
    
    summary = f"Health Check: {report['overall_status']} - "
    critical = len([m for m in report['metrics'] if m['status'] == 'critical'])
    warnings = len([m for m in report['metrics'] if m['status'] == 'warning'])
    
    if critical > 0:
        summary += f"{critical} critical issues, "
    if warnings > 0:
        summary += f"{warnings} warnings, "
    
    summary += f"uptime: {report['uptime_hours']:.1f}h"
    
    logging.info(summary)