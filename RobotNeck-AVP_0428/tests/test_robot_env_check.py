import os
import sys
from pathlib import Path


root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(root_dir)

from tools.deployment.check_robot_env import (
    build_import_probe_env,
    evaluate_environment,
    resolve_project_root,
)


def test_evaluate_environment_reports_missing_components(tmp_path):
    report = evaluate_environment(
        project_root=tmp_path,
        import_results={
            "PyQt6": "ok",
            "cv2": "ok",
            "pyzed.sl": "missing",
            "avp_stream": "ok",
            "dynamixel_sdk": "missing",
        },
        libsl_zed_exists=False,
        ttyusb_exists=False,
        conda_available=True,
        python_version="3.10.19",
    )

    assert report["ready"] is False
    assert report["checks"]["pyzed.sl"]["ok"] is False
    assert report["checks"]["dynamixel_sdk"]["ok"] is False
    assert report["checks"]["libsl_zed"]["ok"] is False
    assert report["checks"]["tty_usb0"]["ok"] is False


def test_evaluate_environment_is_ready_when_all_required_components_exist(tmp_path):
    report = evaluate_environment(
        project_root=tmp_path,
        import_results={
            "PyQt6": "ok",
            "cv2": "ok",
            "pyzed.sl": "ok",
            "avp_stream": "ok",
            "dynamixel_sdk": "ok",
        },
        libsl_zed_exists=True,
        ttyusb_exists=True,
        conda_available=True,
        python_version="3.10.19",
    )

    assert report["ready"] is True
    assert all(item["ok"] for item in report["checks"].values())


def test_resolve_project_root_uses_bundle_robotneck_app_when_running_from_bundle_tools(tmp_path):
    bundle_root = tmp_path / "robot_deploy"
    (bundle_root / "robotneck_app" / "src").mkdir(parents=True)
    script_path = bundle_root / "tools" / "deployment" / "check_robot_env.py"
    script_path.parent.mkdir(parents=True)
    script_path.write_text("# placeholder\n", encoding="utf-8")

    assert resolve_project_root(script_path) == bundle_root / "robotneck_app"


def test_build_import_probe_env_adds_runtime_paths_and_libgomp(tmp_path):
    project_root = tmp_path / "RobotNeck-AVP"
    (project_root / "src").mkdir(parents=True)
    (project_root / "vendor" / "visionproteleop").mkdir(parents=True)
    (project_root / "vendor" / "DynamixelSDK-main" / "python" / "src").mkdir(parents=True)
    python_prefix = tmp_path / "env_prefix"
    (python_prefix / "lib").mkdir(parents=True)
    (python_prefix / "lib" / "libgomp.so.1").write_text("", encoding="utf-8")

    env = build_import_probe_env(project_root, python_prefix=python_prefix, base_env={"PYTHONPATH": "/existing/path"})

    assert str(project_root) in env["PYTHONPATH"]
    assert str(project_root / "vendor" / "visionproteleop") in env["PYTHONPATH"]
    assert str(python_prefix / "lib" / "libgomp.so.1") == env["LD_PRELOAD"].split(":")[0]
