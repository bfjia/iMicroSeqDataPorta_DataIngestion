# Standard operating procedure: adding a new data source

This procedure takes a new data source from "we'd like this data on the portal" to "it uploads by
itself every week". It covers the test (dev) portal first, then the real (prod) one.

It's for the person on the data team who sets the source up. You'll write a small Python
converter, so you need to be comfortable editing Python and using the terminal. Running the tool
week to week is a separate procedure: [SOP_weekly_upload.md](SOP_weekly_upload.md).

> **Nothing in this procedure publishes anything.** The tool only uploads and validates. Records
> become public only when a person presses commit on the portal website.

---

## Who does what

| Who | Does |
|---|---|
| **You** (data team) | The folder, the converter, the settings, the test runs (Steps 1–13) |
| **Data owner** | Agrees to the data going on the portal, and to the first load on each portal |
| **Portal administrators** | Create the source's organization on each portal and give the tool's accounts write permission (Step 5) |
| **Operator** | Reviews and commits each submission on the website ([SOP_weekly_upload.md](SOP_weekly_upload.md), Steps 3–4) |

## Before you start

- **The source:** where the data is downloaded from, how often it's updated, its terms of use,
  and what one row means.
- **The data owner's agreement** to put it on the portal.
- **The tool set up** as in [SOP_weekly_upload.md](SOP_weekly_upload.md), "Before you start": the `ProjectIngestion` conda
  env, and `upload_workflow/.env` with both portal logins.
- **Three names:**

  | Name | What it's for | Example (PHAC) |
  |---|---|---|
  | Folder name | Used in every command, e.g. `./run_initial_upload.sh PHAC`. Short, no spaces, not starting with `_`. | `PHAC` |
  | `SOURCE_ID` | Names the run folders and the source in messages | `PHAC-NWMP` |
  | Organization, per portal | Who the records are submitted as. **Each portal names it differently.** Agree the names with the portal administrators. | dev `PHAC-AUTOINGEST`, prod `PHAC-NWMP` |

In the commands below, replace `<NAME>` with your folder name.

## The steps at a glance

1. Copy the template
2. Write the converter
3. Write `etl.sh`
4. Fill in `source.conf`
5. Get write permission on both portals
6. Test the ETL on its own
7. Dry run on dev
8. First load on dev
9. Confirm nothing is new
10. Turn on weekly runs for dev
11. Prod: dry run and first load
12. Turn on prod
13. Document it and save it to git

There's a checklist at the end.

---

## Step 1. Copy the template

```bash
cd /mnt/d/OneDrive/ProjectIngestion
conda activate ProjectIngestion
cp -r data_ETL/_template data_ETL/<NAME>
```

You now have:

| Path | What goes in it |
|---|---|
| `data_ETL/<NAME>/source.conf` | The source's settings (Step 4) |
| `data_ETL/<NAME>/etl.sh` | Download → convert → remove duplicates (Step 3) |
| `data_ETL/<NAME>/scripts/` | Your converter (Step 2) |
| `data_ETL/<NAME>/raw/`, `curated/` | The downloaded and converted files. They're never saved to git. |
| `data_ETL/<NAME>/README.md` | The source's description (Step 13) |

## Step 2. Write the converter

Write a Python script in `data_ETL/<NAME>/scripts/` that reads the downloaded file and writes
**one iMicroSeq row per record**. Use [data_ETL/PHAC/scripts/parser.py](../data_ETL/PHAC/scripts/parser.py)
as the model: one explicit line per iMicroSeq field.

Follow these rules. Each one prevents a specific failure later:

- **Use the 163 iMicroSeq column titles, exactly.** They're the `title` column of
  `data_specification/fields.tsv`, e.g. `specimen collector sample ID`. The easiest way is to copy
  the `columnNames` list from the PHAC parser.
- **Fill every required field.** These are the 14 fields with `required` = `TRUE` in
  `fields.tsv`. Otherwise the portal rejects the records.
- **Use picklist values exactly as listed, with their ontology ID**, e.g.
  `Not Provided [GENEPIO:0001668]`. A field's `range` column in `fields.tsv` names its picklist,
  e.g. `PurposeOfSamplingMenu`. Find that name in the `name` column of
  `data_specification/enums.tsv`; the allowed values are in the `menu_1` column of the rows below
  it.
- **Write lookups as dictionaries inside the script**, e.g. province name → GAZ term. Don't read
  them from other files when the script runs.
- **Never guess a value.** If one can't be worked out, leave it blank and print a line starting
  with `[MISSING]`:

  ```
  [MISSING] coordinates: ['Somewhere, Yukon'] — please provide values
  ```

  These lines show up in `msg.md`, so someone can supply the value.
