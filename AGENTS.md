## Agent skills

### Issue tracker

Issues are tracked in this repo's GitHub Issues and managed via `gh`. See `docs/agents/issue-tracker.md`.

Repo-specific convention: use the `epic` label for parent planning issues that group multiple implementation issues.

- `/to-prd`: when publishing a PRD as a GitHub issue intended to act as the parent container for follow-on work, apply `epic` in addition to the normal triage label.
- `/to-issues`: when the source issue has the `epic` label, treat it as the parent epic for the generated slice issues. Create the child issues under that parent, but do not apply `epic` to the child issues unless explicitly requested.

### Triage labels

Canonical triage roles map directly to same-name labels (`needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`). See `docs/agents/triage-labels.md`.

### Domain docs

This repo is single-context: read root `CONTEXT.md` and root `docs/adr/`. See `docs/agents/domain.md`.

### Strategic programming

For any repo change, apply the principles and follow `docs/agents/strategic-programming.md`.

### Implementation workflow

For any repo change, follow `docs/agents/implementation-workflow.md`.
