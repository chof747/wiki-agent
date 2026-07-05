from __future__ import annotations

import re
from dataclasses import dataclass

from wiki_agent.runner.capabilities.orchestration import CapabilityResult
from wiki_agent.runner.capabilities.web_research import WebResearchOutput


@dataclass(frozen=True)
class PageCompositionInput:
    current_page_content: str
    model_page_content: str
    capability_result: CapabilityResult


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
        if not web_research_outputs:
            return PageComposition(final_page_content=composition_input.model_page_content)

        body, existing_references = _split_references_section(composition_input.model_page_content)
        reference_lines = _merge_reference_lines(existing_references, web_research_outputs)
        return PageComposition(
            final_page_content=body.rstrip() + "\n\n## References\n" + "\n".join(reference_lines) + "\n"
        )


def _split_references_section(markdown: str) -> tuple[str, tuple[str, ...]]:
    match = re.search(r"\n## References\n(?P<references>[\s\S]*)$", markdown)
    if match is None:
        return markdown.rstrip() + "\n", ()

    body = markdown[: match.start()].rstrip() + "\n"
    references = tuple(line.strip() for line in match.group("references").splitlines() if line.strip())
    return body, references


def _merge_reference_lines(
    existing_references: tuple[str, ...],
    web_research_outputs: tuple[WebResearchOutput, ...],
) -> tuple[str, ...]:
    merged: list[str] = []
    seen_urls: set[str] = set()

    for line in existing_references:
        url = _extract_url(line)
        if url is not None:
            seen_urls.add(url)
        merged.append(line)

    for output in web_research_outputs:
        if output.url in seen_urls:
            continue
        seen_urls.add(output.url)
        merged.append(f"- {output.url}")

    return tuple(merged)


def _extract_url(line: str) -> str | None:
    match = re.search(r"https?://\S+", line)
    if match is None:
        return None
    return match.group(0).rstrip(")].,;")
