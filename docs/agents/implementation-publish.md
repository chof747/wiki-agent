# Implementation Publish

Use this guide after HIL approval for publishing, and also for same-branch CI fixes or same-branch PR review follow-up.

The rules in this guide are normative. `must`, `must not`, and `stop here` are literal requirements.

## Issue Breadcrumbs

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

## Publish Phase

After explicit HIL approval, the agent should handle the Git work end-to-end.

1. Stage intentionally.
2. Create a focused commit.
3. Push the branch.
4. Open a draft PR.
5. Use `github:yeet` for the publish phase.

The workflow must not publish a ready PR by default.

## Naming Rules

1. Branch slug derives from the issue title.
2. Commit subject derives from the issue title.
3. Use `Fix #<n>: <normalized issue title>` for `bug/` branches.
4. Use `Implement #<n>: <normalized issue title>` for `feat/` branches.
5. PR title derives from the issue title.

The draft PR body should use a non-closing reference such as `Refs #<n>`.

Do not use `Closes`, `Fixes`, or `Resolves` by default in draft PRs.

## Draft PR Stabilization

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

## Same-Branch Follow-Up Rule

Once the draft PR exists, all scope-preserving follow-up work must stay on the same branch and same PR.

This includes:

1. Review fixes.
2. CI fixes.
3. Small completion work that does not change the primary outcome.

Only open a new issue, branch, or PR if the requested follow-up is a real scope expansion.

If the primary outcome changes, stop and split.
