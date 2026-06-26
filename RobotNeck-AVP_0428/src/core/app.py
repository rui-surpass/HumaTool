
import time
import numpy as np
from config import config
from src.core.camera_controller import CameraController
from src.core.client import AVPClient
from src.core.tracking_start import resolve_tracking_start_pose_steps
from src.hardware.motor import MotorController
from src.utils.retargeting import HeadRetargeter
from src.utils.motor_math import rad_to_steps, steps_to_deg

class MockMotorController:
    """
    用于测试的虚拟电机控制器，当没有连接真实硬件时使用。
    """
    def __init__(self):
        print("Mock Motor Controller Initialized")
    def enable_torque(self, motor_id, enable=True):
        print(f"Mock: Torque {'enabled' if enable else 'disabled'} for ID {motor_id}")
    def set_goal_position(self, motor_id, position):
        print(f"Mock: Set ID {motor_id} to {position}")
    def set_goal_positions(self, id_pos_dict):
        print(f"Mock: Set multiple positions: {id_pos_dict}")
    def close(self):
        print("Mock: Controller closed")

class MockAVPClient:
    """
    用于测试的虚拟 AVP 客户端，生成模拟的头部姿态数据。
    """
    def __init__(self):
        print("Mock AVP Client Initialized")
        self.t = 0
    
    def get_latest_head_pose(self):
        """生成基于时间的正弦波姿态数据 (Legacy)."""
        self.t += 0.1
        yaw = 0.5 * np.sin(self.t)
        pitch = 0.2 * np.cos(self.t)
        roll = 0.0
        return yaw, pitch, roll

    def get_latest_head_pose_matrix(self):
        """生成模拟的头部姿态矩阵 (4x4)"""
        # 简单生成一个旋转矩阵
        # 假设 AVP 坐标系下的 Yaw/Pitch
        self.t += 0.1
        yaw = 0.5 * np.sin(self.t)
        pitch = 0.2 * np.cos(self.t)
        
        # 简单的旋转矩阵构造 (模拟 AVP Y-up)
        # Ry(yaw)
        cy, sy = np.cos(yaw), np.sin(yaw)
        
        # Y-rotation matrix
        # [ cy  0  sy]
        # [ 0   1  0 ]
        # [-sy  0  cy]
        
        rot = np.eye(4)
        rot[0,0] = cy;  rot[0,2] = sy
        rot[1,1] = 1
        rot[2,0] = -sy; rot[2,2] = cy
        
        return rot

    def start_video_stream(self, frame_source=None, resolution=None, fps=None, bitrate=None, stereo=True, latency="Balanced"):
        print("Mock: Video stream started (Simulated)")

    def get_camera_imu(self):
        # 模拟 IMU 数据: 假设底座静止 [0, 0, 0] 或缓慢移动
        # 返回: yaw, pitch, roll
        return 0.0, 0.0, 0.0

