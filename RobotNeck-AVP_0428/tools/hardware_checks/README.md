# Hardware Checks

This directory contains manual hardware validation scripts.

These scripts are not part of the default automated `pytest` suite. Run them
manually when you have the required hardware and dependencies available.

Typical commands:

```bash
bash tools/hardware_checks/run_field_diagnostics.sh
python tools/hardware_checks/check_avp.py
python tools/hardware_checks/check_avp_connection.py
python tools/hardware_checks/check_camera.py
python tools/hardware_checks/check_motor.py
python tools/hardware_checks/scan_cameras.py
python tools/hardware_checks/scan_motors.py
python tools/hardware_checks/diagnose_tracking_latency.py
```

Additional operator docs:

- `tools/hardware_checks/debug-tracking-latency.md` for diagnosing tracking delay, stale AVP pose input, and safe tuning order

For field diagnosis, prefer the wrapper script:

```bash
bash tools/hardware_checks/run_field_diagnostics.sh
```

This launches the GUI with timing capture enabled, stores samples under `./diagnostics/<timestamp>/`, and runs the latency analyzer automatically after the GUI exits.

Manual capture + analysis is still available:

```bash
ROBO_NECK_DEBUG_TIMING=1 ROBO_NECK_DIAG_CAPTURE=1 bash tools/deployment/run_robot_gui.sh
python tools/hardware_checks/diagnose_tracking_latency.py
```

This writes raw samples under `./diagnostics/<timestamp>/` and generates `summary.json` plus `summary.txt`.

Prerequisites depend on the script:

- Apple Vision Pro connectivity and the `avp_stream` package
- ZED camera and optional `cv2` / ZED SDK support
- Dynamixel motors connected on the configured serial port

Use these scripts for operator-led bring-up and device debugging, not CI.
