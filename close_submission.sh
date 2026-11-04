#!/usr/bin/env bash
#
# Close (discard) the open submission for one source, so the next run can
# upload a new one. Use it when the open submission should not be committed:
# it failed validation, or the data has to be redone.
#
#   ./close_submission.sh PHAC               shows the submission, asks you to confirm
#   ./close_submission.sh PHAC --env prod    the same on the prod portal
#   ./close_submission.sh PHAC --yes         closes it without asking
#
# The portal is --env, else PORTAL_ENV in pipeline.conf. Only an open
# (uncommitted) submission can be closed. Published records are never touched,
# and nothing is ever committed. SOP.md, Procedure L.

set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_NAME="ProjectIngestion"

usage() { sed -n '2,13p' "$0" | sed 's/^# \{0,1\}//'; }

SOURCE_NAME=""
ENV_ARG=""
YES=()
while [[ $# -gt 0 ]]; do
    case "$1" in
        --yes)     YES=(--yes) ;;
        --env)     [[ $# -ge 2 ]] || { echo "$1 needs a value" >&2; exit 2; }; ENV_ARG="$2"; shift ;;
        -h|--help) usage; exit 0 ;;
        -*)        echo "Unknown option: $1" >&2; usage >&2; exit 2 ;;
        *)
            if [[ -n "${SOURCE_NAME}" ]]; then
                echo "One source at a time (got '${SOURCE_NAME}' and '$1')" >&2; exit 2
            fi
            SOURCE_NAME="$1" ;;
    esac
    shift
done
[[ -n "${SOURCE_NAME}" ]] || { usage >&2; exit 2; }

SOURCE_DIR="${REPO_DIR}/data_ETL/${SOURCE_NAME}"
if [[ ! -f "${SOURCE_DIR}/source.conf" ]]; then
    echo "ERROR: no data_ETL/${SOURCE_NAME}/source.conf (the source is the folder name, e.g. PHAC)" >&2
    exit 2
fi
PORTAL_ENV="dev"
# shellcheck source=pipeline.conf
source "${REPO_DIR}/pipeline.conf"
PORTAL_ENV="${ENV_ARG:-${PORTAL_ENV}}"
case "${PORTAL_ENV}" in
    dev|prod) ;;
    *) echo "ERROR: the portal must be dev or prod (got '${PORTAL_ENV}')" >&2; exit 2 ;;
esac
export PORTAL_ENV

# The source's organization and category on this portal.
# shellcheck source=upload_workflow/load_source_conf.sh
source "${REPO_DIR}/upload_workflow/load_source_conf.sh"
loadSourceConf "${SOURCE_DIR}" "${PORTAL_ENV}"
checkSourceConf "${SOURCE_DIR}" "${PORTAL_ENV}" || exit 2
echo "Portal: ${PORTAL_ENV} · organization ${ORGANIZATION} · category ${CATEGORY}"

# --- Conda environment ---------------------------------------------------
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

# Don't close a submission while a pipeline run might be uploading to it.
mkdir -p "${REPO_DIR}/runs"
exec 9>"${REPO_DIR}/runs/.lock"
if ! flock -n 9; then
    echo "ERROR: a pipeline run is in progress (runs/.lock). Try again when it has finished." >&2
    exit 1
fi

python "${REPO_DIR}/upload_workflow/close_submission.py" \
    --organization "${ORGANIZATION}" --category "${CATEGORY}" ${YES[@]+"${YES[@]}"}
