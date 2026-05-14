"""Single-file HTML report.

No CDN dependencies. All CSS inlined. Dark theme by default, light fallback
via prefers-color-scheme. Designed to be sent to maintainers and read once.
"""
from __future__ import annotations

from datetime import datetime, timezone
from html import escape

from .models import PRRecord

_CSS = """
:root {
  --bg: #0a0a0b;
  --bg-elev: #131316;
  --bg-elev-2: #1a1a1f;
  --border: #26262c;
  --border-strong: #34343c;
  --text: #ededee;
  --text-dim: #a1a1a8;
  --text-mute: #6b6b75;
  --accent: #a78bfa;
  --accent-dim: #6d28d9;
  --green: #34d399;
  --green-bg: rgba(52, 211, 153, 0.08);
  --green-border: rgba(52, 211, 153, 0.25);
  --blue: #60a5fa;
  --blue-bg: rgba(96, 165, 250, 0.08);
  --blue-border: rgba(96, 165, 250, 0.25);
  --yellow: #fbbf24;
  --yellow-bg: rgba(251, 191, 36, 0.08);
  --yellow-border: rgba(251, 191, 36, 0.25);
  --orange: #fb923c;
  --orange-bg: rgba(251, 146, 60, 0.08);
  --orange-border: rgba(251, 146, 60, 0.25);
  --red: #f87171;
  --red-bg: rgba(248, 113, 113, 0.08);
  --red-border: rgba(248, 113, 113, 0.25);
  --gray: #94949c;
  --gray-bg: rgba(148, 148, 156, 0.08);
  --gray-border: rgba(148, 148, 156, 0.25);
}
@media (prefers-color-scheme: light) {
  :root {
    --bg: #fafafa;
    --bg-elev: #ffffff;
    --bg-elev-2: #f4f4f5;
    --border: #e4e4e7;
    --border-strong: #d4d4d8;
    --text: #18181b;
    --text-dim: #52525b;
    --text-mute: #71717a;
    --accent: #7c3aed;
    --accent-dim: #a78bfa;
  }
}
* { box-sizing: border-box; }
html { -webkit-text-size-adjust: 100%; }
body {
  margin: 0;
  font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, system-ui, sans-serif;
  font-size: 15px;
  line-height: 1.6;
  color: var(--text);
  background: var(--bg);
  font-feature-settings: 'cv02', 'cv03', 'cv04', 'cv11';
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
}
.mono {
  font-family: ui-monospace, 'SF Mono', 'JetBrains Mono', Consolas, monospace;
  font-feature-settings: 'liga' 0;
}
.container { max-width: 1120px; margin: 0 auto; padding: 56px 24px 96px; }
.hero { margin-bottom: 48px; }
.hero-eyebrow {
  font-size: 12px;
  font-weight: 600;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--accent);
  margin-bottom: 12px;
}
.hero h1 {
  font-size: 40px;
  line-height: 1.15;
  letter-spacing: -0.025em;
  font-weight: 700;
  margin: 0 0 8px;
  color: var(--text);
}
.hero h1 .repo { font-weight: 500; color: var(--text-dim); }
.hero-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
  color: var(--text-mute);
  font-size: 14px;
  margin-top: 12px;
}
.hero-meta span { display: inline-flex; align-items: center; gap: 6px; }
.dot { width: 4px; height: 4px; border-radius: 50%; background: var(--text-mute); display: inline-block; }
.stats {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
  gap: 12px;
  margin: 32px 0 0;
}
.stat {
  background: var(--bg-elev);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 18px 20px;
  transition: border-color 0.15s, transform 0.15s;
}
.stat:hover { border-color: var(--border-strong); }
.stat-num {
  font-family: ui-monospace, 'SF Mono', 'JetBrains Mono', Consolas, monospace;
  font-size: 28px;
  font-weight: 600;
  letter-spacing: -0.02em;
  line-height: 1;
  margin-bottom: 8px;
}
.stat-label {
  font-size: 12px;
  font-weight: 500;
  color: var(--text-mute);
  letter-spacing: 0.04em;
  text-transform: uppercase;
}
.stat.green .stat-num { color: var(--green); }
.stat.blue .stat-num { color: var(--blue); }
.stat.yellow .stat-num { color: var(--yellow); }
.stat.orange .stat-num { color: var(--orange); }
.stat.red .stat-num { color: var(--red); }
.stat.gray .stat-num { color: var(--gray); }

section { margin-top: 64px; }
section h2 {
  font-size: 22px;
  letter-spacing: -0.015em;
  font-weight: 600;
  margin: 0 0 4px;
  color: var(--text);
  display: flex;
  align-items: baseline;
  gap: 12px;
}
section h2 .count {
  font-size: 14px;
  color: var(--text-mute);
  font-weight: 500;
  font-family: ui-monospace, 'SF Mono', 'JetBrains Mono', Consolas, monospace;
}
section .section-sub {
  font-size: 14px;
  color: var(--text-mute);
  margin: 0 0 20px;
}
.empty {
  background: var(--bg-elev);
  border: 1px dashed var(--border);
  border-radius: 8px;
  padding: 20px;
  color: var(--text-mute);
  font-size: 14px;
  text-align: center;
}

table {
  width: 100%;
  border-collapse: separate;
  border-spacing: 0;
  background: var(--bg-elev);
  border: 1px solid var(--border);
  border-radius: 10px;
  overflow: hidden;
  font-size: 14px;
}
thead { background: var(--bg-elev-2); }
th {
  text-align: left;
  font-weight: 500;
  font-size: 11px;
  color: var(--text-mute);
  text-transform: uppercase;
  letter-spacing: 0.06em;
  padding: 12px 16px;
  border-bottom: 1px solid var(--border);
  white-space: nowrap;
}
td {
  padding: 14px 16px;
  border-bottom: 1px solid var(--border);
  vertical-align: top;
  color: var(--text-dim);
}
tr:last-child td { border-bottom: none; }
tr:hover td { background: var(--bg-elev-2); }
td.pr-num { white-space: nowrap; }
td.pr-num a {
  font-family: ui-monospace, 'SF Mono', 'JetBrains Mono', Consolas, monospace;
  font-size: 13px;
  color: var(--accent);
  text-decoration: none;
  font-weight: 500;
}
td.pr-num a:hover { text-decoration: underline; }
td.title { color: var(--text); font-weight: 500; max-width: 360px; }
td.author { color: var(--text-dim); font-size: 13px; }
td.score { font-family: ui-monospace, 'SF Mono', Consolas, monospace; font-weight: 600; }
td.notes { color: var(--text-mute); font-size: 13px; line-height: 1.5; }

.tag {
  display: inline-block;
  font-size: 11px;
  font-weight: 500;
  padding: 2px 8px;
  border-radius: 4px;
  letter-spacing: 0.02em;
  font-family: ui-monospace, 'SF Mono', Consolas, monospace;
}
.tag.passing { background: var(--green-bg); color: var(--green); border: 1px solid var(--green-border); }
.tag.failing { background: var(--red-bg); color: var(--red); border: 1px solid var(--red-border); }
.tag.pending { background: var(--yellow-bg); color: var(--yellow); border: 1px solid var(--yellow-border); }
.tag.unknown { background: var(--gray-bg); color: var(--gray); border: 1px solid var(--gray-border); }
.tag.tiny, .tag.small { background: var(--green-bg); color: var(--green); border: 1px solid var(--green-border); }
.tag.medium { background: var(--blue-bg); color: var(--blue); border: 1px solid var(--blue-border); }
.tag.large, .tag.xlarge { background: var(--orange-bg); color: var(--orange); border: 1px solid var(--orange-border); }
.check { color: var(--green); font-weight: 600; }
.dash { color: var(--text-mute); }

.cards { display: flex; flex-direction: column; gap: 14px; }
.card {
  background: var(--bg-elev);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 20px 22px;
  transition: border-color 0.15s;
}
.card:hover { border-color: var(--border-strong); }
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
  margin-bottom: 4px;
}
.card-title {
  font-size: 15px;
  font-weight: 600;
  margin: 0;
  letter-spacing: -0.005em;
  flex: 1;
}
.card-title a {
  color: var(--accent);
  text-decoration: none;
  font-family: ui-monospace, 'SF Mono', Consolas, monospace;
  font-weight: 500;
  font-size: 14px;
  margin-right: 8px;
}
.card-title a:hover { text-decoration: underline; }
.card-title .title-text { color: var(--text); }
.card-meta {
  font-size: 13px;
  color: var(--text-mute);
  margin: 0 0 12px;
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  align-items: center;
}
.card-meta .meta-sep { color: var(--border-strong); }
.card-summary {
  color: var(--text-dim);
  font-size: 14px;
  line-height: 1.6;
  margin: 0 0 14px;
}
.section-label {
  font-size: 11px;
  font-weight: 500;
  color: var(--text-mute);
  text-transform: uppercase;
  letter-spacing: 0.06em;
  margin: 14px 0 6px;
}
.concerns { display: flex; flex-direction: column; gap: 6px; }
.concern {
  font-size: 13px;
  color: var(--text-dim);
  line-height: 1.55;
  padding: 8px 12px 8px 14px;
  border-left: 2px solid var(--red);
  background: var(--red-bg);
  border-radius: 0 6px 6px 0;
}
.smells { display: flex; flex-wrap: wrap; gap: 6px; }
.smell-tag {
  font-family: ui-monospace, 'SF Mono', Consolas, monospace;
  font-size: 12px;
  color: var(--orange);
  background: var(--orange-bg);
  border: 1px solid var(--orange-border);
  padding: 2px 8px;
  border-radius: 4px;
}

.badge {
  display: inline-block;
  font-size: 11px;
  font-weight: 600;
  padding: 4px 10px;
  border-radius: 20px;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  font-family: 'Inter', -apple-system, sans-serif;
  white-space: nowrap;
}
.badge.merge { background: var(--green-bg); color: var(--green); border: 1px solid var(--green-border); }
.badge.needs_changes { background: var(--yellow-bg); color: var(--yellow); border: 1px solid var(--yellow-border); }
.badge.needs_discussion { background: var(--blue-bg); color: var(--blue); border: 1px solid var(--blue-border); }
.badge.close { background: var(--red-bg); color: var(--red); border: 1px solid var(--red-border); }

.contested {
  background: var(--bg-elev);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 20px 22px;
  margin-bottom: 14px;
}
.contested h3 {
  margin: 0 0 12px;
  font-size: 14px;
  font-weight: 600;
  color: var(--text-dim);
  font-family: ui-monospace, 'SF Mono', Consolas, monospace;
}
.contested-pr {
  display: flex;
  justify-content: space-between;
  padding: 10px 0;
  border-top: 1px solid var(--border);
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}
.contested-pr:first-of-type { border-top: 1px solid var(--border); }
.contested-pr-main {
  font-size: 14px;
  display: flex;
  align-items: baseline;
  gap: 10px;
  flex-wrap: wrap;
}
.contested-pr-main a {
  font-family: ui-monospace, 'SF Mono', Consolas, monospace;
  color: var(--accent);
  text-decoration: none;
  font-weight: 500;
}
.contested-pr-main a:hover { text-decoration: underline; }
.contested-pr-meta {
  color: var(--text-mute);
  font-size: 12px;
}

ul.patterns { padding: 0; margin: 0; list-style: none; }
ul.patterns li {
  padding: 12px 16px 12px 20px;
  border-left: 2px solid var(--accent);
  background: var(--bg-elev);
  margin-bottom: 8px;
  border-radius: 0 8px 8px 0;
  font-size: 14px;
  color: var(--text-dim);
}

.footer {
  margin-top: 80px;
  padding-top: 24px;
  border-top: 1px solid var(--border);
  font-size: 13px;
  color: var(--text-mute);
  display: flex;
  flex-wrap: wrap;
  gap: 12px 18px;
}
.footer code { font-family: ui-monospace, 'SF Mono', Consolas, monospace; color: var(--text-dim); }

@media (max-width: 640px) {
  .container { padding: 32px 16px 64px; }
  .hero h1 { font-size: 30px; }
  table { font-size: 13px; }
  th, td { padding: 10px 12px; }
}
"""


