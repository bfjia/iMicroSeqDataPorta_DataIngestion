#!/usr/bin/env bash
#
# Upload ONE data source end to end. Use it for a source's first (initial)
# load, with --chunk when it's big, and for one-off runs of a single source.
# run_weekly_update.sh calls it for every enabled source each week.
#
#   1 pending check   stop if a submission for the org is still open (before any work)
#   2 ETL             data_ETL/<SOURCE>/etl.sh -> upload-ready CSV
#   3 date window     keep only weeks from <ENV>_MIN_START_DATE (pipeline.conf)
#   4 portal snapshot what the org already has published (and each record's system ID)
#   5 diff            new / changed / unchanged; changed (revised) records become edits
#   6 guard           stop if "new" (MAX_NEW) or the edits (MAX_EDITS) are suspiciously many
#   7 upload          upload + validate the new records and the edits, in ONE submission
#
# It NEVER publishes. A VALID upload is left open for a person to review and
# commit on the portal website. Every run writes a status for msg.md.
#
# --edits-only (what ./run_edits.sh runs) sends only the edits, after showing
# them and asking on the terminal; new records are left for the weekly run.
# docs/how_a_run_works.md explains each step in detail;
# docs/SOP_weekly_upload.md is the plain-language guide.
#
# The portal is dev or prod: --env, else PORTAL_ENV in pipeline.conf.
#
#   ./run_initial_upload.sh PHAC
#   ./run_initial_upload.sh PHAC --env prod --dry-run
#   ./run_initial_upload.sh PHAC --holdout-weeks 1 --keep-work
#   ./run_initial_upload.sh PHAC --env prod --chunk      first load, 10,000 at a time

set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
UPLOAD_DIR="${REPO_DIR}/upload_workflow"
ENV_NAME="ProjectIngestion"

usage() {
    cat <<'EOF'
Usage: ./run_initial_upload.sh <SOURCE> [options]

  <SOURCE>              folder name under data_ETL/, e.g. PHAC

Options:
  --env dev|prod        which portal (default: PORTAL_ENV in pipeline.conf)
  --dry-run             do every step except the upload: shows what WOULD be uploaded
  --force               upload even if there are more new records than MAX_NEW, or
                        more edits than MAX_EDITS
  --edits-only          send only the edits to published records the source has
                        revised (what ./run_edits.sh runs). Shows them and asks
                        first; needs a terminal. Not limited by MAX_EDITS.
  --holdout-weeks N     TEST ONLY: hold back the newest N weeks of new records
  --holdout-random N    TEST ONLY: also hold back N random older new records
  --keep-work           keep the bulky intermediate files in runs/
  --chunk               FIRST LOADS: upload in chunks of CHUNK_SIZE (pipeline.conf,
                        10,000), one submission each. Asks before every chunk;
                        the previous chunk must be committed on the website
                        first. Needs a terminal. Not limited by MAX_NEW.
  -h, --help            show this help

Uploads and validates only. Nothing is published until a person commits the
submission on the portal website.
EOF
}

