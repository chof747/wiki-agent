# Implementation Workflow

This document defines the default implementation workflow for this repo.

It applies to both humans and agents. Agent-specific behavior is called out explicitly where needed.

The rules in this document are normative. `must`, `must not`, and `stop here` are literal requirements.

## 1. Core Rules

1. Every non-trivial code change must start from a GitHub issue.
2. No implementation branch may be created until the issue is labeled `ready-for-agent`.
3. One issue maps to one branch, one draft PR, and one primary outcome.
4. The agent must stop for human-in-the-loop (HIL) review at the checkpoints defined below.
5. The agent must not commit, push, or open a PR before explicit HIL approval.
6. The agent must use the repo glossary in `CONTEXT.md` and must not silently contradict accepted ADRs.

## 2. Intake

### 2.1 Default Intake Path

1. If the request is a small, concrete implementation task, create or refine one GitHub issue.
2. If the request is a medium-sized plan that obviously breaks into multiple independently shippable slices, use `to-issues`.
3. If the request is a broad or ambiguous initiative, use `to-prd` first, then `to-issues`, then triage the resulting issues.
4. The agent may create the GitHub issue for a direct chat request, but must stop before implementation until a human approves scope and the issue reaches `ready-for-agent`.

### 2.2 Narrow Exception

The only exception to issue-first work is a trivial docs-only or instructions-only change.

This exception does not apply to production code, runtime behavior, architecture, or any change that needs a branch/PR audit trail.

If a supposedly trivial request expands beyond a docs/instructions edit, stop and create an issue.

## 3. Issue Readiness Gate

An issue must not be implemented until it satisfies all of the following:

1. It has exactly one primary outcome.
2. It states the user-visible or operator-visible behavior change.
3. It names the relevant code area or subsystem when known.
4. It defines acceptance criteria that can be verified locally.
5. Its scope is small enough to land on one branch without becoming a grab-bag.
6. It has the correct triage label and no unresolved blocking questions.

Only a human may give the final approval that moves an issue into `ready-for-agent`.

The agent may analyze the issue, refine the wording, propose labels, and suggest acceptance criteria, but must not self-promote the issue into `ready-for-agent`.

## 4. Label Meanings

The workflow must treat triage labels as follows:

| Label | Meaning | Agent action |
| --- | --- | --- |
| `needs-triage` | Not ready for implementation | Analyze, refine, propose next steps, do not branch |
| `needs-info` | Missing required clarification | Stop and request clarification |
| `ready-for-agent` | Approved for implementation | Branching and implementation may start |
| `ready-for-human` | Requires human implementation or decision | Stop unless explicitly asked for non-implementation support |
| `wontfix` | Will not be actioned | Stop |

`ready-for-agent` means approved to implement. It does not mean idle, unclaimed, or unstarted.

The workflow must not invent an `in-progress` label. Execution state is tracked through comments and the draft PR.

## 5. Mandatory Domain Pass

Before branch creation or coding, the implementer must:

1. Read [CONTEXT.md](../../CONTEXT.md).
2. Read the ADRs that affect the area being changed.
3. Stop for HIL if the requested change conflicts with `CONTEXT.md` or an accepted ADR.
4. Route through `grill-with-docs` if the issue uses fuzzy language, changes domain language, changes architecture, or changes an external contract.

For core runtime work in this repo, the minimum expected architecture read is [ADR 0002](../adr/0002-scheduled-comment-agent-with-durable-jobs.md).

## 6. Clean Start Rule

Before creating a new implementation branch, the implementer must:

1. Start from a clean working tree.
2. Start from the latest `main`.
3. Stop and ask if unrelated local changes exist.

The only exception is when the user explicitly asks to continue existing in-progress work on an existing branch or draft PR.

Typical commands:

```bash
git status --short
git switch main
git pull --ff-only origin main
```

## 7. Branch Creation

The implementation branch name is decided once, at branch creation time, from the issue labels as they exist at that moment.

Branch prefix rules:

1. If the issue has a `bug` label, create `bug/<issue-number>-<short-slug>`.
2. Otherwise create `feat/<issue-number>-<short-slug>`.
3. If multiple labels are present and one of them is `bug`, `bug` wins.
4. The branch prefix must not be renamed later if the issue is relabeled.

Examples:

```bash
git switch -c feat/12-implement-scanner-enqueueing
git switch -c bug/34-fix-worker-timeout-handling
```

The issue title is the default source of truth for the branch slug. Normalize for clarity, but do not change scope or meaning.

Once the branch is created, the agent must leave an issue comment naming the branch and stating that implementation has started.

## 8. Pre-Code HIL Gate

Implementation may start immediately on a `ready-for-agent` issue unless one of the following is true:

1. The change updates domain language in `CONTEXT.md`.
2. The change requires a new ADR or revises an existing ADR.
3. The change introduces or revises a public CLI, config, or runtime contract.
4. The change widens scope beyond the issue acceptance criteria.

If any of those are true, stop for HIL before coding.

## 9. Skill Order

This repo uses one canonical workflow with conditional branches.

### 9.1 Default Skill Order