- **Make sample IDs unique and stable.** `specimen collector sample ID` must be different for
  every record, and the same record must get the same ID every week.
  - Build it from things that don't change, like the collection date, site and target. PHAC uses
    `PHAC_{weekstart}_{Location}_{measureid}`.
  - Never use row numbers or today's date.
  - If IDs change from week to week, every record looks new and gets uploaded again.
- **Python only, and only inside this folder.** Don't use system temp directories.

## Step 3. Write `etl.sh`

Edit `data_ETL/<NAME>/etl.sh`. It does three things: download, convert, remove duplicates. For
example:

```bash
# 1. Download (to .part first, so a failed download never leaves half a file)
curl -fSL --retry 3 -o "${HERE}/raw/data.csv.part" "https://example.org/data.csv"
mv "${HERE}/raw/data.csv.part" "${HERE}/raw/data.csv"

# 2. Convert
python "${HERE}/scripts/parser.py" --input "${HERE}/raw/data.csv" --output "${HERE}/curated/<NAME>.csv"

# 3. Remove duplicate sample IDs, if the source can repeat a record
```

Then **delete the two placeholder lines at the end** (`echo "TODO: …"` and `exit 1`).

It must:

- take no arguments;
- write the file that `UPLOAD_CSV` names in `source.conf` (Step 4);
- give **exactly one row per sample ID**. If the source repeats records, remove the duplicates
  here, like PHAC's `scripts/dedup_records.py`;
- stop with an error if anything fails. Keep the `set -euo pipefail` line at the top; it does
  this.

## Step 4. Fill in `source.conf`

Open `data_ETL/<NAME>/source.conf` and replace every `TODO`:

```bash
SOURCE_ID="BCCDC-WW"                      # names run folders and messages
UPLOAD_CSV="curated/BCCDC-WW.csv"         # the file etl.sh writes
MAX_NEW=2000                              # safety limit, see below
ENABLED=0                                 # keep 0 until Step 10

ORGANIZATION_DEV="BCCDC-AUTO"             # the organization on dev
ORGANIZATION_PROD="BCCDC-WW"              # the organization on prod
CATEGORY_DEV="imicroseq_wastewater"       # leave as is for wastewater data
CATEGORY_PROD="imicroseq_environmental"   # leave as is for wastewater data
```

- **Organizations.** Both are required, and each portal has its own name, so the tool never
  submits to the wrong one.
  - The organization is the portal permission's name without the `WW-` at the front: the
    permission `WW-BCCDC-WW.WRITE` means organization `BCCDC-WW`.
  - Capital letters matter.
- **`MAX_NEW`.** A run that finds more new records than this stops without uploading. It catches
  a source that suddenly changes its sample IDs. Set it well above a normal week (PHAC brings
  ~215 a week and uses 500). The first load is allowed past it with `--force`.
- **Categories.** Leave them as they are for wastewater data. The two portals call the same
  category by different names.
- **Edits (optional).** When the source revises records that are already published, each run
  sends those as edits, in the same submission as the new records. That's on by default. To only
  report them instead, add `EDIT_REVISED=0`. A run that finds more revised records than
  `MAX_EDITS` (default 2,000) stops with an error; add `MAX_EDITS=…` to change the limit for this
  source.

## Step 5. Get write permission on both portals

Ask the portal administrators to:

1. create the source's organization on each portal, if it doesn't exist yet;
2. give the **dev** account (`devPortalUser` in `upload_workflow/.env`) the permission
   `WW-<dev organization>.WRITE` on dev;
3. give the **prod** account (`prodPortalUser`) the permission `WW-<prod organization>.WRITE` on
   prod.

Then check:

```bash
./list_sources.sh --check
```

This logs in to both portals (uploading nothing) and shows every source. Your source's two rows
need `yes` in the last column:

```
SOURCE     ID           PORTAL ENABLED  ORGANIZATION         CATEGORY                  CAN_WRITE
BCCDC      BCCDC-WW     dev    no       BCCDC-AUTO           imicroseq_wastewater      yes
BCCDC      BCCDC-WW     prod   no       BCCDC-WW             imicroseq_environmental   yes
```

| You see | Means | Do this |
|---|---|---|
| `NO` | The permission isn't there yet, or the name in `source.conf` is spelled differently (capitals matter) | Compare with the administrators' name; ask again if it matches |
| `(not set)` | `ORGANIZATION_DEV` or `ORGANIZATION_PROD` is missing | Step 4 |
| `login failed` | Wrong password for that portal in `.env` | Fix `devPortalPass` / `prodPortalPass` |

