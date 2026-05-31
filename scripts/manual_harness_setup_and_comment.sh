#!/bin/sh
set -eu

ROOT_DIR="$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

PAGE_PATH="${PAGE_PATH:-__tests__/scanner-dry-run/eligible}"
MANUAL_HARNESS_POSTGRES_DSN="${MANUAL_HARNESS_POSTGRES_DSN:-postgresql://wiki_agent:wiki_agent@localhost:5432/wiki_agent}"
MANUAL_HARNESS_ADMIN_POSTGRES_DSN="${MANUAL_HARNESS_ADMIN_POSTGRES_DSN:-$MANUAL_HARNESS_POSTGRES_DSN}"
RESET_COMMENT_JOBS="${RESET_COMMENT_JOBS:-1}"
COMMENT_TEXT="${COMMENT_TEXT:-@marvin # Eligible Fixture

Updated by manual harness test.
}"
ADMIN_CONFIG="$ROOT_DIR/.runtime/integration-harness/wikigo-admin-config.json"

WIKI_AGENT_INTEGRATION_ADMIN_DSN="$MANUAL_HARNESS_ADMIN_POSTGRES_DSN" \
WIKI_AGENT_INTEGRATION_RUNTIME_DSN="$MANUAL_HARNESS_POSTGRES_DSN" \
  env UV_CACHE_DIR=/private/tmp/uv-cache uv run wiki-agent-integration reset

export PATH="$ROOT_DIR/.runtime/integration-harness/bin:$PATH"

if [ "$RESET_COMMENT_JOBS" = "1" ]; then
  MANUAL_HARNESS_POSTGRES_DSN="$MANUAL_HARNESS_POSTGRES_DSN" \
    env UV_CACHE_DIR=/private/tmp/uv-cache uv run python - <<'PY'
import os

import psycopg

dsn = os.environ["MANUAL_HARNESS_POSTGRES_DSN"]
with psycopg.connect(dsn) as connection, connection.cursor() as cursor:
    cursor.execute("TRUNCATE TABLE comment_jobs RESTART IDENTITY")
    connection.commit()
PY
fi

payload_file="$(mktemp)"
cleanup() {
  rm -f "$payload_file"
}
trap cleanup EXIT INT TERM

cat >"$payload_file" <<JSON
{"content":$(printf '%s' "$COMMENT_TEXT" | env UV_CACHE_DIR=/private/tmp/uv-cache uv run python -c 'import json,sys; print(json.dumps(sys.stdin.read()))')}
JSON

WIKIGO_RUNTIME_CONFIG="$ADMIN_CONFIG" \
  env UV_CACHE_DIR=/private/tmp/uv-cache uv run python - <<'PY' "$PAGE_PATH"
import json
import os
import subprocess
import sys
from pathlib import Path

page_path = sys.argv[1]
config = os.environ["WIKIGO_RUNTIME_CONFIG"]
repo_root = Path.cwd()
helper = repo_root / ".runtime" / "integration-harness" / "bin" / "wikigo-comments"

result = subprocess.run(
    [str(helper), "list", page_path],
    cwd=repo_root,
    env={**os.environ, "WIKIGO_RUNTIME_CONFIG": config},
    capture_output=True,
    text=True,
    check=True,
)
for comment in json.loads(result.stdout):
    subprocess.run(
        [str(helper), "delete", comment["id"], page_path],
        cwd=repo_root,
        env={**os.environ, "WIKIGO_RUNTIME_CONFIG": config},
        check=True,
    )
PY

WIKIGO_RUNTIME_CONFIG="$ADMIN_CONFIG" \
wikigo-api POST "/api/comments/add/$PAGE_PATH" "$payload_file" application/json

WIKIGO_RUNTIME_CONFIG="$ADMIN_CONFIG" \
wikigo-comments list "$PAGE_PATH"
