"""Demonstration dataset conversion template.

The project dataset is expected to contain synchronized visual observations,
robot states, and expert actions. This script provides a clean structure for
turning private raw logs into training samples without exposing raw data.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, Iterable, List


def sliding_windows(items: List[dict], window_size: int, stride: int) -> Iterable[List[dict]]:
    """Yield fixed-size windows from a trajectory."""
    if window_size <= 0 or stride <= 0:
        raise ValueError("window_size and stride must be positive")
    for start in range(0, max(0, len(items) - window_size + 1), stride):
        yield items[start : start + window_size]


def load_trajectory(path: Path) -> List[dict]:
    """Load one trajectory JSONL file."""
    with path.open("r", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def build_sample(window: List[dict]) -> Dict:
    """Convert a raw window into a training sample."""
    last = window[-1]
    return {
        "observation": last.get("observation", {}),
        "robot_state": last.get("robot_state", {}),
        "instruction": last.get("instruction", "Pick up the industrial object."),
        "expert_action_chunk": [frame.get("action", {}) for frame in window],
    }


def convert_dataset(input_dir: Path, output_path: Path, window_size: int, stride: int) -> None:
    """Convert all trajectory JSONL files in a folder into a JSONL sample file."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with output_path.open("w", encoding="utf-8") as out:
        for traj_path in sorted(input_dir.glob("*.jsonl")):
            trajectory = load_trajectory(traj_path)
            for window in sliding_windows(trajectory, window_size, stride):
                out.write(json.dumps(build_sample(window), ensure_ascii=False) + "\n")
                count += 1
    print(f"Wrote {count} samples to {output_path}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--window-size", type=int, default=16)
    parser.add_argument("--stride", type=int, default=4)
    args = parser.parse_args()
    convert_dataset(args.input_dir, args.output, args.window_size, args.stride)


if __name__ == "__main__":
    main()
