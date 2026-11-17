"""Write the run's notification digest, msg.md (slack_post.py posts it to Slack).

One message per run, never one per step. run_initial_upload.sh leaves a status.env in
each source's run folder; this reads them all and writes a single Markdown
digest:

  * a headline with the worst status across sources and the run time:
        🔴 problem  >  🟡 action needed  >  🟢 all good
  * one block per source, worst first: a bold headline with its own dot and
    status, then one labelled line per group (New, Edits, Submission), FYI
    lines, and the submission link if there is one:

        **🟡 PHAC-NWMP · review and commit**
        - New: 223 records, weeks 2026-10-11 to 2026-10-25
        - Edits: 69 published records (diagnostic measurement value 1)
        - Submission 463: VALID, 0 errors
        https://dev.virusseq-dataportal.ca/submission/environmental/463

  * FYI lines (missing parser values, revised records that weren't sent as
    edits, test hold-backs) never change the headline on their own;
  * problems add the last log lines (failed steps) and the log path.

Kept short on purpose. A quiet week still produces one line per source, so
silence never has to be read as "did it run?". The file is plain Markdown; slack_post.py converts it for
Slack.

    python notify.py --run-dir runs/20261030-081500 --out runs/20261030-081500/msg.md --copy-to msg.md
"""

import argparse
import csv
import datetime
import os
import shutil

from common import PortalEnv

RepoDir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DateColumn = "sample collection start date"

# status -> (level, ...). Level decides the headline: problem > action > ok.
Levels = {
    "failed": "problem",
    "guard": "problem",
    "edit_guard": "problem",
    "invalid": "problem",
    "waiting_invalid": "problem",
    "review": "action",
    "waiting": "action",
    "paused": "action",
    "nothing_new": "ok",
    "nothing_to_edit": "ok",
    "cancelled": "ok",
    "dry_run": "ok",
}
Icons = {"problem": "🔴", "action": "🟡", "ok": "🟢"}
Rank = {"problem": 0, "action": 1, "ok": 2}


def readStatus(path):
    """Read KEY=value lines; a later line for the same key wins."""
    status = {}
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            line = line.rstrip("\n")
            if "=" in line:
                key, value = line.split("=", 1)
                status[key] = value
    return status


def num(value):
    """'1977' -> '1,977'; anything else is returned unchanged."""
    try:
        return f"{int(value):,}"
    except (TypeError, ValueError):
        return value or "?"


def rel(path):
    return os.path.relpath(path, RepoDir) if path else ""


