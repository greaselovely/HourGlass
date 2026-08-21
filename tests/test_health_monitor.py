"""Tests for lib/health_monitor.py connection and rate-limit checks."""
import sys
from collections import namedtuple
from datetime import datetime, timedelta
from pathlib import Path

import psutil
import pytest

# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from lib.health_monitor import HealthMonitor


# Mirrors the shape psutil returns from Process.net_connections(kind='tcp').
FakeAddr = namedtuple('FakeAddr', ['ip', 'port'])
FakeConn = namedtuple('FakeConn', ['raddr', 'status'])


CAPTURE_IPS = {'192.33.115.91', '192.33.115.92'}


@pytest.fixture
def monitor():
    """A monitor with the capture host pre-resolved, so checks skip DNS."""
    config = {
        'urls': {
            'IMAGE_URL': 'https://public.nrao.edu/wp-content/uploads/temp/vla_webcam_temp.jpg',
            'WEBPAGE': 'https://public.nrao.edu/vla-webcam/',
        }
    }
    monitor = HealthMonitor(config, check_interval=300)
    monitor._capture_host_ips = set(CAPTURE_IPS)
    monitor._capture_ips_resolved_at = datetime.now()
    return monitor


def _patch_connections(monkeypatch, connections):
    """Make psutil report a fixed connection table for this process."""
    monkeypatch.setattr(
        psutil.Process, 'net_connections', lambda self, kind='tcp': connections
    )


class TestCheckConnectionCount:
    """Tests for HealthMonitor._check_connection_count."""

    def test_baseline_single_connection_is_healthy(self, monitor, monkeypatch):
        """The observed steady state — one reused keepalive socket — is healthy."""
        _patch_connections(monkeypatch, [
            FakeConn(FakeAddr('192.33.115.91', 443), 'ESTABLISHED'),
        ])

        metrics = monitor._check_connection_count()

        assert len(metrics) == 1
        assert metrics[0].name == 'capture_host_connections'
        assert metrics[0].value == 1
        assert metrics[0].status == 'healthy'

    def test_above_warning_threshold_warns(self, monitor, monkeypatch):
        """More connections than the warning threshold should warn."""
        _patch_connections(monkeypatch, [
            FakeConn(FakeAddr('192.33.115.91', 443), 'ESTABLISHED')
            for _ in range(monitor.thresholds['capture_connections_warning'] + 1)
        ])

        metrics = monitor._check_connection_count()

        assert metrics[0].status == 'warning'

    def test_above_critical_threshold_is_critical(self, monitor, monkeypatch):
        """Blowing past the critical threshold should escalate, not just warn."""
        _patch_connections(monkeypatch, [
            FakeConn(FakeAddr('192.33.115.92', 443), 'ESTABLISHED')
            for _ in range(monitor.thresholds['capture_connections_critical'] + 1)
        ])

        metrics = monitor._check_connection_count()

        assert metrics[0].status == 'critical'

    def test_other_hosts_are_not_counted(self, monitor, monkeypatch):
        """Pixabay/YouTube/ntfy traffic must not trip the capture-host alert."""
        _patch_connections(monkeypatch, [
            FakeConn(FakeAddr('192.33.115.91', 443), 'ESTABLISHED'),
        ] + [
            FakeConn(FakeAddr('104.18.20.1', 443), 'ESTABLISHED') for _ in range(50)
        ])

        metrics = monitor._check_connection_count()

        assert metrics[0].value == 1
        assert metrics[0].status == 'healthy'

    def test_listening_sockets_without_raddr_are_ignored(self, monitor, monkeypatch):
        """The status API listener has no remote address and must not crash the check."""
        _patch_connections(monkeypatch, [
            FakeConn(None, 'LISTEN'),
            FakeConn(FakeAddr('192.33.115.91', 443), 'ESTABLISHED'),
        ])

        metrics = monitor._check_connection_count()

        assert metrics[0].value == 1

    def test_close_wait_count_surfaces_in_message(self, monitor, monkeypatch):
        """CLOSE_WAIT is the leak signature, so it belongs in the alert text."""
        _patch_connections(monkeypatch, [
            FakeConn(FakeAddr('192.33.115.91', 443), 'CLOSE_WAIT'),
            FakeConn(FakeAddr('192.33.115.91', 443), 'ESTABLISHED'),
        ])

        metrics = monitor._check_connection_count()

        assert '1 CLOSE_WAIT' in metrics[0].message

    def test_access_denied_yields_no_metric(self, monitor, monkeypatch):
        """A platform that refuses socket introspection is a gap, not a critical fault."""
        def deny(self, kind='tcp'):
            raise psutil.AccessDenied()

        monkeypatch.setattr(psutil.Process, 'net_connections', deny)

        assert monitor._check_connection_count() == []

    def test_unresolvable_capture_host_yields_no_metric(self, monkeypatch):
        """With no capture host resolved, report nothing rather than a false all-clear."""
        monitor = HealthMonitor({'urls': {}}, check_interval=300)

        assert monitor._check_connection_count() == []


