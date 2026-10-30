#!/usr/bin/env bash
#
# Run one data source end to end:
#
#   1 pending check   stop if a submission for the org is still open (before any work)
#   2 ETL             data_ETL/<SOURCE>/etl.sh -> upload-ready CSV
#   3 date window     keep only weeks from DEV_MIN_START_DATE (pipeline.conf)
#   4 portal snapshot what the org already has published
#   5 diff            new / changed / unchanged
#   6 guard           stop if "new" is suspiciously large (MAX_NEW)
#   7 upload          upload + validate the new records
#
# It NEVER publishes. A VALID upload is left open for a person to review and
# commit on the portal website. Every run writes a status for msg.md.
# README.md explains each step in detail; SOP.md is the plain-language guide.
#
#   ./run_source.sh PHAC
#   ./run_source.sh PHAC --holdout-weeks 1 --keep-work

set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
UPLOAD_DIR="${REPO_DIR}/upload_workflow"
ENV_NAME="ProjectIngestion"

usage() {
    cat <<'EOF'
Usage: ./run_source.sh <SOURCE> [options]

  <SOURCE>              folder name under data_ETL/, e.g. PHAC

Options:
  --dry-run             do every step except the upload: shows what WOULD be uploaded
  --force               upload even if there are more new records than MAX_NEW
  --holdout-weeks N     TEST ONLY: hold back the newest N weeks of new records
  --holdout-random N    TEST ONLY: also hold back N random older new records
  --keep-work           keep the bulky intermediate files in runs/
  -h, --help            show this help

Uploads and validates only. Nothing is published until a person commits the
submission on the portal website.
EOF
}

# --- Arguments -----------------------------------------------------------
SOURCE_NAME=""
DRY_RUN=0
FORCE=0
HOLDOUT_WEEKS=0
HOLDOUT_RANDOM=0
KEEP_WORK=0
while [[ $# -gt 0 ]]; do
    case "$1" in
        --dry-run)        DRY_RUN=1 ;;
        --force)          FORCE=1 ;;
        --holdout-weeks)  HOLDOUT_WEEKS="${2:-}"; shift ;;
        --holdout-random) HOLDOUT_RANDOM="${2:-}"; shift ;;
        --keep-work)      KEEP_WORK=1 ;;
        -h|--help)        usage; exit 0 ;;
        -*)               echo "Unknown option: $1" >&2; usage >&2; exit 2 ;;
        *)
            if [[ -n "${SOURCE_NAME}" ]]; then
                echo "One source at a time (got '${SOURCE_NAME}' and '$1')" >&2; exit 2
            fi
            SOURCE_NAME="$1" ;;
    esac
    shift
done
[[ -n "${SOURCE_NAME}" ]] || { usage >&2; exit 2; }
if ! [[ "${HOLDOUT_WEEKS}" =~ ^[0-9]+$ && "${HOLDOUT_RANDOM}" =~ ^[0-9]+$ ]]; then
    echo "--holdout-weeks and --holdout-random need a whole number" >&2; exit 2
fi

SOURCE_DIR="${REPO_DIR}/data_ETL/${SOURCE_NAME}"
if [[ ! -f "${SOURCE_DIR}/source.conf" || ! -f "${SOURCE_DIR}/etl.sh" ]]; then
    echo "ERROR: ${SOURCE_DIR} needs a source.conf and an etl.sh (see data_ETL/README.md)" >&2
    exit 2
fi

# --- Configuration -------------------------------------------------------
DEV_MIN_START_DATE=""
DEFAULT_MAX_NEW=2000
# shellcheck source=pipeline.conf
source "${REPO_DIR}/pipeline.conf"

SOURCE_ID=""; ORGANIZATION=""; CATEGORY="imicroseq_wastewater"; UPLOAD_CSV=""; MAX_NEW=""; ENABLED=1
# shellcheck disable=SC1091
source "${SOURCE_DIR}/source.conf"
for var in SOURCE_ID ORGANIZATION CATEGORY UPLOAD_CSV; do
    [[ -n "${!var}" ]] || { echo "ERROR: ${SOURCE_DIR}/source.conf must set ${var}" >&2; exit 2; }
