"""Step 3: fetch the category's dictionary and build the header map.

The portal-schema CSVs use readable column titles ("INSDC Project accession"),
but the service expects the field names from its dictionary
("insdc_project_accession"). The dictionary carries both, as ``displayName``
and ``name``, so the rename is taken from the live dictionary rather than
guessed by mangling strings -- a dictionary version bump then shows up as a
clear error instead of a silent mismatch.
"""

import json

from common import apiGet, buildParser, resolveToken


def fetchDictionary(baseUrl, token, categoryId):
    """Return the dictionary registered for ``categoryId``."""
    return apiGet(
        baseUrl, f"/dictionary/category/{categoryId}", token, "Fetching dictionary"
    ).json()


def selectSchema(dictionary, entityName=None):
    """Return the schema for ``entityName``, or the only one if it is omitted."""
    schemas = dictionary.get("schemas") or []
    if not schemas:
        raise RuntimeError(f"Dictionary {dictionary.get('name')!r} has no schemas")

    if entityName is None:
        if len(schemas) > 1:
            available = ", ".join(s["name"] for s in schemas)
            raise RuntimeError(
                f"Dictionary has {len(schemas)} schemas, so --entity is required. "
                f"Available: {available}"
            )
        return schemas[0]

    for schema in schemas:
        if schema["name"] == entityName:
            return schema

    available = ", ".join(s["name"] for s in schemas)
    raise RuntimeError(f"No entity named {entityName!r}. Available: {available}")


def buildHeaderMap(schema):
    """Return {csv header -> dictionary field name} for ``schema``.

    Field names map to themselves as well, so a CSV that already uses the
    dictionary's names passes through untouched.
    """
    headerMap = {}
    for field in schema["fields"]:
        name = field["name"]
        headerMap[name] = name
        displayName = field.get("displayName")
        if displayName:
            headerMap[displayName] = name
    return headerMap


def fetchSchema(baseUrl, token, categoryId, entityName=None):
    """Return (entityName, headerMap, dictionaryInfo) for a category."""
    dictionary = fetchDictionary(baseUrl, token, categoryId)
    schema = selectSchema(dictionary, entityName)
    dictionaryInfo = {
        "name": dictionary.get("name"),
        "version": dictionary.get("version"),
        "fields": len(schema["fields"]),
    }
    return schema["name"], buildHeaderMap(schema), dictionaryInfo


if __name__ == "__main__":
    parser = buildParser("Fetch a category's dictionary and print its header map.")
    parser.add_argument("--category-id", required=True, type=int, help="Numeric category id")
    parser.add_argument("--entity", default=None, help="Entity name. Defaults to the only schema.")
    args = parser.parse_args()

    egoToken = resolveToken(args.token)
    entity, headerMap, info = fetchSchema(
        args.base_url, egoToken, args.category_id, args.entity
    )
    print(json.dumps({"entityName": entity, "dictionary": info, "headerMap": headerMap}, indent=2))
