# Commands, settings, portals and scheduling

Reference for running the pipeline: every command and option, the settings files, the two portals
(dev and prod), and how to schedule the weekly run. What each step does is in
[how_a_run_works.md](how_a_run_works.md). The plain-language procedures are
[SOP_weekly_upload.md](SOP_weekly_upload.md) and [SOP_new_source.md](SOP_new_source.md).

## Commands and options

```
./run_initial_upload.sh <SOURCE> [--env dev|prod] [--dry-run] [--force] [--chunk] [--holdout-weeks N] [--holdout-random N] [--keep-work]
./run_edits.sh <SOURCE> [--env dev|prod] [--dry-run] [--keep-work]
./run_weekly_update.sh [--env dev|prod] [--dry-run]
./close_submission.sh <SOURCE> [--env dev|prod] [--yes]
./list_sources.sh [--check]
```

| Option | Effect |
|---|---|
| `--env dev\|prod` | Which portal. Without it, `PORTAL_ENV` in `pipeline.conf` (dev). |
| `--dry-run` | Every step except the upload. It still logs in and reads from the portal. |
| `--force` | Upload even if new > `MAX_NEW` or edits > `MAX_EDITS` (first loads, known backfills) |
| `--edits-only` | Send only the edits, after showing them and asking. What `run_edits.sh` runs; not combined with `--chunk`, `--force` or `--holdout-*`. |
| `--chunk` | **First loads.** Upload in chunks of `CHUNK_SIZE` (10,000), one submission each, and ask before every chunk. Not limited by `MAX_NEW`. Needs a terminal. See below. |
| `--holdout-weeks N` / `--holdout-random N` | TEST ONLY: hold back rows to create a delta for the next run |
| `--keep-work` | Keep `in_scope.csv`, `published.csv` and `submit/` |

`run_initial_upload.sh` runs one source. Use it for a source's first load and for one-off runs.
`run_weekly_update.sh` calls it for every enabled source. Each run sends the new records **and**
edits for published records the source has revised, in one submission (unless the source sets
`EDIT_REVISED=0`).

**`run_edits.sh`** sends only the edits: published records whose values the source has changed.
It runs the usual pending check, ETL, window, snapshot and comparison, then shows how many records
change, which fields, and a few sample IDs, and asks: type `yes` to send, `stop` to end with
nothing sent. Needs a terminal (except `--dry-run`). Not limited by `MAX_EDITS`, because a person
approves. New records are left for the weekly run. It's `run_initial_upload.sh --edits-only`.

```bash
./run_edits.sh PHAC --dry-run   # what would be edited; sends nothing
./run_edits.sh PHAC             # show, ask, send
```

**`--chunk`** splits a big first load into submissions of at most `CHUNK_SIZE` records:

- **Order:** the new records are sorted oldest first, after any `--holdout-*` hold-back, so
  held-back records are never in a chunk.
- **One at a time:** before each chunk the script shows its size and weeks and asks `yes` or
  `stop`. From the second chunk on, it checks with the portal that the previous chunk has been
  committed on the website. If it's still open, it says so and asks again.
- **Resumable:** `stop` (or Ctrl+D) ends the run. Running `--chunk` again carries on with what
  isn't published yet, because the comparison with the portal leaves out committed chunks.
- **Long sessions:** each chunk gets a fresh login (dev tokens last 3 hours) and up to an hour to
  validate.
- **Problems:** a chunk that fails validation stops the run (`invalid`). Fix the cause, close it
  (`close_submission.sh`) and run `--chunk` again.

```bash
./run_initial_upload.sh PHAC --env prod --chunk --dry-run   # show the chunk plan
./run_initial_upload.sh PHAC --env prod --chunk             # upload, one confirmed chunk at a time
```

`run_weekly_update.sh` runs every folder in `data_ETL/` that has a `source.conf` with `ENABLED=1` (or
`ENABLED_DEV` / `ENABLED_PROD` for that portal).
Folders starting with `_` are skipped. A failing source doesn't stop the others. Its exit code is 1
if any source ended 🔴. Only one run can happen at a time (`runs/.lock`).

