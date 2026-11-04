# TEMPLATE source

Copy this folder to `data_ETL/<NAME>/` to add a data source. Then follow the step-by-step guide in
[`docs/SOP_new_source.md`](../../docs/SOP_new_source.md).

Replace this file with the source's own README. It should cover:

- **What the source is:** publisher, URL, update frequency, licence or terms of use.
- **What one input row means,** and how it maps to one iMicroSeq record.
- **The ETL steps** in `etl.sh`, one by one: what each reads and writes.
- **How sample IDs are built,** and why they're stable from week to week.
- **Fixed values** the converter sets, and lookups it uses.
- **What can be unresolved** (`[MISSING]`), and how to supply the values.
- **Any deduping,** and why it's needed.
