#!/usr/bin/env bash
# Wrapper: triage + build a stack-aware merge plan for the top N.
# Usage: plan_merges.sh OWNER/REPO N [--min-merge-score 7]
set -euo pipefail
REPO="$1"; shift
N="$1"; shift
exec pr-audit "$REPO" --plan-merges "$N" "$@"
