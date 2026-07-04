# Implementation Code

Use this guide after the issue-scoped worktree exists and implementation is ready to begin.

The rules in this guide are normative. `must`, `must not`, and `stop here` are literal requirements.

## Select The Path

1. Use `diagnose` first for bug work.
2. Use `tdd` for behavior-changing implementation. This is the required default path, not an optional preference.
3. Direct implementation is allowed for docs-only work, comment-only work, scaffolding, and no-behavior refactors.

## Implementation Rules

1. Behavior-changing work must start with `tdd` unless a human explicitly approves a different path in advance.
2. The required `tdd` starting point is a failing automated test or harness-backed integration case that demonstrates the missing behavior, bug, or contract gap before implementation begins.
3. For bug work, reproduce and minimize the problem with `diagnose` before switching into `tdd`.
4. If the codebase lacks a reasonable test seam for the requested behavior change, stop and ask whether creating that seam is in scope.
5. If the implementer does not follow the red/green path for a behavior-changing issue, that deviation must be called out before coding and must be justified again in the HIL review packet.
6. If implementation reveals more than one independently shippable outcome, stop and split scope.
7. If the repo defines a canonical integration harness for a runtime boundary, future runtime work must extend that harness rather than introduce a parallel setup flow unless a human explicitly approves replacing it.
8. For runtime issues that touch the Scanner, Worker, Runner, Postgres Comment Job lifecycle, or Wiki-Go mutation flow, the implementer must explicitly assess harness impact before coding.
9. Before coding a runtime-boundary change that depends on an external SDK, CLI, config contract, runtime-loaded package resource, or local dependency assumption, the implementer must run explicit boundary probes and record the outcome in working notes or the HIL packet.
10. The required probes are only the smallest checks needed to collapse uncertainty in the path of the work, such as import or install availability, external contract shape, required helper-command surface, harness seam availability, or runtime-loaded resource presence.
11. If a boundary probe fails or reveals contract ambiguity, stop before implementation and ask for HIL or issue refinement instead of discovering the boundary mid-patch.
12. If the issue scope makes harness extension possible, the same branch must extend harness coverage.
13. If harness extension is not yet possible, stop and record the blocker in the HIL review packet and linked issue follow-up. Acceptable blockers are limited to missing helper-command surface, missing fixture/seeding seam, or an intentionally earlier issue slice approved by a human.
14. Tests must prove observable behavior or a stable module contract, not just that one method forwards to another.
15. Do not rely only on subclass overrides, mocks, or stubs unless the test still asserts a user-visible or boundary-level effect.
16. If a test would pass with a forwarding stub, strengthen it or document the gap in the HIL review.

## If Scope Must Split

1. Comment on the issue with the discovered split.
2. Create or propose follow-up issues.
3. Keep the current branch focused on the smallest valuable slice, or abandon it if the issue was wrong at its core.

## Documentation Rules During Implementation

Documentation is part of implementation, not cleanup.

1. If behavior changes, update the relevant user-facing or operator-facing docs in the same branch.
2. If domain language changes, update `CONTEXT.md` before or during implementation.
3. If the change introduces a hard-to-reverse, surprising architectural trade-off, stop for HIL and then add or update an ADR in `docs/adr/`.
4. Persistent docs must describe steady-state behavior, contracts, and accepted design, not issue-specific implementation history.
5. Persistent docs must not reference issue numbers, branch names, or transitional refactor rationale unless the repo explicitly treats that document as change history.
6. If change provenance matters, put it in the issue, PR, commit message, or ADR instead of user-facing or operator-facing steady-state docs.
7. If no docs changed, the HIL review packet must explicitly state why no doc updates were needed.
