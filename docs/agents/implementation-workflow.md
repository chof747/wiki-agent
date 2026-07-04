# Implementation Workflow

This document is the canonical router for repo changes.

It applies to both humans and agents. The rules in this workflow are normative. `must`, `must not`, and `stop here` are literal requirements.

## Core Rules

1. Every non-trivial code change must start from a GitHub issue.
2. No implementation branch may be created until the issue is labeled `ready-for-agent`.
3. One issue maps to one branch, one draft PR, and one primary outcome.
4. The agent must stop for human-in-the-loop (HIL) review at the checkpoints defined by this workflow.
5. The agent must not commit, push, or open a PR before explicit HIL approval.
6. The agent must use the repo glossary in `CONTEXT.md` and must not silently contradict accepted ADRs.

## If/Then Router

If the user asks to create or refine one concrete task, go to [implementation-intake.md](./implementation-intake.md).

If the user asks to break down a medium plan into implementation slices, go to [implementation-intake.md](./implementation-intake.md) and use `to-issues`.

If the user asks for a broad or ambiguous initiative, go to [implementation-intake.md](./implementation-intake.md) and use `to-prd` before `to-issues`.

If the user says `implement issue <n>`, wants implementation to start on a `ready-for-agent` issue, or wants to continue issue-scoped work, go to [implementation-start.md](./implementation-start.md).

If implementation is already underway and the task is to write or change repo code or docs on the issue branch, go to [implementation-code.md](./implementation-code.md).

If the user asks to run tests, verify acceptance criteria, or prepare the HIL review packet, go to [implementation-verify.md](./implementation-verify.md).

If the user asks to commit, push, or open the draft PR after approval, go to [implementation-publish.md](./implementation-publish.md).

If CI is failing on the draft PR, stay on the same branch and go to [implementation-publish.md](./implementation-publish.md).

If the user asks to address PR review feedback that preserves the issue's primary outcome, stay on the same branch and go to [implementation-publish.md](./implementation-publish.md).

## Skill Order

Use this default order unless a linked guide says to stop earlier:

1. `grill-with-docs` only when the issue is underspecified or changes domain language, architecture, or an external contract.
2. `triage` when labels, readiness, or acceptance criteria are not yet correct.
3. Start the issue-scoped worktree after the issue is `ready-for-agent`.
4. `diagnose` first for bug work.
5. `tdd` for behavior-changing implementation.
6. Local verification.
7. HIL review on the branch.
8. `github:yeet` after approval for commit, push, and draft PR creation.
9. `github:gh-fix-ci` only if CI fails.
10. `github:gh-address-comments` only when addressing PR review feedback.
