#!/usr/bin/env bash
# Commit and push all branches of nasaspacechallenge.
# Usage: ./push_all_branches.sh <github_username> <github_token>
#   or set env GITHUB_USER and GITHUB_TOKEN.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$REPO_DIR"

GITHUB_USER="${1:-${GITHUB_USER:-}}"
GITHUB_TOKEN="${2:-${GITHUB_TOKEN:-}}"

if [[ -z "$GITHUB_USER" || -z "$GITHUB_TOKEN" ]]; then
  echo "Usage: $0 <github_username> <github_token>"
  echo "   or set GITHUB_USER and GITHUB_TOKEN env vars."
  exit 1
fi

# Ensure git identity
git config user.name "${GIT_USER_NAME:-$GITHUB_USER}" >/dev/null 2>&1 || true
git config user.email "${GIT_USER_EMAIL:-$GITHUB_USER@users.noreply.github.com}" >/dev/null 2>&1 || true

# Embed credentials in remote URL (HTTPS)
REMOTE_URL="https://${GITHUB_USER}:${GITHUB_TOKEN}@github.com/hajji-ismail7655/nasaspacechallenge.git"
git remote set-url origin "$REMOTE_URL"

BRANCHES=(
  main
  Datasets
  BestAlgo/topography
  BestAlgo/mineralogy
  BestAlgo/thermal_illumination
  BestAlgo/granular_aeolian
  BestAlgo/volatiles_subsurface
  OptiAlgo/topography
  OptiAlgo/mineralogy
  OptiAlgo/thermal_illumination
  OptiAlgo/granular_aeolian
  OptiAlgo/volatiles_subsurface
)

for b in "${BRANCHES[@]}"; do
  echo "=== Branch: $b ==="
  git checkout "$b"
  # Remove any stray EOF lines that may have been introduced
  # Stage all changes
  git add -A
  if ! git diff --cached --quiet; then
    git commit -m "chore: sync branch $b"
    echo "  committed changes"
  else
    echo "  nothing to commit"
  fi
  echo "  pushing..."
  git push -u origin "$b"
done

# Restore remote URL without token
git remote set-url origin "https://github.com/hajji-ismail7655/nasaspacechallenge.git"

echo "All branches pushed."
