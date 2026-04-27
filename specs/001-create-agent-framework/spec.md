# Feature Specification: Minimal Agent Framework CLI

**Feature Branch**: `001-create-agent-framework`  
**Created**: 2026-04-26  
**Status**: Draft  
**Input**: User description: "Agent Framework: Create a minimal agent that can use basic tools like https://opencode.ai/, connect to mcp tools and to the open AI gateway with an chatgpt plus account. As an intermediate functionality of this stage the agent should be invokable via a command line script with a simple prompt."

## Clarifications

### Session 2026-04-26

- Q: Where should gateway credentials be sourced from? -> A: Use OS secure credential store when available, with environment-variable fallback for macOS and Linux.
- Q: What should default tool authorization behavior be? -> A: Use a per-run allowlist by default, with an optional allow-all override; persistent tool permission configuration is out of scope for this stage.
- Q: What should transient failure retry policy be for this stage? -> A: No automatic retries.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Run Agent from CLI (Priority: P1)

A developer runs a single command in a terminal, enters a plain-language prompt, and gets a usable agent response in the same session.

**Why this priority**: A working command-line invocation is the minimum value needed to prove the agent can be used end-to-end.

**Independent Test**: Can be fully tested by running the CLI command with a simple prompt and confirming a response is returned without manual setup steps beyond documented prerequisites.

**Acceptance Scenarios**:

1. **Given** valid local setup and credentials, **When** the user runs the CLI script and provides a prompt, **Then** the agent returns a response in the terminal.
2. **Given** the CLI script is invoked with no prompt text, **When** execution starts, **Then** the user receives a clear usage message that explains how to provide a prompt.

---

### User Story 2 - Use MCP-Compatible Tools (Priority: P2)

A developer asks the agent to perform a tool-backed task, and the agent can discover and call connected MCP-compatible tools when available.

**Why this priority**: Tool usage is core to practical agent workflows but can be validated after the base CLI prompt loop is working.

**Independent Test**: Can be tested by connecting at least one MCP-compatible tool source, issuing a prompt that requires tool use, and verifying the tool call result is reflected in the response.

**Acceptance Scenarios**:

1. **Given** at least one MCP-compatible tool is configured and reachable, **When** the user submits a prompt that needs a tool action, **Then** the agent executes the tool action and includes the outcome in its response.
2. **Given** no MCP-compatible tools are reachable, **When** the user submits a tool-dependent prompt, **Then** the agent reports the limitation and does not crash.

---

### User Story 3 - Use AI Gateway Account (Priority: P3)

A developer configures access to an AI gateway account and can receive generated responses through that account without changing the CLI usage pattern.

**Why this priority**: Provider connectivity is essential for real usage but is incrementally valuable after command invocation and basic flow are in place.

**Independent Test**: Can be tested by configuring valid gateway credentials, running a prompt, and verifying the response is generated through the configured provider path.

**Acceptance Scenarios**:

1. **Given** valid gateway credentials are present, **When** the user submits a prompt, **Then** the agent returns a generated response.
2. **Given** gateway credentials are missing or invalid, **When** the user submits a prompt, **Then** the agent returns a clear authentication or configuration error with recovery guidance.

---

### Edge Cases

