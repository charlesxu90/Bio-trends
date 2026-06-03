#!/usr/bin/env bash
# Monthly Bio-trend refresh via headless Claude Code.
#
# Crontab example (1st of each month, 06:00):
#   0 6 1 * * /ABS/PATH/Bio-trend/scripts/monthly_refresh.sh >> /ABS/PATH/Bio-trend/monthly_refresh.log 2>&1
#
# Requires: the `claude` and `gh` CLIs authenticated. Runs the deterministic
# pipeline; the prompt also lets Claude discover new bio sister journals and open
# a PR. For a pure-deterministic run, replace the `claude -p` call with
# `PYTHONNOUSERSITE=1 ./env/bin/bio-trend refresh`.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_DIR"
export PYTHONNOUSERSITE=1

git checkout main
git pull --ff-only || true

if ! command -v claude >/dev/null 2>&1; then
  echo "claude CLI not found; running deterministic refresh instead"
  ./env/bin/bio-trend check-feeds --check || true
  ./env/bin/bio-trend refresh
  exit 0
fi

claude -p \
  --permission-mode acceptEdits \
  --allowedTools "Bash,Read,Edit,Write,Glob,Grep,WebSearch,WebFetch" \
  "$(cat scripts/monthly_prompt.md)"
