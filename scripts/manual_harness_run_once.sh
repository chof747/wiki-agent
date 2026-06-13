#!/bin/sh
set -eu

ROOT_DIR="$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

exec env UV_CACHE_DIR=/private/tmp/uv-cache uv run wiki-agent-integration run-once "$@"
