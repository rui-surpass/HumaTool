
import sys
import os
import time
import cv2

# Ensure the project root is in sys.path
root_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(root_dir)

from config import config
from src.hardware.camera import CameraInterface, HAS_ZED_SDK

def test_camera():
    print("=== Testing ZED Camera ===")
    print(f"ZED SDK Available: {HAS_ZED_SDK}")
    print(f"Use ZED SDK Config: {config.USE_ZED_SDK}")
    print(f"Camera ID: {config.ZED_CAMERA_ID}")
    
    cam = CameraInterface(config.ZED_CAMERA_ID, config.STREAM_RESOLUTION, config.STREAM_FPS)
    
    if not cam.is_opened:
        print("Failed to open camera.")
        return

    print("\n--- 0. Camera Information ---")
    info = cam.get_device_info()
    for k, v in info.items():
        print(f"  {k}: {v}")

    print("\n--- 1. Testing Camera Controls ---")
    # Try setting some values
    cam.set_brightness(4) # SDK expects int range
    cam.set_exposure(50)
    time.sleep(1)

    print("\n--- 2. Grabbing Frames & IMU ---")
    print("Capturing 20 samples at 60Hz loop to test IMU update rate...")
    
    for i in range(20):
        # Read Frame
        ret, frame = cam.read()
        frame_status = "OK" if ret else "FAIL"
        frame_size = frame.shape if ret else 'None'
        
        # Read IMU
        imu = cam.get_imu_data()
        if imu:
            imu_str = f"Yaw={imu[0]:.2f}, Pitch={imu[1]:.2f}, Roll={imu[2]:.2f}"
            status = "[Fresh]"
        elif HAS_ZED_SDK and config.USE_ZED_SDK:
            imu_str = "No New Data"
            status = "[Stale]"
        else:
            imu_str = "N/A (OpenCV/No SDK)"
            status = "[-]"
            
        print(f"Sample {i+1:02d}: Video={frame_status} ({frame_size}) | IMU {status}: {imu_str}")
        
        # Simulate loop rate (e.g., 60Hz)
        time.sleep(1.0/60.0)

    print("\n--- 3. Closing ---")
    cam.close()
    print("=== Camera Test Complete ===")

if __name__ == "__main__":
    test_camera()
