# pr-audit skill

Drop this folder into your Claude Code skills directory and Claude will use it
when you ask about triaging PRs, planning merges, or investigating a specific
PR in a public GitHub repository.

## Install

```bash
# Clone the repo (or copy the skills/ folder into your skills directory)
git clone https://github.com/Raynan00/pr-audit.git
cd pr-audit
pip install -e .

# Then copy the skill into your Claude Code skills folder, e.g.
cp -r skills/pr-audit ~/.claude/skills/
```

## Use

In Claude Code, ask anything like:

- "Triage the open PRs in airweave-ai/airweave"
- "Build a merge plan for the top 5 quick wins in my repo"
- "Which of my open PRs compete with each other?"

The skill picks the right mode (triage / plan / investigate) and shells out
to the `pr-audit` CLI underneath. For deep-investigate questions on a single
PR, Claude reasons directly using the GitHub MCP tools.

## Requirements

- Python 3.10+
- `pip install pr-audit`
- `GITHUB_TOKEN` env var (PAT with public-repo read access)
- `ANTHROPIC_API_KEY` env var (only for the LLM review step; can skip with `--skip-ai`)
