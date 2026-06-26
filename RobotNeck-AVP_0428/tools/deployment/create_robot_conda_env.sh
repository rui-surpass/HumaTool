#!/usr/bin/env bash
set -euo pipefail

resolve_bundle_root() {
  local script_dir="$1"
  local candidate="${script_dir}"

  while [[ "${candidate}" != "/" ]]; do
    if [[ -d "${candidate}/env" && -d "${candidate}/robotneck_app" ]]; then
      printf '%s\n' "${candidate}"
      return 0
    fi
    candidate="$(dirname "${candidate}")"
  done

  cd "${script_dir}/../.." && pwd
}

ensure_conda_shell() {
  if [[ -n "${CONDA_EXE:-}" ]]; then
    eval "$("${CONDA_EXE}" shell.bash hook)"
    return 0
  fi

  if [[ -f "${HOME}/anaconda3/etc/profile.d/conda.sh" ]]; then
    # shellcheck disable=SC1090
    source "${HOME}/anaconda3/etc/profile.d/conda.sh"
    return 0
  fi

  if [[ -f "${HOME}/miniconda3/etc/profile.d/conda.sh" ]]; then
    # shellcheck disable=SC1090
    source "${HOME}/miniconda3/etc/profile.d/conda.sh"
    return 0
  fi

  echo "Could not locate Conda shell initialization on this robot."
  exit 1
}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUNDLE_ROOT="$(resolve_bundle_root "${SCRIPT_DIR}")"
APP_ROOT="${BUNDLE_ROOT}/robotneck_app"
SOURCE_ENV_NAME="${1:-avp_teleop}"
TARGET_ENV_NAME="${2:-${SOURCE_ENV_NAME}}"
FORCE_RECREATE="${3:-}"
SOURCE_PREFIX="${BUNDLE_ROOT}/env/${SOURCE_ENV_NAME}"
RESTORE_SCRIPT="${BUNDLE_ROOT}/tools/deployment/restore_robot_env.sh"
SNAPSHOT_PATH="${BUNDLE_ROOT}/env/snapshot.json"

read_snapshot_machine() {
  if [[ ! -f "${SNAPSHOT_PATH}" ]]; then
    return 0
  fi

  sed -n 's/.*"machine"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' "${SNAPSHOT_PATH}" | head -n 1
}

create_native_environment() {
  echo "Creating native Conda environment '${TARGET_ENV_NAME}' for $(uname -m)."
  conda create --yes --name "${TARGET_ENV_NAME}" -c conda-forge python=3.10 pip numpy scipy pyserial opencv pyqt6 matplotlib
  conda run -n "${TARGET_ENV_NAME}" python -m pip install grpcio aiortc av requests pyyaml tqdm pydub websocket-client gdown flask protobuf
}

HOST_MACHINE="$(uname -m)"
PACKED_MACHINE="$(read_snapshot_machine)"
USE_NATIVE_ENV=false

if [[ -n "${PACKED_MACHINE}" && "${PACKED_MACHINE}" != "${HOST_MACHINE}" ]]; then
  echo "Bundle environment architecture mismatch detected: bundle=${PACKED_MACHINE}, host=${HOST_MACHINE}."
  echo "Skipping bundle clone and creating a native Conda environment instead."
  USE_NATIVE_ENV=true
fi

if [[ "${USE_NATIVE_ENV}" != true && ! -x "${SOURCE_PREFIX}/bin/python" ]]; then
  if [[ -x "${RESTORE_SCRIPT}" ]]; then
    bash "${RESTORE_SCRIPT}" "${SOURCE_ENV_NAME}"
  else
    echo "Could not find a restored bundle environment at ${SOURCE_PREFIX}."
    exit 1
  fi
fi

if [[ "${USE_NATIVE_ENV}" != true && ! -x "${SOURCE_PREFIX}/bin/python" ]]; then
  echo "Bundle-local environment is still missing at ${SOURCE_PREFIX} after restore."
  exit 1
fi

if [[ "${USE_NATIVE_ENV}" != true ]] && ! "${SOURCE_PREFIX}/bin/python" -V >/dev/null 2>&1; then
  echo "Bundle-local environment failed a Python self-check. Creating a native Conda environment instead."
  USE_NATIVE_ENV=true
fi

ensure_conda_shell

existing_envs_json="$(conda env list --json)"
if printf '%s' "${existing_envs_json}" | grep -F "\"/${TARGET_ENV_NAME}\"" >/dev/null || printf '%s' "${existing_envs_json}" | grep -F "\"\\\\${TARGET_ENV_NAME}\"" >/dev/null || printf '%s' "${existing_envs_json}" | grep -F "\"${TARGET_ENV_NAME}\"" >/dev/null; then
  if [[ "${FORCE_RECREATE}" == "--force" ]]; then
    conda env remove --yes --name "${TARGET_ENV_NAME}"
  else
    echo "Conda environment '${TARGET_ENV_NAME}' already exists."
    echo "Use: bash tools/deployment/create_robot_conda_env.sh ${SOURCE_ENV_NAME} ${TARGET_ENV_NAME} --force"
    exit 1
  fi
fi

if [[ "${USE_NATIVE_ENV}" == true ]]; then
  create_native_environment
  echo "Created native Conda environment '${TARGET_ENV_NAME}'."
else
  conda create --yes --name "${TARGET_ENV_NAME}" --clone "${SOURCE_PREFIX}"
  echo "Created Conda environment '${TARGET_ENV_NAME}' from ${SOURCE_PREFIX}"
fi
echo "Activate it with: conda activate ${TARGET_ENV_NAME}"
