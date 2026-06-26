


"""
RoboNeck-AVP 配置文件。

包含 AVP 连接、视频流设置、电机配置以及控制参数。
公开仓库中的默认值应保持为可共享的示例值。
"""

import os


def get_bool_env(name, default):
    val = os.getenv(name, str(default))
    return val.lower() in ("true", "1", "t")


# AVP 配置
AVP_IP = os.getenv("ROBO_NECK_AVP_IP", "192.168.0.10")

# 视频流配置 (ZED Mini 摄像头)
ENABLE_VIDEO = True         # 是否启用视频流功能
ZED_CAMERA_ID = 0           # ZED UVC 摄像头的设备 ID (尝试更换为f 1)
STREAM_RESOLUTION = "3840x1080"  # 视频分辨率 (Default Stereo 1080p)
STREAM_FPS = 30             # 视频帧率 (Hz)
USE_DUMMY_VIDEO_IF_NO_CAMERA = False # 如果未找到摄像头，是否启用虚拟测试图案

# ZED SDK 配置
USE_ZED_SDK = True          # 设置为 True 以使用 ZED SDK (获取 IMU 数据)
ZED_RESOLUTION = "HD1080"    # ZED SDK 分辨率: HD720 (60fps), HD1080 (30fps), HD2K (15fps)

# Dynamixel 电机配置
# 使用 `ls /dev/ttyUSB*` 检查您的设备端口
DYNAMIXEL_PORT = os.getenv("ROBO_NECK_DYNAMIXEL_PORT", "/dev/ttyUSB0")
BAUDRATE = 57600              # 波特率 (wizard软件检查电机设置)
PROTOCOL_VERSION = 2.0          # Dynamixel 协议版本 (X 系列通常为 2.0)

# 电机 ID
YAW_MOTOR_ID = 1    # 偏航轴 (Yaw) 电机 ID
PITCH_MOTOR_ID = 2  # 俯仰轴 (Pitch) 电机 ID

# 控制参数
# 缩放因子：1.0 表示头部角度到电机角度的 1:1 映射
# 增大 > 1.0 会放大动作，减小 < 1.0 会缩小动作
YAW_SCALE = 2 
PITCH_SCALE = 1.5

# 角度限制（单位：度）
# Dynamixel 使用 0-4096 的步进值，此处以度为单位设置软限位
# 假设 0 度为中心位置 (对应电机步进 2048)

YAW_LIMIT_DEG = [-180, 180]     # 偏航角限制范围
PITCH_LIMIT_DEG = [-180, 180]   # 俯仰角限制范围

# 循环频率
LOOP_RATE = 120 # 主控制循环频率 (Hz) - Increased to 60Hz for smoother tracking

# 平滑参数 (Exponential Moving Average)
# Alpha (0.0 - 1.0): 较小的值 = 更强的平滑 (更多的延迟); 较大的值 = 更快的响应
SMOOTHING_ALPHA = 1.0

# 是否启用底座 IMU 补偿
# 默认关闭，只有明确需要抵消底座姿态时再打开
ENABLE_IMU_COMPENSATION = False

# 初始化校准配置
ENABLE_INIT_CALIBRATION = True          # 是否在启动时执行初始化校准
INITIAL_POSE = {"yaw": 0.0, "pitch": 0.0} # 初始化姿态 (度)

# 模拟模式 (Mock Mode)
MOCK_AVP = get_bool_env("MOCK_AVP", False)     # 设置为 True 以模拟 AVP 数据 (测试用)
MOCK_MOTORS = get_bool_env("MOCK_MOTORS", False)  # 设置为 True 以在未连接电机的情况下运行 (测试用)

# 电机规格 (Dynamixel X-series)
STEPS_PER_REV = 4096 # 每转步进数 (分辨率)
ZERO_POS = 2048      # 零位位置 (中心点)
