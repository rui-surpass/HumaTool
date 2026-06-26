# Tracking 长延时调试方案

## 目的

当 neck tracking 出现以下现象时，使用本手册进行定位和调参：

- 头动了，但电机先不动，过一段时间突然追上
- 电机始终慢半拍，持续偏肉
- 只在某些模式下出现，例如开视频流、切换 session、重连后

本手册默认采用“平衡响应与稳定”的调试策略：

- 先确认问题来源
- 再按最小步长调参数
- 不同时改多个关键参数，避免失去归因

## 先看哪里

优先观察两个位置：

1. `Pose Control -> Advanced`
2. 主控页 `AVP Details`

重点字段：

- `Pose Freshness`
- `Sample Age`
- `Control Loop`
- `Last Command Gap`
- `Last Command Target`
- `Stale Count`
- `Pose: Fresh/Not Fresh`
- `Reason`

当前这些字段来自运行时诊断：

- `Pose Freshness`、`Sample Age`、`Control Loop`、`Last Command Gap`、`Last Command Target`、`Stale Count`
  在 [src/gui/pose_control.py](/home/elwen/Projects/Robot/RoboNeck-AVP/RobotNeck-AVP_copy_0326/RobotNeck-AVP/src/gui/pose_control.py)
- 主控页 `AVP Details` 中的 pose 诊断摘要
  在 [src/gui/dashboard.py](/home/elwen/Projects/Robot/RoboNeck-AVP/RobotNeck-AVP_copy_0326/RobotNeck-AVP/src/gui/dashboard.py)

如需打开更细的时序日志，可在启动前设置：

- `ROBO_NECK_DEBUG_TIMING=1`
- `ROBO_NECK_DISABLE_CAMERA_DIAGNOSTICS=1`

建议用法：

- 先只开 `ROBO_NECK_DEBUG_TIMING=1`，观察 `avp_get_latest`、`main_window_update_loop`、`camera_read`、`pose_control_loop`、`motor_write`
- 如果怀疑主线程被相机诊断拖慢，再加 `ROBO_NECK_DISABLE_CAMERA_DIAGNOSTICS=1` 做 A/B 对比
- 如果希望自动保存现场样本并给出根因排序，再加 `ROBO_NECK_DIAG_CAPTURE=1`

推荐现场命令：

```bash
bash tools/hardware_checks/run_field_diagnostics.sh
```

如果需要手动分步执行：

```bash
ROBO_NECK_DEBUG_TIMING=1 ROBO_NECK_DIAG_CAPTURE=1 bash tools/deployment/run_robot_gui.sh
python tools/hardware_checks/diagnose_tracking_latency.py
```

诊断结果会从 `./diagnostics/<timestamp>/events.jsonl` 生成：

- `summary.json`
- `summary.txt`

## 现象分类与判断

### 1. 先不动，随后突然追上

最优先怀疑 AVP pose 输入链路，而不是电机本体。

如果同时看到以下现象，基本可判定是上游样本停顿：

- `Pose Freshness = Not Fresh`
- `Reason = stale_sample` 或 `sample_missing`
- `Sample Age` 明显升高
- `Stale Count` 持续增加
- `Last Command Gap` 也变大

这类问题先查：

- Vision Pro 端 pose 推流是否稳定
- 当前 session 是否刚切换
- 网络是否存在短时卡顿
- 是否在 stream/tracking 切换时出现

### 2. 一直慢半拍，持续偏肉

如果同时满足：

- `Pose Freshness = Fresh`
- `Sample Age` 持续很低
- `Control Loop` 接近目标频率
- `Last Command Gap` 正常

但动作一直偏钝，那么优先怀疑：

- `SMOOTHING_ALPHA` 偏小
- 电机 `Profile Acceleration` 偏保守

### 3. 只在特定模式出现

例如只在以下情况下出现：

- 开启 VisionPro stream 后
- 从 `tracking_only` 切到 `streaming`
- AVP 重连后

这类问题优先记录：

- 当前 session mode
- `Pose Freshness`
- `Reason`
- 是否发生过重连
- 问题是在开始 tracking 前还是 tracking 过程中出现

## 当前项目里真正影响流畅性的项

### AVP pose freshness

这是当前最优先的流畅性判断项。

如果上游 pose 断续，即使电机控制没问题，也会表现成：

- 电机保持旧目标
- 新样本回来后突然追一下

### 控制环频率

当前 `LOOP_RATE = 60`：

```python
LOOP_RATE = 60
```

位置：

- [config/config.py](/home/elwen/Projects/Robot/RoboNeck-AVP/RobotNeck-AVP_copy_0326/RobotNeck-AVP/config/config.py)

正常情况下不建议优先改它。先确认实际 `Control Loop` 是否真的跑不到 60 Hz。

### 平滑参数

当前 `SMOOTHING_ALPHA = 0.4`：

```python
SMOOTHING_ALPHA = 0.4
```

位置：

- [config/config.py](/home/elwen/Projects/Robot/RoboNeck-AVP/RobotNeck-AVP_copy_0326/RobotNeck-AVP/config/config.py)

