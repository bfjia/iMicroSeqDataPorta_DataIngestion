# Standard operating procedure: weekly data upload

This tool downloads the latest wastewater data and gets it ready on the data portal once a week.
**You** make the final decision: nothing becomes public until you review it and press commit on
the portal website.

You don't need to understand the code. Follow the steps in order, and copy the commands exactly as
written. If something goes wrong, the tool says so in plain words in a file called `msg.md`.

Adding a new data source is a separate procedure: [SOP_new_source.md](SOP_new_source.md).

> **There are two portals.** The **test (dev) portal** is `dev.virusseq-dataportal.ca`. The
> **real (prod) portal** is `imicroseq-dataportal.ca`. Every command uses **dev** unless you add
> `--env prod` to it. The first line of every message says which portal, `(dev)` or `(prod)`.
> Committing on the prod website publishes the records for real.

---

## Words you'll see

| Word | Meaning |
|---|---|
| **Submission** | One batch of records uploaded to the portal. Each has a number. `msg.md` gives you the number and a link to it (or see Procedure K). |
| **Validate** | The portal checks the records for errors. The result is **VALID** (all good) or **INVALID** (some records have problems). |
| **Commit** | Publishing a VALID submission. **You do this on the website.** The tool never commits. |
| **Edit** | A correction to a record that is already published, because the source has revised it. The tool sends edits in the same submission as the new records; the website shows each one as old value → new value. They change nothing until you commit. |
| **Close** | Throwing away a submission that hasn't been committed, so a new one can be uploaded. **The website can't do this yet:** use the `close_submission.sh` script (Procedure L). |
| **msg.md** | The tool's message to you after every run: what happened and what to do next |
| **Terminal** | The black window where you type commands (Ubuntu / WSL) |
| **dev / prod** | The test portal and the real one. Commands use dev unless you add `--env prod`. |

---

## Before you start (once only)

1. **Open a terminal and go to the tool's folder:**

   ```bash
   cd /mnt/d/OneDrive/ProjectIngestion
   ```

2. **Check the software environment exists:**

   ```bash
   conda env list
   ```

   You should see `ProjectIngestion` in the list. If it isn't there, create it (this takes a few
   minutes):

   ```bash
   conda env create -f environment.yaml
   ```

3. **Check the login file exists.** It's called `.env` and lives in the `upload_workflow`
   folder. If it's missing, make it from the example and put in a username and password for each
   portal, and the Slack token:

   ```bash
   cp upload_workflow/.env.example upload_workflow/.env
   nano upload_workflow/.env
   ```

   It has these lines (lines starting with `#` are notes):

   ```
   devPortalUser=the.dev.account@example.com
   devPortalPass=the-dev-password
   prodPortalUser=the.prod.account@example.com
   prodPortalPass=the-prod-password
   duoliauthtoken=xoxb-the-slack-bot-token
   ```

   The data team gives you the Slack token. It's only needed if messages go to Slack.

   Save with **Ctrl+O**, **Enter**, then exit with **Ctrl+X**. **Never share this file or put it
   in email, chat or git.**

---

## The weekly routine

Once a week the tool runs by itself on GitHub, every Monday morning against prod (Procedure J).
You can also run it by hand (Procedure A). After every run, do this:

### Step 1. Open the message

The message arrives in the Slack channel **#_integration_notifications** after every run (but
not after a dry run). It's also always saved as `msg.md` in the tool's folder. Open it in VS
Code, or in the terminal with:

```bash
cat /mnt/d/OneDrive/ProjectIngestion/msg.md
```

**Runs on GitHub don't change the `msg.md` on this PC.** For those, read the Slack message, or
open the run on GitHub (Procedure J): the message is at the top of the run's page.

If no Slack message arrived after a scheduled run, check the run on GitHub (Procedure J). A line
starting with `WARNING: msg.md was written but could not be posted to Slack` in the run's log means
the post failed. Tell the data team.

### Step 2. Look at the first line

| First line starts with | Means | Do this |
|---|---|---|
| 🟢 **all good** | Nothing needs you | Nothing. You're done for the week. |
| 🟡 **action needed** | A submission is waiting for your review | Go to Step 3 |
| 🔴 **problem** | Something stopped the upload | Find the 🔴 line and follow the matching procedure below |

