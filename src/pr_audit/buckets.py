"""Bucket assignment: classify each PR into one of 7 buckets and rank within."""
from __future__ import annotations

from .models import Bucket, PRRecord

STALE_DAYS = 60


def assign_buckets(records: list[PRRecord]) -> None:
    """Assign each record to a bucket and a bucket_rank.

    Order of evaluation (a PR lands in the FIRST matching bucket):
    1. contested
    2. quick_wins  (small + passing + clean -- evaluated before ai_flagged
                    so reflex LLM nits don't veto a mergeable PR)
    3. high_impact
    4. ai_flagged  (only fires on close-reco or blocking concerns)
    5. stale
    6. risky
    7. everything_else
    """
    for r in records:
        r.bucket = _bucket_for(r)

    _rank_within_buckets(records)


_BLOCKING_TERMS = (
    "critical",
    "blocker",
    "blocking",
    "data loss",
    "security",
    "wrong",
    "broken",
    "missing field",
    "race condition",
    "sql injection",
    "auth bypass",
    "regress",
    "breaking change",
    "fails",
    "will fail",
    "not implement",
)


def _has_blocking_concerns(ai) -> bool:
    """A concern is 'blocking' if it mentions a hard failure mode, not just a nit.

    Generic concerns like 'no tests' or 'no linked issue' don't qualify.
    """
    if not ai or ai.error or not ai.concerns:
        return False
    for c in ai.concerns:
        cl = c.lower()
        if any(term in cl for term in _BLOCKING_TERMS):
            return True
    return False


def _ci_normalized(r: PRRecord) -> str:
    """Treat stale-pending CI as 'unknown' so old PRs don't masquerade as in-flight.

    GitHub's combined-status endpoint sometimes returns 'pending' on PRs whose
    workflows haven't re-run in weeks. We don't want to penalize a real quick win
    just because its CI status string says 'pending' when it's actually clean.
    """
    if r.ci_status == "pending" and r.stale_days > 14:
        return "unknown"
    return r.ci_status


def _bucket_for(r: PRRecord) -> Bucket:
    ci = _ci_normalized(r)

    # 1. Contested: multiple PRs solving the same issue
    if r.competing_prs:
        return "contested"

    # 2. Quick wins (evaluated BEFORE ai_flagged so the LLM's reflex nits don't
    #    veto a clearly-mergeable PR). LLM concerns still surface as notes.
    if (
        ci in {"passing", "unknown"}
        and r.mergeable is not False
        and r.diff_size_bucket in {"tiny", "small"}
        and r.stale_days < 30
        and r.review_state != "changes_requested"
        and not r.is_draft
    ):
        # Quick wins also require: if AI reviewed, score must be >= 6.
        # A low score means the LLM has hesitation even if no concern hit a blocking term.
        ai_ok = (
            r.ai_review is None
            or r.ai_review.error is not None
            or (r.ai_review.score >= 6 and r.ai_review.merge_recommendation != "close")
        )

        # Bots and trusted contributors are the clearest wins
        if r.is_dependabot or r.author_type in {"core_team", "regular_contributor"}:
            if not ai_ok:
                return "ai_flagged"
            if _has_blocking_concerns(r.ai_review):
                return "ai_flagged"
            return "quick_wins"
        # First-timers with passing CI + tests are also quick wins
        if r.has_tests and ci == "passing":
            if not ai_ok:
                return "ai_flagged"
            if _has_blocking_concerns(r.ai_review):
                return "ai_flagged"
            return "quick_wins"

    # 3. High-impact: closes a high-demand issue, mid/large with passing CI
    if (
        r.closes_high_demand
        and ci in {"passing", "pending", "unknown"}
        and r.diff_size_bucket in {"medium", "large", "xlarge"}
        and not r.is_draft
    ):
        return "high_impact"

    # 4. AI-flagged: serious concerns from LLM review.
    #    Only fires when the LLM is genuinely worried, not just nitpicking.
    if r.ai_review and r.ai_review.error is None:
        rec = r.ai_review.merge_recommendation
        if rec == "close":
            return "ai_flagged"
        if rec == "needs_changes" and _has_blocking_concerns(r.ai_review):
            return "ai_flagged"
        if "hardcoded_secret" in ",".join(r.smell_flags):
            return "ai_flagged"

    # 5. Stale: old, no activity, or in bad merge state
    if (
        r.stale_days > STALE_DAYS
        or r.mergeable_state in {"dirty", "blocked"}
        or (r.ci_status == "failing" and r.stale_days > 14)
    ):
        return "stale"

    # 6. Risky: large diff, no tests, failing or unknown CI
    if r.diff_size_bucket in {"large", "xlarge"} and (not r.has_tests or r.ci_status == "failing"):
        return "risky"

    return "everything_else"


def _rank_within_buckets(records: list[PRRecord]) -> None:
    """Assign bucket_rank (0-indexed) ordering each bucket sensibly."""
    by_bucket: dict[Bucket, list[PRRecord]] = {}
    for r in records:
        by_bucket.setdefault(r.bucket, []).append(r)

    for bucket, items in by_bucket.items():
        if bucket == "quick_wins":
            items.sort(key=lambda x: (not x.is_dependabot, -x.age_days))
        elif bucket == "high_impact":
            items.sort(
                key=lambda x: (
                    -(x.ai_review.score if x.ai_review and not x.ai_review.error else 5),
                    -x.age_days,
                )
            )
        elif bucket == "contested":
            items.sort(key=lambda x: (min(x.linked_issues) if x.linked_issues else 0, x.created_at))
        elif bucket == "ai_flagged":
            items.sort(key=lambda x: -len(x.ai_review.concerns if x.ai_review else []))
        elif bucket == "stale":
            items.sort(key=lambda x: -x.stale_days)
        elif bucket == "risky":
            items.sort(key=lambda x: -(x.additions + x.deletions))
        else:
            items.sort(key=lambda x: -x.age_days)
        for i, r in enumerate(items):
            r.bucket_rank = i
