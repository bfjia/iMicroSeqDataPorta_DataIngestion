# CHI: Alberta wastewater (Centre for Health Informatics, University of Calgary)

| | |
|---|---|
| **Publisher** | Centre for Health Informatics (CHI), Cumming School of Medicine, University of Calgary. Dashboard: https://covid-tracker.chi-csm.ca/ |
| **Files** | `rsvFlu.json`, `aplWasteWaterAbData.json`, `wasteWaterAbData.json`, all from https://chi-covid-data.pages.dev/ |
| **Updates** | Each file holds the whole history. Sites report one or two samples a week. |
| **One record** | One site × one sample date × one pathogen. For COVID, N1 and N2 are targets 1 and 2 of the same record. |
| **Pathogens** | influenza A (`inf_a`), influenza B (`inf_b`), RSV (`rsv`), SARS-CoV-2 (`covid`) |
| **Portal org** | Not set yet (`ORGANIZATION_DEV` / `ORGANIZATION_PROD` in `source.conf` are empty). Prod already has earlier CHI uploads under `AB_QPCR_CHI`; see "Status". |
| **Size** | 2026-11-04 files: 28,076 records (19,218 influenza/RSV, 8,858 COVID), 2020-05-18 to 2026-10-28. About 30 new records a week. |

## The ETL, step by step (`etl.sh`)

Run it on its own with `bash data_ETL/CHI/etl.sh` (with the `ProjectIngestion` env active). It
takes a few seconds.

### 1. Download

`curl` fetches the three files into `raw/`. It downloads to `.part` first, so a failed download
never leaves a half-written file behind, and it retries 3 times.

| File | What's in it | Shape |
|---|---|---|
| `rsvFlu.json` | influenza A/B and RSV, 23 sites, from 2022 | site → pathogen → date → `{v, sd}` (or `{}`) |
| `aplWasteWaterAbData.json` | COVID from July 2023, 10 sites | site → list of `{date, n1, n2, avg}` |
| `wasteWaterAbData.json` | COVID up to July 2023, 24 sites | list of `{date, location, n1_mean, n1_sd, n2_mean, n2_sd, data_type}` |

### 2. Convert (`scripts/parser.py`)

```bash
python scripts/parser.py --rsvflu raw/rsvFlu.json --covid raw/aplWasteWaterAbData.json \
    --covid-pre2023 raw/wasteWaterAbData.json --output curated/CHI.csv
```

This writes one iMicroSeq row (163 columns) per record, all three files into one CSV. The main
mappings:

| iMicroSeq field | Value |
|---|---|
| `specimen collector sample ID` | `{site}_{date}_{pathogen}`, e.g. `Banff_2024-07-17_covid`, `Bonnybrook Wastewater Treatment Plant_2022-01-03_inf_a` (see "Duplicates" below for `_1`, `_2`) |
| `sampling site ID` | the site name |
| `geo loc name (site)` / `(city)` | e.g. `Bonnybrook WWTP` / `Bonnybrook` (" Wastewater Treatment Plant" is shortened) |
| `geo loc name (state/province/territory)` | `Alberta [GAZ:00002566]` |
| `geo loc latitude` / `longitude` | `Not Provided [GENEPIO:0001668]` |
| `sample collection start date` | the sample date |
| `sample collection end date` | the sample date + 1 day; duration `24` `Hour [UO:0000032]` |
| `organism`, `target taxonomic name` | from the pathogen code, e.g. `rsv` → `Respiratory syncytial virus [NCBITaxon:12814]` |
| `sample collected by organisation name` | University of Alberta or University of Calgary, by site (`OrganisationDictionary`) |
| `specimen processing`, `nucleic acid extraction kit` | by organisation: Alberta filtration + MagMAX™; Calgary centrifugation + custom (McCalder et al. 2025) |
| `diagnostic measurement value` | influenza/RSV: `v`. COVID: N1 and N2 (`n1`/`n2`, or `n1_mean`/`n2_mean` before July 2023) |
| `diagnostic measurement unit` | influenza/RSV and COVID before July 2023: `copies per mililiter (C/ml) [GENEPIO:0102225]`. COVID from July 2023: **blank** (see below) |
| `diagnostic target presence` | `diagnostic target absent [GENEPIO:0100988]` when the value is 0, otherwise `present` |
| `data steward contact name` / `email`, `sample collection data steward name`, `authors` | Centre for Health Informatics, Cumming School of Medicine, University of Calgary / `chi@ucalgary.ca` |
| `citation URL` | `https://covid-tracker.chi-csm.ca/` |
| sequencing / host fields | `Not Applicable [GENEPIO:0001619]`, since this is PCR data and not sequencing |

