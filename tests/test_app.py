from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path

from wiki_agent.app import WikiAgentApp
from wiki_agent.comment_jobs import CommentJob, EnqueueResult
from wiki_agent.config import load_config
from wiki_agent.scanner import CommentEvent, ScannerError
from wiki_agent.worker import InvocationOutcome, WorkerRunResult


def test_run_exits_nonzero_when_singleton_lock_is_unavailable(caplog) -> None:
    config = load_config(_fixture_config_path())
    repository = FakeServiceRepository(lock=None)
    worker = FakeServiceWorker([])
    scanner = FakeScanner([])
    shutdown = FakeShutdownEvent([True])
    app = WikiAgentApp(
        config,
        scanner=scanner,
        worker=worker,
        repository=repository,
        shutdown_event=shutdown,
    )

    with caplog.at_level(logging.INFO):
        return_code = app.run()

    assert return_code == 1
    assert repository.schema_ensured is False
    assert repository.marked_stale == []
    assert scanner.scan_calls == 0
    assert worker.run_calls == 0
    assert shutdown.wait_calls == []
    assert _events(caplog.records) == ["service.singleton_lock_unavailable"]


def test_run_marks_stale_jobs_scans_and_drains_worker_until_queue_is_empty(caplog) -> None:
    config = load_config(_fixture_config_path())
    repository = FakeServiceRepository(lock=FakeLockHandle())
    worker = FakeServiceWorker(
        [
            WorkerRunResult(invocation=_invocation("comment-1", "UPDATE_FAILED")),
            WorkerRunResult(invocation=_invocation("comment-2", "SUCCESS")),
            WorkerRunResult(invocation=None),
        ]
    )
    scanner = FakeScanner([_event("comment-1"), _event("comment-2")])
    shutdown = FakeShutdownEvent([True])
    app = WikiAgentApp(
        config,
        scanner=scanner,
        worker=worker,
        repository=repository,
        shutdown_event=shutdown,
    )

    with caplog.at_level(logging.INFO):
        return_code = app.run()

    assert return_code == 0
    assert repository.schema_ensured is True
    assert repository.marked_stale == [timedelta(minutes=15)]
    assert repository.enqueued == ["comment-1", "comment-2"]
    assert scanner.scan_calls == 1
    assert worker.run_calls == 3
    assert shutdown.wait_calls == [60.0]
    assert repository.lock is not None
    assert repository.lock.released is True
    assert _events(caplog.records) == [
        "service.started",
        "scanner.enqueue_completed",
        "worker.drain_completed",
        "service.stopped",
    ]


def test_run_logs_already_processed_duplicate_count(caplog) -> None:
    config = load_config(_fixture_config_path())
    repository = FakeServiceRepository(lock=FakeLockHandle(), enqueue_actions=["already_processed"])
    worker = FakeServiceWorker([WorkerRunResult(invocation=None)])
    scanner = FakeScanner([_event("comment-1")])
    shutdown = FakeShutdownEvent([True])
    app = WikiAgentApp(
        config,
        scanner=scanner,
        worker=worker,
        repository=repository,
        shutdown_event=shutdown,
    )

    with caplog.at_level(logging.INFO):
        return_code = app.run()

    assert return_code == 0
    enqueue_summary = next(record for record in caplog.records if getattr(record, "event", None) == "scanner.enqueue_completed")
    assert enqueue_summary.already_processed_jobs == 1
    assert enqueue_summary.skipped_terminal_jobs == 0


def test_run_logs_skipped_terminal_duplicate_count(caplog) -> None:
    config = load_config(_fixture_config_path())
    repository = FakeServiceRepository(lock=FakeLockHandle(), enqueue_actions=["skipped_terminal"])
    worker = FakeServiceWorker([WorkerRunResult(invocation=None)])
    scanner = FakeScanner([_event("comment-1")])
    shutdown = FakeShutdownEvent([True])
    app = WikiAgentApp(
        config,
        scanner=scanner,
        worker=worker,
        repository=repository,
        shutdown_event=shutdown,
    )

    with caplog.at_level(logging.INFO):
        return_code = app.run()

    assert return_code == 0
    enqueue_summary = next(
        record for record in caplog.records if getattr(record, "event", None) == "scanner.enqueue_completed"
    )
    assert enqueue_summary.already_processed_jobs == 0
    assert enqueue_summary.skipped_terminal_jobs == 1


