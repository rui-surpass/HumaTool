import json
import os
import subprocess
import sys
import tarfile
from pathlib import Path

import pytest


root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(root_dir)

from tools.deployment.common import (
    build_bundle_manifest,
    resolve_vendor_sources,
    stage_bundle_runtime_tree,
    stage_application_tree,
)
from tools.deployment.build_robot_bundle import build_robot_bundle


def test_resolve_vendor_sources_prefers_local_vendor_tree(tmp_path):
    project_root = tmp_path / "RobotNeck-AVP"
    project_root.mkdir()
    vendored_avp = project_root / "vendor" / "visionproteleop"
    vendored_dxl = project_root / "vendor" / "DynamixelSDK-main"
    vendored_avp.mkdir(parents=True)
    (vendored_dxl / "python" / "src").mkdir(parents=True)

    vendors = resolve_vendor_sources(project_root)

    assert vendors["avp_stream"].source_path == vendored_avp
    assert vendors["dynamixel_sdk"].source_path == vendored_dxl


def test_stage_application_tree_copies_repo_and_vendor_dependencies(tmp_path):
    project_root = tmp_path / "RobotNeck-AVP"
    project_root.mkdir()
    (project_root / "src").mkdir()
    (project_root / "src" / "main.py").write_text("print('ok')\n", encoding="utf-8")
    (project_root / "tools" / "hardware_checks").mkdir(parents=True)
    (project_root / "tools" / "hardware_checks" / "run_field_diagnostics.sh").write_text(
        "#!/usr/bin/env bash\n",
        encoding="utf-8",
    )
    (project_root / "__pycache__").mkdir()
    (project_root / "__pycache__" / "stale.pyc").write_bytes(b"pyc")
    sibling_avp = tmp_path / "VisionProTeleop"
    sibling_dxl = tmp_path / "DynamixelSDK-main"
    sibling_avp.mkdir()
    (sibling_avp / "setup.py").write_text("from setuptools import setup\n", encoding="utf-8")
    sibling_dxl.mkdir()
    (sibling_dxl / "python" / "src").mkdir(parents=True)
    (sibling_dxl / "python" / "setup.py").write_text("from setuptools import setup\n", encoding="utf-8")

    bundle_root = tmp_path / "bundle"
    staged_app_root = stage_application_tree(project_root, bundle_root)

    assert (staged_app_root / "src" / "main.py").exists()
    assert (staged_app_root / "tools" / "hardware_checks" / "run_field_diagnostics.sh").exists()
    assert not (staged_app_root / "__pycache__").exists()
    assert (staged_app_root / "vendor" / "visionproteleop" / "setup.py").exists()
    assert (staged_app_root / "vendor" / "DynamixelSDK-main" / "python" / "setup.py").exists()


def test_resolve_vendor_sources_searches_ancestor_siblings(tmp_path):
    workspace_root = tmp_path / "workspace"
    project_root = workspace_root / "RobotNeck-AVP_copy_0326" / "RobotNeck-AVP"
    project_root.mkdir(parents=True)
    ancestor_avp = workspace_root / "VisionProTeleop"
    ancestor_dxl = workspace_root / "DynamixelSDK-main"
    ancestor_avp.mkdir(parents=True)
    (ancestor_dxl / "python" / "src").mkdir(parents=True)

    vendors = resolve_vendor_sources(project_root)

    assert vendors["avp_stream"].source_path == ancestor_avp
    assert vendors["dynamixel_sdk"].source_path == ancestor_dxl


def test_stage_bundle_runtime_tree_copies_deployment_entrypoints(tmp_path):
    project_root = tmp_path / "RobotNeck-AVP"
    deployment_dir = project_root / "tools" / "deployment"
    deployment_dir.mkdir(parents=True)
    for name in ("restore_robot_env.sh", "run_robot_gui.sh", "check_robot_env.py", "create_robot_conda_env.sh"):
        (deployment_dir / name).write_text(f"# {name}\n", encoding="utf-8")

    bundle_root = tmp_path / "bundle"
    stage_bundle_runtime_tree(project_root, bundle_root)

    assert (bundle_root / "tools" / "deployment" / "restore_robot_env.sh").exists()
    assert (bundle_root / "tools" / "deployment" / "run_robot_gui.sh").exists()
    assert (bundle_root / "tools" / "deployment" / "check_robot_env.py").exists()
    assert (bundle_root / "tools" / "deployment" / "create_robot_conda_env.sh").exists()


