# Strategic Programming

This document defines the required decision standard for work in this repo.

The rules in this document are normative. `must`, `must not`, and `stop here` are literal requirements.

This document complements [implementation-workflow.md](./implementation-workflow.md). The workflow governs how work proceeds. This document governs how implementation decisions must be made.

## 1. Core Rule

Implementation must optimize for long-term system coherence, not only immediate task completion.

The implementer must prefer the change that keeps the system understandable, locally consistent, and easier to extend, even when that costs modest extra effort now.

## 2. Tactical Tornado Anti-Pattern

A **tactical tornado** is an implementer who optimizes for immediate code delivery at the expense of design quality, leaving added complexity, follow-on bugs, and cleanup work for others.

This repo must not be changed in that style.

The implementer must not:

1. Code through unresolved ambiguity just to maintain momentum.
2. Trade hidden complexity for local speed without explicit approval.
3. Patch over a design mismatch in a way that makes the touched area harder to understand.
4. Expand one issue into unrelated cleanup or opportunistic redesign.
5. Leave behind partial architectural work without stopping and calling it out.

## 3. Positive Obligations

The implementer must:

1. Resolve domain and design ambiguity before encoding it into code.
2. Keep the current issue focused on one primary outcome.
3. Leave touched code coherent by fixing small problems only (§4).
4. Use explicit language when a trade-off is being made instead of hiding it inside the patch.

If no meaningful improvement is visible, the implementer does not need to invent one.

## 4. Small vs Medium/Large Problems

A **small** problem must be fixed immediately when all of the following are true:

1. It is local to the touched area.
2. It does not require a new design decision.
3. It does not cross a module or contract boundary.
4. It does not change the issue's primary outcome.

A **medium** or **large** problem is any problem where one or more of the following are true:

1. It crosses a module or contract boundary.
2. It requires choosing between multiple plausible designs.
3. It changes the effective scope of the current issue.
4. It would leave behind partial architectural work if handled opportunistically.

## 5. Mandatory Stop Conditions

The implementer must stop here and ask for further instructions when any of the following is discovered during grilling, exploration, implementation or diagnosing:

1. Unresolved ambiguity or design problem in the path of the work.
2. A meaningful architectural trade-off not settled in `CONTEXT.md` or an ADR.
3. Scope pressure creeping into grab-bag territory.
4. Fix requires knowingly adding hidden complexity just to keep moving.

In AFK mode, the same stop rule applies. The agent must not continue autonomously past these conditions.

## 6. Required Output At A Hard Stop

When a stop condition is hit, the implementer must report:

1. The concrete problem that was observed.
2. Why it is not small.
3. The impact on the current issue.
4. The decision or instruction now required from a human.

The implementer must not invent follow-up work, speculative proposals, or new issues when no concrete problem has been observed.

## 7. Narrow Break-Glass Exception

A tactical containment patch is allowed only for urgent break-glass work and only with explicit human-in-the-loop approval before implementation.

When this exception is used:

1. The implementer must stop immideately to get concrete approval for this.
2. The implementer must state that the patch is tactical containment, not the preferred steady-state design.
3. The implementer must describe the compromise plainly.
4. The implementer must create a cleanup issue before or as part of that work.


This exception must not be used for ordinary feature delivery, convenience, or schedule pressure.
