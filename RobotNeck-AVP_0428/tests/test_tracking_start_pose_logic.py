import os
import sys


root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(root_dir)

from config import config
from src.hardware.mock_motor import MockMotorController
from src.core.tracking_start import (
    capture_tracking_start_pose,
    load_tracking_start_pose_record,
    resolve_tracking_start_pose_steps,
    save_tracking_start_pose_from_angles,
)
from src.utils.motor_math import deg_to_steps


def test_resolve_tracking_start_pose_steps_falls_back_to_initial_pose(tmpdir):
    resolved = resolve_tracking_start_pose_steps(tmpdir.join("tracking_start_pose.json"))

    assert resolved == {
        "yaw_start_step": deg_to_steps(config.INITIAL_POSE.get("yaw", 0.0)),
        "pitch_start_step": deg_to_steps(config.INITIAL_POSE.get("pitch", 0.0)),
    }


def test_save_tracking_start_pose_from_angles_persists_converted_steps(tmpdir):
    saved = save_tracking_start_pose_from_angles(
        12.5,
        -18.0,
        tmpdir.join("tracking_start_pose.json"),
    )

    assert saved == {
        "yaw_start_step": deg_to_steps(12.5),
        "pitch_start_step": deg_to_steps(-18.0),
    }

    assert resolve_tracking_start_pose_steps(tmpdir.join("tracking_start_pose.json")) == saved


def test_capture_tracking_start_pose_reads_motor_steps_and_saves_them(tmpdir):
    motor = MockMotorController()
    motor.mock_pos[config.YAW_MOTOR_ID] = 2345
    motor.mock_pos[config.PITCH_MOTOR_ID] = 1678

    saved = capture_tracking_start_pose(motor, tmpdir.join("tracking_start_pose.json"))

    assert saved == {
        "yaw_start_step": 2345,
        "pitch_start_step": 1678,
    }
    assert resolve_tracking_start_pose_steps(tmpdir.join("tracking_start_pose.json")) == saved


def test_load_tracking_start_pose_record_returns_current_and_previous(tmpdir):
    path = tmpdir.join("tracking_start_pose.json")
    save_tracking_start_pose_from_angles(5.0, -5.0, path)
    save_tracking_start_pose_from_angles(10.0, -12.0, path)

    record = load_tracking_start_pose_record(path)

    assert record["has_saved_record"] is True
    assert record["current"] == {
        "yaw_start_step": deg_to_steps(10.0),
        "pitch_start_step": deg_to_steps(-12.0),
    }
    assert record["previous"] == {
        "yaw_start_step": deg_to_steps(5.0),
        "pitch_start_step": deg_to_steps(-5.0),
    }
