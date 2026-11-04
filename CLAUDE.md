# CLAUDE.md

Guidance for Claude Code (and any other contributor) working in this repository.

## What this is

A weekly pipeline that takes external wastewater surveillance data, converts it to the iMicroSeq
data standard (`data_specification/`), and **uploads and validates** it on the data portal. A
person then reviews and **commits** each submission on the portal website. Sources are plug-in
folders under `data_ETL/`. PHAC (NWMP) is the first one.

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
   - **Nothing has been uploaded to prod.** Don't upload or close anything on prod without the
     owner's explicit go-ahead for that specific action. Reads and `--dry-run` are fine.
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
run_weekly.sh          scheduler entry point: every enabled source, then one msg.md
run_source.sh          one source: pending check -> ETL -> date window -> snapshot -> diff -> guard -> upload+validate
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

## Running

```bash
conda activate ProjectIngestion
./run_source.sh PHAC --dry-run      # safe: everything except the upload
./run_weekly.sh --dry-run
./run_weekly.sh --env prod --dry-run   # the same against prod (reads only)
bash data_ETL/PHAC/etl.sh           # ETL only
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
- **Uploading to an open submission appends to it**, so the same records get staged twice
  (`INVALID_BY_UNIQUE`). The pending check exists for this reason.
- **Sample IDs must be unique against published data**, not just within the file.
- **CSV headers are renamed from the live dictionary** (`displayName` → `name`), never hardcoded.
- **The portal stores** list fields as JSON arrays (each field declares its delimiter, `;`) and
  integers as numbers, and drops empty fields. `fetch_published.py` renders them back to CSV text.
- Reads (`/data/...`, `/dictionary/...`, `/category`) need no token. Writes do, and so does the
  per-user submission listing.

## Prod: what's still open

- Submission 233 (`PHAC-NWMP`, prod) is an old empty `OPEN` submission from 2026-07-14. It
  blocks prod runs until the owner closes it (or OKs closing it).
- The first prod load is the full history (51,224 PHAC records). That's over `MAX_NEW`, so it
  needs `--force`, and may need chunked uploads. It's untested.
- Commits stay manual on the website.
