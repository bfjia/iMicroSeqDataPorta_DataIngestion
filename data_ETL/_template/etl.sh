#!/usr/bin/env bash
#
# TEMPLATE ETL. Contract (see data_ETL/README.md):
#   * takes no arguments; may use raw/ and curated/ next to this file;
#   * writes the file named by UPLOAD_CSV in source.conf;
#   * that file uses the iMicroSeq column titles (data_specification/fields.tsv,
#     "title" column) and has exactly one row per "specimen collector sample ID";
#   * exits non-zero on any failure (set -e does this for you).
#
#     bash data_ETL/<NAME>/etl.sh

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
mkdir -p "${HERE}/raw" "${HERE}/curated"

# 1. Fetch the source data into raw/.
# curl -fSL --retry 3 -o "${HERE}/raw/TODO.part" "https://TODO" && mv "${HERE}/raw/TODO.part" "${HERE}/raw/TODO"

# 2. Convert it to the iMicroSeq schema.
# python "${HERE}/scripts/TODO_parser.py" --input "${HERE}/raw/TODO" --output "${HERE}/curated/TODO.csv"

# 3. Make sure every sample ID appears once (if the source can repeat them).

echo "TODO: implement data_ETL/$(basename "${HERE}")/etl.sh" >&2
exit 1