You can carry on with Steps 6 and 7 while you wait. They only warn about a missing permission.

## Step 6. Test the ETL on its own

```bash
bash data_ETL/<NAME>/etl.sh
```

It should finish without an error and write the `UPLOAD_CSV` file. Then run three checks.
`<file>` below is that file, e.g. `data_ETL/<NAME>/curated/BCCDC-WW.csv`.

1. **Columns.** This renames the columns the way the upload does, using the portal's live
   dictionary. Nothing is uploaded:

   ```bash
   python upload_workflow/step4_transform.py --input <file> --output-dir runs/check/<NAME>
   rm -rf runs/check/<NAME>
   ```

   - **Good:** it ends with `"rows": <number>`.
   - **Bad:** `RuntimeError: 2 column(s) … are not in the 'sample' dictionary: [...]`. Fix those
     column titles in the converter.

2. **Duplicate sample IDs:**

   ```bash
   python -c "import csv,collections,sys; ids=[r['specimen collector sample ID'] for r in csv.DictReader(open(sys.argv[1],encoding='utf-8-sig'))]; d=[i for i,c in collections.Counter(ids).items() if c>1]; print(len(ids),'rows,',len(d),'duplicated IDs',d[:5])" <file>
   ```

   - **Good:** `0 duplicated IDs`.
   - **Bad:** any other number. Remove the duplicates in `etl.sh` (Step 3).

3. **Missing values.** Look for `[MISSING]` lines in the ETL's output. Supply what you can in
   the converter (Step 2).

## Step 7. Dry run on dev

```bash
./run_initial_upload.sh <NAME> --dry-run
cat msg.md
```

This does everything except the upload: login, the open-submission check, the ETL, the dev date
window (weeks from 2026-09-01), and the comparison with what's already published.

| `msg.md` says | Means | Do this |
|---|---|---|
| 🟢 *dry run, nothing sent* with a *New: N records* line | It works | Open the `delta.csv` it names and spot-check a few rows. Go to Step 8. |
| 🔴 *stopped: too many new records* | More than `MAX_NEW`, which is normal for a first load | Run `./run_initial_upload.sh <NAME> --dry-run --force` to see the full count |
| 🔴 *run failed during ETL* | `etl.sh` stopped with an error | Open the `Log:` file, fix it, repeat Step 6 |
| 🔴 *run failed during diff* | Duplicate sample IDs | Step 3 |
| 🔴 *run failed during date window* | No records from 2026-09-01 on | Check the dates the converter writes in `sample collection start date` (YYYY-MM-DD) |
| *FYI: the account can't write to …* | Missing permission | Step 5 |

## Step 8. First load on dev

Agree it with the data owner first. Then:

```bash
./run_initial_upload.sh <NAME> --force
cat msg.md
```

`--force` lets the first load go past `MAX_NEW`. The tool uploads and validates; nothing is
published yet.

- 🟡 **Passed validation:** review and commit it on the dev website, as in [SOP_weekly_upload.md](SOP_weekly_upload.md)
  Steps 3–4.
- 🔴 **Failed validation:**
  1. Open the link in `msg.md` to see which records and fields failed. For the same list in the
     terminal:

     ```bash
     python upload_workflow/step6_validate.py --submission-id <number> --details
     ```

  2. Fix the converter. The usual causes:
     - a picklist value that isn't exactly as in `enums.tsv`;
     - a required field left blank;
     - text in a number field.
  3. Close the failed submission and try again:

     ```bash
     ./close_submission.sh <NAME>
     ./run_initial_upload.sh <NAME> --force
     ```

## Step 9. Confirm nothing is new

After the commit, run another dry run:

```bash
./run_initial_upload.sh <NAME> --dry-run
```

It must say 🟢 *nothing new* (*N records checked*). That proves the sample IDs are stable and the
published records match what was sent.

If it finds new records again, or edits for records you just committed, something in the IDs or
values changes from run to run. Fix it before going on (Step 2).

## Step 10. Turn on weekly runs for dev

In `source.conf`, change `ENABLED=0` to these two lines:

```bash
ENABLED=1
ENABLED_PROD=0
```

`ENABLED_PROD=0` keeps the source out of prod runs until Step 12. Check with
`./list_sources.sh`: `ENABLED` should be `yes` for dev and `no` for prod. The weekly run
(`./run_weekly_update.sh`) now includes the source.

## Step 11. Prod: dry run and first load

Prod has **no date window**, so it gets the source's full history.

1. **Dry run.** This shows how many records there are and how they'd be split into chunks of
   10,000:

   ```bash
   ./run_initial_upload.sh <NAME> --env prod --chunk --dry-run
   cat msg.md
   ```

