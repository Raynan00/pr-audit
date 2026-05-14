# pr-audit

AI-assisted PR triage for OSS maintainers. Point it at a public GitHub repo and
get back a ranked report of which PRs to merge first, which to close, and which
need a deeper look — plus a stack-aware merge plan for the top N.

Built because [airweave-ai/airweave](https://github.com/airweave-ai/airweave)
has 79 open PRs sitting in queue. Heuristic ranking + per-PR LLM review +
sequenced merge plan saves hours of review fatigue.

**Live demo:** [Audit of airweave-ai/airweave](https://raynan00.github.io/pr-audit/airweave-audit.html) — the actual output this tool produces.

## Quick start

```bash
pip install -e .
export GITHUB_TOKEN=ghp_xxxxxxxxxxxxxxxx
export ANTHROPIC_API_KEY=sk-ant-xxxxx

pr-audit airweave-ai/airweave --plan-merges 5
```

Default output dir is `./out/`:

| File | Purpose |
|---|---|
| `report.html` | Polished single-file HTML, dark/light, no CDN deps. Share this. |
| `report.md` | Markdown report for GitHub README rendering or terminal viewing. |
| `merge_plan.md` | Stack-aware merge order for the top N (when `--plan-merges N` is set). |
| `pr_data.json` | Full per-PR feature data for programmatic use. |
| `pr_data.csv` | Same data in spreadsheet form. |

## What it does

1. Fetches all open PRs via the GitHub API
2. Extracts per-PR features: author classification, diff size, test inclusion,
   CI status (check-runs aware), linked issues, competing PRs, mergeable state
3. Heuristic code smell scan on each diff (bare excepts, hardcoded secrets,
   debug prints, disabled tests, very long lines)
4. AI-assisted code review per PR via Claude Haiku 4.5 (~$0.50 for 79 PRs)
5. Ranks each PR into one of seven buckets (see below)
6. Renders Markdown + HTML + JSON + CSV
7. Optionally produces a stack-aware merge plan with file-overlap detection

## Buckets

| Bucket | What it means |
|---|---|
| `quick_wins` | Small + passing CI + clean + score ≥ 6 → batch-mergeable |
| `high_impact` | Closes a high-demand issue, passing CI, medium+ diff |
| `contested` | Multiple PRs targeting the same issue. Pick one, close others. |
| `ai_flagged` | LLM flagged a blocking concern (security, broken logic, etc.) |
| `stale` | Idle > 60 days, dirty merge state, or failing CI for weeks |
| `risky` | Large diff without tests or with failing CI. Needs review. |
| `everything_else` | Nothing notable. Lives in `pr_data.json`. |

Buckets are evaluated in order — a PR lands in the first matching bucket.
Quick wins are checked **before** ai_flagged so the LLM's reflex nits (no
tests, no linked issue) don't veto an otherwise-mergeable PR. The LLM only
overrides if it returns `close` or surfaces a concern that mentions a hard
failure mode ("critical", "security", "broken", "will fail", "race condition",
etc.).

## CLI options

```
pr-audit <owner/repo> [options]

  --token TOKEN              GitHub PAT (or GITHUB_TOKEN env)
  --anthropic-key KEY        Anthropic API key (or ANTHROPIC_API_KEY env)
  --skip-ai                  Skip LLM review (metadata-only, free)
  --max-prs N                Only audit the first N open PRs
  --output-dir DIR           Where to write outputs (default: ./out)
  --top-n N                  PRs per ranked section in the report (default: 5)
  --cache-dir DIR            Cache for fetched data (default: <output-dir>/.cache)
  --no-cache                 Disable cache, force fresh fetches
  --model NAME               Anthropic model (default: claude-haiku-4-5-20251001)
  --plan-merges N            After ranking, build a stack-aware merge plan
                             for the top N candidates and write merge_plan.md
  --min-merge-score N        Minimum AI score for inclusion in the merge plan
                             (default: 7)
  --airweave-key KEY         Airweave API key (or AIRWEAVE_API_KEY env).
                             Enables Airweave-backed context retrieval.
  --airweave-collection ID   Airweave collection readable_id
                             (or AIRWEAVE_COLLECTION env).
```

## The merge planner

```
pr-audit airweave-ai/airweave --plan-merges 5 --min-merge-score 7
```

For the top N eligible PRs (in `quick_wins` or `high_impact` with passing CI
and clean mergeable state and score ≥ threshold), the planner:

1. Fetches each PR's changed file list
2. Greedily groups PRs into rebase-independent batches (no file overlap
   within a batch)
3. Records which earlier PRs each later one will need rebase after
4. Skips PRs that fail the eligibility gates and lists the reason

Output is `merge_plan.md` in the output dir. It's a dry-run only — pr-audit
never merges anything on its own.

## Retrieval-augmented reviews via Airweave (optional)

By default, the AI reviewer gets a fixed slice of repo context (README,
CONTRIBUTING.md, recent merged PR titles, sample review comments) fetched
directly from the GitHub API.

If you sync your repo into an [Airweave](https://airweave.ai) collection,
`pr-audit` will swap the GitHub-API fetches for semantic search against that
collection. Per-PR queries are tuned to the PR's title, body, and changed
files, so the LLM gets retrieval-augmented context tuned to each review.

Setup:

```bash
pip install -e .[airweave]
export AIRWEAVE_API_KEY=sk-aw-...
export AIRWEAVE_COLLECTION=my-repo-collection
pr-audit airweave-ai/airweave --plan-merges 5
```

Or pass `--airweave-key` and `--airweave-collection` on the command line.

When the env vars are unset, the tool falls back to the direct GitHub-API
path automatically — so the optional backend is opt-in.

## As a Claude skill

Drop `skills/pr-audit/` into your Claude Code skills folder. Then ask Claude
things like:

- "Triage the open PRs in airweave-ai/airweave"
- "Build a merge plan for the top 5 quick wins"
- "Which of my open PRs compete with each other?"

The skill picks the right mode and shells out to the CLI. See
`skills/pr-audit/SKILL.md` for the full guidance Claude reads on trigger.

## Read-only by design

This tool only fetches public data via the GitHub API. It never comments on
PRs, posts reviews, or modifies any repo. The report is for the maintainer to
read; acting on it is their call.

## Cost

- GitHub API: free (`public_repo` read scope only)
- Anthropic Claude Haiku 4.5: ~$0.50 for a 79-PR audit
- Caching: GET requests are cached by URL key; AI reviews keyed by PR number.
  Re-runs are nearly free.

## Limitations

- LLM reviews are heuristic, not gospel. They can miss things or hallucinate
  concerns. The bucket logic accounts for reflex flags but maintainer judgment
  is still required.
- The tool doesn't run tests; it reads the repo's existing CI status.
- Diffs over 24K characters are truncated head + tail, and the review is
  flagged as `diff_truncated`.
- The legacy `/commits/{sha}/status` endpoint returns "pending" for many
  modern Actions-only repos. `_ci_status` prefers `/check-runs` when present.

## Repo layout

```
src/pr_audit/
  cli.py               # argparse entry point
  fetch.py             # GitHubClient: cached, rate-limit-aware
  features.py          # build_pr_record + feature extraction
  classify.py          # author classification, diff sizing, test detection
  linked.py            # parse closing keywords from PR body and branch name
  smells.py            # regex-based diff smell scanner
  review.py            # Claude Haiku per-PR review with structured JSON output
  buckets.py           # 7-bucket ranking
  planner.py           # stack-aware merge plan
  render.py            # Markdown + JSON + CSV writers
  render_html.py       # single-file HTML report
  airweave_backend.py  # optional retrieval backend (semantic search)
  models.py            # Pydantic types
skills/pr-audit/       # Claude skill wrapper
examples/              # sample audit output (Markdown + HTML)
docs/                  # GitHub Pages source for the live demo
tests/                 # pytest suite
```

## License

MIT.

## Author

[Raynan Wuyep](https://linkedin.com/in/raynan-wuyep).
