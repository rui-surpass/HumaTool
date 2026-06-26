# Run RoboNeck-AVP Pose Retargeting

This example only runs the hardware-independent pose-retargeting smoke test.

```bash
python src/robo_neck_avp/pose_retargeting.py
```

Expected output:

```text
{'yaw_step': 2048, 'pitch_step': 2048}
```

To control real hardware, connect `NeckMotorClient` in `src/robo_neck_avp/motor_control.py` to your approved motor SDK and keep hardware credentials out of Git.
