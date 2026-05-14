"""Smoke tests for bucket assignment edge cases."""
from datetime import datetime, timezone

from pr_audit.buckets import _has_blocking_concerns, assign_buckets
from pr_audit.models import AIReview, PRRecord


def _rec(**overrides):
    base = dict(
        number=1,
        title="x",
        url="https://example.com/1",
        author="alice",
        author_type="core_team",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        age_days=2,
        stale_days=2,
        is_draft=False,
        is_dependabot=False,
        additions=20,
        deletions=5,
        files_changed=2,
        diff_size_bucket="small",
        has_tests=True,
        ci_status="passing",
        mergeable=True,
        mergeable_state="clean",
        review_state="none",
        comments_count=0,
    )
    base.update(overrides)
    return PRRecord(**base)


def test_quick_win_survives_nit_concerns():
    """A small PR with passing CI shouldn't be flagged just because the LLM listed 2 generic nits."""
    rec = _rec(
        ai_review=AIReview(
            score=8,
            merge_recommendation="merge",
            solves_issue="unclear",
            summary="Fine fix",
            concerns=["No tests included", "No linked issue"],
            strengths=[],
            blocking_question_for_author="",
        ),
    )
    assign_buckets([rec])
    assert rec.bucket == "quick_wins"


def test_quick_win_blocked_by_real_concern():
    """A small PR gets flagged when the LLM finds a blocking issue (e.g., 'will fail')."""
    rec = _rec(
        ai_review=AIReview(
            score=4,
            merge_recommendation="needs_changes",
            solves_issue="unclear",
            summary="Has a bug",
            concerns=["Critical: validator missing, test will fail", "No linked issue"],
            strengths=[],
            blocking_question_for_author="",
        ),
    )
    assign_buckets([rec])
    assert rec.bucket == "ai_flagged"


def test_close_recommendation_overrides_quick_win():
    rec = _rec(
        ai_review=AIReview(
            score=2,
            merge_recommendation="close",
            solves_issue="unclear",
            summary="Duplicate",
            concerns=["Duplicates open PR #5"],
            strengths=[],
            blocking_question_for_author="",
        ),
    )
    assign_buckets([rec])
    assert rec.bucket == "ai_flagged"


def test_stale_pending_ci_doesnt_block_quick_win():
    """An old PR with 'pending' CI gets treated as 'unknown' and can still be a quick win for trusted authors."""
    rec = _rec(ci_status="pending", stale_days=45)
    # stale_days > 30 actually disqualifies — bump down
    rec = _rec(ci_status="pending", stale_days=20, age_days=20)
    assign_buckets([rec])
    # ci=pending and stale_days>14 → ci normalizes to 'unknown' → still passes the gate for core_team
    assert rec.bucket == "quick_wins"


def test_has_blocking_concerns_signals():
    assert _has_blocking_concerns(
        AIReview(
            score=4, merge_recommendation="needs_changes", solves_issue="unclear",
            summary="x", concerns=["Critical: data loss risk"], strengths=[],
            blocking_question_for_author="",
        )
    )
    assert not _has_blocking_concerns(
        AIReview(
            score=8, merge_recommendation="merge", solves_issue="unclear",
            summary="x", concerns=["No tests included", "No linked issue"], strengths=[],
            blocking_question_for_author="",
        )
    )
