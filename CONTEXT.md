# Wiki Agent CLI

This context defines the domain language for a scheduled comment agent that processes Wiki-Go comments in deterministic single-comment invocations.

## Language

**Comment Agent**:
The long-running background service that scans Wiki-Go comments, persists eligible work, and processes jobs one at a time.
_Avoid_: webhook receiver, chat bot

**Scanner**:
The scheduled background loop that discovers Wiki-Go comments addressed to the configured bot.
_Avoid_: webhook, listener

**Worker**:
The single-job execution loop that claims queued comment jobs and invokes the runner.
_Avoid_: parallel executor

**Comment Job**:
The canonical durable Postgres record for one source comment, keyed by `source_system + comment_identity`.
_Avoid_: retry attempt, delivery row

**Invocation**:
One deterministic processing attempt for exactly one **Comment Job**, from prompt-envelope construction to exactly one finalized outcome.
_Avoid_: session, conversation

**Runner**:
The language-agnostic executable invoked by the **Worker** for one **Invocation**.
_Avoid_: library callback, embedded agent loop

**Prompt Envelope**:
The structured JSON payload passed to the **Runner** on stdin, containing the stripped **Prompt**, original comment text, source metadata, and hard constraints.
_Avoid_: raw comment text, unstructured input

**Prompt**:
The executable user instruction after the leading bot mention has been stripped.
_Avoid_: comment body, chat message

**Response**:
The single JSON object emitted by the **Runner** on stdout when an **Invocation** finalizes.
_Avoid_: log output, dialogue

**Comment Event**:
A Wiki-Go comment discovered by the **Scanner** and eligible for processing because it starts with the configured bot mention.
_Avoid_: webhook delivery

**Comment Identity**:
The immutable unique identifier of a Wiki-Go comment from the source system.
_Avoid_: mutable key, derived hash

**Idempotency Key**:
The deduplication key used to ensure a **Comment Event** maps to at most one **Comment Job**.
_Avoid_: request id, retry token

**Bot Name**:
The configured identity used to derive the trigger mention, for example `BOT_NAME=marvin` yields `@marvin`.
_Avoid_: hard-coded Marvin

**Bot Mention**:
The required leading mention that activates the scanner for a comment.
_Avoid_: mention anywhere, fuzzy trigger

**Target Page**:
The Wiki-Go page path where the source comment was found.
_Avoid_: page named in the comment, fuzzy match, cross-page target

**Single-Target Scope**:
The rule that one **Comment Event** may affect only its attached **Target Page**.
_Avoid_: multi-page change set

**Primary Action**:
The domain work an **Invocation** performs before source-comment deletion: either a page update or a rejection-comment workflow.
_Avoid_: response

**Update Operation**:
Any wiki page modification requested for the **Target Page**, including full-page overwrite.
_Avoid_: restricted operation set

**Rejection Comment**:
A replacement Wiki-Go comment created by the bot when a request is unclear, impossible, unsafe, unsupported, or violates hard constraints.
_Avoid_: failure log, hidden rejection

**Rejection Reason Code**:
A stable machine-readable reason for `REJECTED_WITH_COMMENT`, such as `UNCLEAR_REQUEST` or `CROSS_PAGE_REQUEST`.
_Avoid_: free-text-only rejection

**Comment Deletion**:
The act of removing the source comment after successful **Primary Action** completion.
_Avoid_: archive, hide

**Completion Order**:
The required sequence of domain steps within a successful **Invocation**.
_Avoid_: best-effort ordering

**Update Confirmation**:
The verification step that proves the requested **Update Operation** is committed on the **Target Page**.
_Avoid_: assumed write success

**Replacement Confirmation**:
The verification step that proves a **Rejection Comment** exists before deleting the source comment.
_Avoid_: optimistic comment creation

**Deletion Confirmation**:
The verification step that proves the source comment is no longer listed after deletion.
_Avoid_: optimistic delete acknowledgment

**Verification Window**:
The maximum time and attempts allowed for post-action confirmation checks.
_Avoid_: delayed polling

