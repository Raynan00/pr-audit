"""Airweave-backed retrieval. Optional: only used when AIRWEAVE_API_KEY +
AIRWEAVE_COLLECTION are set (or the corresponding CLI flags are passed).

When configured, replaces the direct GitHub API fetches in `features.py`
(`fetch_repo_context`, `fetch_pr_context`) with semantic queries against an
Airweave collection synced from the target repo's data sources. The LLM
reviewer then sees retrieval-augmented context tuned to each PR.

Falls back to the direct-GitHub-API path automatically when not configured,
so `pr-audit` still works for users who haven't set up an Airweave instance.
"""
from __future__ import annotations

import os
import sys
import time
from typing import Any

from .models import PRContext, RepoContext

# Airweave's hosted API enforces a per-organization rate limit (sliding-window,
# per minute). Default plan caps:
#   Developer  10 rpm   Pro 100 rpm   Team 250 rpm   Enterprise unlimited
# We default to Developer-safe pacing. Higher-plan users can bump it via the
# AIRWEAVE_RPM env var.
_DEFAULT_RPM = 10


def _min_interval_seconds() -> float:
    try:
        rpm = int(os.environ.get("AIRWEAVE_RPM", _DEFAULT_RPM))
    except ValueError:
        rpm = _DEFAULT_RPM
    rpm = max(1, rpm)
    # Stay ~15% below the documented limit to absorb sliding-window jitter.
    return 60.0 / rpm * 1.15


_last_call_ts: float = 0.0
# Circuit-breaker: once we see a hard quota-exhausted error, every subsequent
# query will also fail, so we stop throttling and just return empty fast.
_quota_exhausted: bool = False


def _throttle() -> None:
    """Sleep enough to keep us under the Airweave rate limit. Single-threaded."""
    if _quota_exhausted:
        return
    global _last_call_ts
    now = time.monotonic()
    delta = now - _last_call_ts
    interval = _min_interval_seconds()
    if delta < interval:
        time.sleep(interval - delta)
    _last_call_ts = time.monotonic()


def _trip_quota_breaker(body: Any) -> bool:
    """Detect Airweave's hard usage-quota error so we can stop hammering."""
    text = str(body or "").lower()
    return "usage limit" in text or "quota" in text


def _is_configured(api_key: str | None, collection: str | None) -> bool:
    return bool(api_key) and bool(collection)


def _new_client(api_key: str):
    """Lazy-import the SDK so users without it can still install pr-audit."""
    try:
        from airweave import AirweaveSDK
    except ImportError as exc:
        raise RuntimeError(
            "airweave-sdk is not installed. Run `pip install airweave-sdk` to use the Airweave backend."
        ) from exc
    return AirweaveSDK(api_key=api_key)


def _search(client: Any, collection: str, query: str, limit: int = 6) -> list[str]:
    """Run a search and flatten the results into short text chunks.

    The SDK's SearchV2Response carries chunk content in `textual_representation`.
    On any failure we log to stderr and return []; we never inject error text
    into the chunk stream (it would surface as a fake "concern" in LLM review).
    Once a hard usage-quota error trips the circuit-breaker, subsequent calls
    short-circuit to empty without sleeping the throttle.
    """
    global _quota_exhausted
    if _quota_exhausted:
        return []

    # Retry policy:
    #   - Network flaps (ConnectError etc.): retry up to 3 times with exp backoff.
    #   - 429: honor Retry-After, retry once. The per-call throttle should
    #     prevent this; the retry is a safety net for sliding-window jitter.
    #   - Quota-exhausted ApiError: trip the breaker and short-circuit all
    #     subsequent calls in this process.
    #   - Anything else: fail fast and return []. Never inject error text into
    #     the chunk stream — it would surface as a fake "concern" in LLM review.
    _NETWORK_TRANSIENT = {"ConnectError", "ReadError", "RemoteProtocolError", "TimeoutException"}
    rate_limit_retried = False
    resp = None
    for attempt in range(3):
        _throttle()
        try:
            resp = client.collections.search.instant(readable_id=collection, query=query)
            break
        except Exception as e:
            name = type(e).__name__
            if name in _NETWORK_TRANSIENT:
                if attempt < 2:
                    time.sleep(2 ** attempt)
                    continue
                print(f"  airweave search failed after retries ({name}) — query={query[:60]!r}", file=sys.stderr)
                return []
            status_code = getattr(e, "status_code", None)
            body = getattr(e, "body", None)
            if name == "ApiError" and status_code == 429 and not rate_limit_retried:
                headers = getattr(e, "headers", None) or {}
                try:
                    retry_after = int(headers.get("Retry-After") or headers.get("retry-after") or 30)
                except (TypeError, ValueError):
                    retry_after = 30
                retry_after = min(retry_after, 90)  # cap to avoid runaway waits
                print(f"  airweave 429, sleeping {retry_after}s — query={query[:60]!r}", file=sys.stderr)
                time.sleep(retry_after)
                rate_limit_retried = True
                continue
            if name == "ApiError" and _trip_quota_breaker(body):
                _quota_exhausted = True
                print(
                    f"  airweave usage quota exhausted (status={status_code}): {body!r} "
                    f"— remaining queries will short-circuit to empty",
                    file=sys.stderr,
                )
                return []
            print(
                f"  airweave search failed ({name} status={status_code}): "
                f"{str(body)[:140]} — query={query[:60]!r}",
                file=sys.stderr,
            )
            return []

    # SearchV2Response.results: list of items; chunk content in `textual_representation`.
    results = getattr(resp, "results", None) or []
    chunks: list[str] = []
    for item in results[:limit]:
        text = getattr(item, "textual_representation", "") or ""
        if text:
            chunks.append(str(text)[:600].strip())
    return chunks


