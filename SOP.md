# Standard operating procedure: weekly data upload

This tool downloads the latest wastewater data and gets it ready on the data portal once a week.
**You** make the final decision: nothing becomes public until you review it and press commit on
the portal website.

You don't need to understand the code. Follow the steps in order, and copy the commands exactly as
written. If something goes wrong, the tool says so in plain words in a file called `msg.md`.

> Right now everything goes to the **test (dev) portal**, `dev.virusseq-dataportal.ca`. Nothing
> reaches the public (prod) site.

---

## Words you'll see

| Word | Meaning |
|---|---|
| **Submission** | One batch of records uploaded to the portal. Each has a number. `msg.md` gives you the number and a link to it (or see Procedure K). |
| **Validate** | The portal checks the records for errors. The result is **VALID** (all good) or **INVALID** (some records have problems). |
| **Commit** | Publishing a VALID submission. **You do this on the website.** The tool never commits. |
| **msg.md** | The tool's message to you after every run: what happened and what to do next |
| **Terminal** | The black window where you type commands (Ubuntu / WSL) |

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
   folder. If it's missing, make it from the example and put in the portal username and password,
   and the Slack token:

   ```bash
   cp upload_workflow/.env.example upload_workflow/.env
   nano upload_workflow/.env
   ```

   It has these lines (lines starting with `#` are notes):

   ```
   portalUser=the.portal.account@example.com
   portalPass=the-password
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

The message arrives in the Slack channel **#duotang-integrations** after every run (but not after
a dry run). It's also always saved as `msg.md` in the tool's folder. Open it in VS Code, or
in the terminal with:

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
3. If anything looks wrong, **don't commit.** See "When to ask for help" at the end.

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

### Procedure B: check what would be uploaded, without uploading

```bash
./run_weekly.sh --dry-run
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

Then do the weekly routine (Steps 1–4) to review and commit it.

### Procedure D: "still waiting for your commit" (🟡)

```
🟡 PHAC-NWMP: submission <number> is still waiting for your commit (open 7 days). Nothing new uploaded.
https://dev.virusseq-dataportal.ca/submission/environmental/<number>
```

Last week's submission was never committed. Do Steps 3–4 for that link. The next run picks up
everything new.

### Procedure E: "failed validation" (🔴)

```
🔴 PHAC-NWMP: submission <number> failed validation (8 errors). Nothing published.
https://dev.virusseq-dataportal.ca/submission/environmental/<number>
Log: `runs/<date>-<time>/PHAC-NWMP/run.log`
```

1. Open the link and look at the **Status** column. It shows which records failed and why. To see
   the errors in the terminal instead, see Procedure K.
2. **Don't try to fix the data by hand on the website.** Send the data team:
   - the link;
   - the `Log:` path from `msg.md`;
   - a screenshot of the errors.
3. While it stays INVALID, the weekly run won't upload anything new for that source, and
   `msg.md` keeps reminding you. Once the data team fixes and re-uploads it, do Steps 3–4 as
   normal.

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
python upload_workflow/check_pending.py --organization PHAC-AUTOINGEST
```

| Line | Means |
|---|---|
| `PENDING=0` | Nothing is open. Every submission has been committed or discarded. |
| `PENDING=1` | One is open. The lines below describe it. |
| `PENDING_ID=` | its number |
| `PENDING_STATUS=` | `VALID` (waiting for your commit) or `INVALID` (needs fixing) |
| `PENDING_CREATED=` | when it was uploaded (UTC time) |
| `PENDING_URL=` | its link: open it in your browser |

`PHAC-AUTOINGEST` is PHAC's organization. For another source, use the `ORGANIZATION=` value in
its `data_ETL/<SOURCE>/source.conf`.

**Every submission the tool has uploaded, committed ones included.** Each upload writes its link
into that run's folder. List them all:

```bash
grep SUBMISSION_URL runs/*/*/status.env
```

Each line looks like `runs/<date>-<time>/<SOURCE>/status.env:SUBMISSION_URL=https://…`. The
folder name is when the run started, so the last line is the newest upload. That run's message is
in `runs/<date>-<time>/msg.md`.

**Open a submission by its number:** go to
`https://dev.virusseq-dataportal.ca/submission/environmental/<number>`, replacing `<number>`, and
log in if asked.

**Check a submission's status and errors in the terminal:**

```bash
python upload_workflow/step6_validate.py --submission-id <number> --details
```

It prints the submission's `status` and its record counts. For an INVALID submission, it ends
with the errors for each record. Send all of it to the data team.

---

## Troubleshooting

| You see | Likely cause | What to do |
|---|---|---|
| `conda: command not found` | Terminal not set up for conda | Close and reopen the terminal, then retry |
| `another pipeline run is in progress` | A run is already going (maybe the scheduled one) | Wait a few minutes and try again |
| 🔴 *run failed during login* | Wrong or expired portal password in `upload_workflow/.env` | Update the password (see "Before you start", step 3) |
| 🔴 *no write permission for …* | The portal account lost or never had access | Ask the portal administrators to grant it |
| 🔴 *run failed during pending check* / *portal snapshot* | The portal is down or unreachable | Try again later (Procedure A) |
| 🔴 *run failed during ETL* | The source's website is down or changed its file | Try later; if it repeats, tell the data team |
| `msg.md` didn't change | The run didn't happen: the PC was off, WSL was closed, or cron wasn't started | Run it by hand (Procedure A). Check the schedule with `crontab -l` and `service cron status` (Procedure J), and look at `runs/cron.log` |

## When to ask for help

Contact the data team if:

- the same 🔴 message appears two runs in a row;
- anything on the website looks wrong before you commit, such as odd dates, blank values or wrong
  places;
- you see a long block of text mentioning `Traceback`. Copy all of it and send it along.

**Never** edit the files ending in `.py` or `.sh`, and never commit on the website if you're
unsure. An uncommitted submission does no harm; it just waits.
