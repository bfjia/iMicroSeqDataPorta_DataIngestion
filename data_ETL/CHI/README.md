# CHI: Alberta wastewater (Centre for Health Informatics, University of Calgary)

| | |
|---|---|
| **Publisher** | Centre for Health Informatics (CHI), Cumming School of Medicine, University of Calgary. Dashboard: https://covid-tracker.chi-csm.ca/ |
| **Files** | `rsvFlu.json`, `aplWasteWaterAbData.json`, `wasteWaterAbData.json`, all from https://chi-covid-data.pages.dev/ |
| **Updates** | Each file holds the whole history. Sites report one or two samples a week. |
| **One record** | One site × one sample date × one pathogen. For COVID, N1 and N2 are targets 1 and 2 of the same record. |
| **Pathogens** | influenza A (`inf_a`), influenza B (`inf_b`), RSV (`rsv`), SARS-CoV-2 (`covid`; `sars-cov-2` in pre-2023 IDs) |
| **Portal org** | Not set yet (`ORGANIZATION_DEV` / `ORGANIZATION_PROD` in `source.conf` are empty). Prod already holds CHI's earlier uploads under `AB_QPCR_CHI`; see "Status". |
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

`parser.py` is the data team's `abparser.py` (the version used for the earlier prod uploads),
adapted for this pipeline: command-line paths, one output CSV, the rules below, and the 163 columns.

```bash
python scripts/parser.py --rsvflu raw/rsvFlu.json --covid raw/aplWasteWaterAbData.json \
    --covid-pre2023 raw/wasteWaterAbData.json --output curated/CHI.csv
```

This writes one iMicroSeq row (163 columns) per record, all three files into one CSV. The main
mappings:

| iMicroSeq field | Value |
|---|---|
| `specimen collector sample ID` | `{site}_{date}_{pathogen}`, e.g. `Banff_2024-07-17_covid`, `Bonnybrook Wastewater Treatment Plant_2022-01-03_inf_a`. Pre-2023 COVID ends `_sars-cov-2` instead, e.g. `Edmonton_2020-05-18_sars-cov-2`, as on prod. See "Duplicates" below for `_1`, `_2`. |
| `sampling site ID` | the site name |
| `geo loc name (site)` / `(city)` | e.g. `Bonnybrook WWTP` / `Bonnybrook` (" Wastewater Treatment Plant" is shortened) |
| `geo loc name (state/province/territory)` | `Alberta [GAZ:00002566]` |
| `geo loc latitude` / `longitude` | one fixed point per city (`LatDictionary` / `LonDictionary`), e.g. Edmonton `53.51974439 N` / `113.4962173 W`; the Calgary city series `51.0447 N` / `114.0719 W` |
| `sample collection start date` | the sample date |
| `sample collection end date` | the sample date + 1 day; duration `24` `Hour [UO:0000032]` |
| `organism`, `target taxonomic name` | from the pathogen code, e.g. `rsv` → `Respiratory syncytial virus [NCBITaxon:12814]` |
| `sample collected by organisation name` / `contact email` | University of Alberta or University of Calgary, by site (`OrganisationDictionary`) / `paula.acostaamador@ucalgary.ca` |
| `specimen processing`, `nucleic acid extraction kit` | by organisation: Alberta filtration + MagMAX™; Calgary centrifugation + custom (McCalder et al. 2025) |
| `specimen processing details` | the organisation's concentration method. COVID from July 2023 adds: "Note: the diagnostic measurement values have been normalized to the population (copies per person)." |
| `diagnostic measurement value` | influenza/RSV: `v`. COVID: N1 and N2 (`n1`/`n2`, or `n1_mean`/`n2_mean` before July 2023) |
| `diagnostic measurement unit` | `copies per mililiter (C/ml) [GENEPIO:0102225]` for every record |
| `diagnostic target presence` | `diagnostic target absent [GENEPIO:0100988]` when the value is 0, otherwise `present` |
| `data steward contact name` / `email`, `sample collection data steward name` | Centre for Health Informatics, Cumming School of Medicine, University of Calgary / `chi@ucalgary.ca` |
| `authors` | CHI, the Pan-Alberta WBS Network and its leads (the full text is in the script) |
| `citation URL` | `https://covid-tracker.chi-csm.ca/` |
| sequencing / host fields | `Not Applicable [GENEPIO:0001619]`, since this is PCR data and not sequencing |

