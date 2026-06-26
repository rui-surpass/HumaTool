# RoboNeck-AVP

RoboNeck-AVP is a Python desktop control project for driving a two-axis robot neck from Apple Vision Pro head motion. The repository combines AVP session handling, a PyQt6 operator UI, camera and motor adapters, and offline deployment tooling for the robot PC.

RoboNeck-AVP 是一个基于 Python 的机器人颈部控制项目，用 Apple Vision Pro 的头部姿态驱动双轴云台/颈部机构。仓库同时包含 AVP 会话管理、PyQt6 操作界面、相机与电机适配层，以及面向机器人端的离线部署工具。

## Highlights

- AVP head-pose retargeting and tracking start calibration
- PyQt6 operator interface for session, camera, and pose control
- Dynamixel motor and ZED camera integration layers
- Offline bundle build and robot environment validation scripts

## Repository Layout

- `src/core/`: runtime bootstrap, AVP session flow, calibration, path handling
- `src/gui/`: PyQt6 windows, dashboard, pose-control logic, stream UI
- `src/hardware/`: camera and motor adapters, mock motor support
- `src/utils/`: orientation, rotation, retargeting, motor math helpers
- `config/`: editable runtime defaults and saved connection / tracking pose records
- `tests/`: automated `pytest` coverage for core logic, UI state, and deployment helpers
- `tools/deployment/`: bundle build, restore, launch, and environment check scripts
- `tools/hardware_checks/`: manual operator checks for AVP, camera, and motor hardware

## Environment

- Python `3.10` is the supported baseline. The codebase uses Python 3.10 type-union syntax such as `tuple | None`.
- Recommended local environment name: `avp_teleop`
- Typical runtime dependencies include `PyQt6`, `opencv-python`, `pyzed`, `avp_stream`, and `dynamixel_sdk`

## Quick Start

```bash
python src/main.py
```

Run the automated suite:

```bash
pytest
```

Run a focused test while iterating:

```bash
pytest tests/test_pose_control_logic.py -v
```

Build an offline robot bundle:

```bash
python tools/deployment/build_robot_bundle.py
```

Check a robot-side environment:

```bash
python tools/deployment/check_robot_env.py
```

## Configuration

Public defaults in `config/config.py` are examples only. Before running on real hardware, update:

- `ROBO_NECK_AVP_IP` or `config.AVP_IP`
- `ROBO_NECK_DYNAMIXEL_PORT` or `config.DYNAMIXEL_PORT`
- camera settings, motion scaling, and mock-mode flags as needed

Saved connection and tracking-start records live in:

- `config/avp_connection.json`
- `config/tracking_start_pose.json`

## Testing And Hardware Checks

Use `pytest` for automated checks. Manual scripts under `tools/hardware_checks/` are intentionally excluded from the default suite because they require operator supervision and real hardware.

典型手工检查命令：

```bash
python tools/hardware_checks/check_avp.py
python tools/hardware_checks/check_camera.py
python tools/hardware_checks/check_motor.py
```

## Release Artifacts

This repository stores source code and tooling, not generated deployment archives. Keep `dist/` out of Git history. When you need to publish a validated bundle, generate it locally and upload the resulting archive to GitHub Releases instead of committing it to the repository.

本仓库只维护源码和脚本，不把 `dist/` 中的部署产物纳入 Git 历史。正式发布时，请本地打包后上传到 GitHub Releases。

## Maintenance Notes

- Use Conventional Commit subjects such as `feat:`, `fix:`, `docs:`, and `test:`
- Record verification commands in pull requests
- Include screenshots when `src/gui/` behavior changes
- Update `tools/deployment/README.md` or `tools/hardware_checks/README.md` when operational workflows change