# --- Arguments -----------------------------------------------------------
SOURCE_NAME=""
ENV_ARG=""
DRY_RUN=0
FORCE=0
HOLDOUT_WEEKS=0
HOLDOUT_RANDOM=0
KEEP_WORK=0
CHUNK=0
EDITS_ONLY=0
while [[ $# -gt 0 ]]; do
    case "$1" in
        --env)            [[ $# -ge 2 ]] || { echo "$1 needs a value" >&2; exit 2; }; ENV_ARG="$2"; shift ;;
        --dry-run)        DRY_RUN=1 ;;
        --force)          FORCE=1 ;;
        --edits-only)     EDITS_ONLY=1 ;;
        --holdout-weeks)  [[ $# -ge 2 ]] || { echo "$1 needs a value" >&2; exit 2; }; HOLDOUT_WEEKS="$2"; shift ;;
        --holdout-random) [[ $# -ge 2 ]] || { echo "$1 needs a value" >&2; exit 2; }; HOLDOUT_RANDOM="$2"; shift ;;
        --keep-work)      KEEP_WORK=1 ;;
        --chunk)          CHUNK=1 ;;
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
if [[ "${EDITS_ONLY}" -eq 1 ]] && (( CHUNK + FORCE + HOLDOUT_WEEKS + HOLDOUT_RANDOM > 0 )); then
    echo "--edits-only sends only edits: it can't be combined with --chunk, --force or --holdout-*" >&2
    exit 2
fi

SOURCE_DIR="${REPO_DIR}/data_ETL/${SOURCE_NAME}"
if [[ ! -f "${SOURCE_DIR}/source.conf" || ! -f "${SOURCE_DIR}/etl.sh" ]]; then
    echo "ERROR: ${SOURCE_DIR} needs a source.conf and an etl.sh (see data_ETL/README.md)" >&2
    exit 2
fi

# --- Configuration -------------------------------------------------------
PORTAL_ENV="dev"
DEV_MIN_START_DATE=""
PROD_MIN_START_DATE=""
DEFAULT_MAX_NEW=2000
DEFAULT_EDIT_REVISED=1
DEFAULT_MAX_EDITS=2000
CHUNK_SIZE=10000
SLACK_CHANNEL=""
# shellcheck source=pipeline.conf
source "${REPO_DIR}/pipeline.conf"

# Which portal: --env wins over pipeline.conf. Python reads $PORTAL_ENV.
PORTAL_ENV="${ENV_ARG:-${PORTAL_ENV}}"
case "${PORTAL_ENV}" in
    dev|prod) ;;
    *) echo "ERROR: the portal must be dev or prod (got '${PORTAL_ENV}')" >&2; exit 2 ;;
esac
export PORTAL_ENV
ENV_UPPER="${PORTAL_ENV^^}"

# The source's settings for this portal (organization, category, ...).
# shellcheck source=upload_workflow/load_source_conf.sh
source "${UPLOAD_DIR}/load_source_conf.sh"
loadSourceConf "${SOURCE_DIR}" "${PORTAL_ENV}"
checkSourceConf "${SOURCE_DIR}" "${PORTAL_ENV}" || exit 2
MAX_NEW="${MAX_NEW:-${DEFAULT_MAX_NEW}}"
EDIT_REVISED="${EDIT_REVISED:-${DEFAULT_EDIT_REVISED}}"
MAX_EDITS="${MAX_EDITS:-${DEFAULT_MAX_EDITS}}"
[[ "${EDIT_REVISED}" == 0 || "${EDIT_REVISED}" == 1 ]] \
    || { echo "ERROR: EDIT_REVISED must be 0 or 1 (got '${EDIT_REVISED}')" >&2; exit 2; }
[[ "${MAX_EDITS}" =~ ^[0-9]+$ ]] \
    || { echo "ERROR: MAX_EDITS must be a whole number (got '${MAX_EDITS}')" >&2; exit 2; }
cutoffVar="${ENV_UPPER}_MIN_START_DATE"
CUTOFF="${!cutoffVar:-}"

if [[ "${EDITS_ONLY}" -eq 1 && "${DRY_RUN}" -eq 0 && ! -t 0 ]]; then
    echo "ERROR: --edits-only asks before sending the edits, so it has to be run from a terminal" >&2
    exit 2
fi
if [[ "${CHUNK}" -eq 1 ]]; then
    [[ "${CHUNK_SIZE}" =~ ^[1-9][0-9]*$ ]] \
        || { echo "ERROR: CHUNK_SIZE in pipeline.conf must be a whole number (got '${CHUNK_SIZE}')" >&2; exit 2; }
    if [[ "${DRY_RUN}" -eq 0 && ! -t 0 ]]; then
        echo "ERROR: --chunk asks before every chunk, so it has to be run from a terminal" >&2
        exit 2
    fi
fi

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
# run_weekly_update.sh sets INGEST_RUN_DIR and already holds the lock. Run on its own,
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
        rm -rf "${OUT}/in_scope.csv" "${OUT}/published.csv" "${OUT}/published_ids.csv" \
            "${OUT}/submit" "${OUT}/chunks"
    fi
    echo "== ${SOURCE_ID}: finished with status '$(grep '^STATUS=' "${STATUS_FILE}" | tail -n1 | cut -d= -f2)' (log: ${LOG#"${REPO_DIR}"/})"
    if [[ "${STANDALONE}" -eq 1 ]]; then
        python "${UPLOAD_DIR}/notify.py" --run-dir "${INGEST_RUN_DIR}" \
            --out "${INGEST_RUN_DIR}/msg.md" --copy-to "${REPO_DIR}/msg.md" > /dev/null \
            && echo "== Notification written to msg.md"
        # Slack: once per run, never for a dry run (run_weekly_update.sh does the same)
        if [[ -n "${SLACK_CHANNEL}" && "${DRY_RUN}" -eq 0 ]]; then
            python "${UPLOAD_DIR}/slack_post.py" --file "${INGEST_RUN_DIR}/msg.md" \
                --channel "${SLACK_CHANNEL}" \
                || echo "WARNING: msg.md was written but could not be posted to Slack (error above)"
        fi
    fi
    exit "${code}"
}
trap onExit EXIT

