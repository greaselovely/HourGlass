# config_validator.py

import os
import json
import requests
import logging
from pathlib import Path
from datetime import datetime
from urllib.parse import urlparse


class ConfigValidator:
    """
    Validates configuration settings and performs health checks.
    
    This class provides comprehensive validation of the VLA configuration,
    including network connectivity, file permissions, and setting reasonableness.
    """
    
    def __init__(self, config_path='config.json'):
        self.config_path = config_path
        self.validation_errors = []
        self.validation_warnings = []
        self.health_status = {}
        
    def validate_config(self, config=None):
        """
        Perform comprehensive configuration validation.
        
        Args:
            config (dict, optional): Configuration to validate. If None, loads from file.
            
        Returns:
            dict: Validation results with status, errors, warnings, and recommendations
        """
        if config is None:
            config = self._load_config()
            
        if not config:
            return self._create_result(False, ["Failed to load configuration"])
            
        self.validation_errors = []
        self.validation_warnings = []
        
        # Core validation checks
        self._validate_required_sections(config)
        self._validate_file_paths(config)
        self._validate_urls(config)
        self._validate_sun_settings(config)
        self._validate_alert_settings(config)
        self._validate_user_agents(config)
        
        # Create result
        is_valid = len(self.validation_errors) == 0
        return self._create_result(is_valid, self.validation_errors, self.validation_warnings)
    
    def health_check(self, config=None, quick=False):
        """
        Perform system health checks.
        
        Args:
            config (dict, optional): Configuration to use for health checks
            quick (bool): If True, skip network connectivity tests
            
        Returns:
            dict: Health check results
        """
        if config is None:
            config = self._load_config()
            
        self.health_status = {}
        
        if not config:
            return {"status": "failed", "error": "No configuration available"}
            
        # File system health
        self._check_filesystem_health(config)
        
        # Network health (unless quick mode)
        if not quick:
            self._check_network_health(config)
            
        # Disk space health
        self._check_disk_space(config)
        
        # Permission health
        self._check_permissions(config)
        
        # Overall status
        failed_checks = [k for k, v in self.health_status.items() if not v.get('status', True)]
        overall_status = "healthy" if not failed_checks else "degraded" if len(failed_checks) < 3 else "unhealthy"
        
        return {
            "overall_status": overall_status,
            "failed_checks": failed_checks,
            "details": self.health_status,
            "timestamp": datetime.now().isoformat()
        }
    
    def _load_config(self):
        """Load configuration from file."""
        try:
            with open(self.config_path, 'r') as f:
                return json.load(f)
        except Exception as e:
            logging.error(f"Failed to load config from {self.config_path}: {e}")
            return None
    
    def _validate_required_sections(self, config):
        """Validate that all required configuration sections exist."""
        required_sections = [
            'files_and_folders',
            'urls', 
            'sun',
            'alerts',
            'user_agents',
            'output_symbols'
        ]
        
        for section in required_sections:
            if section not in config:
                self.validation_errors.append(f"Missing required configuration section: {section}")
                
        # Validate required keys within sections
        if 'files_and_folders' in config:
            required_folder_keys = ['VLA_BASE', 'VIDEO_FOLDER', 'IMAGES_FOLDER', 'LOGGING_FOLDER', 'AUDIO_FOLDER']
            for key in required_folder_keys:
                if key not in config['files_and_folders']:
                    self.validation_errors.append(f"Missing required folder configuration: {key}")
                    
        if 'urls' in config:
            required_url_keys = ['IMAGE_URL', 'WEBPAGE']
            for key in required_url_keys:
                if key not in config['urls']:
                    self.validation_errors.append(f"Missing required URL configuration: {key}")
    
    def _validate_file_paths(self, config):
        """Validate file paths and directory settings."""
        if 'files_and_folders' not in config:
            return
            
        folders = config['files_and_folders']
        
        # Check if base folder is reasonable
        if 'VLA_BASE' in folders:
            base_path = Path(folders['VLA_BASE'])
            
            # Warn if base path is in unusual locations
            unusual_locations = ['/tmp', '/var/tmp', '/dev', '/proc', '/sys']
            if any(str(base_path).startswith(loc) for loc in unusual_locations):
                self.validation_warnings.append(f"VLA_BASE is in an unusual location: {base_path}")
                
            # Check if path is writable (if it exists)
            if base_path.exists() and not os.access(base_path, os.W_OK):
                self.validation_errors.append(f"VLA_BASE directory is not writable: {base_path}")
    
    def _validate_urls(self, config):
        """Validate URL configurations."""
        if 'urls' not in config:
            return
            
        urls = config['urls']
        
        for url_key, url_value in urls.items():
            if not url_value:
                self.validation_warnings.append(f"URL configuration {url_key} is empty")
                continue
                
            # Basic URL format validation
            parsed = urlparse(url_value)
            if not parsed.scheme or not parsed.netloc:
                self.validation_errors.append(f"Invalid URL format for {url_key}: {url_value}")
                
        # Validate NTFY URL if present
        if 'ntfy' in config and config['ntfy']:
            ntfy_url = config['ntfy']
            parsed = urlparse(ntfy_url)
            if not parsed.scheme or not parsed.netloc:
                self.validation_errors.append(f"Invalid NTFY URL format: {ntfy_url}")
    
    def _validate_sun_settings(self, config):
        """Validate sun-related settings."""
        if 'sun' not in config:
            return
            
        sun_config = config['sun']
        
        # Validate time formats
        time_fields = ['SUNRISE', 'SUNSET']
        for field in time_fields:
            if field in sun_config:
                try:
                    datetime.strptime(sun_config[field], '%H:%M:%S')
                except ValueError:
                    self.validation_errors.append(f"Invalid time format for {field}: {sun_config[field]}. Expected HH:MM:SS")
                    
        # Validate sunset time add
        if 'SUNSET_TIME_ADD' in sun_config:
            sunset_add = sun_config['SUNSET_TIME_ADD']
            if not isinstance(sunset_add, (int, float)) or sunset_add < 0 or sunset_add > 300:
                self.validation_warnings.append(f"SUNSET_TIME_ADD seems unusual: {sunset_add} minutes")
    
    def _validate_alert_settings(self, config):
        """Validate alert and notification settings."""
        if 'alerts' not in config:
            return
            
        alerts = config['alerts']
        
        # Validate escalation points
        if 'escalation_points' in alerts:
            points = alerts['escalation_points']
            if not isinstance(points, list) or not all(isinstance(p, int) for p in points):
                self.validation_errors.append("escalation_points must be a list of integers")
            elif points != sorted(points):
                self.validation_warnings.append("escalation_points should be in ascending order")
                
        # Check if NTFY is configured
        if 'ntfy' in alerts and not alerts['ntfy']:
            self.validation_warnings.append("NTFY topic is not configured - notifications will not be sent")
    
    def _validate_user_agents(self, config):
        """Validate user agent configurations."""
        if 'user_agents' not in config:
            self.validation_errors.append("user_agents configuration is missing")
            return
            
        user_agents = config['user_agents']
        
        if not isinstance(user_agents, list):
            self.validation_errors.append("user_agents must be a list")
        elif len(user_agents) == 0:
            self.validation_errors.append("user_agents list is empty")
        elif len(user_agents) < 3:
            self.validation_warnings.append("Consider adding more user agents for better rotation")
    
    def _check_filesystem_health(self, config):
        """Check filesystem health and accessibility."""
        if 'files_and_folders' not in config:
            return
            
        folders = config['files_and_folders']
        
        for folder_key, folder_path in folders.items():
            if not folder_path or folder_key.endswith('_FILE'):
                continue
                
            path = Path(folder_path)
            status = {
                "exists": path.exists(),
                "writable": False,
                "readable": False
            }
            
            if path.exists():
                status["writable"] = os.access(path, os.W_OK)
                status["readable"] = os.access(path, os.R_OK)
            
            status["status"] = status["exists"] and status["writable"] and status["readable"]
            self.health_status[f"filesystem_{folder_key.lower()}"] = status
    
    def _check_network_health(self, config):
        """Check network connectivity to configured URLs."""
        urls_to_check = {}
        
        if 'urls' in config:
            urls_to_check.update(config['urls'])
            
        if 'sun' in config and 'URL' in config['sun']:
            urls_to_check['SUN_URL'] = config['sun']['URL']
            
        for url_key, url_value in urls_to_check.items():
            if not url_value:
                continue
                
            status = {"url": url_value}
            
            try:
                response = requests.head(url_value, timeout=10, allow_redirects=True)
                status.update({
                    "reachable": True,
                    "status_code": response.status_code,
                    "response_time_ms": int(response.elapsed.total_seconds() * 1000),
                    "status": response.status_code < 400
                })
            except requests.RequestException as e:
                status.update({
                    "reachable": False,
                    "error": str(e),
                    "status": False
                })
                
            self.health_status[f"network_{url_key.lower()}"] = status
    
    def _check_disk_space(self, config):
        """Check available disk space for VLA operations."""
        if 'files_and_folders' not in config or 'VLA_BASE' not in config['files_and_folders']:
            return
            
        try:
            import shutil
            
            vla_base = config['files_and_folders']['VLA_BASE']
            total, used, free = shutil.disk_usage(vla_base)
            
            free_gb = free / (1024 ** 3)
            total_gb = total / (1024 ** 3)
            used_percent = (used / total) * 100
            
            status = {
                "free_gb": round(free_gb, 2),
                "total_gb": round(total_gb, 2),
                "used_percent": round(used_percent, 2),
                "status": free_gb > 5.0  # Warn if less than 5GB free
            }
            
            if free_gb < 1.0:
                status["warning"] = "Critical: Less than 1GB free space"
            elif free_gb < 5.0:
                status["warning"] = "Low disk space warning"
                
            self.health_status["disk_space"] = status
            
        except Exception as e:
            self.health_status["disk_space"] = {
                "status": False,
                "error": f"Failed to check disk space: {e}"
            }
    
    def _check_permissions(self, config):
        """Check file permissions for critical operations."""
        permission_checks = {}
        
        # Check config file permissions
        config_path = Path(self.config_path)
        if config_path.exists():
            permission_checks["config_readable"] = os.access(config_path, os.R_OK)
            permission_checks["config_writable"] = os.access(config_path, os.W_OK)
        
        self.health_status["permissions"] = {
            **permission_checks,
            "status": all(permission_checks.values())
        }
    
    def _create_result(self, is_valid, errors=None, warnings=None):
        """Create a standardized validation result."""
        return {
            "valid": is_valid,
            "errors": errors or [],
            "warnings": warnings or [],
            "timestamp": datetime.now().isoformat()
        }


def validate_config_quick(config_path='config.json'):
    """
    Quick configuration validation function.
    
    Args:
        config_path (str): Path to configuration file
        
    Returns:
        bool: True if configuration is valid, False otherwise
    """
    validator = ConfigValidator(config_path)
    result = validator.validate_config()
    return result['valid']


def get_config_recommendations(config_path='config.json'):
    """
    Get configuration improvement recommendations.
    
    Args:
        config_path (str): Path to configuration file
        
    Returns:
        list: List of recommendation strings
    """
    validator = ConfigValidator(config_path)
    config = validator._load_config()
    
    if not config:
        return ["Cannot load configuration file"]
    
    recommendations = []
    
    # Check for common improvements
    if 'alerts' in config and not config['alerts'].get('ntfy'):
        recommendations.append("Configure NTFY notifications for better monitoring")
        
    if 'proxies' in config and not any(config['proxies'].values()):
        recommendations.append("Consider configuring proxies if needed for your network")
        
    if len(config.get('user_agents', [])) < 5:
        recommendations.append("Add more user agents for better web scraping resilience")
        
    return recommendations