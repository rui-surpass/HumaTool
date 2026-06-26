from dataclasses import dataclass


@dataclass(frozen=True)
class SystemSnapshot:
    avp_connected: bool
    camera_connected: bool
    motor_connected: bool
    streaming: bool
    tracking: bool
    avp_session_mode: str = "tracking_only"
    pose_sample_valid: bool = False
    pose_sample_reason: str = ""
    tracking_blocked: bool = False
    tracking_block_reason: str = ""
    yaw_inactive: bool = False
    last_warning: str = ""


@dataclass(frozen=True)
class DashboardState:
    hero_label: str
    severity: str
    severity_label: str
    next_step: str
    summary: str
    motor_action: str
    motor_action_label: str
    motor_action_enabled: bool
    motor_action_reason: str
    avp_action: str
    avp_action_label: str
    avp_action_enabled: bool
    avp_action_reason: str
    connect_camera_enabled: bool
    connect_camera_reason: str
    stream_action: str
    stream_action_label: str
    stream_action_enabled: bool
    stream_action_reason: str
    tracking_action: str
    tracking_action_label: str
    tracking_action_enabled: bool
    tracking_action_reason: str
    calibrate_action_label: str
    calibrate_action_enabled: bool
    calibrate_action_reason: str
    recovery_title: str
    recovery_detail: str
    recovery_action: str
    recovery_action_label: str
    recovery_action_enabled: bool
    recovery_button_visible: bool


def _motor_action_state(snapshot: SystemSnapshot):
    if snapshot.motor_connected:
        return {
            "action": "disconnect",
            "label": "Disconnect Motor",
            "enabled": not snapshot.tracking,
            "reason": (
                "Disconnect the neck motors."
                if not snapshot.tracking
                else "Stop tracking before disconnecting the neck motors."
            ),
        }

    return {
        "action": "connect",
        "label": "Connect Motor",
        "enabled": True,
        "reason": "Connect the neck motors using the current Dynamixel Debug port and baud settings.",
    }


def _avp_action_state(snapshot: SystemSnapshot):
    if snapshot.avp_connected:
        return {
            "action": "disconnect",
            "label": "Disconnect AVP",
            "enabled": not snapshot.tracking,
            "reason": (
                "Disconnect the AVP client."
                if not snapshot.tracking
                else "Stop tracking before disconnecting AVP."
            ),
        }

    return {
        "action": "connect",
        "label": "Connect AVP",
        "enabled": True,
        "reason": "Connect the AVP client using the configured IP.",
    }


def _stream_action_state(snapshot: SystemSnapshot):
    if snapshot.streaming:
        return {
            "action": "stop",
            "label": "Stop Stream",
            "enabled": True,
            "reason": "Stop the active VisionPro stream while keeping AVP tracking available.",
        }

    if not snapshot.avp_connected:
        return {
            "action": "start",
            "label": "Start Stream",
            "enabled": False,
            "reason": "Connect AVP first.",
        }

    if not snapshot.camera_connected:
        return {
            "action": "start",
            "label": "Start Stream",
            "enabled": False,
            "reason": "Connect the ZED camera first.",
        }

    return {
        "action": "start",
        "label": "Start Stream",
        "enabled": True,
        "reason": "Start the VisionPro stream using the connected camera.",
    }


def _tracking_action_state(snapshot: SystemSnapshot):
    if snapshot.tracking:
        return {
            "action": "stop",
            "label": "Stop Tracking",
            "enabled": True,
            "reason": "Stop neck tracking and keep the rest of the system connected.",
        }

    if not snapshot.avp_connected:
        return {
            "action": "start",
            "label": "Start Tracking",
            "enabled": False,
            "reason": "Connect AVP first.",
        }

    if not snapshot.motor_connected:
        return {
            "action": "start",
            "label": "Start Tracking",
            "enabled": False,
            "reason": "Connect the neck motors first.",
        }

    if snapshot.tracking_blocked:
        return {
            "action": "start",
            "label": "Start Tracking",
            "enabled": False,
            "reason": snapshot.tracking_block_reason or "Tracking is temporarily unavailable.",
        }

    return {
        "action": "start",
        "label": "Start Tracking",
        "enabled": True,
        "reason": "Start neck tracking using the current Pose Control workflow.",
    }


