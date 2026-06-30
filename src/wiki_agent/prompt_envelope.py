from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, TextIO

if TYPE_CHECKING:
    from wiki_agent.comment_jobs import CommentJob


class PromptEnvelopeError(ValueError):
    """Raised when a prompt envelope payload is malformed."""


@dataclass(frozen=True)
class PromptEnvelope:
    prompt: str
    original_comment_text: str
    target_page: str
    comment_identity: str

    @classmethod
    def from_comment_job(cls, job: CommentJob) -> "PromptEnvelope":
        return cls(
            prompt=job.prompt,
            original_comment_text=job.original_comment_text,
            target_page=job.target_page,
            comment_identity=job.comment_identity,
        )

    @classmethod
    def from_stdin(cls, stream: TextIO) -> "PromptEnvelope":
        try:
            payload = json.load(stream)
        except json.JSONDecodeError as exc:
            raise PromptEnvelopeError("stdin must contain one JSON prompt envelope") from exc
        return cls.from_payload(payload)

    @classmethod
    def from_payload(cls, payload: object) -> "PromptEnvelope":
        if not isinstance(payload, dict):
            raise PromptEnvelopeError("prompt envelope must be a JSON object")

        expected_keys = {
            "prompt",
            "original_comment_text",
            "target_page",
            "comment_identity",
        }
        unexpected_keys = sorted(set(payload) - expected_keys)
        if unexpected_keys:
            raise PromptEnvelopeError(
                "prompt envelope contains unexpected field(s): "
                + ", ".join(unexpected_keys)
            )

        return cls(
            prompt=_require_non_empty_string(payload, "prompt"),
            original_comment_text=_require_non_empty_string(
                payload, "original_comment_text"
            ),
            target_page=_require_non_empty_string(payload, "target_page"),
            comment_identity=_require_non_empty_string(payload, "comment_identity"),
        )

    def as_dict(self) -> dict[str, str]:
        return {
            "prompt": self.prompt,
            "original_comment_text": self.original_comment_text,
            "target_page": self.target_page,
            "comment_identity": self.comment_identity,
        }

    def to_json(self) -> str:
        return json.dumps(self.as_dict(), sort_keys=True)


def _require_non_empty_string(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise PromptEnvelopeError(
            f"prompt envelope field '{key}' must be a non-empty string"
        )
    return value
