from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from datetime import timedelta
from typing import TYPE_CHECKING, Any

from wiki_agent.domain import ALLOWED_INVOCATION_STATUSES

if TYPE_CHECKING:
    from wiki_agent.comment_jobs import CommentJob


class RunnerConfigError(ValueError):
    """Raised when runner configuration is invalid."""


@dataclass(frozen=True)
class RunnerCommand:
    argv: tuple[str, ...]


@dataclass(frozen=True)
class PromptEnvelope:
    prompt: str
    original_comment_text: str
    target_page: str
    comment_identity: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "prompt": self.prompt,
            "original_comment_text": self.original_comment_text,
            "target_page": self.target_page,
            "comment_identity": self.comment_identity,
        }


@dataclass(frozen=True)
class RunnerResponse:
    status: str
    payload: dict[str, Any]
    stderr: str


class RunnerInvocationError(RuntimeError):
    """Raised when the runner process does not produce a valid finalized response."""


DEFAULT_RUNNER_TIMEOUT = timedelta(minutes=15)
class RunnerClient:
    def __init__(
        self,
        command: RunnerCommand,
        *,
        timeout: timedelta = DEFAULT_RUNNER_TIMEOUT,
    ) -> None:
        self._command = command
        self._timeout = timeout

    def build_prompt_envelope(self, job: CommentJob) -> PromptEnvelope:
        return PromptEnvelope(
            prompt=job.prompt,
            original_comment_text=job.original_comment_text,
            target_page=job.target_page,
            comment_identity=job.comment_identity,
        )

    def invoke(self, job: CommentJob) -> RunnerResponse:
        envelope = self.build_prompt_envelope(job)
        try:
            result = subprocess.run(
                list(self._command.argv),
                input=json.dumps(envelope.as_dict(), sort_keys=True),
                capture_output=True,
                text=True,
                check=False,
                timeout=self._timeout.total_seconds(),
            )
        except subprocess.TimeoutExpired as exc:
            raise RunnerInvocationError("runner timed out without valid response") from exc

        if result.returncode != 0:
            raise RunnerInvocationError(
                f"runner exited with {result.returncode}: {_summarize_stderr(result.stderr)}"
            )

        payload = parse_runner_response(result.stdout)
        status = payload["status"]

        return RunnerResponse(status=status, payload=payload, stderr=result.stderr)


def validate_runner_command(value: object) -> RunnerCommand:
    if not isinstance(value, list) or not value:
        raise RunnerConfigError("runner.command must be a non-empty list of strings")

    argv: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise RunnerConfigError(
                "runner.command must contain only non-empty strings"
            )
        argv.append(item)

    return RunnerCommand(argv=tuple(argv))


def parse_runner_response(stdout: str) -> dict[str, Any]:
    payload = _parse_response_json(stdout)
    status = payload.get("status")
    if status not in ALLOWED_INVOCATION_STATUSES:
        raise RunnerInvocationError("runner response contained invalid status")
    return payload


def _parse_response_json(stdout: str) -> dict[str, Any]:
    stripped = stdout.strip()
    if not stripped:
        raise RunnerInvocationError("runner did not emit a finalized response")

    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError as exc:
        raise RunnerInvocationError("runner emitted invalid JSON on stdout") from exc

    if not isinstance(payload, dict):
        raise RunnerInvocationError("runner response must be a JSON object")

    return payload


def _summarize_stderr(stderr: str) -> str:
    stripped = stderr.strip()
    return stripped or "no stderr"
