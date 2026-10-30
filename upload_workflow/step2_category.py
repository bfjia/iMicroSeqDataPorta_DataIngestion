"""Step 2: turn a category name into the numeric categoryId the API wants.

Every submission endpoint is scoped to a category (a dataset type, e.g.
``imicroseq_wastewater``). Callers pass the readable name; the API paths need
the id.
"""

import json

from common import apiGet, buildParser, resolveToken


def listCategories(baseUrl, token):
    """Return every category the service knows about."""
    return apiGet(baseUrl, "/category", token, "Listing categories").json()


def resolveCategory(baseUrl, token, categoryNameOrId):
    """Return the numeric id for ``categoryNameOrId`` (accepts either form)."""
    categories = listCategories(baseUrl, token)

    wanted = str(categoryNameOrId).strip()
    for category in categories:
        if wanted == str(category["id"]) or wanted.lower() == category["name"].lower():
            return int(category["id"])

    available = ", ".join(f"{c['name']} (id {c['id']})" for c in categories)
    raise RuntimeError(f"No category matching {categoryNameOrId!r}. Available: {available}")


def describeCategory(baseUrl, token, categoryId):
    """Return the category's details, including its dictionary name/version."""
    return apiGet(baseUrl, f"/category/{categoryId}", token, "Fetching category").json()


if __name__ == "__main__":
    parser = buildParser("Resolve a submission category name to its numeric id.")
    parser.add_argument("--category", default=None, help="Category name or id. Omit to list all.")
    args = parser.parse_args()

    egoToken = resolveToken(args.token)
    if args.category is None:
        print(json.dumps(listCategories(args.base_url, egoToken), indent=2))
    else:
        resolvedId = resolveCategory(args.base_url, egoToken, args.category)
        print(json.dumps(describeCategory(args.base_url, egoToken, resolvedId), indent=2))
