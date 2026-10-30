"""Upload a portal-schema CSV to the data portal and wait for it to validate.

Runs six steps in order and stops once the server has validated the data.
It never publishes: committing a submission is done by a person on the portal
website, in dev and in prod. A VALID run prints the link to review and commit
it; an INVALID run prints the link to see which records failed.

    python main.py --input delta.csv --organization PHAC-AUTOINGEST
    python main.py --input delta.csv --organization PHAC-AUTOINGEST --replace
"""

import argparse
import datetime
import json
import os
import shlex
import sys

from common import (
    DefaultBaseURL,
    DefaultPollInterval,
    DefaultPortalURL,
    DefaultTimeout,
    TokenEnvVar,
    resolveToken,
)
from step1_token import hasWriteScope, tokenScopes
from step2_category import describeCategory, resolveCategory
from step3_dictionary import fetchSchema
from step4_transform import transformCsv
from step5_upload import closeSubmission, findActiveSubmission, uploadSubmission
from step6_validate import summarize, waitForValidation

TotalSteps = 6

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


def parseArgs(argv=None):
    parser = argparse.ArgumentParser(
        description="Upload a portal-schema CSV to the data portal and validate it. "
        "Never commits: a person commits on the portal website.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--input", required=True, help="Portal-schema CSV to upload")
    parser.add_argument(
        "--organization", required=True, help="Submitting organization, e.g. PHAC-AUTOINGEST"
    )
    parser.add_argument(
        "--category", default="imicroseq_wastewater", help="Category name or numeric id"
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
    return parser.parse_args(argv)


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
    transformedPath, rowCount = transformCsv(args.input, headerMap, entityName, workDir)
    print(f"      {rowCount} rows -> {transformedPath}")

    banner(5, f"Uploading as organization {args.organization!r}")
    # An open submission is appended to, not replaced, so re-running without
    # clearing it stages a second copy of every record and fails validation on
    # duplicate IDs. Refuse rather than quietly corrupt the batch.
    active = findActiveSubmission(args.base_url, egoToken, categoryId, args.organization)
    if active:
        if not args.replace:
            print(
                f"ERROR: submission {active['id']} is already open for {args.organization!r} "
                f"(status {active['status']}). Uploading would append to it and duplicate every "
                "record.\n       Commit or discard it on the website first, or re-run with "
                "--replace to discard it.\n"
                f"       {args.portal_url.format(submissionId=active['id'])}",
                file=sys.stderr,
            )
            writeResult(args.result_json, {
                "submissionId": active["id"],
                "status": "BLOCKED_BY_OPEN_SUBMISSION",
                "url": args.portal_url.format(submissionId=active["id"]),
                "rows": rowCount,
            })
            return 1
        closeSubmission(args.base_url, egoToken, active["id"])
        print(f"      Discarded open submission {active['id']}", flush=True)

    submissionId, uploadResult = uploadSubmission(
        args.base_url, egoToken, categoryId, entityName, args.organization, transformedPath
    )
    print(f"      submissionId {submissionId}, status {uploadResult.get('status')}")

    banner(6, "Waiting for validation")
    settled = waitForValidation(
        args.base_url, egoToken, submissionId, args.poll_interval, args.timeout
    )
    print(json.dumps(summarize(settled), indent=2), flush=True)

    reviewUrl = args.portal_url.format(submissionId=submissionId)
    status = settled.get("status")
    errorCount = (settled.get("errors") or {}).get("total")
    writeResult(args.result_json, {
        "submissionId": submissionId,
        "status": status,
        "url": reviewUrl,
        "rows": rowCount,
        "errors": errorCount,
    })

    if status != "VALID":
        # The portal already explains what is wrong, per record, better than
        # this can. Hand over the link instead of reproducing its error list.
        rerun = " ".join(shlex.quote(arg) for arg in sys.argv)
        if "--replace" not in sys.argv:
            rerun += " --replace"

        print(
            f"\nERROR: submission {submissionId} is {status} "
            f"({errorCount} validation error(s)).\n\n"
            f"  Review it here:\n"
            f"    {reviewUrl}\n\n"
            f"  Use the Status column to see which records failed and what needs correcting.\n"
            f"  Then fix {args.input} and re-run:\n"
            f"    python {rerun}",
            file=sys.stderr,
        )
        return 1

    print(
        f"\n      Submission {submissionId} is VALID ({rowCount} records) but NOT published.\n"
        f"      Review and commit it on the portal website:\n"
        f"        {reviewUrl}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
