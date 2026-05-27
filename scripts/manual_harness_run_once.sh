#!/bin/sh
set -eu

ROOT_DIR="$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

CONFIG_PATH="$ROOT_DIR/.runtime/integration-harness/wiki-agent.integration.toml"
BOT_CONFIG_PATH="$ROOT_DIR/.runtime/integration-harness/wikigo-bot-config.json"
export PATH="$ROOT_DIR/.runtime/integration-harness/bin:$PATH"
export WIKI_AGENT_POSTGRES_DSN="${WIKI_AGENT_POSTGRES_DSN:-postgresql://wiki_agent:wiki_agent@localhost:5432/wiki_agent}"
export WIKI_AGENT_RUNNER_COMMAND_JSON="${WIKI_AGENT_RUNNER_COMMAND_JSON:-[\"wiki-agent-runner\"]}"
export WIKIGO_RUNTIME_CONFIG="${WIKIGO_RUNTIME_CONFIG:-$BOT_CONFIG_PATH}"

env UV_CACHE_DIR=/private/tmp/uv-cache uv run wiki-agent run-once --config "$CONFIG_PATH"
