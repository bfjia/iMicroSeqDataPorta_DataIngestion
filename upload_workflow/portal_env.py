"""Which portal the scripts talk to: dev or prod.

Chosen by the PORTAL_ENV environment variable ("dev" when unset). The bash
scripts set it from pipeline.conf, or from their --env flag. Run on its own:

    PORTAL_ENV=prod python check_pending.py --organization <ORG> --category imicroseq_environmental

Each portal has its own login in upload_workflow/.env: devPortalUser /
devPortalPass and prodPortalUser / prodPortalPass.
"""

import os

EnvVar = "PORTAL_ENV"
DefaultEnv = "dev"

# The website's host, the submission service (Lyric) and the category that
# holds wastewater records (same dictionary, different name). The login service
# is ego.<site>; a submission's review page is <site>/submission/environmental/<id>.
Environments = {
    "dev": {
        "site": "dev.virusseq-dataportal.ca",
        "submissionService": "https://submission-service.dev.virusseq-dataportal.ca",
        "category": "imicroseq_wastewater",
    },
    "prod": {
        "site": "imicroseq-dataportal.ca",
        "submissionService": "https://submissions.imicroseq-dataportal.ca",
        "category": "imicroseq_environmental",
    },
}


def currentEnv():
    """The selected environment's name; stops on an unknown one."""
    name = os.environ.get(EnvVar, "").strip().lower() or DefaultEnv
    if name not in Environments:
        raise SystemExit(f"ERROR: {EnvVar}={name!r} is not a portal. Use one of: "
                         + ", ".join(Environments))
    return name


def settings(name=None):
    """Everything the scripts need to know about one portal."""
    name = name or currentEnv()
    env = Environments[name]
    return {
        "name": name,
        "site": env["site"],
        "submissionService": env["submissionService"],
        "category": env["category"],
        "ego": f"https://ego.{env['site']}",
        "portalUrl": f"https://{env['site']}/submission/environmental/{{submissionId}}",
        "userKey": f"{name}PortalUser",
        "passKey": f"{name}PortalPass",
    }
