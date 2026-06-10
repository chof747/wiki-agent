# OpenAI Runner Setup

This guide shows how to give `wiki-agent` access to the OpenAI-backed
`wiki-agent-runner` without putting provider secrets into the main app config.

The key rule is:

- `wiki-agent` app config stays provider-agnostic
- OpenAI credentials and model settings live in the **Runner** environment

## 1. Keep the main app config small

Create a normal app config file such as `config.toml`:

```toml
bot_name = "marvin"

[postgres]
dsn = "postgresql://wiki_agent:wiki_agent@localhost:5432/wiki_agent"

[runner]
command = ["wiki-agent-runner"]

[service]
log_level = "INFO"
```

Do not put `OPENAI_API_KEY` or other provider secrets in this file.

## 2. Export the OpenAI API key in the Runner environment

The OpenAI Python SDK reads `OPENAI_API_KEY` from the environment.

For a local shell session:

```bash
export OPENAI_API_KEY="sk-your-real-key-here"
```

If you want to pin a model explicitly, also export:

```bash
export WIKI_AGENT_RUNNER_OPENAI_MODEL="gpt-4o-2024-08-06"
```

If you omit `WIKI_AGENT_RUNNER_OPENAI_MODEL`, the runner currently defaults to
`gpt-4o-2024-08-06`.

## 3. Set the optional Runner guardrails

The runner supports environment-only operational limits:

```bash
export WIKI_AGENT_RUNNER_MAX_INPUT_BYTES="32768"
export WIKI_AGENT_RUNNER_MAX_OUTPUT_BYTES="40960"
export WIKI_AGENT_RUNNER_MODEL_TIMEOUT_SECONDS="60"
```

Current meanings:

- `WIKI_AGENT_RUNNER_MAX_INPUT_BYTES`: max rendered prompt size before the model call
- `WIKI_AGENT_RUNNER_MAX_OUTPUT_BYTES`: max `final_page_content` size before save
- `WIKI_AGENT_RUNNER_MODEL_TIMEOUT_SECONDS`: OpenAI SDK request timeout

## 4. Start the app with those variables present

Example:

```bash
export OPENAI_API_KEY="sk-your-real-key-here"
export WIKI_AGENT_RUNNER_OPENAI_MODEL="gpt-4o-2024-08-06"
export WIKI_AGENT_RUNNER_MAX_INPUT_BYTES="32768"
export WIKI_AGENT_RUNNER_MAX_OUTPUT_BYTES="40960"
export WIKI_AGENT_RUNNER_MODEL_TIMEOUT_SECONDS="60"

wiki-agent run --config config.toml
```

`wiki-agent` launches `wiki-agent-runner` as a subprocess. The subprocess inherits
the environment, so the runner receives the OpenAI credentials and limits.

## 5. Prefer a wrapper script for service deployments

For a managed service, keep secrets out of `config.toml` and load them before
starting the app.

Example wrapper script:

```bash
#!/usr/bin/env bash
set -euo pipefail

export OPENAI_API_KEY="$(security find-generic-password -a wiki-agent -s openai-api-key -w)"
export WIKI_AGENT_RUNNER_OPENAI_MODEL="gpt-4o-2024-08-06"
export WIKI_AGENT_RUNNER_MAX_INPUT_BYTES="32768"
export WIKI_AGENT_RUNNER_MAX_OUTPUT_BYTES="40960"
export WIKI_AGENT_RUNNER_MODEL_TIMEOUT_SECONDS="60"

exec wiki-agent run --config /opt/wiki-agent/config.toml
```

This keeps:

- app config in `config.toml`
- provider secret in keychain or secret storage
- provider-specific Runner behavior in environment variables

## 6. Example launchd or systemd-style environment file

If your process manager supports environment files, keep the values in a file
that is not committed to the repo.

Example `.env`-style file:

```bash
OPENAI_API_KEY=sk-your-real-key-here
WIKI_AGENT_RUNNER_OPENAI_MODEL=gpt-4o-2024-08-06
WIKI_AGENT_RUNNER_MAX_INPUT_BYTES=32768
WIKI_AGENT_RUNNER_MAX_OUTPUT_BYTES=40960
WIKI_AGENT_RUNNER_MODEL_TIMEOUT_SECONDS=60
```

Then load that file before starting the service according to your process
manager's normal mechanism.

## 7. Optional: override the Runner command itself

Most deployments should keep:

```toml
[runner]
command = ["wiki-agent-runner"]
```

If you need a different executable in one environment, use
`WIKI_AGENT_RUNNER_COMMAND_JSON`.

Example:

```bash
export WIKI_AGENT_RUNNER_COMMAND_JSON='["/opt/wiki-agent/bin/wiki-agent-runner"]'
```

This changes the runner subprocess command without changing the committed config.

## 8. Minimal end-to-end local example

```bash
cat > config.toml <<'EOF'
bot_name = "marvin"

[postgres]
dsn = "postgresql://wiki_agent:wiki_agent@localhost:5432/wiki_agent"

[runner]
command = ["wiki-agent-runner"]

[service]
log_level = "INFO"
scan_interval = 60
stale_processing_timeout = 900
EOF

export OPENAI_API_KEY="sk-your-real-key-here"
export WIKI_AGENT_RUNNER_OPENAI_MODEL="gpt-4o-2024-08-06"
export WIKI_AGENT_RUNNER_MAX_INPUT_BYTES="32768"
export WIKI_AGENT_RUNNER_MAX_OUTPUT_BYTES="40960"
export WIKI_AGENT_RUNNER_MODEL_TIMEOUT_SECONDS="60"

wiki-agent run-once --config config.toml
```

## 9. What not to do

- Do not commit `OPENAI_API_KEY` to the repo
- Do not add provider secrets to `config.toml`
- Do not move provider selection into the app-owned config model
- Do not assume the main app needs to know which provider the Runner uses
