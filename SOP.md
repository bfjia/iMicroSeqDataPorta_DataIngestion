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
| **Submission** | One batch of records uploaded to the portal. It has a number, e.g. *submission 412*. |
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

3. **Check the portal login file exists.** It's called `.env` and lives in the
   `upload_workflow` folder. If it's missing, make it from the example and put in the portal
   username and password:

   ```bash
   cp upload_workflow/.env.example upload_workflow/.env
   nano upload_workflow/.env
   ```

   It has two lines:

   ```
   portalUser=the.portal.account@example.com
   portalPass=the-password
   ```

   Save with **Ctrl+O**, **Enter**, then exit with **Ctrl+X**. **Never share this file or put it
   in email, chat or git.**

---

## The weekly routine

Once a week the tool runs by itself, or you run it by hand (Procedure A). After every run, do
this:

### Step 1. Open the message

Open `msg.md` in the tool's folder: in VS Code, or in the terminal with:

```bash
cat /mnt/d/OneDrive/ProjectIngestion/msg.md
```

### Step 2. Look at the first line

| First line starts with | Means | Do this |
|---|---|---|
| 🟢 **all good** | Nothing needs you | Nothing. You're done for the week. |
| 🟡 **action needed** | A submission is waiting for your review | Go to Step 3 |
| 🔴 **a problem needs attention** | Something stopped the upload | Find the 🔴 section and follow the matching procedure below |

### Step 3. Review the submission on the website

The 🟡 section looks like this:

```
## 🟡 PHAC-NWMP: review and commit submission 412
**165 new records** (collection weeks 2026-10-18 to 2026-10-18) passed validation ...
- Review and commit: https://dev.virusseq-dataportal.ca/submission/environmental/412
```

1. **Open the link** (Ctrl+click it in VS Code, or copy it into your browser). Log in to the portal
   if asked.
2. **Check before committing:**
   - the submission number on the page matches the one in `msg.md`;
   - the status is **VALID** with **no errors**;
   - the number of records matches `msg.md` (e.g. 165);
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

The data team usually does this one together with you. A first load is bigger than the usual size
limit, so it needs `--force`:

```bash
./run_source.sh PHAC --dry-run --force    # 1. check the numbers first
./run_source.sh PHAC --force              # 2. upload and validate
```

Then do the weekly routine (Steps 1–4) to review and commit it.

### Procedure D: "still waiting for your commit" (🟡)

```
## 🟡 PHAC-NWMP: submission 412 is still waiting for your commit
Open since 2026-10-30 (7 days). Nothing new was uploaded this run.
```

Last week's submission was never committed. Do Steps 3–4 for that link. The next run picks up
everything new.

### Procedure E: "failed validation" (🔴)

```
## 🔴 PHAC-NWMP: submission 413 failed validation (8 errors)
- See what failed: https://dev.virusseq-dataportal.ca/submission/environmental/413
```

1. Open the link and look at the **Status** column. It shows which records failed and why.
2. **Don't try to fix the data by hand on the website.** Send the data team:
   - the link;
   - the `Log:` path from `msg.md`;
   - a screenshot of the errors.
3. While it stays INVALID, the weekly run won't upload anything new for that source, and
   `msg.md` keeps reminding you. Once the data team fixes and re-uploads it, do Steps 3–4 as
   normal.

### Procedure F: "missing values" (FYI line)

```
- FYI: The parser could not resolve some values and left them blank. Please supply them ...: coordinates: ['Somewhere, Yukon']
```

The source data had something new the tool doesn't know yet, often a new city whose map position
it couldn't find. Those records were still uploaded, with that one value left blank. Send the line
to the data team, who will add the missing value. Nothing else is needed from you.

### Procedure G: "revised values" (FYI line)

```
- FYI: 3 already-published records have revised values at the source; they were not re-uploaded ...
```

The source changed numbers for records that are already published. The tool never overwrites
published records. Pass the line on to the data team if the corrections matter. Otherwise no
action is needed.

### Procedure H: "stopped, N new records is over the limit" (🔴)

The tool found far more new records than a normal week. This is a safety stop: it usually means
the source changed its format, and uploading would create duplicates. **Don't use `--force`
yourself.** Send the `msg.md` section to the data team.

### Procedure I: "run failed during …" (🔴)

Something broke: the internet, the portal being down, the login, or a change at the source. Try
once more later with Procedure A. If it fails again, send the data team the whole 🔴 section of
`msg.md` and the `Log:` file it names.

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
| `msg.md` didn't change | The run didn't happen | Run it by hand (Procedure A) and check that the schedule is still set up |

## When to ask for help

Contact the data team if:

- the same 🔴 message appears two runs in a row;
- anything on the website looks wrong before you commit, such as odd dates, blank values or wrong
  places;
- you see a long block of text mentioning `Traceback`. Copy all of it and send it along.

**Never** edit the files ending in `.py` or `.sh`, and never commit on the website if you're
unsure. An uncommitted submission does no harm; it just waits.