def _badge(rec: str) -> str:
    label = {
        "merge": "approve",
        "needs_changes": "needs changes",
        "needs_discussion": "discuss",
        "close": "close",
    }.get(rec, rec)
    return f'<span class="badge {escape(rec)}">{escape(label)}</span>'


def _stat(num: int, label: str, color: str) -> str:
    return (
        f'<div class="stat {color}">'
        f'<div class="stat-num">{num}</div>'
        f'<div class="stat-label">{escape(label)}</div>'
        f'</div>'
    )


def _tag(value: str) -> str:
    """Render a colored chip. CSS picks the color via .tag.<value> rule."""
    safe = escape(value)
    return f'<span class="tag {safe}">{safe}</span>'


# Back-compat aliases for the two semantic uses (kept short, both call _tag).
_ci_tag = _tag
_size_tag = _tag


def _row(r: PRRecord) -> str:
    ai = r.ai_review
    score = f'{ai.score}' if ai and not ai.error else '<span class="dash">&mdash;</span>'
    notes = ""
    if ai and not ai.error and ai.summary:
        notes = escape(ai.summary[:130])
    tests_cell = '<span class="check">&#10003;</span>' if r.has_tests else '<span class="dash">&mdash;</span>'
    return (
        '<tr>'
        f'<td class="pr-num"><a href="{escape(r.url)}">#{r.number}</a></td>'
        f'<td class="title">{escape(r.title[:90])}</td>'
        f'<td class="author">{escape(r.author)}</td>'
        f'<td>{_size_tag(r.diff_size_bucket)}</td>'
        f'<td>{_ci_tag(r.ci_status)}</td>'
        f'<td>{tests_cell}</td>'
        f'<td class="mono">{r.age_days}d</td>'
        f'<td class="score">{score}</td>'
        f'<td class="notes">{notes}</td>'
        '</tr>'
    )


