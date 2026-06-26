# Robot Deployment

This directory contains the offline deployment helpers for moving the project to the robot PC2.

For the operator-facing Chinese checklist, see `tools/deployment/robot_pc2_startup_checklist.md`.

## Build On The Development Machine

Use the current `avp_teleop` environment to build the bundle:

Copy commands from this document, not from wrapped terminal output. Long commands such as `scp`
and `grep '^...$'` must stay on one line.

```bash
source ~/anaconda3/etc/profile.d/conda.sh
conda activate avp_teleop
python -m pip install -U conda-pack
python tools/deployment/build_robot_bundle.py
```

The output is written to `dist/robot_deploy/` and packed as `dist/robot_deploy.tar.gz`.
The builder now requires a packed `env/avp_teleop.tar.gz` by default and fails fast if `conda-pack`
is unavailable. If you intentionally want a fallback-only bundle for debugging, use:

```bash
python tools/deployment/build_robot_bundle.py --allow-missing-packed-env
```

The bundle includes:

- `robotneck_app/` with the project source
- `robotneck_app/vendor/visionproteleop/`
- `robotneck_app/vendor/DynamixelSDK-main/`
- `env/` with environment snapshots and a required `conda-pack` archive unless you opted into a fallback-only bundle
- `deploy_manifest.json`
- `tools/deployment/` entrypoints at the bundle root for restore, Conda env creation, checks, and GUI launch

Verify the packed archive before copying it to the robot:

```bash
tar -tzf dist/robot_deploy.tar.gz | grep '^robot_deploy/tools/deployment/restore_robot_env.sh$'
tar -tzf dist/robot_deploy.tar.gz | grep '^robot_deploy/tools/deployment/run_robot_gui.sh$'
tar -tzf dist/robot_deploy.tar.gz | grep '^robot_deploy/env/avp_teleop.tar.gz$'
```

The bundle metadata records the build machine architecture. `restore_robot_env.sh` refuses to
restore a packed environment when the bundle architecture does not match the robot architecture.

## Transfer To The Robot

Copy the archive to the robot PC2, for example:

```bash
scp dist/robot_deploy.tar.gz unitree@192.168.123.164:/home/unitree/robotneck/
```

Then unpack on the robot:

```bash
cd /home/unitree/robotneck
rm -rf robot_deploy
tar -xzf robot_deploy.tar.gz
```

## Restore And Check

Restore the packed environment:

```bash
cd /home/unitree/robotneck/robot_deploy
ls tools/deployment/restore_robot_env.sh
ls tools/deployment/run_robot_gui.sh
ls env/avp_teleop.tar.gz
bash tools/deployment/restore_robot_env.sh
```

If you want a named Conda environment on the robot so that `conda activate avp_teleop`
works directly, use:

```bash
bash tools/deployment/create_robot_conda_env.sh
conda activate avp_teleop
```

This step is optional for `run_robot_gui.sh`, but useful when you want to run checks and tools
manually with the robot's Conda activation workflow. The script automatically chooses between:

- cloning the restored bundle-local environment when the architecture matches
- creating a native robot Conda environment when the bundle architecture does not match the robot

Run the robot environment check:

```bash
python tools/deployment/check_robot_env.py
```

Use JSON output when you want a machine-readable report:

```bash
python tools/deployment/check_robot_env.py --format json
```

## Run The GUI

Start the project with:

```bash
bash tools/deployment/run_robot_gui.sh
```

The launcher prefers the bundle-local environment under `env/avp_teleop/` only when it passes a
basic Python self-check and matches the robot architecture. Otherwise it falls back to activating a
Conda environment named `avp_teleop`.

On `aarch64` robots receiving bundles built on `x86_64` development machines, the recommended flow
is:

```bash
bash tools/deployment/create_robot_conda_env.sh
conda activate avp_teleop
python tools/deployment/check_robot_env.py
bash tools/deployment/run_robot_gui.sh
```

## Online Repair On The Robot

If the robot can access the internet, prefer recreating the Conda environment from the latest
bundle and then installing missing runtime dependencies online.

Recreate the robot-native Conda environment from the unpacked bundle:

```bash
cd /home/unitree/robotneck/robot_deploy
bash tools/deployment/create_robot_conda_env.sh avp_teleop avp_teleop --force
source /home/unitree/miniconda3/etc/profile.d/conda.sh
conda activate avp_teleop
```

The native environment script already installs the runtime Python packages needed by the bundled
`avp_stream` vendor tree:

- `grpcio`
- `aiortc`
- `av`
- `requests`
- `pyyaml`
- `tqdm`
- `pydub`
- `websocket-client`
- `gdown`
- `flask`
- `protobuf`

If you need to repair them manually inside the activated environment, use this single-line command:

```bash
python -m pip install -U grpcio aiortc av requests pyyaml tqdm pydub websocket-client gdown flask protobuf
```

`grpcio-tools` is intentionally not installed on the robot because it is not required at runtime.
The generated protobuf code is already bundled with the project.

The Python side of `dynamixel_sdk` is already shipped under
`robotneck_app/vendor/DynamixelSDK-main/python/src`, so there is no separate online SDK install
step for the project runtime. The remaining Dynamixel requirements are hardware-side:

- the USB serial adapter must appear as `/dev/ttyUSB0`
- the current user must have permission to open the serial port

For ZED support on the robot, install the official Stereolabs Jetson / `aarch64` SDK that matches
the robot's JetPack / L4T release. After the SDK install, verify:

```bash
ls /usr/local/zed/lib/libsl_zed.so
python -c "import pyzed.sl as sl; print(sl)"
python tools/deployment/check_robot_env.py
```

## Important Notes

- `pyzed.sl` still depends on the system ZED SDK and `/usr/local/zed/lib/libsl_zed.so`.
- NVIDIA driver, CUDA-capable runtime, and ZED SDK must exist on the robot PC2.
- Dynamixel access still depends on `/dev/ttyUSB0` and serial permissions.
- Fallback-only bundles are for debugging only. They are created only when you pass `--allow-missing-packed-env` and contain:
  - `env/conda-explicit.txt`
  - `env/pip-freeze.txt`
  - `env/environment.yml`
