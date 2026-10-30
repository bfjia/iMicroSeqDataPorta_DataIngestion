# Data sources (ETL)

Each folder here is one data source. The pipeline (`run_source.sh` / `run_weekly.sh`) doesn't know
anything source-specific: it runs the folder's `etl.sh` and takes the CSV it produces. Everything
after that (date window, portal snapshot, diff, upload, notification) is the same for every
source.

| Folder | Source | Status |
|---|---|---|
| [`PHAC/`](PHAC/README.md) | PHAC National Wastewater Monitoring of Pathogens (Health Infobase) | enabled |
| [`_template/`](_template/README.md) | copy-me skeleton | never run (folders starting with `_` are skipped) |

## The source contract

A source folder `data_ETL/<NAME>/` must contain:

| File | Required | Purpose |
|---|---|---|
| `source.conf` | yes | Settings, as plain bash assignments (see below) |
| `etl.sh` | yes | Fetches and converts the data. Takes no arguments. |
| `README.md` | yes | What the source is and how its ETL works, step by step |
| `scripts/` | usual | The source's converter (parser) and any clean-up scripts |
| `raw/`, `curated/` | usual | The downloaded and converted files. Their contents are gitignored, so keep a `.gitkeep`. |

**`etl.sh` must:**

1. take no arguments, and find its own folder with `HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"`;
2. write the file named by `UPLOAD_CSV`, a CSV whose columns are the iMicroSeq **titles** (the
   `title` column of `data_specification/fields.tsv`, e.g. `specimen collector sample ID`);
3. give that CSV **exactly one row per `specimen collector sample ID`**. If the source can repeat
   an ID, dedupe in `etl.sh`; the pipeline stops with an error on duplicates;
4. build sample IDs that are **stable from week to week**. The same record must get the same ID
   every run, or it gets re-uploaded as "new" (the size guard is there to catch this);
5. exit non-zero on any failure (`set -euo pipefail` at the top does this);
6. use only bash and Python, inside this repository's folder. Don't use system temp directories.

It may print freely, since its output goes to `etl.log`. A line starting with `[MISSING]` is
picked up and shown in `msg.md` as "values the parser could not resolve".

**`source.conf` keys:**

| Key | Meaning |
|---|---|
| `SOURCE_ID` | Short unique name used for run folders and in `msg.md`, e.g. `PHAC-NWMP` |
| `ORGANIZATION` | Portal organization to submit as. It is the account's Ego scope `WW-<ORG>.WRITE` minus `WW-`, and case-sensitive. |
| `CATEGORY` | Portal category. The portals name it differently, so set `CATEGORY_DEV="imicroseq_wastewater"` and `CATEGORY_PROD="imicroseq_environmental"`. |
| `UPLOAD_CSV` | Path of the CSV `etl.sh` writes, relative to the source folder |
| `MAX_NEW` | Size guard: a run finding more new records than this stops without uploading (unless `--force`) |
| `ENABLED` | `1` = `run_weekly.sh` runs it, `0` = skipped |

Any of `ORGANIZATION`, `CATEGORY`, `MAX_NEW` and `ENABLED` can be set per portal with a `_DEV` or
`_PROD` suffix. The suffixed key wins on that portal, e.g. `ENABLED_PROD=0` keeps a source on dev
only.

## Adding a new source, step by step

1. **Copy the template:**
   ```bash
   cp -r data_ETL/_template data_ETL/<NAME>
   ```
2. **Write the converter** in `data_ETL/<NAME>/scripts/`. Take `PHAC/scripts/parser.py` as the
   model: one explicit assignment per iMicroSeq field, with lookups as hardcoded dictionaries. Use
   iMicroSeq picklist values exactly as they appear in `data_specification/enums.tsv`, e.g.
   `Not Provided [GENEPIO:0001668]`. Print `[MISSING] …` for values it can't resolve, and leave
   them blank rather than guessing.
3. **Fill in `etl.sh`:** fetch → convert → dedupe, writing `UPLOAD_CSV`.
4. **Fill in `source.conf`.** Keep `ENABLED=0` for now.
5. **Run the ETL on its own** and check the output:
   ```bash
   conda activate ProjectIngestion
   bash data_ETL/<NAME>/etl.sh
   ```
   Check that the columns match the iMicroSeq titles (the upload step fails on any unknown column)
   and that the sample IDs are unique.
6. **Dry-run the whole pipeline** for it. This logs in and reads from the portal but uploads
   nothing:
   ```bash
   ./run_source.sh <NAME> --dry-run
   ```
   Read `msg.md` and `runs/<stamp>/<SOURCE_ID>/delta.csv`.
7. **First load:** agree it with the data owner, then run `./run_source.sh <NAME> --force`. A
   person reviews and **commits it on the website**. Do dev first. For prod, repeat with
   `--env prod`; prod has no date window, so its first load is the full history.
8. **Enable it:** set `ENABLED=1` so `run_weekly.sh` includes it, and add it to the table at the
   top of this file. `ENABLED_PROD=0` keeps it out of prod runs until it's ready there.
9. **Document it** in `data_ETL/<NAME>/README.md`, using `PHAC/README.md` as the model.