done
MAX_NEW="${MAX_NEW:-${DEFAULT_MAX_NEW}}"
CUTOFF="${DEV_MIN_START_DATE}"

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

# --- Run folder, lock, log ----------------------------------------------
# run_weekly.sh sets INGEST_RUN_DIR and already holds the lock. Run on its own,
# this script takes the lock and writes its own msg.md.
STANDALONE=0
if [[ -z "${INGEST_RUN_DIR:-}" ]]; then
    STANDALONE=1
    mkdir -p "${REPO_DIR}/runs"
    exec 9>"${REPO_DIR}/runs/.lock"
    if ! flock -n 9; then
        echo "ERROR: another pipeline run is in progress (runs/.lock). Try again later." >&2
        exit 1
    fi
    INGEST_RUN_DIR="${REPO_DIR}/runs/$(date +%Y%m%d-%H%M%S)"
fi
OUT="${INGEST_RUN_DIR}/${SOURCE_ID}"
mkdir -p "${OUT}"
LOG="${OUT}/run.log"
STATUS_FILE="${OUT}/status.env"
: > "${STATUS_FILE}"
exec > >(tee -a "${LOG}") 2>&1

# --- Status + exit handling ---------------------------------------------
# status.env holds KEY=value lines that notify.py turns into msg.md.
setStatus() { printf '%s=%s\n' "$1" "${2//$'\n'/ }" >> "${STATUS_FILE}"; }
kv() { local s=" $2 "; s="${s#* $1=}"; echo "${s%% *}"; }   # kv new "new=3 changed=0" -> 3

STEP="start-up"
FINAL=""
finish() {             # finish <status> <exit code>
    FINAL="$1"
    setStatus STATUS "$1"
    exit "$2"
}
fail() {               # fail <reason>  -- uses the current STEP
    echo "ERROR: $1" >&2
    setStatus REASON "$1"
    setStatus STEP "${STEP}"
    finish failed 1
}
onExit() {
    local code=$?
    set +e
    if [[ -z "${FINAL}" ]]; then        # an unexpected error stopped the script
        setStatus STATUS failed
        setStatus STEP "${STEP}"
    fi
    if [[ "${KEEP_WORK}" -eq 0 ]]; then
        rm -rf "${OUT}/in_scope.csv" "${OUT}/published.csv" "${OUT}/submit"
    fi
    echo "== ${SOURCE_ID}: finished with status '$(grep '^STATUS=' "${STATUS_FILE}" | tail -n1 | cut -d= -f2)' (log: ${LOG#"${REPO_DIR}"/})"
    if [[ "${STANDALONE}" -eq 1 ]]; then
        python "${UPLOAD_DIR}/notify.py" --run-dir "${INGEST_RUN_DIR}" \
            --out "${INGEST_RUN_DIR}/msg.md" --copy-to "${REPO_DIR}/msg.md" > /dev/null \
            && echo "== Notification written to msg.md"
    fi
    exit "${code}"
}
trap onExit EXIT

setStatus SOURCE_ID "${SOURCE_ID}"
setStatus ORGANIZATION "${ORGANIZATION}"
setStatus LOG "${LOG}"
setStatus CUTOFF "${CUTOFF}"
setStatus MAX_NEW "${MAX_NEW}"

echo "== ${SOURCE_ID}: run started $(date '+%Y-%m-%d %H:%M:%S')"
echo "   organization ${ORGANIZATION}, category ${CATEGORY}, date window from ${CUTOFF:-the beginning}"
(( HOLDOUT_WEEKS + HOLDOUT_RANDOM > 0 )) && echo "   TEST MODE: holding back records (--holdout-*)"
(( DRY_RUN )) && echo "   DRY RUN: every step except the upload"

# --- 1. Pending check, before any actual work ---------------------------
STEP="login"
echo "[1/7] Pending check"
echo "      Logging in to the portal"
PORTAL_TOKEN="$(python "${UPLOAD_DIR}/step1_token.py")" \
    || fail "Could not log in to the portal. Check the username and password in upload_workflow/.env."
export PORTAL_TOKEN

