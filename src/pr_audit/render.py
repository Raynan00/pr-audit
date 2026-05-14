"""Render the audit results to Markdown, JSON, and CSV."""
from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path

from .models import PRRecord
from .render_html import render_html


def write_outputs(
    records: list[PRRecord],
    output_dir: Path,
    owner: str,
    repo: str,
    open_issue_count: int,
    top_n: int = 5,
) -> dict[str, Path]:
    """Write report.md, report.html, pr_data.json, and pr_data.csv. Returns the paths."""
    output_dir.mkdir(parents=True, exist_ok=True)

    json_path = output_dir / "pr_data.json"
    csv_path = output_dir / "pr_data.csv"
    report_path = output_dir / "report.md"

    # JSON
    payload = {
        "generated_at": datetime.now(tz=timezone.utc).isoformat(),
        "owner": owner,
        "repo": repo,
        "open_pr_count": len(records),
        "open_issue_count": open_issue_count,
        "records": [json.loads(r.model_dump_json()) for r in records],
    }
    json_path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")

    # CSV
    fieldnames = [
        "number", "title", "url", "author", "author_type", "bucket", "bucket_rank",
        "age_days", "stale_days", "is_draft", "is_dependabot",
        "additions", "deletions", "files_changed", "diff_size_bucket", "has_tests",
        "ci_status", "mergeable", "mergeable_state", "review_state", "comments_count",
        "linked_issues", "closes_high_demand", "competing_prs", "labels",
        "smell_flags", "ai_score", "ai_recommendation", "ai_summary", "ai_concerns_count",
    ]
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in records:
            ai = r.ai_review
            writer.writerow({
                "number": r.number,
                "title": r.title,
                "url": r.url,
                "author": r.author,
                "author_type": r.author_type,
                "bucket": r.bucket,
                "bucket_rank": r.bucket_rank,
                "age_days": r.age_days,
                "stale_days": r.stale_days,
                "is_draft": r.is_draft,
                "is_dependabot": r.is_dependabot,
                "additions": r.additions,
                "deletions": r.deletions,
                "files_changed": r.files_changed,
                "diff_size_bucket": r.diff_size_bucket,
                "has_tests": r.has_tests,
                "ci_status": r.ci_status,
                "mergeable": r.mergeable,
                "mergeable_state": r.mergeable_state,
                "review_state": r.review_state,
                "comments_count": r.comments_count,
                "linked_issues": ",".join(str(x) for x in r.linked_issues),
                "closes_high_demand": r.closes_high_demand,
                "competing_prs": ",".join(str(x) for x in r.competing_prs),
                "labels": ",".join(r.labels),
                "smell_flags": ",".join(r.smell_flags),
                "ai_score": ai.score if ai and not ai.error else "",
                "ai_recommendation": ai.merge_recommendation if ai and not ai.error else "",
                "ai_summary": (ai.summary if ai and not ai.error else "")[:200],
                "ai_concerns_count": len(ai.concerns) if ai and not ai.error else "",
            })

    # Markdown
    report_path.write_text(_render_markdown(records, owner, repo, open_issue_count, top_n), encoding="utf-8")

    # HTML — shareable, single file, no CDN deps, dark/light mode aware
    html_path = output_dir / "report.html"
    html_path.write_text(
        render_html(records, owner, repo, open_issue_count, top_n=top_n),
        encoding="utf-8",
    )

    return {"report": report_path, "report_html": html_path, "json": json_path, "csv": csv_path}


def _render_markdown(records: list[PRRecord], owner: str, repo: str, open_issue_count: int, top_n: int) -> str:
    by_bucket: dict[str, list[PRRecord]] = {}
    for r in records:
        by_bucket.setdefault(r.bucket, []).append(r)
    for items in by_bucket.values():
        items.sort(key=lambda x: x.bucket_rank)

    lines: list[str] = []
    lines.append(f"# PR Backlog Audit — {owner}/{repo}")
    lines.append("")
    lines.append(f"**Generated:** {datetime.now(tz=timezone.utc).date().isoformat()}")
    lines.append(f"**Open PRs audited:** {len(records)}")
    lines.append(f"**Open issues:** {open_issue_count}")
    lines.append("")

    # TL;DR
    lines.append("## TL;DR")
    lines.append("")
    for bucket, label in [
        ("quick_wins", "quick wins (batch-mergeable)"),
        ("high_impact", "high-impact PRs that close in-demand issues"),
        ("contested", "contested issues (multiple PRs solving the same thing)"),
        ("ai_flagged", "AI-flagged concerns"),
        ("stale", "stale PRs to close or revive"),
        ("risky", "risky PRs needing deeper review"),
    ]:
        n = len(by_bucket.get(bucket, []))
        if n:
            lines.append(f"- **{n}** {label}")
    lines.append("")

    # Sections
    _section_table(lines, "1. Quick wins — merge in batch this week", by_bucket.get("quick_wins", []), top_n)
    _section_table(lines, "2. High-impact — review and merge this week", by_bucket.get("high_impact", []), top_n)
    _section_contested(lines, "3. Contested — pick one, close the others", by_bucket.get("contested", []))
    _section_ai_flagged(lines, "4. AI-flagged — review concerns before merging", by_bucket.get("ai_flagged", []), top_n)
    _section_table(lines, "5. Stale — close or revive", by_bucket.get("stale", []), top_n)
    _section_table(lines, "6. Risky — large diffs, missing tests, or failing CI", by_bucket.get("risky", []), top_n)

    # Patterns
    lines.append("## Patterns observed")
    lines.append("")
    lines.extend(_observed_patterns(records))
    lines.append("")

    # Methodology
    lines.append("---")
    lines.append("")
    lines.append("## Methodology")
    lines.append("")
    lines.append("This audit was generated by `pr-audit`, an open-source tool that ranks open PRs ")
    lines.append("via heuristics (CI status, diff size, test inclusion, linked issues, competing PRs, ")
    lines.append("staleness) and LLM-assisted code review.")
    lines.append("")
    lines.append("- Read-only: only fetches public data via the GitHub API.")
    lines.append("- Does not run tests; reads the maintainer's own CI status.")
    lines.append("- LLM reviews are heuristic. Maintainer judgment is the final word.")
    lines.append("")

    return "\n".join(lines) + "\n"


