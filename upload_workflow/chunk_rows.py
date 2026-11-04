"""Split the new records into chunks for a chunked first load (run_initial_upload.sh --chunk).

Rows are sorted by collection date (oldest first, then sample ID), so each
chunk covers a continuous stretch of time, and cut into files of at most
--size rows: chunk_01.csv, chunk_02.csv, ... Each chunk becomes its own
submission, which a person commits before the next one is uploaded.

The input is the delta after any test hold-back (--holdout-weeks /
--holdout-random), so held-back rows are never in a chunk.

Prints one line per chunk, then a total:

    chunk=1 rows=10000 first=2021-01-03 last=2022-06-12 file=.../chunk_01.csv
    chunks=6 rows=51224

    python chunk_rows.py --input delta.csv --size 10000 --out-dir chunks/
"""

import argparse
import csv
import os

DateColumn = "sample collection start date"
IdColumn = "specimen collector sample ID"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--input", required=True, help="CSV of new records (normally delta.csv)")
    ap.add_argument("--size", type=int, default=10000, help="Most rows per chunk")
    ap.add_argument("--out-dir", required=True, help="Where to write chunk_NN.csv")
    args = ap.parse_args(argv)
    if args.size < 1:
        raise SystemExit("ERROR: --size must be at least 1")

    with open(args.input, newline="", encoding="utf-8-sig") as handle:
        reader = csv.reader(handle)
        header = next(reader)
        rows = list(reader)
    for column in (DateColumn, IdColumn):
        if column not in header:
            raise SystemExit(f"ERROR: {args.input!r} has no {column!r} column")
    dateCol, idCol = header.index(DateColumn), header.index(IdColumn)
    rows.sort(key=lambda r: (r[dateCol], r[idCol]))

    os.makedirs(args.out_dir, exist_ok=True)
    for old in os.listdir(args.out_dir):
        if old.startswith("chunk_") and old.endswith(".csv"):
            os.remove(os.path.join(args.out_dir, old))

    count = 0
    for start in range(0, len(rows), args.size):
        count += 1
        part = rows[start:start + args.size]
        path = os.path.join(args.out_dir, f"chunk_{count:02d}.csv")
        with open(path, "w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(header)
            writer.writerows(part)
        print(f"chunk={count} rows={len(part)} first={part[0][dateCol] or '-'} "
              f"last={part[-1][dateCol] or '-'} file={path}")
    print(f"chunks={count} rows={len(rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
