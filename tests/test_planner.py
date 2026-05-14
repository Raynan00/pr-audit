"""Smoke tests for the merge planner's batching logic."""
from datetime import datetime, timezone
from unittest.mock import MagicMock

from pr_audit.models import AIReview, PRRecord
from pr_audit.planner import plan_merges


def _pr(number, bucket="quick_wins", score=9):
    return PRRecord(
        number=number,
        title=f"PR {number}",
        url=f"https://example.com/{number}",
        author="alice",
        author_type="core_team",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        age_days=1,
        stale_days=1,
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
        bucket=bucket,
        ai_review=AIReview(
            score=score, merge_recommendation="merge", solves_issue="unclear",
            summary="ok", concerns=[], strengths=[], blocking_question_for_author="",
        ),
    )


def _mock_client(files_by_pr):
    c = MagicMock()
    c.get_pull_files.side_effect = lambda owner, repo, n: [
        {"filename": f} for f in files_by_pr.get(n, [])
    ]
    return c


def test_non_overlapping_prs_share_a_batch():
    records = [_pr(1), _pr(2), _pr(3)]
    client = _mock_client({1: ["a.py"], 2: ["b.py"], 3: ["c.py"]})
    plan = plan_merges(records, client, "o", "r", top_n=3)
    assert len(plan.batches) == 1
    assert len(plan.batches[0].steps) == 3


def test_overlapping_prs_split_into_separate_batches():
    records = [_pr(1), _pr(2)]
    client = _mock_client({1: ["a.py"], 2: ["a.py"]})
    plan = plan_merges(records, client, "o", "r", top_n=2)
    assert len(plan.batches) == 2
    # Second batch's PR depends on first batch's PR for rebase
    assert plan.batches[1].steps[0].rebase_required_after == [1]


def test_low_score_pr_is_skipped():
    records = [_pr(1, score=4), _pr(2, score=9)]
    client = _mock_client({1: ["a.py"], 2: ["b.py"]})
    plan = plan_merges(records, client, "o", "r", top_n=2, min_score=7)
    assert len(plan.batches) == 1
    assert plan.batches[0].steps[0].pr.number == 2
    assert any(pr.number == 1 for pr, _ in plan.skipped)


def test_dirty_pr_is_skipped():
    rec = _pr(1)
    rec.mergeable_state = "dirty"
    client = _mock_client({1: ["a.py"]})
    plan = plan_merges([rec], client, "o", "r", top_n=1)
    assert plan.batches == []
    assert plan.skipped[0][0].number == 1