**Reconciliation**:
Duplicate-handling behavior that verifies live source/page/comment state rather than blindly repeating the **Primary Action**.
_Avoid_: blind replay

**Stateless Reconciliation**:
Duplicate handling that uses live Wiki-Go state only, without treating Postgres as an audit authority for whether page content was already applied.
_Avoid_: reconciliation store, audit ledger

**Conflict Policy**:
The rule for handling a **Target Page** that changed before update execution.
_Avoid_: precondition lock

**Instruction Authority**:
The precedence rule for conflicting guidance during page updates.
_Avoid_: implicit convention override

**Input Validation**:
The pre-execution checks that must pass before an update or rejection workflow is attempted.
_Avoid_: best-effort parsing

**Status Code**:
A stable machine-readable domain outcome code for a finalized **Invocation**.
_Avoid_: free-text-only errors

**Status Code Set**:
The minimal stable list of allowed **Status Code** values.
_Avoid_: ad-hoc statuses

**Success Criteria**:
The required conditions for a finalized **Invocation** to be classified as handled.
_Avoid_: partial completion

**Already Processed**:
The terminal outcome for a duplicate **Comment Event** whose source comment was already completed.
_Avoid_: duplicate success

**Terminal Failure**:
A finalized failed outcome that the worker does not automatically retry or re-enqueue.
_Avoid_: retry loop

**Dry Run**:
A non-mutating mode that scans and reports what would be enqueued without writing jobs or invoking the runner.
_Avoid_: test processing

## Relationships

