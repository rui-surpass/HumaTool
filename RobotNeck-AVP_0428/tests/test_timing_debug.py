import logging
import os
import sys


root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(root_dir)

from src.core.timing_debug import (
    RuntimeTimingTracker,
    camera_diagnostics_enabled,
    timing_debug_enabled,
)


def test_timing_debug_enabled_defaults_to_false(monkeypatch):
    monkeypatch.delenv("ROBO_NECK_DEBUG_TIMING", raising=False)

    assert timing_debug_enabled() is False


def test_timing_debug_enabled_accepts_truthy_env(monkeypatch):
    monkeypatch.setenv("ROBO_NECK_DEBUG_TIMING", "1")

    assert timing_debug_enabled() is True


def test_camera_diagnostics_enabled_can_be_disabled_by_env(monkeypatch):
    monkeypatch.setenv("ROBO_NECK_DISABLE_CAMERA_DIAGNOSTICS", "1")

    assert camera_diagnostics_enabled() is False


def test_runtime_timing_tracker_accumulates_snapshot_without_logging(caplog):
    tracker = RuntimeTimingTracker("control_loop", enabled=False)

    with caplog.at_level(logging.INFO):
        tracker.record(12.0, now=1.0)
        tracker.record(24.0, now=2.0)

    snapshot = tracker.snapshot()

    assert snapshot["count"] == 2
    assert snapshot["last_ms"] == 24.0
    assert snapshot["max_ms"] == 24.0
    assert snapshot["avg_ms"] == 18.0
    assert caplog.records == []


def test_runtime_timing_tracker_logs_slow_sample_when_enabled(caplog):
    tracker = RuntimeTimingTracker(
        "camera_read",
        enabled=True,
        log_every_sec=10.0,
        slow_threshold_ms=20.0,
    )

    with caplog.at_level(logging.WARNING):
        tracker.record(25.0, now=1.0, extra={"source": "preview"})

    assert any("camera_read" in record.message for record in caplog.records)
    assert any("source=preview" in record.message for record in caplog.records)
