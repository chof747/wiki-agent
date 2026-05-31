# Scheduled comment agent with durable jobs

Supersedes: [0001-comment-driven-stateless-reconciliation](0001-comment-driven-stateless-reconciliation.md)

## Status

Accepted

## Context

The first architecture decision described a generic comment-triggered single invocation model. During design, several constraints became concrete:

- Wiki-Go does not need to be forked for outbound webhooks.
- The installed `wiki-go` skill already provides helper commands for scanning comments, reading and saving pages, and deleting comments.
- Comment volume is expected to be low, so parallel processing is unnecessary.
- The service should run continuously in the background.
- Postgres is available and should provide durable job storage.
- Rejected, unclear, impossible, unsafe, or unsupported requests should be handled visibly by Marvin rather than left as raw trigger comments.

## Decision

Implement the comment agent as a scheduled background scanner plus a strictly one-at-a-time worker in one long-running foreground process.

The scanner uses the existing Wiki-Go helper command boundary, starting with `wikigo-comments-scan`, to discover comments that start with the configured bot mention derived from `BOT_NAME`. The scanner skips bot-authored comments and any comment containing a `wiki-agent:` marker. Each eligible comment is normalized into a canonical Postgres `comment_jobs` row keyed by `source_system + comment_identity`; duplicate discoveries do not create new processing rows. While a job remains `queued`, duplicate discovery refreshes the stored executable snapshot (`target_page`, original comment text, stripped prompt, and source metadata) plus receipt metadata on that row. After the worker claims the job or the job reaches a terminal status, duplicate discovery refreshes receipt metadata only and leaves the executable snapshot frozen.

The worker claims queued jobs in stable scanner discovery order and invokes a language-agnostic runner executable. The runner receives one Prompt Envelope JSON object on stdin and must emit exactly one finalized Response JSON object on stdout. Logs go to stderr. A non-zero exit or timeout without a valid finalized response is mapped to `UPDATE_FAILED`.

The target page is always the Wiki-Go page where the source comment was found. Comments cannot redirect work to other pages. Cross-page and multi-page requests are rejected rather than executed.

Postgres is the durable queue and operational state store. It is not the reconciliation authority for whether content is already applied. Live Wiki-Go state remains the source for update confirmation, deletion confirmation, and duplicate handling. The service creates its small internal schema at startup using simple idempotent DDL.

The service enforces singleton execution with a Postgres advisory lock. A second instance exits immediately if it cannot acquire the lock. Stale `processing` jobs are marked `UPDATE_FAILED` after a configurable timeout.

## Domain Outcomes

The top-level status code set is:

- `SUCCESS`
- `ALREADY_PROCESSED`
- `REJECTED_WITH_COMMENT`
- `UPDATE_FAILED`
- `DELETE_FAILED`

`MULTI_TARGET_REQUEST` and other non-executable cases are reason codes under `REJECTED_WITH_COMMENT`, not top-level status codes. Missing target page is an operational integration error because the target comes from scanner/helper output.

Initial rejection reason codes are:

- `UNCLEAR_REQUEST`
- `MULTI_TARGET_REQUEST`
- `CROSS_PAGE_REQUEST`
- `FORBIDDEN_ACTION`
- `UNSUPPORTED_ACTION`
- `MISSING_CONTEXT`
- `SAFETY_REFUSAL`

`UPDATE_FAILED` covers any failure before a successful confirmed page update, including provider/model/tool failures, Wiki-Go read failures, save failures, and update confirmation failures. It is terminal, is not automatically retried, and keeps the original source comment undeleted for human review.

`DELETE_FAILED` covers deletion failure after a confirmed page update or confirmed rejection comment. It is terminal, logged, and not automatically retried.

## Successful Update Flow

1. The worker invokes the runner with one Prompt Envelope.
2. The runner fetches the latest target page source via Wiki-Go helper commands.
3. The runner applies the requested update only to the attached target page.
4. The runner saves the page.
5. The runner re-fetches the page source and confirms the update.
6. The runner deletes the original source comment.
7. The runner confirms the source comment is no longer listed.
8. The runner emits `SUCCESS`.

Successful page updates are silent. The agent deletes the trigger comment and does not create a success comment.

## Rejection Flow

When the request is unclear, impossible, unsafe, unsupported, cross-page, or multi-target, the runner performs a visible rejection workflow instead of updating the page.

1. The runner classifies the request with a fixed rejection reason code.
2. The runner creates a replacement comment authored by the configured bot identity.
3. The replacement comment includes a `wiki-agent:` marker, source comment id, visible reason code, exact blockquote of the original comment text, and human-readable explanation.
4. If the original comment is too long, the replacement quote is truncated with a clear note while the full original remains in the Postgres event snapshot.
5. The runner confirms the replacement comment exists.
6. The runner deletes the original source comment.
7. The runner confirms the source comment is no longer listed.
8. The runner emits `REJECTED_WITH_COMMENT`.

Example replacement comment:

```markdown
<!-- wiki-agent:rejection source_comment_id="1234" reason_code="CROSS_PAGE_REQUEST" -->

Marvin could not process this request.

> @marvin update /other-page too

Reason (`CROSS_PAGE_REQUEST`): This agent can only update the page where the comment was posted.
```

## Operational Behavior

The service supports a dry-run mode that scans and reports what would be enqueued without mutating Wiki-Go or writing jobs to Postgres.

The service supports a single-shot mode that scans once, processes at most one job, and exits.

The default scan interval is moderate, starting at 60 seconds and configurable.

The default runner timeout is 15 minutes and configurable.

The service exposes localhost-only health/status endpoints by default. Status endpoints show operational metadata such as lock ownership, last scan time, queue counts, and recent status counts. They do not expose prompts or comment text.

Logs are structured JSON on stdout/stderr. Postgres stores bounded status and error fields, not full runner stdout/stderr.

Configuration uses a config file plus environment overrides. Secrets remain in existing helper/keychain mechanisms rather than plaintext service config.

## Consequences

This design avoids modifying Wiki-Go and reuses the existing helper-command integration boundary.

The architecture prioritizes deterministic, inspectable behavior over throughput. Strict single-job processing is acceptable because expected comment volume is low.

Terminal failure semantics are conservative. Failed jobs do not block later jobs, but the same source comment identity is not re-enqueued on later scans. If a human wants to retry after `UPDATE_FAILED`, they create a new comment.

Retaining jobs indefinitely is acceptable for the first version because volume is expected to be low. Retention can be added later if needed.

The language-agnostic CLI runner protocol keeps implementation choices open while preserving a stable orchestration contract.
