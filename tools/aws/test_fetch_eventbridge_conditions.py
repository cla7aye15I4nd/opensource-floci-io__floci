#!/usr/bin/env python3
"""Tests for fetch_eventbridge_conditions.py, on a page in the EventBridge user guide's markup."""
from __future__ import annotations

import pytest

import fetch_eventbridge_conditions as f


def row(key: str, value: str) -> str:
    return f"<tr><td><p><code>{key}</code></p></td><td><p>{value}</p></td><td><p>ArrayOfString, Null</p></td></tr>"


ROWS = (row("events:creatorAccount", "For creatorAccount, use the account ID for the account that created the rule.")
        + row("events:source", 'Use source for the literal string for the <b>source</b> field of the event such as '
                               '"aws.ec2".')
        + row("events: detail.service", "For service, use the literal string for the <b>detail.service</b> field of "
                                        "the event, such as \"ABUSE\".")
        + row("events:TargetArn", 'For target-arn, use the ARN of the target for the rule, for example "arn:aws:lambda:'
                                  '*:*:function:*".'))
SAYS = ("<p>the user must also have permissions for the <code>events:PutTargets</code> action because, if you want the "
        "rule to do more than publish a CloudWatch metric, you must also add a target to a rule.</p>"
        "<p>To grant access to a specific resource, use the <code>events:TargetArn</code> condition key.</p>"
        "<p>Policy B allows <code>PutRule</code> only if the event pattern of the rule being created matches Amazon "
        "EC2 events.</p><p><code>EventPattern</code> is a mandatory argument to <code>PutRule</code>.</p>")


def page(rows: str = ROWS, says: str = SAYS) -> str:
    return (f'<div id="main-col-body">{says}<table><tr><th>Condition key</th><th>Key value pair</th></tr>{rows}'
            f'</table></div><div class="prev-next"></div>')


def test_each_key_is_read_from_the_member_its_row_names():
    keys = {entry["key"]: entry for entry in f.build(lambda url: page())["keys"]}
    # A field of the event is read from the rule's event pattern, a target's ARN from each target; a key naming
    # neither is not read.
    assert (keys["events:source"]["operation"], keys["events:source"]["member"], keys["events:source"]["field"]) \
        == ("PutRule", "EventPattern", "source")
    assert keys["events:detail.service"]["field"] == "detail.service"
    assert (keys["events:TargetArn"]["operation"], keys["events:TargetArn"]["member"]) == ("PutTargets",
                                                                                           "Targets.*.Arn")
    assert "field" not in keys["events:TargetArn"]
    assert "events:creatorAccount" not in keys
    assert keys["events:source"]["says"][1] == "EventPattern is a mandatory argument to PutRule."


def test_a_page_whose_layout_changed_is_refused():
    for changed, message in ((page(rows=""), "no table"), (page(says=SAYS.replace("mandatory", "required")),
                                                            "no longer says where PutRule")):
        with pytest.raises(ValueError, match=message):
            f.build(lambda url: changed)


def test_the_file_is_stale_when_the_page_says_something_else():
    vendored = f.build(lambda url: page())
    assert not f.stale(vendored, page())
    assert f.stale(vendored, page(rows=ROWS.replace("<b>source</b> field", "<b>origin</b> field")))
