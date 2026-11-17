# iMicroSeq data ingestion

Every week, this tool downloads wastewater surveillance data from outside sources, converts it to
the [iMicroSeq data standard](data_specification/), and uploads the records that are new to the
iMicroSeq data portal, where they're checked. A person then reviews each upload and **publishes
("commits") it on the portal website**. The tool never publishes anything by itself.

Sources so far: PHAC's National Wastewater Monitoring of Pathogens, and Alberta data from the
University of Calgary's Centre for Health Informatics (CHI, being set up). More can be added, each
as its own folder.

## Documentation

| I want to… | Read |
|---|---|
| run the weekly upload, then review and commit it | [docs/SOP_weekly_upload.md](docs/SOP_weekly_upload.md) |
| add a new data source | [docs/SOP_new_source.md](docs/SOP_new_source.md) |
| understand what each step of a run does | [docs/how_a_run_works.md](docs/how_a_run_works.md) |
| look up commands, settings, the two portals or scheduling | [docs/configuration.md](docs/configuration.md) |
| change the code | [CLAUDE.md](CLAUDE.md) (project rules), [data_ETL/README.md](data_ETL/README.md), [upload_workflow/README.md](upload_workflow/README.md) |

## Two portals

| | Address | Used |
|---|---|---|
| **dev** (test) | `dev.virusseq-dataportal.ca` | by default |
| **prod** (real) | `imicroseq-dataportal.ca` | when you add `--env prod` to a command |

Committing on the prod website publishes the records for real.

## Quick start

```bash
cd /mnt/d/OneDrive/ProjectIngestion
conda env create -f environment.yaml                    # once
cp upload_workflow/.env.example upload_workflow/.env    # once, then fill in the logins
conda activate ProjectIngestion

./run_weekly_update.sh --dry-run    # see what would be uploaded; uploads nothing
./run_weekly_update.sh              # upload and check the new records
cat msg.md                          # what happened, and what to do next
```

Then review and commit the upload on the website, using the link in `msg.md`. The full routine is
in [docs/SOP_weekly_upload.md](docs/SOP_weekly_upload.md).

## What a run does

1. **Checks** that nothing from an earlier run is still waiting on the portal. If something is,
   it stops and reminds you.
2. **Downloads and converts** each source's latest data.
3. **Compares** it with what's already published: new records, and published records the source
   has since corrected.
4. **Uploads the new records and the corrections together and waits for the portal's checks**,
   then stops. A person reviews and commits them on the website.
5. **Writes one short message**, `msg.md`, which is also posted to Slack: all good, action
   needed, or a problem.

Step-by-step detail is in [docs/how_a_run_works.md](docs/how_a_run_works.md).

## Folder layout

```
docs/                    procedures (SOPs) and technical guides
data_ETL/                one folder per data source (PHAC, plus _template to copy)
upload_workflow/         the scripts that talk to the portal
data_specification/      the iMicroSeq standard: fields and allowed values
run_weekly_update.sh     the weekly update: every source (what the schedule runs)
run_initial_upload.sh    one source: its first load (--chunk for big ones), or a one-off run
run_edits.sh             one source: only the corrections to already-published records
close_submission.sh      throw away an uncommitted upload, to start over
list_sources.sh          each source's organization on dev and prod
pipeline.conf            settings shared by all sources
runs/                    logs from each run (not saved to git)
```

## Ground rules

- **The tool never publishes.** Committing is always done by a person on the website.
- **`--dry-run` is always safe.** It does everything except the upload.
- **Logins and data never go into git.** `upload_workflow/.env`, `runs/`, `msg.md` and the
  downloaded data are excluded.
