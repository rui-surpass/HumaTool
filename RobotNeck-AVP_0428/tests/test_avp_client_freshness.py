import os
import sys
import threading
import time

import numpy as np


root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(root_dir)

from src.core.client import AVPClient
import src.core.client as client_module


class FakeStreamer:
    def __init__(self, payloads):
        self.payloads = list(payloads)

    def get_latest(self):
        if not self.payloads:
            return None
        return self.payloads.pop(0)


def make_pose(yaw_rad=0.0):
    pose = np.eye(4)
    cy = np.cos(yaw_rad)
    sy = np.sin(yaw_rad)
    pose[0, 0] = cy
    pose[0, 2] = sy
    pose[2, 0] = -sy
    pose[2, 2] = cy
    return pose


def make_client(payloads):
    client = AVPClient.__new__(AVPClient)
    client.streamer = FakeStreamer(payloads)
    client._streamer_lock = threading.Lock()
    client._streamer_thread = None
    client._streamer_error = None
    client._streamer_import_error = ""
    client._connect_requested = False
    client._auto_reconnect = False
    client._stop_event = threading.Event()
    client._last_sample_timestamp = None
    client._last_head_matrix = None
    client._has_ever_received_pose = False
    client.frame_source = None
    client.using_dummy_video = False
    client._connection_status = {
        "state": "idle",
        "ip": "172.20.10.4",
        "auto_reconnect": False,
        "last_error": None,
        "state_since_monotonic": time.monotonic(),
        "last_sample_timestamp": None,
        "has_ever_received_pose": False,
    }
    client._last_pose_status = {
        "valid": False,
        "reason": "uninitialized",
        "fresh": False,
        "last_sample_timestamp": None,
        "source_timestamp": None,
        "last_matrix_shape": None,
        "error": None,
        "state_since_monotonic": time.monotonic(),
    }
    return client


def test_client_uses_local_receive_time_when_upstream_timestamp_is_missing():
    client = make_client([
        {"head": make_pose(0.1)},
    ])

    sample = client.get_latest_head_pose_sample(now=12.5)

    assert sample.timestamp > 0.0
    assert sample.monotonic_timestamp == 12.5
    assert sample.fresh is True
    assert sample.source_timestamp is None
    assert sample.raw_payload["fresh"] is True
    assert sample.raw_payload["source_timestamp"] is None
    assert sample.raw_payload["sample_monotonic_timestamp"] == 12.5
    assert client.get_pose_status()["last_sample_monotonic"] == 12.5
    assert client.get_pose_status()["age_ms"] == 0.0


def test_client_preserves_upstream_wall_timestamp_but_tracks_local_monotonic_age():
    client = make_client([
        {"head": make_pose(0.1), "timestamp": 1_700_000_000.25},
    ])

    sample = client.get_latest_head_pose_sample(now=5.0)
    status = client.get_pose_status()

    assert sample.timestamp == 1_700_000_000.25
    assert sample.monotonic_timestamp == 5.0
    assert sample.fresh is True
    assert status["last_sample_timestamp"] == 5.0
    assert status["last_sample_monotonic"] == 5.0
    assert status["last_sample_wall_time"] == 1_700_000_000.25
    assert status["age_ms"] == 0.0
    assert status["reason"] == "ready"


def test_client_marks_repeated_pose_stale_after_timeout():
    pose = make_pose(0.1)
    client = make_client([
        {"head": pose, "timestamp": 1_700_000_000.0},
        {"head": pose.copy(), "timestamp": 1_700_000_000.0},
    ])

    first = client.get_latest_head_pose_sample(now=10.0)
    second = client.get_latest_head_pose_sample(now=10.4)
    status = client.get_pose_status()

    assert first.fresh is True
    assert second.fresh is False
    assert status["reason"] == "stale_sample"
    assert status["age_ms"] == 400.0
    assert status["repeated_head_matrix_count"] == 1


def test_client_tracks_repeated_source_timestamp_independently_from_matrix_repeats():
    pose = make_pose(0.1)
    client = make_client([
        {"head": pose, "timestamp": 1_700_000_000.0},
        {"head": pose.copy(), "timestamp": 1_700_000_001.0},
        {"head": pose.copy(), "timestamp": 1_700_000_001.0},
    ])

    client.get_latest_head_pose_sample(now=10.0)
    client.get_latest_head_pose_sample(now=10.1)
    client.get_latest_head_pose_sample(now=10.2)

    timing = client.get_debug_timing_snapshot()

    assert timing["repeated_head_matrix_count"] == 2
    assert timing["repeated_source_timestamp_count"] == 1


