from __future__ import annotations

import re
from dataclasses import dataclass

from wiki_agent.runner.capabilities.orchestration import CapabilityResult
from wiki_agent.runner.capabilities.web_research import WebResearchBudgetConstraint, WebResearchOutput


@dataclass(frozen=True)
class PageCompositionInput:
    current_page_content: str
    model_page_content: str
    capability_result: CapabilityResult
    invocation_as_of_date: str = ""
    fresh_verification_obtained: bool = False
    degraded_web_research: bool = False


@dataclass(frozen=True)
class PageComposition:
    final_page_content: str


class PageComposer:
    def compose_update(self, composition_input: PageCompositionInput) -> PageComposition:
        web_research_outputs = tuple(
            artifact
            for artifact in composition_input.capability_result.artifacts
            if isinstance(artifact, WebResearchOutput)
        )
        body, model_references = _split_references_section(composition_input.model_page_content)
        body = _append_research_note(
            body,
            invocation_as_of_date=composition_input.invocation_as_of_date,
            fresh_verification_obtained=composition_input.fresh_verification_obtained,
            degraded_web_research=composition_input.degraded_web_research,
        )

        if not web_research_outputs:
            return PageComposition(final_page_content=body)

        budget_constraint = next(
            (
                artifact
                for artifact in composition_input.capability_result.artifacts
                if isinstance(artifact, WebResearchBudgetConstraint)
            ),
            None,
        )
        budget_note = ""
        if budget_constraint is not None:
            budget_note = f"> Note: {budget_constraint.message}\n\n"
        current_body, current_references = _split_references_section(composition_input.current_page_content)
        reference_lines = _reference_lines(
            existing_references=current_references,
            model_references=model_references,
            web_research_outputs=web_research_outputs,
            current_page_body=current_body,
            final_page_body=body,
        )
        return PageComposition(
            final_page_content=body.rstrip()
            + "\n\n"
            + budget_note
            + "## References\n"
            + "\n".join(reference_lines)
            + "\n"
        )


def _split_references_section(markdown: str) -> tuple[str, tuple[str, ...]]:
    match = re.search(r"\n## References\n(?P<references>[\s\S]*)$", markdown)
    if match is None:
        return markdown.rstrip() + "\n", ()

    body = markdown[: match.start()].rstrip() + "\n"
    references = tuple(line.strip() for line in match.group("references").splitlines() if line.strip())
    return body, references


def _reference_lines(
    *,
    existing_references: tuple[str, ...],
    model_references: tuple[str, ...],
    web_research_outputs: tuple[WebResearchOutput, ...],
    current_page_body: str,
    final_page_body: str,
) -> tuple[str, ...]:
    references: list[str] = []
    seen_keys: set[str] = set()
    existing_reference_urls = {
        url for line in existing_references if (url := _extract_url(line)) is not None
    }
    surfaced_urls = {output.url for output in web_research_outputs}
    preferred_lines_by_url = _preferred_reference_lines_by_url(
        model_references=model_references,
        supported_urls=existing_reference_urls | surfaced_urls,
    )

    for line in existing_references:
        if _is_clearly_obsolete_reference(
            line,
            current_page_body=current_page_body,
            final_page_body=final_page_body,
        ):
            continue

        reference_line = line
        url = _extract_url(line)
        if url is not None:
            reference_line = preferred_lines_by_url.get(url, line)

        key = _reference_dedupe_key(reference_line)
        if key in seen_keys:
            continue

        seen_keys.add(key)
        references.append(reference_line)

    for line in model_references:
        url = _extract_url(line)
        if url is None or url not in preferred_lines_by_url:
            continue

        key = _reference_dedupe_key(line)
        if key in seen_keys:
            continue

        seen_keys.add(key)
        references.append(line)

    for output in web_research_outputs:
        line = preferred_lines_by_url.get(output.url, f"- {output.url}")
        key = _reference_dedupe_key(line)
        if key in seen_keys:
            continue
        seen_keys.add(key)
        references.append(line)

    return tuple(references)


def _append_research_note(
    body: str,
    *,
    invocation_as_of_date: str,
    fresh_verification_obtained: bool,
    degraded_web_research: bool,
) -> str:
    note: str | None = None
    if fresh_verification_obtained:
        note = f"Current-state claims in this update were verified against the listed sources on {invocation_as_of_date}."
    elif degraded_web_research:
        note = (
            f"Research note (as of {invocation_as_of_date}): Hosted web search did not surface a source during this "
            "invocation, so this update is best-effort from page-local context and may be incomplete."
        )

    if note is None:
        return body

    return body.rstrip() + "\n\n" + note + "\n"


def _extract_url(line: str) -> str | None:
    match = re.search(r"https?://\S+", line)
    if match is None:
        return None
    return match.group(0).rstrip(")].,;")


def _reference_dedupe_key(line: str) -> str:
    return _extract_url(line) or line


def _preferred_reference_lines_by_url(
    *,
    model_references: tuple[str, ...],
    supported_urls: set[str],
) -> dict[str, str]:
    preferred_lines: dict[str, str] = {}
    for line in model_references:
        url = _extract_url(line)
        if url is None or url not in supported_urls:
            continue
        preferred_lines[url] = line
    return preferred_lines


def _is_clearly_obsolete_reference(
    line: str,
    *,
    current_page_body: str,
    final_page_body: str,
) -> bool:
    url = _extract_url(line)
    if url is None:
        return False

    current_body_urls = set(re.findall(r"https?://\S+", current_page_body))
    final_body_urls = set(re.findall(r"https?://\S+", final_page_body))
    normalized_current_urls = {current_url.rstrip(")].,;") for current_url in current_body_urls}
    normalized_final_urls = {final_url.rstrip(")].,;") for final_url in final_body_urls}
    return url in normalized_current_urls and url not in normalized_final_urls
