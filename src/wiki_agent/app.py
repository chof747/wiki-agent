from __future__ import annotations

import json
import logging
import sys
import threading

from wiki_agent.config import AppConfig
from wiki_agent.scanner import Scanner, ScannerError
from wiki_agent.worker import Worker


LOGGER = logging.getLogger(__name__)


class WikiAgentApp:
    def __init__(self, config: AppConfig) -> None:
        self._config = config
        self._scanner = Scanner(config)
        self._worker = Worker(config)
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
            self._worker.run_once()
            return_code = 0
        LOGGER.info(
            "Wiki Agent one-shot execution finished.",
            extra={"event": "service.run_once_finished"},
        )
        return return_code

    def request_shutdown(self) -> None:
        self._shutdown.set()