- Empty, whitespace-only, or over-limit prompt input returns a validation error and usage guidance; no provider or tool calls are attempted.
- If a requested tool is unreachable, the invocation completes with a tool-unavailable outcome and actionable recovery steps, without process crash.
- Provider timeout or temporary upstream failure returns a timeout/failure outcome in the same invocation (no automatic retry in this stage).
- Missing or invalid credentials at startup fail fast with a clear setup checklist for recovery.
- If tool output is malformed or incomplete, the invocation returns a partial-failure outcome that includes which step failed.
- If the user requests a non-allowlisted tool, the invocation denies the action with explicit permission guidance.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST provide a command-line script that starts the agent with a single prompt input.
- **FR-002**: System MUST accept prompt input through command arguments or an interactive prompt fallback.
- **FR-003**: System MUST return agent output in the terminal for each invocation.
- **FR-004**: System MUST validate required runtime configuration before sending requests.
- **FR-004a**: System MUST source gateway credentials from the operating system secure credential store when available, with environment-variable fallback when secure store access is unavailable.
- **FR-005**: System MUST support connecting to MCP-compatible tool endpoints configured for the environment.
- **FR-006**: System MUST allow the agent to invoke connected MCP-compatible tools during prompt handling when needed.
- **FR-006a**: System MUST enforce a per-invocation tool allowlist by default and support an explicit allow-all override for trusted development runs.
- **FR-007**: System MUST support using a configured AI gateway account for model response generation.
- **FR-008**: System MUST provide actionable error messages for invalid credentials, unavailable tools, and provider timeouts.
- **FR-009**: System MUST complete each CLI invocation without leaving orphaned background processes.
- **FR-010**: System MUST log invocation-level events sufficient to troubleshoot request lifecycle failures.
- **FR-011**: System MUST reject invalid prompt inputs (empty, whitespace-only, over-limit) before execution and return corrective guidance.
- **FR-012**: System MUST deny non-allowlisted tool actions with a clear permission error that identifies the blocked tool request.

### Key Entities *(include if feature involves data)*

- **Agent Invocation**: A single CLI run containing prompt input, execution start/end timestamps, outcome status, and response text.
- **Tool Connection Profile**: Configured MCP-compatible tool source details, availability status, and permissions for tool invocation.
- **Gateway Credential Context**: Account-scoped authentication material and validation status used to authorize AI response generation.
- **Execution Result**: Structured outcome that includes agent response content, errors (if any), and tool activity summary.

## Operational and AI Constraints *(mandatory)*

- **OA-001**: Polling and scheduling behavior MUST be disabled for this stage; each run is a single on-demand request with no automatic retries.
- **OA-002**: Re-running the same prompt MUST be idempotent at the invocation level, meaning duplicate runs do not corrupt local state or create duplicate side effects without explicit user intent.
- **OA-003**: AI orchestration MUST enforce clear boundaries between prompt routing, tool invocation, and provider calls, with configurable timeout limits for each stage.
- **OA-004**: Runtime expectations MUST support local developer execution in the existing repository environment without requiring long-running background services.
- **OA-005**: Observability MUST include per-invocation logs, tool call outcomes, provider latency signal, and explicit failure reasons.
- **OA-006**: Credential handling MUST support both macOS and Linux runtime environments using a secure-store-first, environment-fallback policy.
- **OA-007**: Persistent agent-level tool permission configuration is deferred to a later stage; current stage applies invocation-scoped permission control only.

## Test Strategy *(mandatory)*

- Unit tests MUST cover prompt parsing, configuration validation, response formatting, and error mapping behavior.
- Integration tests MUST cover end-to-end CLI invocation, tool-enabled prompt handling, and provider-authenticated response generation.
- Contract tests MUST validate compatibility assumptions for tool connections and gateway request/response handling.
- Test sequencing MUST follow red-green-refactor to establish behavior before implementation hardening.
- Failure-path tests MUST cover missing credentials, unreachable tools, timeout scenarios, and partial-response handling.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 95% of valid CLI invocations return a response or explicit user-actionable error within 10 seconds under normal development environment conditions.
- **SC-002**: 100% of sampled tool-enabled prompts either complete with tool-informed responses or fail with explicit tool availability messaging.
- **SC-003**: At least 90% of trial users can complete first-time setup and receive a successful response in one attempt using the written setup instructions.
- **SC-004**: During acceptance testing, 0 unresolved crashes occur across 50 consecutive invocations spanning success and failure-path scenarios.

## Assumptions

- The target user is a developer running the agent locally from a terminal.
- A valid AI gateway account and required credentials are available to authorized users.
- At least one MCP-compatible tool endpoint can be configured in environments where tool-use scenarios are tested.
- This stage focuses on single-prompt invocation, not persistent conversation memory across multiple runs.
- Persistent tool-allow rules in agent configuration are intentionally out of scope for this stage.
- Existing repository conventions for script execution and environment configuration remain available.
