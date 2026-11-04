#!/usr/bin/env bash
#
# CHI ETL: download the Centre for Health Informatics' Alberta wastewater data
# (influenza A/B, RSV, and COVID) and convert it to the iMicroSeq schema.
# Produces the file named by UPLOAD_CSV in source.conf. Run by
# run_initial_upload.sh, or on its own (with the ProjectIngestion conda env active):
#
#     bash data_ETL/CHI/etl.sh
#
#   raw/rsvFlu.json                influenza A/B and RSV, every site (2022 on)
#   raw/aplWasteWaterAbData.json   COVID from July 2023
#   raw/wasteWaterAbData.json      COVID up to July 2023
#   curated/CHI.csv                parser.py output, one row per sample ID -> uploaded
#
# parser.py removes duplicates itself (see README.md here), so there's no
# separate dedupe step.

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASE_URL="https://chi-covid-data.pages.dev"
FILES=(rsvFlu.json aplWasteWaterAbData.json wasteWaterAbData.json)
UPLOAD="${HERE}/curated/CHI.csv"

mkdir -p "${HERE}/raw" "${HERE}/curated"

echo "[etl 1/2] Downloading from ${BASE_URL}"
for name in "${FILES[@]}"; do
    # Download to a temporary name first so a failed download never leaves a
    # half-written file where the parser would read it.
    curl -fSL --retry 3 --retry-delay 10 -o "${HERE}/raw/${name}.part" "${BASE_URL}/${name}"
    mv "${HERE}/raw/${name}.part" "${HERE}/raw/${name}"
    echo "          ${name}: $(wc -c < "${HERE}/raw/${name}") bytes"
done

echo "[etl 2/2] Converting to the iMicroSeq schema (scripts/parser.py)"
# Write to .part first, for the same reason as the downloads.
python "${HERE}/scripts/parser.py" \
    --rsvflu "${HERE}/raw/rsvFlu.json" \
    --covid "${HERE}/raw/aplWasteWaterAbData.json" \
    --covid-pre2023 "${HERE}/raw/wasteWaterAbData.json" \
    --output "${UPLOAD}.part"
mv "${UPLOAD}.part" "${UPLOAD}"
echo "          Upload-ready file -> ${UPLOAD}"
