# Robot PC2 启动清单

这份清单面向将 `RobotNeck-AVP` 部署到宇树机器人 PC2 的现场操作。

适用前提：

- 机器人服务器地址为 `unitree@192.168.123.164`
- 部署目录为 `/home/unitree/robotneck`
- 用户电脑通过网线和转接线接入 G1 交换机
- 用户电脑与机器人通信的网卡配置在 `192.168.123.161/24` 网段
- 已在开发机生成离线包 `dist/robot_deploy.tar.gz`

## 1. 开发机打包

在开发机执行：

注意：

- 优先一行一条命令执行，不要复制终端里已经自动换行的长命令
- 如果需要整体复制，请从本文档的代码块复制，不要从聊天记录或终端回显里复制
- `scp`、`grep` 和长路径命令尤其不要手动插入回车

```bash
cd /home/elwen/Projects/Robot/RoboNeck-AVP/RobotNeck-AVP_copy_0326/RobotNeck-AVP
source ~/anaconda3/etc/profile.d/conda.sh
conda activate avp_teleop
python -m pip install -U conda-pack
python tools/deployment/build_robot_bundle.py
```

如果需要故意生成仅包含 fallback 环境文件的调试包，才使用：

```bash
python tools/deployment/build_robot_bundle.py --allow-missing-packed-env
```

确认以下文件存在：

- `dist/robot_deploy.tar.gz`
- `dist/robot_deploy/env/avp_teleop.tar.gz`
- `dist/robot_deploy/deploy_manifest.json`
- `dist/robot_deploy/tools/deployment/restore_robot_env.sh`

推荐直接执行下面三条校验命令，不要手动改行：

```bash
tar -tzf dist/robot_deploy.tar.gz | grep '^robot_deploy/tools/deployment/restore_robot_env.sh$'
tar -tzf dist/robot_deploy.tar.gz | grep '^robot_deploy/tools/deployment/run_robot_gui.sh$'
tar -tzf dist/robot_deploy.tar.gz | grep '^robot_deploy/env/avp_teleop.tar.gz$'
```

如需查看打包机器架构，可执行：

```bash
python - <<'PY'
import json
with open('dist/robot_deploy/deploy_manifest.json', 'r', encoding='utf-8') as f:
    print(json.load(f)['build_machine'])
PY
```

## 2. 用户电脑网络检查

确认用户电脑和机器人在同一网段：

```bash
ip addr
ping 192.168.123.164
```

要求：

- 连接机器人交换机的网卡地址位于 `192.168.123.161/24`
- 能 `ping` 通 `192.168.123.164`

如果无法连通，先处理网络，不要继续部署。

## 3. 传输到机器人 PC2

从开发机或当前操作电脑传输离线包：

```bash
scp dist/robot_deploy.tar.gz unitree@192.168.123.164:/home/unitree/robotneck/
```

如果离线包不是在当前目录，可直接传绝对路径：

```bash
scp /home/elwen/Projects/Robot/RoboNeck-AVP/RobotNeck-AVP_copy_0326/RobotNeck-AVP/dist/robot_deploy.tar.gz unitree@192.168.123.164:/home/unitree/robotneck/
```

不要把上面的 `scp` 命令拆成两行。特别是 `:/home/unitree/robotneck/` 这一段必须保持完整。

## 4. 登录机器人并解压

登录机器人：

```bash
ssh unitree@192.168.123.164
```

进入部署目录并解压：

```bash
cd /home/unitree/robotneck
rm -rf robot_deploy
tar -xzf robot_deploy.tar.gz
cd /home/unitree/robotneck/robot_deploy
```
## 5. 恢复 Python 运行环境

优先使用离线环境包恢复：

```bash
ls tools/deployment/restore_robot_env.sh
ls tools/deployment/run_robot_gui.sh
ls env/avp_teleop.tar.gz
bash tools/deployment/restore_robot_env.sh
```

如果脚本报 `Packed environment architecture mismatch`，说明离线环境包与机器人 CPU 架构不一致。
此时不要继续 restore 或 clone 这个打包环境，应在机器人本机重新创建原生 `avp_teleop` 环境。

恢复完成后，环境默认位于：

```bash
/home/unitree/robotneck/robot_deploy/env/avp_teleop
```

如果你希望在机器人端直接使用：

```bash
conda activate avp_teleop
```

则继续执行：

```bash
bash tools/deployment/create_robot_conda_env.sh
conda activate avp_teleop
```

这个步骤会自动选择两种方式之一：

- 架构一致时，克隆 bundle 内恢复环境到机器人 Conda
- 架构不一致时，在机器人本机原生创建 `avp_teleop`

如果机器人已经能联网，推荐直接使用下面这条命令强制重建本机原生环境：

