import os
import sys
from pathlib import Path


root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(root_dir)

from src.core.bootstrap import compute_runtime_paths, configure_runtime_paths


def test_compute_runtime_paths_prefers_vendored_dependencies(tmp_path):
    project_root = tmp_path / "RobotNeck-AVP"
    vendored_avp = project_root / "vendor" / "visionproteleop"
    vendored_dxl = project_root / "vendor" / "DynamixelSDK-main" / "python" / "src"

    vendored_avp.mkdir(parents=True)
    vendored_dxl.mkdir(parents=True)

    paths = compute_runtime_paths(project_root)

    assert paths[0] == str(project_root)
    assert str(vendored_avp) in paths
    assert str(vendored_dxl) in paths


def test_compute_runtime_paths_uses_sibling_dependencies_when_vendor_is_missing(tmp_path):
    project_root = tmp_path / "RobotNeck-AVP"
    sibling_root = tmp_path
    project_root.mkdir(parents=True)
    sibling_avp = sibling_root / "VisionProTeleop"
    sibling_dxl = sibling_root / "DynamixelSDK-main" / "python" / "src"
    sibling_avp.mkdir(parents=True)
    sibling_dxl.mkdir(parents=True)

    paths = compute_runtime_paths(project_root)

    assert str(sibling_avp) in paths
    assert str(sibling_dxl) in paths


def test_compute_runtime_paths_searches_ancestor_siblings(tmp_path):
    workspace_root = tmp_path / "workspace"
    project_root = workspace_root / "RobotNeck-AVP_copy_0326" / "RobotNeck-AVP"
    project_root.mkdir(parents=True)
    ancestor_avp = workspace_root / "VisionProTeleop"
    ancestor_dxl = workspace_root / "DynamixelSDK-main" / "python" / "src"
    ancestor_avp.mkdir(parents=True)
    ancestor_dxl.mkdir(parents=True)

    paths = compute_runtime_paths(project_root)

    assert str(ancestor_avp) in paths
    assert str(ancestor_dxl) in paths


def test_configure_runtime_paths_is_idempotent(tmp_path, monkeypatch):
    project_root = tmp_path / "RobotNeck-AVP"
    vendored_avp = project_root / "vendor" / "visionproteleop"
    vendored_dxl = project_root / "vendor" / "DynamixelSDK-main" / "python" / "src"
    vendored_avp.mkdir(parents=True)
    vendored_dxl.mkdir(parents=True)

    monkeypatch.setattr(sys, "path", ["already-there"])

    first_paths = configure_runtime_paths(project_root)
    second_paths = configure_runtime_paths(project_root)

    assert first_paths == second_paths
    assert sys.path.count(str(project_root)) == 1
    assert sys.path.count(str(vendored_avp)) == 1
    assert sys.path.count(str(vendored_dxl)) == 1
