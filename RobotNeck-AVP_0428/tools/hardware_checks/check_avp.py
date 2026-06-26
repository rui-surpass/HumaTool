
import sys
import os
import time

# Ensure the project root is in sys.path
root_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(root_dir)

from config import config
try:
    from avp_stream.streamer import VisionProStreamer
    HAS_AVP_STREAM = True
except ImportError:
    HAS_AVP_STREAM = False

import logging
logging.basicConfig(level=logging.DEBUG)


def test_avp():
    print("=== Testing AVP Connectivity ===")
    print(f"IP Address: {config.AVP_IP}")
    print(f"Config IP repr: {repr(config.AVP_IP)}")
    print(f"avp_stream installed: {HAS_AVP_STREAM}")
    
    if not HAS_AVP_STREAM:
        print("ERROR: avp_stream package not found. Cannot connect to AVP.")
        return

    print("\n--- 1. Initializing Streamer ---")
    try:
        # Enable verbose logging to see connection attempts
        # MATCHING WORKING EXAMPLE: Enable recording (default in 03_visualize...)
        streamer = VisionProStreamer(ip=config.AVP_IP, record=True, verbose=False)
        print("Streamer initialized.")
    except Exception as e:
        print(f"Failed to initialize streamer: {e}")
        return

    print("\n--- 2. Waiting for Data (Head Pose) ---")
    print("Please ensure the AVP app is running and connected.")
    
    for i in range(20):
        data = streamer.get_latest()
        if data and 'head' in data:
            print(f"[{i+1}] Received Head Pose Data!")
            # Print simplified matrix or position
            # print(data['head'])
            break
        else:
            print(f"[{i+1}] Waiting for data...")
        time.sleep(0.5)
        
    print("=== AVP Test Complete ===")

if __name__ == "__main__":
    test_avp()