The script itself is the full and authoritative mapping. Its input and output are not to be
changed without asking (see `CLAUDE.md`).

**Rules the converter applies** (all agreed with the data team on 2026-11-04):

- **Empty influenza/RSV entries (`{}`) mean "not detected"**: value `0`, target absent. They're
  about 60% of `rsvFlu.json` and follow the seasons (influenza B is empty most of the summer).
- **Every value is labelled copies per mL**, COVID from July 2023 included (agreed 2026-11-04,
  and the same as the earlier prod uploads). COVID from July 2023 is really copies per person; the
  iMicroSeq unit list has no such term, so those records say so in `specimen processing details`.
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

**Earlier uploads on prod.** Before this pipeline, CHI data was uploaded to prod with
`abparser.py`: 26,681 records under the organization `AB_QPCR_CHI`, sample dates up to
2025-12-18. Compared with today's converter (checked 2026-11-04, read only), with `AB_QPCR_CHI` as
`ORGANIZATION_PROD`, a prod run would:

| | Records | What happens |
|---|---|---|
| Sample dates after 2025-12-18 | 1,447 | uploaded (new) |
| The 15 duplicate pairs, as `_1`/`_2` | 30 | uploaded. 13 pairs are on prod once already, under the plain ID (the last copy), so one of each pair repeats a published record. |
| Influenza/RSV whose sample date CHI has moved by up to 3 days | 11 | uploaded under the new date; the old date stays on prod |
| Same ID on both | 26,588 | sent as edits to the published records. That's more than `MAX_EDITS` (2,000), so a normal run stops with an error; send them once with `./run_edits.sh CHI --env prod` (it asks first). All of them differ in the improvements made since: `sample collection data steward name`, three null-reason fields, and `Banff WWTP` (prod: `BanffWWTP`); the 1,936 post-2023 COVID records also in the `specimen processing details` note. 1,857 also have values CHI has since revised. |
| On prod but not in today's file | 93 | left alone: mostly the 60 pre-2023 July 2023 copies (the post-2023 file wins) and the plain IDs of the duplicate pairs |

Once those edits are committed, the earlier records carry the same values as new ones, and
weekly runs only send what CHI changes. (The hand-made files in `runs/chi-prod-sync/` from
2026-11-04 aren't needed any more: `run_edits.sh` builds the same edits from fresh data.)

## Known issues (not fixed yet)

Both were found on 2026-11-04 while preparing to bring the earlier prod records in line. They're
left as they are for now.

1. **CHI recalculates its post-2023 COVID values.** These are per-person (normalized) values, and
   CHI revises them across the whole history, not just recent weeks. Between the morning and
   midday of 2026-11-04, 1,795 records already on prod (dated 2023-07-02 to 2025-12-16) changed
   slightly, e.g. `Banff_2023-07-03_covid` N1 0.0478 → 0.0477.
   - Weekly runs now send these as edits (since 2026-11-05), so prod follows CHI's values. Each
     recalculation means a submission with many edits to review.
   - About 1,800 at once is close to `MAX_EDITS` (2,000). A bigger recalculation stops the run
     with an error; send it with `./run_edits.sh CHI`, or raise `MAX_EDITS` in `source.conf`.
2. **A new copy of an already-published record causes a duplicate upload.** The duplicates rule
   numbers every differing copy (`_1`, `_2`). When CHI adds a second copy for a site and date that
   is already on prod under the plain ID, the plain ID disappears from `CHI.csv` and both copies
   are uploaded as new, so one of them repeats the published record.
   - Seen on 2026-11-04 for `Calgary_2025-07-28_covid` and `Calgary_2025-11-17_covid`.
   - A possible fix: the published copy keeps its plain ID and only additional copies are
     numbered.
