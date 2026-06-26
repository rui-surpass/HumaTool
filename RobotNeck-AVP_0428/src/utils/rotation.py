import math

import numpy as np


def _as_rotation_matrix(matrix_or_pose):
    matrix = np.asarray(matrix_or_pose, dtype=float)
    if matrix.shape == (4, 4):
        return matrix[:3, :3]
    return matrix


def matrix_to_euler_yxz(matrix_or_pose):
    """
    Convert a 3x3 or 4x4 rotation matrix into Euler angles in YXZ order.
    Returns (yaw, pitch, roll) in radians.
    """
    matrix = _as_rotation_matrix(matrix_or_pose)

    sin_pitch = float(-matrix[1, 2])
    sin_pitch = max(-1.0, min(1.0, sin_pitch))
    pitch = math.asin(sin_pitch)
    cos_pitch = math.cos(pitch)

    if abs(cos_pitch) > 1e-8:
        yaw = math.atan2(matrix[0, 2], matrix[2, 2])
        roll = math.atan2(matrix[1, 0], matrix[1, 1])
    else:
        # Gimbal-lock fallback: keep roll at zero and solve yaw from the remaining terms.
        roll = 0.0
        if pitch >= 0.0:
            yaw = math.atan2(-matrix[2, 0], matrix[0, 0])
        else:
            yaw = math.atan2(matrix[2, 0], matrix[0, 0])

    return yaw, pitch, roll


def quaternion_to_matrix(quaternion_xyzw):
    """
    Convert a quaternion [x, y, z, w] into a 3x3 rotation matrix.
    """
    x, y, z, w = [float(v) for v in quaternion_xyzw]
    norm = math.sqrt(x * x + y * y + z * z + w * w)
    if norm == 0.0:
        return np.eye(3)

    x /= norm
    y /= norm
    z /= norm
    w /= norm

    xx = x * x
    yy = y * y
    zz = z * z
    xy = x * y
    xz = x * z
    yz = y * z
    wx = w * x
    wy = w * y
    wz = w * z

    return np.array([
        [1.0 - 2.0 * (yy + zz), 2.0 * (xy - wz), 2.0 * (xz + wy)],
        [2.0 * (xy + wz), 1.0 - 2.0 * (xx + zz), 2.0 * (yz - wx)],
        [2.0 * (xz - wy), 2.0 * (yz + wx), 1.0 - 2.0 * (xx + yy)],
    ])


def quaternion_to_euler_yxz(quaternion_xyzw):
    """Convert quaternion [x, y, z, w] into Euler angles in YXZ order."""
    return matrix_to_euler_yxz(quaternion_to_matrix(quaternion_xyzw))