def _section_table(lines: list[str], heading: str, items: list[PRRecord], top_n: int) -> None:
    lines.append(f"## {heading} ({len(items)})")
    lines.append("")
    if not items:
        lines.append("_None._")
        lines.append("")
        return
    lines.append("| # | Title | Author | Size | CI | Tests | Age | AI score | Notes |")
    lines.append("|---|---|---|---|---|---|---|---|---|")
    for r in items[:top_n]:
        ai = r.ai_review
        ai_score = str(ai.score) if ai and not ai.error else "—"
        notes_parts: list[str] = []
        if ai and not ai.error and ai.summary:
            notes_parts.append(ai.summary)
        elif r.smell_flags:
            notes_parts.append("smells: " + ", ".join(r.smell_flags))
        notes = (notes_parts[0] if notes_parts else "")[:140]
        lines.append(
            f"| [#{r.number}]({r.url}) | {_truncate(r.title, 70)} | {r.author} | "
            f"{r.diff_size_bucket} | {r.ci_status} | {'✓' if r.has_tests else '—'} | {r.age_days}d | "
            f"{ai_score} | {notes} |"
        )
    if len(items) > top_n:
        lines.append("")
        lines.append(f"_…and {len(items) - top_n} more in `pr_data.json`._")
    lines.append("")


def _section_contested(lines: list[str], heading: str, items: list[PRRecord]) -> None:
    lines.append(f"## {heading} ({len(items)})")
    lines.append("")
    if not items:
        lines.append("_None._")
        lines.append("")
        return
    # Group by linked issue
    by_issue: dict[int, list[PRRecord]] = {}
    for r in items:
        for n in r.linked_issues:
            by_issue.setdefault(n, []).append(r)
    for issue_num, prs in sorted(by_issue.items()):
        unique = {p.number: p for p in prs}
        if len(unique) < 2:
            continue
        lines.append(f"### Issue #{issue_num}")
        lines.append("")
        for r in sorted(unique.values(), key=lambda x: x.created_at):
            ai = r.ai_review
            ai_bit = ""
            if ai and not ai.error:
                ai_bit = f" — AI: {ai.merge_recommendation} ({ai.score}/10)"
            lines.append(
                f"- **[#{r.number}]({r.url})** by {r.author} ({r.created_at.date()}), "
                f"CI {r.ci_status}, {'has tests' if r.has_tests else 'no tests'}, "
                f"{r.diff_size_bucket} diff{ai_bit}"
            )
        lines.append("")


def _section_ai_flagged(lines: list[str], heading: str, items: list[PRRecord], top_n: int) -> None:
    lines.append(f"## {heading} ({len(items)})")
    lines.append("")
    if not items:
        lines.append("_None._")
        lines.append("")
        return
    for r in items[:top_n]:
        ai = r.ai_review
        if not ai or ai.error:
            continue
        lines.append(f"### [#{r.number}]({r.url}) — {_truncate(r.title, 80)}")
        lines.append("")
        lines.append(f"**AI summary:** {ai.summary}")
        lines.append("")
        if ai.concerns:
            lines.append("**Concerns:**")
            for c in ai.concerns:
                lines.append(f"- {c}")
            lines.append("")
        if r.smell_flags:
            lines.append(f"**Smell flags:** `{', '.join(r.smell_flags)}`")
            lines.append("")
        lines.append(f"**Recommendation:** {ai.merge_recommendation}")
        lines.append("")


def _observed_patterns(records: list[PRRecord]) -> list[str]:
    lines: list[str] = []
    dependabot_count = sum(1 for r in records if r.is_dependabot)
    if dependabot_count >= 5:
        lines.append(f"- {dependabot_count} dependabot PRs in queue. Consider enabling auto-merge for dependency groups.")
    first_time = sum(1 for r in records if r.author_type == "first_time")
    if first_time >= 3:
        lines.append(f"- {first_time} PRs from first-time contributors. Worth a fast first-touch reply to keep them engaged.")
    no_tests = sum(1 for r in records if not r.has_tests and r.diff_size_bucket in {"medium", "large", "xlarge"})
    if no_tests >= 3:
        lines.append(f"- {no_tests} mid/large PRs land without tests. Worth flagging in CONTRIBUTING.md.")
    failing = sum(1 for r in records if r.ci_status == "failing")
    if failing:
        lines.append(f"- {failing} PRs have failing CI. These won't merge until fixed.")
    if not lines:
        lines.append("- No significant patterns surfaced beyond the per-bucket details above.")
    return lines


def _truncate(s: str, n: int) -> str:
    if len(s) <= n:
        return s
    return s[: n - 1] + "…"
