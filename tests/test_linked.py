"""Smoke tests for linked-issue parser."""
from pr_audit.linked import parse_linked_issues, parse_mentioned_issues


def test_closes_keyword():
    body = "This closes #123 and also fixes #456"
    assert parse_linked_issues(body) == [123, 456]


def test_resolves_capitalized():
    body = "Resolves #789"
    assert parse_linked_issues(body) == [789]


def test_no_links():
    assert parse_linked_issues("Random text with no refs") == []


def test_branch_name_keyword():
    assert parse_linked_issues("", branch_name="fix/closes-#42") == [42]


def test_mentioned_issues():
    body = "See #1, #2, and discussion in #3"
    assert parse_mentioned_issues(body) == [1, 2, 3]


def test_empty_body():
    assert parse_linked_issues(None) == []
    assert parse_mentioned_issues(None) == []
