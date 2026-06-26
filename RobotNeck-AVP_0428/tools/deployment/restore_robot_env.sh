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

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUNDLE_ROOT="$(resolve_bundle_root "${SCRIPT_DIR}")"
ENV_ROOT="${BUNDLE_ROOT}/env"
ENV_NAME="${1:-avp_teleop}"
ARCHIVE_PATH="${ENV_ROOT}/${ENV_NAME}.tar.gz"
TARGET_PATH="${ENV_ROOT}/${ENV_NAME}"
SNAPSHOT_PATH="${ENV_ROOT}/snapshot.json"

read_snapshot_machine() {
  if [[ ! -f "${SNAPSHOT_PATH}" ]]; then
    return 0
  fi

  sed -n 's/.*"machine"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' "${SNAPSHOT_PATH}" | head -n 1
}

if [[ ! -f "${ARCHIVE_PATH}" ]]; then
  echo "No packed environment archive found at ${ARCHIVE_PATH}."
  echo "Fallback files are available in ${ENV_ROOT}/conda-explicit.txt and ${ENV_ROOT}/pip-freeze.txt."
  exit 1
fi

HOST_MACHINE="$(uname -m)"
PACKED_MACHINE="$(read_snapshot_machine)"
if [[ -n "${PACKED_MACHINE}" && "${PACKED_MACHINE}" != "${HOST_MACHINE}" ]]; then
  echo "Packed environment architecture mismatch: bundle was built for ${PACKED_MACHINE}, but this machine is ${HOST_MACHINE}."
  echo "Do not restore ${ARCHIVE_PATH} on this robot."
  echo "Create a native Conda environment on the robot or rebuild the bundle on ${HOST_MACHINE}."
  exit 1
fi

rm -rf "${TARGET_PATH}"
mkdir -p "${TARGET_PATH}"
tar -xzf "${ARCHIVE_PATH}" -C "${TARGET_PATH}"

if [[ -x "${TARGET_PATH}/bin/conda-unpack" ]]; then
  "${TARGET_PATH}/bin/conda-unpack"
fi

echo "Restored environment to ${TARGET_PATH}"
