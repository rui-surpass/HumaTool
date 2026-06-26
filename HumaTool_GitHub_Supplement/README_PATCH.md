# Suggested README Add-on

If your repository currently only contains the README and the RoboNeck-AVP code, add the following sections or merge them into your existing README.

## Public Repository Scope

This repository is a public-safe release of the HumaTool project. It focuses on the project overview, the RoboNeck-AVP head-neck teleoperation subsystem, demonstration data format, VLA policy-learning workflow, and evaluation documentation.

The following files are intentionally excluded:

- raw teleoperation demonstrations
- pretrained or fine-tuned model weights
- robot private SDK files
- device IP addresses, serial numbers, and local absolute paths
- unpublished full thesis source files

## Recommended Upload Order

1. Keep the existing `README.md` and `src/robo_neck_avp/` folder.
2. Add `docs/` for portfolio PDF, project report, and software stack notes.
3. Add `assets/` for README figures.
4. Add `configs/` and `examples/` for reproducible configuration and usage documentation.
5. Add `data/README.md` and `models/README.md` to explain why raw data and weights are not included.
6. Add `.gitignore`, `requirements.txt`, `NOTICE.md`, and `CITATION.cff`.
7. Optionally add `src/data_processing/` and `src/vla_finetuning/` as public-safe workflow templates.

## Minimal Commit Sequence

```bash
git add docs assets configs examples data models .gitignore requirements.txt NOTICE.md CITATION.cff
git commit -m "Add project documentation and public-safe assets"

git add src/data_processing src/vla_finetuning
git commit -m "Add public-safe data and policy learning templates"
```
