# OpenAI Runner Setup

This guide shows how to configure the OpenAI-backed `wiki-agent-runner` through
the main `wiki-agent` TOML config and the repo-root `.env` file used by local
entrypoints.

## 1. Put the runner and Wiki-Go settings in `config.toml`

Create a normal app config file such as `config.toml`:

```toml
bot_name = "marvin"

[postgres]
dsn = "postgresql://wiki_agent:wiki_agent@localhost:5432/wiki_agent"

[wikigo]
base_url = "http://127.0.0.1:4010"
username = "marvin"
password = "marvin-pass"

[runner]
command = ["wiki-agent-runner"]

[runner.openai]
api_key = "sk-your-real-key-here"
model = "gpt-4o-2024-08-06"
max_input_bytes = 32768
max_output_bytes = 40960
timeout_seconds = 60

[service]
log_level = "INFO"
```

Current meanings:

- `WIKI_AGENT_RUNNER_MAX_INPUT_BYTES`: max rendered prompt size before the model call
- `WIKI_AGENT_RUNNER_MAX_OUTPUT_BYTES`: max `final_page_content` size for `action="update"` before save
- `WIKI_AGENT_RUNNER_MODEL_TIMEOUT_SECONDS`: OpenAI SDK request timeout

Local startup precedence is:

1. built-in defaults
2. `config.toml`
3. repo-root `.env`
4. explicit exported environment variables

This means `.env` can fill in local secrets or overrides without replacing
values already exported by the calling shell.

`wiki-agent` passes the config path through to both the helper commands and the
runner subprocess, so `run` and `run-once` can use one file end to end.

## 2. Start the app with that config file

```bash
wiki-agent run --config config.toml
```

## 2a. Run the installation shakedown first

Before enabling the long-running service, run:

```bash
wiki-agent check --config config.toml
```

`wiki-agent check` writes one JSON object to stdout with `ok` plus per-check
results for:

- config loading
- Postgres connectivity and `comment_jobs` schema readiness
- the non-mutating `wikigo-comments-scan` helper boundary
- the configured runner subprocess

Exit codes are:

- `0` when every check passes
- `1` when one or more checks fail
- `2` when CLI usage or configuration loading fails before checks run

The runner probe is intentionally local-only. It sends an invalid prompt
envelope and requires the runner to return a finalized `UPDATE_FAILED`
response, which proves the subprocess contract without making an OpenAI call or
attempting Wiki-Go mutations.

## 3. Optional: keep local secrets in repo-root `.env`

Instead of putting secrets in `config.toml`, you can keep them in an
uncommitted repo-root `.env` file:

```dotenv
OPENAI_API_KEY=sk-your-real-key-here
WIKI_AGENT_POSTGRES_DSN=postgresql://wiki_agent:wiki_agent@localhost:5432/wiki_agent
```

`wiki-agent`, `wiki-agent-runner`, and `wiki-agent-integration` load that file
automatically at startup. Exported shell variables still take precedence.

## 4. Optional: override the Runner command itself

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

## 5. Minimal end-to-end local example

```bash
cat > config.toml <<'EOF'
bot_name = "marvin"

[postgres]
dsn = "postgresql://wiki_agent:wiki_agent@localhost:5432/wiki_agent"

[wikigo]
base_url = "http://127.0.0.1:4010"
username = "marvin"
password = "marvin-pass"

[runner]
command = ["wiki-agent-runner"]

[runner.openai]
api_key = "sk-your-real-key-here"
model = "gpt-4o-2024-08-06"
max_input_bytes = 32768
max_output_bytes = 40960
timeout_seconds = 60

[service]
log_level = "INFO"
scan_interval = 60
stale_processing_timeout = 900
EOF

wiki-agent check --config config.toml
wiki-agent run-once --config config.toml
```

## 6. Security note

Putting the OpenAI key in TOML is now supported for local and harness-backed
manual runs because it removes a major source of operator error.

Do not commit real secrets. Prefer an uncommitted local config such as
`config.toml`, an uncommitted repo-root `.env`, or both, and keep committed
examples on placeholder values.
