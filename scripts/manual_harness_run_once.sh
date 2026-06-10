#!/bin/sh
set -eu

ROOT_DIR="$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

if [ -f "$ROOT_DIR/.env" ]; then
  set -a
  . "$ROOT_DIR/.env"
  set +a
fi

CONFIG_PATH="$ROOT_DIR/.runtime/integration-harness/wiki-agent.integration.toml"
env UV_CACHE_DIR=/private/tmp/uv-cache uv run wiki-agent-integration up
export PATH="$ROOT_DIR/.runtime/integration-harness/bin:$PATH"
export WIKI_AGENT_POSTGRES_DSN="${WIKI_AGENT_POSTGRES_DSN:-postgresql://wiki_agent:wiki_agent@localhost:5432/wiki_agent}"
export WIKI_AGENT_RUNNER_COMMAND_JSON="${WIKI_AGENT_RUNNER_COMMAND_JSON:-[\"wiki-agent-runner\"]}"
export WIKI_AGENT_CONFIG_PATH="$CONFIG_PATH"
unset WIKIGO_RUNTIME_CONFIG

env UV_CACHE_DIR=/private/tmp/uv-cache uv run wikigo-comments-scan
env UV_CACHE_DIR=/private/tmp/uv-cache uv run wiki-agent run-once --config "$CONFIG_PATH"
