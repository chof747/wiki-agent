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
BOT_CONFIG_PATH="$ROOT_DIR/.runtime/integration-harness/wikigo-bot-config.json"
export PATH="$ROOT_DIR/.runtime/integration-harness/bin:$PATH"
export WIKI_AGENT_POSTGRES_DSN="${WIKI_AGENT_POSTGRES_DSN:-postgresql://wiki_agent:wiki_agent@localhost:5432/wiki_agent}"
export WIKI_AGENT_RUNNER_COMMAND_JSON="${WIKI_AGENT_RUNNER_COMMAND_JSON:-[\"wiki-agent-runner\"]}"
export WIKIGO_RUNTIME_CONFIG="${WIKIGO_RUNTIME_CONFIG:-$BOT_CONFIG_PATH}"
export OPENAI_API_KEY="${OPENAI_API_KEY:?OPENAI_API_KEY must be set}"
export WIKI_AGENT_RUNNER_OPENAI_MODEL="${WIKI_AGENT_RUNNER_OPENAI_MODEL:-gpt-4o-2024-08-06}"
export WIKI_AGENT_RUNNER_MAX_INPUT_BYTES="${WIKI_AGENT_RUNNER_MAX_INPUT_BYTES:-32768}"
export WIKI_AGENT_RUNNER_MAX_OUTPUT_BYTES="${WIKI_AGENT_RUNNER_MAX_OUTPUT_BYTES:-40960}"
export WIKI_AGENT_RUNNER_MODEL_TIMEOUT_SECONDS="${WIKI_AGENT_RUNNER_MODEL_TIMEOUT_SECONDS:-60}"

env UV_CACHE_DIR=/private/tmp/uv-cache uv run wiki-agent run-once --config "$CONFIG_PATH"
