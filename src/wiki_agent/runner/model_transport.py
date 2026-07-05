from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable, Protocol

from wiki_agent.runner.capabilities.web_research import WebResearchOutput


class ModelTransportError(RuntimeError):
    """Raised when model transport fails before payload validation."""


@dataclass(frozen=True)
class ModelTransportRequest:
    model: str
    system_instruction: str
    user_prompt: str
    response_format: dict[str, Any]
    tools: tuple[dict[str, Any], ...] = ()


@dataclass(frozen=True)
class ModelTransportResponse:
    output_text: str
    web_research_outputs: tuple[WebResearchOutput, ...] = ()


class ModelTransport(Protocol):
    def generate(self, request: ModelTransportRequest) -> ModelTransportResponse: ...


def build_openai_client(*, api_key: str, timeout: float) -> Any:
    from openai import OpenAI

    return OpenAI(api_key=api_key, timeout=timeout)


@dataclass
class OpenAIResponsesTransport:
    api_key: str
    timeout_seconds: float
    client_factory: Callable[..., Any] = build_openai_client

    def generate(self, request: ModelTransportRequest) -> ModelTransportResponse:
        client = self.client_factory(api_key=self.api_key, timeout=self.timeout_seconds)
        payload: dict[str, Any] = {
            "model": request.model,
            "input": [
                {"role": "system", "content": request.system_instruction},
                {"role": "user", "content": request.user_prompt},
            ],
            "text": {"format": request.response_format},
        }
        if request.tools:
            payload["tools"] = list(request.tools)

        response = client.responses.create(
            **payload,
        )

        status = getattr(response, "status", None)
        if status not in {None, "completed"}:
            raise ModelTransportError("model response did not complete successfully")

        output_text = getattr(response, "output_text", None)
        if not isinstance(output_text, str) or not output_text:
            raise ModelTransportError("model response did not include structured output text")

        return ModelTransportResponse(
            output_text=output_text,
            web_research_outputs=_extract_web_research_outputs(response),
        )


def _extract_web_research_outputs(response: Any) -> tuple[WebResearchOutput, ...]:
    outputs: list[WebResearchOutput] = []
    seen_urls: set[str] = set()

    for item in getattr(response, "output", ()) or ():
        if getattr(item, "type", None) != "web_search_call":
            continue

        action = getattr(item, "action", None)
        if getattr(action, "type", None) != "search":
            continue

        for source in getattr(action, "sources", ()) or ():
            if getattr(source, "type", None) != "url":
                continue
            url = getattr(source, "url", None)
            if not isinstance(url, str) or not url or url in seen_urls:
                continue
            seen_urls.add(url)
            outputs.append(WebResearchOutput(title=url, url=url))

    return tuple(outputs)


def parse_json_output(output_text: str) -> object:
    try:
        return json.loads(output_text)
    except json.JSONDecodeError as exc:
        raise ModelTransportError("model output was not valid JSON") from exc