setStatus SOURCE_ID "${SOURCE_ID}"
setStatus SOURCE_NAME "${SOURCE_NAME}"
setStatus PORTAL_ENV "${PORTAL_ENV}"
setStatus ORGANIZATION "${ORGANIZATION}"
setStatus LOG "${LOG}"
setStatus CUTOFF "${CUTOFF}"
setStatus MAX_NEW "${MAX_NEW}"
setStatus EDIT_REVISED "${EDIT_REVISED}"
setStatus MAX_EDITS "${MAX_EDITS}"
setStatus EDITS_ONLY "${EDITS_ONLY}"

echo "== ${SOURCE_ID}: run started $(date '+%Y-%m-%d %H:%M:%S') on ${ENV_UPPER}"
echo "   portal ${PORTAL_ENV}, organization ${ORGANIZATION}, category ${CATEGORY}, date window from ${CUTOFF:-the beginning}"
(( HOLDOUT_WEEKS + HOLDOUT_RANDOM > 0 )) && echo "   TEST MODE: holding back records (--holdout-*)"
(( DRY_RUN )) && echo "   DRY RUN: every step except the upload"
(( CHUNK )) && echo "   CHUNKED: up to ${CHUNK_SIZE} records per submission, confirmed one at a time"
if (( EDITS_ONLY )); then
    echo "   EDITS ONLY: sends edits to revised published records, after asking; no new records"
elif (( EDIT_REVISED )); then
    echo "   Revised published records are sent as edits (up to MAX_EDITS=${MAX_EDITS})"
fi

# --- 1. Pending check, before any actual work ---------------------------
STEP="login"
echo "[1/7] Pending check"
echo "      Logging in to the ${PORTAL_ENV} portal"
PORTAL_TOKEN="$(python "${UPLOAD_DIR}/step1_token.py")" \
    || fail "Could not log in to the ${PORTAL_ENV} portal. Check ${PORTAL_ENV}PortalUser and ${PORTAL_ENV}PortalPass in upload_workflow/.env."
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
    echo "      Stopping before any work. Commit it on the website, or close it with"
    echo "      ./close_submission.sh ${SOURCE_NAME} --env ${PORTAL_ENV}:"
    echo "        ${PENDING_URL}"
    if [[ "${PENDING_STATUS}" == "INVALID" ]]; then
        finish waiting_invalid 1
    fi
    finish waiting 0
fi
echo "      No open submission for ${ORGANIZATION}."

STEP="permission check"
if [[ "${WRITE_SCOPE}" != 1 ]]; then
    NO_SCOPE="The ${PORTAL_ENV} portal account has no write permission for ${ORGANIZATION} (it needs the scope WW-${ORGANIZATION}.WRITE). Ask the portal administrators to grant it."
    if [[ "${DRY_RUN}" -eq 1 ]]; then
        # A dry run uploads nothing, so carry on and show what would be uploaded.
        echo "      WARNING: ${NO_SCOPE} A real run would stop here."
        setStatus NO_WRITE_SCOPE 1
    else
        fail "${NO_SCOPE}"
    fi
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
    --organization "${ORGANIZATION}" --output "${OUT}/published.csv" \
    --ids-out "${OUT}/published_ids.csv"

# --- 5. Diff --------------------------------------------------------------
STEP="diff"
echo "[5/7] Comparing against the published records"
DIFF_SUMMARY="$(python "${UPLOAD_DIR}/diff_new_records.py" --new "${OUT}/in_scope.csv" \
    --baseline "${OUT}/published.csv" --new-out "${OUT}/delta.csv" \
    --changed-out "${OUT}/changed.csv" | tail -n1)"
echo "      ${DIFF_SUMMARY}"
NEW="$(kv new "${DIFF_SUMMARY}")"
CHANGED="$(kv changed "${DIFF_SUMMARY}")"
setStatus CHANGED "${CHANGED}"
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

