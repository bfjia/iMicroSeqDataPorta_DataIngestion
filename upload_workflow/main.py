"""Upload new records and/or edits to the data portal and wait for them to validate.

Runs six steps in order and stops once the server has validated the data.
It never publishes: committing a submission is done by a person on the portal
website, in dev and in prod. A VALID run prints the link to review and commit
it; an INVALID run prints the link to see which records failed.

New records (--input) and edits to published records (--edits, rows with a
systemId column; see build_edits.py) go into ONE submission: new records first,
then the edits. The person reviews and commits both at once.

    python main.py --input delta.csv --organization PHAC-AUTOINGEST
    python main.py --input delta.csv --edits edits.csv --organization PHAC-AUTOINGEST
    python main.py --edits edits.csv --organization PHAC-AUTOINGEST
    python main.py --input delta.csv --organization PHAC-AUTOINGEST --replace
"""

import argparse
import datetime
import json
import os
import shlex
import sys
import time

from common import (
    DefaultBaseURL,
    DefaultCategory,
    DefaultPollInterval,
    DefaultPortalURL,
    DefaultTimeout,
    TokenEnvVar,
    pollUntil,
    resolveToken,
)
from step1_token import hasWriteScope, tokenScopes
from step2_category import describeCategory, resolveCategory
from step3_dictionary import fetchSchema
from step4_transform import transformCsv
from step5_upload import closeSubmission, findActiveSubmission, uploadEdits, uploadSubmission
from step6_validate import PendingStatuses, getSubmission, summarize, waitForValidation

TotalSteps = 6
SystemIdColumn = "systemId"
# Seconds a settled submission may show fewer records than were sent before
# the run gives up on the rest arriving (see step 6 in main()).
StagingGrace = 300

# Without --work-dir the transformed CSV goes under the repo's runs/ folder,
# never a system temp directory.
RepoDir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def banner(step, message):
    print(f"[{step}/{TotalSteps}] {message}", flush=True)


def writeResult(path, result):
    """Write the outcome as JSON for the calling script, if it asked for it."""
    if not path:
        return
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(result, handle, indent=2)


def stagedCounts(submission):
    """(new records, edits) staged in a submission, from its data summary."""
    data = submission.get("data") or {}

    def count(kind):
        return sum((entity or {}).get("recordsCount") or 0
                   for entity in (data.get(kind) or {}).values())

    return count("inserts"), count("updates")


def parseArgs(argv=None):
    parser = argparse.ArgumentParser(
        description="Upload new records and/or edits to the data portal and validate them. "
        "Never commits: a person commits on the portal website.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--input", default=None, help="Portal-schema CSV of new records to upload")
    parser.add_argument(
        "--edits",
        default=None,
        help="Portal-schema CSV of edits to published records, with a systemId column "
        "(build_edits.py). Goes into the same submission as --input.",
    )
    parser.add_argument(
        "--organization", required=True, help="Submitting organization, e.g. PHAC-AUTOINGEST"
    )
    parser.add_argument(
        "--category", default=DefaultCategory, help="Category name or numeric id"
    )
    parser.add_argument("--entity", default=None, help="Entity name. Defaults to the only schema.")
    parser.add_argument("--base-url", default=DefaultBaseURL, help="Submission service base URL")
    parser.add_argument(
        "--portal-url",
        default=DefaultPortalURL,
        help="Portal URL template for reviewing a submission. Uses {submissionId}.",
    )
    parser.add_argument(
        "--token",
        default=None,
        help=f"Auth token. Defaults to ${TokenEnvVar}, else a fresh getToken.py login.",
    )
    parser.add_argument(
        "--poll-interval", type=float, default=DefaultPollInterval, help="Seconds between polls"
    )
    parser.add_argument(
        "--timeout", type=float, default=DefaultTimeout, help="Seconds to wait before giving up"
    )
    parser.add_argument(
        "--work-dir",
        default=None,
        help="Where to write the transformed CSV. Default: runs/main-<timestamp>/ in the repo.",
    )
    parser.add_argument(
        "--replace",
        action="store_true",
        help="Discard any open submission for this organization before uploading",
    )
    parser.add_argument(
        "--require-scope",
        action="store_true",
        help="Stop instead of warning when the token has no WRITE scope for --organization",
    )
    parser.add_argument(
        "--result-json",
        default=None,
        help="Also write the outcome (submissionId, status, link, counts) to this JSON file",
    )
    args = parser.parse_args(argv)
    if not args.input and not args.edits:
        parser.error("give --input (new records), --edits (edits), or both")
    return args


