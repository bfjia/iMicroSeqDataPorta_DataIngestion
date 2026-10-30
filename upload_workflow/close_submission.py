"""Close (discard) the open submission for an organization, so a new one can start.

Until a person commits it on the website, a submission stays open (VALID and
waiting, or INVALID), and the pipeline won't upload anything new for that
organization. Use this when the open submission should NOT be committed, e.g.
it failed validation or the data has to be redone, and the next run should
upload a fresh one.

  * Only the open submission is touched (DELETE /submission/{id}). Records
    that are already published are never affected, and a committed submission
    can't be closed.
  * It shows the submission first and asks you to type its number to confirm.
    --yes skips the question.
  * It never commits anything.

Normally run through ../close_submission.sh, which takes the source name.

    python close_submission.py --organization PHAC-AUTOINGEST
    python close_submission.py --organization PHAC-AUTOINGEST --yes
    PORTAL_ENV=prod python close_submission.py --organization PHAC-AUTOINGEST
"""

import sys

from common import DefaultCategory, DefaultPortalURL, PortalEnv, buildParser, resolveToken
from step2_category import resolveCategory
from step5_upload import closeSubmission, findActiveSubmission


def main():
    parser = buildParser("Close (discard) the open submission for an organization.")
    parser.add_argument("--category", default=DefaultCategory, help="Category name or id")
    parser.add_argument("--organization", required=True, help="Organization, e.g. PHAC-AUTOINGEST")
    parser.add_argument("--yes", action="store_true", help="Close it without asking")
    args = parser.parse_args()

    token = resolveToken(args.token)
    categoryId = resolveCategory(args.base_url, token, args.category)
    active = findActiveSubmission(args.base_url, token, categoryId, args.organization)
    if not active:
        print(f"No open submission for {args.organization}. Nothing to close.")
        return 0

    sid = active.get("id")
    print(f"Open submission for {args.organization} on {PortalEnv}:")
    print(f"  number:  {sid}")
    print(f"  status:  {active.get('status')}")
    print(f"  created: {active.get('createdAt') or '?'}")
    print(f"  link:    {DefaultPortalURL.format(submissionId=sid)}")
    print("Closing discards it and everything staged in it. Published records are not affected.")

    if not args.yes:
        if not sys.stdin.isatty():
            raise SystemExit("ERROR: no terminal to confirm in. Re-run with --yes to close it.")
        answer = input(f"Type {sid} to close it, or press Enter to cancel: ").strip()
        if answer != str(sid):
            print("Cancelled. Nothing was changed.")
            return 1

    closeSubmission(args.base_url, token, sid)
    after = findActiveSubmission(args.base_url, token, categoryId, args.organization)
    if after and after.get("id") == sid:
        raise SystemExit(f"ERROR: submission {sid} still shows as open after closing it.")
    print(f"Closed submission {sid}. The next run uploads a new one.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
