# Wiki Agent CLI

This context defines the domain language for a single-run agent CLI that executes prompts, tools, and provider calls with deterministic completion.

## Language

**Invocation**:
One command execution from input parsing to exactly one finalized outcome.
_Avoid_: run, session

**Prompt**:
The single user instruction accepted by an **Invocation**.
_Avoid_: turn, chat message

**Response**:
The single status report produced when an **Invocation** finalizes.
_Avoid_: conversation, dialogue

**Primary Action**:
The domain work an **Invocation** performs before finalization.
_Avoid_: response

**Comment Deletion**:
The act of removing the source comment after successful **Primary Action** completion.
_Avoid_: archive, hide

**Completion Order**:
The required sequence of domain steps within a successful **Invocation**.
_Avoid_: best-effort ordering

**Reconciliation**:
The duplicate-handling behavior that verifies prior **Primary Action** state and completes pending **Comment Deletion**.
_Avoid_: blind replay

**Target Page**:
The single wiki page selected for update by an explicit identifier in the **Prompt Envelope**.
_Avoid_: fuzzy match, best guess

**Update Operation**:
Any wiki page modification requested for a **Target Page**, including full-page overwrite.
_Avoid_: restricted operation set

**Single-Target Scope**:
The rule that one **Comment Event** may affect exactly one **Target Page**.
_Avoid_: multi-page change set

**Instruction Authority**:
The precedence rule for conflicting guidance during page updates.
_Avoid_: implicit convention override

**Input Validation**:
The pre-execution checks that must pass before any **Update Operation** is attempted.
_Avoid_: best-effort parsing

**Status Code**:
A stable machine-readable outcome code for a finalized **Invocation**.
_Avoid_: free-text-only errors

**Conflict Policy**:
The rule for handling a **Target Page** that changed before update execution.
_Avoid_: precondition lock

**Status Code Set**:
The minimal stable list of allowed **Status Code** values.
_Avoid_: ad-hoc statuses

**Success Criteria**:
The required conditions for a finalized **Invocation** to be classified as success.
_Avoid_: partial completion

**Already Processed**:
The terminal outcome for a duplicate **Comment Event** that has already been completed.
_Avoid_: duplicate success

**Deletion Confirmation**:
The verification step that proves a source comment is no longer retrievable after deletion.
_Avoid_: optimistic delete acknowledgment

**Verification Window**:
The maximum time and attempts allowed for post-action confirmation checks.
_Avoid_: delayed polling

**Update Confirmation**:
The verification step that proves the requested **Update Operation** is committed on the **Target Page**.
_Avoid_: assumed write success

**Provenance Metadata**:
Optional linkage data from a wiki change back to the triggering **Comment Identity**.
_Avoid_: mandatory trace annotation

**Stateless Reconciliation**:
Duplicate handling that uses live source and page state only, without persisted trace records.
_Avoid_: reconciliation store, audit ledger

**Prompt Envelope**:
The structured payload that carries a **Prompt** with source metadata.
_Avoid_: raw comment text, unstructured input

**Comment Event**:
A website comment trigger that starts an **Invocation**.
_Avoid_: chat turn, session event

**Comment Identity**:
The immutable unique identifier of a **Comment Event** from its source system.
_Avoid_: mutable key, derived hash

**Idempotency Key**:
The deduplication key used to ensure a **Comment Event** is processed at most once.
_Avoid_: request id, retry token

**Delivery Semantics**:
The guarantee level of incoming **Comment Event** delivery from the source.
_Avoid_: exactly once (by assumption)

## Relationships

- An **Invocation** may execute zero or more tool calls
- An **Invocation** finalizes with exactly one outcome
- An **Invocation** accepts exactly one **Prompt**
- An **Invocation** produces exactly one **Response**
- A **Comment Event** starts one **Invocation**
- A **Prompt Envelope** contains one **Prompt** plus source metadata
- Each **Comment Event** has exactly one immutable **Comment Identity**
- The **Idempotency Key** is `source_system + comment_identity`
- **Comment Event** delivery is treated as at-least-once
- A successful **Invocation** performs **Primary Action** then **Comment Deletion**
- A duplicate **Comment Event** must not repeat **Primary Action**
- The **Completion Order** is strict: **Primary Action** before **Comment Deletion**
- If **Comment Deletion** fails after successful **Primary Action**, retries perform **Reconciliation** and attempt deletion only
- Each **Invocation** resolves to exactly one **Target Page** using an explicit identifier
- **Update Operation** is unrestricted because wiki history is the rollback mechanism
- **Single-Target Scope** is enforced; multi-page requests are rejected
- Unrestricted **Update Operation** applies only to the one **Target Page**
- **Instruction Authority**: comment instruction wins unless it violates hard system constraints
- **Input Validation** fails fast when the explicit **Target Page** identifier is missing
- Every finalized **Invocation** emits one stable **Status Code** plus human-readable status text
- **Success Criteria** require both a committed wiki update and confirmed **Comment Deletion**
- **Already Processed** is emitted as `ALREADY_PROCESSED` for completed duplicates
- `ALREADY_PROCESSED` is terminal and non-retryable
- If a duplicate arrives with page already updated but comment not deleted, perform **Reconciliation** and retry deletion only
- **Deletion Confirmation** requires a read-after-delete check for the same **Comment Identity**
- **Verification Window** for deletion is single-attempt only; if confirmation fails once, emit `DELETE_FAILED`
- **Update Confirmation** is single-attempt only; if confirmation fails once, emit `UPDATE_FAILED`
- **Provenance Metadata** is not required on wiki updates
- No traceability store is required; reconciliation is **Stateless Reconciliation**
- If update is already applied and comment still exists, delete the comment
- Duplicate detection of "already applied" uses semantic success signals, not byte-for-byte page equality
- If a **Target Page** changed before execution, apply the update to latest page state
- Validation failures keep the source comment undeleted for human correction
- **Status Code Set** is: `SUCCESS`, `ALREADY_PROCESSED`, `MISSING_TARGET_ID`, `MULTI_TARGET_REQUEST`, `UPDATE_FAILED`, `DELETE_FAILED`

## Example dialogue

> **Dev:** "If a tool call times out, does this **Invocation** retry automatically?"
> **Domain expert:** "No. This **Invocation** fails deterministically and finalizes once."

## Flagged ambiguities

- "session" was used for single-command behavior — resolved: use **Invocation** for the current scope.
