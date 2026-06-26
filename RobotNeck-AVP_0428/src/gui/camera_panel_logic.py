import math
import numpy as np


RTP_STREAM_ACTIVE_STYLE = "background-color: #e67e22; color: white;"


def _backend_label(backend):
    mapping = {
        "zed_sdk": "ZED SDK",
        "opencv": "OpenCV Fallback",
        "unavailable": "Unavailable",
    }
    return mapping.get(backend, backend)


def _format_scalar(value, precision=1, suffix=""):
    if value is None:
        return "N/A"
    if isinstance(value, str):
        return value
    if isinstance(value, float):
        return f"{value:.{precision}f}{suffix}"
    return f"{value}{suffix}"


def _format_vector(values, precision=2, suffix=""):
    if not values:
        return "N/A"
    parts = [f"{float(v):.{precision}f}" for v in values]
    return f"[{', '.join(parts)}]{suffix}"


def _imu_summary(imu):
    if not imu.get("available"):
        return "IMU unavailable"
    rpy = imu.get("rpy_rad")
    if not rpy:
        return "IMU unavailable"
    yaw, pitch, roll = [np.rad2deg(v) for v in rpy]
    freshness = "fresh" if imu.get("fresh") else "cached"
    return (
        f"Yaw {yaw:.1f} deg | Pitch {pitch:.1f} deg | Roll {roll:.1f} deg "
        f"({freshness})"
    )


def _health_summary(health_status):
    if not health_status.get("supported"):
        return "Health status unavailable on this backend."

    issues = []
    if health_status.get("low_image_quality"):
        issues.append("low image quality")
    if health_status.get("low_lighting"):
        issues.append("low light")
    if health_status.get("low_depth_reliability"):
        issues.append("low depth reliability")
    if health_status.get("low_motion_sensors_reliability"):
        issues.append("motion sensors")

    if not issues:
        issues_text = "No active alerts"
    else:
        issues_text = "Alerts: " + ", ".join(issues)

    return (
        f"Health check {'enabled' if health_status.get('enabled') else 'disabled'} | "
        f"{issues_text}"
    )


def build_rtp_stream_ui_state(active):
    active = bool(active)
    return {
        "checked": active,
        "text": "Stop RTP Stream" if active else "Start RTP Stream",
        "style": RTP_STREAM_ACTIVE_STYLE if active else "",
    }


def precheck_rtp_stream_request(has_camera, requested_enabled):
    if has_camera:
        return {
            "accepted": True,
            "warning": None,
            "ui_state": build_rtp_stream_ui_state(requested_enabled),
        }

    if requested_enabled:
        warning = "Camera not connected."
    else:
        warning = None

    return {
        "accepted": False,
        "warning": warning,
        "ui_state": build_rtp_stream_ui_state(False),
    }


def build_camera_panel_state(device_info, sensor_snapshot, health_status, streaming_status):
    capabilities = device_info.get("capabilities", {})
    connected = bool(device_info.get("connected"))
    backend_text = _backend_label(device_info.get("backend", "unknown"))
    model = device_info.get("model", "Unknown")
    serial_number = device_info.get("serial_number", "N/A")
    firmware_version = device_info.get("firmware_version", "N/A")
    sensors_firmware_version = device_info.get("sensors_firmware_version", "N/A")
    resolution = device_info.get("resolution", "N/A")
    fps = device_info.get("fps", "N/A")

    device_summary = (
        f"{backend_text} | {model} | Serial {serial_number} | "
        f"FW {firmware_version}/{sensors_firmware_version} | {resolution} @ {fps} FPS"
    )
    backend_summary = (
        f"Backend: {backend_text} | SDK available: "
        f"{'Yes' if device_info.get('sdk_available') else 'No'}"
    )

    control_state = {
        "manual_focus_enabled": connected and capabilities.get("supports_manual_focus", False),
        "auto_focus_enabled": connected and capabilities.get("supports_auto_focus", False),
        "depth_controls_enabled": connected and capabilities.get("supports_depth_controls", False),
        "streaming_enabled": connected and capabilities.get("supports_streaming", False),
    }

    imu = sensor_snapshot.get("imu", {})
    magnetometer = sensor_snapshot.get("magnetometer", {})
    barometer = sensor_snapshot.get("barometer", {})

    streaming_summary = (
        f"{'Active' if streaming_status.get('enabled') else 'Stopped'} | "
        f"{streaming_status.get('codec', 'N/A')} | "
        f"{streaming_status.get('bitrate_kbps', 0)} kbps | "
        f"Port {streaming_status.get('port', 0)}"
    )
    if streaming_status.get("last_error"):
        streaming_summary += f" | Error: {streaming_status['last_error']}"

    return {
        "device_summary": device_summary,
        "backend_summary": backend_summary,
        "imu_summary": _imu_summary(imu),
        "imu_accel_summary": _format_vector(imu.get("linear_acceleration_mps2"), precision=2, suffix=" m/s^2"),
        "imu_gyro_summary": _format_vector(imu.get("angular_velocity_dps"), precision=2, suffix=" deg/s"),
        "mag_summary": _format_vector(magnetometer.get("field_ut"), precision=2, suffix=" uT")
        if magnetometer.get("available")
        else "Magnetometer unavailable",
        "baro_summary": _format_scalar(barometer.get("pressure_hpa"), precision=1, suffix=" hPa")
        if barometer.get("available")
        else "Barometer unavailable",
        "health_summary": _health_summary(health_status),
        "grab_summary": f"Last grab: {health_status.get('last_grab_status', 'N/A')}",
        "streaming_summary": streaming_summary,
        "control_state": control_state,
    }
