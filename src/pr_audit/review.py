"""LLM-powered PR code review using Anthropic Claude.

Falls back to a no-op review (with `error` set) if no API key is available.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

from .models import AIReview, IssueRef, PRContext, RepoContext

# Token budget for diff portion of prompt
MAX_DIFF_CHARS = 24_000  # ~6K tokens; well within Haiku context budget


def truncate_diff(diff: str, max_chars: int = MAX_DIFF_CHARS) -> tuple[str, bool]:
    """Truncate the diff to fit a budget; preserve start + end if cutting mid-stream."""
    if len(diff) <= max_chars:
        return diff, False
    half = max_chars // 2
    head = diff[:half]
    tail = diff[-half:]
    return head + "\n\n...[truncated]...\n\n" + tail, True


def _repo_context_block(rc: RepoContext | None) -> str:
    if not rc:
        return ""
    parts: list[str] = ["=== REPO CONTEXT ==="]
    if rc.name:
        parts.append(f"Repo: {rc.name}")
    if rc.description:
        parts.append(f"Description: {rc.description}")
    if rc.primary_language:
        parts.append(f"Primary language: {rc.primary_language}")
    if rc.readme_excerpt:
        parts.append(f"\nREADME excerpt:\n{rc.readme_excerpt[:1500]}")
    if rc.contributing_excerpt:
        parts.append(f"\nCONTRIBUTING.md excerpt:\n{rc.contributing_excerpt[:1500]}")
    if rc.recent_merged_titles:
        parts.append("\nRecently merged PR titles (signals what kind of changes ship here):")
        for t in rc.recent_merged_titles[:15]:
            parts.append(f"  - {t}")
    if rc.recent_review_excerpts:
        parts.append("\nExamples of past maintainer review comments (their voice and what they push back on):")
        for c in rc.recent_review_excerpts[:6]:
            parts.append(f"  - {c}")
    parts.append("=== END REPO CONTEXT ===\n")
    return "\n".join(parts) + "\n"


def _pr_context_block(pc: PRContext | None) -> str:
    if not pc or (not pc.issue_comments and not pc.review_comments):
        return ""
    parts: list[str] = ["=== PR DISCUSSION ==="]
    if pc.issue_comments:
        parts.append("Conversation comments:")
        for c in pc.issue_comments[:8]:
            parts.append(f"  - {c}")
    if pc.review_comments:
        parts.append("\nInline review comments on the diff:")
        for c in pc.review_comments[:8]:
            parts.append(f"  - {c}")
    if pc.has_changes_requested:
        parts.append("\nNOTE: a reviewer has requested changes on this PR.")
    parts.append("=== END PR DISCUSSION ===\n")
    return "\n".join(parts) + "\n"


def build_prompt(
    pr_title: str,
    pr_body: str,
    diff: str,
    linked_issue: IssueRef | None,
    repo_context: RepoContext | None = None,
    pr_context: PRContext | None = None,
) -> str:
    """Construct the LLM review prompt with repo and PR context.

    The repo block teaches the model the codebase's voice and conventions; the
    PR block surfaces the live conversation. Both are optional - the function
    still works diff-only if you don't pass them.
    """
    repo_block = _repo_context_block(repo_context)
    pr_disc_block = _pr_context_block(pr_context)

    issue_block = ""
    if linked_issue:
        issue_block = (
            "Linked issue:\n"
            f"  #{linked_issue.number} {linked_issue.title}\n"
            f"  Body: {linked_issue.body[:1500]}\n"
            f"  Reactions: {linked_issue.reactions}\n"
            f"  Labels: {', '.join(linked_issue.labels)}\n\n"
        )
    truncated_diff, was_truncated = truncate_diff(diff)
    truncation_note = "\n\n(NOTE: diff was truncated for length.)" if was_truncated else ""

    return f"""You're reviewing an open PR on a public OSS repo. The maintainer needs to decide whether to merge, request changes, discuss, or close.

