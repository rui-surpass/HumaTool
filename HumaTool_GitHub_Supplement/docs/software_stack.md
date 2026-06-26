# Software Stack and Implementation Boundary

This document explains the implementation boundary of the public HumaTool repository.

## Self-developed Component

The main self-developed component is **RoboNeck-AVP**, a Python/PyQt6 program for head-neck teleoperation. It is responsible for:

- Apple Vision Pro session connection and head-pose input
- yaw/pitch pose retargeting
- zero calibration and EMA smoothing
- camera acquisition and visual feedback
- Dynamixel motor command generation
- runtime diagnostics and logging
- robot-side deployment checks

## Related Open-source / Official Resources

The complete project also relies on several external resources:

| Component | Role |
|---|---|
| ZED SDK | ZED Mini stereo camera acquisition and visual feedback |
| DynamixelSDK | head-neck motor communication and synchronized write |
| Unitree `xr_teleoperate` | dual-arm and Dex3-1 hand teleoperation workflow |
| VisionProTeleop-style workflow | Vision Pro tracking data and visual feedback design reference |
| NVIDIA GR00T / Isaac-GR00T | VLA backbone, fine-tuning workflow, and evaluation reference |
| Isaac Sim | simulation task setup and policy evaluation |

## Public Release Boundary

This repository does not claim to reimplement all upstream systems from scratch. Its contribution is the integration and task adaptation pipeline for humanoid tool grasping, especially:

1. RoboNeck-AVP active head-neck teleoperation.
2. Demonstration recording workflow for humanoid tool grasping.
3. Data processing format for visual observations, robot states, and expert actions.
4. GR00T-based VLA fine-tuning configuration for small-sample drill grasping.
5. Evaluation documentation and result analysis.
