# PHAC: National Wastewater Monitoring of Pathogens (NWMP)

| | |
|---|---|
| **Publisher** | Public Health Agency of Canada, on Health Infobase (https://health-infobase.canada.ca/wastewater/) |
| **Feed** | https://health-infobase.canada.ca/src/data/wastewater/wastewater_aggregate.csv |
| **Updates** | Weekly. The whole history is republished each time, and recent weeks may be revised. |
| **One input row** | One location × one week × one target: the weekly average viral concentration (`w_avg`) |
| **Targets** | `covN2` (SARS-CoV-2), `fluA`, `fluB`, `rsv` |
| **Portal org** | `PHAC-AUTOINGEST` on dev, `PHAC-NWMP` on prod; category `imicroseq_wastewater` on dev, `imicroseq_environmental` on prod (see `source.conf`) |
| **Size** | 2026-10-30 feed: 63,291 rows → 51,224 unique records. About 210–220 new records per complete week. |

## The ETL, step by step (`etl.sh`)

Run it on its own with `bash data_ETL/PHAC/etl.sh` (with the `ProjectIngestion` env active).

### 1. Download

`curl` fetches the feed into `raw/wastewater_aggregate.csv`. It downloads to `.part` first, so a
failed download never leaves a half-written file behind, and it retries 3 times.

Feed columns: `Location, site, city, province, country, EpiYear, EpiWeek, weekstart, measureid,
w_avg, min, max, populationcoverage, pruid`.

### 2. Convert (`scripts/parser.py`)

```bash
python scripts/parser.py --input raw/wastewater_aggregate.csv --output curated/PHAC-NWMP.csv
```

This writes one iMicroSeq row (163 columns) per feed row. The main mappings:

| iMicroSeq field | Value |
|---|---|
| `specimen collector sample ID` | `PHAC_{weekstart}_{Location}_{measureid}`, e.g. `PHAC_2026-10-18_Assiniboia_covN2` |
| `sampling site ID` | `Location` |
| `geo loc name (site)` / `(city)` | `site` / `city` |
| `geo loc name (state/province/territory)` | `province` → GAZ term. Blank (multi-province aggregate) → `Not Applicable [GENEPIO:0001619]`. |
| `geo loc name (country)` | `Canada [GAZ:00002560]` |
| `geo loc latitude` / `longitude` | City geocoded via OpenStreetMap Nominatim, e.g. `51.05000 N`, `114.07000 W`. Cached in `scripts/geocode_cache.json`. |
| `sample collection start date` | `weekstart` (a Sunday) |
| `sample collection end date` | `weekstart` + 6 days (the Saturday) |
| `sample collection time duration` | `1` `Week [UO:0000034]` |
| `organism`, `target taxonomic name 1` | from `measureid`: e.g. `covN2` → `Severe acute respiratory syndrome coronavirus 2 [NCBITaxon:2697049]` |
| `assay target name 1` | `measureid` |
| `diagnostic measurement value 1` | `w_avg`, in `copies per mililiter (C/ml) [GENEPIO:0102225]`, measured by qPCR |
| `specimen processing` | `Pooling specimens [OBI:0600016]` (it's a weekly average) |
| `environmental site` / `material` | Wastewater treatment plant / Wastewater |
| `purpose of sampling` | `Wastewater pathogen surveillance [GENEPIO:0100872]` |
| `assay type` | `Reverse transcription polymerase chain reaction assay [OBI:0001170]` |
| sequencing / host fields | `Not Applicable [GENEPIO:0001619]`, since this is PCR data and not sequencing |
| `data steward contact name` / `email` | Public Health Agency of Canada / `nmlwastewater@phac-aspc.gc.ca.` |
| `citation URL` | `https://health-infobase.canada.ca/wastewater/` |

The script itself is the full and authoritative mapping. Its maintainer edits it by hand, and its
input and output are not to be changed without asking (see `CLAUDE.md`).

**Unresolved values.** An unknown `measureid` or province is filled with
`Not Provided [GENEPIO:0001668]`. A city that can't be geocoded gets blank coordinates. Either way
the parser prints a line at the end:

```
[MISSING] coordinates: ['Somewhere, Yukon'] — please provide values
```

The pipeline shows these in `msg.md` as an FYI. To fix one, add the value to the parser's
dictionary, or to `scripts/geocode_cache.json` for coordinates, by hand. Don't guess. The geocode
cache is tracked in git; commit it when it changes.

### 3. Dedupe (`scripts/dedup_records.py`)

```bash
python scripts/dedup_records.py --input curated/PHAC-NWMP.csv --output curated/PHAC-NWMP.dedup.csv
```

PHAC ships every measurement **twice**: once with `site` filled in and once with `site` blank. The
sample ID is built from `Location`, not `site`, so both copies get the same ID. That is about 12k
rows a week. The two copies are otherwise identical, apart from float rounding. The script keeps
the row with a non-blank `geo loc name (site)` and preserves the original order.

`curated/PHAC-NWMP.dedup.csv` is the upload-ready file (`UPLOAD_CSV` in `source.conf`).

## Files

| Path | Tracked in git? | Contents |
|---|---|---|
| `source.conf` | yes | source settings |
| `etl.sh` | yes | the three steps above |
| `scripts/parser.py` | yes | PHAC → iMicroSeq converter |
| `scripts/dedup_records.py` | yes | site-blank duplicate removal |
| `scripts/geocode_cache.json` | yes | city → coordinates cache, updated by the parser |
| `raw/wastewater_aggregate.csv` | no | latest download (~8 MB) |
| `curated/PHAC-NWMP.csv` | no | latest parser output (~160 MB) |
| `curated/PHAC-NWMP.dedup.csv` | no | latest upload-ready file (~130 MB) |

## Notes

- **Recent weeks are partial.** The newest week usually has fewer records than a complete week,
  e.g. 155 vs ~215, and its values may be revised later. Records that arrive later are picked up
  as new on later runs. Revised values of already-published records show up as "changed" FYIs and
  are not re-uploaded.
- **Dev window.** Dev only receives weeks from `DEV_MIN_START_DATE` (2026-09-01) on. That is
  1,437 records (7 weeks) in the 2026-10-30 feed.
- **Prod gets the full history** (`PROD_MIN_START_DATE` is empty): 51,224 records in the
  2026-10-30 feed. Nothing has been uploaded to prod yet. The first load is over the 2,000 size
  guard, and an old empty submission (233) has to be closed first.
