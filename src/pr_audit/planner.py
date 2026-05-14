"""Merge planner: takes ranked PRs and produces a stack-aware merge order.

For each candidate PR, fetch its changed file paths, then group PRs into
rebase-independent batches (no file overlap inside a batch). Within a batch,
PRs can be merged in any order. Across batches, later PRs may need a rebase
after earlier ones merge.

Used by `pr-audit ... --plan-merges N` and by the merge_planner skill script.
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field

from .fetch import GitHubClient
from .models import PRRecord


@dataclass
class MergeStep:
    pr: PRRecord
    files: list[str]
    rebase_required_after: list[int]  # PR numbers whose merge will force this one to rebase
    rebase_complexity: str  # "trivial", "moderate", "manual" (line-range overlap detection)


@dataclass
class MergeBatch:
    """A set of PRs that can be merged in any order without inter-batch rebase."""

    steps: list[MergeStep] = field(default_factory=list)

    def files(self) -> set[str]:
        out: set[str] = set()
        for s in self.steps:
            out.update(s.files)
        return out


@dataclass
class MergePlan:
    batches: list[MergeBatch]
    skipped: list[tuple[PRRecord, str]]  # (PR, reason)

    def to_markdown(self) -> str:
        if not self.batches and not self.skipped:
            return "_No merge candidates._\n"

        lines: list[str] = []
        for i, batch in enumerate(self.batches, start=1):
            label = "rebase-independent batch" if len(batch.steps) > 1 else "single PR"
            lines.append(f"### Batch {i} ({label}, {len(batch.steps)} PR{'s' if len(batch.steps) != 1 else ''})")
            lines.append("")
            for step in batch.steps:
                pr = step.pr
                files_str = ", ".join(step.files[:3]) + (f" +{len(step.files) - 3} more" if len(step.files) > 3 else "")
                ai_bit = ""
                if pr.ai_review and not pr.ai_review.error:
                    ai_bit = f" — score {pr.ai_review.score}/10"
                rebase_bit = ""
                if step.rebase_required_after:
                    after = ", ".join(f"#{n}" for n in step.rebase_required_after)
                    rebase_bit = f" (rebase {step.rebase_complexity} after {after})"
                lines.append(f"- **[#{pr.number}]({pr.url})** {pr.title[:80]}{ai_bit}{rebase_bit}")
                lines.append(f"  - files: {files_str or '(none)'}")
            lines.append("")

        if self.skipped:
            lines.append("### Skipped (not merge-ready)")
            lines.append("")
            for pr, reason in self.skipped:
                lines.append(f"- **[#{pr.number}]({pr.url})** {pr.title[:80]} — {reason}")
            lines.append("")

        return "\n".join(lines) + "\n"


def plan_merges(
    records: Iterable[PRRecord],
    client: GitHubClient,
    owner: str,
    repo: str,
    *,
    top_n: int = 5,
    min_score: int = 7,
    eligible_buckets: tuple[str, ...] = ("quick_wins", "high_impact"),
) -> MergePlan:
    """Build a merge plan for the top-N mergeable PRs.

    A PR is eligible if:
      - It's in `eligible_buckets`
      - mergeable_state is clean
      - ci_status is passing or unknown
      - LLM score is None or >= min_score
    """
    candidates: list[PRRecord] = []
    skipped: list[tuple[PRRecord, str]] = []

    for r in records:
        if r.bucket not in eligible_buckets:
            continue
        if r.mergeable_state not in {"clean", None}:
            skipped.append((r, f"mergeable_state={r.mergeable_state}"))
            continue
        if r.ci_status not in {"passing", "unknown"}:
            skipped.append((r, f"ci={r.ci_status}"))
            continue
        if r.ai_review and not r.ai_review.error and r.ai_review.score < min_score:
            skipped.append((r, f"AI score {r.ai_review.score} < {min_score}"))
            continue
        candidates.append(r)
        if len(candidates) >= top_n * 2:  # cap fetches
            break

    # Fetch changed files for each candidate
    files_by_pr: dict[int, list[str]] = {}
    for r in candidates:
        try:
            files = client.get_pull_files(owner, repo, r.number)
            files_by_pr[r.number] = [f.get("filename", "") for f in files if f.get("filename")]
        except Exception as e:
            skipped.append((r, f"file fetch failed: {e}"))

    eligible = [r for r in candidates if r.number in files_by_pr]
    eligible = eligible[:top_n]

    # Greedy batching: each PR goes into the first batch whose files don't overlap
    batches: list[MergeBatch] = []
    for r in eligible:
        files = set(files_by_pr[r.number])
        placed = False
        for batch in batches:
            if not (files & batch.files()):
                batch.steps.append(MergeStep(pr=r, files=sorted(files), rebase_required_after=[], rebase_complexity="trivial"))
                placed = True
                break
        if not placed:
            # Find which earlier PRs this one conflicts with for rebase tracking
            conflict_prs: list[int] = []
            for batch in batches:
                for step in batch.steps:
                    if files & set(step.files):
                        conflict_prs.append(step.pr.number)
            new_batch = MergeBatch(steps=[MergeStep(
                pr=r,
                files=sorted(files),
                rebase_required_after=conflict_prs,
                rebase_complexity="trivial" if len(conflict_prs) <= 1 else "moderate",
            )])
            batches.append(new_batch)

    return MergePlan(batches=batches, skipped=skipped)
