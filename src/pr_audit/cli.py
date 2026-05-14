"""CLI entry point for pr-audit."""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from .airweave_backend import (
    fetch_pr_context_via_airweave,
    fetch_repo_context_via_airweave,
    get_airweave_config,
)
from .buckets import assign_buckets
from .features import (
    attach_issue_demand,
    build_issue_ref,
    build_pr_record,
    detect_competing,
    fetch_pr_context,
    fetch_repo_context,
    issues_to_map,
)
from .fetch import GitHubClient
from .models import PRRecord
from .planner import plan_merges
from .render import write_outputs
from .review import review_pr_with_claude
from .smells import scan_diff_for_smells


def main(argv: list[str] | None = None) -> int:
    load_dotenv()

    parser = argparse.ArgumentParser(
        prog="pr-audit",
        description="AI-assisted PR triage for OSS maintainers.",
    )
    parser.add_argument("repo", help="GitHub repository in owner/repo form")
    parser.add_argument("--token", default=None, help="GitHub PAT (or GITHUB_TOKEN env)")
    parser.add_argument("--anthropic-key", default=None, help="Anthropic API key (or ANTHROPIC_API_KEY env)")
    parser.add_argument("--skip-ai", action="store_true", help="Skip LLM review (metadata-only mode)")
    parser.add_argument("--max-prs", type=int, default=0, help="Cap to first N open PRs (0 = all)")
    parser.add_argument("--output-dir", default="./out", help="Where to write outputs")
    parser.add_argument("--top-n", type=int, default=5, help="How many PRs per ranked section")
    parser.add_argument("--cache-dir", default=None, help="Cache directory (default: output_dir/.cache)")
    parser.add_argument("--no-cache", action="store_true", help="Disable cache")
    parser.add_argument(
        "--model",
        default="claude-haiku-4-5-20251001",
        help="Anthropic model name for LLM review",
    )
    parser.add_argument(
        "--plan-merges",
        type=int,
        default=0,
        metavar="N",
        help="After ranking, build a stack-aware merge plan for top N candidates and write to merge_plan.md",
    )
    parser.add_argument(
        "--min-merge-score",
        type=int,
        default=7,
        help="Minimum AI score for a PR to be included in the merge plan (default 7)",
    )
    parser.add_argument(
        "--airweave-key",
        default=None,
        help="Airweave API key (or AIRWEAVE_API_KEY env). Enables Airweave-backed retrieval for the LLM reviewer.",
    )
    parser.add_argument(
        "--airweave-collection",
        default=None,
        help="Airweave collection readable_id (or AIRWEAVE_COLLECTION env). Required to enable the Airweave backend.",
    )
    args = parser.parse_args(argv)

    if "/" not in args.repo:
        print(f"error: repo must be in owner/repo form, got {args.repo!r}", file=sys.stderr)
        return 2
    owner, repo = args.repo.split("/", 1)

    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    cache_dir = Path(args.cache_dir).resolve() if args.cache_dir else (output_dir / ".cache")

    token = args.token or os.environ.get("GITHUB_TOKEN")
    if not token:
        print("warning: no GITHUB_TOKEN set; rate-limited to 60 req/hour", file=sys.stderr)

    client = GitHubClient(token=token, cache_dir=cache_dir, use_cache=not args.no_cache)

    print(f"Fetching open PRs for {owner}/{repo}…")
    pr_summaries = client.list_open_pulls(owner, repo)
    if args.max_prs > 0:
        pr_summaries = pr_summaries[: args.max_prs]
    print(f"  found {len(pr_summaries)} open PRs")

    print("Fetching open issues (for high-demand detection)…")
    all_issues = client.list_open_issues(owner, repo)
    issues_by_number = issues_to_map(all_issues)
    print(f"  found {len(issues_by_number)} open issues (PRs filtered out)")

    print("Classifying contributors…")
    contributors_data = client.list_contributors(owner, repo)
    contributor_set = {c.get("login", "") for c in contributors_data}
    collaborators = client.list_collaborators(owner, repo)
    core_team = {c.get("login", "") for c in collaborators}
    if not core_team:
        # Fall back: top 5 contributors by commits are very likely core team
        core_team = {c.get("login", "") for c in contributors_data[:5]}

    print("Building per-PR records…")
    records: list[PRRecord] = []
    for i, summary in enumerate(pr_summaries, start=1):
        try:
            rec = build_pr_record(client, owner, repo, summary, core_team, contributor_set)
            records.append(rec)
            print(f"  {i}/{len(pr_summaries)} #{rec.number} {rec.title[:60]}")
        except Exception as e:
            print(f"  warning: failed to build record for PR #{summary.get('number')}: {e}", file=sys.stderr)

    attach_issue_demand(records, issues_by_number)
    detect_competing(records)

    print("Scanning diffs for smells…")
    diffs: dict[int, str] = {}
    for rec in records:
        try:
            diff = client.get_pull_diff(owner, repo, rec.number)
            diffs[rec.number] = diff
            rec.smell_flags = scan_diff_for_smells(diff)
        except Exception as e:
            print(f"  warning: diff fetch failed for #{rec.number}: {e}", file=sys.stderr)

    if not args.skip_ai:
        airweave_cfg = get_airweave_config(args.airweave_key, args.airweave_collection)
        if airweave_cfg:
            aw_key, aw_collection = airweave_cfg
            print(f"Fetching repo context via Airweave (collection={aw_collection})…")
            repo_context = fetch_repo_context_via_airweave(aw_key, aw_collection, owner, repo)
        else:
            print("Fetching repo context via GitHub API (set AIRWEAVE_API_KEY + AIRWEAVE_COLLECTION for semantic retrieval)…")
            repo_context = fetch_repo_context(client, owner, repo)
        print(
            f"  README: {len(repo_context.readme_excerpt)} chars, "
            f"CONTRIBUTING: {len(repo_context.contributing_excerpt)} chars, "
            f"{len(repo_context.recent_merged_titles)} recent merged titles, "
            f"{len(repo_context.recent_review_excerpts)} review excerpts"
        )

        print("Running AI review per PR (with repo + PR context)…")
        review_cache = cache_dir / "reviews"
        for i, rec in enumerate(records, start=1):
            linked = None
            for n in rec.linked_issues:
                issue = issues_by_number.get(n)
                if issue:
                    linked = build_issue_ref(issue)
                    break
            if airweave_cfg:
                pr_ctx = fetch_pr_context_via_airweave(
                    aw_key, aw_collection, rec.title, rec.body, rec.changed_files,
                )
            else:
                pr_ctx = fetch_pr_context(client, owner, repo, rec.number)
            rec.ai_review = review_pr_with_claude(
                pr_number=rec.number,
                pr_title=rec.title,
                pr_body=rec.body,
                diff=diffs.get(rec.number, ""),
                linked_issue=linked,
                repo_context=repo_context,
                pr_context=pr_ctx,
                api_key=args.anthropic_key,
                model=args.model,
                cache_dir=review_cache,
            )
            score = rec.ai_review.score if rec.ai_review and not rec.ai_review.error else "—"
            print(f"  {i}/{len(records)} #{rec.number} score={score}")
    else:
        print("Skipping AI review (--skip-ai)")

    print("Assigning buckets and writing outputs…")
    assign_buckets(records)
    paths = write_outputs(
        records,
        output_dir=output_dir,
        owner=owner,
        repo=repo,
        open_issue_count=len(issues_by_number),
        top_n=args.top_n,
    )

    if args.plan_merges > 0:
        print(f"Building merge plan for top {args.plan_merges}…")
        plan = plan_merges(
            records, client, owner, repo,
            top_n=args.plan_merges,
            min_score=args.min_merge_score,
        )
        plan_path = output_dir / "merge_plan.md"
        plan_path.write_text(
            f"# Merge plan for {owner}/{repo}\n\n"
            f"Top {args.plan_merges} merge candidates, grouped into rebase-independent batches.\n\n"
            + plan.to_markdown(),
            encoding="utf-8",
        )
        paths["merge_plan"] = plan_path
        print(f"  wrote {plan_path}")

    print()
    print("Done. Outputs:")
    for k, p in paths.items():
        print(f"  {k}: {p}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
