# CLAUDE.md

Guidance for Claude Code (and any other contributor) working in this repository.

## What this is

A weekly pipeline that takes external wastewater surveillance data, converts it to the iMicroSeq
data standard (`data_specification/`), and **uploads and validates** it on the data portal. A
person then reviews and **commits** each submission on the portal website. Sources are plug-in
folders under `data_ETL/`. PHAC (NWMP) is the first one; CHI (Alberta, University of Calgary) has
its ETL ready but no portal organization yet.

- Docs live in `docs/`: `SOP_weekly_upload.md` and `SOP_new_source.md` (plain-language
  procedures), `how_a_run_works.md` and `configuration.md` (technical). `README.md` stays short and
  non-technical: what the tool is, links, quick start.
- Repo: https://github.com/bfjia/iMicroSeqDataPorta_DataIngestion. Push to `main`.

## Rules (from the project owner, all mandatory)

1. **Never commit/publish to the portal.** Not in code, not while testing, not by any workaround.
   - Commits are done by a person on the portal website, in dev and prod.
   - The pipeline only uploads and validates. `upload_workflow/main.py` has no commit path, and
     `step7_commit.py` was deliberately not carried over; don't add either back.
   - **Ask before every upload, and before closing (discarding) any submission**, on dev or
     prod, while developing or testing. `--dry-run` is the safe way to exercise the pipeline.
   - Closing an open submission is the operator's call (`close_submission.sh`). It never touches
     published records.
   - "Commit" here means publishing on the portal. Git commits and pushes are separate and fine.
2. **Two portals: dev and prod.** Dev is `dev.virusseq-dataportal.ca`; prod is
   `imicroseq-dataportal.ca` (since 2026-10-30). Don't contact any other portal host.
   - Dev stays the default (`PORTAL_ENV="dev"` in `pipeline.conf`). Prod only via `--env prod`.
   - Hosts live only in `upload_workflow/portal_env.py`; scripts read `$PORTAL_ENV`.
   - **Prod holds real, published data** (PHAC's full history, and earlier CHI uploads). Don't
     upload or close anything on prod without the owner's explicit go-ahead for that specific
     action. Reads and `--dry-run` are fine.
3. **Stay inside this folder.** Ask before using any temp directory, `/tmp` included. Working files
   go in `runs/`.
4. **Use the conda env `ProjectIngestion`** (`environment.yaml`). Keep `environment.yaml` and
   `requirements.txt` in step when dependencies change.
5. **Bash and Python only.** If something can't be done that way, say so first.
6. **Don't change the input/output of curation scripts** (`data_ETL/*/scripts/`, e.g. PHAC
   `parser.py`, `dedup_records.py`) without asking first. Their maintainer edits them by hand:
   keep diffs minimal and the existing style, hardcode mappings rather than parsing mapping
   files at runtime, and ask rather than invent values the parser can't resolve.
7. **Never commit secrets or data to git.** `upload_workflow/.env`, `runs/`, `msg.md`,
   `data_ETL/*/raw|curated/*` and `old/` are gitignored. Check `git status` before every commit.
8. **`old/` is read-only.** It is the original workflow, kept as a reference. Copy from it, never
   edit it.
9. **Keep the docs in step with the code.** Any behaviour change updates the matching files in
   `docs/` (`how_a_run_works.md` / `configuration.md` for the technical side, the SOPs for the
   plain-language side) and the relevant folder README, in the same change. Keep `README.md` short.

## Layout

