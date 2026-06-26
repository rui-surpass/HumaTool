#!/usr/bin/env bash
set -euo pipefail

resolve_project_root() {
  cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd
}

json_escape() {
  python -c 'import json, sys; print(json.dumps(sys.argv[1]))' "$1"
}

latest_diagnostic_dir() {
  local base_dir="$1"
  if [[ ! -d "${base_dir}" ]]; then
    return 1
  fi

  find "${base_dir}" -mindepth 1 -maxdepth 1 -type d -printf '%P\n' | sort | tail -n 1
}

latest_diagnostic_dir_since() {
  local base_dir="$1"
  local started_at="$2"
  if [[ ! -d "${base_dir}" ]]; then
    return 1
  fi

  find "${base_dir}" -mindepth 1 -maxdepth 1 -type d -printf '%T@ %P\n' \
    | awk -v started_at="${started_at}" '$1 >= started_at { print $2 }' \
    | sort \
    | tail -n 1
}

write_run_metadata() {
  local diag_path="$1"
  local gui_exit_code="$2"
  local analysis_exit_code="$3"
  local archive_path="$4"
  local git_commit="unknown"
  local git_branch="unknown"
  local host_name
  local ended_at

  if git -C "${PROJECT_ROOT}" rev-parse HEAD >/dev/null 2>&1; then
    git_commit="$(git -C "${PROJECT_ROOT}" rev-parse HEAD)"
  fi
  if git -C "${PROJECT_ROOT}" rev-parse --abbrev-ref HEAD >/dev/null 2>&1; then
    git_branch="$(git -C "${PROJECT_ROOT}" rev-parse --abbrev-ref HEAD)"
  fi

  host_name="$(hostname)"
  ended_at="$(date -Iseconds)"

  cat > "${diag_path}/run_meta.json" <<EOF
{
  "project_root": $(json_escape "${PROJECT_ROOT}"),
  "diagnostics_dir": $(json_escape "${diag_path}"),
  "gui_runner": $(json_escape "${GUI_RUNNER}"),
  "analyzer": $(json_escape "${ANALYZER}"),
  "started_at_epoch": ${STARTED_AT},
  "started_at_iso": $(json_escape "${STARTED_AT_ISO}"),
  "ended_at_iso": $(json_escape "${ended_at}"),
  "host": $(json_escape "${host_name}"),
  "user": $(json_escape "${USER:-unknown}"),
  "cwd": $(json_escape "${PROJECT_ROOT}"),
  "git_commit": $(json_escape "${git_commit}"),
  "git_branch": $(json_escape "${git_branch}"),
  "gui_exit_code": ${gui_exit_code},
  "analysis_exit_code": ${analysis_exit_code},
  "archive_path": $(json_escape "${archive_path}"),
  "env": {
    "ROBO_NECK_DEBUG_TIMING": $(json_escape "${ROBO_NECK_DEBUG_TIMING}"),
    "ROBO_NECK_DIAG_CAPTURE": $(json_escape "${ROBO_NECK_DIAG_CAPTURE}")
  }
}
EOF
}

create_archive() {
  local diag_path="$1"
  local archive_path="$2"
  local diag_name
  diag_name="$(basename "${diag_path}")"
  tar -C "$(dirname "${diag_path}")" -czf "${archive_path}" "${diag_name}"
}

PROJECT_ROOT="$(resolve_project_root)"
GUI_RUNNER="${ROBO_NECK_GUI_RUNNER:-${PROJECT_ROOT}/tools/deployment/run_robot_gui.sh}"
ANALYZER="${ROBO_NECK_DIAG_ANALYZER:-${PROJECT_ROOT}/tools/hardware_checks/diagnose_tracking_latency.py}"
DIAGNOSTICS_DIR="${ROBO_NECK_DIAGNOSTICS_DIR:-${PROJECT_ROOT}/diagnostics}"

if [[ ! -f "${GUI_RUNNER}" ]]; then
  echo "Missing GUI launcher: ${GUI_RUNNER}"
  exit 1
fi

if [[ ! -f "${ANALYZER}" ]]; then
  echo "Missing analyzer script: ${ANALYZER}"
  exit 1
fi

mkdir -p "${DIAGNOSTICS_DIR}"
cd "${PROJECT_ROOT}"

export ROBO_NECK_DEBUG_TIMING="${ROBO_NECK_DEBUG_TIMING:-1}"
export ROBO_NECK_DIAG_CAPTURE="${ROBO_NECK_DIAG_CAPTURE:-1}"

STARTED_AT="$(date +%s)"
STARTED_AT_ISO="$(date -Iseconds)"

echo "Project root: ${PROJECT_ROOT}"
echo "Diagnostics dir: ${DIAGNOSTICS_DIR}"
echo "ROBO_NECK_DEBUG_TIMING=${ROBO_NECK_DEBUG_TIMING}"
echo "ROBO_NECK_DIAG_CAPTURE=${ROBO_NECK_DIAG_CAPTURE}"
echo "Launching GUI. Reproduce the latency issue, then close the GUI to auto-run analysis."

set +e
bash "${GUI_RUNNER}" "$@"
GUI_EXIT_CODE=$?
set -e

LATEST_DIR_NAME="$(latest_diagnostic_dir_since "${DIAGNOSTICS_DIR}" "${STARTED_AT}" || true)"
if [[ -z "${LATEST_DIR_NAME}" ]]; then
  LATEST_DIR_NAME="$(latest_diagnostic_dir "${DIAGNOSTICS_DIR}" || true)"
fi

ANALYSIS_EXIT_CODE=0
ARCHIVE_PATH=""
if [[ -n "${LATEST_DIR_NAME}" && -f "${DIAGNOSTICS_DIR}/${LATEST_DIR_NAME}/events.jsonl" ]]; then
  DIAG_PATH="${DIAGNOSTICS_DIR}/${LATEST_DIR_NAME}"
  echo ""
  echo "Analyzing diagnostic capture: ${DIAG_PATH}"
  set +e
  python "${ANALYZER}" --input-dir "${DIAG_PATH}"
  ANALYSIS_EXIT_CODE=$?
  set -e
  ARCHIVE_PATH="${DIAGNOSTICS_DIR}/${LATEST_DIR_NAME}.tar.gz"
  write_run_metadata "${DIAG_PATH}" "${GUI_EXIT_CODE}" "${ANALYSIS_EXIT_CODE}" "${ARCHIVE_PATH}"
  create_archive "${DIAG_PATH}" "${ARCHIVE_PATH}"
  echo ""
  if [[ "${ANALYSIS_EXIT_CODE}" -eq 0 ]]; then
    echo "Analysis status: success"
  else
    echo "Analysis status: failed (${ANALYSIS_EXIT_CODE})"
  fi
  echo "events.jsonl: found"
  echo "summary.json: $( [[ -f "${DIAG_PATH}/summary.json" ]] && echo found || echo missing )"
  echo "run_meta.json: $( [[ -f "${DIAG_PATH}/run_meta.json" ]] && echo found || echo missing )"
  echo "Archive: ${ARCHIVE_PATH}"
  echo "Raw capture saved under: ${DIAG_PATH}"
else
  echo ""
  echo "No diagnostic capture was found under ${DIAGNOSTICS_DIR}."
  echo "If the GUI exited before initialization, rerun and reproduce the issue for a longer interval."
fi

if [[ "${GUI_EXIT_CODE}" -ne 0 ]]; then
  exit "${GUI_EXIT_CODE}"
fi

if [[ "${ANALYSIS_EXIT_CODE}" -ne 0 ]]; then
  exit "${ANALYSIS_EXIT_CODE}"
fi