class TestRateLimitTracking:
    """Tests for record_rate_limit and _check_rate_limiting."""

    def test_no_rate_limits_is_healthy(self, monitor):
        """A quiet window should report healthy so a prior alert can clear."""
        metrics = monitor._check_rate_limiting()

        assert len(metrics) == 1
        assert metrics[0].name == 'rate_limit_responses'
        assert metrics[0].value == 0
        assert metrics[0].status == 'healthy'

    def test_crossing_threshold_warns(self, monitor):
        """More 429s than the threshold within the window should warn."""
        for _ in range(monitor.thresholds['rate_limit_count'] + 1):
            monitor.record_rate_limit(429)

        metrics = monitor._check_rate_limiting()

        assert metrics[0].status == 'warning'

    def test_503_is_recorded_too(self, monitor):
        """503 is the other shape origin overload takes."""
        monitor.record_rate_limit(503)

        assert monitor._check_rate_limiting()[0].value == 1

    def test_entries_older_than_window_are_pruned(self, monitor):
        """A fixed problem should stop alerting instead of decaying for hours."""
        stale = datetime.now() - timedelta(seconds=monitor.rate_limit_window_seconds + 60)
        for _ in range(20):
            monitor.recent_rate_limits.append(stale)

        metrics = monitor._check_rate_limiting()

        assert metrics[0].value == 0
        assert metrics[0].status == 'healthy'

    def test_skipped_while_sleeping(self, monitor):
        """Nothing is being fetched overnight, so there is nothing to judge."""
        monitor.is_sleeping = True

        assert monitor._check_rate_limiting() == []


class TestAlertCooldown:
    """The new metrics must not bypass the existing alert-fatigue controls."""

    def test_second_alert_within_cooldown_is_suppressed(self, monitor, monkeypatch):
        """Repeated breaches inside the cooldown window should send once."""
        sent = []
        monkeypatch.setattr(
            'lib.health_monitor.message_processor',
            lambda message, level, notify=False, **kwargs: sent.append(message)
        )
        metric = {'name': 'capture_host_connections', 'message': 'too many connections'}

        monitor._send_alert(metric, 'warning')
        monitor._send_alert(metric, 'warning')

        assert len(sent) == 1

    def test_recovery_clears_the_cooldown(self, monitor, monkeypatch):
        """After recovering, the next incident should alert immediately."""
        sent = []
        monkeypatch.setattr(
            'lib.health_monitor.message_processor',
            lambda message, level, notify=False, **kwargs: sent.append(message)
        )
        metric = {'name': 'capture_host_connections', 'message': 'too many connections'}

        monitor._send_alert(metric, 'warning')
        monitor._process_health_report({
            'metrics': [{'name': 'capture_host_connections', 'status': 'healthy'}],
            'overall_status': 'healthy',
        })
        monitor._send_alert(metric, 'warning')

        assert len(sent) == 2


class TestPerformHealthCheck:
    """The new checks must be wired into the report the CLI and thread both use."""

    def test_new_metrics_present_in_report(self, monitor, monkeypatch):
        """--health and the background thread should both surface the new metrics."""
        _patch_connections(monkeypatch, [
            FakeConn(FakeAddr('192.33.115.91', 443), 'ESTABLISHED'),
        ])
        monkeypatch.setattr(monitor, '_check_network_connectivity', lambda: [])

        report = monitor.perform_health_check()
        names = {m['name'] for m in report['metrics']}

        assert 'capture_host_connections' in names
        assert 'rate_limit_responses' in names
