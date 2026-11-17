# Shared by run_initial_upload.sh, run_weekly_update.sh, close_submission.sh and list_sources.sh.
# Source this file, then call:
#
#   loadSourceConf <source folder> <dev|prod>
#
# It reads <source folder>/source.conf and sets, for that portal:
#   SOURCE_ID  ORGANIZATION  CATEGORY  UPLOAD_CSV  MAX_NEW  ENABLED  EDIT_REVISED  MAX_EDITS
#
# Each portal names a source's organization differently, so the organization is
# always given per portal: ORGANIZATION_DEV and ORGANIZATION_PROD. CATEGORY,
# MAX_NEW, ENABLED, EDIT_REVISED and MAX_EDITS can also be set per portal with a
# _DEV or _PROD suffix, which wins over the plain key on that portal. MAX_NEW,
# EDIT_REVISED and MAX_EDITS are left empty when not set, so the caller can use
# pipeline.conf's DEFAULT_... value.
#
#   checkSourceConf <source folder> <dev|prod>
#
# Prints what's missing for that portal and returns 1, or returns 0.

loadSourceConf() {
    local dir="$1" up="${2^^}" key override
    SOURCE_ID=""; CATEGORY=""; UPLOAD_CSV=""; MAX_NEW=""; ENABLED=1
    ORGANIZATION=""; ORGANIZATION_DEV=""; ORGANIZATION_PROD=""
    CATEGORY_DEV=""; CATEGORY_PROD=""; MAX_NEW_DEV=""; MAX_NEW_PROD=""
    ENABLED_DEV=""; ENABLED_PROD=""
    EDIT_REVISED=""; EDIT_REVISED_DEV=""; EDIT_REVISED_PROD=""
    MAX_EDITS=""; MAX_EDITS_DEV=""; MAX_EDITS_PROD=""
    # shellcheck disable=SC1091
    source "${dir}/source.conf"
    # The organization only comes from the portal's own key.
    override="ORGANIZATION_${up}"
    ORGANIZATION="${!override:-}"
    for key in CATEGORY MAX_NEW ENABLED EDIT_REVISED MAX_EDITS; do
        override="${key}_${up}"
        if [[ -n "${!override:-}" ]]; then printf -v "${key}" '%s' "${!override}"; fi
    done
}

checkSourceConf() {
    local dir="$1" up="${2^^}" ok=0
    [[ -n "${SOURCE_ID}" ]]  || { echo "ERROR: ${dir}/source.conf must set SOURCE_ID" >&2; ok=1; }
    [[ -n "${ORGANIZATION}" ]] || { echo "ERROR: ${dir}/source.conf must set ORGANIZATION_${up} (the organization on the ${2} portal)" >&2; ok=1; }
    [[ -n "${CATEGORY}" ]]   || { echo "ERROR: ${dir}/source.conf must set CATEGORY_${up} (or CATEGORY)" >&2; ok=1; }
    [[ -n "${UPLOAD_CSV}" ]] || { echo "ERROR: ${dir}/source.conf must set UPLOAD_CSV" >&2; ok=1; }
    return "${ok}"
}
