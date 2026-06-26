import argparse
import json
import platform
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from tools.deployment.common import (
    build_bundle_manifest,
    resolve_vendor_sources,
    stage_bundle_runtime_tree,
    stage_application_tree,
    write_bundle_manifest,
)


def _run_command(command, output_path, cwd=None):
    result = subprocess.run(
        command,
        cwd=cwd,
        check=False,
        text=True,
        capture_output=True,
    )
    output_path.write_text(result.stdout + result.stderr, encoding="utf-8")
    return result.returncode == 0


def export_environment_snapshot(bundle_root, env_name):
    bundle_root = Path(bundle_root).resolve()
    env_root = bundle_root / "env"
    env_root.mkdir(parents=True, exist_ok=True)

    snapshot = {
        "env_name": env_name,
        "conda_pack_created": False,
        "machine": platform.machine(),
    }

    _run_command(["conda", "list", "--explicit"], env_root / "conda-explicit.txt")
    _run_command([sys.executable, "-m", "pip", "freeze"], env_root / "pip-freeze.txt")
    _run_command(["conda", "env", "export"], env_root / "environment.yml")

    probe = subprocess.run(
        [sys.executable, "-c", "import importlib.util; print(importlib.util.find_spec('conda_pack') is not None)"],
        check=False,
        text=True,
        capture_output=True,
    )
    conda_pack_available = probe.stdout.strip() == "True"
    snapshot["conda_pack_available"] = conda_pack_available

    if conda_pack_available:
        archive_path = env_root / f"{env_name}.tar.gz"
        conda_pack_cmd = shutil.which("conda-pack")
        packed = subprocess.run(
            [
                conda_pack_cmd or "conda-pack",
                "-n",
                env_name,
                "-o",
                str(archive_path),
                "--ignore-editable-packages",
            ],
            check=False,
            text=True,
            capture_output=True,
        )
        (env_root / "conda-pack.log").write_text(
            packed.stdout + packed.stderr,
            encoding="utf-8",
        )
        snapshot["conda_pack_created"] = packed.returncode == 0 and archive_path.exists()
    else:
        (env_root / "conda-pack.log").write_text(
            "conda_pack is not installed in the current Python environment.\n",
            encoding="utf-8",
        )

    (env_root / "snapshot.json").write_text(json.dumps(snapshot, indent=2, sort_keys=True), encoding="utf-8")
    return snapshot


def build_robot_bundle(project_root, output_dir, env_name, allow_missing_packed_env=False):
    project_root = Path(project_root).resolve()
    output_dir = Path(output_dir).resolve()
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    staged_app_root = stage_application_tree(project_root, output_dir)
    stage_bundle_runtime_tree(project_root, output_dir)
    vendors = resolve_vendor_sources(project_root)
    manifest = build_bundle_manifest(project_root, vendors, env_name)
    snapshot = export_environment_snapshot(output_dir, env_name)
    if not allow_missing_packed_env and not snapshot.get("conda_pack_created"):
        raise RuntimeError(
            "No packed environment archive was created for the deployment bundle. "
            "Install conda-pack in the active environment or rerun with "
            "--allow-missing-packed-env if you intentionally want a fallback-only bundle."
        )
    write_bundle_manifest(output_dir, manifest)

    archive_path = output_dir.with_suffix(".tar.gz")
    if archive_path.exists():
        archive_path.unlink()
    with tarfile.open(archive_path, "w:gz") as archive:
        archive.add(output_dir, arcname=output_dir.name)

    return {
        "bundle_root": str(output_dir),
        "staged_app_root": str(staged_app_root),
        "archive_path": str(archive_path),
    }


def main():
    parser = argparse.ArgumentParser(description="Build an offline RobotNeck deployment bundle.")
    parser.add_argument("--project-root", default=str(PROJECT_ROOT))
    parser.add_argument("--output-dir", default=str(PROJECT_ROOT / "dist" / "robot_deploy"))
    parser.add_argument("--env-name", default="avp_teleop")
    parser.add_argument(
        "--allow-missing-packed-env",
        action="store_true",
        help="Allow bundles that only contain fallback environment files when conda-pack is unavailable.",
    )
    args = parser.parse_args()

    result = build_robot_bundle(
        project_root=args.project_root,
        output_dir=args.output_dir,
        env_name=args.env_name,
        allow_missing_packed_env=args.allow_missing_packed_env,
    )
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
