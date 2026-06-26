import json
import os

from config import config
from src.core.calibration import TrackingStartPoseCalibration
from src.core.paths import get_tracking_start_path
from src.utils.motor_math import initial_pose_deg_to_steps, steps_to_deg


def default_tracking_start_pose_steps():
    init_steps = initial_pose_deg_to_steps(
        config.INITIAL_POSE.get("yaw", 0.0),
        config.INITIAL_POSE.get("pitch", 0.0),
    )
    return {
        "yaw_start_step": int(init_steps[config.YAW_MOTOR_ID]),
        "pitch_start_step": int(init_steps[config.PITCH_MOTOR_ID]),
    }


def get_tracking_start_store(path=None):
    default_steps = default_tracking_start_pose_steps()
    return TrackingStartPoseCalibration(
        path or get_tracking_start_path(),
        default_yaw_step=default_steps["yaw_start_step"],
        default_pitch_step=default_steps["pitch_start_step"],
    )


def resolve_tracking_start_pose_steps(path=None):
    return get_tracking_start_store(path).load()


def load_tracking_start_pose_record(path=None):
    resolved_path = str(path or get_tracking_start_path())
    default_steps = default_tracking_start_pose_steps()
    if not os.path.exists(resolved_path):
        return {
            "path": resolved_path,
            "has_saved_record": False,
            "current": dict(default_steps),
            "previous": dict(default_steps),
        }

    with open(resolved_path, "r", encoding="utf-8") as handle:
        data = json.load(handle)

    return {
        "path": resolved_path,
        "has_saved_record": True,
        "current": dict(data.get("current", default_steps)),
        "previous": dict(data.get("previous", default_steps)),
    }


def save_tracking_start_pose_steps(yaw_start_step, pitch_start_step, path=None):
    return get_tracking_start_store(path).save(yaw_start_step, pitch_start_step)


def save_tracking_start_pose_from_angles(yaw_deg, pitch_deg, path=None):
    init_steps = initial_pose_deg_to_steps(yaw_deg, pitch_deg)
    return save_tracking_start_pose_steps(
        init_steps[config.YAW_MOTOR_ID],
        init_steps[config.PITCH_MOTOR_ID],
        path=path,
    )


def rollback_tracking_start_pose(path=None):
    return get_tracking_start_store(path).rollback()


def tracking_start_steps_to_degrees(pose_steps):
    return {
        "yaw": float(steps_to_deg(pose_steps["yaw_start_step"])),
        "pitch": float(steps_to_deg(pose_steps["pitch_start_step"])),
    }


def capture_tracking_start_pose(motor_controller, path=None):
    if motor_controller is None or not hasattr(motor_controller, "get_present_position"):
        raise RuntimeError("Motor controller does not support reading present position.")

    yaw_step = motor_controller.get_present_position(config.YAW_MOTOR_ID)
    pitch_step = motor_controller.get_present_position(config.PITCH_MOTOR_ID)
    if yaw_step is None or pitch_step is None:
        raise RuntimeError("Failed to read current motor position.")

    return save_tracking_start_pose_steps(yaw_step, pitch_step, path=path)
