from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from wiki_agent.runner.model_transport import (
    ModelTransportError,
    ModelTransportRequest,
    OpenAIResponsesTransport,
    parse_json_output,
)


def test_openai_responses_transport_builds_one_structured_request() -> None:
    seen: dict[str, object] = {}

    class FakeClient:
        def __init__(self) -> None:
            self.responses = self

        def create(self, **kwargs):
            seen.update(kwargs)
            return SimpleNamespace(status="completed", output_text=json.dumps({"action": "update"}))

    transport = OpenAIResponsesTransport(
        api_key="test-key",
        timeout_seconds=12.5,
        client_factory=lambda **kwargs: seen.update(kwargs) or FakeClient(),
    )

    response = transport.generate(
        ModelTransportRequest(
            model="gpt-test",
            system_instruction="system instruction",
            user_prompt="user prompt",
            response_format={"type": "json_schema"},
            tools=({"type": "web_search"},),
        )
    )

    assert response.output_text == '{"action": "update"}'
    assert seen == {
        "api_key": "test-key",
        "timeout": 12.5,
        "model": "gpt-test",
        "input": [
            {"role": "system", "content": "system instruction"},
            {"role": "user", "content": "user prompt"},
        ],
        "text": {"format": {"type": "json_schema"}},
        "tools": [{"type": "web_search"}],
    }


def test_openai_responses_transport_extracts_surfaced_web_search_urls() -> None:
    class FakeClient:
        def __init__(self) -> None:
            self.responses = self

        def create(self, **_kwargs):
            return SimpleNamespace(
                status="completed",
                output_text=json.dumps({"action": "update"}),
                output=[
                    SimpleNamespace(
                        type="web_search_call",
                        action=SimpleNamespace(
                            type="search",
                            sources=[
                                SimpleNamespace(type="url", url="https://example.com/1"),
                                SimpleNamespace(type="url", url="https://example.com/1"),
                                SimpleNamespace(type="url", url="https://example.com/2"),
                            ],
                        ),
                    )
                ],
            )

    transport = OpenAIResponsesTransport(
        api_key="test-key",
        timeout_seconds=12.5,
        client_factory=lambda **_kwargs: FakeClient(),
    )

    response = transport.generate(
        ModelTransportRequest(
            model="gpt-test",
            system_instruction="system instruction",
            user_prompt="user prompt",
            response_format={"type": "json_schema"},
        )
    )

    assert [item.url for item in response.web_research_outputs] == [
        "https://example.com/1",
        "https://example.com/2",
    ]


def test_openai_responses_transport_rejects_incomplete_status() -> None:
    class FakeClient:
        def __init__(self) -> None:
            self.responses = self

        def create(self, **_kwargs):
            return SimpleNamespace(status="incomplete", output_text="{}")

    transport = OpenAIResponsesTransport(
        api_key="test-key",
        timeout_seconds=12.5,
        client_factory=lambda **_kwargs: FakeClient(),
    )

    with pytest.raises(ModelTransportError, match="did not complete successfully"):
        transport.generate(
            ModelTransportRequest(
                model="gpt-test",
                system_instruction="system instruction",
                user_prompt="user prompt",
                response_format={"type": "json_schema"},
            )
        )


def test_parse_json_output_rejects_invalid_json() -> None:
    with pytest.raises(ModelTransportError, match="not valid JSON"):
        parse_json_output("{not json}")
