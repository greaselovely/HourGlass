# notifications.py
"""
Unified notification manager supporting multiple services (ntfy, Pushover).
Each service can be independently enabled/disabled. Rate limiting and
exponential backoff are applied globally across all services.
"""

import json
import logging
import requests
from time import sleep, monotonic
from urllib.parse import urljoin


# Pushover log_level -> priority mapping
# -2 = lowest, -1 = low, 0 = normal, 1 = high, 2 = emergency
_PUSHOVER_PRIORITY = {
    "info": 0,
    "warning": 1,
    "error": 1,
    "download": -1,
    "none": -1,
}

# Rate-limiting state (shared across all services)
_last_send = 0.0
_min_interval = 10  # seconds between any notification
_backoff = 0         # current backoff seconds (0 = none)


class NotificationManager:
    """Dispatches messages to all enabled notification services."""

    def __init__(self, config):
        self._services = {}
        self._load_from_config(config)

    # ------------------------------------------------------------------
    # Config loading
    # ------------------------------------------------------------------
    def _load_from_config(self, config):
        """Build internal service dict from project config."""
        alerts = config.get("alerts", {})
        services = alerts.get("services", {})

        # --- ntfy ---
        ntfy_cfg = services.get("ntfy", {})
        if ntfy_cfg.get("enabled") and ntfy_cfg.get("topic"):
            base_url = ntfy_cfg.get("url", config.get("ntfy", "http://ntfy.sh/"))
            self._services["ntfy"] = {
                "type": "ntfy",
                "url": base_url,
                "topic": ntfy_cfg["topic"],
            }

        # --- Pushover ---
        po_cfg = services.get("pushover", {})
        if po_cfg.get("enabled") and po_cfg.get("api_token") and po_cfg.get("user_key"):
            self._services["pushover"] = {
                "type": "pushover",
                "api_token": po_cfg["api_token"],
                "user_key": po_cfg["user_key"],
            }

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    @property
    def has_services(self):
        return bool(self._services)

    def send(self, message, log_level="info"):
        """Send *message* to every enabled service. Returns True if at least one succeeded."""
        if not self._services:
            return False

        self._enforce_rate_limit()

        ok = False
        for name, svc in self._services.items():
            try:
                if svc["type"] == "ntfy":
                    ok |= self._send_ntfy(svc, message)
                elif svc["type"] == "pushover":
                    ok |= self._send_pushover(svc, message, log_level)
            except Exception as e:
                logging.error(f"Notification service '{name}' error: {e}")
        return ok

    # ------------------------------------------------------------------
    # Rate limiting (shared across services)
    # ------------------------------------------------------------------
    @staticmethod
    def _enforce_rate_limit():
        global _last_send, _backoff
        now = monotonic()
        wait = max(_min_interval, _backoff) - (now - _last_send)
        if wait > 0:
            logging.info(f"Notification rate limit: waiting {wait:.0f}s")
            sleep(wait)

    @staticmethod
    def _record_send():
        global _last_send
        _last_send = monotonic()

    @staticmethod
    def _apply_backoff(seconds):
        global _backoff
        _backoff = seconds

    @staticmethod
    def _reset_backoff():
        global _backoff
        _backoff = 0

    # ------------------------------------------------------------------
    # ntfy
    # ------------------------------------------------------------------
    def _send_ntfy(self, svc, message):
        url = urljoin(svc["url"], svc["topic"])
        headers = {"Content-Type": "application/x-www-form-urlencoded"}

        max_retries = 3
        for attempt in range(max_retries):
            try:
                resp = requests.post(url, headers=headers, data=str(message))
                resp.raise_for_status()
                self._record_send()
                self._reset_backoff()
                logging.info(f"Notification sent to {url}")
                return True
            except requests.RequestException as e:
                is_429 = hasattr(e, "response") and e.response is not None and e.response.status_code == 429
                if is_429 and attempt < max_retries - 1:
                    bo = max(30, _backoff * 2) if _backoff else 30
                    self._apply_backoff(bo)
                    logging.warning(f"ntfy 429, backing off {bo}s (attempt {attempt+1}/{max_retries})")
                    sleep(bo)
                    continue
                if is_429:
                    self._apply_backoff(max(60, _backoff * 2) if _backoff else 60)
                logging.error(f"ntfy send failed: {e}")
                self._record_send()
                return False
        return False

    # ------------------------------------------------------------------
    # Pushover
    # ------------------------------------------------------------------
    def _send_pushover(self, svc, message, log_level="info"):
        url = "https://api.pushover.net/1/messages.json"
        priority = _PUSHOVER_PRIORITY.get(log_level, 0)

        payload = {
            "token": svc["api_token"],
            "user": svc["user_key"],
            "message": str(message),
            "priority": priority,
        }
        # Emergency priority requires retry + expire params
        if priority == 2:
            payload["retry"] = 60
            payload["expire"] = 3600

        try:
            resp = requests.post(url, data=payload)
            resp.raise_for_status()
            self._record_send()
            self._reset_backoff()
            logging.info("Notification sent via Pushover")
            return True
        except requests.RequestException as e:
            logging.error(f"Pushover send failed: {e}")
            self._record_send()
            return False


