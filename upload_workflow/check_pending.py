"""Pre-flight check: is a submission for this organization still open?

This is the first thing run_source.sh does, before downloading or parsing
anything. Commits happen on the portal website, by a person, so last week's
upload may still be waiting: VALID and waiting to be committed, or INVALID and
waiting to be fixed. Uploading on top of it would append to it and duplicate
records, so the pipeline stops and reminds instead.

The listing endpoint only shows the logged-in user's submissions, so this needs
a real token -- an anonymous call returns an empty list whatever is open. Any
error makes this exit non-zero; it never guesses "nothing pending".

Prints shell-friendly KEY=VALUE lines (or JSON with --json):

    PENDING=0|1
    PENDING_ID, PENDING_STATUS, PENDING_CREATED, PENDING_URL   (when PENDING=1)
    WRITE_SCOPE=0|1     whether the token carries <prefix><org>.WRITE

    python check_pending.py --organization PHAC-AUTOINGEST
"""

import json

from common import DefaultPortalURL, buildParser, resolveToken
from step1_token import hasWriteScope
from step2_category import resolveCategory
from step5_upload import findActiveSubmission


def checkPending(baseUrl, token, category, organization, portalUrl=DefaultPortalURL):
    """Return a dict describing the open submission (if any) and the write scope."""
    categoryId = resolveCategory(baseUrl, token, category)
    active = findActiveSubmission(baseUrl, token, categoryId, organization)
    result = {
        "PENDING": 1 if active else 0,
        "WRITE_SCOPE": 1 if hasWriteScope(token, organization) else 0,
    }
    if active:
        result.update({
            "PENDING_ID": active.get("id"),
            "PENDING_STATUS": active.get("status"),
            "PENDING_CREATED": active.get("createdAt") or "",
            "PENDING_URL": portalUrl.format(submissionId=active.get("id")),
        })
    return result


if __name__ == "__main__":
    parser = buildParser("Check whether a submission is still open for an organization.")
    parser.add_argument("--category", default="imicroseq_wastewater", help="Category name or id")
    parser.add_argument("--organization", required=True, help="Organization, e.g. PHAC-AUTOINGEST")
    parser.add_argument("--portal-url", default=DefaultPortalURL, help="Review link template")
    parser.add_argument("--json", action="store_true", help="Print JSON instead of KEY=VALUE")
    args = parser.parse_args()

    egoToken = resolveToken(args.token)
    status = checkPending(args.base_url, egoToken, args.category, args.organization, args.portal_url)
    if args.json:
        print(json.dumps(status, indent=2))
    else:
        for key, value in status.items():
            print(f"{key}={value}")