def _dashboard_state(snapshot: SystemSnapshot, hero_label: str, next_step: str, summary: str) -> DashboardState:
    motor_action = _motor_action_state(snapshot)
    avp_action = _avp_action_state(snapshot)
    stream_action = _stream_action_state(snapshot)
    tracking_action = _tracking_action_state(snapshot)
    connect_camera_enabled = not snapshot.camera_connected
    connect_camera_reason = (
        "Connect the ZED camera for video preview and streaming."
        if connect_camera_enabled
        else "Disconnect the ZED camera."
    )
    camera_action_label = "Connect Camera" if connect_camera_enabled else "Disconnect Camera"
    calibrate_action_enabled = snapshot.motor_connected and not snapshot.tracking
    if not snapshot.motor_connected:
        calibrate_action_reason = "Connect the neck motors first."
    elif snapshot.tracking:
        calibrate_action_reason = "Stop tracking before calibration."
    else:
        calibrate_action_reason = "Move to the saved home position and capture a new center pose."
    if not snapshot.avp_connected:
        severity = "blocked"
        recovery = {
            "title": "AVP not connected",
            "detail": "Use Quick Actions > Device Actions to connect AVP.",
            "action": "connect_avp",
            "label": "Connect AVP",
            "enabled": False,
            "visible": False,
        }
    elif not snapshot.pose_sample_valid:
        severity = "warning" if snapshot.camera_connected else "blocked"
        recovery = {
            "title": "Waiting for first pose sample",
            "detail": (
                "Video streaming can start now, but tracking will stay disabled until the first pose sample arrives."
                if snapshot.camera_connected
                else "Check the Vision Pro app and wait for the first pose sample."
            ),
            "action": "check_avp",
            "label": "Check AVP",
            "enabled": True,
            "visible": True,
        }
    elif snapshot.tracking_blocked:
        severity = "warning"
        recovery = {
            "title": "Tracking is temporarily blocked",
            "detail": snapshot.tracking_block_reason or "Tracking is temporarily unavailable.",
            "action": "toggle_tracking",
            "label": "Start Tracking",
            "enabled": False,
            "visible": False,
        }
    elif snapshot.yaw_inactive:
        severity = "warning"
        recovery = {
            "title": "Yaw input looks inactive",
            "detail": "Consider switching to AVP + Stream and rechecking the pose feed.",
            "action": "check_avp",
            "label": "Check AVP",
            "enabled": True,
            "visible": True,
        }
    elif not snapshot.camera_connected:
        severity = "blocked"
        recovery = {
            "title": "Camera required for stream",
            "detail": "Use Quick Actions > Device Actions to connect the ZED camera.",
            "action": "connect_camera",
            "label": "Connect Camera",
            "enabled": False,
            "visible": False,
        }
    else:
        severity = "ready"
        recovery = {
            "title": "System online",
            "detail": "All key devices are connected. Use Check AVP if tracking needs a quick health check.",
            "action": "check_avp",
            "label": "Check AVP",
            "enabled": True,
            "visible": True,
        }
    return DashboardState(
        hero_label=hero_label,
        severity=severity,
        severity_label=severity.capitalize(),
        next_step=next_step,
        summary=summary,
        motor_action=motor_action["action"],
        motor_action_label=motor_action["label"],
        motor_action_enabled=motor_action["enabled"],
        motor_action_reason=motor_action["reason"],
        avp_action=avp_action["action"],
        avp_action_label=avp_action["label"],
        avp_action_enabled=avp_action["enabled"],
        avp_action_reason=avp_action["reason"],
        connect_camera_enabled=connect_camera_enabled,
        connect_camera_reason=connect_camera_reason,
        stream_action=stream_action["action"],
        stream_action_label=stream_action["label"],
        stream_action_enabled=stream_action["enabled"],
        stream_action_reason=stream_action["reason"],
        tracking_action=tracking_action["action"],
        tracking_action_label=tracking_action["label"],
        tracking_action_enabled=tracking_action["enabled"],
        tracking_action_reason=tracking_action["reason"],
        calibrate_action_label="Move To Home And Calibrate",
        calibrate_action_enabled=calibrate_action_enabled,
        calibrate_action_reason=calibrate_action_reason,
        recovery_title=recovery["title"],
        recovery_detail=recovery["detail"],
        recovery_action=recovery["action"],
        recovery_action_label=recovery["label"],
        recovery_action_enabled=recovery["enabled"],
        recovery_button_visible=recovery["visible"],
    )


def derive_dashboard_state(snapshot: SystemSnapshot) -> DashboardState:
    if snapshot.tracking:
        return _dashboard_state(
            snapshot,
            hero_label="Tracking",
            next_step="Tracking is running.",
            summary=(
                "AVP pose tracking is running."
                if snapshot.avp_session_mode == "tracking_only"
                else "AVP pose and stream are active."
            ),
        )

    if not snapshot.avp_connected:
        return _dashboard_state(
            snapshot,
            hero_label="Waiting for AVP",
            next_step="Connect AVP first.",
            summary="The Vision Pro head pose source is not connected yet.",
        )

    if not snapshot.pose_sample_valid:
        reason = snapshot.pose_sample_reason or "waiting_first_sample"
        if snapshot.camera_connected:
            return _dashboard_state(
                snapshot,
                hero_label="Ready to Stream",
                next_step="Start the VisionPro stream or wait for the first pose sample before tracking.",
                summary=f"AVP is connected and the camera is ready. Tracking is waiting for pose: {reason}.",
            )
        return _dashboard_state(
            snapshot,
            hero_label="Waiting for Pose",
            next_step="Check the Vision Pro app and wait for the first pose sample.",
            summary=f"AVP is connected, but pose is not ready: {reason}.",
        )

    if snapshot.tracking_blocked:
        return _dashboard_state(
            snapshot,
            hero_label="Tracking Blocked",
            next_step=snapshot.tracking_block_reason or "Resolve the current Pose Control block before tracking.",
            summary="Dashboard tracking follows the same start conditions as Pose Control.",
        )

    if snapshot.yaw_inactive:
        return _dashboard_state(
            snapshot,
            hero_label="Yaw Check",
            next_step="Yaw input looks inactive. Consider switching to AVP + Stream and rechecking.",
            summary="Pitch is updating but yaw stays near zero. This usually means the current AVP session is not providing usable yaw.",
        )

    if not snapshot.camera_connected:
        return _dashboard_state(
            snapshot,
            hero_label="Waiting for Camera",
            next_step="Connect the ZED camera.",
            summary="AVP is ready. Camera can be connected independently before streaming.",
        )

    if not snapshot.streaming:
        return _dashboard_state(
            snapshot,
            hero_label="Ready to Stream",
            next_step="Start the VisionPro stream.",
            summary="AVP pose and camera are ready.",
        )

    return _dashboard_state(
        snapshot,
        hero_label="System Ready",
        next_step="You can start normal operation.",
        summary="AVP, camera, and streaming are online.",
    )
