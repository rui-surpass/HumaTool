import sys
import os
import time
import numpy as np

# Ensure root is in path
root_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(root_dir)

from config import config

try:
    from avp_stream import VisionProStreamer
except ImportError:
    print("Error: avp_stream not installed. Run 'pip install -e ../VisionProTeleop'")
    sys.exit(1)

def test_connection():
    ip = config.AVP_IP
    print(f"==========================================")
    print(f"Testing connection to Apple Vision Pro")
    print(f"Target IP: {ip}")
    print(f"==========================================")
    
    # 1. Ping Test
    print(f"[1/3] Pinging {ip}...")
    response = os.system(f"ping -c 1 -W 1 {ip} > /dev/null 2>&1")
    if response == 0:
        print(f"  -> PASS: {ip} is reachable.")
    else:
        print(f"  -> FAIL: {ip} is NOT reachable.")
        print("     Suggestions:")
        print("     - Check if AVP is connected to Wi-Fi.")
        print("     - Check if PC and AVP are on the same local network.")
        print("     - Verify IP address in config/config.py.")
        # We continue even if ping fails, as some networks block ICMP
    
    # 2. Initialize Streamer
    print(f"\n[2/3] Initializing VisionProStreamer...")
    try:
        streamer = VisionProStreamer(ip=ip, record=False)
        print("  -> PASS: Streamer object initialized.")
    except Exception as e:
        print(f"  -> FAIL: Streamer init failed: {e}")
        return

    # 3. Receive Data
    print(f"\n[3/3] Waiting for Head Pose data (Timeout: 10s)...")
    print("     Please ensure the 'AVP Stream' app is open and running on the device.")
    
    start_time = time.time()
    received = False
    
    try:
        while time.time() - start_time < 10:
            data = streamer.get_latest()
            if data and 'head' in data:
                head = data['head']
                print(f"  -> PASS: Received Head Pose data!")
                print(f"     Matrix Shape: {head.shape}")
                print(f"     Sample Data:\n{head}")
                received = True
                break
            time.sleep(0.1)
            print(".", end="", flush=True)
            
    except KeyboardInterrupt:
        print("\nAborted by user.")
    
    if not received:
        print(f"\n  -> FAIL: No data received within timeout.")
        print("     Suggestions:")
        print("     - Check if the AVP app is authorized to send data.")
        print("     - Restart the AVP app.")
    
    print("\nTest Complete.")

if __name__ == "__main__":
    test_connection()