def run_app():
    """
    RoboNeck-AVP 主控制循环。
    """
    print("Starting RoboNeck-AVP...")
    
    # 初始化客户端
    if config.MOCK_AVP:
        avp = MockAVPClient(config.AVP_IP)
    else:
        avp = AVPClient(config.AVP_IP)
        avp.connect(ip=config.AVP_IP, auto_reconnect=False)
    camera_controller = CameraController()

    if config.MOCK_MOTORS:
        motors = MockMotorController()
    else:
        motors = MotorController(config.DYNAMIXEL_PORT, config.BAUDRATE)
    
    # 初始化 Retargeter
    retargeter = HeadRetargeter()
        
    # 如果启用，启动视频流
    if (
        (hasattr(config, 'ENABLE_VIDEO') and config.ENABLE_VIDEO)
        or getattr(config, 'ENABLE_IMU_COMPENSATION', False)
    ):
        camera_controller.open_camera(config.STREAM_RESOLUTION, config.STREAM_FPS)

    if hasattr(config, 'ENABLE_VIDEO') and config.ENABLE_VIDEO:
        avp.start_video_stream(
            frame_source=camera_controller if camera_controller.is_connected else None,
            resolution=config.STREAM_RESOLUTION,
            fps=config.STREAM_FPS,
        )
        
    # 初始化电机模式 (确保为位置控制模式)
    if not config.MOCK_MOTORS:
        print("Configuring Motor Operating Modes...")
        motors.enable_torque(config.YAW_MOTOR_ID, False)
        motors.enable_torque(config.PITCH_MOTOR_ID, False)
        motors.set_operating_mode(config.YAW_MOTOR_ID, 3)
        motors.set_operating_mode(config.PITCH_MOTOR_ID, 3)

    # 启用扭矩
    motors.enable_torque(config.YAW_MOTOR_ID, True)
    motors.enable_torque(config.PITCH_MOTOR_ID, True)

    # 设置平滑运动参数
    if hasattr(motors, 'set_profile') and not config.MOCK_MOTORS:
        # 设置 Profile Velocity 和 Profile Acceleration
        # Increase values for responsiveness (let EMA handle smoothness)
        # 0 = Max Velocity (Infinite)
        motors.set_profile(config.YAW_MOTOR_ID, velocity=0, acceleration=500)
        motors.set_profile(config.PITCH_MOTOR_ID, velocity=0, acceleration=500)

    # -------------------------------------------------------------------------
    # 初始化校准 (Initialization Calibration)
    # 移动到预设的初始姿态 (INITIAL_POSE)
    # -------------------------------------------------------------------------
    if hasattr(config, 'ENABLE_INIT_CALIBRATION') and config.ENABLE_INIT_CALIBRATION:
        init_pose = resolve_tracking_start_pose_steps()
        init_yaw_steps = init_pose["yaw_start_step"]
        init_pitch_steps = init_pose["pitch_start_step"]
        init_yaw_deg = steps_to_deg(init_yaw_steps)
        init_pitch_deg = steps_to_deg(init_pitch_steps)

        print(
            f"\n[Init] Performing Initialization Calibration to "
            f"yaw={init_yaw_deg:.1f} deg, pitch={init_pitch_deg:.1f} deg "
            f"(steps: {init_yaw_steps}, {init_pitch_steps})..."
        )
        
        init_cmd = {}
        if config.YAW_LIMIT_DEG[0] <= init_yaw_deg <= config.YAW_LIMIT_DEG[1]:
            init_cmd[config.YAW_MOTOR_ID] = init_yaw_steps
            print(f"[Init] Yaw Target: {init_yaw_deg} deg -> {init_yaw_steps} steps")
            
        if config.PITCH_LIMIT_DEG[0] <= init_pitch_deg <= config.PITCH_LIMIT_DEG[1]:
             init_cmd[config.PITCH_MOTOR_ID] = init_pitch_steps
             print(f"[Init] Pitch Target: {init_pitch_deg} deg -> {init_pitch_steps} steps")

        # 发送指令
        if init_cmd:
            if hasattr(motors, 'set_goal_positions'):
                    motors.set_goal_positions(init_cmd)
            else:
                for mid, pos in init_cmd.items():
                        motors.set_goal_position(mid, pos)
            
            # 等待移动到位
            print("[Init] Moving... Waiting 2.0s to settle.")
            time.sleep(2.0)
            print("[Init] Complete.\n")
    # -------------------------------------------------------------------------
    
    print("Control Loop Started. Press Ctrl+C to stop.")
    
    try:
        loop_count = 0
        while True:
            start_time = time.time()
            loop_count += 1
            
            # 定期监控电机状态
            if loop_count % 100 == 0 and not config.MOCK_MOTORS:
                status_yaw = motors.read_status(config.YAW_MOTOR_ID)
                pass 

            # 获取姿态矩阵
            pose_data = avp.get_latest_head_pose_matrix()
            
            if pose_data is not None:
                # 获取机器人底座姿态 (来自 ZED IMU)
                base_imu = camera_controller.get_imu_data() if getattr(config, 'ENABLE_IMU_COMPENSATION', False) else None
                
                # Compute targets using Retargeter
                yaw_target, pitch_target = retargeter.compute_neck_target(pose_data, base_imu_rpy=base_imu)
                
                if config.MOCK_AVP and loop_count % 100 == 0:
                     print(f"Retargeting: Target Yaw={yaw_target:.2f}, Pitch={pitch_target:.2f}")

                # 应用缩放
                yaw_cmd = yaw_target * config.YAW_SCALE
                pitch_cmd = pitch_target * config.PITCH_SCALE
                
                # 应用限制（转换为度数进行检查）
                yaw_deg = np.rad2deg(yaw_cmd)
                pitch_deg = np.rad2deg(pitch_cmd)
                
                motor_commands = {}

                if config.YAW_LIMIT_DEG[0] <= yaw_deg <= config.YAW_LIMIT_DEG[1]:
                    yaw_steps = rad_to_steps(yaw_cmd)
                    motor_commands[config.YAW_MOTOR_ID] = yaw_steps
                
                if config.PITCH_LIMIT_DEG[0] <= pitch_deg <= config.PITCH_LIMIT_DEG[1]:
                    # 确定俯仰方向
                    pitch_steps = rad_to_steps(pitch_cmd) 
                    motor_commands[config.PITCH_MOTOR_ID] = pitch_steps
                
                # 同步发送指令 (SyncWrite)
                if motor_commands:
                    if hasattr(motors, 'set_goal_positions'):
                         motors.set_goal_positions(motor_commands)
                    else:
                        for mid, pos in motor_commands.items():
                             motors.set_goal_position(mid, pos)

            # 速率限制
            elapsed = time.time() - start_time
            sleep_time = (1.0 / config.LOOP_RATE) - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)

            # Check for generic input (Enter or 'q') to stop
            import sys, select
            if sys.stdin in select.select([sys.stdin], [], [], 0)[0]:
                line = sys.stdin.read(1)
                if line == 'q' or line == '\n':
                    print("\nKey press detected. Stopping...")
                    break
                elif line == 'c':
                    print("\n[User Request] Recalibrating...")
                    retargeter.trigger_calibration()
                elif line == 'r':
                    print("\n[User Request] Resetting Calibration...")
                    retargeter.reset_calibration()

    except KeyboardInterrupt:
        print("\nStopping (Ctrl+C)...")
    
    finally:
        print("\nCleaning up resources...")
        try:
            avp.stop_video_stream()
            camera_controller.close_camera()
            if hasattr(avp, "close"):
                avp.close()
            motors.enable_torque(config.YAW_MOTOR_ID, False)
            motors.enable_torque(config.PITCH_MOTOR_ID, False)
            motors.close()
        except Exception as e:
            print(f"Error during motor cleanup: {e}")
        print("Done.")

if __name__ == "__main__":
    run_app()
