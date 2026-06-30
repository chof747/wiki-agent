from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from wiki_agent.comment_jobs import CommentJob
from wiki_agent.config import load_config
from wiki_agent.failure_feedback import TerminalFailureFeedback


def test_update_failed_creates_visible_failure_comment() -> None:
    comments: list[dict[str, str]] = []
    created: list[tuple[str, str]] = []

    def list_comments(_page: str) -> list[dict[str, str]]:
        return list(comments)

    def create_comment(page: str, content: str) -> None:
        created.append((page, content))
        comments.append({"id": "comment-created-1", "text": content})

    feedback = TerminalFailureFeedback(
        _config(),
        list_comments=list_comments,
        create_comment=create_comment,
    )

    result = feedback.ensure_for_job(_job(status="UPDATE_FAILED", error_detail="runner timed out"))

    assert result.action == "created"
    assert created == [
        (
            "/pages/example",
            '<!-- wiki-agent:failure source_comment_id="comment-1" status="UPDATE_FAILED" reason="runner timed out" -->\n\n'
            'Marvin could not complete this request (`UPDATE_FAILED`).\n\n'
            'Reason: runner timed out\n\n'
            'Next step: Review the problem and post a new comment if you want Marvin to try again.\n',
        )
    ]


def test_matching_failure_comment_is_not_duplicated() -> None:
    existing_comment = (
        '<!-- wiki-agent:failure source_comment_id="comment-1" status="UPDATE_FAILED" reason="runner timed out" -->\n\n'
        'Marvin could not complete this request (`UPDATE_FAILED`).\n\n'
        'Reason: runner timed out\n\n'
        'Next step: Review the problem and post a new comment if you want Marvin to try again.\n'
    )
    created: list[tuple[str, str]] = []
    feedback = TerminalFailureFeedback(
        _config(),
        list_comments=lambda _page: [{"id": "comment-created-1", "text": existing_comment}],
        create_comment=lambda page, content: created.append((page, content)),
    )

    result = feedback.ensure_for_job(_job(status="UPDATE_FAILED", error_detail="runner timed out"))

    assert result.action == "already_present"
    assert created == []


def test_delete_failed_after_rejection_does_not_create_second_failure_comment() -> None:
    created: list[tuple[str, str]] = []
    rejection_comment = (
        '<!-- wiki-agent:rejection source_comment_id="comment-1" reason_code="CROSS_PAGE_REQUEST" -->\n\n'
        'Marvin could not process this request.\n'
    )
    feedback = TerminalFailureFeedback(
        _config(),
        list_comments=lambda _page: [{"id": "comment-created-1", "text": rejection_comment}],
        create_comment=lambda page, content: created.append((page, content)),
    )

    result = feedback.ensure_for_job(_job(status="DELETE_FAILED", error_detail="source comment still present"))

    assert result.action == "not_required"
    assert created == []


def test_delete_failed_after_update_creates_failure_comment() -> None:
    comments: list[dict[str, str]] = []
    created: list[tuple[str, str]] = []

    def list_comments(_page: str) -> list[dict[str, str]]:
        return list(comments)

    def create_comment(page: str, content: str) -> None:
        created.append((page, content))
        comments.append({"id": "comment-created-1", "text": content})

    feedback = TerminalFailureFeedback(
        _config(),
        list_comments=list_comments,
        create_comment=create_comment,
    )

    result = feedback.ensure_for_job(_job(status="DELETE_FAILED", error_detail="source comment still present"))

    assert result.action == "created"
    assert created == [
        (
            "/pages/example",
            '<!-- wiki-agent:failure source_comment_id="comment-1" status="DELETE_FAILED" reason="source comment still present" -->\n\n'
            'Marvin could not complete this request (`DELETE_FAILED`).\n\n'
            'Reason: source comment still present\n\n'
            'Next step: Review the page update and remove the original source comment manually if needed.\n',
        )
    ]


def _config():
    return load_config(Path(__file__).parent / "fixtures" / "config.toml")


def _job(*, status: str, error_detail: str | None) -> CommentJob:
    scanned_at = datetime(2026, 5, 24, 20, 0, tzinfo=UTC)
    return CommentJob(
        id=1,
        source_system="wiki-go",
        comment_identity="comment-1",
        target_page="/pages/example",
        original_comment_text="@marvin tighten intro",
        prompt="tighten intro",
        source_metadata={"source_system": "wiki-go", "author": "alice"},
        status=status,
        receipt_count=1,
        first_scanned_at=scanned_at,
        last_scanned_at=scanned_at,
        claimed_at=scanned_at,
        completed_at=scanned_at,
        error_detail=error_detail,
    )