```
docs/                  SOPs (weekly upload, new source) + technical guides (how a run works, configuration)
.github/workflows/     weekly_ingestion.yml: Monday REAL prod run (manual: prod, dry run by default)
                       dev_test.yml: manual-only test uploads to dev (one source or ALL-ENABLED)
run_weekly_update.sh   scheduler entry point: every enabled source, then one msg.md
run_initial_upload.sh  one source: pending check -> ETL -> window -> snapshot -> diff -> guard -> upload new + edits (--chunk: first loads)
run_edits.sh           one source, edits only: shows the revised published records, asks, sends them (run_initial_upload.sh --edits-only)
close_submission.sh    discard a source's open submission (asks for its number) so a new one can start
list_sources.sh        each source's organization/category per portal; --check logs in and checks WRITE
pipeline.conf          PORTAL_ENV (default portal), DEV_/PROD_MIN_START_DATE, DEFAULT_MAX_NEW, SLACK_CHANNEL
data_ETL/<SOURCE>/     source.conf + etl.sh (+ scripts/, raw/, curated/)
data_ETL/_template/    copy-me skeleton for a new source
upload_workflow/       portal API scripts (step1-6, main.py) + pipeline helpers
runs/<stamp>/          per-run logs and working files (gitignored)
msg.md                 latest notification digest, posted to Slack if SLACK_CHANNEL is set (gitignored)
data_specification/    iMicroSeq fields.tsv / enums.tsv
old/                   original workflow (read-only, gitignored)
```

## Source contract

`data_ETL/<NAME>/etl.sh` takes no arguments and writes `UPLOAD_CSV` (named in `source.conf`).
`source.conf` must name the organization **per portal** (`ORGANIZATION_DEV`, `ORGANIZATION_PROD`);
each portal names it differently. `upload_workflow/load_source_conf.sh` is the one loader.
That CSV has the iMicroSeq column titles and **exactly one row per `specimen collector sample ID`**.
Deduping is the source's job; `diff_new_records.py` hard-errors on duplicates. Details are in
`data_ETL/README.md`.

## How "new" is decided

There is no local ledger. Commits happen on the website, so the pipeline can't know when something
is published. Each run downloads the org's published records from the portal
(`fetch_published.py`) and diffs today's data against them. A run first checks for an open
submission (`check_pending.py`, which needs a token: the listing is per logged-in user). If one
exists, the run stops before doing any work and reminds the person to commit or fix it.

Records that are published but whose values the source has changed since ("changed") are sent as
**edits** in the same submission as the new records (`build_edits.py` → `main.py --edits`), unless
the source sets `EDIT_REVISED=0`. More than `MAX_EDITS` stops the run with an error
(`edit_guard`). Edits, like new records, change nothing until a person commits on the website.

## Running

```bash
conda activate ProjectIngestion
./run_initial_upload.sh PHAC --dry-run          # safe: everything except the upload
./run_weekly_update.sh --dry-run
./run_weekly_update.sh --env prod --dry-run     # the same against prod (reads only)
./run_initial_upload.sh PHAC --env prod --chunk # first load in chunks (asks before each)
./run_edits.sh PHAC --dry-run                   # edits only: what would be edited (asks before sending)
bash data_ETL/PHAC/etl.sh                       # ETL only
```

## Portal gotchas (Overture Lyric 0.3.0, dev and prod)

- **The portals differ in names, not schema.** Prod's submission host is `submissions.`, not
  `submission-service.`. Its category is `imicroseq_environmental` (id 1); dev's is
  `imicroseq_wastewater` (id 3). The dictionary is the same: v1.17, 163 fields. Sources set
  `CATEGORY_DEV` / `CATEGORY_PROD`.
- **Each portal has its own account** in `.env` (`devPortalUser`… / `prodPortalUser`…), with its
  own scopes and its own organization names. PHAC is `PHAC-AUTOINGEST` on dev, `PHAC-NWMP` on prod
  (`WW-PHAC-NWMP.WRITE` granted 2026-11-03).

- **Organization = Ego scope minus `WW-`.** Scope `WW-PHAC-AUTOINGEST.WRITE` → org
  `PHAC-AUTOINGEST`. It is case-sensitive. A wrong org gives a generic 403. Tokens are snapshots:
  mint a fresh one after a permission change (`python upload_workflow/step1_token.py --scopes`).
