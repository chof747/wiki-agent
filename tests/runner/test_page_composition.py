from __future__ import annotations

from wiki_agent.runner.capabilities.orchestration import CapabilityResult
from wiki_agent.runner.capabilities.web_research import WebResearchOutput
from wiki_agent.runner.page_composition import PageComposer, PageComposition, PageCompositionInput


def test_page_composer_preserves_current_passthrough_update_behavior() -> None:
    composition = PageComposer().compose_update(
        PageCompositionInput(
            current_page_content="# Current\n",
            model_page_content="# Updated\n",
            capability_result=CapabilityResult(
                artifacts=(WebResearchOutput(title="Source", url="https://example.com"),)
            ),
        )
    )

    assert composition == PageComposition(final_page_content="# Updated\n")