# Revised records -> edits. They're already published, but the source has
# changed them since; each edit carries the record's system ID and replaces it.
EDITS=0
if [[ "${CHANGED}" -gt 0 ]]; then
    if [[ "${CHUNK}" -eq 1 ]]; then
        echo "      ${CHANGED} published record(s) were revised; --chunk doesn't send edits."
        echo "      Send them afterwards with ./run_edits.sh ${SOURCE_NAME} --env ${PORTAL_ENV}"
    elif [[ "${EDIT_REVISED}" -eq 1 || "${EDITS_ONLY}" -eq 1 ]]; then
        STEP="edits"
        echo "      Edits for the ${CHANGED} revised record(s). Fields that change:"
        EDITS_OUT="$(python "${UPLOAD_DIR}/build_edits.py" --changed "${OUT}/changed.csv" \
            --ids "${OUT}/published_ids.csv" --published "${OUT}/published.csv" \
            --output "${OUT}/edits.csv" --fields-out "${OUT}/edit_fields.csv")" \
            || fail "Could not build the edits for the revised records; see the log."
        sed '$d' <<< "${EDITS_OUT}"
        EDITS="$(kv edits "$(tail -n1 <<< "${EDITS_OUT}")")"
    fi
fi
setStatus EDITS "${EDITS}"

# --- 6. Guard -------------------------------------------------------------
STEP="size check"
if [[ "${EDITS_ONLY}" -eq 1 ]]; then
    # A person approves the edits below, so MAX_EDITS doesn't apply.
    if [[ "${EDITS}" -eq 0 ]]; then
        echo "[6/7] No published records need editing."
        finish nothing_to_edit 0
    fi
    echo "[6/7] ${EDITS} published record(s) to edit, e.g. $(python -c '
import csv, sys
ids = [r["specimen collector sample ID"] for r in csv.DictReader(open(sys.argv[1], encoding="utf-8"))]
print(", ".join(ids[:5]) + (", ..." if len(ids) > 5 else ""))
' "${OUT}/edits.csv")"
    if [[ "${NEW}" -gt 0 ]]; then
        echo "      ${NEW} new record(s) are not sent here; the weekly run uploads them."
    fi
elif [[ "${NEW}" -eq 0 && "${EDITS}" -eq 0 ]]; then
    echo "[6/7] Nothing new to upload$([[ "${EDIT_REVISED}" -eq 1 ]] && echo ", and nothing to edit")."
    finish nothing_new 0
elif [[ "${CHUNK}" -eq 1 ]]; then
    # Chunks are confirmed one by one by a person, so MAX_NEW doesn't apply.
    STEP="chunk split"
    CHUNK_DIR="${OUT}/chunks"
    CHUNK_OUT="$(python "${UPLOAD_DIR}/chunk_rows.py" --input "${OUT}/delta.csv" \
        --size "${CHUNK_SIZE}" --out-dir "${CHUNK_DIR}")"
    CHUNK_LINES=(); while IFS= read -r line; do [[ "${line}" == chunk=* ]] && CHUNK_LINES+=("${line}"); done <<< "${CHUNK_OUT}"
    CHUNK_COUNT="$(kv chunks "$(tail -n1 <<< "${CHUNK_OUT}")")"
    setStatus CHUNK_TOTAL "${CHUNK_COUNT}"
    setStatus CHUNK_SIZE "${CHUNK_SIZE}"
    echo "[6/7] ${NEW} new record(s) in ${CHUNK_COUNT} chunk(s) of up to ${CHUNK_SIZE}, oldest first:"
    for line in "${CHUNK_LINES[@]}"; do
        echo "        chunk $(kv chunk "${line}"): $(kv rows "${line}") records, weeks $(kv first "${line}") to $(kv last "${line}")"
    done
elif [[ "${NEW}" -gt "${MAX_NEW}" && "${FORCE}" -eq 0 ]]; then
    echo "[6/7] STOP: ${NEW} new records is more than MAX_NEW=${MAX_NEW}. Nothing uploaded."
    echo "      If this is expected (e.g. a first load), re-run with --force, or --chunk."
    finish guard 1
