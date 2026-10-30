"""Write the run's notification digest, msg.md (slack_post.py posts it to Slack).

One message per run, never one per step. run_source.sh leaves a status.env in
each source's run folder; this reads them all and writes a single Markdown
digest:

  * a headline with the worst status across sources:
        🔴 problem  >  🟡 action needed  >  🟢 all good
  * one section per source, showing only that source's most important status;
  * FYI lines inside a section (unresolved parser values, revised records,
    test hold-backs) that never change the headline on their own.

A quiet week still produces one short message, so silence never has to be read
as "did it run?". The file is plain Markdown; slack_post.py converts it for
Slack.

    python notify.py --run-dir runs/20261030-081500 --out runs/20261030-081500/msg.md --copy-to msg.md
"""

import argparse
import csv
import datetime
import os
import shutil

from common import DefaultBaseURL

RepoDir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DateColumn = "sample collection start date"

# status -> (level, ...). Level decides the headline: problem > action > ok.
Levels = {
    "failed": "problem",
    "guard": "problem",
    "invalid": "problem",
    "waiting_invalid": "problem",
    "review": "action",
    "waiting": "action",
    "nothing_new": "ok",
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
    """'2026-10-30T15:12:00.000Z' -> ('2026-10-30', 5) or (raw, None)."""
    try:
        created = datetime.datetime.fromisoformat(createdAt.replace("Z", "+00:00"))
    except (AttributeError, ValueError):
        return createdAt or "an unknown date", None
    days = (datetime.datetime.now(datetime.timezone.utc) - created).days
    return created.date().isoformat(), days


def logTail(path, lines=12):
    if not path or not os.path.exists(path):
        return ""
    with open(path, encoding="utf-8", errors="replace") as handle:
        content = [l.rstrip() for l in handle if l.strip() and "\r" not in l]
    return "\n".join(content[-lines:])


def section(s, folder):
    """Render one source's section. Returns (level, markdown)."""
    status = s.get("STATUS", "failed")
    level = Levels.get(status, "problem")
    source = s.get("SOURCE_ID", os.path.basename(folder))
    sid = s.get("SUBMISSION_ID", "")
    url = s.get("SUBMISSION_URL", "")
    new = num(s.get("NEW"))
    out = []

    if status == "review":
        rng = dateRange(os.path.join(folder, "delta.csv"))
        weeks = f" (collection weeks {rng[0]} to {rng[1]})" if rng else ""
        out += [
            f"## {Icons[level]} {source}: review and commit submission {sid}",
            f"**{new} new records**{weeks} passed validation and are waiting for you. "
            "Nothing is published until you commit it on the website.",
            f"- Review and commit: {url}",
        ]
    elif status in ("waiting", "waiting_invalid"):
        since, days = waitedFor(s.get("PENDING_CREATED", ""))
        age = f" ({days} day{'s' if days != 1 else ''})" if days is not None else ""
        if status == "waiting":
            out += [
                f"## {Icons[level]} {source}: submission {sid} is still waiting for your commit",
                f"Open since {since}{age}. Nothing new was uploaded this run. New records go up "
                "on the first run after you commit it.",
                f"- Review and commit: {url}",
            ]
        else:
            out += [
                f"## {Icons[level]} {source}: submission {sid} failed validation and is still open",
                f"Open since {since}{age}. Nothing new is uploaded until it is resolved: fix the "
                "data and re-upload with `--replace`, or discard it on the website.",
                f"- See what failed: {url}",
                "- How: SOP.md, \"Validation failed\"",
            ]
    elif status == "invalid":
        out += [
            f"## {Icons[level]} {source}: submission {sid} failed validation "
            f"({num(s.get('ERRORS'))} errors)",
            f"{new} records were uploaded but did not validate. Nothing was published.",
            f"- See what failed: {url}",
            "- How: SOP.md, \"Validation failed\"",
        ]
    elif status == "guard":
        out += [
            f"## {Icons[level]} {source}: stopped, {new} new records is over the limit of "
            f"{num(s.get('MAX_NEW'))}",
            "A normal week brings a few hundred. A jump like this usually means the source "
            "changed how sample IDs are built, which would re-upload old data under new IDs. "
            "Nothing was uploaded. If the number is expected, re-run with `--force`.",
        ]
    elif status == "nothing_new":
        out += [
            f"## {Icons[level]} {source}: nothing new",
            f"{num(s.get('IN_SCOPE'))} records checked, all already published.",
        ]
    elif status == "dry_run":
        rng = dateRange(os.path.join(folder, "delta.csv"))
        weeks = f" (collection weeks {rng[0]} to {rng[1]})" if rng else ""
        out += [
            f"## {Icons[level]} {source}: dry run, nothing uploaded",
            f"**{new} new records**{weeks} would be uploaded "
            f"(list: `{rel(os.path.join(folder, 'delta.csv'))}`).",
        ]
    else:  # failed
        step = s.get("STEP", "an unknown step")
        reason = s.get("REASON", "")
        out += [f"## {Icons[level]} {source}: run failed during {step}"]
        if reason:
            out.append(reason)
        tail = logTail(s.get("LOG"))
        if tail:
            out += ["Last lines of the log:", "```", tail, "```"]

    # FYI lines: worth knowing, but never a reason to change the headline.
    fyi = []
    changed = s.get("CHANGED", "0")
    if changed not in ("", "0"):
        fyi.append(f"{num(changed)} already-published records have revised values at the source; "
                   f"they were not re-uploaded (list: `{rel(os.path.join(folder, 'changed.csv'))}`).")
    missingPath = os.path.join(folder, "missing.txt")
    if os.path.exists(missingPath):
        with open(missingPath, encoding="utf-8") as handle:
            missing = [l.strip() for l in handle if l.strip()]
        if missing:
            fyi.append("The parser could not resolve some values and left them blank. "
                       "Please supply them (SOP.md, \"Missing values\"): " + "; ".join(missing))
    held = s.get("HELD_OUT", "0")
    if held not in ("", "0"):
        fyi.append(f"Test mode: {num(held)} records were held back on purpose "
                   f"(`{rel(os.path.join(folder, 'heldout.csv'))}`).")
    cutoff = s.get("CUTOFF", "")
    if cutoff and status in ("review", "dry_run"):
        fyi.append(f"Dev window: only collection weeks from {cutoff} on are uploaded.")
    out += [f"- FYI: {line}" for line in fyi]

    if s.get("LOG"):
        out.append(f"- Log: `{rel(s['LOG'])}`")
    return level, "\n".join(out)


def build(runDir):
    folders = sorted(
        os.path.join(runDir, d) for d in os.listdir(runDir)
        if os.path.isfile(os.path.join(runDir, d, "status.env"))
    )
    env = "dev" if ".dev." in DefaultBaseURL else "prod"
    stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

    if not folders:
        return ("# 🔴 iMicroSeq ingestion (" + env + "): run produced no results\n\n"
                f"Run {stamp}. No source reported a status; check `{rel(runDir)}`.\n")

    sections = [section(readStatus(os.path.join(f, "status.env")), f) for f in folders]
    worst = min((lvl for lvl, _ in sections), key=Rank.get)
    title = {"problem": "a problem needs attention",
             "action": "action needed",
             "ok": "all good"}[worst]
    counts = {lvl: sum(1 for l, _ in sections if l == lvl) for lvl in Rank}
    summary = (f"Run {stamp} · {len(sections)} source{'s' if len(sections) != 1 else ''} · "
               f"{counts['action']} waiting on you · {counts['problem']} problem"
               f"{'s' if counts['problem'] != 1 else ''}")

    parts = [f"# {Icons[worst]} iMicroSeq ingestion ({env}): {title}", summary]
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
