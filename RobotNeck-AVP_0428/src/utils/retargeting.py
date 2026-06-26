import logging

import numpy as np
from config import config
from src.utils.orientation import extract_avp_head_euler

logger = logging.getLogger(__name__)

class EMASmoother:
    """
    Exponential Moving Average smoother for scalar values.
    """
    def __init__(self, alpha=0.5, initial_value=None):
        self.alpha = alpha
        self.value = initial_value

    def update(self, new_value):
        if self.value is None:
            self.value = new_value
        else:
            self.value = self.alpha * new_value + (1 - self.alpha) * self.value
        return self.value

class HeadRetargeter:
    """
    Handles the coordinate transformation and angle extraction from 
    Apple Vision Pro (AVP) head pose to Robot Neck motors (Yaw, Pitch).
    """

    def __init__(self):
        # Initialize smoothers for Yaw and Pitch
        # Alpha from config: default 0.2 (strong smoothing) -> 1.0 (no smoothing)
        alpha = getattr(config, 'SMOOTHING_ALPHA', 0.2)
        self.yaw_smoother = EMASmoother(alpha=alpha)
        self.pitch_smoother = EMASmoother(alpha=alpha)
        
        # Calibration offsets
        self.yaw_offset = 0.0
        self.pitch_offset = 0.0
        self.calibrated = False
        self._pending_calibration = True # Auto-calibrate on first successful frame(s)

    def trigger_calibration(self):
        """
        Flag to capture the next frame as the zero point.
        """
        self._pending_calibration = True

    def reset_calibration(self):
        """
        Reset offsets to zero (Absolute AVP Pose).
        """
        self.yaw_offset = 0.0
        self.pitch_offset = 0.0
        self.calibrated = False
        logger.info("Calibration reset to absolute pose.")

    def sync_offsets(self, avp_yaw, avp_pitch, robot_yaw, robot_pitch):
        """
        Set offsets such that (AVP - Offset) = Robot.
        Offset = AVP - Robot.
        Used to prevent jumping when starting tracking.
        """
        # Note: AVP/Robot yaw/pitch should be in same coordinate frame/direction
        # compute_neck_target does scaling/direction internally, so we might need to be careful.
        # Ideally we act on raw input.
        # But compute_neck_target logic is: Target = -AVP - Offset.
        # We want: Target = Robot.
        # Robot = -AVP - Offset => Offset = -AVP - Robot.
        
        # Check standard mapping in compute_neck_target:
        # raw_yaw = -avp_yaw
        # target_yaw = raw_yaw - self.yaw_offset
        # So: target_yaw = -avp_yaw - self.yaw_offset
        # We want target_yaw = robot_yaw
        # robot_yaw = -avp_yaw - self.yaw_offset
        # self.yaw_offset = -avp_yaw - robot_yaw
        
        self.yaw_offset = -avp_yaw - robot_yaw
        self.pitch_offset = -avp_pitch - robot_pitch
        
        self.calibrated = True
        self._pending_calibration = False
        logger.info("Calibration synced to robot pose. yaw_offset=%.3f", self.yaw_offset)

    def compute_raw_neck_input(self, head_pose_mat, base_imu_rpy=None):
        """
        Convert AVP head pose into raw robot yaw/pitch input before calibration/smoothing.

        Args:
            head_pose_mat (np.ndarray): 4x4 Homogeneous matrix or 3x3 Rotation matrix from AVP.
            base_imu_rpy (tuple, optional): (yaw, pitch, roll) in radians from robot base IMU. 
                                            If provided, compensates for base movement.

        Returns:
            tuple: (yaw, pitch) in radians.
        """
        # 1. Coordinate System Conversion
        # AVP uses Y-up. We typically want to extract Yaw (around gravity) and Pitch (elevation).
        # In AVP frame:
        #   Yaw is rotation around Y-axis.
        #   Pitch is rotation around local X-axis.
        
        avp_yaw, avp_pitch, avp_roll = extract_avp_head_euler(head_pose_mat)
        
        # Note on direction: 
        # AVP Yaw: +Left/-Right 
        # Robot Yaw: +Left/-Right (Standard ROS)
        
        # Reverting to negative (standard mapping) + Debugging
        raw_yaw = -avp_yaw   
        raw_pitch = -avp_pitch 
        
        # DEBUG: Print raw values to help diagnose mapping
        # print(f"DEBUG: AVP Yaw={avp_yaw:.2f} -> Robot Yaw={raw_yaw:.2f}") 
        # print(f"DEBUG: AVP Pitch={avp_pitch:.2f} -> Robot Pitch={raw_pitch:.2f}") 
        
        # 2. Compensate for Base IMU only when explicitly enabled.
        if getattr(config, 'ENABLE_IMU_COMPENSATION', False) and base_imu_rpy is not None:
            # base_imu_rpy expected in Robot Frame (Z-up)
            # yaw, pitch, roll (from src/core/app.py logic)
            b_yaw, b_pitch, b_roll = base_imu_rpy
            
            # Yaw is global (Z-axis)
            raw_yaw -= b_yaw
            
            # Pitch compensation (simplified)
            raw_pitch -= b_pitch

        return raw_yaw, raw_pitch

    def sync_with_robot_pose(self, head_pose_mat, robot_yaw, robot_pitch, base_imu_rpy=None):
        """
        Sync offsets so the current AVP pose matches the current robot pose.
        """
        raw_yaw, raw_pitch = self.compute_raw_neck_input(head_pose_mat, base_imu_rpy=base_imu_rpy)
        self.yaw_offset = raw_yaw - robot_yaw
        self.pitch_offset = raw_pitch - robot_pitch
        self.calibrated = True
        self._pending_calibration = False
        logger.info("Calibration synced to current robot pose. yaw_offset=%.3f", self.yaw_offset)

    def compute_neck_target(self, head_pose_mat, base_imu_rpy=None):
        """
        Compute target Yaw and Pitch for the robot neck.

        Args:
            head_pose_mat (np.ndarray): 4x4 Homogeneous matrix or 3x3 Rotation matrix from AVP.
            base_imu_rpy (tuple, optional): (yaw, pitch, roll) in radians from robot base IMU. 
                                            If provided and enabled, compensates for base movement.

        Returns:
            tuple: (yaw, pitch) in radians, ensuring ranges are safe.
        """
        raw_yaw, raw_pitch = self.compute_raw_neck_input(head_pose_mat, base_imu_rpy=base_imu_rpy)
        
        # 5. Check Calibration
        if self._pending_calibration:
            self.yaw_offset = raw_yaw
            self.pitch_offset = raw_pitch
            self.calibrated = True
            self._pending_calibration = False
            logger.info(
                "Calibration zero point set. yaw_offset=%.3f pitch_offset=%.3f",
                self.yaw_offset,
                self.pitch_offset,
            )

        # 6. Apply Calibration Offsets
        # We subtract the offset from the raw global angle to get relative angle from "zero"
        target_yaw = raw_yaw - self.yaw_offset
        target_pitch = raw_pitch - self.pitch_offset

        # 7. Apply Smoothing (on the calibrated target)
        smooth_yaw = self.yaw_smoother.update(target_yaw)
        smooth_pitch = self.pitch_smoother.update(target_pitch)

        return smooth_yaw, smooth_pitch
