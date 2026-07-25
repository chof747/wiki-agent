from __future__ import annotations

import json

from wiki_agent.runner import model_transport


def test_page_update_transport_keeps_stripped_request_separate_from_attached_context() -> None:
    transport = model_transport.build_page_update_transport(
        prompt="# Rewrite the page\n\nMake it shorter.\n",
        rendered_context=(
            "Target page: /pages/example\n\n"
            "Original source comment:\n@marvin # Rewrite the page\n\nMake it shorter.\n\n"
            "Current page content:\n# Current page\n"
        ),
    )

    assert transport.input == [
        {"role": "system", "content": model_transport.SYSTEM_INSTRUCTION},
        {"role": "user", "content": "# Rewrite the page\n\nMake it shorter.\n"},
        {
            "role": "user",
            "content": (
                "Attached invocation context:\n"
                "Target page: /pages/example\n\n"
                "Original source comment:\n@marvin # Rewrite the page\n\nMake it shorter.\n\n"
                "Current page content:\n# Current page\n"
            ),
        },
    ]
    assert "Current page content:" not in transport.input[0]["content"]
    assert "Original source comment:" not in transport.input[0]["content"]
    assert "Target page:" not in transport.input[0]["content"]


def test_page_update_transport_byte_count_matches_openai_request_payload() -> None:
    transport = model_transport.build_page_update_transport(
        prompt="tighten intro",
        rendered_context="Target page: /pages/example\n\nCurrent page content:\n# Current page\n",
    )

    request_kwargs = transport.to_openai_request(model="gpt-4o-2024-08-06")

    assert transport.payload_bytes(model="gpt-4o-2024-08-06") == len(
        json.dumps(request_kwargs, ensure_ascii=False).encode("utf-8")
    )