`close_submission.sh` discards the source's open submission (`DELETE /submission/{id}`) so the
next run can upload a new one. Use it after an INVALID upload whose cause is fixed, or when the
data has to be redone. The portal website has no way to close a submission yet, so this is the
only way short of `main.py --replace`.

- **What it touches:** only the open, uncommitted submission. Published records are untouched,
  and it never commits.
- **Confirmation:** it shows the submission and asks you to type its number. `--yes` skips that.
  Without a terminal and without `--yes`, it refuses.
- **Lock:** it takes `runs/.lock`, so it can't run during a pipeline run.
- **Where the logic lives:** `upload_workflow/close_submission.py`, which reuses
  `step5_upload.closeSubmission`.

## Settings

**`pipeline.conf`** (applies to every source):

| Key | Default | Meaning |
|---|---|---|
| `PORTAL_ENV` | `dev` | Portal used when no `--env` is given, including by the scheduler: `dev` or `prod` |
| `DEV_MIN_START_DATE` | `2026-09-01` | Dev: only weeks on or after this date are uploaded. `""` = no cutoff. |
| `PROD_MIN_START_DATE` | `""` | Prod: the same, empty = full history |
| `DEFAULT_MAX_NEW` | `2500` | Size guard for sources that don't set `MAX_NEW` |
| `DEFAULT_EDIT_REVISED` | `1` | `1` = send revised published records as edits, in the same submission as the new records; `0` = only report them |
| `DEFAULT_MAX_EDITS` | `2000` | Edit guard for sources that don't set `MAX_EDITS`: more revised records than this stops the run with an error (`edit_guard`) |
| `CHUNK_SIZE` | `10000` | Most records per submission with `--chunk` |
| `SLACK_CHANNEL` | `C0CDQRKNWFK` | Slack channel ID that gets `msg.md` after each run (#_integration_notifications). `""` = don't post. |

**`data_ETL/<SOURCE>/source.conf`**:

| Key | Example (PHAC) | Meaning |
|---|---|---|
| `SOURCE_ID` | `PHAC-NWMP` | Name used for run folders and messages |
| `ORGANIZATION_DEV` / `ORGANIZATION_PROD` | `PHAC-AUTOINGEST` / `PHAC-NWMP` | **Required, per portal.** The organization the source submits as: the account's Ego scope `WW-<ORG>.WRITE` minus `WW-`. Every portal names it differently, so there's no shared `ORGANIZATION`. |
| `CATEGORY_DEV` / `CATEGORY_PROD` | `imicroseq_wastewater` / `imicroseq_environmental` | Portal category. The two portals name it differently (same dictionary). |
| `UPLOAD_CSV` | `curated/PHAC-NWMP.dedup.csv` | What `etl.sh` writes, relative to the source folder |
| `MAX_NEW` | `500` | Size guard |
| `ENABLED` | `1`, with `ENABLED_DEV=0` (PHAC is off on dev) | `0` = `run_weekly_update.sh` skips the source |
| `EDIT_REVISED` | not set (uses `DEFAULT_EDIT_REVISED`, 1) | `0` = this source doesn't send edits; revised records are only reported |
| `MAX_EDITS` | not set (uses `DEFAULT_MAX_EDITS`, 2,000) | Edit guard for this source |

`CATEGORY`, `MAX_NEW`, `ENABLED`, `EDIT_REVISED` and `MAX_EDITS` can also be given per portal with a `_DEV` or `_PROD` suffix.
The suffixed key wins on that portal, e.g. `ENABLED_PROD=0` keeps a new source on dev only.
`upload_workflow/load_source_conf.sh` applies these rules for every script.

`./list_sources.sh` prints the whole mapping, every source on both portals.
`./list_sources.sh --check` also logs in to each portal and shows whether its account can write to
each organization:

```
SOURCE     ID           PORTAL ENABLED  ORGANIZATION         CATEGORY                  CAN_WRITE
PHAC       PHAC-NWMP    dev    yes      PHAC-AUTOINGEST      imicroseq_wastewater      yes
PHAC       PHAC-NWMP    prod   yes      PHAC-NWMP            imicroseq_environmental   yes
```

**`upload_workflow/.env`** (never committed): one login per portal, `devPortalUser` /
`devPortalPass` and `prodPortalUser` / `prodPortalPass`, and `duoliauthtoken`, the Slack bot's
OAuth token (only needed when `SLACK_CHANNEL` is set). `.env.example` shows the format.

## Dev and prod

The portal is chosen per run: `--env dev|prod`, else `PORTAL_ENV` in `pipeline.conf` (`dev`). The
bash scripts export it as `$PORTAL_ENV`, and every Python script reads it through
`upload_workflow/portal_env.py`, the one place the hosts live. To run a Python script on its own
against prod: `PORTAL_ENV=prod python upload_workflow/check_pending.py --organization …`.

| | dev | prod |
|---|---|---|
| Website | `dev.virusseq-dataportal.ca` | `imicroseq-dataportal.ca` |
| Submission service | `submission-service.dev.virusseq-dataportal.ca` | `submissions.imicroseq-dataportal.ca` |
| Login | `ego.dev…` → `keycloak.dev…` | `ego.imicroseq-dataportal.ca` → `keycloak.imicroseq-dataportal.ca` |
| Category | `imicroseq_wastewater` (id 3) | `imicroseq_environmental` (id 1) |
| Dictionary | `imicroseq_wastewater` v1.17, 163 fields | identical (checked 2026-10-30) |
| Account (`.env`) | `devPortalUser` / `devPortalPass` | `prodPortalUser` / `prodPortalPass` |
| Date window | from 2026-09-01 | full history |
| Review link | `https://dev.virusseq-dataportal.ca/submission/environmental/<id>` | `https://imicroseq-dataportal.ca/submission/environmental/<id>` |
| PHAC organization | `PHAC-AUTOINGEST` | `PHAC-NWMP` |

**Prod status (2026-11-03).** Nothing has been uploaded to prod by this pipeline. Nothing is open
for `PHAC-NWMP`.

- **Permission:** the prod account has `WW-PHAC-NWMP.WRITE`.
- **First load:** a prod dry run finds all 51,224 PHAC records as new: 6 chunks with `--chunk`
  (2020-10-25 to 2026-10-18).

Commits stay manual on the website, in both portals. `runs/`, `msg.md` and the Slack channel are
shared by both; the run log, `status.env` (`PORTAL_ENV`) and the `msg.md` headline say which portal
a run used.

## Scheduling the weekly run

Use **one** scheduler, never two. Two schedulers mean two weekly runs: the second is stopped by the
pending check, but it still posts a confusing Slack message. Pick a day after the source's weekly
update.

### GitHub Actions (recommended)

[`.github/workflows/weekly_ingestion.yml`](../.github/workflows/weekly_ingestion.yml) runs
`run_weekly_update.sh` on a GitHub runner, so the PC doesn't need to be on. The workflow file only
starts the script; all the logic stays in Bash and Python.

- **Schedule:** Mondays at 16:30 UTC, a **real run against prod**. That is 08:30 Pacific in winter
  and 09:30 in summer, since cron on GitHub is always UTC. GitHub can start scheduled jobs late at
  busy times. `MAX_NEW`, `MAX_EDITS` and the pending check apply as usual, and nothing is
  committed.
- **By hand:** Actions tab → *Weekly ingestion* → *Run workflow*, also against prod. *Dry run* is
  ticked by default.
- **Dev test uploads:** a separate workflow,
  [`.github/workflows/dev_test.yml`](../.github/workflows/dev_test.yml) (*Dev test upload*). It is
  manual only and always runs against dev, and it uploads unless *Dry run* is ticked. Choose a
  `source`, which runs `run_initial_upload.sh <SOURCE> --env dev` and ignores `ENABLED`, or
  `ALL-ENABLED` (`run_weekly_update.sh --env dev`; only sources enabled for dev, and PHAC is
  `ENABLED_DEV=0`). With one source, `holdout_weeks`, `holdout_random` and `force` give
  `--holdout-weeks`, `--holdout-random` and `--force`. Holding records back leaves new ones for
  the next test. A new source has to be added to the workflow's `source` options. `--chunk` and
  `--edits-only` ask on a terminal, so they stay local.
- **Each workflow gets only its own portal's login:** the weekly job gets the prod secrets, the
  dev test job the dev ones. A dev test can't reach prod even by mistake.
- **One run at a time:** a `concurrency` group per workflow keeps runs from overlapping
  (`portal-ingestion` for prod, `dev-test` for dev). It does the job of `runs/.lock` across
  machines.
- **Results:** `msg.md` goes to Slack, as it does locally, and onto the run's summary page. The full
  log is on the run page. `runs/` is thrown away with the runner and is **not** saved as an
  artifact, because the repo is public. To dig into a run, repeat it locally with `--dry-run`.
- **A failed run** (exit code 1) marks the run red, and GitHub emails the person who last edited
  the workflow's schedule.

**Secrets:** under *Settings → Environments*, create an environment named `portal`. Under
*Deployment branches*, allow only `main`, and don't add required reviewers (they would block the
unattended run). Add these secrets to it. Each one maps to the name the scripts read from
`upload_workflow/.env`:

