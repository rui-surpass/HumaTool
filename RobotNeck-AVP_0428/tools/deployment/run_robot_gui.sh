#!/usr/bin/env bash
set -euo pipefail

resolve_bundle_root() {
  local script_dir="$1"
  local candidate="${script_dir}"

  while [[ "${candidate}" != "/" ]]; do
    if [[ -d "${candidate}/robotneck_app" ]]; then
      printf '%s\n' "${candidate}"
      return 0
    fi
    candidate="$(dirname "${candidate}")"
  done

  cd "${script_dir}/../.." && pwd
}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUNDLE_ROOT="$(resolve_bundle_root "${SCRIPT_DIR}")"
APP_ROOT="${BUNDLE_ROOT}/robotneck_app"
if [[ ! -d "${APP_ROOT}/src" ]]; then
  APP_ROOT="${BUNDLE_ROOT}"
fi
LOCAL_ENV="${BUNDLE_ROOT}/env/avp_teleop"
SNAPSHOT_PATH="${BUNDLE_ROOT}/env/snapshot.json"

if [[ ! -f "${APP_ROOT}/src/gui/main.py" ]]; then
  echo "Could not find GUI entrypoint under ${APP_ROOT}/src/gui/main.py"
  exit 1
fi

read_snapshot_machine() {
  if [[ ! -f "${SNAPSHOT_PATH}" ]]; then
    return 0
  fi

  sed -n 's/.*"machine"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' "${SNAPSHOT_PATH}" | head -n 1
}

prepend_libgomp_preload() {
  local prefix="$1"
  local libgomp_path="${prefix}/lib/libgomp.so.1"
  if [[ ! -f "${libgomp_path}" ]]; then
    return 0
  fi

  if [[ -n "${LD_PRELOAD:-}" ]]; then
    case ":${LD_PRELOAD}:" in
      *":${libgomp_path}:"*) return 0 ;;
    esac
    export LD_PRELOAD="${libgomp_path}:${LD_PRELOAD}"
    return 0
  fi

  export LD_PRELOAD="${libgomp_path}"
}

export PYTHONPATH="${APP_ROOT}:${APP_ROOT}/vendor/visionproteleop:${APP_ROOT}/vendor/DynamixelSDK-main/python/src:${PYTHONPATH:-}"

LOCAL_ENV_PYTHON="${LOCAL_ENV}/bin/python"
HOST_MACHINE="$(uname -m)"
PACKED_MACHINE="$(read_snapshot_machine)"

if [[ -x "${LOCAL_ENV_PYTHON}" ]]; then
  if [[ -n "${PACKED_MACHINE}" && "${PACKED_MACHINE}" != "${HOST_MACHINE}" ]]; then
    echo "Skipping bundle-local environment due to architecture mismatch: bundle=${PACKED_MACHINE}, host=${HOST_MACHINE}."
  elif "${LOCAL_ENV_PYTHON}" -V >/dev/null 2>&1; then
    prepend_libgomp_preload "${LOCAL_ENV}"
    exec "${LOCAL_ENV_PYTHON}" "${APP_ROOT}/src/gui/main.py"
  else
    echo "Skipping bundle-local environment because ${LOCAL_ENV_PYTHON} failed a Python self-check."
  fi
fi

if [[ -n "${CONDA_EXE:-}" ]]; then
  eval "$("${CONDA_EXE}" shell.bash hook)"
elif [[ -f "${HOME}/anaconda3/etc/profile.d/conda.sh" ]]; then
  source "${HOME}/anaconda3/etc/profile.d/conda.sh"
elif [[ -f "${HOME}/miniconda3/etc/profile.d/conda.sh" ]]; then
  source "${HOME}/miniconda3/etc/profile.d/conda.sh"
fi

conda activate avp_teleop
if [[ -n "${CONDA_PREFIX:-}" ]]; then
  prepend_libgomp_preload "${CONDA_PREFIX}"
fi
exec python "${APP_ROOT}/src/gui/main.py"