在 retargeting 中对 target 做 EMA：

- [src/utils/retargeting.py](/home/elwen/Projects/Robot/RoboNeck-AVP/RobotNeck-AVP_copy_0326/RobotNeck-AVP/src/utils/retargeting.py)

影响规律：

- 更小：更稳，但更慢
- 更大：更快，但更容易抖

### 电机 Profile

电机连接后的默认 profile：

- `velocity = 0`
- `acceleration = 20`

位置：

- [src/gui/dynamixel_debug.py](/home/elwen/Projects/Robot/RoboNeck-AVP/RobotNeck-AVP_copy_0326/RobotNeck-AVP/src/gui/dynamixel_debug.py)

手动调参时使用：

- `acceleration = 50`

对体感影响很直接：

- acceleration 太小：明显肉
- acceleration 太大：更冲、更容易机械抖动

### 电机下发方式

当前目标位置是 `GroupSyncWrite`，不是逐个单发：

- [src/hardware/motor.py](/home/elwen/Projects/Robot/RoboNeck-AVP/RobotNeck-AVP_copy_0326/RobotNeck-AVP/src/hardware/motor.py)

所以软件层“发送方式太慢”通常不是首要嫌疑。

## 推荐调试顺序

### Step 1. 先判定是不是 AVP 输入停顿

复现问题时记录：

- `Pose Freshness`
- `Reason`
- `Sample Age`
- `Stale Count`
- `Last Command Gap`

如果这些指标异常，先不要动 smoothing 或电机 profile。

### Step 2. 再看控制环是否正常

观察：

- `Control Loop`
- `Last Command Gap`
- 自动报告中的 `top_cause`
- 自动报告中的 `camera.frame_age_ms`
- 自动报告中的 `timing.update_loop / timing.control_loop / timing.camera_read`

如果 `Control Loop` 明显偏低，再查：

- GUI 主线程负载
- 相机读取是否阻塞
- 是否同时开了高负载预览或 streaming

### Step 3. 只有在 pose fresh 且 loop 正常时，再开始调参数

先调一个参数，测试，再决定下一步。

不要同时改：

- `SMOOTHING_ALPHA`
- `Profile Acceleration`
- PID

## 平衡型调参建议

默认目标：

- 响应更快一点
- 不明显增加抖动和冲击

### A. 先调 `SMOOTHING_ALPHA`

当前值：

- `0.4`

建议测试顺序：

1. `0.4 -> 0.5`
2. 如果仍明显偏肉，再试 `0.6`

预期：

- `0.5`：响应更快，通常风险较低
- `0.6`：进一步提速，但更容易放大头部细碎抖动

不建议一上来改到：

- `0.8`
- `1.0`

这类值在实际硬件上更容易让动作变得“硬”。

### B. 再调 `Profile Acceleration`

默认连接值：

- `20`

平衡型建议顺序：

1. `20 -> 30`
2. `30 -> 40`
3. 如果机械状态稳定，再考虑 `50`

预期：

- 更高 acceleration 会减少“起步迟疑”
- 但太高会增加冲击感、抖动和机械负担

如果是“先停住后突然追”，不要优先动这个值。

### C. `Profile Velocity`

当前默认是：

- `0`

一般不作为第一优先级。先看 acceleration 和 smoothing。

## 什么时候不要调参数

出现以下任一情况时，先停下，不调参：

- `Pose Freshness = Not Fresh`
- `Reason = stale_sample`
- `Sample Age` 明显升高
- `Stale Count` 连续增长
- 问题只在 session 切换时出现

这些更像输入链问题，不是控制参数问题。

## 调试记录模板

每次只改一个参数，并记录：

```markdown
## 调试记录

- 时间：
- 模式：
  - tracking_only / streaming
- 现象：
  - 先不动后追上 / 持续慢半拍 / 其他
- 诊断值：
  - Pose Freshness:
  - Reason:
  - Sample Age:
  - Control Loop:
  - Last Command Gap:
  - Stale Count:
- 本次改动：
  - 例如 `SMOOTHING_ALPHA: 0.4 -> 0.5`
- 结果：
  - 更快 / 无明显变化 / 出现抖动
- 结论：
  - 保留 / 回退 / 继续下一档
```

## 建议的最小实验集

按这个顺序做，最容易保留归因：

1. 原始参数，记录一次基线
2. `SMOOTHING_ALPHA: 0.4 -> 0.5`
3. 若需要，回到 `0.4`，再单独测 `Profile Acceleration: 20 -> 30`
4. 若需要，再组合测试 `0.5 + 30`

不要一开始就同时改三项以上。

## 当前结论

如果最近测试中已经没有出现长延时，说明当前工况下：

- AVP pose 流可能较稳定
- 控制环也基本正常

这不等于控制参数已经最优，而是说明：

- 现阶段先保留当前参数
- 后续出现问题时，优先用本手册定位来源
- 只有在证据明确指向参数问题时，再做小步调参
