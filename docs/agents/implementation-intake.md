# Implementation Intake

Use this guide when the request is about creating, refining, or slicing work before implementation starts.

The rules in this guide are normative. `must`, `must not`, and `stop here` are literal requirements.

## Default Intake Path

1. If the request is a small, concrete implementation task, create or refine one GitHub issue.
2. If the request is a medium-sized plan that obviously breaks into multiple independently shippable slices, use `to-issues`.
3. If the request is a broad or ambiguous initiative, use `to-prd` first, then `to-issues`, then triage the resulting issues.
4. The agent may create the GitHub issue for a direct chat request, but must stop before implementation until a human approves scope and the issue reaches `ready-for-agent`.

## No Docs-Only Exception

There is no docs-only bypass for this repository.

Implementation work, including documentation and instructions changes, must go through an issue-scoped branch and worktree.

## Issue Readiness Gate

An issue must not be implemented until it satisfies all of the following:

1. It has exactly one primary outcome.
2. It states the user-visible or operator-visible behavior change.
3. It names the relevant code area or subsystem when known.
4. It defines acceptance criteria that can be verified locally.
5. Its scope is small enough to land on one branch without becoming a grab-bag.
6. It has the correct triage label and no unresolved blocking questions.

Only a human may give the final approval that moves an issue into `ready-for-agent`.

The agent may analyze the issue, refine the wording, propose labels, and suggest acceptance criteria, but must not self-promote the issue into `ready-for-agent`.

## Label Meanings

Treat triage labels as follows:

| Label | Meaning | Agent action |
| --- | --- | --- |
| `needs-triage` | Not ready for implementation | Analyze, refine, propose next steps, do not branch |
| `needs-info` | Missing required clarification | Stop and request clarification |
| `ready-for-agent` | Approved for implementation | Branching and implementation may start |
| `ready-for-human` | Requires human implementation or decision | Stop unless explicitly asked for non-implementation support |
| `wontfix` | Will not be actioned | Stop |

`ready-for-agent` means approved to implement. It does not mean idle, unclaimed, or unstarted.

The workflow must not invent an `in-progress` label. Execution state is tracked through comments and the draft PR.