def main(argv=None):
    args = parseArgs(argv)

    banner(1, "Getting an auth token")
    egoToken = resolveToken(args.token)
    scopes = tokenScopes(egoToken)
    print(f"      Token acquired, scopes: {', '.join(scopes) or '(none)'}", flush=True)

    # A hint, not a verdict: the server decides whether the upload is allowed.
    if not hasWriteScope(egoToken, args.organization):
        message = (
            f"token has no {args.organization}.WRITE scope. Scopes present: {scopes}. "
            "The server decides, so this may still work."
        )
        if args.require_scope:
            print(f"ERROR: {message}", file=sys.stderr)
            return 1
        print(f"      NOTE: {message}", flush=True)

    banner(2, f"Resolving category {args.category!r}")
    categoryId = resolveCategory(args.base_url, egoToken, args.category)
    category = describeCategory(args.base_url, egoToken, categoryId)
    print(f"      id {categoryId}, dictionary {category['dictionary']['name']} "
          f"v{category['dictionary']['version']}")

    banner(3, "Fetching the dictionary")
    entityName, headerMap, dictionaryInfo = fetchSchema(
        args.base_url, egoToken, categoryId, args.entity
    )
    print(f"      entity {entityName!r}, {dictionaryInfo['fields']} fields")

    banner(4, "Renaming CSV headers to dictionary field names")
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    workDir = args.work_dir or os.path.join(RepoDir, "runs", f"main-{stamp}")
    newPath, newCount, editsPath, editsCount = None, 0, None, 0
    if args.input:
        newPath, newCount = transformCsv(args.input, headerMap, entityName, workDir)
        print(f"      new records: {newCount} rows -> {newPath}")
    if args.edits:
        # Its own folder: both files are named after the entity (sample.csv).
        editsPath, editsCount = transformCsv(args.edits, headerMap, entityName,
                                             os.path.join(workDir, "edits"),
                                             passthrough=(SystemIdColumn,))
        print(f"      edits: {editsCount} rows -> {editsPath}")

    def result(submissionId, status, url, errors=None):
        writeResult(args.result_json, {
            "submissionId": submissionId,
            "status": status,
            "url": url,
            "rows": newCount,
            "edits": editsCount,
            "errors": errors,
        })

    banner(5, f"Uploading as organization {args.organization!r}")
    # An open submission is appended to, not replaced, so re-running without
    # clearing it stages a second copy of every record and fails validation on
    # duplicate IDs. Refuse rather than quietly corrupt the batch. Checked once,
    # before the first upload: the edits are meant to join this run's new records.
    active = findActiveSubmission(args.base_url, egoToken, categoryId, args.organization)
    if active:
        if not args.replace:
            print(
                f"ERROR: submission {active['id']} is already open for {args.organization!r} "
                f"(status {active['status']}). Uploading would append to it and duplicate every "
                "record.\n       Commit it on the website, or close it first "
                "(../close_submission.sh <SOURCE>), or re-run with --replace to discard it.\n"
                f"       {args.portal_url.format(submissionId=active['id'])}",
                file=sys.stderr,
            )
            result(active["id"], "BLOCKED_BY_OPEN_SUBMISSION",
                   args.portal_url.format(submissionId=active["id"]))
            return 1
        closeSubmission(args.base_url, egoToken, active["id"])
        print(f"      Discarded open submission {active['id']}", flush=True)

    submissionId = None
    if newPath:
        submissionId, uploadResult = uploadSubmission(
            args.base_url, egoToken, categoryId, entityName, args.organization, newPath
        )
        print(f"      new records: submissionId {submissionId}, status {uploadResult.get('status')}")
    if editsPath:
        if submissionId:
            # Edits sent while the portal is still validating the new records are
            # accepted but never staged (seen on dev, 2026-11-05), so wait first.
            print("      waiting for the new records to validate before sending the edits", flush=True)
            waitForValidation(args.base_url, egoToken, submissionId, args.poll_interval, args.timeout)
        editsId, editsResult = uploadEdits(
            args.base_url, egoToken, categoryId, args.organization, editsPath
        )
        if not editsId:
            # Added to an open submission, the portal answers without its number.
            active = findActiveSubmission(args.base_url, egoToken, categoryId, args.organization)
            editsId = active.get("id") if active else None
        print(f"      edits: submissionId {editsId}, status {editsResult.get('status')}")
        if submissionId and str(editsId) != str(submissionId):
            # Expected to be one submission; two would each need reviewing.
            print(
                f"ERROR: the edits went into submission {editsId}, not {submissionId} with the new "
                "records. Review both on the website before committing either:\n"
                f"       {args.portal_url.format(submissionId=submissionId)}\n"
                f"       {args.portal_url.format(submissionId=editsId)}",
                file=sys.stderr,
            )
            result(submissionId, "SPLIT_SUBMISSION", args.portal_url.format(submissionId=submissionId))
            return 1
        submissionId = editsId
    if not submissionId:
        raise RuntimeError("The upload was accepted but no open submission can be found for it")

    banner(6, "Waiting for validation")
    # Done when everything sent is staged and validated. Right after the edits the
    # submission can still read VALID for the new records alone, so a settled
    # status with fewer records than sent only counts as done after a grace period.
    expected = (newCount, editsCount)
    started = time.monotonic()

    def settledAndComplete(submission):
        if submission.get("status") in PendingStatuses:
            return False
        return stagedCounts(submission) == expected or time.monotonic() - started > StagingGrace

    settled = pollUntil(
        fetch=lambda: getSubmission(args.base_url, egoToken, submissionId),
        isDone=settledAndComplete,
        interval=args.poll_interval,
        timeout=args.timeout,
        description=f"submission {submissionId} to finish validating",
    )
    print(json.dumps(summarize(settled), indent=2), flush=True)

    reviewUrl = args.portal_url.format(submissionId=submissionId)
    status = settled.get("status")
    errorCount = (settled.get("errors") or {}).get("total")
    what = " and ".join(part for part in (
        f"{newCount} new records" if newPath else "",
        f"{editsCount} edits" if editsPath else "",
    ) if part)

    staged = stagedCounts(settled)
    if staged != expected:
        # The portal accepted an upload without staging all of it. Never report
        # that as VALID: committing it would publish only part of the run.
        print(
            f"\nERROR: submission {submissionId} holds {staged[0]} new records and {staged[1]} "
            f"edits, but this run sent {what}.\n"
            "       The portal accepted the upload without staging all of it. Don't commit it;\n"
            "       close it (../close_submission.sh <SOURCE>) and run again.\n"
            f"       {reviewUrl}",
            file=sys.stderr,
        )
        result(submissionId, "INCOMPLETE_SUBMISSION", reviewUrl, errorCount)
        return 1
    result(submissionId, status, reviewUrl, errorCount)

    if status != "VALID":
        # The portal already explains what is wrong, per record, better than
        # this can. Hand over the link instead of reproducing its error list.
        rerun = " ".join(shlex.quote(arg) for arg in sys.argv)
        if "--replace" not in sys.argv:
            rerun += " --replace"

        print(
            f"\nERROR: submission {submissionId} ({what}) is {status} "
            f"({errorCount} validation error(s)).\n\n"
            f"  Review it here:\n"
            f"    {reviewUrl}\n\n"
            f"  Use the Status column to see which records failed and what needs correcting.\n"
            f"  Then fix the input and re-run:\n"
            f"    python {rerun}",
            file=sys.stderr,
        )
        return 1

    print(
        f"\n      Submission {submissionId} is VALID ({what}) but NOT published.\n"
        f"      Review and commit it on the portal website:\n"
        f"        {reviewUrl}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
