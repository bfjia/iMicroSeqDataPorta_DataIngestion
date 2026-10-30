"""Download what an organization has already published, as a baseline CSV.

Commits happen on the portal website, by a person, so the pipeline cannot keep
its own record of what is published. Instead every run asks the portal and
diffs against the answer. This script pages through

    GET /data/category/{categoryId}/organization/{organization}

and writes one CSV row per published record, with the same column titles the
curated CSVs use, so diff_new_records.py can read it as ``--baseline``.

How portal values are turned back into CSV text:
  * fields the portal leaves out (empty values) become empty cells;
  * list fields are joined with the delimiter the dictionary declares (";");
  * numbers are written as plain text ("1", "9.61644").

An organization with nothing published (the portal answers 404 "No Submitted
data found") gives a header-only CSV, i.e. every record is new.

    python fetch_published.py --organization PHAC-AUTOINGEST --output published.csv
"""

import csv
import json
import os

import requests

from common import buildParser, raiseForStatus, resolveToken
from step2_category import resolveCategory
from step3_dictionary import fetchDictionary, selectSchema

DefaultPageSize = 1000


def fetchPage(baseUrl, token, categoryId, organization, page, pageSize):
    """Return one page of published records, or None when there are none at all."""
    response = requests.get(
        baseUrl.rstrip("/") + f"/data/category/{categoryId}/organization/{organization}",
        headers={"Authorization": f"Bearer {token}"},
        params={"page": page, "pageSize": pageSize},
        timeout=120,
    )
    if response.status_code == 404 and "No Submitted data found" in response.text:
        return None
    return raiseForStatus(response, "Fetching published data").json()


def cellText(value, delimiter):
    """Render one portal value the way it would appear in a curated CSV."""
    if value is None:
        return ""
    if isinstance(value, list):
        return delimiter.join(cellText(v, delimiter) for v in value)
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def fetchPublished(baseUrl, token, category, organization, entityName=None,
                   pageSize=DefaultPageSize):
    """Return (columns, rows) for everything ``organization`` has published."""
    categoryId = resolveCategory(baseUrl, token, category)
    schema = selectSchema(fetchDictionary(baseUrl, token, categoryId), entityName)

    # dictionary field name -> (CSV column title, list delimiter)
    fields = {
        f["name"]: (f.get("displayName") or f["name"], f.get("delimiter") or ";")
        for f in schema["fields"]
    }
    columns = [title for title, _ in fields.values()]

    rows, page = [], 1
    while True:
        result = fetchPage(baseUrl, token, categoryId, organization, page, pageSize)
        if result is None:
            break
        for record in result.get("records") or []:
            if record.get("entityName") != schema["name"]:
                continue
            data = record.get("data") or {}
            unknown = sorted(set(data) - set(fields))
            if unknown:
                raise RuntimeError(
                    f"Published record {record.get('systemId')} has fields the dictionary "
                    f"does not define: {unknown}"
                )
            row = {title: "" for title in columns}
            for name, value in data.items():
                title, delimiter = fields[name]
                row[title] = cellText(value, delimiter)
            rows.append(row)
        totalPages = (result.get("pagination") or {}).get("totalPages") or 0
        if page >= totalPages:
            break
        page += 1

    return columns, rows


def writeCsv(path, columns, rows):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    parser = buildParser("Download an organization's published records as a baseline CSV.")
    parser.add_argument("--category", default="imicroseq_wastewater", help="Category name or id")
    parser.add_argument("--organization", required=True, help="Organization, e.g. PHAC-AUTOINGEST")
    parser.add_argument("--entity", default=None, help="Entity name. Defaults to the only schema.")
    parser.add_argument("--output", required=True, help="Where to write the baseline CSV")
    parser.add_argument("--page-size", type=int, default=DefaultPageSize, help="Records per request")
    args = parser.parse_args()

    egoToken = resolveToken(args.token)
    cols, published = fetchPublished(
        args.base_url, egoToken, args.category, args.organization, args.entity, args.page_size
    )
    writeCsv(args.output, cols, published)
    print(json.dumps({"organization": args.organization, "published": len(published),
                      "output": args.output}))
