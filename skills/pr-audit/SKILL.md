---
name: pr-audit
description: |
  Use this skill when the user wants to triage open pull requests, plan
  merges, or investigate a specific PR in a public GitHub repository.
  Triggers: "triage my PRs", "audit the backlog", "what should I merge",
  "merge plan for top 5", "review PR #123 deeply", or any mention of a
  GitHub repo's open PR list.
---

# pr-audit skill

This skill wraps the `pr-audit` Python package, which ranks open PRs into
seven buckets (quick wins, high impact, contested, AI flagged, stale,
risky, everything else), produces stack-aware merge plans, and runs
LLM-assisted code review on each PR.

## When to use

- The user mentions a GitHub repo and asks what to merge, close, or review
- The user references "my PR backlog" or "open PRs piling up"
- The user wants to know which PRs compete with each other
- The user wants a sequenced merge order for the top N PRs

## How to use

This skill has three modes. Pick the one that matches the user's intent.

### Mode 1: Triage (full audit)

Use when the user wants the full report on the whole backlog.

```bash
pr-audit OWNER/REPO --output-dir out/
```

Required env: `GITHUB_TOKEN` (PAT with public-repo read), `ANTHROPIC_API_KEY`.

Optional: `AIRWEAVE_API_KEY` + `AIRWEAVE_COLLECTION`. When set, pr-audit
replaces the direct GitHub context fetches with semantic search against the
Airweave collection — per-PR retrieval tuned to title, body, and changed files.
Falls back to GitHub API automatically when not configured.

Pass `--skip-ai` to skip the LLM review step for a faster, cheaper metadata-only
audit. Pass `--max-prs N` to cap to the first N PRs (useful for first runs).

The CLI writes four files to `out/`: `report.md`, `report.html`, `pr_data.json`,
`pr_data.csv`. Hand the report path back to the user and summarize the bucket
counts.

### Mode 2: Merge plan

Use when the user wants a stack-aware order for merging the top N quick wins.

```bash
pr-audit OWNER/REPO --output-dir out/ --plan-merges 5 --min-merge-score 7
```

This adds `merge_plan.md` to the output directory. The plan groups PRs into
rebase-independent batches (no file overlap inside a batch) and tracks which
PRs will need rebase if their dependencies merge first.

After running, summarize the batches in chat and ask whether the user wants
to proceed to actual merging (Mode 3, opt-in only).

### Mode 3: Deep investigate (interactive)

Use when the user asks about a specific PR's competing PRs, author history,
or wants you to reason about whether to merge a contested one.

For this mode you should NOT shell out. Instead, use the GitHub MCP tools
directly to:

1. Fetch the PR (`gh_get_pull` or equivalent)
2. Fetch any linked issues
3. Fetch the diff and any competing PRs touching the same files
4. Compare authors' track records via their other PRs in the same repo
5. Reason through it and present a recommendation

The goal is the same kind of judgment a senior maintainer would apply, with
the retrieved context laid out so the user can verify your reasoning.

## Important defaults

- Always operate read-only unless the user explicitly opts into merging.
- Never merge a PR with score below 7 or `mergeable_state != clean`.
- For first-time contributors, suggest a friendly comment template if you
  recommend changes.
- If the AI review flags a PR as "close", restate the duplicate or quality
  reason in plain language and ask the user to confirm before posting.

## Output formatting

When summarizing a report in chat:

- Lead with the bucket counts (quick wins, contested, ai_flagged, stale, risky)
- Show top 3 quick wins by PR number, author, and one-line AI summary
- Mention the merge plan only if `--plan-merges` was used
- Always link back to the full `report.md` so the user can drill in

## Cost notes

- Metadata-only audit: free (just GitHub API calls)
- Full audit with AI review on Airweave-sized backlog (79 PRs):
  ~$0.50 using claude-haiku-4-5
- Merge plan: free (just one extra API call per PR to fetch file list)
