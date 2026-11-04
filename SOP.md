# Standard operating procedure: weekly data upload

This tool downloads the latest wastewater data and gets it ready on the data portal once a week.
**You** make the final decision: nothing becomes public until you review it and press commit on
the portal website.

You don't need to understand the code. Follow the steps in order, and copy the commands exactly as
written. If something goes wrong, the tool says so in plain words in a file called `msg.md`.

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

Once a week the tool runs by itself (once it's scheduled, Procedure J), or you run it by hand
(Procedure A). After every run, do this:

### Step 1. Open the message

The message arrives in the Slack channel **#_integration_notifications** after every run (but
not after a dry run). It's also always saved as `msg.md` in the tool's folder. Open it in VS
Code, or in the terminal with:

```bash
cat /mnt/d/OneDrive/ProjectIngestion/msg.md
```

If no Slack message arrived after a scheduled run, check `msg.md`. A line starting with
`WARNING: msg.md was written but could not be posted to Slack` in `runs/cron.log` or the run's
`weekly.log` means the post failed. Tell the data team.

### Step 2. Look at the first line

| First line starts with | Means | Do this |
|---|---|---|
| 🟢 **all good** | Nothing needs you | Nothing. You're done for the week. |
| 🟡 **action needed** | A submission is waiting for your review | Go to Step 3 |
| 🔴 **problem** | Something stopped the upload | Find the 🔴 line and follow the matching procedure below |

### Step 3. Review the submission on the website

The 🟡 line looks like this:

```
🟡 PHAC-NWMP: 155 new records (week 2026-10-18) passed validation. Review and commit:
https://dev.virusseq-dataportal.ca/submission/environmental/<number>
```

1. **Open the link** (Ctrl+click it in VS Code, or copy it into your browser). Log in to the portal
   if asked. No link? See Procedure K.
2. **Check before committing:**
   - the submission number on the page matches the one in `msg.md`;
   - the status is **VALID** with **no errors**;
   - the number of records matches `msg.md` (e.g. 155);
   - spot-check a few records: dates are recent, places look right, and the values aren't blank.
3. If anything looks wrong, **don't commit.** See "When to ask for help" at the end. If it has to
   be redone, close it with the script (Procedure L), not on the website.

### Step 4. Commit on the website

On the submission page, press the **Commit** button and confirm. Wait until the page shows the
submission as **COMMITTED**. The records are now published.

> These website steps will be checked against the real portal pages after the first commit. If a
> button is named differently, the data team will update this section.

**If you don't commit**, the next weekly run won't upload anything new for that source. It reminds
you (🟡 *still waiting for your commit*) until you do. No data is lost: everything that's new goes
up on the first run after you commit.

---

## Procedures

### Procedure A: run the tool by hand

Use this when you don't want to wait for the weekly schedule.

```bash
cd /mnt/d/OneDrive/ProjectIngestion
conda activate ProjectIngestion
./run_weekly.sh
```

It prints its progress as `[1/7]` to `[7/7]`. It takes about a minute. When it ends, go to the
weekly routine above, Step 1.

**For the prod portal**, add `--env prod`:

```bash
./run_weekly.sh --env prod
```

Don't do this until the data team has done the first prod load with you (Procedure C).

### Procedure B: check what would be uploaded, without uploading

```bash
./run_weekly.sh --dry-run              # dev
./run_weekly.sh --env prod --dry-run   # prod
```

This does everything except the upload. `msg.md` then says 🟢 *dry run* and how many records
*would* be uploaded. Nothing is sent to the portal.

### Procedure C: the first load for a new source

The data team usually does this one together with you. A first load is often bigger than the usual
size limit, so it is run with `--force`:

```bash
./run_source.sh PHAC --dry-run --force    # 1. check the numbers first
./run_source.sh PHAC --force              # 2. upload and validate
```

For prod, add `--env prod` to both commands. Prod gets the source's full history, which for PHAC
is about 51,000 records, so plan the prod first load with the data team.

Then do the weekly routine (Steps 1–4) to review and commit it.

### Procedure D: "still waiting for your commit" (🟡)

```
🟡 PHAC-NWMP: submission <number> is still waiting for your commit (open 7 days). Nothing new uploaded.
https://dev.virusseq-dataportal.ca/submission/environmental/<number>
```

Last week's submission was never committed. Do Steps 3–4 for that link. The next run picks up
everything new. If it should **not** be committed (for example, the data has to be redone), close
it instead (Procedure L).

### Procedure E: "failed validation" (🔴)

```
🔴 PHAC-NWMP: submission <number> failed validation (8 errors). Fix the cause, then `./close_submission.sh PHAC` and run again.
https://dev.virusseq-dataportal.ca/submission/environmental/<number>
Log: `runs/<date>-<time>/PHAC-NWMP/run.log`
```

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
- FYI: 3 published records were revised at the source, not re-uploaded (`runs/…/changed.csv`)
```

The source changed numbers for records that are already published. The tool never overwrites
published records. Pass the line on to the data team if the corrections matter. Otherwise no
action is needed.

### Procedure H: "stopped: N new records is over the limit" (🔴)

The tool found far more new records than a normal week. This is a safety stop: it usually means
the source changed its format, and uploading would create duplicates. **Don't use `--force`
yourself.** Send the 🔴 line from `msg.md` to the data team.

### Procedure I: "run failed during …" (🔴)

Something broke: the internet, the portal being down, the login, or a change at the source. Try
once more later with Procedure A. If it fails again, send the data team the 🔴 lines of
`msg.md` and the `Log:` file it names.

### Procedure J: run it automatically every week (crontab)

This makes the computer start the weekly run by itself. You still read `msg.md` and commit on the
website afterwards (the weekly routine above).

> **Know the limits first.** cron only works while the PC is on **and** a WSL (Ubuntu) window is
> open. If the PC is off or WSL is closed at the scheduled time, that week's run is simply
> skipped; do it by hand with Procedure A. For a schedule that works without a WSL window open,
> ask the data team to set up Windows Task Scheduler instead (see `README.md`).

1. **Open your schedule for editing:**

   ```bash
   crontab -e
   ```

   The first time, it asks which editor to use. Type the number next to `nano` and press
   **Enter**.

2. **Add these two lines at the bottom** of the file. Copy them exactly:

   ```
   # iMicroSeq weekly ingestion: every Monday at 09:00
   0 9 * * 1  /mnt/d/OneDrive/ProjectIngestion/run_weekly.sh >> /mnt/d/OneDrive/ProjectIngestion/runs/cron.log 2>&1
   ```

   This runs against the portal set by `PORTAL_ENV` in `pipeline.conf` (dev). To schedule prod
   instead, put `--env prod` right after `run_weekly.sh`.

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

**To stop the schedule:** run `crontab -e` again, put a `#` at the start of the `run_weekly.sh`
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
| `msg.md` didn't change | The run didn't happen: the PC was off, WSL was closed, or cron wasn't started | Run it by hand (Procedure A). Check the schedule with `crontab -l` and `service cron status` (Procedure J), and look at `runs/cron.log` |

## When to ask for help

Contact the data team if:

- the same 🔴 message appears two runs in a row;
- anything on the website looks wrong before you commit, such as odd dates, blank values or wrong
  places;
- you're not sure whether to commit a submission or close it;
- you see a long block of text mentioning `Traceback`. Copy all of it and send it along.

**Never** edit the files ending in `.py` or `.sh`, and never commit on the website if you're
unsure. An uncommitted submission does no harm; it just waits.
