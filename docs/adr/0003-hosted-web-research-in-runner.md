# Hosted web research in runner

Marvin may autonomously perform web research inside the runner when it helps satisfy a prompt. We use OpenAI-hosted `web_search` for discovery and page opening, restrict research to links surfaced directly by that search, require citations in a trailing `## References` section, and enforce a configurable per-invocation research budget with best-effort completion when the budget is exhausted. This keeps the worker and prompt-envelope contracts unchanged while adding bounded external research that remains read-only, single-target, and reviewable.
