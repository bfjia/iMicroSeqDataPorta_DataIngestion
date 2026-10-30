"""Step 5: upload the file, opening a submission.

Nothing is published here. The service stages the records, hands back a
submissionId, and starts validating in the background -- step 6 waits for that
to finish, step 7 publishes.
"""

import json
import os

import requests

from common import apiGet, apiPost, buildParser, resolveToken


def findActiveSubmission(baseUrl, token, categoryId, organization):
    """Return the open submission for this category and organization, if any."""
    listing = apiGet(
        baseUrl,
        f"/submission/category/{categoryId}",
        token,
        "Listing active submissions",
        params={"onlyActive": "true", "organization": organization, "pageSize": 100},
    ).json()

    for record in listing.get("records", []):
        if record.get("organization") == organization:
            return record
    return None


def closeSubmission(baseUrl, token, submissionId):
    """Discard an open submission and everything staged in it."""
    response = requests.delete(
        baseUrl.rstrip("/") + f"/submission/{submissionId}",
        headers={"Authorization": f"Bearer {token}"},
        timeout=60,
    )
    if not response.ok:
        raise RuntimeError(
            f"Closing submission {submissionId} failed: HTTP {response.status_code}\n{response.text}"
        )
    return response


def uploadSubmission(baseUrl, token, categoryId, entityName, organization, filePath):
    """POST ``filePath`` as a new submission. Returns (submissionId, result).

    Uploading does not always start from nothing: if this category and
    organization already have an open submission, the service *appends* to it.
    Uploading the same file twice that way stages two copies of every record and
    fails validation on duplicate IDs, so callers should clear an open
    submission first -- see findActiveSubmission and closeSubmission.
    """
    try:
        with open(filePath, "rb") as handle:
            response = apiPost(
                baseUrl,
                f"/submission/category/{categoryId}/data",
                token,
                "Uploading submission",
                files={"submissionFile": (os.path.basename(filePath), handle, "text/csv")},
                data={"entityName": entityName, "organization": organization},
            )
    except RuntimeError as error:
        # The common case, and not something the caller can fix by retrying:
        # the account has no write access for this organization.
        if "HTTP 403" in str(error):
            raise RuntimeError(
                f"{error}\n\n"
                f"The portal will not let this account submit as {organization!r}. Either the "
                "organization name is wrong, or the account has not been granted write access "
                "to it -- ask the portal administrators to grant it."
            ) from None
        raise

    result = response.json()
    status = result.get("status")

    if status == "INVALID_SUBMISSION":
        errors = json.dumps(result.get("batchErrors", []), indent=2)
        raise RuntimeError(f"The service rejected the file outright:\n{errors}")

    submissionId = result.get("submissionId")
    if not submissionId:
        raise RuntimeError(f"Upload returned no submissionId:\n{json.dumps(result, indent=2)}")

    return submissionId, result


if __name__ == "__main__":
    parser = buildParser("Upload a transformed CSV as a new submission.")
    parser.add_argument("--file", required=True, help="Transformed CSV to upload")
    parser.add_argument("--category-id", required=True, type=int, help="Numeric category id")
    parser.add_argument("--entity", required=True, help="Entity name, e.g. sample")
    parser.add_argument("--organization", required=True, help="Submitting organization")
    parser.add_argument(
        "--replace",
        action="store_true",
        help="Discard any open submission for this organization first, instead of appending to it",
    )
    args = parser.parse_args()

    egoToken = resolveToken(args.token)

    if args.replace:
        active = findActiveSubmission(args.base_url, egoToken, args.category_id, args.organization)
        if active:
            closeSubmission(args.base_url, egoToken, active["id"])
            print(f"Closed open submission {active['id']}")

    _, uploadResult = uploadSubmission(
        args.base_url,
        egoToken,
        args.category_id,
        args.entity,
        args.organization,
        args.file,
    )
    print(json.dumps(uploadResult, indent=2))
