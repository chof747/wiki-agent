from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class WebResearchOutput:
    title: str
    url: str
