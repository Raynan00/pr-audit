"""Data models for pr-audit."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

DiffSizeBucket = Literal["tiny", "small", "medium", "large", "xlarge"]
CIStatus = Literal["passing", "failing", "pending", "unknown"]
AuthorType = Literal["bot", "core_team", "regular_contributor", "first_time", "unknown"]
ReviewState = Literal["none", "requested", "approved", "changes_requested", "commented"]
SolvesIssue = Literal["yes", "partial", "no", "unclear", "no_linked_issue"]
MergeRec = Literal["merge", "needs_changes", "needs_discussion", "close"]
Bucket = Literal[
    "quick_wins",
    "high_impact",
    "contested",
    "ai_flagged",
    "stale",
    "risky",
    "everything_else",
]


class IssueRef(BaseModel):
    """Lightweight reference to an issue referenced by a PR."""

    number: int
    title: str = ""
    body: str = ""
    state: str = "open"
    reactions: int = 0
    labels: list[str] = Field(default_factory=list)


class RepoContext(BaseModel):
    """Repo-level context fetched once per audit and injected into every PR review.

    The point: stop reviewing diffs in isolation. Give the LLM the conventions,
    architecture, and prior-review patterns so its judgments are tuned to THIS
    repo, not a generic codebase.
    """

    name: str = ""  # owner/repo
    description: str = ""
    primary_language: str = ""
    readme_excerpt: str = ""
    contributing_excerpt: str = ""
    recent_merged_titles: list[str] = Field(default_factory=list)
    recent_review_excerpts: list[str] = Field(default_factory=list)


class PRContext(BaseModel):
    """Per-PR conversation context: comments and review comments from maintainers."""

    issue_comments: list[str] = Field(default_factory=list)  # PR conversation thread
    review_comments: list[str] = Field(default_factory=list)  # inline diff comments
    has_changes_requested: bool = False


class AIReview(BaseModel):
    """Structured output from the LLM review pass."""

    solves_issue: SolvesIssue = "no_linked_issue"
    score: int = 5
    strengths: list[str] = Field(default_factory=list)
    concerns: list[str] = Field(default_factory=list)
    merge_recommendation: MergeRec = "needs_discussion"
    summary: str = ""
    diff_truncated: bool = False
    error: str | None = None  # populated if review failed


class PRRecord(BaseModel):
    """All extracted facts about a single PR."""

    # Identity
    number: int
    title: str
    body: str = ""
    url: str
    author: str
    author_type: AuthorType = "unknown"

    # Timeline
    created_at: datetime
    updated_at: datetime
    age_days: int = 0
    stale_days: int = 0
    is_draft: bool = False
    is_dependabot: bool = False

    # Diff
    additions: int = 0
    deletions: int = 0
    files_changed: int = 0
    diff_size_bucket: DiffSizeBucket = "small"
    has_tests: bool = False
    changed_files: list[str] = Field(default_factory=list)

    # State
    ci_status: CIStatus = "unknown"
    mergeable: bool | None = None
    mergeable_state: str = "unknown"
    review_state: ReviewState = "none"
    comments_count: int = 0

    # Linkage
    linked_issues: list[int] = Field(default_factory=list)
    closes_high_demand: bool = False
    competing_prs: list[int] = Field(default_factory=list)
    labels: list[str] = Field(default_factory=list)

    # AI + smells
    smell_flags: list[str] = Field(default_factory=list)
    ai_review: AIReview | None = None

    # Bucket assignment
    bucket: Bucket = "everything_else"
    bucket_rank: int = 99