elif [[ "${EDITS}" -gt "${MAX_EDITS}" && "${FORCE}" -eq 0 ]]; then
    echo "[6/7] ERROR: ${EDITS} published records were revised at the source, more than"
    echo "      MAX_EDITS=${MAX_EDITS}. That many changes isn't expected. Nothing uploaded."
    echo "      See what changed in ${OUT#"${REPO_DIR}"/}/edit_fields.csv and edits.csv."
    echo "      If it's expected, send them with ./run_edits.sh ${SOURCE_NAME} --env ${PORTAL_ENV},"
    echo "      or re-run with --force."
    finish edit_guard 1
else
    MSG="[6/7] ${NEW} new record(s)"
    [[ "${EDITS}" -gt 0 ]] && MSG+=" and ${EDITS} edit(s)"
    MSG+=" to upload"
    [[ "${FORCE}" -eq 1 && "${NEW}" -gt "${MAX_NEW}" ]] && MSG+=" (new records over MAX_NEW, allowed by --force)"
    [[ "${FORCE}" -eq 1 && "${EDITS}" -gt "${MAX_EDITS}" ]] && MSG+=" (edits over MAX_EDITS, allowed by --force)"
    echo "${MSG}"
fi

if [[ "${DRY_RUN}" -eq 1 ]]; then
    echo "[7/7] DRY RUN: stopping before the upload. Nothing was sent to the portal."
    if [[ "${EDITS_ONLY}" -eq 0 && "${NEW}" -gt 0 ]]; then
        echo "      The new records that would be uploaded are in ${OUT#"${REPO_DIR}"/}/delta.csv"
    fi
    if [[ "${EDITS}" -gt 0 ]]; then
        echo "      The edits that would be sent are in ${OUT#"${REPO_DIR}"/}/edits.csv (what changes: edit_fields.csv)"
    fi
    finish dry_run 0
fi

# --- 7. Upload + validate (never commits) --------------------------------
freshToken() {   # tokens expire (3 h on dev), and a chunked load or a prompt can wait longer
    PORTAL_TOKEN="$(python "${UPLOAD_DIR}/step1_token.py")" \
        || fail "Could not log in to the ${PORTAL_ENV} portal again."
    export PORTAL_TOKEN
}

# uploadOne <new-records csv, or ""> <work dir> <timeout seconds> [<edits csv>]
# Uploads the new records and/or the edits into one submission and waits for
# validation. Sets RESULT_ID, RESULT_STATUS, RESULT_URL and RESULT_ERRORS.
uploadOne() {
    local inputs=()
    if [[ -n "$1" ]]; then inputs+=(--input "$1"); fi
    if [[ -n "${4:-}" ]]; then inputs+=(--edits "$4"); fi
    rm -f "${OUT}/result.json"
    set +e
    python "${UPLOAD_DIR}/main.py" "${inputs[@]}" --organization "${ORGANIZATION}" \
        --category "${CATEGORY}" --work-dir "$2" --result-json "${OUT}/result.json" --timeout "$3"
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
        VALID)   ;;
        INVALID) finish invalid 1 ;;
        BLOCKED_BY_OPEN_SUBMISSION)
            fail "A submission (${RESULT_ID}) was opened for ${ORGANIZATION} while this run was working; nothing was uploaded." ;;
        INCOMPLETE_SUBMISSION)
            fail "Submission ${RESULT_ID} holds fewer records than this run sent (the portal didn't stage all of them). Don't commit it: close it with ./close_submission.sh ${SOURCE_NAME} --env ${PORTAL_ENV} and run again." ;;
        SPLIT_SUBMISSION)
            fail "The new records and the edits went into different submissions. Review both on the website before committing either (see the log)." ;;
        *)       fail "Validation ended with status ${RESULT_STATUS}." ;;
    esac
}

if [[ "${CHUNK}" -eq 0 ]]; then
    NEW_FILE=""; EDITS_FILE=""; TIMEOUT=600
    if [[ "${EDITS_ONLY}" -eq 0 && "${NEW}" -gt 0 ]]; then NEW_FILE="${OUT}/delta.csv"; fi
    if [[ "${EDITS}" -gt 0 ]]; then EDITS_FILE="${OUT}/edits.csv"; TIMEOUT=1800; fi
    if [[ "${EDITS_ONLY}" -eq 1 ]]; then
        STEP="confirmation"
        TIMEOUT=3600
        echo
        while true; do
            printf '      Send these %s edit(s) to %s on the %s portal? Type yes, or stop: ' \
                "${EDITS}" "${ORGANIZATION}" "${PORTAL_ENV}"
            answer=""
            read -r answer || answer="stop"
            echo
            case "${answer,,}" in
                yes)  break ;;
                stop) echo "      Stopped. Nothing was sent; the edits are in ${OUT#"${REPO_DIR}"/}/edits.csv"
                      finish cancelled 0 ;;
                *)    echo "      Please type yes or stop." ;;
            esac
        done
        freshToken   # the question may have waited a long time
    fi
    STEP="upload and validation"
    echo "[7/7] Uploading and validating (this never publishes)"
    uploadOne "${NEW_FILE}" "${OUT}/submit" "${TIMEOUT}" "${EDITS_FILE}"
    finish review 0
