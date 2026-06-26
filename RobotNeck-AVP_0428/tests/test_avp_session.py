import os
import sys


root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(root_dir)

from src.core.avp_session import AVPSessionCoordinator


class FakeClient:
    def __init__(self, ip=None, action_log=None):
        self.ip = ip or "172.20.10.2"
        self.action_log = action_log if action_log is not None else []
        self.connect_calls = []
        self.disconnect_calls = 0
        self.stop_stream_calls = 0
        self.connection_status = {
            "state": "idle",
            "ip": self.ip,
            "auto_reconnect": False,
            "session_mode": "tracking_only",
        }

    def connect(self, ip=None, auto_reconnect=False, session_mode="tracking_only"):
        self.ip = ip or self.ip
        self.connect_calls.append(
            {
                "ip": self.ip,
                "auto_reconnect": bool(auto_reconnect),
                "session_mode": session_mode,
            }
        )
        self.connection_status.update(
            {
                "state": "ready",
                "ip": self.ip,
                "auto_reconnect": bool(auto_reconnect),
                "session_mode": session_mode,
            }
        )
        self.action_log.append(("connect", session_mode))
        return True

    def disconnect(self):
        self.disconnect_calls += 1
        self.connection_status["state"] = "disconnected"
        self.action_log.append(("disconnect", self.connection_status["session_mode"]))

    def stop_video_stream(self):
        self.stop_stream_calls += 1
        self.connection_status["session_mode"] = "tracking_only"
        self.action_log.append(("stop_video_stream", None))
        return True


class FakeStreamerClient(FakeClient):
    def __init__(self, ip=None, action_log=None):
        super().__init__(ip=ip, action_log=action_log)
        self.streamer = None


def test_switch_mode_rebuilds_tracking_only_to_streaming_and_restores_runtime_state():
    created_clients = []
    restored_states = []
    exported_states = []

    def client_factory(ip):
        client = FakeClient(ip)
        created_clients.append(client)
        return client

    def export_runtime_state():
        state = {"was_tracking": True, "yaw_offset": 1.2}
        exported_states.append(state)
        return state

    coordinator = AVPSessionCoordinator(client_factory=client_factory)
    old_client = FakeClient("172.20.10.2")
    old_client.connection_status.update({"state": "ready", "session_mode": "tracking_only"})

    result = coordinator.switch_mode(
        current_client=old_client,
        target_mode="streaming",
        ip="172.20.10.2",
        auto_reconnect=True,
        export_runtime_state=export_runtime_state,
        restore_runtime_state=restored_states.append,
        stop_tracking=lambda: None,
    )

    assert result.success is True
    assert result.reason == ""
    assert result.client is created_clients[0]
    assert old_client.disconnect_calls == 1
    assert result.client.connect_calls == [
        {"ip": "172.20.10.2", "auto_reconnect": True, "session_mode": "streaming"}
    ]
    assert exported_states == [{"was_tracking": True, "yaw_offset": 1.2}]
    assert restored_states == [{"was_tracking": True, "yaw_offset": 1.2}]


def test_switch_mode_rebuilds_streaming_to_tracking_only_and_stops_old_stream_first():
    action_log = []

    def client_factory(ip):
        return FakeClient(ip, action_log=action_log)

    coordinator = AVPSessionCoordinator(client_factory=client_factory)
    old_client = FakeClient("172.20.10.2", action_log=action_log)
    old_client.connection_status.update({"state": "ready", "session_mode": "streaming"})

    result = coordinator.switch_mode(
        current_client=old_client,
        target_mode="tracking_only",
        ip="172.20.10.2",
        auto_reconnect=False,
        export_runtime_state=lambda: {"was_tracking": False},
        restore_runtime_state=lambda state: None,
        stop_tracking=lambda: None,
    )

    assert result.success is True
    assert old_client.stop_stream_calls == 1
    assert old_client.disconnect_calls == 1
    assert action_log[:3] == [
        ("stop_video_stream", None),
        ("disconnect", "tracking_only"),
        ("connect", "tracking_only"),
    ]


def test_switch_mode_returns_timeout_failure_without_restoring_runtime_state():
    restored_states = []

    def client_factory(ip):
        return FakeStreamerClient(ip)

    coordinator = AVPSessionCoordinator(
        client_factory=client_factory,
        wait_timeout_sec=0.01,
        poll_interval_sec=0.001,
    )
    old_client = FakeClient("172.20.10.2")
    old_client.connection_status.update({"state": "ready", "session_mode": "tracking_only"})

    result = coordinator.switch_mode(
        current_client=old_client,
        target_mode="streaming",
        ip="172.20.10.2",
        auto_reconnect=False,
        export_runtime_state=lambda: {"was_tracking": True},
        restore_runtime_state=restored_states.append,
        stop_tracking=lambda: None,
    )

    assert result.success is False
    assert result.reason == "AVP streaming session was not ready in time."
    assert restored_states == []


def test_switch_mode_records_phase_timings_and_events():
    events = []

    def client_factory(ip):
        return FakeClient(ip)

    coordinator = AVPSessionCoordinator(client_factory=client_factory)
    old_client = FakeClient("172.20.10.2")
    old_client.connection_status.update({"state": "ready", "session_mode": "streaming"})

    result = coordinator.switch_mode(
        current_client=old_client,
        target_mode="tracking_only",
        ip="172.20.10.2",
        auto_reconnect=False,
        export_runtime_state=lambda: {"was_tracking": True},
        restore_runtime_state=lambda state: None,
        stop_tracking=lambda: None,
        emit_event=lambda name, payload: events.append((name, payload)),
    )

    assert result.success is True
    names = [item[0] for item in events]
    assert names == [
        "avp_switch_start",
        "avp_switch_export_state_done",
        "avp_switch_stop_tracking_done",
        "avp_switch_stop_stream_done",
        "avp_switch_disconnect_done",
        "avp_switch_connect_done",
        "avp_switch_wait_ready_done",
        "avp_switch_restore_state_done",
        "avp_switch_complete",
    ]
    assert events[-1][1]["target_mode"] == "tracking_only"
    assert "total_ms" in events[-1][1]
