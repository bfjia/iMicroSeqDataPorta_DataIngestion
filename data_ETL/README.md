# Data sources (ETL)

Each folder here is one data source. The pipeline (`run_initial_upload.sh` / `run_weekly_update.sh`) doesn't know
anything source-specific: it runs the folder's `etl.sh` and takes the CSV it produces. Everything
after that (date window, portal snapshot, diff, upload, notification) is the same for every
source.

| Folder | Source | Status |
|---|---|---|
| [`PHAC/`](PHAC/README.md) | PHAC National Wastewater Monitoring of Pathogens (Health Infobase) | enabled on prod; off on dev (`ENABLED_DEV=0`) |
| [`CHI/`](CHI/README.md) | Alberta wastewater: influenza A/B, RSV, COVID (Centre for Health Informatics, University of Calgary) | ETL ready; not enabled (no portal organization yet) |
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
| `ORGANIZATION_DEV`, `ORGANIZATION_PROD` | **Required.** The portal organization to submit as, one per portal, since each portal names it differently. It's the account's Ego scope `WW-<ORG>.WRITE` minus `WW-`, and case-sensitive. |
| `CATEGORY` | Portal category. The portals name it differently, so set `CATEGORY_DEV="imicroseq_wastewater"` and `CATEGORY_PROD="imicroseq_environmental"`. |
| `UPLOAD_CSV` | Path of the CSV `etl.sh` writes, relative to the source folder |
| `MAX_NEW` | Size guard: a run finding more new records than this stops without uploading (unless `--force`) |
| `ENABLED` | `1` = `run_weekly_update.sh` runs it, `0` = skipped |

`CATEGORY`, `MAX_NEW` and `ENABLED` can also be set per portal with a `_DEV` or `_PROD` suffix. The
suffixed key wins on that portal, e.g. `ENABLED_PROD=0` keeps a source on dev only. See every
source's values on both portals with `./list_sources.sh`. Add `--check` to also confirm that each
portal's account can write to the organization.

## Adding a new source

Follow **[docs/SOP_new_source.md](../docs/SOP_new_source.md)**. It goes from copying `_template/`
to weekly runs on dev and prod, with the checks to run at each step.