fi

# --- 7 (chunked). One submission per chunk, a person confirms each ---------
openSubmission() {   # sets OPEN_ID / OPEN_STATUS (empty = nothing open). Never in $(...):
    local out key value  # a failed check must stop the run, not read as "nothing open"
    OPEN_ID=""; OPEN_STATUS=""
    out="$(python "${UPLOAD_DIR}/check_pending.py" --category "${CATEGORY}" --organization "${ORGANIZATION}")" \
        || fail "Could not check the portal for open submissions, so stopped rather than risk a duplicate upload."
    while IFS='=' read -r key value; do
        case "${key}" in PENDING_ID) OPEN_ID="${value}" ;; PENDING_STATUS) OPEN_STATUS="${value}" ;; esac
    done <<< "${out}"
}
stopChunks() {   # stopChunks <chunks uploaded so far>
    echo "      Stopped. ${1} of ${CHUNK_COUNT} chunk(s) uploaded; run again with --chunk to continue."
    freshToken
    if [[ "$1" -gt 0 ]]; then
        openSubmission
        if [[ -n "${OPEN_ID}" ]]; then finish review 0; fi   # the last chunk still waits for its commit
    fi
    finish paused 0
}

STEP="chunked upload"
echo "[7/7] Chunked upload to the ${PORTAL_ENV} portal: ${CHUNK_COUNT} submission(s), one at a time (this never publishes)"
LEFT="${NEW}"
setStatus CHUNK_DONE 0
setStatus CHUNK_LEFT "${LEFT}"
for ((i = 1; i <= CHUNK_COUNT; i++)); do
    line="${CHUNK_LINES[$((i - 1))]}"
    rows="$(kv rows "${line}")"; first="$(kv first "${line}")"; last="$(kv last "${line}")"
    while true; do
        echo
        if (( i > 1 )); then
            echo "      Chunk $((i - 1)) is submission ${RESULT_ID}. Commit it on the website before the next one:"
            echo "        ${RESULT_URL}"
        fi
        printf '      Upload chunk %s of %s (%s records, weeks %s to %s)? Type yes, or stop: ' \
            "${i}" "${CHUNK_COUNT}" "${rows}" "${first}" "${last}"
        answer=""
        read -r answer || answer="stop"
        echo
        case "${answer,,}" in
            yes)
                freshToken
                if (( i > 1 )); then
                    openSubmission
                    if [[ -n "${OPEN_ID}" ]]; then
                        echo "      Submission ${OPEN_ID} is still open (${OPEN_STATUS}). Commit it on the website first."
                        continue
                    fi
                fi
                break ;;
            stop) stopChunks $((i - 1)) ;;
            *)    echo "      Please type yes or stop." ;;
        esac
    done

    echo "      --- chunk ${i} of ${CHUNK_COUNT}: ${rows} records, weeks ${first} to ${last}"
    setStatus CHUNK_NUMBER "${i}"
    setStatus CHUNK_ROWS "${rows}"
    setStatus CHUNK_FIRST "${first}"
    setStatus CHUNK_LAST "${last}"
    uploadOne "$(kv file "${line}")" "${OUT}/submit/chunk_${i}" 3600
    LEFT=$((LEFT - rows))
    setStatus CHUNK_DONE "${i}"
    setStatus CHUNK_LEFT "${LEFT}"
    echo "      Chunk ${i} of ${CHUNK_COUNT} is VALID: submission ${RESULT_ID}. ${LEFT} record(s) left to upload."
done
echo
echo "      All ${CHUNK_COUNT} chunk(s) uploaded. Commit the last one on the website:"
echo "        ${RESULT_URL}"
finish review 0