### Step 3. Review the submission on the website

The 🟡 block looks like this:

```
🟡 PHAC-NWMP · review and commit
• New: 155 records, week 2026-10-18
• Edits: 69 published records (diagnostic measurement value 1)
• Submission <number>: VALID, 0 errors
https://dev.virusseq-dataportal.ca/submission/environmental/<number>
```

The **Edits** line appears only when the source has revised records that are already published,
and names the fields that change. Some weeks there are only new records, some weeks only edits.

1. **Open the link** (Ctrl+click it in VS Code, or copy it into your browser). Log in to the portal
   if asked. No link? See Procedure K.
2. **Check before committing:**
   - the submission number on the page matches the one in `msg.md`;
   - the status is **VALID** with **no errors**;
   - the number of records matches `msg.md`: new records (e.g. 155) and, if any, edits (e.g. 69);
   - spot-check a few new records: dates are recent, places look right, and the values aren't
     blank;
   - if there are edits, spot-check a few: each shows the old and the new value. Usually only a
     measurement changes, for recent weeks. Many fields changing at once, or very old weeks, is
     unusual: ask the data team before committing.
3. If anything looks wrong, **don't commit.** See "When to ask for help" at the end. If it has to
   be redone, close it with the script (Procedure L), not on the website.

### Step 4. Commit on the website

On the submission page, press the **Commit** button and confirm. Wait until the page shows the
submission as **COMMITTED**. The records are now published.

> These website steps will be checked against the real portal pages after the first commit. If a
> button is named differently, the data team will update this section.

**If you don't commit**, the next weekly run won't upload anything new for that source. It reminds
you (🟡 *waiting for your commit*) until you do. No data is lost: everything that's new goes
up on the first run after you commit.

---

## Procedures

### Procedure A: run the tool by hand

Use this when you don't want to wait for the weekly schedule.

```bash
cd /mnt/d/OneDrive/ProjectIngestion
conda activate ProjectIngestion
./run_weekly_update.sh
```

It prints its progress as `[1/7]` to `[7/7]`. It takes about a minute. When it ends, go to the
weekly routine above, Step 1.

**For the prod portal**, add `--env prod`:

```bash
./run_weekly_update.sh --env prod
```

Don't do this until the data team has done the first prod load with you (Procedure C).

### Procedure B: check what would be uploaded, without uploading

```bash
./run_weekly_update.sh --dry-run              # dev
./run_weekly_update.sh --env prod --dry-run   # prod
```

This does everything except the upload. `msg.md` then says 🟢 *dry run* and how many records
*would* be uploaded. Nothing is sent to the portal.

### Procedure C: the first load for a new source

The data team usually does this one together with you. A first load is often bigger than the usual
size limit, so it is run with `--force`:

```bash
./run_initial_upload.sh PHAC --dry-run --force    # 1. check the numbers first
./run_initial_upload.sh PHAC --force              # 2. upload and validate
```

Then do the weekly routine (Steps 1–4) to review and commit it.

**A big first load (prod), in chunks.** Prod gets the source's full history, about 51,000 records
for PHAC. That goes up in chunks of 10,000, each a separate submission that you commit before the
next one is sent:

```bash
./run_initial_upload.sh PHAC --env prod --chunk --dry-run   # 1. see the chunks, uploads nothing
./run_initial_upload.sh PHAC --env prod --chunk             # 2. upload, one chunk at a time
```

The script asks before every chunk:

```
      Upload chunk 2 of 6 (10000 records, weeks 2023-05-07 to 2024-03-10)? Type yes, or stop:
```

1. Type `yes` and press **Enter** to upload the chunk. Wait until it says the chunk is **VALID**
   and shows its link.
2. Open the link and **commit that submission on the website** (Steps 3–4).
3. Back in the terminal, type `yes` for the next chunk. If you haven't committed the last one yet,
   it tells you so and asks again.
4. Repeat until it says *All chunks uploaded*, then commit the last one.

You can type `stop` at any question. Nothing is lost: run the same command again later, and it
carries on with whatever isn't published yet. If a chunk fails validation, the run stops; see
Procedure E. Keep the terminal open while chunks upload.

