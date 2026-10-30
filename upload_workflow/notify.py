"""Write the run's notification digest, msg.md (slack_post.py posts it to Slack).

One message per run, never one per step. run_source.sh leaves a status.env in
each source's run folder; this reads them all and writes a single Markdown
digest:

  * a headline with the worst status across sources and the run time:
        🔴 problem  >  🟡 action needed  >  🟢 all good
  * one short section per source: a bold one-liner with its own dot, then the
    submission link if there is one;
  * FYI lines inside a section (missing parser values, revised records,
    test hold-backs) that never change the headline on their own;
  * the log path only for problems.

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
    """'2026-10-30T15:12:00.000Z' -> 'open since today' / 'open 5 days'."""
    try:
        created = datetime.datetime.fromisoformat(createdAt.replace("Z", "+00:00"))
    except (AttributeError, ValueError):
        return f"open since {createdAt or 'an unknown date'}"
    days = (datetime.datetime.now(datetime.timezone.utc) - created).days
    if days < 1:
        return "open since today"
    return f"open {days} day{'s' if days != 1 else ''}"


def weeks(csvPath):
    """' (week 2026-10-18)' / ' (weeks 2026-09-06 to 2026-10-11)' / ''."""
    rng = dateRange(csvPath)
    if not rng:
        return ""
    return f" (week {rng[0]})" if rng[0] == rng[1] else f" (weeks {rng[0]} to {rng[1]})"


def logTail(path, lines=6):
    if not path or not os.path.exists(path):
        return ""
    with open(path, encoding="utf-8", errors="replace") as handle:
        content = [l.rstrip() for l in handle if l.strip() and "\r" not in l]
    return "\n".join(content[-lines:])


def section(s, folder):
    """Render one source's section: a bold one-liner, then a link/FYIs. Returns (level, md)."""
    status = s.get("STATUS", "failed")
    level = Levels.get(status, "problem")
    head = f"**{Icons[level]} {s.get('SOURCE_ID', os.path.basename(folder))}:**"
    sid = s.get("SUBMISSION_ID", "")
    url = s.get("SUBMISSION_URL", "")
    new = num(s.get("NEW"))
    delta = os.path.join(folder, "delta.csv")
    out = []

    if status == "review":
        out += [f"{head} {new} new records{weeks(delta)} passed validation. Review and commit:", url]
    elif status == "waiting":
        out += [f"{head} submission {sid} is still waiting for your commit "
                f"({waitedFor(s.get('PENDING_CREATED', ''))}). Nothing new uploaded.", url]
    elif status == "waiting_invalid":
        out += [f"{head} submission {sid} failed validation "
                f"({waitedFor(s.get('PENDING_CREATED', ''))}). Fix the cause, then "
                f"`./close_submission.sh {s.get('SOURCE_NAME', '<SOURCE>')}` and run again.", url]
    elif status == "invalid":
        out += [f"{head} submission {sid} failed validation ({num(s.get('ERRORS'))} errors). "
                f"Fix the cause, then `./close_submission.sh {s.get('SOURCE_NAME', '<SOURCE>')}` "
                "and run again.", url]
    elif status == "guard":
        out += [f"{head} stopped: {new} new records is over the limit of "
                f"{num(s.get('MAX_NEW'))}. Nothing uploaded. Likely a sample-ID change; "
                "if expected, re-run with `--force`."]
    elif status == "nothing_new":
        out += [f"{head} nothing new ({num(s.get('IN_SCOPE'))} records checked)."]
    elif status == "dry_run":
        out += [f"{head} dry run: {new} new records{weeks(delta)} would be uploaded "
                f"(`{rel(delta)}`)."]
    else:  # failed
        reason = s.get("REASON", "")
        out += [f"{head} run failed during {s.get('STEP', 'an unknown step')}."
                + (f" {reason}" if reason else "")]
        tail = logTail(s.get("LOG"))
        if tail:
            out += ["```", tail, "```"]

    # FYI lines: worth knowing, but never a reason to change the headline.
    changed = s.get("CHANGED", "0")
    if changed not in ("", "0"):
        out.append(f"- FYI: {num(changed)} published records were revised at the source, not "
                   f"re-uploaded (`{rel(os.path.join(folder, 'changed.csv'))}`)")
    missingPath = os.path.join(folder, "missing.txt")
    if os.path.exists(missingPath):
        with open(missingPath, encoding="utf-8") as handle:
            missing = [l.strip() for l in handle if l.strip()]
        if missing:
            out.append("- FYI: missing values, please supply: " + "; ".join(missing))
    held = s.get("HELD_OUT", "0")
    if held not in ("", "0"):
        out.append(f"- FYI: test mode, {num(held)} records held back")

    if level == "problem" and s.get("LOG"):
        out.append(f"Log: `{rel(s['LOG'])}`")
    return level, "\n".join(out)


def build(runDir):
    folders = sorted(
        os.path.join(runDir, d) for d in os.listdir(runDir)
        if os.path.isfile(os.path.join(runDir, d, "status.env"))
    )
    env = "dev" if ".dev." in DefaultBaseURL else "prod"
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
