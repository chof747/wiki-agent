from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any


UPDATE_FAILED = {"status": "UPDATE_FAILED"}
DELETE_FAILED = {"status": "DELETE_FAILED"}
SUCCESS = {"status": "SUCCESS"}


class RunnerContractError(ValueError):
    """Raised when the prompt envelope is malformed."""


class HelperCommandError(RuntimeError):
    """Raised when a helper command fails or returns invalid data."""


@dataclass(frozen=True)
class RunnerEnvelope:
    prompt: str
    original_comment_text: str
    target_page: str
    comment_identity: str

    @classmethod
    def from_stdin(cls) -> "RunnerEnvelope":
        try:
            payload = json.load(sys.stdin)
        except json.JSONDecodeError as exc:
            raise RunnerContractError("stdin must contain one JSON prompt envelope") from exc

        if not isinstance(payload, dict):
            raise RunnerContractError("prompt envelope must be a JSON object")

        prompt = _require_string(payload, "prompt")
        original_comment_text = _require_string(payload, "original_comment_text")
        target_page = _require_string(payload, "target_page")
        comment_identity = _require_string(payload, "comment_identity")

        return cls(
            prompt=prompt,
            original_comment_text=original_comment_text,
            target_page=target_page,
            comment_identity=comment_identity,
        )


def main(argv: list[str] | None = None) -> int:
    del argv

    try:
        envelope = RunnerEnvelope.from_stdin()
    except RunnerContractError as exc:
        print(str(exc), file=sys.stderr)
        json.dump(UPDATE_FAILED, sys.stdout, sort_keys=True)
        sys.stdout.write("\n")
        return 0

    try:
        _read_page(envelope.target_page)
        _save_page(envelope.target_page, envelope.prompt)
        confirmed_markdown = _read_page(envelope.target_page)
    except HelperCommandError as exc:
        print(str(exc), file=sys.stderr)
        json.dump(UPDATE_FAILED, sys.stdout, sort_keys=True)
        sys.stdout.write("\n")
        return 0

    if confirmed_markdown != envelope.prompt:
        print("saved page content did not match confirmation fetch", file=sys.stderr)
        json.dump(UPDATE_FAILED, sys.stdout, sort_keys=True)
        sys.stdout.write("\n")
        return 0

    try:
        _delete_comment(envelope.comment_identity, envelope.target_page)
        remaining_comments = _list_comments(envelope.target_page)
    except HelperCommandError as exc:
        print(str(exc), file=sys.stderr)
        json.dump(DELETE_FAILED, sys.stdout, sort_keys=True)
        sys.stdout.write("\n")
        return 0

    if any(comment.get("id") == envelope.comment_identity for comment in remaining_comments):
        print("source comment still present after delete confirmation", file=sys.stderr)
        json.dump(DELETE_FAILED, sys.stdout, sort_keys=True)
        sys.stdout.write("\n")
        return 0

    json.dump(SUCCESS, sys.stdout, sort_keys=True)
    sys.stdout.write("\n")
    return 0


def _read_page(target_page: str) -> str:
    result = _run_helper(["wikigo-page", "get", target_page])

    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise HelperCommandError("wikigo-page get emitted invalid JSON") from exc

    if not isinstance(payload, dict):
        raise HelperCommandError("wikigo-page get must return a JSON object")

    markdown = payload.get("markdown")
    if isinstance(markdown, str):
        return markdown

    content = payload.get("content")
    if isinstance(content, str):
        return content

    raise HelperCommandError("wikigo-page get response is missing markdown content")


def _save_page(target_page: str, markdown: str) -> None:
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".md", delete=False) as handle:
            handle.write(markdown)
            temp_path = Path(handle.name)

        _run_helper(["wikigo-page", "save", target_page, str(temp_path)])
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)


def _delete_comment(comment_identity: str, target_page: str) -> None:
    _run_helper(["wikigo-comments", "delete", comment_identity, target_page])


def _list_comments(target_page: str) -> list[dict[str, Any]]:
    result = _run_helper(["wikigo-comments", "list", target_page])

    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise HelperCommandError("wikigo-comments list emitted invalid JSON") from exc

    if not isinstance(payload, list):
        raise HelperCommandError("wikigo-comments list must return a JSON array")

    comments: list[dict[str, Any]] = []
    for item in payload:
        if isinstance(item, dict):
            comments.append(item)
    return comments


def _run_helper(argv: list[str]) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        argv,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        stderr = result.stderr.strip() or result.stdout.strip() or "no helper diagnostics"
        raise HelperCommandError(f"{argv[0]} failed: {stderr}")
    return result


def _require_string(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise RunnerContractError(f"prompt envelope field '{key}' must be a non-empty string")
    return value


if __name__ == "__main__":
    raise SystemExit(main())
