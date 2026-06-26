import argparse
import importlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


def resolve_project_root(script_path=None):
    script_file = Path(script_path or __file__).resolve()
    for ancestor in script_file.parents:
        bundled_app_root = ancestor / "robotneck_app"
        if (bundled_app_root / "src").exists():
            return bundled_app_root

    return script_file.parents[2]


PROJECT_ROOT = resolve_project_root()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.core.bootstrap import compute_runtime_paths, configure_runtime_paths


DEFAULT_IMPORTS = ["PyQt6", "cv2", "pyzed.sl", "avp_stream", "dynamixel_sdk"]
DEFAULT_ZED_LIBRARY = Path("/usr/local/zed/lib/libsl_zed.so")
DEFAULT_MOTOR_PORT = Path("/dev/ttyUSB0")


def build_import_probe_env(project_root, python_prefix=None, base_env=None):
    env = dict(base_env or os.environ)

    runtime_paths = compute_runtime_paths(project_root)
    existing_pythonpath = env.get("PYTHONPATH", "")
    pythonpath_parts = [path for path in runtime_paths if path]
    if existing_pythonpath:
        pythonpath_parts.append(existing_pythonpath)
    env["PYTHONPATH"] = os.pathsep.join(pythonpath_parts)

    prefix = Path(python_prefix or sys.prefix)
    libgomp_path = prefix / "lib" / "libgomp.so.1"
    if libgomp_path.exists():
        existing_preload = env.get("LD_PRELOAD", "")
        preload_parts = [str(libgomp_path)]
        if existing_preload:
            preload_parts.append(existing_preload)
        env["LD_PRELOAD"] = ":".join(preload_parts)

    return env


def _import_probe(module_name, project_root):
    env = build_import_probe_env(project_root)
    probe_code = (
        "import importlib, sys\n"
        "importlib.import_module(sys.argv[1])\n"
        "print('ok')\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", probe_code, module_name],
        check=False,
        text=True,
        capture_output=True,
        env=env,
    )
    if result.returncode == 0:
        return "ok"

    detail = (result.stderr or result.stdout).strip()
    if detail:
        return detail.splitlines()[-1]
    return f"ImportError: failed to import {module_name}"


def evaluate_environment(
    project_root,
    import_results,
    libsl_zed_exists,
    ttyusb_exists,
    conda_available,
    python_version,
):
    python_ok = str(python_version).startswith("3.10")
    checks = {
        "conda": {
            "ok": bool(conda_available),
            "detail": "available" if conda_available else "conda command not found",
        },
        "python": {
            "ok": python_ok,
            "detail": str(python_version),
        },
        "PyQt6": {
            "ok": import_results.get("PyQt6") == "ok",
            "detail": import_results.get("PyQt6", "not checked"),
        },
        "cv2": {
            "ok": import_results.get("cv2") == "ok",
            "detail": import_results.get("cv2", "not checked"),
        },
        "pyzed.sl": {
            "ok": import_results.get("pyzed.sl") == "ok",
            "detail": import_results.get("pyzed.sl", "not checked"),
        },
        "avp_stream": {
            "ok": import_results.get("avp_stream") == "ok",
            "detail": import_results.get("avp_stream", "not checked"),
        },
        "dynamixel_sdk": {
            "ok": import_results.get("dynamixel_sdk") == "ok",
            "detail": import_results.get("dynamixel_sdk", "not checked"),
        },
        "libsl_zed": {
            "ok": bool(libsl_zed_exists),
            "detail": str(DEFAULT_ZED_LIBRARY),
        },
        "tty_usb0": {
            "ok": bool(ttyusb_exists),
            "detail": str(DEFAULT_MOTOR_PORT),
        },
        "project_root": {
            "ok": Path(project_root).exists(),
            "detail": str(Path(project_root).resolve()),
        },
    }
    return {
        "ready": all(item["ok"] for item in checks.values()),
        "checks": checks,
    }


def collect_environment_report(project_root):
    configure_runtime_paths(project_root)
    import_results = {module_name: _import_probe(module_name, project_root) for module_name in DEFAULT_IMPORTS}
    return evaluate_environment(
        project_root=project_root,
        import_results=import_results,
        libsl_zed_exists=DEFAULT_ZED_LIBRARY.exists(),
        ttyusb_exists=DEFAULT_MOTOR_PORT.exists(),
        conda_available=shutil.which("conda") is not None,
        python_version=sys.version.split()[0],
    )


def main():
    parser = argparse.ArgumentParser(description="Check whether the robot runtime environment is ready.")
    parser.add_argument(
        "--project-root",
        default=str(PROJECT_ROOT),
        help="Project root that should be available on the robot.",
    )
    parser.add_argument(
        "--format",
        choices=["json", "text"],
        default="text",
        help="Output format.",
    )
    args = parser.parse_args()

    report = collect_environment_report(args.project_root)
    if args.format == "json":
        print(json.dumps(report, indent=2, sort_keys=True))
        return

    status = "READY" if report["ready"] else "NOT READY"
    print(f"Robot environment status: {status}")
    for name, result in report["checks"].items():
        flag = "OK" if result["ok"] else "FAIL"
        print(f"[{flag}] {name}: {result['detail']}")


if __name__ == "__main__":
    main()
