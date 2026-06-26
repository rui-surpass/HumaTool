import numpy as np


def extract_yxz_euler(rotation_matrix):
    """
    Extract yaw, pitch, roll from a rotation matrix using a Y-X-Z interpretation.
    """
    matrix = np.asarray(rotation_matrix)
    if matrix.shape == (4, 4):
        matrix = matrix[:3, :3]

    pitch = np.arcsin(np.clip(-matrix[1, 2], -1.0, 1.0))
    cos_pitch = np.cos(pitch)

    if abs(cos_pitch) < 1e-6:
        yaw = np.arctan2(-matrix[2, 0], matrix[0, 0])
        roll = 0.0
    else:
        yaw = np.arctan2(matrix[0, 2], matrix[2, 2])
        roll = np.arctan2(matrix[1, 0], matrix[1, 1])

    return yaw, pitch, roll


def extract_avp_head_euler(rotation_matrix):
    """
    Extract yaw, pitch, roll from the head matrix produced by VisionProTeleop.

    VisionProTeleop applies YUP->ZUP and an additional -90 degree rotation
    around X before publishing the head pose. After that conversion, head yaw
    is around Z and pitch remains around X.
    """
    matrix = np.asarray(rotation_matrix)
    if matrix.shape == (4, 4):
        matrix = matrix[:3, :3]

    pitch = np.arcsin(np.clip(matrix[2, 1], -1.0, 1.0))
    cos_pitch = np.cos(pitch)

    if abs(cos_pitch) < 1e-6:
        yaw = np.arctan2(matrix[1, 0], matrix[0, 0])
        roll = 0.0
    else:
        yaw = np.arctan2(-matrix[0, 1], matrix[1, 1])
        roll = np.arctan2(-matrix[2, 0], matrix[2, 2])

    return yaw, pitch, roll


def extract_avp_head_angles(rotation_matrix):
    yaw, pitch, _roll = extract_avp_head_euler(rotation_matrix)
    return yaw, pitch
