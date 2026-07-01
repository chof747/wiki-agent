from __future__ import annotations

import html
import logging
import re
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

from wiki_agent.domain import STATUS_DELETE_FAILED, STATUS_UPDATE_FAILED
from wiki_agent.wikigo_adapter import WikiGoAdapterError, parse_helper_comments_output

if TYPE_CHECKING:
    from wiki_agent.comment_jobs import CommentJob
    from wiki_agent.config import AppConfig


LOGGER = logging.getLogger(__name__)
FAILURE_MARKER = "wiki-agent:failure"
REJECTION_MARKER = "wiki-agent:rejection"
SOURCE_COMMENT_ATTR = "source_comment_id"
STATUS_ATTR = "status"
REASON_ATTR = "reason"
_MARKER_ATTR_RE = re.compile(r'([a-z_]+)="([^"]*)"')


class FeedbackCommandError(RuntimeError):
    """Raised when a comment helper command fails or returns invalid data."""


@dataclass(frozen=True)
class FailureFeedbackResult:
    action: str


class TerminalFailureFeedback:
    def __init__(
        self,
        config: "AppConfig",
        *,
        list_comments: Callable[[str], list[dict[str, Any]]] | None = None,
        create_comment: Callable[[str, str], None] | None = None,
    ) -> None:
        self._bot_name = _display_bot_name(config.bot_name)
        self._list_comments = list_comments or _list_comments
        self._create_comment = create_comment or _create_comment

    def ensure_for_job(self, job: "CommentJob") -> FailureFeedbackResult:
        if job.status not in {STATUS_UPDATE_FAILED, STATUS_DELETE_FAILED}:
            return FailureFeedbackResult(action="not_required")

        try:
            existing_comments = self._list_comments(job.target_page)
        except FeedbackCommandError:
            LOGGER.warning(
                "Failure comment check failed.",
                extra=_feedback_log_extra("failure_feedback.check_failed", job),
            )
            return FailureFeedbackResult(action="check_failed")

        if job.status == STATUS_DELETE_FAILED and _has_matching_rejection_comment(existing_comments, job.comment_identity):
            LOGGER.info(
                "Failure comment not required because a rejection comment already explains the outcome.",
                extra=_feedback_log_extra("failure_feedback.not_required", job),
            )
            return FailureFeedbackResult(action="not_required")

        if _has_matching_failure_comment(existing_comments, job.comment_identity, job.status):
            LOGGER.info(
                "Failure comment already present.",
                extra=_feedback_log_extra("failure_feedback.already_present", job),
            )
            return FailureFeedbackResult(action="already_present")

        comment = _build_failure_comment(
            bot_name=self._bot_name,
            comment_identity=job.comment_identity,
            status=job.status,
            reason=job.error_detail,
        )
        try:
            self._create_comment(job.target_page, comment)
        except FeedbackCommandError:
            LOGGER.warning(
                "Failure comment creation failed.",
                extra=_feedback_log_extra("failure_feedback.create_failed", job),
            )
            return FailureFeedbackResult(action="create_failed")

        try:
            confirmed_comments = self._list_comments(job.target_page)
        except FeedbackCommandError:
            LOGGER.warning(
                "Failure comment confirmation failed.",
                extra=_feedback_log_extra("failure_feedback.confirmation_failed", job),
            )
            return FailureFeedbackResult(action="confirmation_failed")

        expected = comment.strip()
        if not any(isinstance(item.get("text"), str) and item["text"].strip() == expected for item in confirmed_comments):
            LOGGER.warning(
                "Failure comment confirmation failed.",
                extra=_feedback_log_extra("failure_feedback.confirmation_failed", job),
            )
            return FailureFeedbackResult(action="confirmation_failed")

        LOGGER.info(
            "Failure comment created.",
            extra=_feedback_log_extra("failure_feedback.created", job),
        )
        return FailureFeedbackResult(action="created")


def _build_failure_comment(*, bot_name: str, comment_identity: str, status: str, reason: str | None) -> str:
    visible_reason = (reason or "no additional details available").strip()
    next_step = (
        "Review the page update and remove the original source comment manually if needed."
        if status == STATUS_DELETE_FAILED
        else "Review the problem and post a new comment if you want Marvin to try again."
    )
    escaped_reason = html.escape(visible_reason, quote=True)
    return (
        f'<!-- {FAILURE_MARKER} {SOURCE_COMMENT_ATTR}="{comment_identity}" {STATUS_ATTR}="{status}" '
        f'{REASON_ATTR}="{escaped_reason}" -->\n\n'
        f"{bot_name} could not complete this request (`{status}`).\n\n"
        f"Reason: {visible_reason}\n\n"
        f"Next step: {next_step}\n"
    )


def _has_matching_failure_comment(comments: list[dict[str, Any]], comment_identity: str, status: str) -> bool:
    for comment in comments:
        marker = _parse_marker(str(comment.get("text", "")), FAILURE_MARKER)
        if marker.get(SOURCE_COMMENT_ATTR) == comment_identity and marker.get(STATUS_ATTR) == status:
            return True
    return False


def _has_matching_rejection_comment(comments: list[dict[str, Any]], comment_identity: str) -> bool:
    for comment in comments:
        marker = _parse_marker(str(comment.get("text", "")), REJECTION_MARKER)
        if marker.get(SOURCE_COMMENT_ATTR) == comment_identity:
            return True
    return False


def _parse_marker(text: str, marker_name: str) -> dict[str, str]:
    marker_start = f"<!-- {marker_name} "
    marker_end = "-->"
    start = text.find(marker_start)
    if start == -1:
        return {}
    end = text.find(marker_end, start)
    if end == -1:
        return {}
    raw_attributes = text[start + len(marker_start) : end]
    return {key: value for key, value in _MARKER_ATTR_RE.findall(raw_attributes)}


def _display_bot_name(bot_name: str) -> str:
    stripped = bot_name.strip()
    if not stripped:
        return "Bot"
    return stripped[:1].upper() + stripped[1:]


def _feedback_log_extra(event: str, job: "CommentJob") -> dict[str, Any]:
    return {
        "event": event,
        "job_id": job.id,
        "comment_identity": job.comment_identity,
        "status": job.status,
        "target_page": job.target_page,
        "error_detail": job.error_detail,
    }


def _list_comments(target_page: str) -> list[dict[str, Any]]:
    result = _run_helper(["wikigo-comments", "list", target_page])
    try:
        return parse_helper_comments_output(result.stdout)
    except WikiGoAdapterError as exc:
        raise FeedbackCommandError(str(exc)) from exc


def _create_comment(target_page: str, content: str) -> None:
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".md", delete=False) as handle:
            handle.write(content)
            temp_path = Path(handle.name)
        _run_helper(["wikigo-comments", "create", target_page, str(temp_path)])
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)


def _run_helper(argv: list[str]) -> subprocess.CompletedProcess[str]:
    try:
        result = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError as exc:
        raise FeedbackCommandError(f"{argv[0]} executable was not found") from exc
    if result.returncode != 0:
        stderr = result.stderr.strip() or result.stdout.strip() or "no helper diagnostics"
        raise FeedbackCommandError(f"{argv[0]} failed: {stderr}")
    return result
