# health_monitor.py

import time
import socket
import psutil
import requests
import logging
from typing import Dict, List
from urllib.parse import urlparse
from collections import deque
from datetime import datetime, timedelta
from threading import Thread, Event
from .timelapse_core import message_processor
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
        }

        # Connection/rate-limit thresholds are config-driven: they are tuned against a
        # measured per-project baseline (VLA idles at a single reused keepalive socket),
        # so a sensible number here is not universal the way "90% disk" is.
        health_cfg = self.config.get('health', {})
        self.thresholds.update({
            'capture_connections_warning': health_cfg.get('capture_connections_warning', 5),
            'capture_connections_critical': health_cfg.get('capture_connections_critical', 10),
            'rate_limit_count': health_cfg.get('rate_limit_count', 5),
        })
        
        # Health history
        self.health_history = []
        self.max_history_size = 288  # 24 hours of 5-minute checks
        
        # Alert tracking
        self.last_alerts = {}
        # Metrics currently in an alerting state, so we can say "recovered" once.
        self.active_alerts = {}
        self.alert_cooldown = 1800  # default: 30 minutes between same alerts
        # Per-metric cooldown overrides (seconds). Disk is slow-moving — a single
        # low-disk alert per run/day is plenty, not one every 30 minutes.
        self.alert_cooldowns = {
            'disk_free_space': 86400,
            'disk_usage_percent': 86400,
        }

        # While a video is compiling, ffmpeg pegs CPU/memory by design, so those
        # alerts are noise. Toggled by main.py via set_video_compiling().
        self.is_compiling_video = False
        self._compile_suppressed = {'system_memory', 'cpu_usage'}
        
        # Performance tracking
        self.performance_stats = {
            'images_captured': 0,
            'errors_encountered': 0,
            'session_recreations': 0,
            'start_time': datetime.now(),
            'last_image_time': None
        }

        # Rolling window of recent capture attempts: (timestamp, is_error).
        # The error rate is computed over this window rather than over the whole
        # session, so a fixed problem stops alerting instead of slowly decaying
        # below the threshold over the next several hours.
        self.recent_attempts = deque()
        self.error_window_seconds = 1800  # 30 minutes
        self.min_window_attempts = 5      # need a real sample before judging

        # Rolling window of 429/503 responses from the capture host. The capture path
        # treats every non-200 identically, so without this a rate-limit response is
        # indistinguishable from a 404 in the logs.
        self.recent_rate_limits = deque()
        self.rate_limit_window_seconds = 1800  # 30 minutes, same window as error_rate

        # Resolved IPs of the capture host, cached so the check does not do a DNS
        # lookup on every pass. Refreshed on the interval below.
        self._capture_host_ips = set()
        self._capture_ips_resolved_at = None
        self._capture_ips_ttl_seconds = 1800

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
            # Don't carry pre-sleep attempts into the next daylight window, and
            # drop any open capture alert so we don't push an all-clear at dawn
            # for something that stopped mattering at dusk. Log only, no notify.
            self.recent_attempts.clear()
            severity = self.active_alerts.pop('error_rate', None)
            if severity:
                self.last_alerts.pop(f"error_rate_{severity}", None)
            logging.info("Health monitor: System entering sleep mode")
        else:
            logging.info("Health monitor: System waking from sleep mode")

    def set_video_compiling(self, is_compiling: bool):
        """Suppress CPU/memory alerts during video compilation (expected load)."""
        self.is_compiling_video = is_compiling

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
        metrics.extend(self._check_connection_count())
        metrics.extend(self._check_rate_limiting())
        
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
                elif response.status_code in (429, 503):
                    status = 'warning'
                    message = f"{name} rate limited (status {response.status_code})"
                    self.record_rate_limit(response.status_code)
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
        """Check image capture performance (error rate over the recent window)."""
        metrics = []

        # Skip capture performance checks during sleep mode
        if self.is_sleeping:
            return metrics

        try:
            attempts, errors = self._recent_attempt_counts()

            # Not enough recent activity to say anything meaningful.
            if attempts < self.min_window_attempts:
                return metrics

            error_rate = (errors / attempts) * 100
            window_minutes = self.error_window_seconds / 60

            if error_rate > self.thresholds['error_rate_percent']:
                status = 'warning'
                message = (f"High error rate: {error_rate:.1f}% "
                           f"({errors}/{attempts} in last {window_minutes:.0f}m)")
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
    
    def _get_capture_host_ips(self):
        """Resolve the capture host(s) to a set of IPs, cached with a TTL.

        Both IMAGE_URL and WEBPAGE are resolved because they can be different hosts,
        and a single hostname can return several A records (public.nrao.edu answers
        with two), all of which count as the same origin.
        """
        now = datetime.now()
        if (self._capture_ips_resolved_at is not None
                and (now - self._capture_ips_resolved_at).total_seconds() < self._capture_ips_ttl_seconds):
            return self._capture_host_ips

        urls = self.config.get('urls', {})
        hostnames = set()
        for url in (urls.get('IMAGE_URL'), urls.get('WEBPAGE')):
            if not url:
                continue
            hostname = urlparse(url).hostname
            if hostname:
                hostnames.add(hostname)

        ips = set()
        for hostname in hostnames:
            try:
                _, _, addresses = socket.gethostbyname_ex(hostname)
                ips.update(addresses)
            except Exception as e:
                logging.debug(f"Could not resolve capture host {hostname}: {e}")

        # Keep the previous answer on a total resolution failure rather than reporting
        # zero connections, which would look like a clean bill of health.
        if ips:
            self._capture_host_ips = ips
            self._capture_ips_resolved_at = now

        return self._capture_host_ips

    def _check_connection_count(self) -> List[HealthMetric]:
        """Check how many TCP connections this process holds open to the capture host.

        Scoped to the capture host on purpose: counting every connection would fire on
        Pixabay downloads and YouTube uploads, which would force the threshold so high
        it could no longer detect the thing it exists to detect.
        """
        metrics = []

        try:
            capture_ips = self._get_capture_host_ips()
            if not capture_ips:
                return metrics

            connections = psutil.Process().net_connections(kind='tcp')
            to_capture = [c for c in connections if c.raddr and c.raddr.ip in capture_ips]
            count = len(to_capture)
            close_wait = sum(1 for c in to_capture if c.status == 'CLOSE_WAIT')

            # A climbing CLOSE_WAIT count is the signature of responses that were never
            # closed, so it is worth naming in the message even when the total is fine.
            detail = f"({count} open, {close_wait} CLOSE_WAIT)"

            if count > self.thresholds['capture_connections_critical']:
                status = 'critical'
                message = f"Critical: {count} connections to capture host {detail}"
            elif count > self.thresholds['capture_connections_warning']:
                status = 'warning'
                message = f"Warning: elevated connections to capture host {detail}"
            else:
                status = 'healthy'
                message = f"Capture host connections normal {detail}"

            metrics.append(HealthMetric(
                name='capture_host_connections',
                value=count,
                threshold=self.thresholds['capture_connections_warning'],
                status=status,
                message=message,
                timestamp=datetime.now(),
                unit='connections'
            ))

        except psutil.AccessDenied:
            # Some platforms refuse socket introspection. That is a missing measurement,
            # not a fault worth paging about.
            logging.debug("Connection check skipped: psutil denied access to socket table")
        except Exception as e:
            metrics.append(HealthMetric(
                name='connection_check',
                value=0,
                threshold=0,
                status='warning',
                message=f"Failed to check connections: {e}",
                timestamp=datetime.now()
            ))

        return metrics

    def _check_rate_limiting(self) -> List[HealthMetric]:
        """Check how many 429/503 responses the capture host returned recently."""
        metrics = []

        if self.is_sleeping:
            return metrics

        try:
            count = self._recent_rate_limit_count()
            window_minutes = self.rate_limit_window_seconds / 60

            if count > self.thresholds['rate_limit_count']:
                status = 'warning'
                message = (f"Being rate limited: {count} 429/503 responses "
                           f"in last {window_minutes:.0f}m")
            else:
                status = 'healthy'
                message = f"No significant rate limiting ({count} in last {window_minutes:.0f}m)"

            metrics.append(HealthMetric(
                name='rate_limit_responses',
                value=count,
                threshold=self.thresholds['rate_limit_count'],
                status=status,
                message=message,
                timestamp=datetime.now(),
                unit='responses'
            ))

        except Exception as e:
            metrics.append(HealthMetric(
                name='rate_limit_check',
                value=0,
                threshold=0,
                status='warning',
                message=f"Failed to check rate limiting: {e}",
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

        # Anything that recovered gets a clean slate, so the next incident alerts
        # immediately instead of waiting out a stale cooldown. Logged, not pushed —
        # no news is good news.
        healthy_names = {m['name'] for m in health_report['metrics'] if m['status'] == 'healthy'}
        for name in healthy_names & set(self.active_alerts):
            self._clear_alert(name, self.active_alerts.pop(name))

        # Log overall status
        if health_report['overall_status'] != 'healthy':
            logging.warning(f"Health check: {health_report['overall_status']} status detected")
    
    def _send_alert(self, metric, severity):
        """Send alert for a metric."""
        # Silence expected CPU/memory spikes while a video is compiling.
        if self.is_compiling_video and metric['name'] in self._compile_suppressed:
            return

        alert_key = f"{metric['name']}_{severity}"
        now = datetime.now()

        # Check cooldown (per-metric override if set, else the default)
        cooldown = self.alert_cooldowns.get(metric['name'], self.alert_cooldown)
        if alert_key in self.last_alerts:
            time_since_last = (now - self.last_alerts[alert_key]).total_seconds()
            if time_since_last < cooldown:
                return  # Still in cooldown period
        
        # Send alert
        try:
            message_processor(
                f"Health Alert [{severity.upper()}]: {metric['message']}", 
                "error" if severity == 'critical' else "warning",
                notify=True
            )
            self.last_alerts[alert_key] = now
            self.active_alerts[metric['name']] = severity

        except Exception as e:
            logging.error(f"Failed to send health alert: {e}")

    def _clear_alert(self, metric_name, severity):
        """Reset alert state when a previously alerting metric recovers (log only)."""
        self.last_alerts.pop(f"{metric_name}_{severity}", None)
        logging.info(f"Health recovered: {metric_name} back to normal")

    def _recent_attempt_counts(self):
        """Prune the attempt window and return (attempts, errors) within it."""
        cutoff = datetime.now() - timedelta(seconds=self.error_window_seconds)
        while self.recent_attempts and self.recent_attempts[0][0] < cutoff:
            self.recent_attempts.popleft()

        attempts = len(self.recent_attempts)
        errors = sum(1 for _, is_error in self.recent_attempts if is_error)
        return attempts, errors

    def _recent_rate_limit_count(self):
        """Prune the rate-limit window and return how many remain within it."""
        cutoff = datetime.now() - timedelta(seconds=self.rate_limit_window_seconds)
        while self.recent_rate_limits and self.recent_rate_limits[0] < cutoff:
            self.recent_rate_limits.popleft()
        return len(self.recent_rate_limits)

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

        if stat_name in ('images_captured', 'errors_encountered'):
            now = datetime.now()
            is_error = stat_name == 'errors_encountered'
            self.recent_attempts.extend([(now, is_error)] * max(1, increment))

        if stat_name == 'images_captured':
            self.performance_stats['last_image_time'] = datetime.now()

    def record_rate_limit(self, status_code):
        """
        Record a rate-limit response from the capture host.

        Args:
            status_code (int): The HTTP status that triggered this (429 or 503)
        """
        self.recent_rate_limits.append(datetime.now())
        logging.warning(f"Capture host returned {status_code} (rate limited)")
    

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