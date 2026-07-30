from __future__ import annotations

from wiki_agent.runner.capabilities.orchestration import (
    CapabilityContext,
    CapabilityOrchestrator,
    CapabilityResult,
)
from wiki_agent.runner.capabilities.web_research import WebResearchOutput


class FakeCapability:
    def __init__(self, outputs: CapabilityResult) -> None:
        self.outputs = outputs
        self.seen_context: CapabilityContext | None = None

    def prepare(self, context: CapabilityContext) -> CapabilityResult:
        self.seen_context = context
        return self.outputs


def test_capability_orchestrator_merges_prompt_sections_and_artifacts_in_order() -> None:
    first = FakeCapability(
        CapabilityResult(
            prompt_sections=("Section one",),
            artifacts=(WebResearchOutput(title="One", url="https://example.com/1"),),
        )
    )
    second = FakeCapability(
        CapabilityResult(
            prompt_sections=("Section two",),
            artifacts=(WebResearchOutput(title="Two", url="https://example.com/2"),),
        )
    )
    context = CapabilityContext(
        prompt="tighten intro",
        original_comment_text="@marvin tighten intro",
        target_page="/pages/example",
        current_page_content="# Current\n",
    )

    outputs = CapabilityOrchestrator(capabilities=(first, second)).prepare(context)

    assert first.seen_context == context
    assert second.seen_context == context
    assert outputs == CapabilityResult(
        prompt_sections=("Section one", "Section two"),
        artifacts=(
            WebResearchOutput(title="One", url="https://example.com/1"),
            WebResearchOutput(title="Two", url="https://example.com/2"),
        ),
    )