def test_run_logs_and_continues_after_scan_failure(caplog) -> None:
    config = load_config(_fixture_config_path())
    repository = FakeServiceRepository(lock=FakeLockHandle())
    worker = FakeServiceWorker([WorkerRunResult(invocation=None)])
    scanner = FakeScanner(error=ScannerError("boom"))
    shutdown = FakeShutdownEvent([True])
    app = WikiAgentApp(
        config,
        scanner=scanner,
        worker=worker,
        repository=repository,
        shutdown_event=shutdown,
    )

    with caplog.at_level(logging.INFO):
        return_code = app.run()

    assert return_code == 0
    assert repository.marked_stale == [timedelta(minutes=15)]
    assert worker.run_calls == 0
    assert _events(caplog.records) == [
        "service.started",
        "scanner.enqueue_failed",
        "service.stopped",
    ]


def _fixture_config_path() -> Path:
    return Path(__file__).parent / "fixtures" / "config.toml"


def _event(comment_identity: str) -> CommentEvent:
    return CommentEvent(
        comment_identity=comment_identity,
        target_page="/pages/example",
        original_comment_text=f"@marvin {comment_identity}",
        prompt=comment_identity,
        source_metadata={"source_system": "wiki-go", "author": "alice"},
    )


def _invocation(comment_identity: str, status: str) -> InvocationOutcome:
    scanned_at = datetime(2026, 5, 24, 20, 0, tzinfo=UTC)
    return InvocationOutcome(
        job=CommentJob(
            id=1,
            source_system="wiki-go",
            comment_identity=comment_identity,
            target_page="/pages/example",
            original_comment_text=f"@marvin {comment_identity}",
            prompt=comment_identity,
            source_metadata={"source_system": "wiki-go", "author": "alice"},
            status=status,
            receipt_count=1,
            first_scanned_at=scanned_at,
            last_scanned_at=scanned_at,
            claimed_at=scanned_at,
            completed_at=scanned_at,
            error_detail=None,
        ),
        status=status,
        error_detail=None,
    )


def _events(records: list[logging.LogRecord]) -> list[str]:
    return [record.event for record in records if hasattr(record, "event")]


class FakeServiceRepository:
    def __init__(self, *, lock: FakeLockHandle | None, enqueue_actions: list[str] | None = None) -> None:
        self.lock = lock
        self.schema_ensured = False
        self.marked_stale: list[timedelta] = []
        self.enqueued: list[str] = []
        self._enqueue_actions = list(enqueue_actions or [])

    def try_acquire_singleton_lock(self) -> FakeLockHandle | None:
        return self.lock

    def ensure_schema(self) -> None:
        self.schema_ensured = True

    def mark_stale_processing_jobs(self, *, now=None, processing_timeout: timedelta):  # type: ignore[no-untyped-def]
        self.marked_stale.append(processing_timeout)
        return 0

    def enqueue_event(self, event: CommentEvent, *, scanned_at=None):  # type: ignore[no-untyped-def]
        self.enqueued.append(event.comment_identity)
        scanned_at = datetime(2026, 5, 24, 20, 0, tzinfo=UTC)
        return EnqueueResult(
            action=self._enqueue_actions.pop(0) if self._enqueue_actions else "inserted",
            job=CommentJob(
                id=len(self.enqueued),
                source_system="wiki-go",
                comment_identity=event.comment_identity,
                target_page=event.target_page,
                original_comment_text=event.original_comment_text,
                prompt=event.prompt,
                source_metadata=event.source_metadata,
                status="queued",
                receipt_count=1,
                first_scanned_at=scanned_at,
                last_scanned_at=scanned_at,
                claimed_at=None,
                completed_at=None,
                error_detail=None,
            ),
        )


class FakeServiceWorker:
    def __init__(self, results: list[WorkerRunResult]) -> None:
        self._results = list(results)
        self.run_calls = 0

    def run_once(self) -> WorkerRunResult:
        self.run_calls += 1
        if not self._results:
            raise AssertionError("fake worker exhausted")
        return self._results.pop(0)


class FakeScanner:
    def __init__(
        self,
        events: list[CommentEvent] | None = None,
        *,
        error: ScannerError | None = None,
    ) -> None:
        self._events = events or []
        self._error = error
        self.scan_calls = 0

    def scan(self) -> list[CommentEvent]:
        self.scan_calls += 1
        if self._error is not None:
            raise self._error
        return list(self._events)


class FakeShutdownEvent:
    def __init__(self, results: list[bool]) -> None:
        self._results = list(results)
        self.wait_calls: list[float] = []
        self._is_set = False

    def wait(self, timeout: float | None = None) -> bool:
        if timeout is not None:
            self.wait_calls.append(timeout)
        if not self._results:
            return True
        return self._results.pop(0)

    def set(self) -> None:
        self._is_set = True
        self._results = [True]

    def is_set(self) -> bool:
        return self._is_set


class FakeLockHandle:
    def __init__(self) -> None:
        self.released = False

    def release(self) -> None:
        self.released = True
