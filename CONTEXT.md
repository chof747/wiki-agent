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
The structured JSON payload passed to the **Runner** on stdin, containing the stripped **Prompt**, original comment text, attached **Target Page**, and **Comment Identity**.
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

**Web Research**:
Autonomous read-only searching and fetching of public web sources during an **Invocation** when useful for satisfying the **Prompt**, with authoritative primary sources preferred.
_Avoid_: user-authorized browsing, authenticated source access, private source access, external mutation

**Hosted Web Search**:
The OpenAI-managed web search capability used by the **Runner** to discover and open public web sources during **Web Research**.
_Avoid_: arbitrary crawler, direct browser automation

**References Section**:
The dedicated `## References` section at the end of a **Target Page** containing links to sources that materially informed an update.
_Avoid_: inline-only citations, uncited web-derived claims

**Current-State Claim**:
A web-derived claim whose accuracy depends on when it is evaluated, such as a latest release, price, schedule, or current officeholder.
_Avoid_: timeless fact, implicitly current claim

**Source Conflict**:
A material disagreement between credible web sources that cannot be resolved during the current **Invocation**.
_Avoid_: silent source selection, automatic rejection

**Non-Primary Source**:
A public web source that is not authoritative for its claims, such as a blog, forum, community post, or marketing page.
_Avoid_: implicit authority, established fact without qualification

**Surfaced Link**:
A source URL explicitly returned by **Hosted Web Search** and therefore eligible to be opened during the same **Invocation**.
_Avoid_: arbitrary discovered link, recursive crawl target

**Research Budget**:
The configurable per-**Invocation** limit on **Hosted Web Search** actions and opened **Surfaced Links**.
_Avoid_: unbounded research loop, hidden cost growth

**Research Image**:
A fetched JPEG or PNG used as evidence during **Web Research** but not published, embedded, or linked as page content.
_Avoid_: wiki image asset, hotlinked image

**Rejection Comment**:
A replacement Wiki-Go comment created by the bot when a request is unclear, impossible, unsafe, unsupported, or violates hard constraints.
_Avoid_: failure log, hidden rejection