STEP="pending check"
PENDING_OUT="$(python "${UPLOAD_DIR}/check_pending.py" --category "${CATEGORY}" --organization "${ORGANIZATION}")" \
    || fail "Could not check the portal for open submissions, so stopped rather than risk a duplicate upload."

PENDING=""; WRITE_SCOPE=""; PENDING_ID=""; PENDING_STATUS=""; PENDING_CREATED=""; PENDING_URL=""
while IFS='=' read -r key value; do
    case "${key}" in
        PENDING|WRITE_SCOPE|PENDING_ID|PENDING_STATUS|PENDING_CREATED|PENDING_URL)
            printf -v "${key}" '%s' "${value}" ;;
    esac
done <<< "${PENDING_OUT}"
[[ "${PENDING}" == 0 || "${PENDING}" == 1 ]] || fail "The open-submission check gave no answer."

if [[ "${PENDING}" == 1 ]]; then
    setStatus SUBMISSION_ID "${PENDING_ID}"
    setStatus SUBMISSION_URL "${PENDING_URL}"
    setStatus PENDING_STATUS "${PENDING_STATUS}"
    setStatus PENDING_CREATED "${PENDING_CREATED}"
    echo "      Submission ${PENDING_ID} is still open (${PENDING_STATUS}), created ${PENDING_CREATED}."
    echo "      Stopping before any work. It needs to be committed or fixed on the website:"
    echo "        ${PENDING_URL}"
    if [[ "${PENDING_STATUS}" == "INVALID" ]]; then
        finish waiting_invalid 1
    fi
    finish waiting 0
fi
echo "      No open submission for ${ORGANIZATION}."

STEP="permission check"
if [[ "${WRITE_SCOPE}" != 1 ]]; then
    fail "The portal account has no write permission for ${ORGANIZATION} (it needs the scope WW-${ORGANIZATION}.WRITE). Ask the portal administrators to grant it."
fi

# --- 2. ETL ---------------------------------------------------------------
STEP="ETL (data_ETL/${SOURCE_NAME}/etl.sh)"
echo "[2/7] ETL: data_ETL/${SOURCE_NAME}/etl.sh"
export TQDM_MININTERVAL=30   # keep the parser's progress bar from flooding the log
if ! bash "${SOURCE_DIR}/etl.sh" 2>&1 | tee "${OUT}/etl.log"; then
    fail "The source's etl.sh failed; see the log."
fi
grep -F '[MISSING]' "${OUT}/etl.log" | sed -e 's/^\[MISSING\] //' -e 's/ — please provide values$//' \
    > "${OUT}/missing.txt" || true
[[ -s "${OUT}/missing.txt" ]] && echo "      NOTE: the parser left some values blank (see missing.txt)"

UPLOAD_PATH="${SOURCE_DIR}/${UPLOAD_CSV}"
[[ -s "${UPLOAD_PATH}" ]] || fail "etl.sh finished but did not write ${UPLOAD_CSV}."

# --- 3. Date window -------------------------------------------------------
STEP="date window"
echo "[3/7] Date window: keeping collection weeks from ${CUTOFF:-the beginning (no cutoff)}"
FILTER_SUMMARY="$(python "${UPLOAD_DIR}/filter_rows.py" --input "${UPLOAD_PATH}" \
    --output "${OUT}/in_scope.csv" --min-start-date "${CUTOFF}" | tail -n1)"
echo "      ${FILTER_SUMMARY}"
IN_SCOPE="$(kv kept "${FILTER_SUMMARY}")"
setStatus IN_SCOPE "${IN_SCOPE}"
if [[ "${IN_SCOPE}" -eq 0 ]]; then
    fail "No records fall inside the date window (from ${CUTOFF}). The source feed may be stale."
fi

# --- 4. Portal snapshot -------------------------------------------------
STEP="portal snapshot"
echo "[4/7] Fetching what ${ORGANIZATION} already has published"
python "${UPLOAD_DIR}/fetch_published.py" --category "${CATEGORY}" \
    --organization "${ORGANIZATION}" --output "${OUT}/published.csv"

# --- 5. Diff --------------------------------------------------------------
STEP="diff"
echo "[5/7] Comparing against the published records"
DIFF_SUMMARY="$(python "${UPLOAD_DIR}/diff_new_records.py" --new "${OUT}/in_scope.csv" \
    --baseline "${OUT}/published.csv" --new-out "${OUT}/delta.csv" \
    --changed-out "${OUT}/changed.csv" | tail -n1)"