- **`GET /submission/{id}` is a server-sent event stream**, not JSON, and is held open while
  validating. Use `common.apiGetEvent`.
- **Edits:** `PUT /submission/category/{id}/data` with `files` (named `sample.csv`) and
  `organization`. Each row has a `systemId` column plus every field; an edit replaces the whole
  record. Staged as `updates` in the open submission; the website shows old → new and commits
  them like new records. Confirmed on dev 2026-11-05 (461: edits alone; 463: 223 new + 69 edits).
  **Send edits only after the new records have validated:** edits sent while the submission is
  still validating are answered `PROCESSING` and then silently dropped. Added to an open
  submission, the PUT reply has no `submissionId`. `main.py` waits, then checks the staged counts.
  A website upload closes the user's own open submission first (the API appends instead).
- **Uploading to an open submission appends to it**, so the same records get staged twice
  (`INVALID_BY_UNIQUE`). The pending check exists for this reason.
- **Sample IDs must be unique against published data**, not just within the file.
- **CSV headers are renamed from the live dictionary** (`displayName` → `name`), never hardcoded.
- **The portal stores** list fields as JSON arrays (each field declares its delimiter, `;`) and
  integers as numbers, and drops empty fields. `fetch_published.py` renders them back to CSV text.
- Reads (`/data/...`, `/dictionary/...`, `/category`) need no token. Writes do, and so does the
  per-user submission listing.

## Prod: what's still open

- PHAC's first prod load is done: all 51,224 records published under `PHAC-NWMP` (by 2026-11-04,
  with `--chunk`).
- **CHI on prod:** prod already holds 26,681 CHI records under `AB_QPCR_CHI`, uploaded before this
  pipeline with `abparser.py`. `data_ETL/CHI/scripts/parser.py` is that script adapted, with the
  same sample IDs (pre-2023 COVID ends `_sars-cov-2`), so a prod run adds only new records (~1,490
  on 2026-11-04). The improvements agreed since (null reasons, "Banff WWTP") mean every existing
  record is reported as revised on each run, by the owner's choice. See `data_ETL/CHI/README.md`,
  including its two known issues (CHI recalculates COVID values; new copies cause duplicate uploads).
- **Edits on prod:** on by default, as on dev (`DEFAULT_EDIT_REVISED=1`). Prod dry runs on
  2026-11-05 (reads only) found PHAC-NWMP 0 new and 69 edits, matched to prod's own system IDs.
  No edit has been sent to prod yet; the first goes with the next prod run
  (`./run_weekly_update.sh --env prod`, or `./run_edits.sh PHAC --env prod`, which asks first),
  which is the first scheduled GitHub Actions run if nobody runs it before.
- Commits stay manual on the website.

## GitHub Actions (the weekly scheduler)

- `.github/workflows/weekly_ingestion.yml` runs `run_weekly_update.sh --env prod` every Monday
  (16:30 UTC). The owner chose real prod uploads on 2026-11-17. "Run workflow" by hand is prod
  too, defaulting to dry run. The YAML only starts the script; keep the logic in Bash/Python
  (rule 5).
- `.github/workflows/dev_test.yml` is manual-only and always dev. It uploads by default, with
  holdout/force inputs. Each workflow maps only its own portal's secrets, so a dev test can't
  reach prod. A new source must be added to its `source` choice list.
- **The repo is public, so Actions logs are public.** Secrets go in the `portal` environment
  (main branch only) and in `env:` on the run step only. Never print a credential, never upload
  `runs/` as an artifact, never add `pull_request_target`, and pin actions to commit SHAs.
  `maskToken` in `run_initial_upload.sh` masks the minted portal JWT through `ACTIONS_LOG_FD`,
  bypassing the tee so the mask line never reaches `run.log` / `msg.md`.
- Don't trigger a live (non-dry) workflow run yourself; rules 1 and 2 apply as everywhere else.
- Only one scheduler: no local crontab or Task Scheduler while the GitHub schedule is on.