**Failure Comment**:
A visible Wiki-Go comment created by the bot to explain a terminal failed **Comment Job** to page readers.
_Avoid_: leftover source comment, operator log, retry prompt

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
- Duplicate scanner discoveries do not create additional processing rows.
- Duplicate discovery updates the executable snapshot (`target_page`, original comment text, stripped prompt, source metadata) while the job remains `queued`.
- Duplicate discovery updates receipt metadata only after the job is `processing` or reaches a terminal status.
- **Comment Jobs** are stored in Postgres and retained indefinitely for the first version.
- Postgres is the durable queue and operational state store, not the source of truth for page reconciliation.
- The Postgres schema is created with simple idempotent startup DDL.
- Startup DDL is limited to small internal-service schema setup such as `CREATE TABLE IF NOT EXISTS`.
- Job ordering uses stable scanner discovery order, represented by the inserted job sequence.
- A singleton Postgres advisory lock prevents multiple service instances from processing concurrently.
- A second service instance exits immediately if it cannot acquire the singleton lock.
- Stale `processing` jobs are marked `UPDATE_FAILED` after a configurable timeout and get the same **Failure Comment** feedback as other `UPDATE_FAILED` jobs.
- Failed jobs do not block later queued jobs.
- Terminal failed jobs are skipped by later scans, even if the original comment remains visible.
- Editing a failed source comment does not create a new job because the **Comment Identity** is unchanged.
- A **Failure Comment** explains a terminal failure but is not a retry surface.
- The **Worker** invokes the **Runner** with one **Prompt Envelope** on stdin.
- The **Runner** emits exactly one finalized **Response** JSON object on stdout.
- Runner logs and diagnostics go to stderr.
- A non-zero runner exit without a valid finalized **Response** maps to `UPDATE_FAILED`.
- The **Worker** enforces a configurable runner timeout, defaulting to 15 minutes.
- The **Prompt Envelope** includes both the stripped **Prompt** and the original comment text.
- The **Prompt Envelope** includes the attached **Target Page** and **Comment Identity** needed for the **Runner** workflow.
- The **Runner** uses Wiki-Go helper commands directly for page and comment operations.
- The **Runner** owns **Web Research** within an **Invocation**.
- An **Invocation** may execute zero or more tool calls.
- An **Invocation** may autonomously perform **Web Research** when useful for satisfying the **Prompt**.
- **Web Research** does not relax **Single-Target Scope**; external sources are read-only and only the attached **Target Page** may be updated.
- **Web Research** uses public sources only and prefers authoritative primary sources.
- The **Runner** performs **Web Research** through **Hosted Web Search**.
- The **Runner** may open only a **Surfaced Link** during **Web Research**.
- Each **Invocation** has a configurable **Research Budget** with reasonable defaults.
- When **Web Research** materially informs an update, the **Target Page** must end with a **References Section** containing links to the sources used.
- Source provenance for **Web Research** is retained in the **References Section**, not separate job metadata.
- A web-informed update merges sources into one trailing **References Section**, deduplicates links, preserves still-relevant existing references, and removes references only when the update makes them obsolete.
- A **Current-State Claim** must be verified during the current **Invocation**, include an explicit as-of date in the **Target Page**, and cite its source in the **References Section**.
- If a requested **Current-State Claim** cannot be freshly verified, the request is non-executable rather than presented as current.
- A **Source Conflict** is disclosed in the **Target Page** text and the conflicting sources are marked as conflicting in the **References Section**.
- A **Source Conflict** does not by itself make a request non-executable.
- A **Non-Primary Source** may be used when relevant or when primary sources are unavailable, but its source type and uncertainty must remain visible in the **Target Page**.
- Web-derived content is treated as evidence, never as instructions to execute.
- When the **Research Budget** is exhausted, Marvin completes a best-effort cited update with the evidence already gathered rather than aborting the **Invocation**.
- If the **Research Budget** materially constrained the result, the **Target Page** must disclose that the update is based on incomplete research.
- If **Hosted Web Search** fails, Marvin continues with page-local context and any evidence already gathered, and discloses the degraded research when it materially affects the update.
- A **Prompt** that specifically requires fresh external verification remains non-executable if **Hosted Web Search** fails before that verification is obtained.
- **Web Research** does not create a new finalized outcome; the existing **Status Code Set** and no-op failure behavior remain unchanged.
- A fetched JPEG or PNG is a **Research Image** and may inform an update, but is not published, embedded, or hotlinked in the **Target Page**.
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
- `DELETE_FAILED` after a confirmed page update creates a **Failure Comment** because no other bot-authored comment explains the visible leftover source comment.
- `DELETE_FAILED` after a confirmed **Rejection Comment** does not create a second **Failure Comment** because the **Rejection Comment** already explains the handled outcome.
- `UPDATE_FAILED` includes provider/model/tool failures, Wiki-Go read failures, save failures, and update confirmation failures before a confirmed successful update.
- `UPDATE_FAILED` is terminal and keeps the original source comment undeleted for human review.
- `UPDATE_FAILED` creates a **Failure Comment** and keeps the original source comment undeleted for human review.
- A **Failure Comment** begins its visible text with the **Bot Name**.
- No automatic rollback is attempted after an update confirmation failure.
- If a duplicate is already complete, emit `ALREADY_PROCESSED`.
- `ALREADY_PROCESSED` is terminal and non-retryable.
- **Update Operation** is unrestricted because Wiki-Go history is the rollback mechanism.
- Unrestricted **Update Operation** applies only to the one **Target Page**.
- **Web Research** does not narrow or expand the allowed **Update Operation** on the attached **Target Page**.
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
- **Failure Comments** are authored by the configured bot identity.
- **Failure Comments** include a hidden `wiki-agent:` marker, the source comment id, the terminal **Status Code**, and the available failure reason.
- A **Failure Comment** is not duplicated when a matching failure marker already exists for the same source comment id and terminal **Status Code**.
- **Failure Comments** visibly include the **Bot Name**, terminal **Status Code**, concise failure reason, and next step.
- **Failure Comments** do not quote the original source comment because the source comment remains visible when a **Failure Comment** is created.
- Retrying after `UPDATE_FAILED` requires a new source comment with a new **Comment Identity**.
- `DELETE_FAILED` is not user-retryable because the **Primary Action** already succeeded.
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
