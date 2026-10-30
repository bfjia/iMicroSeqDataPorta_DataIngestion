#!/usr/bin/env bash
#
# Weekly entry point -- point the scheduler (Windows Task Scheduler or cron)
# at this script. It runs run_source.sh for every enabled source under
# data_ETL/ and then writes ONE notification digest, msg.md.
#
#   ./run_weekly.sh             normal run (what the scheduler calls)
#   ./run_weekly.sh --dry-run   every step except the upload, for checking
#
# * Folders under data_ETL/ starting with "_" (the template) are skipped, as
#   are sources whose source.conf says ENABLED=0.
# * One source failing does not stop the others.
# * Only one pipeline run at a time (lock file runs/.lock).
# * Nothing is ever published: submissions wait for a person to commit them
#   on the portal website.
#
# Exit code: 0 if every source finished cleanly (including "waiting for your
# commit" and "nothing new"), 1 if any source had a problem.

set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_NAME="ProjectIngestion"

SOURCE_ARGS=()
DRY_RUN=0
case "${1:-}" in
    "")        ;;
    --dry-run) SOURCE_ARGS=(--dry-run); DRY_RUN=1 ;;
    -h|--help) sed -n '2,20p' "$0"; exit 0 ;;
    *)         echo "Unknown option: $1 (only --dry-run is accepted)" >&2; exit 2 ;;
esac

SLACK_CHANNEL=""
# shellcheck source=pipeline.conf
source "${REPO_DIR}/pipeline.conf"

# --- Conda environment (a scheduler starts with a bare shell) -------------
activateEnv() {
    [[ "${CONDA_DEFAULT_ENV:-}" == "${ENV_NAME}" ]] && return 0
    local conda="${CONDA_EXE:-}"
    [[ -x "${conda}" ]] || conda="${HOME}/miniconda3/bin/conda"
    if [[ ! -x "${conda}" ]]; then
        echo "ERROR: conda not found. Run 'conda activate ${ENV_NAME}' first." >&2
        return 1
    fi
    set +u
    eval "$("${conda}" shell.bash hook)"
    conda activate "${ENV_NAME}"
    local rc=$?
    set -u
    return ${rc}
}
activateEnv

# --- Lock + run folder ----------------------------------------------------
mkdir -p "${REPO_DIR}/runs"
exec 9>"${REPO_DIR}/runs/.lock"
if ! flock -n 9; then
    echo "ERROR: another pipeline run is in progress (runs/.lock). Try again later." >&2
    exit 1
fi

export INGEST_RUN_DIR="${REPO_DIR}/runs/$(date +%Y%m%d-%H%M%S)"
mkdir -p "${INGEST_RUN_DIR}"
exec > >(tee -a "${INGEST_RUN_DIR}/weekly.log") 2>&1

echo "== Weekly run started $(date '+%Y-%m-%d %H:%M:%S') -> ${INGEST_RUN_DIR#"${REPO_DIR}"/}"

# --- Every enabled source -------------------------------------------------
ANY_PROBLEM=0
RAN=0
for dir in "${REPO_DIR}"/data_ETL/*/; do
    name="$(basename "${dir}")"
    [[ "${name}" == _* ]] && continue
    [[ -f "${dir}/source.conf" ]] || continue

    enabled="$(ENABLED=1; source "${dir}/source.conf"; echo "${ENABLED}")"
    if [[ "${enabled}" != 1 ]]; then
        echo "== Skipping ${name} (ENABLED=${enabled} in its source.conf)"
        continue
    fi

    echo
    echo "################ ${name} ################"
    RAN=$((RAN + 1))
    if ! "${REPO_DIR}/run_source.sh" "${name}" ${SOURCE_ARGS[@]+"${SOURCE_ARGS[@]}"}; then
        ANY_PROBLEM=1
    fi
done

[[ "${RAN}" -gt 0 ]] || echo "== No enabled sources found under data_ETL/"

# --- One notification for the whole run -----------------------------------
echo
python "${REPO_DIR}/upload_workflow/notify.py" --run-dir "${INGEST_RUN_DIR}" \
    --out "${INGEST_RUN_DIR}/msg.md" --copy-to "${REPO_DIR}/msg.md"
echo "== Weekly run finished $(date '+%Y-%m-%d %H:%M:%S'); notification in msg.md"

# --- Post it to Slack: once per run, never for a dry run ------------------
# A failed post doesn't change the run's outcome; msg.md is still written.
if [[ -n "${SLACK_CHANNEL}" && "${DRY_RUN}" -eq 0 ]]; then
    python "${REPO_DIR}/upload_workflow/slack_post.py" --file "${INGEST_RUN_DIR}/msg.md" \
        --channel "${SLACK_CHANNEL}" \
        || echo "WARNING: msg.md was written but could not be posted to Slack (error above)"
fi
exit "${ANY_PROBLEM}"