# ------------------------------------------------------------------
# Module-level singleton (set by init_notifications)
# ------------------------------------------------------------------
_manager = None


def init_notifications(config):
    """Initialise the global NotificationManager from a loaded config dict."""
    global _manager
    _manager = NotificationManager(config)
    return _manager


def get_manager():
    """Return the current NotificationManager (or None if not initialised)."""
    return _manager


def notify(message, log_level="info"):
    """Convenience: send through the global manager. Returns True on success."""
    if _manager is None:
        return False
    return _manager.send(message, log_level)


# ------------------------------------------------------------------
# Interactive wizard for --notifications CLI
# ------------------------------------------------------------------
def notifications_wizard(config_path):
    """
    Interactive CRUD wizard for notification services.
    Reads and writes the project JSON config directly, then exits.
    """
    from pathlib import Path

    path = Path(config_path)
    if not path.exists():
        print(f"Config not found: {config_path}")
        return False

    with open(path, "r") as f:
        config = json.load(f)

    alerts = config.setdefault("alerts", {})
    services = alerts.setdefault("services", {})

    # Ensure skeleton entries exist for display
    if "ntfy" not in services:
        services["ntfy"] = {"enabled": False, "topic": ""}
    if "pushover" not in services:
        services["pushover"] = {"enabled": False, "api_token": "", "user_key": ""}

    # Ensure status_api section exists
    status_api = config.setdefault("status_api", {"tailscale_ip": "", "port": 8321})

    while True:
        print("\n" + "=" * 50)
        print(" Notification & Status API")
        print("=" * 50)
        _print_status(services)
        _print_status_api(status_api)

        print("\nOptions:")
        print("  1. Configure ntfy")
        print("  2. Configure Pushover")
        print("  3. Configure Status API (Tailscale)")
        print("  4. Toggle service on/off")
        print("  5. Test notifications")
        print("  6. Save & exit")
        print("  7. Exit without saving")

        choice = input("\nSelect (1-7): ").strip()

        if choice == "1":
            _configure_ntfy(services, config)
        elif choice == "2":
            _configure_pushover(services)
        elif choice == "3":
            _configure_status_api(status_api)
        elif choice == "4":
            _toggle_service(services)
        elif choice == "5":
            _test_notifications(config)
        elif choice == "6":
            with open(path, "w") as f:
                json.dump(config, f, indent=2)
            print(f"\nSaved to {path}")
            return True
        elif choice == "7":
            print("Exiting without saving.")
            return False
        else:
            print("Invalid choice.")


def _print_status(services):
    """Print a table of configured services."""
    for name, cfg in services.items():
        enabled = cfg.get("enabled", False)
        status = "ON" if enabled else "OFF"
        details = ""
        if name == "ntfy":
            topic = cfg.get("topic", "")
            details = f"topic={topic}" if topic else "(not configured)"
        elif name == "pushover":
            has_token = bool(cfg.get("api_token"))
            has_user = bool(cfg.get("user_key"))
            if has_token and has_user:
                details = "credentials set"
            else:
                details = "(not configured)"
        print(f"  {name:12s} [{status:3s}]  {details}")


