
import sys
import os
import time

# Ensure the project root is in sys.path
root_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(root_dir)

from config import config
from src.hardware.motor import MotorController

def test_motor():
    print("=== Testing Dynamixel Motors ===")
    print(f"Port: {config.DYNAMIXEL_PORT}, Baud: {config.BAUDRATE}")
    
    try:
        motors = MotorController(config.DYNAMIXEL_PORT, config.BAUDRATE)
    except Exception as e:
        print(f"Failed to initialize motors: {e}")
        return

    if not motors.connected:
        print("Failed to connect to Dynamixel port.")
        return

    ids = [config.YAW_MOTOR_ID, config.PITCH_MOTOR_ID]
    connected_ids = []

    print("\n--- 0. Pinging Motors ---")
    for mid in ids:
        model = motors.ping(mid)
        if model:
            print(f"ID {mid}: Connected (Model {model})")
            connected_ids.append(mid)
            
            # Check Operating Mode (must be done with Torque Disabled)
            motors.enable_torque(mid, False)
            current_mode = motors.get_operating_mode(mid)
            print(f"ID {mid}: Current Mode = {current_mode}")
            
            if current_mode != 3: # 3 = Position Control Mode
                print(f"ID {mid}: Switching to Position Control Mode (3)...")
                motors.set_operating_mode(mid, 3)
        else:
            print(f"ID {mid}: Not found!")
    
    if not connected_ids:
        print("No motors found. Check connections or run 'python tools/hardware_checks/scan_motors.py'.")
        motors.close()
        return

    print("\n--- 1. Testing Torque Enable ---")
    for mid in connected_ids:
        motors.enable_torque(mid, True)
    time.sleep(1)

    print("\n--- 2. Reading Initial Status ---")
    for mid in connected_ids:
        status = motors.read_status(mid)
        # Read position
        pos = motors.get_present_position(mid)
        if status:
            print(f"ID {mid}: Voltage={status['voltage']}V, Temp={status['temperature']}C, Pos={pos}")
        else:
            print(f"ID {mid}: Failed to read status")

    print("\n--- 3. Testing Motion (Center -> Offset -> Center) ---")
    
    # Configure Profile for smooth motion
    vel = 200
    acc = 200
    print(f"Setting Profile: Vel={vel}, Acc={acc}")
    for mid in connected_ids:
        motors.set_profile(mid, vel, acc)

    # Move to zero (Center)
    print("Moving to Zero...")
    motors.set_goal_positions({id: config.ZERO_POS for id in connected_ids})
    time.sleep(2)
    for mid in connected_ids:
        print(f"ID {mid} Pos: {motors.get_present_position(mid)}")

    # Move to some offset
    print(f"Moving to +90 degrees (Target ~{config.ZERO_POS + 341})...")
    offset_steps = int(90 * (config.STEPS_PER_REV / 360.0))
    target_pos = config.ZERO_POS + offset_steps
    motors.set_goal_positions({id: target_pos for id in connected_ids})
    
    # Check status during motion
    for i in range(20):
        time.sleep(0.1)
        # Optional: could print position here to show trajectory
    
    for mid in connected_ids:
        print(f"ID {mid} Pos: {motors.get_present_position(mid)}")
    
    time.sleep(1) # wait to settle

    print("Moving back to Zero...")
    motors.set_goal_positions({id: config.ZERO_POS for id in connected_ids})
    time.sleep(2)
    for mid in connected_ids:
        print(f"ID {mid} Pos: {motors.get_present_position(mid)}")

    print("\n--- 4. Disable Torque & Close ---")
    for mid in connected_ids:
        motors.enable_torque(mid, False)
    motors.close()
    print("=== Motor Test Complete ===")

if __name__ == "__main__":
    test_motor()
