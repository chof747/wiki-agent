from __future__ import annotations

import json
import logging
import sys
import threading
from typing import TYPE_CHECKING

from wiki_agent.comment_jobs import CommentJobRepository
from wiki_agent.config import AppConfig
from wiki_agent.scanner import Scanner, ScannerError
from wiki_agent.worker import Worker

if TYPE_CHECKING:
    from wiki_agent.comment_jobs import EnqueueResult


LOGGER = logging.getLogger(__name__)


class WikiAgentApp:
    def __init__(
        self,
        config: AppConfig,
        *,
        scanner: Scanner | None = None,
        worker: Worker | None = None,
        repository: CommentJobRepository | None = None,
    ) -> None:
        self._config = config
        self._scanner = scanner or Scanner(config)
        self._repository = repository or CommentJobRepository(config.postgres.dsn)
        self._worker = worker or Worker(config, repository=self._repository)
        self._shutdown = threading.Event()

    def run(self) -> int:
        LOGGER.info(
            "Wiki Agent service started.",
            extra={"event": "service.started"},
        )
        while not self._shutdown.wait(timeout=1):
            continue
        LOGGER.info(
            "Wiki Agent service stopped.",
            extra={"event": "service.stopped"},
        )
        return 0

    def run_once(self, *, dry_run: bool = False) -> int:
        LOGGER.info(
            "Wiki Agent one-shot execution started.",
            extra={"event": "service.run_once_started"},
        )
        if dry_run:
            try:
                comment_events = self._scanner.dry_run()
            except ScannerError as exc:
                LOGGER.error(
                    "Scanner dry-run failed.",
                    extra={"event": "scanner.dry_run_failed", "error": str(exc)},
                )
                return 1

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
            return_code = 0
        else:
            try:
                self._repository.ensure_schema()
                enqueue_results = [
                    self._repository.enqueue_event(event)
                    for event in self._scanner.scan()
                ]
            except ScannerError as exc:
                LOGGER.error(
                    "Scanner enqueue pass failed.",
                    extra={"event": "scanner.enqueue_failed", "error": str(exc)},
                )
                return 1

            _log_enqueue_summary(enqueue_results)
            self._worker.run_once()
            return_code = 0
        LOGGER.info(
            "Wiki Agent one-shot execution finished.",
            extra={"event": "service.run_once_finished"},
        )
        return return_code

    def request_shutdown(self) -> None:
        self._shutdown.set()


def _log_enqueue_summary(results: list["EnqueueResult"]) -> None:
    inserted = sum(1 for result in results if result.action == "inserted")
    refreshed = sum(1 for result in results if result.action == "refreshed")
    skipped_terminal = sum(1 for result in results if result.action == "skipped_terminal")
    LOGGER.info(
        "Scanner enqueue pass completed.",
        extra={
            "event": "scanner.enqueue_completed",
            "eligible_comment_events": len(results),
            "inserted_jobs": inserted,
            "refreshed_jobs": refreshed,
            "skipped_terminal_jobs": skipped_terminal,
        },
    )
