from __future__ import annotations

import logging
import threading

from wiki_agent.config import AppConfig
from wiki_agent.scanner import Scanner
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
            return_code = self._scanner.run_dry_run()
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
