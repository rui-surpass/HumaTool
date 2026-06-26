import os
import sys


root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(root_dir)

from src.gui.camera_panel_logic import (
    build_camera_panel_state,
    build_rtp_stream_ui_state,
    precheck_rtp_stream_request,
)


def test_camera_panel_state_disables_sdk_only_controls_for_fallback_backend():
    state = build_camera_panel_state(
        device_info={
            "backend": "opencv",
            "connected": True,
            "sdk_available": False,
            "model": "OpenCV / UVC Generic",
            "serial_number": "N/A",
            "firmware_version": "N/A",
            "sensors_firmware_version": "N/A",
            "resolution": "1280x720",
            "fps": 30,
            "capabilities": {
                "supports_manual_focus": False,
                "supports_auto_focus": False,
                "supports_depth_controls": False,
                "supports_sensor_snapshot": False,
                "supports_health_status": False,
                "supports_streaming": False,
            },
        },
        sensor_snapshot={"supported": False, "imu": {"available": False}, "magnetometer": {"available": False}, "barometer": {"available": False}},
        health_status={"supported": False},
        streaming_status={"supported": False, "enabled": False, "codec": "N/A", "bitrate_kbps": 0, "port": 0, "last_error": ""},
    )

    assert state["control_state"]["auto_focus_enabled"] is False
    assert state["control_state"]["streaming_enabled"] is False
    assert state["control_state"]["depth_controls_enabled"] is False
    assert "OpenCV" in state["device_summary"]


def test_camera_panel_state_formats_zed_runtime_summaries():
    state = build_camera_panel_state(
        device_info={
            "backend": "zed_sdk",
            "connected": True,
            "sdk_available": True,
            "model": "ZED-M",
            "serial_number": 12345,
            "firmware_version": 100,
            "sensors_firmware_version": 200,
            "resolution": "1280x720",
            "fps": 30,
            "capabilities": {
                "supports_manual_focus": True,
                "supports_auto_focus": False,
                "supports_depth_controls": True,
                "supports_sensor_snapshot": True,
                "supports_health_status": True,
                "supports_streaming": True,
            },
        },
        sensor_snapshot={
            "supported": True,
            "imu": {"available": True, "fresh": True, "rpy_rad": [0.1, -0.2, 0.0], "angular_velocity_dps": [1.0, 2.0, 3.0], "linear_acceleration_mps2": [0.1, 0.2, 9.8]},
            "magnetometer": {"available": True, "fresh": True, "field_ut": [1.0, 2.0, 3.0]},
            "barometer": {"available": True, "fresh": False, "pressure_hpa": 1001.2},
        },
        health_status={
            "supported": True,
            "enabled": True,
            "low_image_quality": False,
            "low_lighting": True,
            "low_depth_reliability": False,
            "low_motion_sensors_reliability": True,
            "last_grab_status": "SUCCESS",
        },
        streaming_status={"supported": True, "enabled": True, "codec": "H265", "bitrate_kbps": 10000, "port": 30000, "last_error": ""},
    )

    assert state["control_state"]["manual_focus_enabled"] is True
    assert state["control_state"]["streaming_enabled"] is True
    assert "Serial 12345" in state["device_summary"]
    assert "Yaw" in state["imu_summary"]
    assert "low light" in state["health_summary"].lower()
    assert "H265" in state["streaming_summary"]


def test_rtp_stream_ui_state_matches_requested_activity():
    active = build_rtp_stream_ui_state(True)
    inactive = build_rtp_stream_ui_state(False)

    assert active["checked"] is True
    assert active["text"] == "Stop RTP Stream"
    assert "#e67e22" in active["style"]

    assert inactive["checked"] is False
    assert inactive["text"] == "Start RTP Stream"
    assert inactive["style"] == ""


def test_rtp_stream_request_is_rejected_when_camera_is_missing():
    decision = precheck_rtp_stream_request(has_camera=False, requested_enabled=True)

    assert decision["accepted"] is False
    assert decision["warning"] == "Camera not connected."
    assert decision["ui_state"] == build_rtp_stream_ui_state(False)
