"""Turn changed.csv into edits.csv: revised records, ready to send as portal edits.

diff_new_records.py writes changed.csv: today's full rows for records that are
already published but whose values have changed since. The portal edits a
published record by its system ID (its own record ID), so this adds a
``systemId`` column taken from published_ids.csv (fetch_published.py
--ids-out). An edit replaces the whole record, so every field is kept, not only
the ones that changed.

It also counts, per field, how many records change (--fields-out), so the
person approving the edits can see what they do:

    field,records_changed,published_example,new_example

    python build_edits.py --changed changed.csv --ids published_ids.csv \\
        --published published.csv --output edits.csv --fields-out edit_fields.csv

Prints one line per changed field, then ``edits=<N>``.
"""

import argparse
import collections

import pandas as pd

from diff_new_records import KEY, cellsEqual

SystemIdColumn = "systemId"


def readCsv(path):
    try:
        return pd.read_csv(path, dtype=str, keep_default_na=False)
    except pd.errors.EmptyDataError:
        return pd.DataFrame()


def buildEdits(changed, ids, published):
    """Return (edits, fieldCounts). ``fieldCounts`` is a list of
    (field, count, publishedExample, newExample), most changed first."""
    if changed.empty:
        return pd.DataFrame(columns=[SystemIdColumn] + list(changed.columns)), []
    if not ids.empty and ids[KEY].duplicated().any():
        raise SystemExit("ERROR: the published IDs list has a sample ID twice; fetch it again")
    systemIds = dict(zip(ids[KEY], ids[SystemIdColumn])) if not ids.empty else {}
    missing = [i for i in changed[KEY] if not systemIds.get(i)]
    if missing:
        shown = ", ".join(missing[:10]) + (" ..." if len(missing) > 10 else "")
        raise SystemExit(f"ERROR: no system ID for {len(missing)} changed record(s): {shown}\n"
                         "       They should all be published; fetch the snapshot again.")
    edits = changed.copy()
    edits.insert(0, SystemIdColumn, edits[KEY].map(systemIds))

    base = published.set_index(KEY) if not published.empty else pd.DataFrame()
    counts, examples = collections.Counter(), {}
    for _, row in changed.iterrows():
        old = base.loc[row[KEY]] if row[KEY] in base.index else None
        for col, new in row.items():
            if col == KEY:
                continue
            before = "" if old is None or col not in old.index else old[col]
            if not cellsEqual(new, before):
                counts[col] += 1
                examples.setdefault(col, (before, new))
    fieldCounts = [(c, n, *examples[c]) for c, n in counts.most_common()]
    return edits, fieldCounts


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--changed", required=True, help="changed.csv from diff_new_records.py")
    ap.add_argument("--ids", required=True, help="published_ids.csv from fetch_published.py --ids-out")
    ap.add_argument("--published", required=True, help="published.csv (the baseline), for the field counts")
    ap.add_argument("--output", required=True, help="Where to write edits.csv")
    ap.add_argument("--fields-out", default=None, help="Where to write the per-field counts")
    args = ap.parse_args(argv)

    edits, fieldCounts = buildEdits(readCsv(args.changed), readCsv(args.ids), readCsv(args.published))
    edits.to_csv(args.output, index=False)
    if args.fields_out:
        pd.DataFrame(fieldCounts, columns=["field", "records_changed", "published_example",
                                           "new_example"]).to_csv(args.fields_out, index=False)
    for field, n, before, after in fieldCounts:
        print(f"      {n:6d}  {field}: e.g. {before[:40]!r} -> {after[:40]!r}")
    print(f"edits={len(edits)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
