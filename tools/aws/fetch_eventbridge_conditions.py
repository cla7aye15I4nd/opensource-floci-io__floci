#!/usr/bin/env python3
"""Vendor which request member carries each EventBridge condition key a rule's request takes into
tools/aws/sources/eventbridge-condition-keys.json, a source of the request condition key table.

AWS's Service Reference gives PutRule the keys `events:source`, `events:detail-type` and the `events:detail.*` keys,
and PutTargets `events:TargetArn`, without saying where a request carries them, and botocore does not say it either:
it models PutRule's EventPattern as a string ("The event pattern") and PutTargets' Targets as the targets it adds.
EventBridge's user guide says, in its table of condition keys, what each one holds:

    events:source        Use source for the literal string for the source field of the event such as "aws.ec2"
    events:TargetArn     For target-arn, use the ARN of the target for the rule

and that the event's fields are those of the event pattern of the rule PutRule creates, and the target the one a
rule is given:

    Policy B allows PutRule only if the event pattern of the rule being created matches Amazon EC2 events.
    EventPattern is a mandatory argument to PutRule.
    ... you must also add a target to a rule.
    To grant access to a specific resource, use the events:TargetArn condition key.

    https://docs.aws.amazon.com/eventbridge/latest/userguide/eb-use-conditions.html

This script copies each key's row of that table as it stands, with the sentence saying where its value is, and gives
each key whose row names a field of the event that field, read from PutRule's EventPattern, and the key whose row names
the ARN of the target, read from each of PutTargets' Targets. A row naming neither is not read. Nothing in the output
is written by hand; regen_request_condition_keys.py reads it to give the table those members.

Run from anywhere in the repo:
    python3 tools/aws/fetch_eventbridge_conditions.py           # rewrite the vendored file from the page
    python3 tools/aws/fetch_eventbridge_conditions.py --verify  # online: the file still says what the page does
"""
from __future__ import annotations

import argparse
import html
import json
import re
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

PAGE = "https://docs.aws.amazon.com/eventbridge/latest/userguide/eb-use-conditions.html"
REPO_ROOT = Path(__file__).resolve().parents[2]
OUTPUT = REPO_ROOT / "tools/aws/sources/eventbridge-condition-keys.json"

# The members the page says carry the keys, each with what a key's row says of its value and the sentences of the page
# that say where the request carries it: a field of the event, read from the event pattern of the rule PutRule
# creates, and the ARN of a target, read from each target PutTargets adds to a rule.
MEMBERS = (
    {"operation": "PutRule", "member": "EventPattern",
     "row": re.compile(r"\bthe literal string for the (?P<field>[A-Za-z][\w.-]*) field of the event\b"),
     "says": (re.compile(r"\bPutRule only if the event pattern of the rule being created\b[^.]*\."),
              re.compile(r"\bEventPattern is a mandatory argument to PutRule\s*\.")),
     "document": True},
    {"operation": "PutTargets", "member": "Targets.*.Arn",
     "row": re.compile(r"\buse the ARN of the target for the rule\b"),
     "says": (re.compile(r"\bpermissions for the events:PutTargets action because[^.]*add a target to a rule\."),
              re.compile(r"\bTo grant access to a specific resource, use the events:TargetArn condition key\.")),
     "document": False},
)
KEY_RE = re.compile(r"^events:[\w./-]+$")


def text(fragment: str) -> str:
    """A fragment of a page as text, spaces collapsed and none left before a full stop."""
    return re.sub(r"\s+([.,])", r"\1", re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", fragment)))).strip()


def body(page: str) -> str:
    """The page's own content, its navigation left out."""
    match = re.search(r'<div id="main-col-body">(?P<body>.*?)(?:<div class="prev-next"|$)', page, re.S)
    return match.group("body") if match else page


def key_rows(page: str) -> list[tuple[str, str]]:
    """Each EventBridge key of the page's table of condition keys, with its row's key and value pair as text."""
    for table in re.findall(r"<table[^>]*>(.*?)</table>", body(page), re.S):
        rows = []
        for row in re.findall(r"<tr>(.*?)</tr>", table, re.S):
            cells = [text(cell) for cell in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row, re.S)]
            key = cells[0].replace(" ", "") if cells else ""
            if len(cells) > 1 and KEY_RE.match(key):
                rows.append((key, cells[1]))
        if rows:
            return rows
    raise ValueError(f"{PAGE} has no table of EventBridge condition keys: its layout changed")


def build(fetch) -> dict:
    page = fetch(PAGE)
    content = text(body(page))
    keys = []
    for member in MEMBERS:
        said = [found.group(0) for found in (pattern.search(content) for pattern in member["says"]) if found]
        if len(said) != len(member["says"]):
            raise ValueError(f"{PAGE} no longer says where {member['operation']}'s {member['member']} carries its "
                             f"keys: its layout changed")
        for key, row in key_rows(page):
            found = member["row"].search(row)
            if found is None:
                continue
            entry = {"key": key, "operation": member["operation"], "member": member["member"]}
            if member["document"]:
                entry["field"] = found.group("field")
            keys.append({**entry, "row": row, "says": said})
    if not keys:
        raise ValueError(f"{PAGE} names no key's member: its layout changed")
    return {
        "_source": {
            "page": PAGE,
            "fetcher": str(Path(__file__).resolve().relative_to(REPO_ROOT)),
            "retrieved": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "note": "Each EventBridge key whose row of the page's table of condition keys names a field of the event, "
                    "read from PutRule's EventPattern (field), or the ARN of the target, read from PutTargets' "
                    "Targets[].Arn, with the row and the page's sentences saying so, copied as they stand.",
        },
        "keys": sorted(keys, key=lambda entry: (entry["operation"], entry["key"])),
    }


def fetch_url(url: str) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": "floci-tools"})
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read().decode("utf-8")


def stale(vendored: dict, page: str) -> bool:
    """Whether the page now gives something other than the vendored file, its date aside."""
    return vendored.get("keys") != build(lambda url: page)["keys"]


def main(argv: list[str] | None = None, fetch=fetch_url) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--verify", action="store_true", help="online: the vendored file matches the page")
    args = parser.parse_args(argv)
    try:
        page = fetch(PAGE)
    except OSError as e:
        print(f"error: could not read the EventBridge user guide ({e})", file=sys.stderr)
        return 2
    if args.verify:
        vendored = json.loads(OUTPUT.read_text(encoding="utf-8"))
        if stale(vendored, page):
            print(f"error: {OUTPUT.relative_to(REPO_ROOT)} no longer says what the EventBridge user guide does: run "
                  f"tools/aws/fetch_eventbridge_conditions.py and then make request-condition-keys-sync",
                  file=sys.stderr)
            return 1
        print(f"{OUTPUT.relative_to(REPO_ROOT)} matches the EventBridge user guide")
        return 0
    built = build(lambda url: page)
    OUTPUT.write_text(json.dumps(built, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {OUTPUT.relative_to(REPO_ROOT)} ({len(built['keys'])} keys)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
