#!/usr/bin/env bash

set -euo pipefail

if ! command -v git >/dev/null 2>&1; then
  echo "git is required for this safety check."
  exit 1
fi

if ! command -v rg >/dev/null 2>&1; then
  echo "ripgrep (rg) is required for this safety check."
  exit 1
fi

repo_root="$(git rev-parse --show-toplevel)"
cd "$repo_root"

tmp_files="$(mktemp)"
trap 'rm -f "$tmp_files"' EXIT

git ls-files -co --exclude-standard -z > "$tmp_files"

if [[ ! -s "$tmp_files" ]]; then
  echo "No tracked or unignored files found to scan."
  exit 0
fi

has_risky_names=0
has_secret_like_content=0

echo "Checking tracked and unignored files for risky filenames..."

while IFS= read -r -d '' file; do
  case "$file" in
    .env.example)
      ;;
    .env|.env.*|*.pem|*.p8|*.p12|*.key|*service-account*.json|*credentials*.json)
      echo "  risky file: $file"
      has_risky_names=1
      ;;
  esac
done < "$tmp_files"

echo "Scanning tracked and unignored files for secret-like content..."

while IFS= read -r -d '' file; do
  if rg -I -l \
    -e 'BEGIN (RSA )?PRIVATE KEY' \
    -e 'sk-[A-Za-z0-9]{20,}' \
    -e 'AIza[0-9A-Za-z_-]{20,}' \
    -- "$file" >/dev/null 2>&1; then
    echo "  possible secret-like content: $file"
    has_secret_like_content=1
  fi
done < "$tmp_files"

if [[ "$has_risky_names" -eq 1 || "$has_secret_like_content" -eq 1 ]]; then
  echo
  echo "Safety check failed."
  echo "Review the files above before pushing or opening a PR."
  exit 1
fi

echo "Safety check passed."
