# Issue Worktree Workflow

Use `wiki-agent-worktree` to create and remove issue-scoped implementation worktrees for this repo.

This guide covers local setup and command behavior. For the policy that requires issue-scoped worktrees, see the [implementation workflow](../agents/implementation-workflow.md).

## 1. One-time setup

Install the repo-local Git hooks path once per clone:

```bash
git config core.hooksPath .githooks
```

That enables the repo-owned `pre-commit` hook that blocks direct commits on `main`.

## 2. Create an issue worktree

Run the command from the control checkout on a clean, up-to-date `main`:

```bash
wiki-agent-worktree create <issue-number>
```

The helper:

- requires the GitHub issue to be open and labeled `ready-for-agent`
- derives `bug/<issue-number>-<slug>` when the issue has a `bug` label, otherwise `feat/<issue-number>-<slug>`
- creates the worktree under `../wiki-agent-worktrees/wiki-agent-<issue-number>`
- copies local `.env`, `.runtime/`, and `.vscode/` state when present
- runs `uv sync --locked --dev` in the new worktree
- runs `env UV_CACHE_DIR=/private/tmp/uv-cache uv run wiki-agent-integration reset`
- runs `env UV_CACHE_DIR=/private/tmp/uv-cache uv run wiki-agent-integration down`

After the command finishes, the new worktree is ready for implementation work.

## 3. Local state that follows the worktree

The copied paths are intentionally local-only state:

- `.env`
- `.runtime/`
- `.vscode/`

They stay ignored by Git, so they do not count as meaningful dirty state during later cleanup checks.

## 4. Remove an issue worktree

After the branch has a pull request and the worktree is clean, remove the worktree directory with:

```bash
wiki-agent-worktree delete <issue-number>
```

The helper:

- resolves the worktree by `../wiki-agent-worktrees/wiki-agent-<issue-number>`
- hard-stops if the worktree has meaningful dirty state
- verifies a pull request exists for the issue branch
- runs best-effort `uv run wiki-agent-integration down` inside the worktree
- removes only the worktree directory and leaves the branch intact

If the cleanup command stops, either finish publishing the branch or clean the worktree before retrying.
