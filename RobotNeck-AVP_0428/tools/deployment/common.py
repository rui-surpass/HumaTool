import json
import platform
import shutil
from dataclasses import dataclass
from pathlib import Path


IGNORE_NAMES = {
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".git",
    ".DS_Store",
    "dist",
}


@dataclass(frozen=True)
class VendorSource:
    name: str
    source_path: Path
    bundle_path: str
    python_path: str


def _project_root_path(project_root):
    return Path(project_root).resolve()


def _ancestor_candidate_paths(root, relative_path):
    candidates = []
    for ancestor in [root] + list(root.parents):
        candidate = ancestor / relative_path
        if candidate not in candidates:
            candidates.append(candidate)
    return candidates


def resolve_vendor_sources(project_root):
    root = _project_root_path(project_root)
    specs = {
        "avp_stream": {
            "candidates": _ancestor_candidate_paths(root, Path("vendor") / "visionproteleop")
            + _ancestor_candidate_paths(root.parent, Path("VisionProTeleop")),
            "bundle_path": "vendor/visionproteleop",
            "python_path": "vendor/visionproteleop",
        },
        "dynamixel_sdk": {
            "candidates": _ancestor_candidate_paths(root, Path("vendor") / "DynamixelSDK-main")
            + _ancestor_candidate_paths(root.parent, Path("DynamixelSDK-main")),
            "bundle_path": "vendor/DynamixelSDK-main",
            "python_path": "vendor/DynamixelSDK-main/python/src",
        },
    }

    resolved = {}
    for name, spec in specs.items():
        source_path = next((candidate for candidate in spec["candidates"] if candidate.exists()), None)
        if source_path is None:
            raise FileNotFoundError(f"Required vendor dependency '{name}' was not found for {root}")
        resolved[name] = VendorSource(
            name=name,
            source_path=source_path.resolve(),
            bundle_path=spec["bundle_path"],
            python_path=spec["python_path"],
        )
    return resolved


def _ignore_filter(_directory, names):
    return {name for name in names if name in IGNORE_NAMES}


def stage_application_tree(project_root, bundle_root):
    root = _project_root_path(project_root)
    bundle_root = Path(bundle_root).resolve()
    app_root = bundle_root / "robotneck_app"
    if app_root.exists():
        shutil.rmtree(app_root)

    shutil.copytree(root, app_root, ignore=_ignore_filter)

    vendor_root = app_root / "vendor"
    if vendor_root.exists():
        shutil.rmtree(vendor_root)

    for vendor in resolve_vendor_sources(root).values():
        target = app_root / vendor.bundle_path
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(vendor.source_path, target, ignore=_ignore_filter)

    return app_root


def stage_bundle_runtime_tree(project_root, bundle_root):
    root = _project_root_path(project_root)
    bundle_root = Path(bundle_root).resolve()
    deployment_source = root / "tools" / "deployment"
    deployment_target = bundle_root / "tools" / "deployment"

    if deployment_target.exists():
        shutil.rmtree(deployment_target)

    deployment_target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(deployment_source, deployment_target, ignore=_ignore_filter)
    return deployment_target


def build_bundle_manifest(project_root, vendors, env_name):
    root = _project_root_path(project_root)
    return {
        "project_name": root.name,
        "env_name": str(env_name),
        "build_machine": platform.machine(),
        "entrypoints": {
            "gui_launcher": "tools/deployment/run_robot_gui.sh",
            "env_restore": "tools/deployment/restore_robot_env.sh",
            "conda_env_create": "tools/deployment/create_robot_conda_env.sh",
            "env_check": "tools/deployment/check_robot_env.py",
            "bundle_builder": "tools/deployment/build_robot_bundle.py",
            "app_gui": "robotneck_app/src/gui/main.py",
            "app": "robotneck_app/src/main.py",
        },
        "vendors": {
            name: {
                "source_path": str(vendor.source_path),
                "bundle_path": vendor.bundle_path,
                "python_path": vendor.python_path,
            }
            for name, vendor in vendors.items()
        },
        "system_requirements": {
            "python": "3.10",
            "zed_sdk_library": "/usr/local/zed/lib/libsl_zed.so",
            "motor_port": "/dev/ttyUSB0",
        },
    }


def write_bundle_manifest(bundle_root, manifest):
    bundle_root = Path(bundle_root).resolve()
    manifest_path = bundle_root / "deploy_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    return manifest_path
