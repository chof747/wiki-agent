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
            invocation_as_of_date="2026-07-07",
            fresh_verification_obtained=True,
        )
    )

    assert composition == PageComposition(
        final_page_content=(
            "# Updated\n\n"
            "New facts.\n\n"
            "Current-state claims in this update were verified against the listed sources on 2026-07-07.\n\n"
            "## References\n"
            "- https://example.com/1\n"
            "- https://example.com/2\n"
        )
    )


def test_page_composer_adds_visible_degraded_research_note_without_references() -> None:
    composition = PageComposer().compose_update(
        PageCompositionInput(
            current_page_content="# Current\n",
            model_page_content="# Updated\n\nBest-effort rewrite.\n",
            capability_result=CapabilityResult(),
            invocation_as_of_date="2026-07-07",
            degraded_web_research=True,
        )
    )

    assert composition == PageComposition(
        final_page_content=(
            "# Updated\n\n"
            "Best-effort rewrite.\n\n"
            "Research note (as of 2026-07-07): Hosted web search did not surface a source during this invocation, so this "
            "update is best-effort from page-local context and may be incomplete.\n"
        )
    )


def test_page_composer_preserves_existing_references_from_current_page() -> None:
    composition = PageComposer().compose_update(
        PageCompositionInput(
            current_page_content=(
                "# Current\n\n"
                "## References\n"
                "- https://example.com/existing\n"
                "- https://example.com/1\n"
            ),
            model_page_content=(
                "# Updated\n\n"
                "New facts.\n\n"
                "## References\n"
                "- existing source without link\n"
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
            "- https://example.com/existing\n"
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


def test_page_composer_ignores_model_reference_lines_that_drop_existing_links() -> None:
    composition = PageComposer().compose_update(
        PageCompositionInput(
            current_page_content=(
                "# Current\n\n"
                "## References\n"
                "- Existing source: https://example.com/existing\n"
            ),
            model_page_content=(
                "# Updated\n\n"
                "New facts.\n\n"
                "## References\n"
                "- Existing source\n"
            ),
            capability_result=CapabilityResult(
                artifacts=(
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
            "- Existing source: https://example.com/existing\n"
            "- https://example.com/2\n"
        )
    )


def test_page_composer_deduplicates_existing_and_new_reference_urls() -> None:
    composition = PageComposer().compose_update(
        PageCompositionInput(
            current_page_content=(
                "# Current\n\n"
                "## References\n"
                "- https://example.com/1\n"
                "- https://example.com/2\n"
            ),
            model_page_content=(
                "# Updated\n\n"
                "New facts.\n\n"
                "## References\n"
                "- https://example.com/2\n"
                "- https://example.com/3\n"
            ),
            capability_result=CapabilityResult(
                artifacts=(
                    WebResearchOutput(title="Source 1", url="https://example.com/1"),
                    WebResearchOutput(title="Source 3", url="https://example.com/3"),
                    WebResearchOutput(title="Source 4", url="https://example.com/4"),
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
            "- https://example.com/3\n"
            "- https://example.com/4\n"
        )
    )


def test_page_composer_preserves_conflict_annotations_from_model_references() -> None:
    composition = PageComposer().compose_update(
        PageCompositionInput(
            current_page_content="# Current\n",
            model_page_content=(
                "# Updated\n\n"
                "Official docs say one thing, but community reports disagree.\n\n"
                "## References\n"
                "- Authoritative source: https://example.com/official\n"
                "- Conflicting source: https://example.com/community\n"
            ),
            capability_result=CapabilityResult(
                artifacts=(
                    WebResearchOutput(title="Official", url="https://example.com/official"),
                    WebResearchOutput(title="Community", url="https://example.com/community"),
                )
            ),
        )
    )

    assert composition == PageComposition(
        final_page_content=(
            "# Updated\n\n"
            "Official docs say one thing, but community reports disagree.\n\n"
            "## References\n"
            "- Authoritative source: https://example.com/official\n"
            "- Conflicting source: https://example.com/community\n"
        )
    )


def test_page_composer_can_upgrade_existing_reference_line_with_model_annotation() -> None:
    composition = PageComposer().compose_update(
        PageCompositionInput(
            current_page_content=(
                "# Current\n\n"
                "## References\n"
                "- https://example.com/community\n"
            ),
            model_page_content=(
                "# Updated\n\n"
                "Community reports conflict with the vendor statement.\n\n"
                "## References\n"
                "- Conflicting source: https://example.com/community\n"
            ),
            capability_result=CapabilityResult(
                artifacts=(
                    WebResearchOutput(title="Community", url="https://example.com/community"),
                )
            ),
        )
    )

    assert composition == PageComposition(
        final_page_content=(
            "# Updated\n\n"
            "Community reports conflict with the vendor statement.\n\n"
            "## References\n"
            "- Conflicting source: https://example.com/community\n"
        )
    )


def test_page_composer_removes_reference_when_its_body_link_is_removed() -> None:
    composition = PageComposer().compose_update(
        PageCompositionInput(
            current_page_content=(
                "# Current\n\n"
                "See https://example.com/obsolete for details.\n\n"
                "## References\n"
                "- https://example.com/obsolete\n"
                "- https://example.com/still-relevant\n"
            ),
            model_page_content=(
                "# Updated\n\n"
                "Fresh summary without the obsolete inline link.\n"
            ),
            capability_result=CapabilityResult(
                artifacts=(
                    WebResearchOutput(title="Still relevant", url="https://example.com/still-relevant"),
                )
            ),
        )
    )

    assert composition == PageComposition(
        final_page_content=(
            "# Updated\n\n"
            "Fresh summary without the obsolete inline link.\n\n"
            "## References\n"
            "- https://example.com/still-relevant\n"
        )
    )
