"""Partition a freshly-curated CSV against what is already published.

Sources republish their entire history every run, but the portal rejects a
sample ID it already holds. This script keeps uploads to what actually changed,
keyed on the identity column ``specimen collector sample ID``:

  * NEW       -- sample ID not in the baseline. Written to ``--new-out`` for
                 upload.
  * CHANGED   -- sample ID in the baseline but row content differs (e.g. PHAC
                 revised a past week's measurement). Written to ``--changed-out``
                 and reported, but NOT uploaded -- these existing records need
                 a manual update.
  * UNCHANGED -- identical to the baseline. Ignored.

The baseline is a snapshot of the published records, as written by
fetch_published.py. Both inputs must already have one row per sample ID:
deduping is each source's job (see data_ETL/<source>/etl.sh), so a duplicate
here is a hard error rather than something to guess about.

The exit code reflects errors only, not the presence of changed rows, so the
workflow keeps going and merely warns. Counts are printed as the last line as
``new=<N> changed=<M> unchanged=<K>`` for the caller to read if it wants.
"""

import argparse
import math
import sys

import pandas as pd

KEY = "specimen collector sample ID"

# The baseline stores measurements as submitted (rounded), while a fresh parse
# emits full float precision, so "4.271202229" and "4.2712022287494" are the
# same value. Compare numeric cells numerically within this tolerance so
# formatting alone is not reported as a revision.
NUM_REL_TOL = 1e-6
NUM_ABS_TOL = 1e-9


def cellsEqual(a, b):
    """True if two cell strings are the same value, ignoring float formatting."""
    if a == b:
        return True
    try:
        return math.isclose(float(a), float(b), rel_tol=NUM_REL_TOL, abs_tol=NUM_ABS_TOL)
    except (TypeError, ValueError):
        return False


def loadKeyed(path):
    """Read a curated CSV as strings, keyed by sample ID.

    Returns ``(dataframe, by_key)`` where ``by_key`` maps sample ID -> row dict
    (column -> value) for content comparison. A missing or empty file yields
    empties so the first run treats every record as new.
    """
    try:
        df = pd.read_csv(path, dtype=str, keep_default_na=False)
    except (FileNotFoundError, pd.errors.EmptyDataError):
        return pd.DataFrame(), {}
    if KEY not in df.columns:
        raise SystemExit(f"ERROR: {path!r} has no {KEY!r} column")
    # A duplicate ID would make "new" vs "changed" ambiguous, and the portal
    # would reject it anyway. Name them so the source's ETL can be fixed.
    dupes = df[KEY][df[KEY].duplicated(keep=False)].unique().tolist()
    if dupes:
        shown = ", ".join(dupes[:10]) + (" ..." if len(dupes) > 10 else "")
        raise SystemExit(
            f"ERROR: {path!r} has {len(dupes)} duplicated {KEY!r} value(s): {shown}\n"
            "       Each sample ID must appear once. Dedupe in the source's etl.sh."
        )
    byKey = {row[KEY]: row.to_dict() for _, row in df.iterrows()}
    return df, byKey


def rowChanged(row, baseRow):
    """True if ``row`` differs from the baseline row in any column by value."""
    for col, val in row.items():
        if not cellsEqual(val, baseRow.get(col, "")):
            return True
    return False


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--new", required=True, help="Freshly-parsed curated CSV to partition")
    ap.add_argument("--baseline", required=True, help="Last-published baseline CSV (may be absent)")
    ap.add_argument("--new-out", required=True, help="Where to write NEW records (for submission)")
    ap.add_argument("--changed-out", required=True, help="Where to write CHANGED records (warn only)")
    args = ap.parse_args(argv)

    freshDf, fresh = loadKeyed(args.new)
    if freshDf.empty:
        raise SystemExit(f"ERROR: parsed output {args.new!r} is empty; nothing to diff")
    _, baseline = loadKeyed(args.baseline)

    newMask, changedMask = [], []
    for _, row in freshDf.iterrows():
        key = row[KEY]
        if key not in baseline:
            newMask.append(True)
            changedMask.append(False)
        elif rowChanged(row, baseline[key]):
            newMask.append(False)
            changedMask.append(True)
        else:
            newMask.append(False)
            changedMask.append(False)

    newDf = freshDf[newMask]
    changedDf = freshDf[changedMask]

    # Always write both files (header even when empty) so downstream steps have
    # a stable, predictable path to read.
    newDf.to_csv(args.new_out, index=False)
    changedDf.to_csv(args.changed_out, index=False)

    if not changedDf.empty:
        ids = changedDf[KEY].tolist()
        shown = ", ".join(ids[:10]) + (" ..." if len(ids) > 10 else "")
        print(
            f"\n  WARNING: {len(changedDf)} record(s) have revised values since the last "
            f"publish and were NOT submitted.\n"
            f"           These existing records need a manual update: {shown}\n"
            f"           Full list -> {args.changed_out}\n",
            file=sys.stderr,
        )

    unchanged = len(freshDf) - len(newDf) - len(changedDf)
    print(f"new={len(newDf)} changed={len(changedDf)} unchanged={unchanged}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