def _table_section(title: str, blurb: str, items: list, top_n: int) -> str:
    count_html = f'<span class="count">{len(items)}</span>'
    if not items:
        return (
            f'<section><h2>{escape(title)} {count_html}</h2>'
            f'<p class="section-sub">{escape(blurb)}</p>'
            f'<div class="empty">No PRs in this bucket.</div></section>'
        )
    rows = "".join(_row(r) for r in items[:top_n])
    more = ""
    if len(items) > top_n:
        more = f'<p class="section-sub" style="margin-top:12px;">&hellip; and {len(items) - top_n} more in pr_data.json</p>'
    return (
        f'<section><h2>{escape(title)} {count_html}</h2>'
        f'<p class="section-sub">{escape(blurb)}</p>'
        '<table><thead><tr>'
        '<th>PR</th><th>Title</th><th>Author</th><th>Size</th><th>CI</th>'
        '<th>Tests</th><th>Age</th><th>Score</th><th>AI summary</th>'
        '</tr></thead><tbody>'
        f'{rows}'
        f'</tbody></table>{more}</section>'
    )


def _ai_card(r: PRRecord) -> str:
    ai = r.ai_review
    if not ai or ai.error:
        return ""
    concerns = "".join(f'<div class="concern">{escape(c)}</div>' for c in ai.concerns)
    smells_html = ""
    if r.smell_flags:
        smells_html = (
            '<div class="section-label">Smell flags</div>'
            '<div class="smells">'
            + "".join(f'<span class="smell-tag">{escape(s)}</span>' for s in r.smell_flags)
            + '</div>'
        )
    concerns_block = (
        f'<div class="section-label">Concerns</div><div class="concerns">{concerns}</div>'
        if concerns else ""
    )
    return (
        '<div class="card">'
        '<div class="card-header">'
        f'<h3 class="card-title"><a href="{escape(r.url)}">#{r.number}</a>'
        f'<span class="title-text">{escape(r.title[:100])}</span></h3>'
        f'{_badge(ai.merge_recommendation)}'
        '</div>'
        '<div class="card-meta">'
        f'<span>by {escape(r.author)}</span>'
        '<span class="meta-sep">&middot;</span>'
        f'<span class="mono">score {ai.score}/10</span>'
        '<span class="meta-sep">&middot;</span>'
        f'<span>{_size_tag(r.diff_size_bucket)}</span>'
        '<span class="meta-sep">&middot;</span>'
        f'<span>{_ci_tag(r.ci_status)}</span>'
        '<span class="meta-sep">&middot;</span>'
        f'<span class="mono">{r.age_days}d old</span>'
        '</div>'
        f'<p class="card-summary">{escape(ai.summary)}</p>'
        f'{concerns_block}'
        f'{smells_html}'
        '</div>'
    )


