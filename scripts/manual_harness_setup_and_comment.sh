#!/bin/sh
set -eu

ROOT_DIR="$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

PAGE_PATH="${PAGE_PATH:-__tests__/scanner-dry-run/eligible}"
RESET_COMMENT_JOBS="${RESET_COMMENT_JOBS:-1}"
COMMENT_TEXT="${COMMENT_TEXT:-@marvin # Write a 4 line poem.
}"

if [ "$RESET_COMMENT_JOBS" = "1" ]; then
  exec env UV_CACHE_DIR=/private/tmp/uv-cache uv run wiki-agent-integration seed-comment --page "$PAGE_PATH" --text "$COMMENT_TEXT"
fi

exec env UV_CACHE_DIR=/private/tmp/uv-cache uv run wiki-agent-integration seed-comment --page "$PAGE_PATH" --text "$COMMENT_TEXT" --no-reset-comment-jobs