```bash
bash tools/deployment/create_robot_conda_env.sh avp_teleop avp_teleop --force
```

然后激活：

```bash
source /home/unitree/miniconda3/etc/profile.d/conda.sh
conda activate avp_teleop
```

如果恢复失败，检查：

- `env/avp_teleop.tar.gz` 是否存在
- 机器人磁盘空间是否足够
- 当前目录是否为 `/home/unitree/robotneck/robot_deploy`
- 如果你是通过 `robotneck_app/tools/deployment/...` 调用脚本，改为优先使用 bundle 根目录下的 `tools/deployment/...`

## 6. 系统前置检查

运行环境检查脚本：

```bash
./env/avp_teleop/bin/python tools/deployment/check_robot_env.py
```

如果你已经执行了 `create_robot_conda_env.sh` 并 `conda activate avp_teleop`，也可以使用：

```bash
python tools/deployment/check_robot_env.py
```

如需结构化输出：

```bash
python tools/deployment/check_robot_env.py --format json
```

重点检查以下项目：

- `conda`
- `python`
- `PyQt6`
- `cv2`
- `pyzed.sl`
- `avp_stream`
- `dynamixel_sdk`
- `libsl_zed`
- `tty_usb0`

如果 `avp_stream` 依赖仍未装齐，而机器人此时已经可以联网，可在激活后的
`avp_teleop` 环境中执行：

```bash
python -m pip install -U grpcio aiortc av requests pyyaml tqdm pydub websocket-client gdown flask protobuf
```

说明：

- 不需要安装 `grpcio-tools`，运行时不依赖它
- `dynamixel_sdk` 的 Python 代码已随部署包提供，不需要额外在线安装 SDK

## 7. 必须满足的硬件与系统条件

在启动 GUI 之前，必须确认：

- 机器人 PC2 已安装 NVIDIA 驱动
- 机器人 PC2 已安装 ZED SDK
- `/usr/local/zed/lib/libsl_zed.so` 存在
- ZED 相机已接入并被机器人识别
- 电机串口设备存在，通常为 `/dev/ttyUSB0`
- 当前用户对串口设备有访问权限

可手动检查：

```bash
ls /usr/local/zed/lib/libsl_zed.so
ls /dev/ttyUSB*
```

如果机器人已经联网，ZED SDK 请直接按 Stereolabs 官方 Jetson / `aarch64` 安装包安装，
并确保版本与当前 JetPack / L4T 匹配。安装完成后再执行：

```bash
python -c "import pyzed.sl as sl; print(sl)"
python tools/deployment/check_robot_env.py
```

## 8. 启动项目

在机器人 PC2 上启动 GUI：

```bash
bash tools/deployment/run_robot_gui.sh
```

该脚本会优先使用本地恢复环境：

- `/home/unitree/robotneck/robot_deploy/env/avp_teleop`

如果本地恢复环境架构不匹配或自检失败，则回退到系统中的 Conda 环境 `avp_teleop`。

对当前这类 `aarch64` 机器人 + `x86_64` 开发机构建包的组合，推荐正式流程是：

```bash
bash tools/deployment/create_robot_conda_env.sh
conda activate avp_teleop
python tools/deployment/check_robot_env.py
bash tools/deployment/run_robot_gui.sh
```

## 9. 启动后的现场检查

进入 GUI 后，按下面顺序检查：

1. 主界面是否正常显示，没有导入错误或 Qt 报错
2. Camera 页面是否能识别 ZED 相机
3. Motor 页面是否能识别 `/dev/ttyUSB0` 对应电机
4. AVP 面板参数是否正确
5. 不启动视频流时，先测试 AVP 连接和 tracking
6. 再测试视频流启动、停止与恢复

## 10. 常见问题

### `pyzed.sl` 导入失败

通常表示：

- 未安装 ZED SDK
- ZED SDK 版本与 Python 环境不匹配
- `/usr/local/zed/lib/libsl_zed.so` 缺失

### `dynamixel_sdk` 导入失败

通常表示：

- 未从离线包目录启动
- `PYTHONPATH` 未带上 `vendor/DynamixelSDK-main/python/src`
- 恢复环境未成功

### 找不到 `avp_stream`

通常表示：

- 未从离线包目录启动
- `vendor/visionproteleop` 未正确随包解压

### 电机连接失败

优先检查：

- `/dev/ttyUSB0` 是否存在
- USB 线和串口转接器是否插好
- 当前用户是否有串口权限

### 相机连接失败

优先检查：

- ZED 相机 USB 连接
- ZED SDK 安装状态
- `python tools/deployment/check_robot_env.py` 中 `pyzed.sl` 和 `libsl_zed` 项