def _contested_section(items: list) -> str:
    title = "Contested"
    blurb = "Multiple PRs are targeting the same issue. Pick one, close the others."
    count_html = f'<span class="count">{len(items)}</span>'
    if not items:
        return (
            f'<section><h2>{title} {count_html}</h2>'
            f'<p class="section-sub">{blurb}</p>'
            '<div class="empty">No contested PRs.</div></section>'
        )
    by_issue: dict = {}
    for r in items:
        for n in r.linked_issues:
            by_issue.setdefault(n, []).append(r)
    chunks = [f'<section><h2>{title} {count_html}</h2><p class="section-sub">{blurb}</p>']
    for issue_num, prs in sorted(by_issue.items()):
        unique = {p.number: p for p in prs}
        if len(unique) < 2:
            continue
        chunks.append(f'<div class="contested"><h3>Issue #{issue_num}</h3>')
        for r in sorted(unique.values(), key=lambda x: x.created_at):
            ai = r.ai_review
            ai_bit = ""
            if ai and not ai.error:
                ai_bit = f'<span class="meta-sep">&middot;</span>{_badge(ai.merge_recommendation)}<span class="mono">{ai.score}/10</span>'
            chunks.append(
                '<div class="contested-pr">'
                '<div class="contested-pr-main">'
                f'<a href="{escape(r.url)}">#{r.number}</a>'
                f'<span style="color: var(--text-mute); font-size: 13px;">by {escape(r.author)}</span>'
                f'{_size_tag(r.diff_size_bucket)}{_ci_tag(r.ci_status)}'
                f'{ai_bit}'
                '</div>'
                f'<div class="contested-pr-meta mono">{r.age_days}d</div>'
                '</div>'
            )
        chunks.append('</div>')
    chunks.append('</section>')
    return "".join(chunks)