### Procedure D: "waiting for your commit" (🟡)

```
🟡 PHAC-NWMP · waiting for your commit
• Submission <number>, open 7 days. Nothing new uploaded.
https://dev.virusseq-dataportal.ca/submission/environmental/<number>
```

Last week's submission was never committed. Do Steps 3–4 for that link. The next run picks up
everything new. If it should **not** be committed (for example, the data has to be redone), close
it instead (Procedure L).

### Procedure E: "failed validation" (🔴)

```
🔴 PHAC-NWMP · failed validation
• New: 155 records, week 2026-10-18
• Submission <number>: INVALID, 8 errors
• Fix the cause, then `./close_submission.sh PHAC --env dev` and run again
https://dev.virusseq-dataportal.ca/submission/environmental/<number>
Log: `runs/<date>-<time>/PHAC-NWMP/run.log`
```

If the block says *an earlier submission failed validation*, it's a submission from a previous
run that's still open; the steps are the same.

1. Open the link and look at the **Status** column. It shows which records failed and why. To see
   the errors in the terminal instead, see Procedure K.
2. **Don't try to fix the data by hand on the website.** Send the data team:
   - the link;
   - the `Log:` path from `msg.md`;
   - a screenshot of the errors.
3. While it stays open, the weekly run won't upload anything new for that source, and
   `msg.md` keeps reminding you. Once the data team has fixed the cause, close it
   (Procedure L) and run again (Procedure A). Then do Steps 3–4 for the new submission.

### Procedure F: "missing values" (FYI line)

```
- FYI: missing values, please supply: coordinates: ['Somewhere, Yukon']
```

The source data had something new the tool doesn't know yet, often a new city whose map position
it couldn't find. Those records were still uploaded, with that one value left blank. Send the line
to the data team, who will add the missing value. Nothing else is needed from you.

### Procedure G: "revised values" (FYI line)

```
- FYI: 3 published records were revised at the source, not sent (edits are off for this source; `runs/…/changed.csv`)
```

The source changed numbers for records that are already published. Normally the tool sends these
as edits, in the same submission as the new records (Step 3). You see this line only when edits
are turned off for that source, or after a chunked first load. Pass the line on to the data team
if the corrections matter. Otherwise no action is needed.

### Procedure H: "stopped: too many new records" (🔴)

The tool found far more new records than a normal week. This is a safety stop: it usually means
the source changed its format, and uploading would create duplicates. **Don't use `--force`
yourself.** Send the 🔴 line from `msg.md` to the data team.

### Procedure I: "run failed during …" (🔴)

Something broke: the internet, the portal being down, the login, or a change at the source. Try
once more later with Procedure A. If it fails again, send the data team the 🔴 lines of
`msg.md` and the `Log:` file it names.

### Procedure J: the automatic weekly run

The weekly run starts by itself on **GitHub**, every **Monday morning** (08:30 Pacific in winter,
09:30 in summer; sometimes a little later). It runs against **prod** and uploads for real. Nothing
is committed: you still review and commit on the website afterwards (the weekly routine above). It
works whether or not this PC is on.

**Use only one schedule.** If GitHub runs it, don't also set up crontab on this PC (J2), or the
tool runs twice a week.

#### J1. On GitHub (the normal way)

