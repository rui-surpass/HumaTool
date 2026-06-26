# HumaTool

**Teleoperation and VLA for Humanoid Tool Grasping**

HumaTool is an academic robotics project that explores a teleoperation-to-learning pipeline for humanoid tool grasping in smart construction scenarios. The project enables a Unitree G1 humanoid robot to grasp an electric drill by combining active visual teleoperation, expert demonstration collection, and Vision-Language-Action policy adaptation.

## Overview

The project focuses on a tool-based construction manipulation task: grasping an electric drill with a humanoid robot. Expert demonstrations are collected through teleoperation and then used to fine-tune a pretrained VLA policy for autonomous tool grasping.

The system integrates:

* Unitree G1 humanoid robot
* Apple Vision Pro-based operator input
* Active 2-DoF head-neck stereo vision module
* ZED Mini first-person visual feedback
* Dual-arm and dexterous-hand teleoperation
* Synchronized demonstration recording
* GR00T-based VLA policy learning with LoRA adaptation
* Isaac Sim-based evaluation

## Project Information

* **Project name:** HumaTool
* **Time:** 2026.03–2026.06
* **Affiliation:** College of Civil Engineering, Tongji University
* **Instructor:** Yuqing Gao
* **Scenario:** Smart construction and humanoid tool operation
* **Task:** Electric drill grasping
* **Robot platform:** Unitree G1 humanoid robot
* **Model:** GR00T N1.6-based VLA policy
* **Best success rate:** 41.67%

## System Pipeline

The project is organized as a continuous pipeline:

1. **Teleoperation System Construction**
   Build a closed-loop teleoperation system with operator motion input, robot execution, active visual feedback, and synchronized recording.

2. **Demonstration Dataset Collection**
   Collect expert trajectories including visual observations, robot states, end-effector poses, hand states, and operator action commands.

3. **VLA Policy Fine-tuning**
   Fine-tune a pretrained GR00T-based Vision-Language-Action model using LoRA adapters for the drill-grasping task.

4. **Simulation and Evaluation**
   Evaluate the trained policy in Isaac Sim through success rate comparison, failure-stage analysis, and qualitative case studies.

```

## Key Results

The fine-tuned GR00T-based policy achieved the best success rate among tested strategies in the drill-grasping task.

| Method           | Success Rate |
| ---------------- | -----------: |
| Fine-tuned GR00T |       41.67% |
| Diffusion Policy |       35.42% |
| BC Transformer   |       29.17% |
| GR00T zero-shot  |        4.08% |

The stage-wise analysis shows that motion reaching is relatively stable, while grasping remains the main bottleneck due to the need for precise finger-tool contact.

## Limitations and Future Work

Current demonstrations mainly focus on a single drill-grasping task. Future work will expand the dataset to include more tools, operators, initial poses, lighting conditions, occlusions, and recovery cases. Further improvements will also focus on grasping robustness, contact stability, and finger closure timing.