def render_html(records: list, owner: str, repo: str, open_issue_count: int, top_n: int = 8) -> str:
    by_bucket: dict = {}
    for r in records:
        by_bucket.setdefault(r.bucket, []).append(r)
    for items in by_bucket.values():
        items.sort(key=lambda x: x.bucket_rank)

    quick_wins = by_bucket.get("quick_wins", [])
    high_impact = by_bucket.get("high_impact", [])
    contested = by_bucket.get("contested", [])
    ai_flagged = by_bucket.get("ai_flagged", [])
    stale = by_bucket.get("stale", [])
    risky = by_bucket.get("risky", [])

    dependabot = sum(1 for r in records if r.is_dependabot)
    first_time = sum(1 for r in records if r.author_type == "first_time")
    no_tests = sum(1 for r in records if not r.has_tests and r.diff_size_bucket in {"medium", "large", "xlarge"})
    failing = sum(1 for r in records if r.ci_status == "failing")

    today = datetime.now(tz=timezone.utc).date().isoformat()

    body = []
    body.append(
        '<div class="hero">'
        '<div class="hero-eyebrow">PR Backlog Audit</div>'
        f'<h1>{escape(owner)}<span class="repo">/{escape(repo)}</span></h1>'
        '<div class="hero-meta">'
        f'<span>{escape(today)}</span><span class="dot"></span>'
        f'<span><span class="mono">{len(records)}</span> open PRs</span><span class="dot"></span>'
        f'<span><span class="mono">{open_issue_count}</span> open issues</span>'
        '</div>'
        '<div class="stats">'
        + _stat(len(quick_wins), "quick wins", "green")
        + _stat(len(high_impact), "high impact", "blue")
        + _stat(len(contested), "contested", "yellow")
        + _stat(len(ai_flagged), "ai flagged", "orange")
        + _stat(len(stale), "stale", "gray")
        + _stat(len(risky), "risky", "red")
        + '</div></div>'
    )
    body.append(_table_section("Quick wins", "Small, passing CI, mergeable. Batch these this week.", quick_wins, top_n))
    body.append(_table_section("High impact", "Closes high-demand issues. Worth dedicated review time.", high_impact, top_n))
    body.append(_contested_section(contested))

    if ai_flagged:
        ai_html = (
            f'<section><h2>AI flagged <span class="count">{len(ai_flagged)}</span></h2>'
            '<p class="section-sub">LLM review surfaced blocking concerns. Review each before merging.</p>'
            '<div class="cards">'
            + "".join(_ai_card(r) for r in ai_flagged[:top_n])
            + '</div>'
        )
        if len(ai_flagged) > top_n:
            ai_html += f'<p class="section-sub" style="margin-top:12px;">&hellip; and {len(ai_flagged) - top_n} more in pr_data.json</p>'
        ai_html += '</section>'
        body.append(ai_html)
    else:
        body.append('<section><h2>AI flagged <span class="count">0</span></h2><p class="section-sub">LLM review surfaced blocking concerns.</p><div class="empty">No PRs flagged.</div></section>')

    body.append(_table_section("Stale", "60+ days idle, dirty merge state, or failing CI for weeks. Close or revive.", stale, top_n))
    body.append(_table_section("Risky", "Large diffs without tests or with failing CI. Need deeper review.", risky, top_n))

    patterns_lines = []
    if dependabot >= 5:
        patterns_lines.append(f"{dependabot} dependabot PRs in queue. Consider enabling auto-merge for dependency groups.")
    if first_time >= 3:
        patterns_lines.append(f"{first_time} PRs from first-time contributors. A fast first-touch reply keeps them engaged.")
    if no_tests >= 3:
        patterns_lines.append(f"{no_tests} mid/large PRs landed without tests. Worth flagging in CONTRIBUTING.md.")
    if failing:
        patterns_lines.append(f"{failing} PRs have failing CI and won't merge until fixed.")
    if not patterns_lines:
        patterns_lines.append("No significant patterns surfaced beyond the per-bucket details above.")

    body.append(
        '<section><h2>Patterns</h2>'
        '<p class="section-sub">Recurring signals across the backlog worth a CONTRIBUTING.md note or workflow change.</p>'
        '<ul class="patterns">'
        + "".join(f'<li>{escape(p)}</li>' for p in patterns_lines)
        + '</ul></section>'
    )

    body.append(
        '<div class="footer">'
        '<span>Generated by <code>pr-audit</code></span>'
        '<span class="dot"></span>'
        '<span>Read-only, public data only</span>'
        '<span class="dot"></span>'
        '<span>LLM reviews via Claude Haiku 4.5</span>'
        '<span class="dot"></span>'
        '<span>Maintainer judgment is the final word</span>'
        '</div>'
    )

    return (
        '<!DOCTYPE html><html lang="en"><head>'
        '<meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        '<meta name="color-scheme" content="dark light">'
        f'<title>PR audit &middot; {escape(owner)}/{escape(repo)}</title>'
        f'<style>{_CSS}</style>'
        '</head><body><div class="container">'
        + "".join(body) +
        '</div></body></html>'
    )
