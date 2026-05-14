"""Per-PR feature extraction. Orchestrates calls to GitHubClient and assembles PRRecord."""
from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from datetime import datetime, timezone

from .classify import (
    classify_author,
    diff_size_bucket,
    has_tests_in_files,
    review_state_from_reviews,
)
from .fetch import GitHubClient
from .linked import parse_linked_issues
from .models import AuthorType, CIStatus, IssueRef, PRContext, PRRecord, RepoContext


def _parse_dt(value: str | None) -> datetime:
    if not value:
        return datetime.now(tz=timezone.utc)
    s = value.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(s)
    except Exception:
        return datetime.now(tz=timezone.utc)


def _ci_status(combined: dict | None, check_runs: dict | None) -> CIStatus:
    """Aggregate combined status + check runs into one CI status.

    The legacy /status endpoint returns 'pending' for repos that don't use the
    classic commit-status API (which is most modern repos using only GitHub
    Actions). When check_runs are present, they are authoritative: if every
    check_run has conclusion=success, the PR is passing regardless of what
    combined.state says.
    """
    check_states: list[str] = []
    if check_runs:
        for run in check_runs.get("check_runs", []):
            conclusion = run.get("conclusion") or run.get("status")
            if conclusion:
                check_states.append(conclusion)

    # Authoritative path: trust check_runs when present
    if check_states:
        has_failure = any(s in {"failure", "error", "timed_out", "cancelled", "action_required"} for s in check_states)
        if has_failure:
            return "failing"
        has_pending = any(s in {"pending", "in_progress", "queued", "waiting"} for s in check_states)
        if has_pending:
            return "pending"
        has_success = any(s in {"success", "neutral", "completed"} for s in check_states)
        return "passing" if has_success else "unknown"

    # Fallback: legacy combined status only
    if combined:
        state = combined.get("state", "unknown")
        if state == "success":
            return "passing"
        if state == "failure" or state == "error":
            return "failing"
        if state == "pending":
            return "pending"
    return "unknown"


def issue_reaction_total(issue: dict) -> int:
    """Sum of meaningful positive reactions on an issue."""
    reactions = issue.get("reactions") or {}
    return int(reactions.get("+1", 0)) + int(reactions.get("heart", 0)) + int(reactions.get("hooray", 0)) + int(reactions.get("rocket", 0))


def issue_is_high_demand(issue: dict) -> bool:
    """An issue is 'high demand' if it has reactions or specific labels."""
    if not issue:
        return False
    if issue_reaction_total(issue) >= 5:
        return True
    labels = {(lbl.get("name") or "").lower() for lbl in (issue.get("labels") or [])}
    if labels & {"help wanted", "good first issue", "enhancement"}:
        return True
    return False


def build_pr_record(
    client: GitHubClient,
    owner: str,
    repo: str,
    pr_summary: dict,
    core_team: set[str],
    contributors: set[str],
) -> PRRecord:
    """Fetch full PR details and assemble a PRRecord."""
    number = pr_summary["number"]
    full = client.get_pull(owner, repo, number) or pr_summary

    author_login = (full.get("user") or {}).get("login", "")
    author_type: AuthorType = classify_author(
        author_login,
        (full.get("user") or {}).get("type"),
        core_team,
        contributors,
    )

    additions = int(full.get("additions") or 0)
    deletions = int(full.get("deletions") or 0)
    files_changed = int(full.get("changed_files") or 0)
    bucket_size = diff_size_bucket(additions, deletions)

    # Fetch file list to detect test paths
    files = client.get_pull_files(owner, repo, number)
    changed_paths = [f.get("filename", "") for f in files]
    has_tests = has_tests_in_files(changed_paths)

    # Review state
    reviews = client.list_pull_reviews(owner, repo, number)
    review_state = review_state_from_reviews(reviews)

    # CI status: use head commit sha
    head_sha = (full.get("head") or {}).get("sha", "")
    combined = None
    check_runs = None
    if head_sha:
        try:
            combined = client.get_combined_status(owner, repo, head_sha)
        except Exception:
            combined = None
        try:
            check_runs = client.get_check_runs(owner, repo, head_sha)
        except Exception:
            check_runs = None
    ci = _ci_status(combined, check_runs)

    created_at = _parse_dt(full.get("created_at"))
    updated_at = _parse_dt(full.get("updated_at"))
    now = datetime.now(tz=timezone.utc)
    age_days = max(0, (now - created_at).days)
    stale_days = max(0, (now - updated_at).days)

    branch_name = (full.get("head") or {}).get("ref", "")
    linked = parse_linked_issues(full.get("body"), branch_name)

    labels = [(lbl.get("name") or "") for lbl in (full.get("labels") or [])]

    return PRRecord(
        number=number,
        title=full.get("title", ""),
        body=full.get("body") or "",
        url=full.get("html_url", ""),
        author=author_login,
        author_type=author_type,
        created_at=created_at,
        updated_at=updated_at,
        age_days=age_days,
        stale_days=stale_days,
        is_draft=bool(full.get("draft")),
        is_dependabot=author_type == "bot" and "dependabot" in author_login.lower(),
        additions=additions,
        deletions=deletions,
        files_changed=files_changed,
        diff_size_bucket=bucket_size,
        has_tests=has_tests,
        changed_files=changed_paths[:200],
        ci_status=ci,
        mergeable=full.get("mergeable"),
        mergeable_state=full.get("mergeable_state") or "unknown",
        review_state=review_state,
        comments_count=int(full.get("comments") or 0) + int(full.get("review_comments") or 0),
        linked_issues=linked,
        labels=labels,
    )


