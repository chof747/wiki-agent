from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True)
class CapabilityContext:
    prompt: str
    original_comment_text: str
    target_page: str
    current_page_content: str


@dataclass(frozen=True)
class CapabilityResult:
    prompt_sections: tuple[str, ...] = ()
    artifacts: tuple[object, ...] = ()


class RunnerCapability(Protocol):
    def prepare(self, context: CapabilityContext) -> CapabilityResult: ...


@dataclass
class CapabilityOrchestrator:
    capabilities: tuple[RunnerCapability, ...] = field(default_factory=tuple)

    def prepare(self, context: CapabilityContext) -> CapabilityResult:
        prompt_sections: list[str] = []
        artifacts: list[object] = []

        for capability in self.capabilities:
            outputs = capability.prepare(context)
            prompt_sections.extend(section for section in outputs.prompt_sections if section)
            artifacts.extend(outputs.artifacts)

        return CapabilityResult(
            prompt_sections=tuple(prompt_sections),
            artifacts=tuple(artifacts),
        )
