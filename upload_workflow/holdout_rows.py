"""TEST ONLY: hold some rows back from an upload so the next run has a delta.

When there is no newer source data to test with, the first load can leave a
few records out on purpose. The next run on the same data must then find
exactly those records as new. Two kinds are held back:

  * every row in the newest N collection weeks (``--latest-weeks``), which
    looks like a normal weekly update;
  * N random rows from the remaining, older weeks (``--random``), which checks
    that late-arriving older records are caught too.

The last line printed is ``kept=<N> held=<M>``.

    python holdout_rows.py --input delta.csv --output kept.csv --held-out heldout.csv \\
        --latest-weeks 1 --random 10 --seed 42
"""

import argparse
import csv
import random

DateColumn = "sample collection start date"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--input", required=True, help="CSV to split (normally the delta)")
    ap.add_argument("--output", required=True, help="Where to write the rows that stay")
    ap.add_argument("--held-out", required=True, help="Where to write the held-back rows")
    ap.add_argument("--latest-weeks", type=int, default=0, help="Hold back the newest N weeks")
    ap.add_argument("--random", type=int, default=0, help="Also hold back N random older rows")
    ap.add_argument("--seed", type=int, default=42, help="Random seed, for a repeatable pick")
    args = ap.parse_args(argv)

    with open(args.input, newline="", encoding="utf-8-sig") as handle:
        reader = csv.reader(handle)
        header = next(reader)
        rows = list(reader)
    if DateColumn not in header:
        raise SystemExit(f"ERROR: {args.input!r} has no {DateColumn!r} column")
    col = header.index(DateColumn)

    weeks = sorted({r[col] for r in rows if r[col]}, reverse=True)
    newestWeeks = set(weeks[:max(args.latest_weeks, 0)])
    held = {i for i, r in enumerate(rows) if r[col] in newestWeeks}

    older = [i for i in range(len(rows)) if i not in held]
    pick = min(max(args.random, 0), len(older))
    held.update(random.Random(args.seed).sample(older, pick))

    for path, keep in ((args.output, False), (args.held_out, True)):
        with open(path, "w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(header)
            writer.writerows(r for i, r in enumerate(rows) if (i in held) == keep)

    print(f"kept={len(rows) - len(held)} held={len(held)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
