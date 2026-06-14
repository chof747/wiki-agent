# Main Branch Protection

Configure GitHub branch protection for `main` so that changes land through pull requests and cannot merge until the repo's required status check passes.

## Required settings

Enable **Require a pull request before merging**.

Enable **Require status checks to pass before merging** and mark `CI / pytest` as a required check.

That check is emitted by:

- workflow: `CI`
- job: `pytest`

## Recommended companion settings

These are recommended operator settings for `main`, but they are not part of the required baseline for this issue:

- Require branches to be up to date before merging.
- Require at least one approving review.
- Dismiss stale approvals when new commits are pushed.
- Block force pushes.
- Block branch deletion.

## Scope note

The current required status-check gate is intentionally limited to the repo's default fast baseline:

```bash
uv run pytest
```

Harness-backed Wiki-Go and Postgres integration coverage remains a future follow-up and is not part of the required `main` merge gate yet.