def dateRange(csvPath):
    """Return (first, last) collection start date in a CSV, or None."""
    if not csvPath or not os.path.exists(csvPath):
        return None
    with open(csvPath, newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        dates = sorted(r[DateColumn] for r in reader if r.get(DateColumn))
    return (dates[0], dates[-1]) if dates else None


def waitedFor(createdAt):
    """'2026-10-30T15:12:00.000Z' -> 'open since today' / 'open 5 days'."""
    try:
        created = datetime.datetime.fromisoformat(createdAt.replace("Z", "+00:00"))
    except (AttributeError, ValueError):
        return f"open since {createdAt or 'an unknown date'}"
    days = (datetime.datetime.now(datetime.timezone.utc) - created).days
    if days < 1:
        return "open since today"
    return f"open {days} day{'s' if days != 1 else ''}"


def logTail(path, lines=6):
    if not path or not os.path.exists(path):
        return ""
    with open(path, encoding="utf-8", errors="replace") as handle:
        content = [l.rstrip() for l in handle if l.strip() and "\r" not in l]
    return "\n".join(content[-lines:])


def span(csvPath):
    """'week 2026-10-18' / 'weeks 2026-09-06 to 2026-10-11' / ''."""
    rng = dateRange(csvPath)
    if not rng:
        return ""
    return f"week {rng[0]}" if rng[0] == rng[1] else f"weeks {rng[0]} to {rng[1]}"


def editFields(folder, counts=False, top=3):
    """The fields the edits change, most changed first, from edit_fields.csv:
    'diagnostic measurement value 1' or, with counts, 'geo loc name (site) (2,500), ...'."""
    path = os.path.join(folder, "edit_fields.csv")
    if not os.path.exists(path):
        return ""
    with open(path, newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    shown = [f"{r['field']} ({num(r['records_changed'])})" if counts else r["field"] for r in rows[:top]]
    more = f", +{len(rows) - top} more" if len(rows) > top else ""
    return ", ".join(shown) + more


def section(s, folder):
    """Render one source as a block (returns (level, md)):

        **🟡 PHAC-NWMP · review and commit**
        - New: 223 records, weeks 2026-10-11 to 2026-10-25
        - Edits: 69 published records (diagnostic measurement value 1)
        - Submission 463: VALID, 0 errors
        https://...

    A bold headline with the status, one labelled line per group, FYI lines,
    then the link. Problems add the last log lines and the log path.
    """
    status = s.get("STATUS", "failed")
    level = Levels.get(status, "problem")
    name = s.get("SOURCE_ID", os.path.basename(folder))
    source, env = s.get("SOURCE_NAME", "<SOURCE>"), s.get("PORTAL_ENV", "dev")
    sid, url = s.get("SUBMISSION_ID", ""), s.get("SUBMISSION_URL", "")
    newN, edits = s.get("NEW", "0") or "0", s.get("EDITS", "0") or "0"
    editsOnly = s.get("EDITS_ONLY") == "1"
    delta = os.path.join(folder, "delta.csv")
    closeCmd = f"`./close_submission.sh {source} --env {env}`"
    # Chunked first load (run_initial_upload.sh --chunk)
    total, done, left = s.get("CHUNK_TOTAL", ""), s.get("CHUNK_DONE", "0"), s.get("CHUNK_LEFT", "0")
    again = f"`./run_initial_upload.sh {source} --env {env} --chunk`"
    chunkOf = f"chunk {s.get('CHUNK_NUMBER', done)} of {total}" if total else ""

    newLine = ""
    if newN != "0" and not editsOnly:
        when = span(delta)
        newLine = f"New: {num(newN)} records" + (f", {when}" if when else "")
    editsLine = ""
    if edits != "0":
        changed = editFields(folder)
        editsLine = f"Edits: {num(edits)} published records" + (f" ({changed})" if changed else "")
    sent = [l for l in (newLine, editsLine) if l]
    lines, link = [], ""

    if status == "review" and total:
        head = f"{chunkOf}: review and commit"
        first, last = s.get("CHUNK_FIRST", ""), s.get("CHUNK_LAST", "")
        when = f"week {first}" if first == last else f"weeks {first} to {last}"
        lines = [f"New: {num(s.get('CHUNK_ROWS'))} records, {when}",
                 f"Submission {sid}: VALID, {num(s.get('ERRORS', '0'))} errors"]
        if left not in ("", "0"):
            lines.append(f"Still to upload: {num(left)} records. After committing, run {again}")
        link = url
    elif status == "paused":
        head = "chunked upload paused"
        lines = [f"{done} of {total} chunks uploaded; {num(left)} records still to upload",
                 f"To continue: {again}"]
    elif status == "review":
        head = "review and commit"
        lines = sent + [f"Submission {sid}: VALID, {num(s.get('ERRORS', '0'))} errors"]
        link = url
    elif status == "waiting":
        head = "waiting for your commit"
        lines = [f"Submission {sid}, {waitedFor(s.get('PENDING_CREATED', ''))}. Nothing new uploaded."]
        link = url
    elif status == "waiting_invalid":
        head = "an earlier submission failed validation"
        lines = [f"Submission {sid}, {waitedFor(s.get('PENDING_CREATED', ''))}",
                 f"Fix the cause, then {closeCmd} and run again"]
        link = url
    elif status == "invalid":
        head = "failed validation"
        lines = sent + [f"Submission {sid}{' (' + chunkOf + ')' if total else ''}: INVALID, "
                        f"{num(s.get('ERRORS'))} errors",
                        f"Fix the cause, then {closeCmd} and run again"]
        link = url
    elif status == "guard":
        head = "stopped: too many new records"
        lines = [f"{num(newN)} new records; the limit is {num(s.get('MAX_NEW'))}. Nothing uploaded.",
                 "Likely a sample-ID change. If expected, re-run with `--force`."]
    elif status == "edit_guard":
        head = "stopped: too many edits"
        lines = [f"{num(edits)} published records were revised; the limit is "
                 f"{num(s.get('MAX_EDITS'))}. Nothing uploaded.",
                 f"What changed: {editFields(folder, counts=True) or 'see edit_fields.csv'}",
                 f"If expected: `./run_edits.sh {source} --env {env}`"]
    elif status == "nothing_new":
        head = "nothing new"
        lines = [f"{num(s.get('IN_SCOPE'))} records checked"]
    elif status == "nothing_to_edit":
        head = "nothing to edit"
        lines = [f"{num(s.get('IN_SCOPE'))} records checked"]
    elif status == "cancelled":
        head = "edits not sent"
        lines = [f"Stopped at the confirmation; the {num(edits)} edits are in "
                 f"`{rel(os.path.join(folder, 'edits.csv'))}`"]
    elif status == "dry_run":
        head = "dry run, nothing sent"
        lines = list(sent)
        if total:
            lines.append(f"In {total} chunks of up to {num(s.get('CHUNK_SIZE'))}")
        files = ([delta] if newLine else []) + ([os.path.join(folder, "edits.csv")] if editsLine else [])
        if files:
            lines.append("Files: " + ", ".join(f"`{rel(f)}`" for f in files))
        if not sent:
            lines.append("Nothing to upload")
    else:  # failed
        head = f"run failed during {s.get('STEP', 'an unknown step')}"
        lines = [s.get("REASON", "")]

    # FYI lines: worth knowing, but never a reason to change the headline.
    changed = s.get("CHANGED", "0")
    if changed not in ("", "0") and edits == "0":
        # Revised records that weren't sent as edits: edits are off for this
        # source, or a --chunk first load (which doesn't send edits).
        how = (f"send them with `./run_edits.sh {source} --env {env}`" if s.get("EDIT_REVISED") == "1"
               else "edits are off for this source")
        lines.append(f"FYI: {num(changed)} published records were revised at the source, not sent "
                     f"({how}; `{rel(os.path.join(folder, 'changed.csv'))}`)")
    if editsOnly and newN != "0":
        lines.append(f"FYI: {num(newN)} new records were not sent; the weekly run uploads them")
    missingPath = os.path.join(folder, "missing.txt")
    if os.path.exists(missingPath):
        with open(missingPath, encoding="utf-8") as handle:
            missing = [l.strip() for l in handle if l.strip()]
        if missing:
            lines.append("FYI: missing values, please supply: " + "; ".join(missing))
    if s.get("NO_WRITE_SCOPE") == "1":
        lines.append(f"FYI: the account can't write to {s.get('ORGANIZATION', 'this organization')} "
                     "on this portal yet; a real run would stop")
    held = s.get("HELD_OUT", "0")
    if held not in ("", "0"):
        lines.append(f"FYI: test mode, {num(held)} records held back")

    out = [f"**{Icons[level]} {name} · {head}**"] + [f"- {l}" for l in lines if l]
    if link:
        out.append(link)
    if status == "failed":
        tail = logTail(s.get("LOG"))
        if tail:
            out += ["```", tail, "```"]
    if level == "problem" and s.get("LOG"):
        out.append(f"Log: `{rel(s['LOG'])}`")
    return level, "\n".join(out)


def build(runDir):
    folders = sorted(
        os.path.join(runDir, d) for d in os.listdir(runDir)
        if os.path.isfile(os.path.join(runDir, d, "status.env"))
    )
    env = PortalEnv
    stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

    if not folders:
        return (f"# 🔴 iMicroSeq ({env}): problem · {stamp}\n\n"
                f"No source reported a status; check `{rel(runDir)}`.\n")

    sections = [section(readStatus(os.path.join(f, "status.env")), f) for f in folders]
    worst = min((lvl for lvl, _ in sections), key=Rank.get)
    title = {"problem": "problem", "action": "action needed", "ok": "all good"}[worst]

    parts = [f"# {Icons[worst]} iMicroSeq ({env}): {title} · {stamp}"]
    parts += [md for _, md in sorted(sections, key=lambda x: Rank[x[0]])]
    return "\n\n".join(parts) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run-dir", required=True, help="runs/<stamp> folder to summarize")
    ap.add_argument("--out", required=True, help="Where to write the digest")
    ap.add_argument("--copy-to", default=None, help="Also copy it here (e.g. the repo's msg.md)")
    args = ap.parse_args(argv)

    text = build(args.run_dir)
    with open(args.out, "w", encoding="utf-8") as handle:
        handle.write(text)
    if args.copy_to:
        shutil.copyfile(args.out, args.copy_to)
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
