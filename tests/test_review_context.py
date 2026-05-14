"""Smoke tests for repo/PR context injection into the LLM review prompt."""
from pr_audit.models import PRContext, RepoContext
from pr_audit.review import build_prompt


def test_prompt_works_without_context():
    """No context = same shape as before, no crash."""
    p = build_prompt("Add foo", "Fixes bar.", "+def foo(): pass\n", linked_issue=None)
    assert "Add foo" in p
    assert "=== REPO CONTEXT ===" not in p
    assert "=== PR DISCUSSION ===" not in p


def test_prompt_includes_repo_context():
    rc = RepoContext(
        name="airweave-ai/airweave",
        description="Context retrieval for AI agents",
        primary_language="Python",
        readme_excerpt="Airweave syncs your data sources into a vector store.",
        contributing_excerpt="Run pytest before pushing. Use ruff for formatting.",
        recent_merged_titles=["fix(google_drive): handle 403 on shared drives", "feat: add Notion connector"],
        recent_review_excerpts=["This needs a test for the timeout path.", "Please add a docstring here."],
    )
    p = build_prompt("Foo", "", "+def x(): pass\n", linked_issue=None, repo_context=rc)
    assert "=== REPO CONTEXT ===" in p
    assert "Airweave syncs" in p
    assert "Run pytest before pushing" in p
    assert "fix(google_drive): handle 403" in p
    assert "This needs a test for the timeout path." in p


def test_prompt_includes_pr_discussion():
    pc = PRContext(
        issue_comments=["maintainer: please add tests for the empty-input case"],
        review_comments=["reviewer: this regex won't catch Unicode whitespace"],
        has_changes_requested=True,
    )
    p = build_prompt("Foo", "", "+def x(): pass\n", linked_issue=None, pr_context=pc)
    assert "=== PR DISCUSSION ===" in p
    assert "please add tests for the empty-input" in p
    assert "Unicode whitespace" in p
    assert "changes on this PR" in p  # the changes-requested note


def test_prompt_drops_empty_pr_context():
    pc = PRContext()  # no comments
    p = build_prompt("Foo", "", "+def x(): pass\n", linked_issue=None, pr_context=pc)
    assert "=== PR DISCUSSION ===" not in p
