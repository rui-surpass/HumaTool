from __future__ import annotations

import time
from dataclasses import dataclass


@dataclass(frozen=True)
class SessionSwitchResult:
    success: bool
    client: object | None
    reason: str = ""


class AVPSessionCoordinator:
    def __init__(self, client_factory, wait_timeout_sec=2.0, poll_interval_sec=0.05):
        self.client_factory = client_factory
        self.wait_timeout_sec = float(wait_timeout_sec)
        self.poll_interval_sec = float(poll_interval_sec)

    def switch_mode(
        self,
        current_client,
        target_mode,
        ip,
        auto_reconnect,
        export_runtime_state=None,
        restore_runtime_state=None,
        stop_tracking=None,
        attach_client=None,
        emit_event=None,
    ):
        started = time.time()

        def record_event(name, **payload):
            if emit_event is None:
                return
            event_payload = dict(payload)
            event_payload["target_mode"] = target_mode
            event_payload["ip"] = ip
            emit_event(name, event_payload)

        if current_client is None:
            return SessionSwitchResult(success=False, client=None, reason="AVP client is not ready yet.")
        record_event("avp_switch_start", auto_reconnect=bool(auto_reconnect))

        runtime_state = {}
        if export_runtime_state is not None:
            step_started = time.time()
            runtime_state = export_runtime_state() or {}
            record_event("avp_switch_export_state_done", duration_ms=round((time.time() - step_started) * 1000.0, 3))

        if stop_tracking is not None:
            step_started = time.time()
            stop_tracking()
            record_event("avp_switch_stop_tracking_done", duration_ms=round((time.time() - step_started) * 1000.0, 3))

        if target_mode == "tracking_only":
            step_started = time.time()
            current_client.stop_video_stream()
            record_event("avp_switch_stop_stream_done", duration_ms=round((time.time() - step_started) * 1000.0, 3))
        else:
            record_event("avp_switch_stop_stream_done", duration_ms=0.0, skipped=True)
        step_started = time.time()
        current_client.disconnect()
        record_event("avp_switch_disconnect_done", duration_ms=round((time.time() - step_started) * 1000.0, 3))

        step_started = time.time()
        new_client = self.client_factory(ip)
        new_client.connect(ip=ip, auto_reconnect=auto_reconnect, session_mode=target_mode)
        record_event("avp_switch_connect_done", duration_ms=round((time.time() - step_started) * 1000.0, 3))

        if attach_client is not None:
            attach_client(new_client)

        step_started = time.time()
        ready = self._wait_for_session(new_client)
        record_event(
            "avp_switch_wait_ready_done",
            duration_ms=round((time.time() - step_started) * 1000.0, 3),
            success=bool(ready),
        )
        if not ready:
            failure_reason = self._failure_reason(target_mode)
            record_event(
                "avp_switch_complete",
                success=False,
                total_ms=round((time.time() - started) * 1000.0, 3),
                reason=failure_reason,
            )
            return SessionSwitchResult(
                success=False,
                client=new_client,
                reason=failure_reason,
            )

        if restore_runtime_state is not None:
            step_started = time.time()
            restore_runtime_state(runtime_state)
            record_event("avp_switch_restore_state_done", duration_ms=round((time.time() - step_started) * 1000.0, 3))

        record_event("avp_switch_complete", success=True, total_ms=round((time.time() - started) * 1000.0, 3))
        return SessionSwitchResult(success=True, client=new_client, reason="")

    def _wait_for_session(self, client):
        if client is None:
            return False

        if not hasattr(client, "streamer"):
            return True

        deadline = time.time() + max(0.0, self.wait_timeout_sec)
        while time.time() < deadline:
            if getattr(client, "streamer", None) is not None:
                return True
            time.sleep(self.poll_interval_sec)
        return getattr(client, "streamer", None) is not None

    def _failure_reason(self, target_mode):
        if target_mode == "streaming":
            return "AVP streaming session was not ready in time."
        return "AVP tracking session was not ready in time."
