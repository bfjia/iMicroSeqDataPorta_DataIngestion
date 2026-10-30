"""Collapse duplicate sample IDs to one row each.

PHAC's feed carries, for each measurement, both a site-labelled row and a
site-blank row. The parser builds ``specimen collector sample ID`` from the
Location (not the site), so those two rows collapse to the same ID -- a
duplicate the insert-only portal would reject. The two copies are otherwise
identical (same measurement, bar float rounding), so we keep the more complete
one: the row whose ``geo loc name (site)`` is filled in.

Used two ways, sharing one rule:
  * as a workflow step (``--input``/``--output``) to dedupe the fresh parse
    before it is diffed and submitted;
  * imported by diff_new_records.py to dedupe the baseline the same way, so a
    duplicate on the baseline side is not mistaken for a revision.
"""

import argparse

import pandas as pd

KEY = "specimen collector sample ID"
SITE = "geo loc name (site)"


def dedupe(df):
    """Return ``df`` with one row per sample ID, preferring a non-blank site.

    Stable: among a sample ID's rows the non-blank-site one wins, ties break to
    the earliest, and original row order is otherwise preserved.
    """
    if df.empty or KEY not in df.columns:
        return df
    blankSite = df[SITE].str.strip().eq("") if SITE in df.columns else pd.Series(False, index=df.index)
    # Stable sort puts non-blank-site rows first within each id; keep first,
    # then restore the original ordering.
    order = df.assign(_blank=blankSite).sort_values("_blank", kind="stable")
    kept = order.drop_duplicates(subset=KEY, keep="first").drop(columns="_blank")
    return kept.sort_index()


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--input", required=True, help="CSV to dedupe")
    ap.add_argument("--output", required=True, help="Where to write the deduped CSV")
    args = ap.parse_args(argv)

    df = pd.read_csv(args.input, dtype=str, keep_default_na=False)
    kept = dedupe(df)
    kept.to_csv(args.output, index=False)
    print(f"deduped: {len(df)} -> {len(kept)} rows (removed {len(df) - len(kept)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
