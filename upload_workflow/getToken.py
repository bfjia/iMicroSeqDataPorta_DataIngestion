import os
import re
from urllib.parse import unquote
import requests
from dotenv import load_dotenv
from portal_env import settings

#endpoints: dev or prod, picked by $PORTAL_ENV (see portal_env.py)
Env = settings()
BaseURL = Env["site"]
EgoURL = Env["ego"]
EgoLoginURL = EgoURL + "/api/oauth/login/keycloak"
EgoAfterLogInGetTokenURL = EgoURL + "/api/oauth/ego-token"
EgoClientID = "portal-ui" #after login, need to manually set the client ID.

#regex to pull the Keycloak login page from the login form
KeyCloakURLRegex = r'action="([^"]+login-actions/authenticate[^"]+)"'

#get the user/pass from .env
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
egoUsername = os.environ.get(Env["userKey"], "")
egoPassword = os.environ.get(Env["passKey"], "")
if not egoUsername or not egoPassword:
    raise SystemExit(f"Missing login information for {Env['name']}. "
                     f"Set {Env['userKey']} and {Env['passKey']} in .env first.")


def getEgoToken(username, password):
    """Log in as ``username`` and return an auth token.

    Replicates the browser login: most stuff is done via cookies so using one 
    ``requests.Session`` to move the cookies from one step to next. Output is
    a JWT formatted token.

    """
    session = requests.Session()

    # 1. request the login page
    resp = session.get(
        EgoLoginURL,
        params={"client_id": EgoClientID},
        timeout=30,
    )
    resp.raise_for_status()

    # 2. The log in page/form generates several one-time login values, extract the keycloak URL with these values.
    match = re.search(KeyCloakURLRegex, resp.text)
    if match is None:
        raise RuntimeError("Step 2 failed, missing KeyCload 1 time login values")
    KeyCloakURL = unquote(match.group(1)).replace("&amp;", "&")

    # 3. POST the credentials to KeyCloak, following the redirects back to ego and get a LOGIN_NONCE.
    resp = session.post(
        KeyCloakURL,
        data={"username": username, "password": password, "credentialId": ""},
        allow_redirects=True,
        timeout=30,
    )
    if "LOGIN_NONCE" not in session.cookies.get_dict():
        raise RuntimeError("Step 3 failed, login did not complete (no LOGIN_NONCE)")

    # 4. POST the login nonce to Ego for the auth token. Should be in the body response
    resp = session.post(
        EgoAfterLogInGetTokenURL,
        params={"client_id": EgoClientID},
        timeout=30,
    )
    resp.raise_for_status()
    token = resp.text.strip()
    if token.count(".") != 2:
        raise RuntimeError(f"Step 4 did not return a token in the body. Response text: {token[:120]!r}")
    return token

egoToken = getEgoToken(egoUsername, egoPassword)
print(egoToken)