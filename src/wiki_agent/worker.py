from __future__ import annotations

import logging

from wiki_agent.comment_jobs import CommentJobRepository
from wiki_agent.config import AppConfig
from wiki_agent.runner_client import RunnerClient, RunnerInvocationError


LOGGER = logging.getLogger(__name__)


class Worker:
    def __init__(
        self,
        config: AppConfig,
        *,
        repository: CommentJobRepository | None = None,
        runner_client: RunnerClient | None = None,
    ) -> None:
        self._config = config
        self._repository = repository or CommentJobRepository(config.postgres.dsn)
        self._runner_client = runner_client or RunnerClient(config.runner)

    def run_once(self) -> None:
        job = self._repository.claim_next_queued()
        if job is None:
            LOGGER.info(
                "Worker found no queued jobs.",
                extra={"event": "worker.no_queued_jobs"},
            )
            return

        LOGGER.info(
            "Worker claimed queued job.",
            extra={
                "event": "worker.job_claimed",
                "job_id": job.id,
                "comment_identity": job.comment_identity,
                "target_page": job.target_page,
            },
        )

        try:
            response = self._runner_client.invoke(job)
        except RunnerInvocationError as exc:
            self._repository.update_job_status(job.id, "UPDATE_FAILED", error_detail=str(exc))
            LOGGER.error(
                "Runner invocation failed.",
                extra={
                    "event": "worker.runner_failed",
                    "job_id": job.id,
                    "comment_identity": job.comment_identity,
                    "error": str(exc),
                },
            )
            return

        self._repository.update_job_status(job.id, response.status)
        LOGGER.info(
            "Worker finalized job from runner response.",
            extra={
                "event": "worker.job_finalized",
                "job_id": job.id,
                "comment_identity": job.comment_identity,
                "status": response.status,
                "runner_stderr": response.stderr.strip() or None,
            },
        )