| GitHub secret | Read by the scripts as |
|---|---|
| `PROD_PORTAL_USER` / `PROD_PORTAL_PASS` | `prodPortalUser` / `prodPortalPass` (weekly workflow only) |
| `DEV_PORTAL_USER` / `DEV_PORTAL_PASS` | `devPortalUser` / `devPortalPass` (dev test workflow only) |
| `SLACK_BOT_TOKEN` | `duoliauthtoken` (both; dev tests post too, like local dev runs, unless it's a dry run) |

There's no `.env` file on the runner. `load_dotenv` finds nothing and the scripts use the
environment variables.

**The log is public.** Anyone can read a public repo's Actions logs, so:

- GitHub shows secrets as `***`.
- The portal token is minted during the run, so GitHub doesn't know it as a secret. No script
  prints it. As a backstop, `run_initial_upload.sh` (`maskToken`) asks GitHub to mask it. The mask
  command goes to fd `ACTIONS_LOG_FD`, which the workflow opens on the runner's own output, so it
  never lands in `run.log`, whose last lines are copied into `msg.md` on a failure.
- Secrets are set on the run step only. Third-party actions are pinned to commit SHAs. Forks and
  pull requests never get the secrets.
- **Never add a `pull_request_target` trigger,** and never upload `runs/` as an artifact.

**Limits:**

- **GitHub turns off scheduled workflows in a public repo after 60 days without a commit.** If
  Monday's Slack message doesn't come, check the Actions tab. If it shows the workflow as
  disabled, click *Enable workflow*.
- **PHAC geocoding:** the runner uses the `geocode_cache.json` committed in git. A city that isn't
  in it yet is looked up on Nominatim on every run. The runner's updated cache is thrown away,
  because the job can't write to the repo. To keep it, run the PHAC ETL locally now and then and
  commit the cache.
- The interactive tools (`run_edits.sh`, `--chunk`, `close_submission.sh`) still run locally from a
  terminal.

### On this PC

**Windows Task Scheduler**. It works without a WSL window open, as
long as the PC is on. Find your distro name with `wsl.exe -l -v`, then run this from Windows
(PowerShell or cmd):

```
schtasks /Create /TN "iMicroSeq weekly ingestion" /SC WEEKLY /D MON /ST 09:00 ^
  /TR "wsl.exe -d <Distro> -- bash -lc '/mnt/d/OneDrive/ProjectIngestion/run_weekly_update.sh'"
```

**cron inside WSL.** This only fires while WSL is running. This WSL has no systemd, so the cron
service has to be started after every WSL restart (`sudo service cron start`), unless systemd is
enabled in `/etc/wsl.conf`. Step-by-step for operators: [SOP_weekly_upload.md](SOP_weekly_upload.md), Procedure J2.

```
0 9 * * 1  /mnt/d/OneDrive/ProjectIngestion/run_weekly_update.sh >> /mnt/d/OneDrive/ProjectIngestion/runs/cron.log 2>&1
```

cron gives the script a bare environment (`PATH=/usr/bin:/bin`, no conda, working directory
`$HOME`). This was tested with `env -i` and works. `runs/cron.log` only captures what the
scheduler itself sees; each run's full log is in `runs/<stamp>/weekly.log`.

`run_weekly_update.sh` activates the `ProjectIngestion` conda env by itself. It looks for `$CONDA_EXE`,
falling back to `~/miniconda3/bin/conda`.
