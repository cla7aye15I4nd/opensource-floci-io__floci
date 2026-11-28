#!/usr/bin/env python3
"""Vendor which role an AWS Backup request member names, and the service that role is for, into
tools/aws/sources/backup-roles.json, a source of the passed-roles table.

AWS's Service Reference passes StartScanJob's roles to `backup.amazonaws.com` and
`malware-protection.guardduty.amazonaws.com` without saying which member's role goes where, and botocore does not say
it as data either. The AWS Backup developer guide's page on malware protection names the two roles a scan takes, in
its Access section:

    First, the AWSBackupServiceRolePolicyForBackup or AWSBackupServiceRolePolicyForScans managed policy must be
    attached to your existing or new backup role. This is the same role found in the resource assignment for your
    backup plan in the console, or through the BackupSelection API. ...

    Second, a new scanner role is required with AWSBackupGuardDutyRolePolicyForScans managed policy that trusts
    malware-protection.guardduty.amazonaws.com. ...

    https://docs.aws.amazon.com/aws-backup/latest/devguide/malware-protection.html

the first linking the API reference's CreateBackupSelection page. This script copies each member's description on its
API reference page as it stands, the guide's item of its role, and from that item the service principal the role
trusts, or else the operation whose role the guide says it is (sameRoleAs). Nothing in the output is written by hand;
regen_iam_passed_roles.py reads it to choose, among the services the Service Reference passes an operation's roles to,
the one each member's role is for: the one the role trusts, or the one the Service Reference passes that operation's
role to.

Run from anywhere in the repo:
    python3 tools/aws/fetch_backup_roles.py           # rewrite the vendored file from the pages
    python3 tools/aws/fetch_backup_roles.py --verify  # online: the file still says what the pages do
"""
from __future__ import annotations

import argparse
import html
import json
import re
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

API_REFERENCE = "https://docs.aws.amazon.com/aws-backup/latest/APIReference/"
DEVELOPER_GUIDE = "https://docs.aws.amazon.com/aws-backup/latest/devguide/"
MALWARE_PROTECTION = DEVELOPER_GUIDE + "malware-protection.html"
REPO_ROOT = Path(__file__).resolve().parents[2]
OUTPUT = REPO_ROOT / "tools/aws/sources/backup-roles.json"

# The members that name a role, each by the API reference page and anchor describing it, with the words the malware
# protection page's Access section names its role by (`role`).
MEMBERS = (
    {"operation": "StartScanJob", "member": "IamRoleArn", "role": "backup role"},
    {"operation": "StartScanJob", "member": "ScannerRoleArn", "role": "scanner role"},
)
# The section of the malware protection page naming the roles a scan takes.
ACCESS_SECTION = "Access"
# An item's sentence naming the service principal its role trusts.
TRUSTS_RE = re.compile(r"\btrusts (?P<service>[a-z0-9.-]+\.amazonaws\.com)\b")
# An item's sentence naming the API reference page of the operation whose role its role is.
SAME_ROLE_RE = re.compile(r'This is the same role found in [^<]*(?:<(?!/p)[^>]*>[^<]*)*?<a href="(?P<href>[^"#]+)"')
OPERATION_PAGE_RE = re.compile(r"/API_(?P<operation>[A-Za-z0-9]+)\.html$")


def text(fragment: str) -> str:
    """A fragment of a page as text, spaces collapsed."""
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", fragment))).strip()


def api_page(member: dict) -> str:
    """The API reference page describing the member's operation."""
    return API_REFERENCE + "API_" + member["operation"] + ".html"


def anchor(member: dict) -> str:
    """The id of the member's entry on its API reference page."""
    return f"Backup-{member['operation']}-request-{member['member']}"


def read_description(page: str, member: dict) -> str:
    """The member's description on its API reference page, as text."""
    match = re.search(r'id="' + re.escape(anchor(member)) + r'"[^>]*>(?P<entry>.*?)</dd>', page, re.S)
    if match is None:
        raise ValueError(f"{api_page(member)} has no entry {anchor(member)}: its layout changed")
    entry = match.group("entry")
    described = re.search(r"<dd[^>]*>(?P<body>.*?)<p>\s*Type:", entry + "<p>Type:", re.S)
    return text(described.group("body") if described else entry)


