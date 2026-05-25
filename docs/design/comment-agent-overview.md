# Comment Agent Overview

This document gives a high-level view of the Wiki-Go **Comment Agent** system.
Use it as the system map. For domain terminology, read [CONTEXT.md](../../CONTEXT.md). For architectural rationale, read [ADR 0002](../adr/0002-scheduled-comment-agent-with-durable-jobs.md).

## Purpose

The **Comment Agent** processes Wiki-Go comments that explicitly address the configured bot. Its job is to turn one eligible source comment into one deterministic **Invocation** that either:

- updates the attached **Target Page**, or
- creates a visible **Rejection Comment**

The system is intentionally conservative:

- one source comment maps to one durable **Comment Job**
- processing is one-at-a-time
- only the page where the comment was found may be changed
- completion is confirmed before the source comment is deleted

## Runtime Shape

The service runs as one foreground process started through the `wiki-agent` CLI.

Its main runtime components are:

- **Scanner**: discovers eligible Wiki-Go comments and normalizes them into durable **Comment Jobs**
- **Worker**: claims the next queued **Comment Job** and supervises one **Invocation**
- **Runner**: external executable invoked by the **Worker** to perform the domain work for one **Invocation**
- **Postgres**: durable queue and operational state store

## Responsibilities

The **Scanner** is responsible for discovery and enqueueing:

- read comments through Wiki-Go helper commands
- keep only comments that start with the configured **Bot Mention**
- skip bot-authored comments and comments containing `wiki-agent:` markers
- persist or refresh the canonical **Comment Job**

The **Worker** is responsible for orchestration:

- claim the next queued **Comment Job**
- build the **Prompt Envelope**
- launch the external **Runner**
- enforce timeout and process supervision
- record the finalized outcome

The **Runner** is responsible for execution against Wiki-Go:

- read the latest **Target Page**
- decide whether to perform an **Update Operation** or a rejection flow
- save and confirm the result
- delete the source comment only after the primary action is confirmed
- emit exactly one finalized **Response**

## Execution Flows

### Long-running mode

`wiki-agent run` starts the foreground service process. In the full design, this process repeatedly scans for work and processes queued jobs one at a time.

### One-shot mode

`wiki-agent run-once` exists for controlled execution and smoke testing.

The current implementation supports a scanner-only dry-run at `wiki-agent run-once --dry-run`. That path performs one non-mutating **Scanner** pass, emits normalized eligible **Comment Event** data to stdout as structured JSON, and does not write **Comment Jobs**, invoke the **Runner**, or mutate Wiki-Go.

Without `--dry-run`, the current implementation performs one **Scanner** pass, ensures the internal Postgres schema exists, persists or refreshes eligible **Comment Jobs**, then enters the **Worker** boundary once before exiting.

## Configuration Model

The current configuration contract is intentionally small:

- `bot_name`
- `postgres.dsn`
- `runner.command`
- `service.log_level`

Configuration precedence is:

1. built-in defaults where applicable
2. concrete config file passed by `--config`
3. environment-variable overrides

The repo ships `config.example.toml`. Real deployment config files such as `config.toml` are environment-specific and should not be committed. Secrets should come from environment variables.

## Current Skeleton

Issue 3 establishes the implementation skeleton, not the full runtime behavior.

The repo currently provides:

- Python 3.14 project setup with `uv` and `hatchling`
- `src/wiki_agent/` package layout
- `wiki-agent run` and `wiki-agent run-once` CLI commands
- stdlib-based config loading and JSON logging
- a bootable service stub with clean shutdown handling
- a real single-shot **Scanner** dry-run path via `wikigo-comments-scan`
- a Postgres-backed **Comment Job** repository with idempotent startup DDL
- durable enqueueing that preserves one canonical job per `source_system + comment_identity`
- a **Worker** stub boundary
- smoke and config tests

## Deferred Work

The following behaviors are intentionally deferred to later issues:

- actual **Runner** subprocess execution
- health and status HTTP endpoints
- full status mapping and invocation persistence

## Related Documents

- [CONTEXT.md](../../CONTEXT.md)
- [ADR 0001](../adr/0001-comment-driven-stateless-reconciliation.md)
- [ADR 0002](../adr/0002-scheduled-comment-agent-with-durable-jobs.md)
- [Integration Harness](./integration-harness.md)