def test_client_does_not_return_repeated_stale_matrix_by_default():
    pose = make_pose(0.1)
    client = make_client([
        {"head": pose, "timestamp": 1_700_000_000.0},
        {"head": pose.copy(), "timestamp": 1_700_000_000.0},
    ])

    assert client.get_latest_head_pose_matrix(now=10.0) is not None

    assert client.get_latest_head_pose_matrix(now=10.4) is None
    assert client.get_pose_status()["reason"] == "stale_sample"


def test_client_does_not_return_cached_matrix_when_streamer_has_no_new_payload():
    client = make_client([
        {"head": make_pose(0.1)},
        None,
    ])

    assert client.get_latest_head_pose_matrix(now=20.0) is not None

    assert client.get_latest_head_pose_matrix(now=20.4) is None
    assert client.get_pose_status()["reason"] == "stale_sample"


def test_client_starts_idle_until_operator_requests_manual_connection():
    client = AVPClient("172.20.10.4")

    assert client.streamer is None
    assert client.get_connection_status()["state"] == "idle"
    assert client.get_connection_status()["session_mode"] == "tracking_only"
    assert client.get_pose_status()["reason"] == "idle"


def test_client_connect_records_requested_session_mode():
    client = AVPClient("172.20.10.4")
    client._start_streamer_thread = lambda: None

    client.connect(auto_reconnect=True, session_mode="streaming")

    status = client.get_connection_status()
    assert status["state"] == "connecting"
    assert status["session_mode"] == "streaming"
    assert status["auto_reconnect"] is True


def test_client_manual_connect_does_not_block_while_streamer_connects_in_background():
    original_streamer = client_module.VisionProStreamer

    class SlowStreamer:
        def __init__(self, ip, record=True):
            time.sleep(0.5)
            self.ip = ip

        def get_latest(self):
            return None

        def cleanup(self):
            return None

    client_module.VisionProStreamer = SlowStreamer
    try:
        client = AVPClient("172.20.10.4")
        started = time.time()
        client.connect(auto_reconnect=False)
        elapsed = time.time() - started

        assert elapsed < 0.2
        assert client.streamer is None
        assert client._streamer_thread is not None
        assert client.get_connection_status()["state"] == "connecting"
    finally:
        client.disconnect()
        client_module.VisionProStreamer = original_streamer


def test_client_auto_reconnect_eventually_recovers_after_initial_connect_failure(monkeypatch):
    original_streamer = client_module.VisionProStreamer
    attempts = []

    class FlakyStreamer:
        def __init__(self, ip, record=True):
            attempts.append(ip)
            if len(attempts) == 1:
                raise RuntimeError("connection refused")
            self.ip = ip

        def get_latest(self):
            return None

        def cleanup(self):
            return None

    monkeypatch.setattr(client_module, "AVP_RECONNECT_RETRY_SEC", 0.01, raising=False)
    client_module.VisionProStreamer = FlakyStreamer
    try:
        client = AVPClient("172.20.10.4")
        client.connect(auto_reconnect=True)

        deadline = time.time() + 0.3
        while time.time() < deadline and client.streamer is None:
            time.sleep(0.01)

        assert len(attempts) >= 2
        assert client.streamer is not None
        assert client.get_connection_status()["state"] == "connected_waiting_first_sample"
    finally:
        client.disconnect()
        client_module.VisionProStreamer = original_streamer


def test_client_disconnect_stops_auto_reconnect_attempts(monkeypatch):
    original_streamer = client_module.VisionProStreamer
    attempts = []

    class AlwaysFailStreamer:
        def __init__(self, ip, record=True):
            attempts.append(ip)
            raise RuntimeError("connection refused")

    monkeypatch.setattr(client_module, "AVP_RECONNECT_RETRY_SEC", 0.01, raising=False)
    client_module.VisionProStreamer = AlwaysFailStreamer
    try:
        client = AVPClient("172.20.10.4")
        client.connect(auto_reconnect=True)

        deadline = time.time() + 0.2
        while time.time() < deadline and len(attempts) < 2:
            time.sleep(0.01)

        client.disconnect()
        attempts_after_disconnect = len(attempts)
        time.sleep(0.05)

        assert attempts_after_disconnect >= 1
        assert len(attempts) == attempts_after_disconnect
        assert client.get_connection_status()["state"] == "disconnected"
    finally:
        client_module.VisionProStreamer = original_streamer