def access_items(page: str) -> list[str]:
    """The items of the malware protection page's Access section, as markup."""
    match = re.search(r"<h2[^>]*>\s*" + re.escape(ACCESS_SECTION) + r"\s*</h2>(?P<body>.*?)(?=<h2|$)", page, re.S)
    if match is None:
        raise ValueError(f"{MALWARE_PROTECTION} has no section '{ACCESS_SECTION}': its layout changed")
    return re.findall(r'<li class="listitem">(.*?)</li>', match.group("body"), re.S)


def read_role(items: list[str], member: dict) -> dict:
    """What the Access section's one item naming the member's role says of it: the service principal it trusts, or
    else the operation whose role the guide says it is."""
    named = [item for item in items if member["role"] in text(item)]
    if len(named) != 1:
        raise ValueError(f"{MALWARE_PROTECTION}'s {ACCESS_SECTION} section names the {member['role']} in "
                         f"{len(named)} items, not one: its layout changed")
    item = named[0]
    found: dict = {"rolePage": MALWARE_PROTECTION, "section": ACCESS_SECTION, "roleText": text(item)}
    trusts = TRUSTS_RE.search(text(item))
    if trusts:
        return {**found, "trustedBy": [trusts.group("service")]}
    same = SAME_ROLE_RE.search(item)
    operation = OPERATION_PAGE_RE.search(urllib.parse.urljoin(MALWARE_PROTECTION, same.group("href"))) \
        if same else None
    if operation is None or not same.group("href").startswith(API_REFERENCE):
        raise ValueError(f"{MALWARE_PROTECTION} says neither what the {member['role']} trusts nor which operation's "
                         f"role it is: its layout changed")
    return {**found, "sameRoleAs": {"operation": operation.group("operation")}}


def build(fetch) -> dict:
    items = access_items(fetch(MALWARE_PROTECTION))
    members = []
    pages = []
    for member in MEMBERS:
        description = read_description(fetch(api_page(member)), member)
        members.append({"operation": member["operation"], "member": member["member"], "description": description,
                        **read_role(items, member)})
        pages.append(api_page(member))
    return {
        "_source": {
            "pages": list(dict.fromkeys(pages + [MALWARE_PROTECTION])),
            "fetcher": str(Path(__file__).resolve().relative_to(REPO_ROOT)),
            "retrieved": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "note": "Each member's description on its API reference page, copied as it stands; the malware "
                    "protection page's Access item naming its role (roleText); and from that item the service "
                    "principal the role trusts, or else the operation whose role the guide says it is (sameRoleAs).",
        },
        "members": members,
    }


def fetch_url(url: str) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": "floci-tools"})
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read().decode("utf-8")


def fetch_all(fetch=fetch_url) -> tuple:
    """The pages, each fetched once, as a reader of them."""
    cache: dict[str, str] = {}

    def cached(url: str) -> str:
        if url not in cache:
            cache[url] = fetch(url)
        return cache[url]

    build(cached)
    return (cache,)


def stale(vendored: dict, pages: dict[str, str]) -> bool:
    """Whether the pages now give something other than the vendored file, its date aside."""
    return vendored.get("members") != build(lambda url: pages[url])["members"]


def main(argv: list[str] | None = None, fetch=fetch_url) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--verify", action="store_true", help="online: the vendored file matches the pages")
    args = parser.parse_args(argv)
    try:
        (pages,) = fetch_all(fetch)
    except OSError as e:
        print(f"error: could not read the AWS Backup documentation ({e})", file=sys.stderr)
        return 2
    if args.verify:
        vendored = json.loads(OUTPUT.read_text(encoding="utf-8"))
        if stale(vendored, pages):
            print(f"error: {OUTPUT.relative_to(REPO_ROOT)} no longer says what the AWS Backup API reference and "
                  f"developer guide do: run tools/aws/fetch_backup_roles.py and then make iam-passed-roles-sync",
                  file=sys.stderr)
            return 1
        print(f"{OUTPUT.relative_to(REPO_ROOT)} matches the AWS Backup API reference and developer guide")
        return 0
    built = build(lambda url: pages[url])
    OUTPUT.write_text(json.dumps(built, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {OUTPUT.relative_to(REPO_ROOT)} ({len(built['members'])} members' roles)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
