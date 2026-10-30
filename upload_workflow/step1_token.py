"""Step 1: get an auth token for the submission service.

Wraps the existing getToken.py. Also decodes the token's scopes, which is how
the workflow knows up front whether the account may write for a given
organization.
"""

import argparse
import base64
import json
import os
import subprocess
import sys

WorkflowDir = os.path.dirname(os.path.abspath(__file__))
GetTokenScript = os.path.join(WorkflowDir, "getToken.py")


def getToken():
    """Return a JWT for the portal.

    getToken.py logs in as a side effect of being imported (it calls
    getEgoToken() at module level and prints the result), so it is run as a
    subprocess and read off stdout rather than imported.
    """
    result = subprocess.run(
        [sys.executable, GetTokenScript],
        capture_output=True,
        text=True,
        cwd=WorkflowDir,
    )
    if result.returncode != 0:
        raise RuntimeError(f"getToken.py failed:\n{result.stderr.strip()}")

    token = result.stdout.strip()
    if token.count(".") != 2:
        raise RuntimeError(f"getToken.py did not print a JWT. Got: {token[:120]!r}")
    return token


def tokenScopes(token):
    """Return the scopes carried by ``token``.

    Decodes the JWT payload only; the signature is not checked because the
    server does that. Scopes look like ``WW-phac.WRITE``.
    """
    payload = token.split(".")[1]
    payload += "=" * (-len(payload) % 4)
    claims = json.loads(base64.urlsafe_b64decode(payload))
    context = claims.get("context") or {}
    return list(claims.get("scope") or context.get("scope") or [])


def hasWriteScope(token, organization):
    """True if ``token`` looks able to submit on behalf of ``organization``.

    Scopes are named after the Ego policy, which carries a ``WW-`` prefix the
    organization itself does not: the scope ``WW-PHAC-AUTO.WRITE`` grants
    submitting as ``PHAC-AUTO``. Both spellings are accepted because the
    server, not this check, is the authority.
    """
    scopes = tokenScopes(token)
    return any(f"{prefix}{organization}.WRITE" in scopes for prefix in ("", "WW-"))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Get an auth token for the submission service.")
    parser.add_argument(
        "--scopes", action="store_true", help="Print the token's scopes instead of the token"
    )
    args = parser.parse_args()

    egoToken = getToken()
    if args.scopes:
        print(json.dumps(tokenScopes(egoToken), indent=2))
    else:
        print(egoToken)
