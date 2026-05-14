"""GitHub API client for pr-audit. Uses httpx; supports token auth and caching."""
from __future__ import annotations

import base64
import json
import os
import time
from pathlib import Path
from typing import Any

import httpx

_TRANSIENT_HTTPX_ERRORS = (httpx.ConnectError, httpx.ReadError, httpx.RemoteProtocolError)

GITHUB_API = "https://api.github.com"


class GitHubClient:
    """Minimal GitHub REST client with caching and rate-limit awareness."""

    def __init__(
        self,
        token: str | None = None,
        cache_dir: Path | None = None,
        use_cache: bool = True,
    ):
        self.token = token or os.environ.get("GITHUB_TOKEN")
        self.cache_dir = cache_dir
        self.use_cache = use_cache
        if cache_dir:
            cache_dir.mkdir(parents=True, exist_ok=True)

        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "pr-audit/0.1.0",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        self.client = httpx.Client(
            base_url=GITHUB_API,
            headers=headers,
            timeout=30.0,
            follow_redirects=True,
        )

    def close(self) -> None:
        self.client.close()

    def _cache_path(self, key: str) -> Path | None:
        if not self.cache_dir:
            return None
        safe_key = key.replace("/", "_").replace("?", "_").replace("&", "_")
        return self.cache_dir / f"{safe_key}.json"

    def _read_cache(self, key: str) -> Any | None:
        if not self.use_cache:
            return None
        path = self._cache_path(key)
        if path and path.exists():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                return None
        return None

    def _write_cache(self, key: str, data: Any) -> None:
        if not self.use_cache:
            return
        path = self._cache_path(key)
        if path:
            path.write_text(json.dumps(data, default=str), encoding="utf-8")

    def get(self, path: str, params: dict | None = None) -> Any:
        """GET a path with caching and rate-limit handling."""
        cache_key = path + ("?" + "&".join(f"{k}={v}" for k, v in (params or {}).items()) if params else "")
        cached = self._read_cache(cache_key)
        if cached is not None:
            return cached

        for attempt in range(5):
            try:
                resp = self.client.get(path, params=params)
            except _TRANSIENT_HTTPX_ERRORS:
                if attempt == 4:
                    raise
                time.sleep(2 ** attempt)
                continue
            if resp.status_code == 403 and "rate limit" in resp.text.lower():
                reset = int(resp.headers.get("X-RateLimit-Reset", "0"))
                wait_for = max(0, reset - int(time.time())) + 2
                if wait_for > 0 and wait_for < 120:
                    time.sleep(wait_for)
                    continue
                raise RuntimeError(f"GitHub rate-limited, reset in {wait_for}s. Provide GITHUB_TOKEN.")
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            data = resp.json()
            self._write_cache(cache_key, data)
            return data
        raise RuntimeError(f"Failed to fetch {path} after 5 attempts")

    def paginate(self, path: str, params: dict | None = None, per_page: int = 100, max_pages: int = 50) -> list[Any]:
        """Auto-paginate a list endpoint."""
        params = dict(params or {})
        params["per_page"] = per_page
        results: list[Any] = []
        for page in range(1, max_pages + 1):
            params["page"] = page
            batch = self.get(path, params=params)
            if not batch:
                break
            if isinstance(batch, dict):
                # Some endpoints return wrapped objects; assume not a list
                return results
            results.extend(batch)
            if len(batch) < per_page:
                break
        return results

    # High-level helpers

    def list_open_pulls(self, owner: str, repo: str) -> list[dict]:
        return self.paginate(f"/repos/{owner}/{repo}/pulls", params={"state": "open", "sort": "created", "direction": "desc"})

    def get_pull(self, owner: str, repo: str, number: int) -> dict | None:
        return self.get(f"/repos/{owner}/{repo}/pulls/{number}")

    def get_pull_files(self, owner: str, repo: str, number: int) -> list[dict]:
        return self.paginate(f"/repos/{owner}/{repo}/pulls/{number}/files", per_page=100, max_pages=5) or []

    def get_pull_diff(self, owner: str, repo: str, number: int) -> str:
        """Fetch the raw .diff payload (text). Bypasses the JSON cache machinery
        because diff responses aren't JSON, but uses the same transient-error
        retry policy as the JSON path."""
        cache_key = f"diff_{owner}_{repo}_{number}"
        cached = self._read_cache(cache_key)
        if cached is not None and isinstance(cached, dict) and "diff" in cached:
            return cached["diff"]
        for attempt in range(5):
            try:
                resp = self.client.get(
                    f"/repos/{owner}/{repo}/pulls/{number}",
                    headers={"Accept": "application/vnd.github.v3.diff"},
                )
                break
            except _TRANSIENT_HTTPX_ERRORS:
                if attempt == 4:
                    raise
                time.sleep(2 ** attempt)
        if resp.status_code != 200:
            return ""
        text = resp.text
        self._write_cache(cache_key, {"diff": text})
        return text

    def list_pull_reviews(self, owner: str, repo: str, number: int) -> list[dict]:
        return self.paginate(f"/repos/{owner}/{repo}/pulls/{number}/reviews", per_page=100, max_pages=3) or []

    def get_combined_status(self, owner: str, repo: str, sha: str) -> dict | None:
        return self.get(f"/repos/{owner}/{repo}/commits/{sha}/status")

    def get_check_runs(self, owner: str, repo: str, sha: str) -> dict | None:
        return self.get(f"/repos/{owner}/{repo}/commits/{sha}/check-runs")

    def list_collaborators(self, owner: str, repo: str) -> list[dict]:
        # public repos may not let you list collaborators without permission;
        # fall back to contributors if 403
        try:
            return self.paginate(f"/repos/{owner}/{repo}/collaborators", per_page=100, max_pages=2) or []
        except httpx.HTTPStatusError:
            return []

    def list_contributors(self, owner: str, repo: str) -> list[dict]:
        return self.paginate(f"/repos/{owner}/{repo}/contributors", per_page=100, max_pages=3) or []

    def get_repo(self, owner: str, repo: str) -> dict | None:
        return self.get(f"/repos/{owner}/{repo}")

    def list_open_issues(self, owner: str, repo: str) -> list[dict]:
        # GitHub's /issues endpoint returns both issues and PRs; filter PRs out by caller
        return self.paginate(
            f"/repos/{owner}/{repo}/issues",
            params={"state": "open", "sort": "created", "direction": "desc"},
        ) or []

    def get_file_contents(self, owner: str, repo: str, path: str) -> str | None:
        """Fetch a single file's raw contents from default branch. Returns None on 404."""
        try:
            data = self.get(f"/repos/{owner}/{repo}/contents/{path}")
        except Exception:
            return None
        if not data or not isinstance(data, dict):
            return None
        content = data.get("content")
        if not content:
            return None
        try:
            return base64.b64decode(content).decode("utf-8", errors="replace")
        except Exception:
            return None

    def list_pull_issue_comments(self, owner: str, repo: str, number: int) -> list[dict]:
        """PR conversation comments (not inline review comments)."""
        try:
            return self.paginate(f"/repos/{owner}/{repo}/issues/{number}/comments", per_page=30, max_pages=2) or []
        except Exception:
            return []

    def list_pull_review_comments(self, owner: str, repo: str, number: int) -> list[dict]:
        """Inline review comments on a PR's diff."""
        try:
            return self.paginate(f"/repos/{owner}/{repo}/pulls/{number}/comments", per_page=30, max_pages=2) or []
        except Exception:
            return []

    def list_recent_merged_pulls(self, owner: str, repo: str, limit: int = 30) -> list[dict]:
        """Recently-merged PRs (used to detect maintainer review patterns)."""
        try:
            results = self.paginate(
                f"/repos/{owner}/{repo}/pulls",
                params={"state": "closed", "sort": "updated", "direction": "desc"},
                per_page=50,
                max_pages=1,
            ) or []
        except Exception:
            return []
        merged = [p for p in results if p.get("merged_at")]
        return merged[:limit]