def attach_issue_demand(records: Iterable[PRRecord], issues_by_number: dict[int, dict]) -> None:
    """Mark `closes_high_demand` on PRs based on issue reactions/labels."""
    for r in records:
        if not r.linked_issues:
            continue
        for n in r.linked_issues:
            issue = issues_by_number.get(n)
            if issue and issue_is_high_demand(issue):
                r.closes_high_demand = True
                break


def detect_competing(records: list[PRRecord]) -> None:
    """For each PR, populate competing_prs (other PRs that link the same issue)."""
    issue_to_prs: dict[int, list[int]] = defaultdict(list)
    for r in records:
        for n in r.linked_issues:
            issue_to_prs[n].append(r.number)
    for r in records:
        competitors: set[int] = set()
        for n in r.linked_issues:
            for other in issue_to_prs[n]:
                if other != r.number:
                    competitors.add(other)
        r.competing_prs = sorted(competitors)


def issues_to_map(issues: list[dict]) -> dict[int, dict]:
    """Filter out PRs (the /issues endpoint returns both) and map by number."""
    out: dict[int, dict] = {}
    for i in issues:
        if "pull_request" in i:
            continue
        out[int(i["number"])] = i
    return out


def build_issue_ref(issue: dict | None) -> IssueRef | None:
    if not issue:
        return None
    return IssueRef(
        number=int(issue["number"]),
        title=issue.get("title", ""),
        body=issue.get("body", "") or "",
        state=issue.get("state", "open"),
        reactions=issue_reaction_total(issue),
        labels=[(lbl.get("name") or "") for lbl in (issue.get("labels") or [])],
    )


def fetch_repo_context(client: GitHubClient, owner: str, repo: str) -> RepoContext:
    """One-shot retrieval of repo-level context for the LLM reviewer.

    Returns a RepoContext with README excerpt, CONTRIBUTING.md excerpt, recent
    merged PR titles, and short examples of past review-comment language. The
    LLM uses these to tune its review to THIS repo's conventions instead of
    judging diffs in a vacuum.
    """
    repo_meta = client.get_repo(owner, repo) or {}
    readme = client.get_file_contents(owner, repo, "README.md") or ""
    contributing = (
        client.get_file_contents(owner, repo, "CONTRIBUTING.md")
        or client.get_file_contents(owner, repo, ".github/CONTRIBUTING.md")
        or ""
    )

    recent_merged = client.list_recent_merged_pulls(owner, repo, limit=20)
    recent_titles = [p.get("title", "") for p in recent_merged if p.get("title")]

    # Sample review-comment excerpts from a handful of recent merged PRs so the
    # LLM picks up on the maintainers' voice and what they actually push back on.
    review_excerpts: list[str] = []
    for p in recent_merged[:5]:
        number = p.get("number")
        if not number:
            continue
        for c in client.list_pull_review_comments(owner, repo, number)[:3]:
            body = (c.get("body") or "").strip()
            if 20 <= len(body) <= 280:  # skip greetings and walls of text
                review_excerpts.append(body)
        if len(review_excerpts) >= 8:
            break

    return RepoContext(
        name=f"{owner}/{repo}",
        description=repo_meta.get("description") or "",
        primary_language=repo_meta.get("language") or "",
        readme_excerpt=readme[:3000],
        contributing_excerpt=contributing[:3000],
        recent_merged_titles=recent_titles[:20],
        recent_review_excerpts=review_excerpts[:8],
    )


def fetch_pr_context(client: GitHubClient, owner: str, repo: str, number: int) -> PRContext:
    """Per-PR conversation context: issue comments + inline review comments."""
    issue_comments_raw = client.list_pull_issue_comments(owner, repo, number)
    review_comments_raw = client.list_pull_review_comments(owner, repo, number)

    def _clip(c: dict) -> str:
        body = (c.get("body") or "").strip()
        author = (c.get("user") or {}).get("login", "")
        if not body:
            return ""
        return f"{author}: {body[:400]}"

    issue_comments = [s for s in (_clip(c) for c in issue_comments_raw[:10]) if s]
    review_comments = [s for s in (_clip(c) for c in review_comments_raw[:10]) if s]

    has_changes_requested = any(
        "changes requested" in (c.get("body") or "").lower()
        for c in issue_comments_raw
    )

    return PRContext(
        issue_comments=issue_comments,
        review_comments=review_comments,
        has_changes_requested=has_changes_requested,
    )
