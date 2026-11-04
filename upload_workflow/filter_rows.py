"""Keep only rows whose collection week starts on or after a cutoff date.

Dev does not need every source's full history, so pipeline.conf sets
DEV_MIN_START_DATE and run_initial_upload.sh applies it right after the ETL. Rows are
kept when ``sample collection start date`` (YYYY-MM-DD) is on or after the
cutoff. While a cutoff is set, rows with a blank or malformed date are dropped
too, since they cannot be placed in the window. With an empty cutoff every row
is kept.

The last line printed is ``kept=<N> before_cutoff=<M> undated=<K>``.

    python filter_rows.py --input in.csv --output out.csv --min-start-date 2026-09-01
"""

import argparse
import csv
import re

DateColumn = "sample collection start date"
IsoDate = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--input", required=True, help="Curated CSV to filter")
    ap.add_argument("--output", required=True, help="Where to write the kept rows")
    ap.add_argument("--min-start-date", default="", help="YYYY-MM-DD; empty keeps every row")
    ap.add_argument("--column", default=DateColumn, help="Date column (default: %(default)s)")
    args = ap.parse_args(argv)

    cutoff = args.min_start_date.strip()
    if cutoff and not IsoDate.match(cutoff):
        raise SystemExit(f"ERROR: --min-start-date must be YYYY-MM-DD, got {cutoff!r}")

    kept = beforeCutoff = undated = 0
    with open(args.input, newline="", encoding="utf-8-sig") as src, \
            open(args.output, "w", newline="", encoding="utf-8") as dst:
        reader = csv.reader(src)
        writer = csv.writer(dst)
        header = next(reader)
        if args.column not in header:
            raise SystemExit(f"ERROR: {args.input!r} has no {args.column!r} column")
        col = header.index(args.column)
        writer.writerow(header)
        for row in reader:
            value = row[col].strip() if col < len(row) else ""
            if cutoff:
                if not IsoDate.match(value):
                    undated += 1
                    continue
                if value < cutoff:  # ISO dates compare correctly as text
                    beforeCutoff += 1
                    continue
            writer.writerow(row)
            kept += 1

    print(f"kept={kept} before_cutoff={beforeCutoff} undated={undated}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
