# Implementation Start

Use this guide when the user says `implement issue <n>`, wants work to start on a `ready-for-agent` issue, or wants to continue issue-scoped work.

The rules in this guide are normative. `must`, `must not`, and `stop here` are literal requirements.

## Mandatory Domain Pass

Before branch creation or coding, the implementer must:

1. Read [CONTEXT.md](../../CONTEXT.md).
2. Read the ADRs that affect the area being changed.
3. Stop for HIL if the requested change conflicts with `CONTEXT.md` or an accepted ADR.
4. Route through `grill-with-docs` if the issue uses fuzzy language, changes domain language, changes architecture, or changes an external contract.

For core runtime work in this repo, the minimum expected architecture read is [ADR 0002](../adr/0002-scheduled-comment-agent-with-durable-jobs.md).

## Clean Start Rule

Before creating a new implementation branch, the implementer must:

1. Start from a clean working tree.
2. Start from a clean control checkout.
3. Stop and ask if unrelated local changes exist.

The only exception is when the user explicitly asks to continue existing in-progress work on an existing branch or draft PR.

## `implement issue <n>` Path

1. Confirm the issue is open and labeled `ready-for-agent`.
2. From the clean control checkout, run the repo helper:

```bash
uv run wiki-agent-worktree create <issue-number>
uv run wiki-agent-worktree create <issue-number> --base release/<release-name>
```

3. Use the worktree and branch created by the helper.
4. Do not manually recreate helper behavior with `git worktree`, ad hoc branch naming, or manual environment copying.
5. If the helper fails or reveals an ambiguity about the start path, stop here and ask for HIL instead of inventing a fallback flow.
6. After the branch is created, leave an issue comment naming the branch and stating that implementation has started.

Operator setup and helper behavior are documented in [Issue Worktree Workflow](../operators/worktree-workflow.md).

## Branch Rules

1. The implementation branch name is decided once, at branch creation time, from the issue labels as they exist at that moment.
2. If the issue has a `bug` label, the helper creates `bug/<issue-number>-<short-slug>`.
3. Otherwise the helper creates `feat/<issue-number>-<short-slug>`.
4. If multiple labels are present and one of them is `bug`, `bug` wins.
5. The branch prefix must not be renamed later if the issue is relabeled.
6. These repo-specific branch prefixes override generic agent defaults such as `codex/` for work in this repository.
7. The issue title is the default source of truth for the branch slug. Normalize for clarity, but do not change scope or meaning.

## Pre-Code HIL Gate

Implementation may start immediately on a `ready-for-agent` issue unless one of the following is true:

1. The change updates domain language in `CONTEXT.md`.
2. The change requires a new ADR or revises an existing ADR.
3. The change introduces or revises a public CLI, config, or runtime contract.
4. The change widens scope beyond the issue acceptance criteria.

If any of those are true, stop for HIL before coding.
