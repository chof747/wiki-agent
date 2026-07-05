from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable, Protocol


class ModelTransportError(RuntimeError):
    """Raised when model transport fails before payload validation."""


@dataclass(frozen=True)
class ModelTransportRequest:
    model: str
    system_instruction: str
    user_prompt: str
    response_format: dict[str, Any]


@dataclass(frozen=True)
class ModelTransportResponse:
    output_text: str


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
        response = client.responses.create(
            model=request.model,
            input=[
                {"role": "system", "content": request.system_instruction},
                {"role": "user", "content": request.user_prompt},
            ],
            text={"format": request.response_format},
        )

        status = getattr(response, "status", None)
        if status not in {None, "completed"}:
            raise ModelTransportError("model response did not complete successfully")

        output_text = getattr(response, "output_text", None)
        if not isinstance(output_text, str) or not output_text:
            raise ModelTransportError("model response did not include structured output text")

        return ModelTransportResponse(output_text=output_text)


def parse_json_output(output_text: str) -> object:
    try:
        return json.loads(output_text)
    except json.JSONDecodeError as exc:
        raise ModelTransportError("model output was not valid JSON") from exc
