from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any


SYSTEM_INSTRUCTION = """You are executing exactly one Wiki Agent invocation for one attached Wiki-Go page.

Rules:
- Operate only on the attached target page.
- Return only structured JSON matching the provided schema.
- If the request is executable on the attached target page, return `action="update"` with the full final page content.
- If the request is unclear, impossible, unsupported, unsafe, forbidden, cross-page, or multi-target, return `action="reject"` with one rejection reason code and a concise explanation.
- Allowed rejection reason codes are: `UNCLEAR_REQUEST`, `MULTI_TARGET_REQUEST`, `CROSS_PAGE_REQUEST`, `FORBIDDEN_ACTION`, `UNSUPPORTED_ACTION`, `MISSING_CONTEXT`, `SAFETY_REFUSAL`.
- For `update`, preserve the raw page format unless the instruction requires a format change.
- For `update`, make the narrowest possible change that satisfies the request.
- For `update`, do not add success commentary, provenance notes, headers, or footers unless the request itself requires them.
- Never describe or perform work on any page other than the attached target page."""

ATTACHED_CONTEXT_PREFIX = "Attached invocation context:\n"


@dataclass(frozen=True)
class ModelTransport:
    input: list[dict[str, str]]
    text: dict[str, Any]

    def to_openai_request(self, *, model: str) -> dict[str, Any]:
        return {
            "model": model,
            "input": self.input,
            "text": self.text,
        }

    def payload_bytes(self, *, model: str) -> int:
        return len(json.dumps(self.to_openai_request(model=model), ensure_ascii=False).encode("utf-8"))


def build_page_update_transport(*, prompt: str, rendered_context: str) -> ModelTransport:
    return ModelTransport(
        input=[
            {"role": "system", "content": SYSTEM_INSTRUCTION},
            {"role": "user", "content": prompt},
            {"role": "user", "content": f"{ATTACHED_CONTEXT_PREFIX}{rendered_context}"},
        ],
        text=_response_format_schema(),
    )


def _response_format_schema() -> dict[str, Any]:
    return {
        "type": "json_schema",
        "name": "wiki_agent_runner_decision",
        "schema": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["update", "reject"]},
                "final_page_content": {"type": ["string", "null"]},
                "rejection_reason_code": {"type": ["string", "null"]},
                "explanation": {"type": ["string", "null"]},
            },
            "required": ["action", "final_page_content", "rejection_reason_code", "explanation"],
            "additionalProperties": False,
        },
        "strict": True,
    }
