from __future__ import annotations

from dataclasses import dataclass

from wiki_agent.runner.capabilities.orchestration import CapabilityResult


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
        return PageComposition(final_page_content=composition_input.model_page_content)
