"""Parse linked issues from PR bodies."""
from __future__ import annotations

import re

# Match standard GitHub linking keywords + #N (with whitespace, hyphen, underscore, or colon as separator)
_KEYWORD_PATTERN = re.compile(
    r"(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)[\s\-_:]+#?(\d+)",
    re.IGNORECASE,
)
_BARE_REF = re.compile(r"#(\d{1,6})")


def parse_linked_issues(body: str | None, branch_name: str = "") -> list[int]:
    if not body:
        body = ""
    matches = _KEYWORD_PATTERN.findall(body)
    nums = {int(m) for m in matches}
    branch_keyword = _KEYWORD_PATTERN.findall(branch_name)
    nums.update(int(m) for m in branch_keyword)
    return sorted(nums)


def parse_mentioned_issues(body: str | None) -> list[int]:
    if not body:
        return []
    matches = _BARE_REF.findall(body)
    return sorted({int(m) for m in matches})
