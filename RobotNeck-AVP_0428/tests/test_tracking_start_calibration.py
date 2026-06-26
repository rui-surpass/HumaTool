import os
import sys


root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(root_dir)

from src.core.calibration import TrackingStartPoseCalibration


def test_tracking_start_calibration_loads_default_when_file_missing(tmpdir):
    calibration = TrackingStartPoseCalibration(
        tmpdir.join("tracking_start_pose.json"),
        default_yaw_step=2100,
        default_pitch_step=1900,
    )

    assert calibration.load() == {
        "yaw_start_step": 2100,
        "pitch_start_step": 1900,
    }


def test_tracking_start_calibration_save_keeps_current_and_previous(tmpdir):
    calibration = TrackingStartPoseCalibration(
        tmpdir.join("tracking_start_pose.json"),
        default_yaw_step=2048,
        default_pitch_step=2048,
    )

    calibration.save(2200, 1800)
    saved = calibration.save(2300, 1700)

    assert saved == {
        "yaw_start_step": 2300,
        "pitch_start_step": 1700,
    }

    assert calibration.load() == saved

    with open(str(tmpdir.join("tracking_start_pose.json")), "r", encoding="utf-8") as handle:
        payload = handle.read()

    assert '"current"' in payload
    assert '"previous"' in payload
    assert '"yaw_start_step": 2200' in payload
    assert '"pitch_start_step": 1800' in payload


def test_tracking_start_calibration_rollback_restores_previous_record(tmpdir):
    calibration = TrackingStartPoseCalibration(
        tmpdir.join("tracking_start_pose.json"),
        default_yaw_step=2048,
        default_pitch_step=2048,
    )

    calibration.save(2200, 1800)
    calibration.save(2300, 1700)

    rolled_back = calibration.rollback()

    assert rolled_back == {
        "yaw_start_step": 2200,
        "pitch_start_step": 1800,
    }
    assert calibration.load() == rolled_back
