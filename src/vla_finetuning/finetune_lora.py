"""GR00T / VLA LoRA fine-tuning entry template.

This is a public-safe training scaffold. It documents the expected fine-tuning
steps without bundling pretrained checkpoints, private training data, or SDK-specific code.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import yaml


def load_config(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def finetune_gr00t(config: dict) -> None:
    """Documented fine-tuning flow."""
    print("Fine-tuning plan:")
    print("1. Load pretrained GR00T backbone")
    print("2. Convert teleoperation demonstrations to the selected training format")
    print("3. Freeze the visual-language backbone")
    print("4. Attach LoRA adapters to the diffusion action module")
    print("5. Train with flow matching / supervised action prediction")
    print("6. Export LoRA checkpoint for inference")
    print("\nConfig:")
    for key, value in config.items():
        print(f"- {key}: {value}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=Path("configs/train_lora.yaml"))
    args = parser.parse_args()
    config = load_config(args.config)
    finetune_gr00t(config)


if __name__ == "__main__":
    main()