2. **First load**, once the data owner agrees for prod. Upload it in chunks. Each chunk is its own
   submission, and the script asks before each one:

   ```bash
   ./run_initial_upload.sh <NAME> --env prod --chunk
   ```

   For a small source (under 2,000 records) `--force` instead of `--chunk` uploads it in one go.
3. **Review and commit each chunk on the prod website** (`imicroseq-dataportal.ca`) before
   typing `yes` for the next one. How the questions work is in
   [SOP_weekly_upload.md](SOP_weekly_upload.md), Procedure C. **Committing on prod publishes the
   records for real.**
4. **Confirm nothing is new:**

   ```bash
   ./run_initial_upload.sh <NAME> --env prod --dry-run
   ```

   It must say 🟢 *nothing new*.

If a prod run stops with *waiting for your commit* for a submission you don't recognize, an
older submission is open for that organization. Find it and close it with [SOP_weekly_upload.md](SOP_weekly_upload.md)
Procedures K and L, adding `--env prod`.

## Step 12. Turn on prod

Delete the line `ENABLED_PROD=0` from `source.conf`. Then run `./list_sources.sh --check`. Your
source should show `ENABLED yes` and `CAN_WRITE yes` on both portals.

The scheduled weekly run on GitHub runs **prod** ([SOP_weekly_upload.md](SOP_weekly_upload.md),
Procedure J). From the next Monday on, it uploads your source's new records to prod. Dev isn't
scheduled. To check the source on dev, use the **Dev test upload** workflow (Procedure J1) or run
it locally. First add the source's folder name to the `source` options in
`.github/workflows/dev_test.yml`.

## Step 13. Document it and save it to git

1. **Write the source's README.** Replace `data_ETL/<NAME>/README.md`; the template's README lists
   what to cover. Use [data_ETL/PHAC/README.md](../data_ETL/PHAC/README.md) as the model.
2. **Add the source to the table** at the top of [data_ETL/README.md](../data_ETL/README.md).
3. **Save the code and settings to git:**

   ```bash
   git add data_ETL/<NAME> data_ETL/README.md
   git status
   git commit -m "Add the <NAME> data source"
   git push
   ```

   Before you commit, check that `git status` lists **no** data or secrets. That means nothing from
   `raw/` or `curated/` (only their `.gitkeep`), nothing from `runs/`, no `msg.md`, and no
   `upload_workflow/.env`. These are set to be ignored, but always look.

---

## Checklist

- [ ] The data owner agreed
- [ ] `data_ETL/<NAME>/` copied from the template
- [ ] Converter: the 163 column titles, required fields filled, exact picklist values, stable and unique sample IDs, `[MISSING]` for unknowns
- [ ] `etl.sh`: download → convert → remove duplicates; the placeholder lines deleted
- [ ] `source.conf`: `SOURCE_ID`, `UPLOAD_CSV`, `MAX_NEW`, `ORGANIZATION_DEV`, `ORGANIZATION_PROD`
- [ ] `./list_sources.sh --check`: `CAN_WRITE yes` on dev and prod
- [ ] Column and duplicate checks pass (Step 6)
- [ ] Dev dry run looks right (Step 7)
- [ ] Dev first load committed on the website (Step 8)
- [ ] Dev dry run says *nothing new* (Step 9)
- [ ] `ENABLED=1` and `ENABLED_PROD=0` (Step 10)
- [ ] Prod first load committed; prod dry run says *nothing new* (Step 11)
- [ ] `ENABLED_PROD=0` deleted (Step 12)
- [ ] README written, `data_ETL/README.md` table updated, pushed to git (Step 13)

## When the source doesn't fit the pattern

- **It isn't a simple file download** (an API, a login, a spreadsheet): handle it in `etl.sh`
  with bash and Python. If it can't be done that way, talk to the data team first.
- **It isn't wastewater data:** set `CATEGORY_DEV` and `CATEGORY_PROD` to the right category's
  name on each portal. Ask the portal administrators which one.
- **The source revises old records:** revisions are sent as edits to the published records, for a
  person to review and commit (Step 4, "Edits"). `run_edits.sh` sends a big batch of them on its
  own, after asking.
- **You need different settings per portal:** `CATEGORY`, `MAX_NEW`, `ENABLED`, `EDIT_REVISED`
  and `MAX_EDITS` all accept a `_DEV` or `_PROD` suffix, which wins on that portal.

Technical background is in [data_ETL/README.md](../data_ETL/README.md) (the source contract) and
[how_a_run_works.md](how_a_run_works.md).
