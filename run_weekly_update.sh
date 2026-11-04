#!/usr/bin/env bash
#
# Weekly entry point -- point the scheduler (Windows Task Scheduler or cron)
# at this script. It runs run_initial_upload.sh for every enabled source under
# data_ETL/ and then writes ONE notification digest, msg.md.
#
#   ./run_weekly_update.sh                    normal run (what the scheduler calls)
#   ./run_weekly_update.sh --dry-run          every step except the upload, for checking
#   ./run_weekly_update.sh --env prod [...]   use the prod portal (default: PORTAL_ENV
#                                             in pipeline.conf)
#
# * Folders under data_ETL/ starting with "_" (the template) are skipped, as
#   are sources whose source.conf says ENABLED=0 (or ENABLED_DEV / _PROD=0).
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
ENV_ARG=""
while [[ $# -gt 0 ]]; do
    case "$1" in
        --dry-run) SOURCE_ARGS+=(--dry-run); DRY_RUN=1 ;;
        --env)     [[ $# -ge 2 ]] || { echo "$1 needs a value" >&2; exit 2; }; ENV_ARG="$2"; shift ;;
        -h|--help) sed -n '2,22p' "$0"; exit 0 ;;
        *)         echo "Unknown option: $1 (accepted: --dry-run, --env dev|prod)" >&2; exit 2 ;;
    esac
    shift
done

PORTAL_ENV="dev"
SLACK_CHANNEL=""
# shellcheck source=pipeline.conf
source "${REPO_DIR}/pipeline.conf"

# Which portal: --env wins over pipeline.conf. Every source in this run uses it.
PORTAL_ENV="${ENV_ARG:-${PORTAL_ENV}}"
case "${PORTAL_ENV}" in
    dev|prod) ;;
    *) echo "ERROR: the portal must be dev or prod (got '${PORTAL_ENV}')" >&2; exit 2 ;;
esac
export PORTAL_ENV
SOURCE_ARGS+=(--env "${PORTAL_ENV}")

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

echo "== Weekly run started $(date '+%Y-%m-%d %H:%M:%S') on ${PORTAL_ENV^^} -> ${INGEST_RUN_DIR#"${REPO_DIR}"/}"

# --- Every enabled source -------------------------------------------------
ANY_PROBLEM=0
RAN=0
for dir in "${REPO_DIR}"/data_ETL/*/; do
    name="$(basename "${dir}")"
    [[ "${name}" == _* ]] && continue
    [[ -f "${dir}/source.conf" ]] || continue

    # ENABLED_DEV / ENABLED_PROD win over ENABLED on that portal.
    enabled="$(source "${REPO_DIR}/upload_workflow/load_source_conf.sh"; loadSourceConf "${dir}" "${PORTAL_ENV}"; echo "${ENABLED}")"
    if [[ "${enabled}" != 1 ]]; then
        echo "== Skipping ${name} (not enabled for ${PORTAL_ENV} in its source.conf)"
        continue
    fi

    echo
    echo "################ ${name} ################"
    RAN=$((RAN + 1))
    if ! "${REPO_DIR}/run_initial_upload.sh" "${name}" ${SOURCE_ARGS[@]+"${SOURCE_ARGS[@]}"}; then
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
