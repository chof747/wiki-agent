from __future__ import annotations

import logging

from wiki_agent.config import AppConfig


LOGGER = logging.getLogger(__name__)


class Worker:
    def __init__(self, config: AppConfig) -> None:
        self._config = config

    def run_once(self) -> None:
        LOGGER.info(
            "Worker boundary reached; job execution is not implemented yet.",
            extra={"event": "worker.run_once_not_implemented"},
        )

