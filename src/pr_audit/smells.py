"""Heuristic code smell scanner. Regex-based, runs on PR diff text."""
from __future__ import annotations

import re

# Each pattern matches added lines (starting with `+ ` but not `+++ `, the file marker).
# The patterns are kept conservative; aim for high signal, low noise.
SMELL_PATTERNS: dict[str, str] = {
    # Bare except clauses
    "bare_except": r"^\+\s*except\s*:\s*$",
    # Looks like a hardcoded secret or API key (12+ chars of base64-ish alnum after `=` in a key/secret/token var)
    "hardcoded_secret": (
        r"^\+.*(?:api[_-]?key|secret|password|token|access[_-]?key)"
        r"\s*[:=]\s*[\"\'][A-Za-z0-9+/_\-]{16,}[\"\']"
    ),
    # TODO/FIXME/XXX markers added in this PR
    "todo_added": r"^\+.*(?:TODO|FIXME|XXX|HACK)\b",
    # Debug-style prints / logs
    "debug_print": r"^\+\s*(?:print\s*\(|console\.log\s*\()",
    # Disabled tests
    "disabled_test": r"^\+\s*(?:@pytest\.mark\.skip|xit\(|it\.skip\(|test\.skip\()",
    # Very long lines (potential code generation or copy-paste)
    "very_long_line": r"^\+.{300,}$",
}


def scan_diff_for_smells(diff: str) -> list[str]:
    """Return a list of `flag:count` strings for any smells detected."""
    if not diff:
        return []
    flags: list[str] = []
    for name, pattern in SMELL_PATTERNS.items():
        try:
            matches = re.findall(pattern, diff, re.MULTILINE | re.IGNORECASE)
        except re.error:
            continue
        if matches:
            flags.append(f"{name}:{len(matches)}")
    return flags
