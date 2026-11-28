#!/usr/bin/env python3
"""Tests for fetch_backup_roles.py, on pages in the AWS Backup API reference's and developer guide's markup."""
from __future__ import annotations

import pytest

import fetch_backup_roles as f

API = f.API_REFERENCE


def entry(member: str, description: str) -> str:
    return (f'<dl><dt id="Backup-StartScanJob-request-{member}"><b><code class="code">{member}</code></b></dt>'
            f'<dd><p>{description}</p><p>Type: String</p></dd></dl>')


BACKUP_ROLE = ('<li class="listitem"><p>First, the <a href="https://docs.aws.amazon.com/aws-managed-policy/latest/'
               'reference/AWSBackupServiceRolePolicyForScans.html">AWSBackupServiceRolePolicyForScans</a> managed '
               'policy must be attached to your existing or new backup role. This is the same role found in the '
               'resource assignment for your backup plan in the console, or through the <a href="' + API
               + 'API_CreateBackupSelection.html">BackupSelection API</a>.</p></li>')
SCANNER_ROLE = ('<li class="listitem"><p>Second, a new scanner role is required that trusts <code class="code">'
                'malware-protection.guardduty.amazonaws.com</code>. This is the same role found in the scan settings '
                'in your <a href="' + API + 'API_CreateBackupPlan.html">BackupPlan API</a>.</p></li>')


def malware(items: str) -> str:
    return ('<div id="main-col-body"><h2 id="malware-access">Access</h2><p>AWS Backup malware scanning requires two '
            f'IAM roles:</p><ul class="itemizedlist">{items}</ul><h2 id="next">Incremental vs full scans</h2></div>')


PAGES = {
    API + "API_StartScanJob.html": (
        entry("IamRoleArn", "Specifies the IAM role ARN used to create the target recovery point.")
        + entry("ScannerRoleArn", "Specified the IAM scanner role ARN.")),
    f.MALWARE_PROTECTION: malware(BACKUP_ROLE + SCANNER_ROLE),
}


def test_each_member_is_read_with_what_the_guide_says_of_its_role():
    built = f.build(lambda url: PAGES[url])
    by_member = {m["member"]: m for m in built["members"]}
    # The scanner role trusts its service; the backup role is CreateBackupSelection's, the operation its item links.
    assert by_member["ScannerRoleArn"]["trustedBy"] == ["malware-protection.guardduty.amazonaws.com"]
    assert "sameRoleAs" not in by_member["ScannerRoleArn"]
    assert by_member["IamRoleArn"]["sameRoleAs"] == {"operation": "CreateBackupSelection"}
    assert "trustedBy" not in by_member["IamRoleArn"]
    assert by_member["IamRoleArn"]["description"].startswith("Specifies the IAM role ARN used to create")
    assert by_member["IamRoleArn"]["roleText"].startswith("First, the AWSBackupServiceRolePolicyForScans")


def test_a_page_whose_layout_changed_is_refused():
    for url, page, message in (
            (API + "API_StartScanJob.html", entry("ScannerRoleArn", "A role."), "has no entry"),
            (f.MALWARE_PROTECTION, "<div id=\"main-col-body\"></div>", "has no section"),
            (f.MALWARE_PROTECTION, malware(SCANNER_ROLE), "names the backup role in 0 items"),
            (f.MALWARE_PROTECTION, malware(BACKUP_ROLE.replace("This is the same role found in", "It is like")
                                           + SCANNER_ROLE), "neither what the backup role trusts")):
        changed = dict(PAGES, **{url: page})
        with pytest.raises(ValueError, match=message):
            f.build(lambda u: changed[u])


def test_the_file_is_stale_when_a_page_says_something_else():
    vendored = f.build(lambda url: PAGES[url])
    assert not f.stale(vendored, PAGES)
    assert f.stale(vendored, dict(PAGES, **{f.MALWARE_PROTECTION: malware(
        BACKUP_ROLE + SCANNER_ROLE.replace("malware-protection.guardduty", "guardduty"))}))