def _print_status_api(status_api):
    """Print status API configuration."""
    ip = status_api.get("tailscale_ip", "")
    port = status_api.get("port", 8321)
    if ip:
        print(f"\n  Status API:  http://{ip}:{port}/status/{{PROJECT}}")
    else:
        print(f"\n  Status API:  (not configured — no Tailscale IP)")


def _configure_status_api(status_api):
    """Walk through status API setup."""
    print("\n--- Status API Configuration ---")
    print("The status API runs on your server and is queried by v.sh over Tailscale.")
    print("Enter your server's Tailscale IP so v.sh knows where to connect.\n")

    current_ip = status_api.get("tailscale_ip", "")
    ip = input(f"Server Tailscale IP [{current_ip}]: ").strip()
    if ip:
        status_api["tailscale_ip"] = ip

    current_port = status_api.get("port", 8321)
    port_str = input(f"Status API port [{current_port}]: ").strip()
    if port_str:
        try:
            status_api["port"] = int(port_str)
        except ValueError:
            print("Invalid port, keeping current value.")


def _configure_ntfy(services, config):
    """Walk through ntfy setup."""
    ntfy = services.setdefault("ntfy", {"enabled": False, "topic": ""})
    print("\n--- ntfy Configuration ---")

    current_url = config.get("ntfy", "http://ntfy.sh/")
    url = input(f"ntfy base URL [{current_url}]: ").strip()
    if url:
        config["ntfy"] = url
        ntfy["url"] = url

    current_topic = ntfy.get("topic", "")
    topic = input(f"Topic name [{current_topic}]: ").strip()
    if topic:
        ntfy["topic"] = topic

    if ntfy.get("topic"):
        enable = input("Enable ntfy? (y/n) [y]: ").strip().lower() != "n"
        ntfy["enabled"] = enable
    else:
        print("No topic set — ntfy remains disabled.")
        ntfy["enabled"] = False


def _configure_pushover(services):
    """Walk through Pushover setup."""
    po = services.setdefault("pushover", {"enabled": False, "api_token": "", "user_key": ""})
    print("\n--- Pushover Configuration ---")
    print("You need an API token (from your Pushover app) and your user key.")

    current_token = po.get("api_token", "")
    masked = f"...{current_token[-4:]}" if len(current_token) > 4 else current_token
    token = input(f"API token [{masked}]: ").strip()
    if token:
        po["api_token"] = token

    current_user = po.get("user_key", "")
    masked = f"...{current_user[-4:]}" if len(current_user) > 4 else current_user
    user = input(f"User key [{masked}]: ").strip()
    if user:
        po["user_key"] = user

    if po.get("api_token") and po.get("user_key"):
        enable = input("Enable Pushover? (y/n) [y]: ").strip().lower() != "n"
        po["enabled"] = enable
    else:
        print("Missing credentials — Pushover remains disabled.")
        po["enabled"] = False


def _toggle_service(services):
    """Toggle a service on/off."""
    names = list(services.keys())
    if not names:
        print("No services configured.")
        return

    print("\nToggle which service?")
    for i, name in enumerate(names, 1):
        status = "ON" if services[name].get("enabled") else "OFF"
        print(f"  {i}. {name} [{status}]")

    choice = input(f"Select (1-{len(names)}): ").strip()
    try:
        idx = int(choice) - 1
        svc = services[names[idx]]
        svc["enabled"] = not svc.get("enabled", False)
        new_status = "ON" if svc["enabled"] else "OFF"
        print(f"{names[idx]} is now {new_status}")
    except (ValueError, IndexError):
        print("Invalid choice.")


def _test_notifications(config):
    """Send a test message through all enabled services."""
    mgr = NotificationManager(config)
    if not mgr.has_services:
        print("No services are enabled — nothing to test.")
        return
    print("Sending test notification...")
    ok = mgr.send("HourGlass test notification", "info")
    if ok:
        print("Test notification sent successfully!")
    else:
        print("Test notification failed. Check the logs.")
