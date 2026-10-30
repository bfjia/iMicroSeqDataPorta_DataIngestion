"""Step 4: rewrite the CSV headers into the dictionary's field names.

This is the only step with no network calls, and the one that catches a
mismatch between the parser's output and the registered dictionary before
anything is sent. An unmapped column is a hard error naming the column, rather
than a validation failure to untangle later.

The output file is named after the entity (``sample.csv``), matching the
template the service hands out.
"""

import csv
import json
import os

from common import DefaultCategory, buildParser, resolveToken


def transformCsv(inputPath, headerMap, entityName, outputDir):
    """Write ``inputPath`` with renamed headers into ``outputDir``.

    Returns (outputPath, rowCount).
    """
    with open(inputPath, newline="", encoding="utf-8-sig") as handle:
        reader = csv.reader(handle)
        try:
            headers = next(reader)
        except StopIteration:
            raise RuntimeError(f"{inputPath} is empty")

        unmapped = [h for h in headers if h not in headerMap]
        if unmapped:
            raise RuntimeError(
                f"{len(unmapped)} column(s) in {os.path.basename(inputPath)} are not in the "
                f"{entityName!r} dictionary: {unmapped}"
            )

        outputPath = os.path.join(outputDir, f"{entityName}.csv")
        os.makedirs(outputDir, exist_ok=True)

        rowCount = 0
        with open(outputPath, "w", newline="", encoding="utf-8") as outHandle:
            writer = csv.writer(outHandle)
            writer.writerow([headerMap[h] for h in headers])
            for row in reader:
                writer.writerow(row)
                rowCount += 1

    if rowCount == 0:
        raise RuntimeError(f"{inputPath} has headers but no data rows")

    return outputPath, rowCount


if __name__ == "__main__":
    parser = buildParser("Rename a portal-schema CSV's headers to dictionary field names.")
    parser.add_argument("--input", required=True, help="Portal-schema CSV to transform")
    parser.add_argument("--output-dir", default=".", help="Where to write {entity}.csv")
    parser.add_argument("--category", default=DefaultCategory, help="Category name or id")
    parser.add_argument("--entity", default=None, help="Entity name. Defaults to the only schema.")
    parser.add_argument(
        "--header-map",
        default=None,
        help="JSON file of {header: field name} to use instead of fetching the dictionary. "
        "Lets this step run offline.",
    )
    args = parser.parse_args()

    if args.header_map:
        with open(args.header_map, encoding="utf-8") as handle:
            loaded = json.load(handle)
        # accept either a bare map or the full step 3 output
        headerMap = loaded.get("headerMap", loaded)
        entity = args.entity or loaded.get("entityName")
        if not entity:
            raise SystemExit("--entity is required when --header-map has no entityName")
    else:
        from step2_category import resolveCategory
        from step3_dictionary import fetchSchema

        egoToken = resolveToken(args.token)
        categoryId = resolveCategory(args.base_url, egoToken, args.category)
        entity, headerMap, _ = fetchSchema(args.base_url, egoToken, categoryId, args.entity)

    path, rows = transformCsv(args.input, headerMap, entity, args.output_dir)
    print(json.dumps({"outputPath": path, "rows": rows, "entityName": entity}, indent=2))