Use the REPO CONTEXT and PR DISCUSSION blocks below to tune your review to THIS codebase's conventions and the live conversation. Don't flag generic concerns (like "no tests" or "no linked issue") if the repo's own patterns suggest they're not required for this kind of change.

{repo_block}{pr_disc_block}PR title: {pr_title}
PR description:
{(pr_body or "(empty)")[:2000]}

{issue_block}Diff:
{truncated_diff}{truncation_note}

Assess:
1. Does the PR appear to solve the linked issue? (yes / partial / no / unclear / no_linked_issue if none)
2. Are there obvious bugs, missing edge cases, or logic errors?
3. Does it follow the repo's conventions visible in the context blocks?
4. Are tests included where the repo's patterns would expect them?
5. Anti-patterns, security risks, code smells?
6. Does it conflict with feedback already in the PR discussion?

Output ONLY a JSON object with this exact schema (no markdown fences, no commentary):
{{
  "solves_issue": "yes" | "partial" | "no" | "unclear" | "no_linked_issue",
  "score": <integer 1-10>,
  "strengths": [<short bullet>, ...],
  "concerns": [<short bullet>, ...],
  "merge_recommendation": "merge" | "needs_changes" | "needs_discussion" | "close",
  "summary": "<one-sentence assessment for the maintainer>"
}}"""


def _parse_review_json(text: str) -> dict:
    """Be liberal in what we accept; the model sometimes wraps JSON in ``` blocks."""
    # Strip code fences if present
    text = text.strip()
    fence_match = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, re.DOTALL)
    if fence_match:
        text = fence_match.group(1)
    # Find first { ... last }
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end < 0:
        raise ValueError("No JSON object found in response")
    return json.loads(text[start : end + 1])


def review_pr_with_claude(
    pr_number: int,
    pr_title: str,
    pr_body: str,
    diff: str,
    linked_issue: IssueRef | None,
    repo_context: RepoContext | None = None,
    pr_context: PRContext | None = None,
    api_key: str | None = None,
    model: str = "claude-haiku-4-5-20251001",
    cache_dir: Path | None = None,
) -> AIReview:
    """Run an LLM review of a single PR. Caches by PR number.

    If `api_key` (or ANTHROPIC_API_KEY env) is missing, returns a no-op review
    with `error` populated so the caller can decide what to do.
    """
    # Cache check
    if cache_dir:
        cache_dir.mkdir(parents=True, exist_ok=True)
        cache_path = cache_dir / f"review_{pr_number}.json"
        if cache_path.exists():
            try:
                return AIReview(**json.loads(cache_path.read_text(encoding="utf-8")))
            except Exception:
                pass  # fall through to re-run

    key = api_key or os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        return AIReview(error="no_api_key", summary="LLM review skipped: ANTHROPIC_API_KEY not set.")

    try:
        from anthropic import Anthropic
    except ImportError:
        return AIReview(error="anthropic_not_installed", summary="anthropic Python package not installed.")

    client = Anthropic(api_key=key)
    prompt = build_prompt(pr_title, pr_body, diff, linked_issue, repo_context, pr_context)
    try:
        resp = client.messages.create(
            model=model,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        text = "".join(block.text for block in resp.content if hasattr(block, "text"))
        data = _parse_review_json(text)
        review = AIReview(
            solves_issue=data.get("solves_issue", "no_linked_issue"),
            score=int(data.get("score", 5)),
            strengths=list(data.get("strengths") or [])[:6],
            concerns=list(data.get("concerns") or [])[:6],
            merge_recommendation=data.get("merge_recommendation", "needs_discussion"),
            summary=data.get("summary", ""),
            diff_truncated=len(diff) > MAX_DIFF_CHARS,
        )
        if cache_dir:
            cache_path = cache_dir / f"review_{pr_number}.json"
            cache_path.write_text(review.model_dump_json(indent=2), encoding="utf-8")
        return review
    except Exception as e:
        return AIReview(error=f"{type(e).__name__}: {e}", summary="LLM review failed.")
