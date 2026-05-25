# Main Branch Protection

This repo's required merge gate for `main` is the GitHub Actions status check `CI / pytest`.

Configure GitHub branch protection for `main` so that pull requests cannot merge until that check passes.

## Required setting

Enable **Require status checks to pass before merging** and mark `CI / pytest` as a required check.

That check is emitted by:

- workflow: `CI`
- job: `pytest`

## Recommended companion settings

These are recommended operator settings for `main`, but they are not the mandatory requirement for this issue:

- Require a pull request before merging.
- Require branches to be up to date before merging.
- Require at least one approving review.
- Dismiss stale approvals when new commits are pushed.
- Block force pushes.
- Block branch deletion.

## Scope note

The current required gate is intentionally limited to the repo's default fast baseline:

```bash
uv run pytest
```

Harness-backed Wiki-Go and Postgres integration coverage remains a future follow-up and is not part of the required `main` merge gate yet.