- The **Comment Agent** runs as one long-running foreground process by default.
- The **Comment Agent** contains a scheduled **Scanner** and a strictly one-at-a-time **Worker**.
- The **Scanner** uses the installed Wiki-Go helper command boundary, including `wikigo-comments-scan`.
- The **Scanner** discovers comments across all pages and keeps only comments that start with `@<BOT_NAME>`.
- The **Scanner** skips comments authored by the bot and comments containing any `wiki-agent:` marker.
- The **Scanner** strips the leading **Bot Mention** before creating the **Prompt**.
- The **Target Page** is inferred from the Wiki-Go page where the comment was found.
- Comments cannot redirect work to another target page.
- Cross-page and multi-page requests are rejected with a **Rejection Comment**.
- Each **Comment Event** maps to one canonical **Comment Job**.
- The **Idempotency Key** is `source_system + comment_identity`.
- Duplicate scanner discoveries update receipt metadata only and do not create additional processing rows.
- **Comment Jobs** are stored in Postgres and retained indefinitely for the first version.
- Postgres is the durable queue and operational state store, not the source of truth for page reconciliation.
- The Postgres schema is created with simple idempotent startup DDL.
- Startup DDL is limited to small internal-service schema setup such as `CREATE TABLE IF NOT EXISTS`.
- Job ordering uses stable scanner discovery order, represented by the inserted job sequence.
- A singleton Postgres advisory lock prevents multiple service instances from processing concurrently.
- A second service instance exits immediately if it cannot acquire the singleton lock.
- Stale `processing` jobs are marked `UPDATE_FAILED` after a configurable timeout.
- Failed jobs do not block later queued jobs.
- Terminal failed jobs are skipped by later scans, even if the original comment remains visible.
- Editing a failed source comment does not create a new job because the **Comment Identity** is unchanged.
- The **Worker** invokes the **Runner** with one **Prompt Envelope** on stdin.
- The **Runner** emits exactly one finalized **Response** JSON object on stdout.
- Runner logs and diagnostics go to stderr.
- A non-zero runner exit without a valid finalized **Response** maps to `UPDATE_FAILED`.
- The **Worker** enforces a configurable runner timeout, defaulting to 15 minutes.
- The **Prompt Envelope** includes both the stripped **Prompt** and the original comment text.
- The **Prompt Envelope** includes a hard constraint that only the attached **Target Page** may be processed.
- The **Runner** uses Wiki-Go helper commands directly for page and comment operations.
- An **Invocation** may execute zero or more tool calls.
- An **Invocation** finalizes with exactly one outcome.
- An **Invocation** accepts exactly one **Prompt**.
- An **Invocation** produces exactly one **Response**.
- A **Comment Event** starts one **Invocation** through its **Comment Job**.
- Each **Comment Event** has exactly one immutable **Comment Identity**.
- A successful page-update **Invocation** performs page update, **Update Confirmation**, **Comment Deletion**, and **Deletion Confirmation**.
- A successful rejection **Invocation** creates a **Rejection Comment**, performs **Replacement Confirmation**, performs **Comment Deletion**, and performs **Deletion Confirmation**.
- **Completion Order** is strict: **Primary Action** before **Comment Deletion**.
- If **Comment Deletion** fails after a confirmed page update or confirmed replacement comment, finalize as `DELETE_FAILED`.
- `DELETE_FAILED` is terminal and is logged rather than automatically retried.
- `UPDATE_FAILED` includes provider/model/tool failures, Wiki-Go read failures, save failures, and update confirmation failures before a confirmed successful update.
- `UPDATE_FAILED` is terminal and keeps the original source comment undeleted for human review.
- No automatic rollback is attempted after an update confirmation failure.
- If a duplicate is already complete, emit `ALREADY_PROCESSED`.
- `ALREADY_PROCESSED` is terminal and non-retryable.
- **Update Operation** is unrestricted because Wiki-Go history is the rollback mechanism.
- Unrestricted **Update Operation** applies only to the one **Target Page**.
- **Instruction Authority**: comment instruction wins unless it violates hard system constraints.
- **Conflict Policy**: read the latest **Target Page** content at invocation time and apply the update to that latest state.
- **Update Confirmation** requires re-fetching the page source after save.
- **Deletion Confirmation** requires listing or reading comments after delete and proving the source **Comment Identity** is absent.
- **Verification Window** is single-attempt only for update, replacement, and deletion confirmation.
- **Provenance Metadata** is not added to page content by default.
- Successful page updates are silent: the source comment is deleted and no success comment is created.
- **Rejection Comments** are authored by the configured bot identity.
- **Rejection Comments** include a `wiki-agent:` marker, the source comment id, a visible **Rejection Reason Code**, an exact blockquote of the original comment text, and a human-readable explanation.
- Long original comments in **Rejection Comments** are truncated with a clear note; the full original text remains in the job snapshot.
- The **Status Code Set** is: `SUCCESS`, `ALREADY_PROCESSED`, `REJECTED_WITH_COMMENT`, `UPDATE_FAILED`, `DELETE_FAILED`.
- The initial **Rejection Reason Code** set is: `UNCLEAR_REQUEST`, `MULTI_TARGET_REQUEST`, `CROSS_PAGE_REQUEST`, `FORBIDDEN_ACTION`, `UNSUPPORTED_ACTION`, `MISSING_CONTEXT`, `SAFETY_REFUSAL`.
- `REJECTED_WITH_COMMENT` covers all non-executable requests that are intentionally handled with a replacement comment.
- `MULTI_TARGET_REQUEST` is a rejection reason code, not a top-level status code.
- Missing target page from helper output is an operational integration error, not a normal domain status.
- Dry-run mode does not mutate Wiki-Go and does not write jobs to Postgres.
- Single-shot mode scans once, processes at most one job, and exits.
- The service exposes localhost-only health/status endpoints by default.
- Status endpoints expose counts and operational metadata, not prompts or comment text.
- Configuration uses a config file plus environment overrides.
- Secrets are handled by existing helper and keychain mechanisms, not stored in plain service config.

## Example Dialogue

> **Dev:** "If Marvin cannot understand a comment, does it leave the trigger comment in place?"
> **Domain expert:** "No. Marvin creates an explanatory replacement comment quoting the original, verifies that replacement, deletes the original trigger, verifies deletion, and finalizes with `REJECTED_WITH_COMMENT`."

> **Dev:** "If the model times out before any page update is confirmed, does the worker retry automatically?"
> **Domain expert:** "No. The job finalizes as terminal `UPDATE_FAILED`, the original comment remains visible, and later scans skip that same comment identity."

## Flagged Ambiguities

- None currently open.
