# Wiki Agent

Wiki Agent is a scheduled Wiki-Go comment agent. It scans for comments that start with the configured bot mention, turns each eligible comment into one durable Postgres-backed job, and processes jobs one at a time.

Start here if you need to:

- run the local integration harness
- deploy the service with the published Docker image
- understand the repo's ticket, triage, and implementation flow

For the domain model, read [`CONTEXT.md`](./CONTEXT.md). For the accepted architecture, read [`docs/adr/0002-scheduled-comment-agent-with-durable-jobs.md`](./docs/adr/0002-scheduled-comment-agent-with-durable-jobs.md).

## Prerequisites

- Python 3.14
- `uv`
- Docker
- a reachable Postgres instance
- a local `.env` file and runtime `config.toml` with your environment-specific settings

The repo provides these main entrypoints:

```bash
uv run wiki-agent --help
uv run wiki-agent-integration --help
uv run wiki-agent-worktree --help
```

## Run The Integration Harness

Use the repo-owned harness when you want a real Wiki-Go boundary for local runtime checks or integration tests.

If one DSN is correct for both admin and runtime access, export it once:

```bash
export WIKI_AGENT_POSTGRES_DSN="postgresql://wiki_agent:wiki_agent@localhost:5432/wiki_agent"
env UV_CACHE_DIR=/private/tmp/uv-cache uv run wiki-agent-integration reset
env UV_CACHE_DIR=/private/tmp/uv-cache uv run wiki-agent-integration test
```

If the harness needs separate admin and runtime credentials:

```bash
export WIKI_AGENT_INTEGRATION_ADMIN_DSN="postgresql://admin:admin@localhost:5432/postgres"
export WIKI_AGENT_INTEGRATION_RUNTIME_DSN="postgresql://wiki_agent:wiki_agent@localhost:5432/wiki_agent"
env UV_CACHE_DIR=/private/tmp/uv-cache uv run wiki-agent-integration reset
env UV_CACHE_DIR=/private/tmp/uv-cache uv run wiki-agent-integration test
```

For manual harness-backed QA:

```bash
env UV_CACHE_DIR=/private/tmp/uv-cache uv run wiki-agent-integration run-once
env UV_CACHE_DIR=/private/tmp/uv-cache uv run wiki-agent-integration seed-comment --page "__tests__/scanner-dry-run/eligible" --text "@marvin # Write a 4 line poem."
```

Thin helper scripts are also available:

```bash
scripts/manual_harness_setup_and_comment.sh
scripts/manual_harness_run_once.sh
```

More detail: [`docs/design/integration-harness.md`](./docs/design/integration-harness.md)

## Deploy With The Docker Image

The published image is:

`ghcr.io/chof747/wiki-agent`

The default container command is:

```text
wiki-agent run --config /config/config.toml
```

Mount your runtime config at `/config/config.toml`. Keep Postgres, Wiki-Go, and secrets external to the image.

Example Compose service:

```yaml
services:
  wiki-agent:
    image: ghcr.io/chof747/wiki-agent:latest
    restart: unless-stopped
    volumes:
      - ./wiki-agent/config.toml:/config/config.toml:ro
    environment:
      OPENAI_API_KEY: ${OPENAI_API_KEY}
    healthcheck:
      interval: 2m
      timeout: 45s
```

Before enabling the long-running service, run the installed shakedown locally or in your container environment:

```bash
uv run wiki-agent check --config config.toml
```

For local image verification:

```bash
docker build -t wiki-agent:local .
docker inspect --format='{{json .Config.Healthcheck}}' wiki-agent:local
docker run --rm wiki-agent:local --help
docker run --rm --entrypoint wikigo-helper wiki-agent:local --help
docker run --rm --entrypoint sh wiki-agent:local -lc 'command -v wikigo-comments-scan && command -v wikigo-helper'
```

More detail: [`docs/operators/docker-image.md`](./docs/operators/docker-image.md)

## Innovation Cycle

The repo's default change flow is:

1. Capture the idea in GitHub Issues.
2. If the work is broad, turn it into a PRD with `/to-prd`.
3. If the work needs multiple independent slices, break it into issues with `/to-issues`.
4. Triage the resulting issue until it reaches `ready-for-agent`.
5. Create an issue-scoped worktree and implement exactly one issue outcome.
6. Run local verification.
7. Stop for human review before commit, push, or PR creation.

The policy details live in [`docs/agents/implementation-workflow.md`](./docs/agents/implementation-workflow.md).

## Where To Add Tickets

Create tickets in this repo's GitHub issue tracker with `gh` from inside the clone:

```bash
gh issue create --title "..." --body "..."
```

Use:

- one issue for a small concrete implementation task
- `/to-prd` first for broad initiatives
- `/to-issues` for medium-sized plans that should become independent slices

Issue tracker reference: [`docs/agents/issue-tracker.md`](./docs/agents/issue-tracker.md)

## How To Do Triage

Triage is label-driven. The canonical states are:

- `needs-triage`: needs evaluation, not ready to implement
- `needs-info`: waiting on clarification
- `ready-for-agent`: approved for implementation
- `ready-for-human`: requires human implementation or decision
- `wontfix`: will not be actioned

An issue is ready to implement only when it has one primary outcome, clear acceptance criteria, the right triage label, and no unresolved blocking questions.

Triage references:

- [`docs/agents/triage-labels.md`](./docs/agents/triage-labels.md)
- [`docs/agents/implementation-workflow.md`](./docs/agents/implementation-workflow.md)

## How To Invoke Implementation And Testing

Implementation starts from a `ready-for-agent` issue on a clean control checkout.

Create the issue worktree:

```bash
uv run wiki-agent-worktree create <issue-number>
uv run wiki-agent-worktree create <issue-number> --base release/<release-name>
```

That creates an issue branch and worktree from `origin/main` by default, or from an explicit `origin/release/<release-name>` base when `--base` is provided. It also installs dependencies and prepares the local runtime state used by the repo workflow.

Inside the issue worktree, use the default verification baseline:

```bash
uv run pytest
WIKI_AGENT_TEST_POSTGRES_DSN=postgresql://wiki_agent:wiki_agent@localhost:5432/wiki_agent uv run pytest
```

If the change touches the harness-backed runtime boundary, also run the harness-managed verification path:

```bash
env UV_CACHE_DIR=/private/tmp/uv-cache uv run wiki-agent-integration test
```

Useful runtime commands during implementation:

```bash
uv run wiki-agent check --config config.toml
uv run wiki-agent run-once --config config.toml
uv run wiki-agent run --config config.toml
```

Worktree and implementation references:

- [`docs/operators/worktree-workflow.md`](./docs/operators/worktree-workflow.md)
- [`docs/operators/openai-runner-setup.md`](./docs/operators/openai-runner-setup.md)
- [`docs/design/comment-agent-overview.md`](./docs/design/comment-agent-overview.md)

## Additional Docs

- Architecture overview: [`docs/design/comment-agent-overview.md`](./docs/design/comment-agent-overview.md)
- Integration harness: [`docs/design/integration-harness.md`](./docs/design/integration-harness.md)
- Runner setup: [`docs/operators/openai-runner-setup.md`](./docs/operators/openai-runner-setup.md)
- Docker image: [`docs/operators/docker-image.md`](./docs/operators/docker-image.md)
