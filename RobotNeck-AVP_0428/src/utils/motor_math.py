import numpy as np

from config import config


def rad_to_steps(rad):
    """Convert radians to Dynamixel steps using the configured center position."""
    steps_from_center = rad * (config.STEPS_PER_REV / (2 * np.pi))
    target = config.ZERO_POS + steps_from_center
    return int(max(0, min(config.STEPS_PER_REV - 1, target)))


def deg_to_steps(deg):
    """Convert degrees to Dynamixel steps."""
    return rad_to_steps(np.deg2rad(deg))


def steps_to_rad(steps):
    """Convert Dynamixel steps back into radians around the configured center."""
    return (steps - config.ZERO_POS) * (2 * np.pi / config.STEPS_PER_REV)


def steps_to_deg(steps):
    """Convert Dynamixel steps back into degrees."""
    return np.rad2deg(steps_to_rad(steps))


def initial_pose_deg_to_steps(yaw_deg, pitch_deg):
    """Convert yaw/pitch degrees into a motor command dictionary."""
    return {
        config.YAW_MOTOR_ID: deg_to_steps(yaw_deg),
        config.PITCH_MOTOR_ID: deg_to_steps(pitch_deg),
    }
