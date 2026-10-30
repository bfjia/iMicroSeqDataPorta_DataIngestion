# Upload workflow

Scripts that talk to the data portal, plus the generic helpers `run_source.sh` uses between the
ETL and the upload. Each portal stage is its own script, so it can be run, debugged or replaced on
its own. `main.py` chains the upload stages together.

> **Nothing here publishes.** Committing a submission is done by a person on the portal website.
> The original `step7_commit.py` and `main.py --commit` are deliberately not part of this copy.
> They are still in `old/` for reference only.

**Running it as an operator?** Use [`../SOP.md`](../SOP.md). **Want the whole flow?** See
[`../README.md`](../README.md).

## How the portal works

The submission service is [Overture Lyric](https://github.com/overture-stack/lyric) 0.3.0. There
are two portals, and `$PORTAL_ENV` picks one (`dev` when unset; see `portal_env.py`):

| | dev | prod |
|---|---|---|
| Submission service | `https://submission-service.dev.virusseq-dataportal.ca` | `https://submissions.imicroseq-dataportal.ca` |
| Login | `ego.dev.virusseq-dataportal.ca` | `ego.imicroseq-dataportal.ca` |
| Wastewater category | `imicroseq_wastewater` (id 3) | `imicroseq_environmental` (id 1) |
| `.env` login | `devPortalUser` / `devPortalPass` | `prodPortalUser` / `prodPortalPass` |

Both use the same dictionary (`imicroseq_wastewater` v1.17). Lyric's API docs are only readable
at `/api-docs/swagger-ui-init.js`. A submission goes through three phases:

1. **Upload:** the file is staged into a *submission* and validated in the background.
2. **Validate:** the submission settles on `VALID` or `INVALID`. Nothing is public yet.
3. **Commit:** the records are published. **This happens on the website, by a person.**

An open submission (VALID or INVALID) is harmless. It waits until someone commits it on the
website, or closes it with `close_submission.py` / `../close_submission.sh`. The website has no
way to close one yet.

## The scripts

All of them follow `$PORTAL_ENV` (dev unless set) for the portal, its login and the default
`--category`. They also take `--base-url` and `--token`. Without a token, they read
`$PORTAL_TOKEN`, and failing that they log in fresh using `.env`. Each one runs standalone. Run
them from anywhere with the `ProjectIngestion` env active, e.g.
`PORTAL_ENV=prod python check_pending.py --organization PHAC-AUTOINGEST`. Don't reuse a
`$PORTAL_TOKEN` from one portal on the other.

### Portal stages (used by `main.py`)

| Script | What it does | Portal calls | Standalone example |
|---|---|---|---|
| `portal_env.py` | The dev and prod hosts, categories and `.env` key names, picked by `$PORTAL_ENV`. The only place portal hosts are written down. | | |
| `getToken.py` | Logs in through Keycloak like a browser and prints an Ego JWT. The original script, changed only to take the portal and its `.env` login (`<env>PortalUser` / `<env>PortalPass`) from `portal_env.py`. | `ego.<portal>/api/oauth/login/keycloak`, `…/ego-token` | `python getToken.py` |
| `step1_token.py` | Wraps `getToken.py`. `--scopes` prints the token's permissions. | (as above) | `python step1_token.py --scopes` |
| `step2_category.py` | Turns a category name into its numeric id | `GET /category`, `GET /category/{id}` | `python step2_category.py --category imicroseq_wastewater` |
| `step3_dictionary.py` | Fetches the dictionary and builds the map from CSV title to field name | `GET /dictionary/category/{id}` | `python step3_dictionary.py --category-id 3` |
| `step4_transform.py` | Renames the CSV headers to field names, writing `sample.csv`. An unknown column is a hard error. | dictionary only | `python step4_transform.py --input delta.csv --output-dir out/` |
| `step5_upload.py` | Uploads a file, opening a submission. `--replace` discards an open one first. | `GET /submission/category/{id}?onlyActive=true`, `DELETE /submission/{id}`, `POST /submission/category/{id}/data` | (normally via `main.py`) |
| `step6_validate.py` | Polls until validation settles. `--details` prints per-record errors. | `GET /submission/{id}` (event stream), `GET /submission/{id}/details` | `python step6_validate.py --submission-id <number> --details` |
| `main.py` | Runs steps 1–6 and stops. On VALID it prints the website link to commit. On INVALID it prints the link to the errors. `--result-json` writes the outcome for scripts. | all of the above | `python main.py --input delta.csv --organization PHAC-AUTOINGEST` |
| `common.py` | Shared HTTP, polling and token helpers. `PortalEnv`, `DefaultBaseURL`, `DefaultPortalURL` and `DefaultCategory` come from `portal_env.py`. | | |

`main.py` refuses to upload if a submission is already open for the organization. Passing
`--replace` discards that submission first; use it only when re-uploading after fixing an INVALID
submission. Without `--work-dir`, its working files go in `runs/main-<timestamp>/`, never `/tmp`.

### Pipeline helpers (used by `run_source.sh`)

| Script | Step | What it does | Example |
|---|---|---|---|
| `check_pending.py` | 1 | Is a submission still open for the org? Also reports whether the token has the org's write scope. Prints `KEY=VALUE` (or `--json`). It needs a real token, because the listing is per logged-in user. | `python check_pending.py --organization PHAC-AUTOINGEST` |
| `filter_rows.py` | 3 | Keeps rows with `sample collection start date` ≥ the cutoff and drops undated rows while a cutoff is set. Prints `kept= before_cutoff= undated=`. | `python filter_rows.py --input a.csv --output b.csv --min-start-date 2026-09-01` |
| `fetch_published.py` | 4 | Downloads the org's published records as a CSV with the curated column titles. Lists are joined with each field's delimiter, and omitted fields become empty. A 404 "No Submitted data found" gives a header-only CSV. | `python fetch_published.py --organization PHAC-AUTOINGEST --output published.csv` |
| `diff_new_records.py` | 5 | Splits the curated rows into new / changed / unchanged against the published snapshot. Numbers are compared numerically (rel. 1e-6). A duplicate sample ID is a hard error. Prints `new= changed= unchanged=`. | `python diff_new_records.py --new a.csv --baseline published.csv --new-out delta.csv --changed-out changed.csv` |
| `holdout_rows.py` | 5 | **Test only.** Holds back the newest N weeks plus N random older rows, to create a delta for the next run | `python holdout_rows.py --input delta.csv --output kept.csv --held-out held.csv --latest-weeks 1 --random 10` |
| `close_submission.py` | — | Discards the org's open submission so a new one can start (used by `../close_submission.sh`). Shows it, then asks for its number unless `--yes`. Re-checks that it's gone. Never touches published records. | `python close_submission.py --organization PHAC-AUTOINGEST` |
| `notify.py` | 8 | Builds the run's single `msg.md` digest from each source's `status.env` | `python notify.py --run-dir runs/<stamp> --out msg.md` |
| `slack_post.py` | 8 | Posts `msg.md` to Slack (`chat.postMessage`) after converting it to Slack markdown. Token: `duoliauthtoken` in `.env`; the bot must be in the channel. `--print` shows the text and sends nothing. Modeled on `old/duoli.py`. | `python slack_post.py --file ../msg.md --channel C0123456789` |

## Things that will bite you

**The organization is not the scope name.** Permissions are Ego scopes named after the policy,
with a `WW-` prefix the organization doesn't have. The scope `WW-PHAC-AUTOINGEST.WRITE` means you
submit as `PHAC-AUTOINGEST`. It is case-sensitive, and *every* wrong value gives the same
`403 User is not authorized to submit data to '<org>'`. Check with `python step1_token.py --scopes`.

**Tokens are snapshots.** Scopes are baked in when the token is minted. Get a fresh token after any
permissions change.

**Uploading to an open submission appends to it.** Every record gets staged a second time and
validation fails with `INVALID_BY_UNIQUE`. This is why the pipeline checks for an open submission
first, and why `main.py` refuses without `--replace`.

**Uniqueness spans published data.** `specimen collector sample ID` must be unique against
everything already published, not just within the file. This is why the pipeline diffs against
the portal snapshot.

**`GET /submission/{id}` is an event stream, not JSON,** and the server holds it open while
validating. `common.apiGetEvent` reads the first `data:` event and closes the connection.

**The submission listing is per user.** `GET /submission/category/{id}` only shows the logged-in
user's submissions. An anonymous call returns an empty list even when something is open.

**Column names come from the live dictionary.** The CSVs use readable titles
(`INSDC Project accession`). The API wants field names (`insdc_project_accession`). The map is
fetched at every run, so a dictionary version bump shows up as a clear error.

**Reads are open, writes are not.** `/data/…`, `/dictionary/…` and `/category` work without a
token. Uploads (and the per-user listing) need one.

## Requirements

- The `ProjectIngestion` conda env (`../environment.yaml`).
- `upload_workflow/.env` with `devPortalUser` / `devPortalPass` and `prodPortalUser` /
  `prodPortalPass`, plus `duoliauthtoken` (the Slack bot token) if Slack is on. Copy
  `.env.example`. It is never committed.