1. `grill-with-docs` only when the issue is underspecified or changes domain language, architecture, or external contract.
2. `triage` when labels, readiness, or acceptance criteria are not yet correct.
3. Branch creation after the issue is `ready-for-agent`.
4. `diagnose` first for bug work.
5. `tdd` for behavior-changing implementation.
6. Local verification.
7. HIL review on the branch.
8. `github:yeet` after approval for commit, push, and draft PR creation.
9. `github:gh-fix-ci` only if CI fails.
10. `github:gh-address-comments` only when addressing PR review feedback.

### 9.2 Skill Selection by Situation

| Situation | Required path |
| --- | --- |
| Broad initiative | `to-prd` -> `to-issues` -> `triage` |
| Medium scoped plan with clear slices | `to-issues` -> `triage` |
| Underspecified issue | `triage` and possibly `grill-with-docs` |
| Bug | `diagnose` -> `tdd` |
| Behavior-changing feature | `tdd` |
| Docs-only or no-behavior refactor | direct implementation, tests only if risk justifies them |
| PR review follow-up | `github:gh-address-comments` |
| Failing CI on the draft PR | `github:gh-fix-ci` |

## 10. Implementation Rules

1. Use `tdd` by default for behavior-changing work.
2. For bug work, reproduce and minimize the problem with `diagnose` before switching into `tdd`.
3. Direct implementation is allowed for docs-only work, comment-only work, scaffolding, and no-behavior refactors.
4. If the codebase lacks a reasonable test seam for the requested behavior change, stop and ask whether creating that seam is in scope.
5. If implementation reveals more than one independently shippable outcome, stop and split scope.

If scope must split:

1. Comment on the issue with the discovered split.
2. Create or propose follow-up issues.
3. Keep the current branch focused on the smallest valuable slice, or abandon it if the issue was wrong at its core.

## 11. Documentation Rules During Implementation

Documentation is part of implementation, not cleanup.

1. If behavior changes, update the relevant user-facing or operator-facing docs in the same branch.
2. If domain language changes, update `CONTEXT.md` before or during implementation.
3. If the change introduces a hard-to-reverse, surprising architectural trade-off, stop for HIL and then add or update an ADR in `docs/adr/`.
4. If no docs changed, the HIL review packet must explicitly state why no doc updates were needed.

## 12. Local Verification Baseline

The workflow must describe the verification baseline honestly, as the repo exists today.

The current default baseline is:

```bash
uv run pytest
```

Additional rules:

1. If CLI behavior changes, run a CLI smoke check relevant to the changed command path.
2. Add any issue-specific verification required by the acceptance criteria.
3. If a required check cannot be run locally, the implementer must say so explicitly in the HIL review packet.
4. When the repo later adds standard lint, format, or static-analysis checks, update this document to make them part of the baseline.

## 13. Issue Breadcrumbs

The agent must leave issue comments only at state transitions.

Required transition comments:

1. Implementation started, including the branch name.
2. Work stopped because the issue needs info, needs scope split, or needs HIL/design review.
3. Draft PR opened.

The issue must not be spammed with every local step, test run, or partial thought.

Use labels for triage state. Use comments for execution breadcrumbs.

Useful issue commands:

```bash
gh issue view <number> --comments
gh issue comment <number> --body "Starting implementation on feat/<number>-<slug>."
```

## 14. Post-Implementation HIL Checkpoint

After local verification is complete and before any commit, push, or PR, stop for HIL review.

The review packet must include all of the following:

1. Branch name and linked issue number.
2. Brief summary of the implemented change.
3. Acceptance criteria checklist with pass/fail status.
4. Exact local verification performed.
5. Known risks, gaps, or items not verified.
6. Whether docs, `CONTEXT.md`, or ADRs changed, or why they did not.

Chat approval is authoritative. The approval does not need to be duplicated into GitHub before work resumes.

After approval, the agent should add the appropriate issue or PR breadcrumb as part of continuing the workflow.

## 15. Publish Phase

After explicit HIL approval, the agent should handle the Git work end-to-end.

Required publication rules:

1. Stage intentionally.
2. Create a focused commit.
3. Push the branch.
4. Open a draft PR.
5. Use `github:yeet` for the publish phase.

The workflow must not publish a ready PR by default.

Default naming rules:

1. Branch slug derives from the issue title.
2. Commit subject derives from the issue title.
3. Use `Fix #<n>: <normalized issue title>` for `bug/` branches.
4. Use `Implement #<n>: <normalized issue title>` for `feat/` branches.
5. PR title derives from the issue title.

The draft PR body should use a non-closing reference such as `Refs #<n>`.

Do not use `Closes`, `Fixes`, or `Resolves` by default in draft PRs.

## 16. Draft PR Stabilization

The implementation workflow ends when the draft PR exists and is stable.

This includes:

1. Commit created.
2. Branch pushed.
3. Draft PR opened.
4. Immediate CI issues addressed.
5. Scope-preserving review feedback applied on the same branch.

This workflow does not include:

1. Marking the PR ready for review.
2. Merging.
3. Post-merge cleanup.

Those remain explicit human decisions unless a separate workflow is defined.

## 17. Same-Branch Follow-Up Rule

Once the draft PR exists, all scope-preserving follow-up work must stay on the same branch and same PR.

This includes:

1. Review fixes.
2. CI fixes.
3. Small completion work that does not change the primary outcome.

Only open a new issue, branch, or PR if the requested follow-up is a real scope expansion.

If the primary outcome changes, stop and split.