echo "      ${DIFF_SUMMARY}"
NEW="$(kv new "${DIFF_SUMMARY}")"
setStatus CHANGED "$(kv changed "${DIFF_SUMMARY}")"
setStatus UNCHANGED "$(kv unchanged "${DIFF_SUMMARY}")"

if (( HOLDOUT_WEEKS + HOLDOUT_RANDOM > 0 )); then
    STEP="test hold-back"
    echo "      TEST: holding back the newest ${HOLDOUT_WEEKS} week(s) and ${HOLDOUT_RANDOM} random older record(s)"
    HOLD_SUMMARY="$(python "${UPLOAD_DIR}/holdout_rows.py" --input "${OUT}/delta.csv" \
        --output "${OUT}/delta.kept.csv" --held-out "${OUT}/heldout.csv" \
        --latest-weeks "${HOLDOUT_WEEKS}" --random "${HOLDOUT_RANDOM}" | tail -n1)"
    mv "${OUT}/delta.kept.csv" "${OUT}/delta.csv"
    echo "      ${HOLD_SUMMARY} (held rows -> heldout.csv)"
    NEW="$(kv kept "${HOLD_SUMMARY}")"
    setStatus HELD_OUT "$(kv held "${HOLD_SUMMARY}")"
fi
setStatus NEW "${NEW}"

# --- 6. Guard -------------------------------------------------------------
STEP="size check"
if [[ "${NEW}" -eq 0 ]]; then
    echo "[6/7] Nothing new to upload."
    finish nothing_new 0
fi
if [[ "${NEW}" -gt "${MAX_NEW}" && "${FORCE}" -eq 0 ]]; then
    echo "[6/7] STOP: ${NEW} new records is more than MAX_NEW=${MAX_NEW}. Nothing uploaded."
    echo "      If this is expected (e.g. a first load), re-run with --force."
    finish guard 1
fi
echo "[6/7] ${NEW} new record(s) to upload$([[ "${FORCE}" -eq 1 && "${NEW}" -gt "${MAX_NEW}" ]] && echo " (over MAX_NEW, allowed by --force)")"

if [[ "${DRY_RUN}" -eq 1 ]]; then
    echo "[7/7] DRY RUN: stopping before the upload. Nothing was sent to the portal."
    echo "      The records that would be uploaded are in ${OUT#"${REPO_DIR}"/}/delta.csv"
    finish dry_run 0
fi

# --- 7. Upload + validate (never commits) --------------------------------
STEP="upload and validation"
echo "[7/7] Uploading and validating (this never publishes)"
rm -f "${OUT}/result.json"
set +e
python "${UPLOAD_DIR}/main.py" --input "${OUT}/delta.csv" --organization "${ORGANIZATION}" \
    --category "${CATEGORY}" --work-dir "${OUT}/submit" --result-json "${OUT}/result.json"
MAIN_RC=$?
set -e
[[ -f "${OUT}/result.json" ]] || fail "The upload stopped before validation finished (main.py exit ${MAIN_RC}); see the log."

read -r RESULT_ID RESULT_STATUS RESULT_URL RESULT_ERRORS < <(python -c '
import json, sys
d = json.load(open(sys.argv[1]))
print(d.get("submissionId") or "-", d.get("status") or "-", d.get("url") or "-",
      d.get("errors") if d.get("errors") is not None else "-")
' "${OUT}/result.json")
setStatus SUBMISSION_ID "${RESULT_ID}"
setStatus SUBMISSION_URL "${RESULT_URL}"
setStatus ERRORS "${RESULT_ERRORS}"

case "${RESULT_STATUS}" in
    VALID)   finish review 0 ;;
    INVALID) finish invalid 1 ;;
    BLOCKED_BY_OPEN_SUBMISSION)
        fail "A submission (${RESULT_ID}) was opened for ${ORGANIZATION} while this run was working; nothing was uploaded." ;;
    *)       fail "Validation ended with status ${RESULT_STATUS}." ;;
esac
