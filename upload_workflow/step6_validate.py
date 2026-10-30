"""Step 6: wait for the server to finish validating a submission.

Validation runs in the background, so the submission sits in OPEN/VALIDATING
for a while before settling on VALID or INVALID. Runnable on its own against
any submissionId, so a submission left open by an earlier run can be re-checked
without re-uploading.
"""

import json

from common import addPollArgs, apiGet, apiGetEvent, buildParser, pollUntil, resolveToken

# statuses that mean the server is still working
PendingStatuses = {"OPEN", "VALIDATING"}


def getSubmission(baseUrl, token, submissionId):
    """Return the current state of a submission."""
    return apiGetEvent(baseUrl, f"/submission/{submissionId}", token, "Fetching submission")


def waitForValidation(baseUrl, token, submissionId, interval, timeout):
    """Poll until the submission settles, then return it."""
    return pollUntil(
        fetch=lambda: getSubmission(baseUrl, token, submissionId),
        isDone=lambda s: s.get("status") not in PendingStatuses,
        interval=interval,
        timeout=timeout,
        description=f"submission {submissionId} to finish validating",
    )


def getErrorDetails(baseUrl, token, submissionId, pageSize=50):
    """Return the per-record errors for an INVALID submission."""
    return apiGet(
        baseUrl,
        f"/submission/{submissionId}/details",
        token,
        "Fetching submission details",
        params={"pageSize": pageSize},
    ).json()


def formatErrors(details, limit=50):
    """Render the errors from a /details response as readable lines.

    The response also carries every submitted record in full, which for this
    dictionary is 163 fields each -- printing the raw payload buries the few
    lines that say what is actually wrong.
    """
    errors = details.get("errors") or []
    if not errors:
        return ["No per-record errors reported."]

    lines = [f"{len(errors)} validation error(s):"]
    for error in errors[:limit]:
        lines.append(
            f"  row {error.get('index')}: {error.get('fieldName')} = "
            f"{error.get('fieldValue')!r} -- {error.get('reason')}"
        )
        for detail in error.get("errors") or []:
            rule = (detail.get("restriction") or {}).get("rule")
            lines.append(f"      {detail.get('message')}" + (f" [{rule}]" if rule else ""))
        matching = error.get("matchingRecords")
        if matching:
            lines.append(f"      also at row(s): {matching}")

    if len(errors) > limit:
        lines.append(f"  ... and {len(errors) - limit} more")
    return lines


def summarize(submission):
    """Return the counts worth printing for a settled submission."""
    return {
        "submissionId": submission.get("id"),
        "status": submission.get("status"),
        "organization": submission.get("organization"),
        "dictionary": submission.get("dictionary"),
        "data": submission.get("data"),
        "errors": submission.get("errors"),
    }


if __name__ == "__main__":
    parser = addPollArgs(buildParser("Wait for a submission to finish validating."))
    parser.add_argument("--submission-id", required=True, help="Submission id to poll")
    parser.add_argument(
        "--details", action="store_true", help="Also print per-record errors when INVALID"
    )
    args = parser.parse_args()

    egoToken = resolveToken(args.token)
    settled = waitForValidation(
        args.base_url, egoToken, args.submission_id, args.poll_interval, args.timeout
    )
    print(json.dumps(summarize(settled), indent=2))

    if args.details and settled.get("status") == "INVALID":
        details = getErrorDetails(args.base_url, egoToken, args.submission_id, pageSize=200)
        for line in formatErrors(details):
            print(line)

    raise SystemExit(0 if settled.get("status") == "VALID" else 1)
