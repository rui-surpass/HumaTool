import os
import sys

import numpy as np


root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(root_dir)

from src.utils.retargeting import HeadRetargeter


YUP2ZUP = np.array(
    [
        [1.0, 0.0, 0.0, 0.0],
        [0.0, 0.0, -1.0, 0.0],
        [0.0, 1.0, 0.0, 0.0],
        [0.0, 0.0, 0.0, 1.0],
    ]
)


def rot_x(angle):
    c = np.cos(angle)
    s = np.sin(angle)
    return np.array(
        [
            [1.0, 0.0, 0.0, 0.0],
            [0.0, c, -s, 0.0],
            [0.0, s, c, 0.0],
            [0.0, 0.0, 0.0, 1.0],
        ]
    )


def rot_y(angle):
    c = np.cos(angle)
    s = np.sin(angle)
    return np.array(
        [
            [c, 0.0, s, 0.0],
            [0.0, 1.0, 0.0, 0.0],
            [-s, 0.0, c, 0.0],
            [0.0, 0.0, 0.0, 1.0],
        ]
    )


def make_streamed_head_pose(yaw_rad=0.0, pitch_rad=0.0):
    source = rot_y(yaw_rad) @ rot_x(pitch_rad)
    return YUP2ZUP @ source @ rot_x(np.deg2rad(-90.0))


def make_ready_retargeter():
    retargeter = HeadRetargeter()
    retargeter._pending_calibration = False
    retargeter.calibrated = True
    retargeter.yaw_offset = 0.0
    retargeter.pitch_offset = 0.0
    return retargeter


def test_streamed_head_pitch_maps_to_pitch_axis_not_yaw():
    retargeter = make_ready_retargeter()

    yaw_target, pitch_target = retargeter.compute_neck_target(
        make_streamed_head_pose(pitch_rad=0.2)
    )

    assert np.isclose(yaw_target, 0.0, atol=1e-6)
    assert not np.isclose(pitch_target, 0.0, atol=1e-3)


def test_streamed_head_yaw_maps_to_yaw_axis_not_pitch():
    retargeter = make_ready_retargeter()

    yaw_target, pitch_target = retargeter.compute_neck_target(
        make_streamed_head_pose(yaw_rad=0.35)
    )

    assert not np.isclose(yaw_target, 0.0, atol=1e-3)
    assert np.isclose(pitch_target, 0.0, atol=1e-6)
