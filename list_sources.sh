#!/usr/bin/env bash
#
# Show every data source's settings on both portals: whether it's enabled,
# which organization it submits as and into which category. The values come
# from each data_ETL/<SOURCE>/source.conf (ORGANIZATION_DEV, ORGANIZATION_PROD, ...).
#
#   ./list_sources.sh           the table, read from the config files only
#   ./list_sources.sh --check   also log in to each portal and check that its
#                               account can write to each organization
#
# Uploads nothing. Exit code 1 if a source is missing a setting, or (with
# --check) an enabled source's account can't write to its organization.

set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_NAME="ProjectIngestion"
PORTALS=(dev prod)

CHECK=0
case "${1:-}" in
    "")        ;;
    --check)   CHECK=1 ;;
    -h|--help) sed -n '2,12p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *)         echo "Unknown option: $1 (accepted: --check)" >&2; exit 2 ;;
esac

# shellcheck source=upload_workflow/load_source_conf.sh
source "${REPO_DIR}/upload_workflow/load_source_conf.sh"

# --- With --check: one login per portal, keep its scopes -------------------
declare -A SCOPES=()
if [[ "${CHECK}" -eq 1 ]]; then
    if [[ "${CONDA_DEFAULT_ENV:-}" != "${ENV_NAME}" ]]; then
        conda="${CONDA_EXE:-}"
        [[ -x "${conda}" ]] || conda="${HOME}/miniconda3/bin/conda"
        set +u; eval "$("${conda}" shell.bash hook)"; conda activate "${ENV_NAME}"; set -u
    fi
    for portal in "${PORTALS[@]}"; do
        if ! SCOPES[${portal}]="$(PORTAL_ENV="${portal}" python "${REPO_DIR}/upload_workflow/step1_token.py" --scopes 2>/dev/null)"; then
            SCOPES[${portal}]="LOGIN_FAILED"
            echo "WARNING: could not log in to ${portal} (check ${portal}PortalUser / ${portal}PortalPass in upload_workflow/.env)" >&2
        fi
    done
fi

canWrite() {   # canWrite <portal> <org> -> yes / NO / login failed
    local scopes="${SCOPES[$1]}"
    if [[ "${scopes}" == LOGIN_FAILED ]]; then echo "login failed"; return; fi
    if grep -qF "\"WW-$2.WRITE\"" <<< "${scopes}" || grep -qF "\"$2.WRITE\"" <<< "${scopes}"; then
        echo "yes"
    else
        echo "NO"
    fi
}

# --- The table -----------------------------------------------------------
PROBLEM=0
format="%-10s %-12s %-6s %-8s %-20s %-25s"
header=(SOURCE ID PORTAL ENABLED ORGANIZATION CATEGORY)
if [[ "${CHECK}" -eq 1 ]]; then format+=" %s"; header+=(CAN_WRITE); fi
# shellcheck disable=SC2059
printf "${format}\n" "${header[@]}"

for dir in "${REPO_DIR}"/data_ETL/*/; do
    dir="${dir%/}"
    name="$(basename "${dir}")"
    [[ "${name}" == _* || ! -f "${dir}/source.conf" ]] && continue
    for portal in "${PORTALS[@]}"; do
        loadSourceConf "${dir}" "${portal}"
        enabled="no"; [[ "${ENABLED}" == 1 ]] && enabled="yes"
        if ! checkSourceConf "${dir}" "${portal}" 2>/dev/null; then
            PROBLEM=1
        fi
        row=("${name}" "${SOURCE_ID:-?}" "${portal}" "${enabled}" "${ORGANIZATION:-(not set)}" "${CATEGORY:-(not set)}")
        if [[ "${CHECK}" -eq 1 ]]; then
            write="-"
            if [[ -n "${ORGANIZATION}" ]]; then write="$(canWrite "${portal}" "${ORGANIZATION}")"; fi
            [[ "${enabled}" == yes && "${write}" != yes ]] && PROBLEM=1
            row+=("${write}")
        fi
        # shellcheck disable=SC2059
        printf "${format}\n" "${row[@]}"
    done
done

if [[ "${PROBLEM}" -eq 1 ]]; then
    echo
    echo "Something needs attention: a setting is missing (see data_ETL/<SOURCE>/source.conf)"
    [[ "${CHECK}" -eq 1 ]] && echo "or an enabled source's account can't write to its organization (ask the portal admins)."
fi
exit "${PROBLEM}"
