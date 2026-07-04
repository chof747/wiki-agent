# Implementation Verify

Use this guide when implementation is complete enough to verify locally and prepare the HIL review packet.

The rules in this guide are normative. `must`, `must not`, and `stop here` are literal requirements.

## Local Verification Baseline

The workflow must describe the verification baseline honestly, as the repo exists today.

The current default baseline is:

```bash
uv run pytest
```

The final local verification pass must also run with the local Postgres dev instance enabled so coverage includes the non-dry-run CLI smoke path gated by `WIKI_AGENT_TEST_POSTGRES_DSN`, for example:

```bash
WIKI_AGENT_TEST_POSTGRES_DSN=postgresql://wiki_agent:wiki_agent@localhost:5432/wiki_agent uv run pytest
```

That baseline is also the current GitHub Actions merge gate for `main` through the required status check `CI / pytest`.

## Additional Verification Rules

1. If CLI behavior changes, run a CLI smoke check relevant to the changed command path.
2. Before stopping for HIL, rerun the test suite with `WIKI_AGENT_TEST_POSTGRES_DSN` pointed at the local dev Postgres instance and report that command exactly in the review packet.
3. If the issue touches a runtime boundary covered or intended to be covered by the repo-owned integration harness, include the harness-managed verification command in the final verification set unless the issue documents why that is not yet possible.
4. Add any issue-specific verification required by the acceptance criteria.
5. If a required check cannot be run locally, the implementer must say so explicitly in the HIL review packet.
6. When the repo later adds standard lint, format, or static-analysis checks, update this document to make them part of the baseline.
7. If an issue exercises a repo-owned integration harness, prefer extending and invoking that harness rather than adding a separate integration command path.
8. Harness-backed Wiki-Go and Postgres integration coverage remains a future follow-up and is not part of the required `CI / pytest` gate yet.
9. `config.example.toml` is a placeholder example, not a working harness QA config; harness-backed local verification must use the generated `.runtime/integration-harness/wiki-agent.integration.toml` after `wiki-agent-integration reset`.
10. When local Postgres is not reachable through the repo fallback DSNs, set `WIKI_AGENT_INTEGRATION_ADMIN_DSN` and `WIKI_AGENT_INTEGRATION_RUNTIME_DSN`, or `WIKI_AGENT_POSTGRES_DSN` when one DSN is correct for both, before running harness commands.
11. For harness-backed manual QA, use `wiki-agent-integration run-once`, `wiki-agent-integration seed-comment`, or the thin wrapper scripts instead of reconstructing the harness environment in the shell.

## Post-Implementation HIL Checkpoint

After local verification is complete and before any commit, push, or PR, stop for HIL review.

The review packet must include all of the following:

1. Branch name and linked issue number.
2. Brief summary of the implemented change.
3. Acceptance criteria checklist with pass/fail status.
4. Exact local verification performed.
5. Known risks, gaps, or items not verified.
6. Whether docs, `CONTEXT.md`, or ADRs changed, or why they did not.
7. Whether the implementation followed the red/green `tdd` path; if not, the concrete reason for the deviation and when it was approved.
8. Whether harness coverage changed; if not, the concrete blocker and linked follow-up issue.

Chat approval is authoritative. The approval does not need to be duplicated into GitHub before work resumes.
