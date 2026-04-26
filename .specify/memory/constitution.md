<!--
Sync Impact Report
- Version change: 0.0.0 -> 1.0.0
- Modified principles:
  - Template Principle 1 -> I. Wiki Feedback Automation Scope
  - Template Principle 2 -> II. Service-Native Deployment and Reliability
  - Template Principle 3 -> III. Test-First Delivery (NON-NEGOTIABLE)
  - Template Principle 4 -> IV. AI Agent Framework and Model Access Boundaries
  - Template Principle 5 -> V. Clean Code and Minimal Stack
- Added sections:
  - Technical Standards and Constraints
  - Delivery Workflow and Quality Gates
- Removed sections:
  - None
- Templates requiring updates:
  - ✅ updated .specify/templates/plan-template.md
  - ✅ updated .specify/templates/spec-template.md
  - ✅ updated .specify/templates/tasks-template.md
  - ✅ reviewed .specify/templates/commands/*.md (no files present)
  - ✅ reviewed .opencode/command/speckit.constitution.md (no stale agent naming)
  - ✅ reviewed .specify/extensions/git/README.md (no constitution conflicts)
- Follow-up TODOs:
  - None
-->
# Wiki Agent Constitution

## Core Principles

### I. Wiki Feedback Automation Scope
The system MUST poll editorial comments at defined intervals and trigger an AI
agent workflow that applies approved feedback into the wiki-go wiki. All feature
work MUST directly support this flow or required platform capabilities (security,
operations, reliability, or developer productivity). Rationale: strict scope
prevents feature drift and keeps delivery focused on editorial value.

### II. Service-Native Deployment and Reliability
The agent MUST be deployable as part of the existing wiki service runtime,
including environment-based configuration, health checks, and graceful recovery
from temporary upstream failures. Polling and feedback-application operations MUST
be idempotent to prevent duplicate wiki edits. Rationale: operational safety is
mandatory for background automation in production services.

### III. Test-First Delivery (NON-NEGOTIABLE)
Development MUST follow TDD: write failing tests first, implement the smallest
change to pass, then refactor. Every change MUST include unit tests and any
required integration/contract tests for scheduler behavior, agent orchestration,
and wiki-go write paths. No feature is complete until automated tests pass in CI.
Rationale: interval automation and AI integrations are failure-prone without
regression protection.

### IV. AI Agent Framework and Model Access Boundaries
AI orchestration MUST use a maintained agent framework with clear abstractions for
tool execution, prompts, retries, and model/provider configuration. The codebase
MUST support OpenAI-compatible model access configured via environment secrets,
with provider wiring isolated behind interfaces so model implementations are
replaceable and mockable for tests. Rationale: framework-backed boundaries reduce
vendor lock-in and enable deterministic testing.

### V. Clean Code and Minimal Stack
The implementation MUST prefer a small, maintainable dependency set and clear
module boundaries over layered complexity. Every dependency addition MUST be
justified by clear functional need and lack of simpler alternatives. Code MUST
favor readability, single-responsibility components, and explicit interfaces over
implicit coupling. Rationale: maintainability is the primary long-term risk in
automation services.

## Technical Standards and Constraints

- Runtime architecture MUST include: comment polling scheduler, feedback triage,
  AI task execution, wiki-go integration client, and structured audit logging.
- Secrets MUST never be committed; model credentials and wiki-go auth MUST be
  supplied through environment configuration and secret management.
- Time-based workflows MUST define polling interval defaults, backoff strategy,
  and dead-letter/error handling behavior.
- External I/O (LLM calls and wiki writes) MUST include retry limits and timeout
  policies with explicit failure reporting.
- Any persistent state used for deduplication or checkpointing MUST have a clear
  ownership model and migration strategy.

## Delivery Workflow and Quality Gates

- Plans MUST pass a Constitution Check before design begins and before
  implementation starts.
- Specs MUST define independently testable user stories and explicit acceptance
  scenarios for polling, feedback transformation, and wiki publishing behavior.
- Tasks MUST include test-first tasks per story and operational readiness tasks
  (observability, deployment configuration, rollback verification).
- Pull requests MUST document constitution compliance, including TDD evidence,
  dependency impact, and deployment impact.
- Releases MUST include quickstart or runbook updates when workflows, configs, or
  operational expectations change.

## Governance

This constitution is the source of truth for engineering decisions in this
repository and supersedes conflicting local conventions.

Amendment process:
- Propose changes in a pull request that includes rationale, migration impact,
  and updates to dependent templates/docs.
- Require approval from repository maintainers before merge.
- Record version and date updates in this document with each amendment.

Versioning policy:
- MAJOR: remove or redefine a principle in a backward-incompatible way.
- MINOR: add a principle/section or materially expand required practices.
- PATCH: clarify wording without changing normative requirements.

Compliance review expectations:
- Every implementation plan, task list, and pull request MUST include an explicit
  constitution compliance check.
- Reviewers MUST block merges when mandatory principles or quality gates are not
  satisfied.

**Version**: 1.0.0 | **Ratified**: 2026-04-26 | **Last Amended**: 2026-04-26