def test_repo_contains_field_diagnostic_launcher():
    project_root = Path(root_dir)

    assert (project_root / "tools" / "hardware_checks" / "run_field_diagnostics.sh").exists()


def test_field_diagnostic_launcher_writes_run_metadata_and_archive(tmp_path):
    project_root = Path(root_dir)
    launcher = project_root / "tools" / "hardware_checks" / "run_field_diagnostics.sh"
    fake_gui = tmp_path / "fake_gui.sh"
    diagnostics_dir = tmp_path / "diagnostics"
    capture_dir = diagnostics_dir / "20990101-000000"
    capture_dir.mkdir(parents=True)
    events_path = capture_dir / "events.jsonl"
    events_path.write_text(
        json.dumps(
            {
                "kind": "app_snapshot",
                "ts": 1.0,
                "payload": {
                    "tracking": True,
                    "session_mode": "tracking_only",
                    "pose_reason": "ready",
                    "pose_fresh": True,
                    "pose_age_ms": 18000.0,
                    "loop_rate_hz": 58.0,
                    "camera": {"frame_age_ms": 10.0, "read_failures": 0},
                    "timing": {
                        "avp_read": {"avg_ms": 1.0, "max_ms": 2.0},
                        "camera_read": {"avg_ms": 0.0, "max_ms": 0.0},
                        "update_loop": {"avg_ms": 1.0, "max_ms": 2.0},
                        "control_loop": {"avg_ms": 1.0, "max_ms": 2.0},
                        "motor_write": {"avg_ms": 1.0, "max_ms": 2.0},
                    },
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )
    fake_gui.write_text(
        "\n".join(
            [
                "#!/usr/bin/env bash",
                "set -euo pipefail",
                "sleep 1",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    fake_gui.chmod(0o755)

    env = os.environ.copy()
    env["ROBO_NECK_GUI_RUNNER"] = str(fake_gui)
    env["ROBO_NECK_DIAGNOSTICS_DIR"] = str(diagnostics_dir)

    result = subprocess.run(
        ["bash", str(launcher)],
        check=False,
        text=True,
        capture_output=True,
        env=env,
    )

    assert result.returncode == 0, result.stderr or result.stdout
    assert (capture_dir / "run_meta.json").exists()
    assert (diagnostics_dir / "20990101-000000.tar.gz").exists()
    run_meta = json.loads((capture_dir / "run_meta.json").read_text(encoding="utf-8"))
    assert run_meta["gui_exit_code"] == 0
    assert run_meta["diagnostics_dir"] == str(capture_dir)
    with tarfile.open(diagnostics_dir / "20990101-000000.tar.gz", "r:gz") as archive:
        names = archive.getnames()
    assert any(name.endswith("summary.json") for name in names)
    assert any(name.endswith("run_meta.json") for name in names)


def test_build_robot_bundle_requires_packed_environment_by_default(tmp_path, monkeypatch):
    project_root = tmp_path / "RobotNeck-AVP"
    (project_root / "src").mkdir(parents=True)
    (project_root / "src" / "main.py").write_text("print('ok')\n", encoding="utf-8")
    deployment_dir = project_root / "tools" / "deployment"
    deployment_dir.mkdir(parents=True)
    for name in ("restore_robot_env.sh", "run_robot_gui.sh", "check_robot_env.py", "build_robot_bundle.py"):
        (deployment_dir / name).write_text(f"# {name}\n", encoding="utf-8")
    vendored_avp = project_root / "vendor" / "visionproteleop"
    vendored_dxl = project_root / "vendor" / "DynamixelSDK-main"
    vendored_avp.mkdir(parents=True)
    (vendored_dxl / "python" / "src").mkdir(parents=True)

    monkeypatch.setattr(
        "tools.deployment.build_robot_bundle.export_environment_snapshot",
        lambda bundle_root, env_name: {
            "env_name": env_name,
            "conda_pack_available": False,
            "conda_pack_created": False,
        },
    )

    with pytest.raises(RuntimeError, match="No packed environment archive was created"):
        build_robot_bundle(project_root, tmp_path / "bundle", "avp_teleop")


def test_build_bundle_manifest_records_build_machine(tmp_path):
    project_root = tmp_path / "RobotNeck-AVP"
    project_root.mkdir()
    (project_root / "src").mkdir()
    vendored_avp = project_root / "vendor" / "visionproteleop"
    vendored_dxl = project_root / "vendor" / "DynamixelSDK-main"
    vendored_avp.mkdir(parents=True)
    (vendored_dxl / "python" / "src").mkdir(parents=True)

    vendors = resolve_vendor_sources(project_root)
    manifest = build_bundle_manifest(project_root, vendors, env_name="avp_teleop")

    assert "build_machine" in manifest
    assert manifest["build_machine"]


def test_restore_robot_env_script_finds_bundle_root_from_nested_app_path(tmp_path):
    project_root = Path(root_dir)
    script_source = project_root / "tools" / "deployment" / "restore_robot_env.sh"
    bundle_root = tmp_path / "robot_deploy"
    nested_script = bundle_root / "robotneck_app" / "tools" / "deployment" / "restore_robot_env.sh"
    nested_script.parent.mkdir(parents=True)
    nested_script.write_text(script_source.read_text(encoding="utf-8"), encoding="utf-8")
    nested_script.chmod(0o755)

    env_archive_root = bundle_root / "env"
    env_archive_root.mkdir(parents=True)
    packed_env_root = tmp_path / "packed_env"
    (packed_env_root / "bin").mkdir(parents=True)
    (packed_env_root / "bin" / "python").write_text("", encoding="utf-8")
    archive_path = env_archive_root / "avp_teleop.tar.gz"
    with tarfile.open(archive_path, "w:gz") as archive:
        archive.add(packed_env_root, arcname=".")

    result = subprocess.run(
        ["bash", str(nested_script)],
        check=False,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stderr or result.stdout
    assert (bundle_root / "env" / "avp_teleop" / "bin" / "python").exists()


def test_create_robot_conda_env_script_restores_and_clones_named_env(tmp_path):
    project_root = Path(root_dir)
    create_script_source = project_root / "tools" / "deployment" / "create_robot_conda_env.sh"
    restore_script_source = project_root / "tools" / "deployment" / "restore_robot_env.sh"

    bundle_root = tmp_path / "robot_deploy"
    tools_dir = bundle_root / "tools" / "deployment"
    tools_dir.mkdir(parents=True)

    create_script = tools_dir / "create_robot_conda_env.sh"
    create_script.write_text(create_script_source.read_text(encoding="utf-8"), encoding="utf-8")
    create_script.chmod(0o755)

    restore_script = tools_dir / "restore_robot_env.sh"
    restore_script.write_text(restore_script_source.read_text(encoding="utf-8"), encoding="utf-8")
    restore_script.chmod(0o755)

    (bundle_root / "robotneck_app" / "src").mkdir(parents=True)
    env_root = bundle_root / "env"
    env_root.mkdir(parents=True)
    packed_env_root = tmp_path / "packed_env"
    (packed_env_root / "bin").mkdir(parents=True)
    packed_python = packed_env_root / "bin" / "python"
    packed_python.write_text("", encoding="utf-8")
    packed_python.chmod(0o755)
    with tarfile.open(env_root / "avp_teleop.tar.gz", "w:gz") as archive:
        archive.add(packed_env_root, arcname=".")

    fake_bin = tmp_path / "fake_bin"
    fake_bin.mkdir()
    conda_log = tmp_path / "conda.log"
    fake_conda = fake_bin / "conda"
    fake_conda.write_text(
        "\n".join(
            [
                "#!/usr/bin/env bash",
                "set -euo pipefail",
                "LOG_PATH=\"" + str(conda_log) + "\"",
                "if [[ \"${1:-}\" == \"shell.bash\" && \"${2:-}\" == \"hook\" ]]; then",
                "  cat <<'EOF'",
                "conda() { \"$CONDA_EXE\" \"$@\"; }",
                "EOF",
                "  exit 0",
                "fi",
                "printf '%s\\n' \"$*\" >> \"$LOG_PATH\"",
                "if [[ \"${1:-}\" == \"env\" && \"${2:-}\" == \"list\" && \"${3:-}\" == \"--json\" ]]; then",
                "  printf '{\"envs\": []}'",
                "  exit 0",
                "fi",
                "if [[ \"${1:-}\" == \"create\" ]]; then",
                "  exit 0",
                "fi",
                "printf 'unexpected conda call: %s\\n' \"$*\" >&2",
                "exit 1",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    fake_conda.chmod(0o755)

    result = subprocess.run(
        ["bash", str(create_script)],
        check=False,
        text=True,
        capture_output=True,
        env={
            "PATH": f"{fake_bin}:{os.environ['PATH']}",
            "HOME": str(tmp_path / "home"),
            "CONDA_EXE": str(fake_conda),
        },
    )

    assert result.returncode == 0, result.stderr or result.stdout
    assert (bundle_root / "env" / "avp_teleop" / "bin" / "python").exists()
    logged = conda_log.read_text(encoding="utf-8")
    assert "create --yes --name avp_teleop --clone " in logged


def test_create_robot_conda_env_script_builds_native_env_when_arch_mismatches(tmp_path):
    project_root = Path(root_dir)
    create_script_source = project_root / "tools" / "deployment" / "create_robot_conda_env.sh"

    bundle_root = tmp_path / "robot_deploy"
    tools_dir = bundle_root / "tools" / "deployment"
    tools_dir.mkdir(parents=True)
    create_script = tools_dir / "create_robot_conda_env.sh"
    create_script.write_text(create_script_source.read_text(encoding="utf-8"), encoding="utf-8")
    create_script.chmod(0o755)

    app_root = bundle_root / "robotneck_app"
    (app_root / "src").mkdir(parents=True)
    (app_root / "vendor" / "visionproteleop").mkdir(parents=True)
    (app_root / "vendor" / "DynamixelSDK-main" / "python").mkdir(parents=True)

    env_root = bundle_root / "env"
    env_root.mkdir(parents=True)
    (env_root / "snapshot.json").write_text(
        json.dumps(
            {
                "env_name": "avp_teleop",
                "machine": "x86_64",
                "conda_pack_available": True,
                "conda_pack_created": True,
            }
        ),
        encoding="utf-8",
    )

    fake_bin = tmp_path / "fake_bin"
    fake_bin.mkdir()
    conda_log = tmp_path / "conda_native.log"
    fake_uname = fake_bin / "uname"
    fake_uname.write_text(
        "#!/usr/bin/env bash\nif [[ \"${1:-}\" == \"-m\" ]]; then\n  echo aarch64\nelse\n  /usr/bin/uname \"$@\"\nfi\n",
        encoding="utf-8",
    )
    fake_uname.chmod(0o755)
    fake_conda = fake_bin / "conda"
    fake_conda.write_text(
        "\n".join(
            [
                "#!/usr/bin/env bash",
                "set -euo pipefail",
                "LOG_PATH=\"" + str(conda_log) + "\"",
                "if [[ \"${1:-}\" == \"shell.bash\" && \"${2:-}\" == \"hook\" ]]; then",
                "  cat <<'EOF'",
                "conda() { \"$CONDA_EXE\" \"$@\"; }",
                "EOF",
                "  exit 0",
                "fi",
                "printf '%s\\n' \"$*\" >> \"$LOG_PATH\"",
                "if [[ \"${1:-}\" == \"env\" && \"${2:-}\" == \"list\" && \"${3:-}\" == \"--json\" ]]; then",
                "  printf '{\"envs\": []}'",
                "  exit 0",
                "fi",
                "exit 0",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    fake_conda.chmod(0o755)

    result = subprocess.run(
        ["bash", str(create_script)],
        check=False,
        text=True,
        capture_output=True,
        env={
            "PATH": f"{fake_bin}:{os.environ['PATH']}",
            "HOME": str(tmp_path / "home"),
            "CONDA_EXE": str(fake_conda),
        },
    )

    assert result.returncode == 0, result.stderr or result.stdout
    assert "creating native conda environment" in result.stdout.lower()
    logged = conda_log.read_text(encoding="utf-8")
    assert "create --yes --name avp_teleop -c conda-forge python=3.10 pip numpy scipy pyserial opencv pyqt6 matplotlib" in logged
    assert "run -n avp_teleop python -m pip install grpcio aiortc av requests pyyaml tqdm pydub websocket-client gdown flask protobuf" in logged


def test_run_robot_gui_skips_mismatched_local_env_and_uses_conda(tmp_path):
    project_root = Path(root_dir)
    script_source = project_root / "tools" / "deployment" / "run_robot_gui.sh"

    bundle_root = tmp_path / "robot_deploy"
    tools_dir = bundle_root / "tools" / "deployment"
    tools_dir.mkdir(parents=True)
    run_script = tools_dir / "run_robot_gui.sh"
    run_script.write_text(script_source.read_text(encoding="utf-8"), encoding="utf-8")
    run_script.chmod(0o755)

    app_root = bundle_root / "robotneck_app"
    (app_root / "src" / "gui").mkdir(parents=True)
    (app_root / "src" / "gui" / "main.py").write_text("print('placeholder')\n", encoding="utf-8")
    (app_root / "vendor" / "visionproteleop").mkdir(parents=True)
    (app_root / "vendor" / "DynamixelSDK-main" / "python" / "src").mkdir(parents=True)

    local_env_bin = bundle_root / "env" / "avp_teleop" / "bin"
    local_env_bin.mkdir(parents=True)
    local_python = local_env_bin / "python"
    local_python.write_text("", encoding="utf-8")
    local_python.chmod(0o755)

    snapshot_path = bundle_root / "env" / "snapshot.json"
    snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    snapshot_path.write_text(
        json.dumps(
            {
                "env_name": "avp_teleop",
                "machine": "x86_64",
                "conda_pack_available": True,
                "conda_pack_created": True,
            }
        ),
        encoding="utf-8",
    )

    fake_bin = tmp_path / "fake_bin"
    fake_bin.mkdir()
    invocation_log = tmp_path / "invocation.log"
    fake_uname = fake_bin / "uname"
    fake_uname.write_text(
        "#!/usr/bin/env bash\nif [[ \"${1:-}\" == \"-m\" ]]; then\n  echo aarch64\nelse\n  /usr/bin/uname \"$@\"\nfi\n",
        encoding="utf-8",
    )
    fake_uname.chmod(0o755)
    fake_conda = fake_bin / "conda"
    fake_conda.write_text(
        "\n".join(
                [
                    "#!/usr/bin/env bash",
                    "set -euo pipefail",
                    "LOG_PATH=\"" + str(invocation_log) + "\"",
                    "if [[ \"${1:-}\" == \"shell.bash\" && \"${2:-}\" == \"hook\" ]]; then",
                "  cat <<'EOF'",
                    "conda() { \"$CONDA_EXE\" \"$@\"; }",
                    "EOF",
                    "  exit 0",
                    "fi",
                    "printf '%s\\n' \"$*\" >> \"$LOG_PATH\"",
                    "if [[ \"${1:-}\" == \"activate\" && \"${2:-}\" == \"avp_teleop\" ]]; then",
                    "  export PATH=\"" + str(fake_bin) + ":$PATH\"",
                    "  return 0 2>/dev/null || exit 0",
                    "fi",
                    "exit 0",
                ]
            )
        + "\n",
        encoding="utf-8",
    )
    fake_conda.chmod(0o755)
    fake_python = fake_bin / "python"
    fake_python.write_text(
        "#!/usr/bin/env bash\nprintf '%s\\n' \"$@\" > \"" + str(invocation_log) + ".python\"\nexit 0\n",
        encoding="utf-8",
    )
    fake_python.chmod(0o755)

    result = subprocess.run(
        ["bash", str(run_script)],
        check=False,
        text=True,
        capture_output=True,
        env={
            "PATH": f"{fake_bin}:{os.environ['PATH']}",
            "HOME": str(tmp_path / "home"),
            "CONDA_EXE": str(fake_conda),
        },
    )

    assert result.returncode == 0, result.stderr or result.stdout
    assert "architecture mismatch" in result.stdout.lower()
    assert "activate avp_teleop" in invocation_log.read_text(encoding="utf-8")


def test_build_bundle_manifest_records_vendor_install_locations(tmp_path):
    project_root = tmp_path / "RobotNeck-AVP"
    project_root.mkdir()
    (project_root / "src").mkdir()
    vendored_avp = project_root / "vendor" / "visionproteleop"
    vendored_dxl = project_root / "vendor" / "DynamixelSDK-main"
    vendored_avp.mkdir(parents=True)
    (vendored_dxl / "python" / "src").mkdir(parents=True)

    vendors = resolve_vendor_sources(project_root)
    manifest = build_bundle_manifest(project_root, vendors, env_name="avp_teleop")

    assert manifest["env_name"] == "avp_teleop"
    assert manifest["vendors"]["avp_stream"]["bundle_path"] == "vendor/visionproteleop"
    assert manifest["vendors"]["dynamixel_sdk"]["python_path"] == "vendor/DynamixelSDK-main/python/src"
    json.dumps(manifest)
