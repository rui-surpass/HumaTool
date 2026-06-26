import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _ancestor_candidate_paths(root, relative_path):
    candidates = []
    for ancestor in [root] + list(root.parents):
        candidate = ancestor / relative_path
        if candidate not in candidates:
            candidates.append(candidate)
    return candidates


def compute_runtime_paths(project_root=None):
    root = Path(project_root or PROJECT_ROOT).resolve()
    candidates = [root]
    candidates.extend(_ancestor_candidate_paths(root, Path("vendor") / "visionproteleop"))
    candidates.extend(_ancestor_candidate_paths(root, Path("vendor") / "DynamixelSDK-main" / "python" / "src"))
    candidates.extend(_ancestor_candidate_paths(root.parent, Path("VisionProTeleop")))
    candidates.extend(_ancestor_candidate_paths(root.parent, Path("DynamixelSDK-main") / "python" / "src"))

    paths = []
    for candidate in candidates:
        text = str(candidate)
        if candidate.exists() and text not in paths:
            paths.append(text)
    return paths


def configure_runtime_paths(project_root=None):
    runtime_paths = compute_runtime_paths(project_root)
    for candidate in reversed(runtime_paths):
        if candidate not in sys.path:
            sys.path.insert(0, candidate)
    return runtime_paths