The script itself is the full and authoritative mapping. Its input and output are not to be
changed without asking (see `CLAUDE.md`).

**Rules the converter applies** (all agreed with the data team on 2026-11-04):

- **Empty influenza/RSV entries (`{}`) mean "not detected"**: value `0`, target absent. They're
  about 60% of `rsvFlu.json` and follow the seasons (influenza B is empty most of the summer).
- **COVID from July 2023 is in copies per person.** The iMicroSeq unit list has no such term yet,
  so the unit is left blank. If the term is added later, records already published won't change by
  themselves; the weekly run only reports them as revised.
- **`wasteWaterAbData.json`**: only its `raw` rows are used (not `normalized`), and its `Calgary`
  rows are skipped (the three Calgary plants are listed separately).
- **July 2023 overlap.** Both COVID files have some site+dates in July 2023, in different units.
  The July-2023-on file (`aplWasteWaterAbData.json`) wins; the other file's copy is dropped.
- **Duplicates.** A record listed twice with identical values is kept once. Copies that differ are
  all kept, numbered in file order: `Calgary_2024-07-29_covid_1`, `Calgary_2024-07-29_covid_2`. On
  2026-11-04 that's 15 pairs (30 records). The numbers follow the file order, so if CHI removes or
  reorders one copy, the IDs shift and the records look new or revised.

**Unresolved values.** A site or pathogen code that isn't in the converter's lookups
(`OrganisationDictionary`, `OrganismDictionary`) stops the ETL with a `[MISSING]` line naming it.
Add it to the lookup and run again. Any other value the lookups can't resolve is left blank, with a
`[MISSING]` line in `msg.md`.

## Checking it

The three checks in [docs/SOP_new_source.md](../../docs/SOP_new_source.md), Step 6, all pass on
the 2026-11-04 files: the 163 columns match the live dev dictionary, there are no duplicate sample
IDs, and every picklist value is one the schema allows.

## Status

Not enabled (`ENABLED=0`). Next: the portal administrators create CHI's organization on dev and
prod and grant the tool's accounts `WW-<org>.WRITE`; then `source.conf` gets the two names, and
the new-source SOP continues at Step 7 (dry run on dev).

**Earlier uploads on prod.** Before this pipeline, CHI data was uploaded to prod with an earlier
version of the converter: 26,681 records under the organization `AB_QPCR_CHI`, sample dates up to
2025-12-18. Compared with today's converter (checked 2026-11-04, read only), with
`AB_QPCR_CHI` as `ORGANIZATION_PROD`:

| | Records | What a prod run would do |
|---|---|---|
| Pre-2023 COVID, IDs `<site>_<date>_sars-cov-2` on prod, `…_covid` today | 6,546 | upload them **again** under the new IDs |
| The 15 duplicate pairs: mostly one plain ID on prod, `_1`/`_2` today | 30 | upload both copies; one usually duplicates what's published |
| Influenza/RSV whose sample date moved by up to 3 days | 11 | upload again under the new date |
| Sample dates after 2025-12-18 | 1,447 | upload (these are new) |
| Same ID on both | 20,042 | report as revised every run, never re-upload. The earlier version had a contact email and coordinates, no null reasons, `C/ml` on post-2023 COVID, and some values CHI has since revised. |

Settle these with the data team before CHI runs on prod. A different prod organization isn't a
way around it: the pipeline would see nothing published there and upload all 28,076.
