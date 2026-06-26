
import glob
import os

def scan_cameras():
    print("=== Video Device Scanner ===")
    
    # List /dev/video*
    devices = sorted(glob.glob("/dev/video*"))
    
    if not devices:
        print("No video devices found in /dev/video*")
        return

    print(f"Found {len(devices)} devices:")
    
    found_zed = False
    
    for dev in devices:
        # Get index number
        try:
            idx = int(dev.replace("/dev/video", ""))
        except ValueError:
            continue
            
        # Try to read name from sysfs
        name_path = f"/sys/class/video4linux/video{idx}/name"
        camera_name = "Unknown"
        if os.path.exists(name_path):
            try:
                with open(name_path, 'r') as f:
                    camera_name = f.read().strip()
            except:
                pass
        
        print(f"  {dev} (ID {idx}): {camera_name}")
        
        if "ZED" in camera_name:
            found_zed = True

    print("\n--- Configuration Hint ---")
    if found_zed:
        print("ZED Camera detected!")
        print("For ZED SDK usage (ZED_CAMERA_ID), typically key '0' selects the first ZED camera, regardless of /dev/video index.")
        print("If you have multiple ZEDs, '1' selects the second one, etc.")
    else:
        print("No ZED camera name detected via sysfs. Check USB connection.")

if __name__ == "__main__":
    scan_cameras()
