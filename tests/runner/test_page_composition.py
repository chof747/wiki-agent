from __future__ import annotations

from wiki_agent.runner.capabilities.orchestration import CapabilityResult
from wiki_agent.runner.capabilities.web_research import WebResearchBudgetConstraint, WebResearchOutput
from wiki_agent.runner.page_composition import PageComposer, PageComposition, PageCompositionInput


def test_page_composer_preserves_current_passthrough_update_behavior() -> None:
    composition = PageComposer().compose_update(
        PageCompositionInput(
            current_page_content="# Current\n",
            model_page_content="# Updated\n",
            capability_result=CapabilityResult(),
        )
    )

    assert composition == PageComposition(final_page_content="# Updated\n")


def test_page_composer_appends_trailing_references_for_web_research_outputs() -> None:
    composition = PageComposer().compose_update(
        PageCompositionInput(
            current_page_content="# Current\n",
            model_page_content="# Updated\n\nNew facts.\n",
            capability_result=CapabilityResult(
                artifacts=(
                    WebResearchOutput(title="Source 1", url="https://example.com/1"),
                    WebResearchOutput(title="Source 2", url="https://example.com/2"),
                )
            ),
        )
    )

    assert composition == PageComposition(
        final_page_content=(
            "# Updated\n\n"
            "New facts.\n\n"
            "## References\n"
            "- https://example.com/1\n"
            "- https://example.com/2\n"
        )
    )


def test_page_composer_rebuilds_existing_references_from_surfaced_web_research_outputs() -> None:
    composition = PageComposer().compose_update(
        PageCompositionInput(
            current_page_content="# Current\n",
            model_page_content=(
                "# Updated\n\n"
                "New facts.\n\n"
                "## References\n"
                "- https://example.com/existing\n"
                "- https://example.com/1\n"
            ),
            capability_result=CapabilityResult(
                artifacts=(
                    WebResearchOutput(title="Source 1", url="https://example.com/1"),
                    WebResearchOutput(title="Source 2", url="https://example.com/2"),
                )
            ),
        )
    )

    assert composition == PageComposition(
        final_page_content=(
            "# Updated\n\n"
            "New facts.\n\n"
            "## References\n"
            "- https://example.com/1\n"
            "- https://example.com/2\n"
        )
    )


def test_page_composer_discloses_material_budget_constraints_before_references() -> None:
    composition = PageComposer().compose_update(
        PageCompositionInput(
            current_page_content="# Current\n",
            model_page_content="# Updated\n\nNew facts.\n",
            capability_result=CapabilityResult(
                artifacts=(
                    WebResearchOutput(title="Source 1", url="https://example.com/1"),
                    WebResearchBudgetConstraint(
                        message=(
                            "Web research hit the per-invocation budget. "
                            "This update reflects only the evidence gathered before the limit was reached."
                        )
                    ),
                )
            ),
        )
    )

    assert composition == PageComposition(
        final_page_content=(
            "# Updated\n\n"
            "New facts.\n\n"
            "> Note: Web research hit the per-invocation budget. "
            "This update reflects only the evidence gathered before the limit was reached.\n\n"
            "## References\n"
            "- https://example.com/1\n"
        )
    )
