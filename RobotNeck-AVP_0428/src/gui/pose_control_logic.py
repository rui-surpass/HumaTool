def format_pose_text(pose):
    return f"Yaw {pose['yaw']:.1f} deg | Pitch {pose['pitch']:.1f} deg"


def build_tracking_start_display(current_pose, previous_pose, path, has_saved_record):
    source_prefix = "Saved record" if has_saved_record else "Config fallback"
    return {
        "current_text": format_pose_text(current_pose),
        "previous_text": format_pose_text(previous_pose),
        "source_text": f"{source_prefix}: {path}",
    }


def build_pose_control_view_state(motors_connected, is_tracking, manual_adjust_active):
    if not motors_connected:
        status_text = "Disconnected"
        step_message = "Connect motors before manual adjustment. Manual angle input can still be saved."
    elif manual_adjust_active:
        status_text = "Manual Adjust"
        step_message = "Torque released. Adjust the neck by hand, then click 'Read Motor Pose & Save'."
    elif is_tracking:
        status_text = "Tracking"
        step_message = "Tracking head pose in real time."
    else:
        status_text = "Idle"
        step_message = "Review the saved home position, then calibrate or start tracking."

    return {
        "status_text": status_text,
        "step_message": step_message,
        "release_enabled": motors_connected and not manual_adjust_active,
        "capture_enabled": motors_connected and manual_adjust_active,
        "tracking_enabled": not manual_adjust_active,
    }


def resolve_base_imu(camera_controller, imu_enabled):
    if not imu_enabled or camera_controller is None:
        return None
    return camera_controller.get_imu_data()


def calculate_pose_age_ms(pose_status, monotonic_now, wall_now):
    pose_status = dict(pose_status or {})

    explicit_age_ms = pose_status.get("age_ms")
    if isinstance(explicit_age_ms, (int, float)):
        return round(max(0.0, float(explicit_age_ms)), 1)

    last_sample_monotonic = pose_status.get("last_sample_monotonic")
    if isinstance(last_sample_monotonic, (int, float)):
        return round(max(0.0, float(monotonic_now) - float(last_sample_monotonic)) * 1000.0, 1)

    last_sample_wall_time = pose_status.get("last_sample_wall_time")
    if isinstance(last_sample_wall_time, (int, float)):
        return round(max(0.0, float(wall_now) - float(last_sample_wall_time)) * 1000.0, 1)

    last_sample_timestamp = pose_status.get("last_sample_timestamp")
    if isinstance(last_sample_timestamp, (int, float)):
        reference_now = float(wall_now) if float(last_sample_timestamp) > 1_000_000_000 else float(monotonic_now)
        return round(max(0.0, reference_now - float(last_sample_timestamp)) * 1000.0, 1)

    return None


def should_skip_motor_update(
    pose_status,
    is_tracking,
    motor_commands,
    last_command_targets_deg,
    command_targets_deg,
    min_delta_deg=0.05,
):
    if not is_tracking:
        return True, "not_tracking"
    if not motor_commands:
        return True, "no_motor_commands"

    pose_status = dict(pose_status or {})
    if not bool(pose_status.get("fresh", False)):
        return True, "stale_pose"

    last_command_targets_deg = dict(last_command_targets_deg or {})
    command_targets_deg = dict(command_targets_deg or {})
    last_yaw = last_command_targets_deg.get("yaw")
    last_pitch = last_command_targets_deg.get("pitch")
    yaw = command_targets_deg.get("yaw")
    pitch = command_targets_deg.get("pitch")
    if all(isinstance(value, (int, float)) for value in (last_yaw, last_pitch, yaw, pitch)):
        if abs(float(yaw) - float(last_yaw)) < min_delta_deg and abs(float(pitch) - float(last_pitch)) < min_delta_deg:
            return True, "unchanged_target"

    return False, ""
