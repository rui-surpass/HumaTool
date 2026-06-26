# HumaTool Project Report

## 1. Research Context

Humanoid robots are increasingly expected to perform tool-based operations in construction and industrial environments. However, direct deployment remains challenging because fine-grained tool manipulation requires integrated perception, embodiment-specific control, and task-oriented policy adaptation.

HumaTool takes electric drill grasping as an entry task for smart construction. The project builds a teleoperation-to-learning workflow that connects expert demonstration collection with VLA policy adaptation.

## 2. Research Gaps

The project addresses three practical gaps:

1. **System integration gap:** integrated head-neck stereo teleoperation systems still require stable implementation and validation.
2. **Task adaptation gap:** VLA adaptation for fine-grained tool manipulation under limited demonstrations remains difficult.
3. **Workflow validation gap:** the continuous chain from teleoperated demonstration to autonomous policy transfer is still underexplored.

## 3. Teleoperation System

The teleoperation system uses Apple Vision Pro for operator-side head, wrist, and hand input. On the robot side, the Unitree G1 arms, three-finger dexterous hand, and active head-neck stereo module execute teleoperated actions.

The active visual module consists of a 2-DoF neck mechanism and a ZED Mini stereo camera. The self-developed RoboNeck-AVP program maps AVP head poses to robot yaw/pitch targets and provides camera configuration, pose tracking, motor debugging, and runtime diagnostics.

## 4. Demonstration Dataset

The demonstration dataset contains about 30 high-quality trajectories. Each trajectory includes:

- visual observations
- robot states
- end-effector poses
- hand states
- operator commands
- expert action chunks

The data processing pipeline includes image preprocessing, feature engineering, vector normalization, and sliding-window sample construction.

## 5. VLA Policy Learning

GR00T N1.6 is used as the pretrained VLA backbone. The visual-language backbone is frozen, and LoRA adapters are attached to the diffusion action module. The model is fine-tuned with supervised learning / flow matching on expert demonstration action chunks.

## 6. Evaluation

The drill-grasping task is evaluated in Isaac Sim. The fine-tuned GR00T policy achieves a best success rate of 41.67%, outperforming Diffusion Policy, BC Transformer, and GR00T zero-shot baselines.

| Method | Success Rate |
|---|---:|
| Fine-tuned GR00T | 41.67% |
| Diffusion Policy | 35.42% |
| BC Transformer | 29.17% |
| GR00T zero-shot | 4.08% |

Stage-wise analysis suggests that motion reaching is relatively reliable, while final grasping remains the main bottleneck.

## 7. Limitations

- The demonstration dataset focuses on a single drill-grasping task.
- More tools, operators, initial poses, and recovery cases are needed.
- Future work should improve contact stability, finger closure timing, lighting robustness, and pose-deviation recovery.
