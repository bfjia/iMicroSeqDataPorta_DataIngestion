"""Post msg.md (the run's notification digest) to Slack.

One post per run: run_weekly_update.sh (and a standalone run_initial_upload.sh) call this
right after notify.py, when SLACK_CHANNEL is set in pipeline.conf. Dry runs
never post.

msg.md is GitHub Markdown, and Slack uses its own "mrkdwn", so this converts
the few things notify.py writes:

    # / ## heading   -> *heading*  (Slack has no headings; a bold line instead)
    **bold**         -> *bold*
    - bullet         -> • bullet
    [text](url)      -> <url|text>
    & < >            -> &amp; &lt; &gt;  (Slack requires these escaped)

Code spans and ``` blocks are only escaped, nothing else.

Modeled on old/duoli.py: the bot's OAuth token is read from
upload_workflow/.env (key duoliauthtoken) and the message goes out with
chat.postMessage. The bot must be a member of the channel (in Slack:
/invite @<bot name>). The last line printed is ``posted channel=<id> ts=<ts>``.

    python slack_post.py --file ../msg.md --channel C0123456789
    python slack_post.py --file ../msg.md --print      # show the Slack text, send nothing
"""

import argparse
import os
import re

from dotenv import load_dotenv

EnvFile = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
TokenKey = "duoliauthtoken"
MaxChars = 39000  # chat.postMessage cuts text off after 40,000 characters

HeadingRe = re.compile(r"^#{1,6}\s+(.*)$")
BulletRe = re.compile(r"^(\s*)[-*]\s+")
LinkRe = re.compile(r"\[([^\]]+)\]\((https?://[^)\s]+)\)")
BoldRe = re.compile(r"\*\*(.+?)\*\*")
CodeSpanRe = re.compile(r"(`[^`]*`)")

# Slack error code -> what to do about it
Hints = {
    "not_in_channel": "invite the bot to the channel first (in Slack: /invite @<bot name>)",
    "channel_not_found": "check SLACK_CHANNEL in pipeline.conf, and that the bot can see the channel",
    "invalid_auth": f"check {TokenKey} in upload_workflow/.env",
    "not_authed": f"set {TokenKey} in upload_workflow/.env",
    "token_revoked": f"the token was revoked; put a new one in upload_workflow/.env ({TokenKey})",
    "missing_scope": "the Slack app needs the chat:write permission",
}


def escape(text):
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def inline(text):
    """Bold and links outside code spans; escaping everywhere."""
    out = []
    for part in CodeSpanRe.split(text):
        if part.startswith("`") and part.endswith("`") and len(part) > 1:
            out.append(escape(part))
            continue
        part = escape(part)
        part = LinkRe.sub(lambda m: f"<{m.group(2)}|{m.group(1)}>", part)
        part = BoldRe.sub(r"*\1*", part)
        out.append(part)
    return "".join(out)


def toSlack(markdown):
    """Convert notify.py's Markdown to Slack mrkdwn."""
    lines = []
    inFence = False
    for line in markdown.splitlines():
        if line.strip().startswith("```"):
            inFence = not inFence
            lines.append(line)
            continue
        if inFence:
            lines.append(escape(line))
            continue
        heading = HeadingRe.match(line)
        if heading:
            lines.append(f"*{inline(heading.group(1).replace('**', '').strip())}*")
            continue
        bullet = BulletRe.match(line)
        if bullet:
            line = f"{bullet.group(1)}• {line[bullet.end():]}"
        lines.append(inline(line))
    text = "\n".join(lines).strip()
    if len(text) > MaxChars:
        text = text[:MaxChars] + "\n… (cut short; the full message is in msg.md)"
    return text


def post(text, channel):
    from slack_sdk import WebClient
    from slack_sdk.errors import SlackApiError

    load_dotenv(EnvFile)
    token = os.environ.get(TokenKey, "").strip()
    if not token:
        raise SystemExit(f"ERROR: no Slack token. Set {TokenKey} in upload_workflow/.env "
                         "(never commit it).")
    client = WebClient(token=token)
    try:
        resp = client.chat_postMessage(channel=channel, text=text, mrkdwn=True,
                                       unfurl_links=False, unfurl_media=False)
    except SlackApiError as e:
        err = e.response.get("error", str(e))
        hint = Hints.get(err, "")
        raise SystemExit(f"ERROR: Slack post failed: {err}" + (f" -- {hint}" if hint else ""))
    return resp["channel"], resp["ts"]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--file", required=True, help="Markdown file to post (normally msg.md)")
    ap.add_argument("--channel", default="", help="Slack channel ID, e.g. C0123456789")
    ap.add_argument("--print", action="store_true", dest="printOnly",
                    help="Print the converted Slack text and send nothing")
    args = ap.parse_args(argv)

    with open(args.file, encoding="utf-8") as handle:
        text = toSlack(handle.read())
    if args.printOnly:
        print(text)
        return 0
    if not args.channel:
        raise SystemExit("ERROR: --channel is required (or use --print to send nothing)")
    if not text:
        raise SystemExit(f"ERROR: {args.file!r} is empty; nothing to post")

    channel, ts = post(text, args.channel)
    print(f"posted channel={channel} ts={ts}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
