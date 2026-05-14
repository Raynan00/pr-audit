#!/usr/bin/env bash
# Wrapper: full PR backlog triage.
# Usage: triage.sh OWNER/REPO [--max-prs N] [--skip-ai] [--output-dir PATH]
set -euo pipefail
exec pr-audit "$@"
