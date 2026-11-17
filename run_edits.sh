#!/usr/bin/env bash
#
# Send edits for ONE source: published records that the source has revised
# since they were published. Nothing else: new records are left for the weekly
# run.
#
#   1 pending check   stop if a submission for the org is still open
#   2 ETL             fresh data from the source
#   3 date window     as for every run
#   4 portal snapshot what's published, with each record's system ID
#   5 diff            which published records the source has revised -> edits.csv
#   6 show            how many, which fields change, a few examples
#   7 ask, then send  type "yes" to stage the edits in a submission and validate it
#
# It NEVER publishes. A person reviews the edits (old -> new) and commits them on
# the portal website. Not limited by MAX_EDITS, since a person approves them.
# Needs a terminal, except with --dry-run. It's run_initial_upload.sh --edits-only.
#
#   ./run_edits.sh PHAC --dry-run          see what would be edited; sends nothing
#   ./run_edits.sh PHAC                    show the edits, ask, send
#   ./run_edits.sh CHI --env prod

set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

for arg in "$@"; do
    case "${arg}" in
        -h|--help)
            sed -n '2,22p' "$0" | sed 's/^# \{0,1\}//'
            echo
            echo "Options: --env dev|prod, --dry-run, --keep-work"
            exit 0 ;;
        --chunk|--force|--holdout-weeks|--holdout-random|--edits-only)
            echo "run_edits.sh only sends edits; '${arg}' isn't accepted here" >&2
            exit 2 ;;
    esac
done

exec "${REPO_DIR}/run_initial_upload.sh" "$@" --edits-only
