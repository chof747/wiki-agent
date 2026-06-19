from __future__ import annotations

import json
import logging
import sys
import threading
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from wiki_agent.comment_jobs import CommentJobRepository
from wiki_agent.config import AppConfig
from wiki_agent.domain import STATUS_UPDATE_FAILED
from wiki_agent.scanner import Scanner, ScannerError
from wiki_agent.worker import Worker, WorkerRunResult

if TYPE_CHECKING:
    from wiki_agent.comment_jobs import EnqueueResult
    from wiki_agent.scanner import CommentEvent


LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class CommentAgentCycle:
    enqueue_results: list["EnqueueResult"]
    worker_run_result: WorkerRunResult


class WikiAgentApp:
    def __init__(
        self,
        config: AppConfig,
        *,
        scanner: Scanner | None = None,
        worker: Worker | None = None,
        repository: CommentJobRepository | None = None,
        shutdown_event: threading.Event | None = None,
    ) -> None:
        self._config = config
        self._scanner = scanner or Scanner(config)
        self._repository = repository or CommentJobRepository(config.postgres.dsn)
        self._worker = worker or Worker(config, repository=self._repository)
        self._shutdown = shutdown_event or threading.Event()

    def run(self) -> int:
        lock = self._repository.try_acquire_singleton_lock()
        if lock is None:
            LOGGER.error(
                "Wiki Agent service could not acquire the singleton advisory lock.",
                extra={"event": "service.singleton_lock_unavailable"},
            )
            return 1

        self._repository.ensure_schema()
        LOGGER.info(
            "Wiki Agent service started.",
            extra={"event": "service.started"},
        )
        try:
            while True:
                self._run_service_cycle()
                if self._shutdown.wait(timeout=self._config.service.scan_interval.total_seconds()):
                    break
        finally:
            lock.release()
            LOGGER.info(
                "Wiki Agent service stopped.",
                extra={"event": "service.stopped"},
            )
        return 0

    def run_comment_agent_cycle(self) -> CommentAgentCycle:
        return self._run_comment_agent_cycle(self._scanner.scan())

    def run_once(self, *, dry_run: bool = False) -> int:
        LOGGER.info(
            "Wiki Agent one-shot execution started.",
            extra={"event": "service.run_once_started"},
        )
        try:
            comment_events = self._scanner.scan()
        except ScannerError as exc:
            _log_scan_failure(dry_run=dry_run, error=exc)
            return 1

        if dry_run:
            self._emit_dry_run_output(comment_events)
        else:
            self._run_comment_agent_cycle(comment_events)
        LOGGER.info(
            "Wiki Agent one-shot execution finished.",
            extra={"event": "service.run_once_finished"},
        )
        return 0

    def request_shutdown(self) -> None:
        self._shutdown.set()

    def _run_service_cycle(self) -> None:
        stale_count = self._repository.mark_stale_processing_jobs(
            now=datetime.now(tz=UTC),
            processing_timeout=self._config.service.stale_processing_timeout,
        )
        if stale_count:
            LOGGER.warning(
                "Service marked stale processing jobs terminal.",
                extra={
                    "event": "worker.stale_processing_marked",
                    "stale_processing_jobs": stale_count,
                    "status": STATUS_UPDATE_FAILED,
                    "error_detail": "stale processing timeout",
                },
            )

        try:
            comment_events = self._scanner.scan()
        except ScannerError as exc:
            _log_scan_failure(dry_run=False, error=exc)
            return

        enqueue_results = [self._repository.enqueue_event(event) for event in comment_events]
        _log_enqueue_summary(enqueue_results)
        self._drain_worker()

    def _run_comment_agent_cycle(self, comment_events: list["CommentEvent"]) -> CommentAgentCycle:
        self._repository.ensure_schema()
        enqueue_results = [self._repository.enqueue_event(event) for event in comment_events]
        _log_enqueue_summary(enqueue_results)
        worker_run_result = self._worker.run_once()
        return CommentAgentCycle(
            enqueue_results=enqueue_results,
            worker_run_result=worker_run_result,
        )

    def _emit_dry_run_output(self, comment_events: list["CommentEvent"]) -> None:
        json.dump(
            {"comment_events": [event.as_dict() for event in comment_events]},
            sys.stdout,
            sort_keys=True,
        )
        sys.stdout.write("\n")
        LOGGER.info(
            "Scanner dry-run completed.",
            extra={
                "event": "scanner.dry_run_completed",
                "eligible_comment_events": len(comment_events),
            },
        )

    def _drain_worker(self) -> None:
        processed_jobs = 0
        while not self._shutdown_requested():
            worker_run_result = self._worker.run_once()
            if worker_run_result.invocation is None:
                break
            processed_jobs += 1
        LOGGER.info(
            "Worker drain pass completed.",
            extra={"event": "worker.drain_completed", "processed_jobs": processed_jobs},
        )

    def _shutdown_requested(self) -> bool:
        is_set = getattr(self._shutdown, "is_set", None)
        if callable(is_set):
            return bool(is_set())
        return False


def _log_enqueue_summary(results: list["EnqueueResult"]) -> None:
    already_processed = sum(1 for result in results if result.action == "already_processed")
    inserted = sum(1 for result in results if result.action == "inserted")
    refreshed = sum(1 for result in results if result.action == "refreshed")
    receipt_refreshed = sum(1 for result in results if result.action == "receipt_refreshed")
    skipped_terminal = sum(1 for result in results if result.action == "skipped_terminal")
    LOGGER.info(
        "Scanner enqueue pass completed.",
        extra={
            "event": "scanner.enqueue_completed",
            "eligible_comment_events": len(results),
            "already_processed_jobs": already_processed,
            "inserted_jobs": inserted,
            "refreshed_jobs": refreshed,
            "receipt_refreshed_jobs": receipt_refreshed,
            "skipped_terminal_jobs": skipped_terminal,
        },
    )


def _log_scan_failure(*, dry_run: bool, error: ScannerError) -> None:
    event = "scanner.dry_run_failed" if dry_run else "scanner.enqueue_failed"
    message = "Scanner dry-run failed." if dry_run else "Scanner enqueue pass failed."
    LOGGER.error(
        message,
        extra={"event": event, "error": str(error)},
    )
