"""Shared helpers for the submission workflow steps.

Every step script talks to the same Lyric submission service and needs the same
three things: a base URL, a bearer token on each request, and a way to wait for
a background job to finish. They live here so the steps stay short.
"""

import argparse
import json
import os
import time

import requests

from portal_env import settings as portalSettings

# endpoints: dev or prod, picked by $PORTAL_ENV (see portal_env.py)
PortalEnv = portalSettings()["name"]
DefaultBaseURL = portalSettings()["submissionService"]
DefaultCategory = portalSettings()["category"]  # default --category for the CLIs

# Where a submission is reviewed in the portal UI. Its status column explains
# what failed, so a submission that does not validate is handed to the user as
# this link rather than as errors reproduced in the terminal.
DefaultPortalURL = portalSettings()["portalUrl"]

DefaultPollInterval = 3.0
DefaultTimeout = 600.0

# env var checked by resolveToken so the steps can be chained from a shell
# without logging in once per step
TokenEnvVar = "PORTAL_TOKEN"


def raiseForStatus(response, action):
    """Raise with the response body included.

    ``requests.raise_for_status`` only reports the status code, but this API
    puts the useful part (which field, which row) in the body.
    """
    if response.ok:
        return response
    raise RuntimeError(
        f"{action} failed: HTTP {response.status_code} {response.reason}\n{response.text}"
    )


def apiGetEvent(baseUrl, path, token, action, **kwargs):
    """GET an endpoint that answers with a server-sent event stream.

    ``GET /submission/{id}`` does not return JSON -- it opens an event stream
    and holds it open to push later updates, so reading it like an ordinary
    response blocks until the request times out. Only the first ``data:`` event
    is read, and the connection is closed straight after.
    """
    response = requests.get(
        baseUrl.rstrip("/") + path,
        headers={"Authorization": f"Bearer {token}"},
        stream=True,
        timeout=60,
        **kwargs,
    )
    try:
        if not response.ok:
            raiseForStatus(response, action)
        for line in response.iter_lines(decode_unicode=True):
            if line and line.startswith("data:"):
                return json.loads(line[len("data:"):].strip())
    finally:
        response.close()

    raise RuntimeError(f"{action}: the event stream closed without sending any data")


def apiGet(baseUrl, path, token, action, **kwargs):
    """GET ``path`` with the bearer token attached."""
    response = requests.get(
        baseUrl.rstrip("/") + path,
        headers={"Authorization": f"Bearer {token}"},
        timeout=60,
        **kwargs,
    )
    return raiseForStatus(response, action)


def apiPost(baseUrl, path, token, action, **kwargs):
    """POST to ``path`` with the bearer token attached."""
    response = requests.post(
        baseUrl.rstrip("/") + path,
        headers={"Authorization": f"Bearer {token}"},
        timeout=300,
        **kwargs,
    )
    return raiseForStatus(response, action)


def apiPut(baseUrl, path, token, action, **kwargs):
    """PUT to ``path`` with the bearer token attached."""
    response = requests.put(
        baseUrl.rstrip("/") + path,
        headers={"Authorization": f"Bearer {token}"},
        timeout=300,
        **kwargs,
    )
    return raiseForStatus(response, action)


def pollUntil(fetch, isDone, interval, timeout, description):
    """Call ``fetch`` every ``interval`` seconds until ``isDone`` accepts it."""
    deadline = time.monotonic() + timeout
    while True:
        value = fetch()
        if isDone(value):
            return value
        if time.monotonic() >= deadline:
            raise TimeoutError(f"Timed out after {timeout:.0f}s waiting for {description}")
        time.sleep(interval)


def resolveToken(token=None):
    """Find an auth token: explicit argument, then env var, then a fresh login."""
    if token:
        return token
    fromEnv = os.environ.get(TokenEnvVar, "")
    if fromEnv:
        return fromEnv
    from step1_token import getToken

    return getToken()


def addCommonArgs(parser):
    """Add the arguments every step's standalone CLI accepts."""
    parser.add_argument("--base-url", default=DefaultBaseURL, help="Submission service base URL")
    parser.add_argument(
        "--token",
        default=None,
        help=f"Auth token. Defaults to ${TokenEnvVar}, else a fresh getToken.py login.",
    )
    return parser


def addPollArgs(parser):
    """Add the polling arguments the steps that wait on the server accept."""
    parser.add_argument(
        "--poll-interval", type=float, default=DefaultPollInterval, help="Seconds between polls"
    )
    parser.add_argument(
        "--timeout", type=float, default=DefaultTimeout, help="Seconds to wait before giving up"
    )
    return parser


def buildParser(description):
    """A parser preloaded with the common arguments."""
    return addCommonArgs(argparse.ArgumentParser(description=description))
