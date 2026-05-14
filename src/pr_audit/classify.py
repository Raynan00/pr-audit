"""Author classification: bot, core team, regular contributor, first-time."""
from __future__ import annotations

from .models import AuthorType


def classify_author(
    login: str,
    user_type: str | None,
    core_team: set[str],
    contributors: set[str],
) -> AuthorType:
    """Classify a PR author.

    `user_type` is the GitHub user object's "type" field which is "User" or "Bot".
    """
    if not login:
        return "unknown"
    lower = login.lower()
    if user_type == "Bot" or lower.endswith("[bot]") or lower in {"dependabot", "renovate"}:
        return "bot"
    if login in core_team:
        return "core_team"
    if login in contributors:
        return "regular_contributor"
    return "first_time"


def diff_size_bucket(additions: int, deletions: int) -> str:
    total = additions + deletions
    if total < 50:
        return "tiny"
    if total < 200:
        return "small"
    if total < 1000:
        return "medium"
    if total < 3000:
        return "large"
    return "xlarge"


def review_state_from_reviews(reviews: list[dict]) -> str:
    """Aggregate latest review state across all reviewers."""
    if not reviews:
        return "none"
    # Walk reviews in order; take the latest non-COMMENTED state per reviewer
    latest_by_user: dict[str, str] = {}
    for r in reviews:
        user = (r.get("user") or {}).get("login", "")
        state = r.get("state", "")
        if not user:
            continue
        if state in {"APPROVED", "CHANGES_REQUESTED", "DISMISSED", "COMMENTED"}:
            latest_by_user[user] = state
    if not latest_by_user:
        return "none"
    states = set(latest_by_user.values())
    if "CHANGES_REQUESTED" in states:
        return "changes_requested"
    if "APPROVED" in states:
        return "approved"
    if "COMMENTED" in states:
        return "commented"
    return "requested"


def has_tests_in_files(changed_files: list[str]) -> bool:
    """Heuristic: does the PR include any test file changes?"""
    test_markers = ("test_", "_test.", "/tests/", "/test/", ".test.", ".spec.")
    for path in changed_files:
        lower = path.lower()
        if any(marker in lower for marker in test_markers):
            return True
    return False
