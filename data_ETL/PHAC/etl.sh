#!/usr/bin/env bash
#
# PHAC ETL: download the NWMP feed, convert it to the iMicroSeq schema, and
# remove duplicate sample IDs. Produces the file named by UPLOAD_CSV in
# source.conf. Run by run_source.sh, or on its own (with the ProjectIngestion
# conda env active):
#
#     bash data_ETL/PHAC/etl.sh
#
#   raw/wastewater_aggregate.csv     the feed as downloaded (overwritten each run)
#   curated/PHAC-NWMP.csv            parser.py output (one row per feed row)
#   curated/PHAC-NWMP.dedup.csv      one row per sample ID -> uploaded
#
# parser.py and dedup_records.py are used unchanged. See README.md here for
# what each one does.

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PHAC_URL="https://health-infobase.canada.ca/src/data/wastewater/wastewater_aggregate.csv"
RAW="${HERE}/raw/wastewater_aggregate.csv"
PARSED="${HERE}/curated/PHAC-NWMP.csv"
UPLOAD="${HERE}/curated/PHAC-NWMP.dedup.csv"

mkdir -p "${HERE}/raw" "${HERE}/curated"

echo "[etl 1/3] Downloading ${PHAC_URL}"
# Download to a temporary name first so a failed download never leaves a
# half-written file where the parser would read it.
curl -fSL --retry 3 --retry-delay 10 -o "${RAW}.part" "${PHAC_URL}"
mv "${RAW}.part" "${RAW}"
echo "          $(( $(wc -l < "${RAW}") - 1 )) data lines -> ${RAW}"

echo "[etl 2/3] Converting to the iMicroSeq schema (scripts/parser.py)"
python "${HERE}/scripts/parser.py" --input "${RAW}" --output "${PARSED}"

echo "[etl 3/3] Removing duplicate sample IDs (scripts/dedup_records.py)"
python "${HERE}/scripts/dedup_records.py" --input "${PARSED}" --output "${UPLOAD}"
echo "          Upload-ready file -> ${UPLOAD}"
