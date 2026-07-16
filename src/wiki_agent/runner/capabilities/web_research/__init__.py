from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class WebResearchOutput:
    title: str
    url: str


@dataclass(frozen=True)
class WebResearchBudget:
    max_search_actions: int
    max_opened_links: int


@dataclass(frozen=True)
class WebResearchBudgetUsage:
    search_actions_used: int = 0
    opened_links_used: int = 0
    materially_constrained: bool = False


@dataclass(frozen=True)
class WebResearchBudgetConstraint:
    message: str
