import os
import sys

import numpy as np

# Ensure the project root is in sys.path
root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(root_dir)

from config import config
from src.utils.retargeting import HeadRetargeter
from src.utils.motor_math import deg_to_steps, initial_pose_deg_to_steps


def make_head_pose_matrix(yaw, pitch, roll=0.0):
    yup2zup = np.array([
        [1.0, 0.0, 0.0, 0.0],
        [0.0, 0.0, -1.0, 0.0],
        [0.0, 1.0, 0.0, 0.0],
        [0.0, 0.0, 0.0, 1.0],
    ])

    cy, sy = np.cos(yaw), np.sin(yaw)
    cx, sx = np.cos(pitch), np.sin(pitch)
    cz, sz = np.cos(roll), np.sin(roll)

    rot_y = np.array([
        [cy, 0.0, sy],
        [0.0, 1.0, 0.0],
        [-sy, 0.0, cy],
    ])
    rot_x = np.array([
        [1.0, 0.0, 0.0],
        [0.0, cx, -sx],
        [0.0, sx, cx],
    ])
    rot_z = np.array([
        [cz, -sz, 0.0],
        [sz, cz, 0.0],
        [0.0, 0.0, 1.0],
    ])

    raw_pose = np.eye(4)
    raw_pose[:3, :3] = rot_y.dot(rot_x).dot(rot_z)

    rot_x_neg_90 = np.array([
        [1.0, 0.0, 0.0, 0.0],
        [0.0, 0.0, 1.0, 0.0],
        [0.0, -1.0, 0.0, 0.0],
        [0.0, 0.0, 0.0, 1.0],
    ])
    return yup2zup.dot(raw_pose).dot(rot_x_neg_90)


def set_config_attr(name, value):
    had_attr = hasattr(config, name)
    old_value = getattr(config, name, None)
    setattr(config, name, value)
    return had_attr, old_value


def restore_config_attr(name, state):
    had_attr, old_value = state
    if had_attr:
        setattr(config, name, old_value)
    else:
        delattr(config, name)


def test_raw_neck_input_ignores_base_imu_when_compensation_disabled():
    state = set_config_attr("ENABLE_IMU_COMPENSATION", False)
    try:
        pose = make_head_pose_matrix(0.3, -0.2)
        retargeter = HeadRetargeter()

        raw_no_imu = retargeter.compute_raw_neck_input(pose, base_imu_rpy=None)
        raw_with_imu = retargeter.compute_raw_neck_input(pose, base_imu_rpy=(0.6, 0.4, 0.0))

        assert np.allclose(raw_no_imu, raw_with_imu)
        assert np.allclose(raw_no_imu, (-0.3, 0.2))
    finally:
        restore_config_attr("ENABLE_IMU_COMPENSATION", state)


def test_raw_neck_input_applies_base_imu_when_compensation_enabled():
    state = set_config_attr("ENABLE_IMU_COMPENSATION", True)
    try:
        pose = make_head_pose_matrix(0.3, -0.2)
        retargeter = HeadRetargeter()

        raw_yaw, raw_pitch = retargeter.compute_raw_neck_input(
            pose, base_imu_rpy=(0.1, 0.05, 0.0)
        )

        assert np.isclose(raw_yaw, -0.4)
        assert np.isclose(raw_pitch, 0.15)
    finally:
        restore_config_attr("ENABLE_IMU_COMPENSATION", state)


def test_initial_pose_angle_conversion_maps_degrees_to_motor_steps():
    assert deg_to_steps(0.0) == config.ZERO_POS
    assert deg_to_steps(90.0) == config.ZERO_POS + 1024
    assert deg_to_steps(-90.0) == config.ZERO_POS - 1024

    steps = initial_pose_deg_to_steps(15.0, -20.0)

    assert steps == {
        config.YAW_MOTOR_ID: deg_to_steps(15.0),
        config.PITCH_MOTOR_ID: deg_to_steps(-20.0),
    }