def fetch_repo_context_via_airweave(
    api_key: str,
    collection: str,
    owner: str,
    repo: str,
) -> RepoContext:
    """Build a RepoContext using semantic search instead of direct file fetches.

    Each section of the RepoContext maps to a targeted query. The model ends up
    with context that's both broader (cross-source) and more specific (matched
    semantically to what would help reviewing PRs in this repo).
    """
    client = _new_client(api_key)

    readme_chunks = _search(client, collection, "what this project does, architecture overview, primary modules", limit=4)
    contributing_chunks = _search(
        client, collection,
        "contributing guide, coding conventions, testing requirements, style rules",
        limit=4,
    )
    review_patterns = _search(
        client, collection,
        "code review feedback, common requested changes, maintainer review comments",
        limit=8,
    )
    recent_changes = _search(
        client, collection,
        "recent feature work, recent bug fixes, areas of active development",
        limit=10,
    )

    return RepoContext(
        name=f"{owner}/{repo}",
        readme_excerpt="\n\n".join(readme_chunks)[:3000],
        contributing_excerpt="\n\n".join(contributing_chunks)[:3000],
        recent_merged_titles=[c[:120] for c in recent_changes[:15]],
        recent_review_excerpts=[c[:280] for c in review_patterns[:8]],
    )


def fetch_pr_context_via_airweave(
    api_key: str,
    collection: str,
    pr_title: str,
    pr_body: str,
    changed_files: list[str] | None = None,
) -> PRContext:
    """Build a PRContext by semantic searching for prior discussions related to
    THIS PR's content.

    Surfaces past comments, issues, or docs that mention the same modules /
    concepts the PR touches — not just the PR's own conversation thread.
    """
    client = _new_client(api_key)

    # Build a focused query from the PR title + first 200 chars of body + top changed files
    file_hint = ", ".join((changed_files or [])[:5])
    pr_query = f"{pr_title}\n{(pr_body or '')[:200]}\nfiles: {file_hint}".strip()

    related_chunks = _search(client, collection, pr_query, limit=8)
    similar_issues = _search(
        client, collection,
        f"open issues or past PRs related to: {pr_title}",
        limit=5,
    )

    return PRContext(
        issue_comments=[c for c in related_chunks if c][:6],
        review_comments=[c for c in similar_issues if c][:6],
        has_changes_requested=False,  # the GitHub-API path detects this; Airweave one doesn't yet
    )


def get_airweave_config(
    cli_key: str | None = None,
    cli_collection: str | None = None,
) -> tuple[str, str] | None:
    """Resolve API key + collection from CLI flags or env vars.

    Accepts a few common variable names so users don't have to remember the
    exact one. Preferred: AIRWEAVE_API_KEY and AIRWEAVE_COLLECTION.

    Returns (key, collection) if both are configured, None otherwise.
    """
    api_key = (
        cli_key
        or os.environ.get("AIRWEAVE_API_KEY")
        or os.environ.get("AIRWEAVE_KEY")
    )
    collection = (
        cli_collection
        or os.environ.get("AIRWEAVE_COLLECTION")
        or os.environ.get("AIRWEAVE_COLLECTION_ID")
        or os.environ.get("COLLECTION_ID")
    )
    if _is_configured(api_key, collection):
        return api_key, collection  # type: ignore[return-value]
    return None