**To see a run:** open the repository on GitHub
(https://github.com/bfjia/iMicroSeqDataPorta_DataIngestion), click **Actions**, then
**Weekly ingestion**. Each line is one run: ✅ finished cleanly, ❌ had a problem. Click a run to
see its message (the same text as Slack) at the top of the page.

**To start a prod run by hand** (for example, to check something before Monday):

1. On the **Weekly ingestion** page, click **Run workflow** (on the right).
2. Leave **Dry run** ticked to only check what would be uploaded to prod (nothing is sent, no
   Slack message). Untick it only for a real prod upload.
3. Click the green **Run workflow** button. The run appears in the list after a few seconds.

**To test on dev** (data team): use the other workflow, **Dev test upload**, in the same Actions
list. It never touches prod, and it only runs when someone starts it.

1. Click **Dev test upload**, then **Run workflow**.
2. Pick the **Source** (for example `PHAC`).
3. **Dry run** is unticked here: the test really uploads to dev. Tick it to only check.
4. Usually leave the other boxes as they are. For a repeat test, when dev already has
   everything, put `1` in **holdout weeks** so the newest week is held back and stays new for the
   next test.
5. Click **Run workflow**. Afterwards, review the submission on the **dev** website and commit
   it, or ask the data team to close it (Procedure L, without `--env prod`).

**If the Monday run didn't happen** (no Slack message, nothing new in the list): GitHub switches
the schedule off when nobody has changed the repository for 60 days. If the Weekly ingestion page
shows a yellow banner saying it is disabled, click **Enable workflow**, then start a run by hand
(above). If you can't see the Actions tab or the buttons, ask the data team.

**If the login fails** on GitHub (🔴 *run failed during login*): the password stored on GitHub
is out of date. Ask the data team to update it (configuration.md, "Scheduling the weekly run").

#### J2. With crontab on this PC (only if GitHub isn't used)

This makes the computer start the weekly run by itself. You still read `msg.md` and commit on the
website afterwards (the weekly routine above).

> **Know the limits first.** cron only works while the PC is on **and** a WSL (Ubuntu) window is
> open. If the PC is off or WSL is closed at the scheduled time, that week's run is simply
> skipped; do it by hand with Procedure A. For a schedule that works without a WSL window open,
> ask the data team to set up Windows Task Scheduler instead (see
> [configuration.md](configuration.md), "Scheduling the weekly run").

1. **Open your schedule for editing:**

   ```bash
   crontab -e
   ```

   The first time, it asks which editor to use. Type the number next to `nano` and press
   **Enter**.

2. **Add these two lines at the bottom** of the file. Copy them exactly:

   ```
   # iMicroSeq weekly ingestion: every Monday at 09:00
   0 9 * * 1  /mnt/d/OneDrive/ProjectIngestion/run_weekly_update.sh >> /mnt/d/OneDrive/ProjectIngestion/runs/cron.log 2>&1
   ```

   This runs against the portal set by `PORTAL_ENV` in `pipeline.conf` (dev). To schedule prod
   instead, put `--env prod` right after `run_weekly_update.sh`.

   The five values at the start are *minute, hour, day of month, month, day of week*. `0 9 * * 1`
   means "at 09:00, every month, on Mondays" (0 = Sunday, 1 = Monday … 6 = Saturday). To run
   on Tuesdays at 08:30 instead, use `30 8 * * 2`. Lines starting with `#` are notes and are
   ignored.

3. **Save and exit:** **Ctrl+O**, **Enter**, then **Ctrl+X**.

4. **Check it was saved:**

   ```bash
   crontab -l
   ```

   You should see the two lines.

5. **Start the cron service.** On this computer it doesn't start by itself, so **do this every
   time you open WSL after a restart** of the PC or of WSL:

   ```bash
   sudo service cron start
   ```

   It asks for your Ubuntu password. Check it's running with `service cron status`. It should
   say `cron is running`.

**To check a scheduled run happened:** look at the date on the first line of `msg.md`, or at the
end of the cron log:

```bash
tail -n 20 /mnt/d/OneDrive/ProjectIngestion/runs/cron.log
```

**To stop the schedule:** run `crontab -e` again, put a `#` at the start of the `run_weekly_update.sh`
line (or delete both lines), and save.

### Procedure K: find a submission (for troubleshooting)

Normally you don't need this, because `msg.md` always has the link. Use it if you've lost the
message, or the data team asks about a submission.

**The submission that is still open** (waiting for your commit, or INVALID and waiting for a fix):

```bash
cd /mnt/d/OneDrive/ProjectIngestion
conda activate ProjectIngestion
python upload_workflow/check_pending.py --organization PHAC-AUTOINGEST                   # dev
PORTAL_ENV=prod python upload_workflow/check_pending.py --organization PHAC-NWMP         # prod
```

| Line | Means |
|---|---|
| `PENDING=0` | Nothing is open. Every submission has been committed or discarded. |
| `PENDING=1` | One is open. The lines below describe it. |
| `PENDING_ID=` | its number |
| `PENDING_STATUS=` | `VALID` (waiting for your commit) or `INVALID` (needs fixing) |
| `PENDING_CREATED=` | when it was uploaded (UTC time) |
| `PENDING_URL=` | its link: open it in your browser |

Each portal has its own name for a source's organization. PHAC's is `PHAC-AUTOINGEST` on dev and
`PHAC-NWMP` on prod. For any source, `./list_sources.sh` shows its organization on both portals.

**Every submission the tool has uploaded, committed ones included.** Each upload writes its link
into that run's folder. List them all:

```bash
grep SUBMISSION_URL runs/*/*/status.env
```

Each line looks like `runs/<date>-<time>/<SOURCE>/status.env:SUBMISSION_URL=https://…`. The
folder name is when the run started, so the last line is the newest upload. The link shows the
portal: `dev.virusseq-dataportal.ca` is dev, `imicroseq-dataportal.ca` is prod. That run's message
is in `runs/<date>-<time>/msg.md`.

**Open a submission by its number** (replace `<number>`, and log in if asked):

- dev: `https://dev.virusseq-dataportal.ca/submission/environmental/<number>`
- prod: `https://imicroseq-dataportal.ca/submission/environmental/<number>`

**Check a submission's status and errors in the terminal:**

```bash
python upload_workflow/step6_validate.py --submission-id <number> --details                   # dev
PORTAL_ENV=prod python upload_workflow/step6_validate.py --submission-id <number> --details   # prod
```

It prints the submission's `status` and its record counts. For an INVALID submission, it ends
with the errors for each record. Send all of it to the data team.

### Procedure L: close the open submission and start over

> **The portal website has no way to close a submission yet.** Use this script. Don't look for
> a button on the website.

**When to use it:** the open submission should **not** be committed. Either it failed validation
(🔴) and the data team has fixed the cause, or the data has to be redone. While a submission is
open, the tool uploads nothing new for that source, so closing it is how you start over.

**What closing does:**

- It throws away the open submission and the records in it. This can't be undone.
- No data is lost: those records aren't published, so the next run finds them as new again and
  uploads them.
- Records that are already published are never affected. A committed submission can't be closed.
- Nothing is committed.

**Steps:**

1. **Check which submission is open** and that it's the one you mean (Procedure K):

   ```bash
   cd /mnt/d/OneDrive/ProjectIngestion
   conda activate ProjectIngestion
   python upload_workflow/check_pending.py --organization PHAC-AUTOINGEST                   # dev
   PORTAL_ENV=prod python upload_workflow/check_pending.py --organization PHAC-NWMP         # prod
   ```

   Note the `PENDING_ID` number.

2. **Run the close script** for the source. `PHAC` is the source's folder name under
   `data_ETL/`:

   ```bash
   ./close_submission.sh PHAC              # dev
   ./close_submission.sh PHAC --env prod   # prod
   ```

3. **Confirm.** The script shows the open submission and asks for its number:

```
Portal: dev · organization PHAC-AUTOINGEST · category imicroseq_wastewater
Open submission for PHAC-AUTOINGEST on dev:
  number:  <number>
  status:  INVALID
  created: 2026-10-30T18:24:19.424Z
  link:    https://dev.virusseq-dataportal.ca/submission/environmental/<number>
Closing discards it and everything staged in it. Published records are not affected.
Type <number> to close it, or press Enter to cancel:
```

   Check the portal and the number match step 1. Then type the number and press **Enter** to
   close it, or just press **Enter** to cancel (nothing changes).

4. **Check it worked.** It should end with:

   ```
   Closed submission <number>. The next run uploads a new one.
   ```

5. **Start a new submission** by running the tool again (Procedure A). It uploads everything
   that isn't published yet. Then follow the weekly routine (Steps 1–4) for the new submission.
   If the old one failed validation, only do this once the data team says the cause is fixed;
   otherwise the new one fails the same way.

| The script says | Means | Do this |
|---|---|---|
| `No open submission … Nothing to close` | Nothing is open | Nothing. You can run the tool (Procedure A). |
| `Cancelled. Nothing was changed.` | You pressed Enter, or typed a different number | Run it again if you meant to close it |
| `a pipeline run is in progress` | A run is going right now | Wait a few minutes and try again |
| `ERROR: … still shows as open after closing it` | The portal didn't close it | Send the output to the data team |
| `ERROR: … HTTP 401` / `403` | Login or permission problem | Check `upload_workflow/.env`; tell the data team if it repeats |

### Procedure M: send only the edits (data team)

Use this to bring already-published records up to date on their own, for example after a
converter change, or when a run stopped with "stopped: too many edits" (Procedure N).

```bash
cd /mnt/d/OneDrive/ProjectIngestion
conda activate ProjectIngestion
./run_edits.sh PHAC --dry-run   # 1. see what would be edited; sends nothing
./run_edits.sh PHAC             # 2. show the edits, ask, send
```

Add `--env prod` for prod. It downloads fresh data, compares it with what's published, and shows
how many records would change, which fields, and a few examples:

```
      Edits for the 69 revised record(s). Fields that change:
          69  diagnostic measurement value 1: e.g. '0.838214474305977' -> '2.61515129117012'
[6/7] 69 published record(s) to edit, e.g. PHAC_2026-10-18_Bathurst_covN2, …
      Send these 69 edit(s) to PHAC-AUTOINGEST on the dev portal? Type yes, or stop:
```

1. Type `yes` and press **Enter** to send them, or `stop` to end with nothing sent.
2. Wait until it says the submission is **VALID** and shows its link.
3. Review and commit it on the website (Steps 3–4). Each edit shows the old and the new value.

It sends only edits; new records wait for the weekly run. It needs a terminal.

### Procedure N: "stopped: too many edits" (🔴)

```
🔴 PHAC-NWMP · stopped: too many edits
• 2,500 published records were revised; the limit is 2,000. Nothing uploaded.
• What changed: geo loc name (site) (2,500), diagnostic measurement value 1 (70)
• If expected: `./run_edits.sh PHAC --env dev`
```

Far more already-published records changed than in a normal week (PHAC usually revises about 70).
This is a safety stop: it usually means the source, or the tool's converter, changed a value for
everything. Nothing was uploaded. **Don't use `--force` yourself.** Send the 🔴 line to the data
team. If the changes are expected, they send them with `run_edits.sh` (Procedure M).

---

## Troubleshooting

| You see | Likely cause | What to do |
|---|---|---|
| `conda: command not found` | Terminal not set up for conda | Close and reopen the terminal, then retry |
| `another pipeline run is in progress` | A run is already going (maybe the scheduled one) | Wait a few minutes and try again |
| 🔴 *run failed during login* | Wrong or expired password for that portal (`devPortalPass` or `prodPortalPass` in `upload_workflow/.env`) | Update the password (see "Before you start", step 3) |
| 🔴 *no write permission for …* / FYI *the account can't write to …* | That portal's account lost or never had access to the organization | Run `./list_sources.sh --check` to see which. Ask the portal administrators to grant it. |
| 🔴 *run failed during pending check* / *portal snapshot* | The portal is down or unreachable | Try again later (Procedure A) |
| 🔴 *run failed during ETL* | The source's website is down or changed its file | Try later; if it repeats, tell the data team |
| No Slack message on Monday | The GitHub run didn't happen or couldn't post | Check the run on GitHub (Procedure J1). Its schedule may have been switched off. |
| `msg.md` didn't change | Normal after a GitHub run: those don't touch this PC. With crontab, the run didn't happen (the PC was off, WSL was closed, or cron wasn't started). | GitHub: read Slack or the run page (Procedure J1). Crontab: run it by hand (Procedure A), check the schedule with `crontab -l` and `service cron status` (Procedure J2), and look at `runs/cron.log`. |

## When to ask for help

Contact the data team if:

- the same 🔴 message appears two runs in a row;
- anything on the website looks wrong before you commit, such as odd dates, blank values or wrong
  places;
- you're not sure whether to commit a submission or close it;
- you see a long block of text mentioning `Traceback`. Copy all of it and send it along.

**Never** edit the files ending in `.py` or `.sh`, and never commit on the website if you're
unsure. An uncommitted submission does no harm; it just waits.
