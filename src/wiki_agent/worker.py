from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from wiki_agent.comment_jobs import CommentJobRepository
from wiki_agent.config import AppConfig
from wiki_agent.domain import STATUS_UPDATE_FAILED
from wiki_agent.runner_client import RunnerClient, RunnerInvocationError

if TYPE_CHECKING:
    from wiki_agent.comment_jobs import CommentJob


LOGGER = logging.getLogger(__name__)
MAX_ERROR_DETAIL_LENGTH = 256


@dataclass(frozen=True)
class InvocationOutcome:
    job: "CommentJob"
    status: str
    error_detail: str | None


@dataclass(frozen=True)
class WorkerRunResult:
    invocation: InvocationOutcome | None


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

    def run_once(self) -> WorkerRunResult:
        job = self._repository.claim_next_queued()
        if job is None:
            LOGGER.info(
                "Worker found no queued jobs.",
                extra={"event": "worker.no_queued_jobs"},
            )
            return WorkerRunResult(invocation=None)

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
            error_detail = _bounded_error_detail(str(exc))
            result = self._finalize_job(job.id, STATUS_UPDATE_FAILED, error_detail=error_detail)
            LOGGER.error(
                "Runner invocation failed.",
                extra={
                    "event": "worker.runner_failed",
                    "job_id": job.id,
                    "comment_identity": job.comment_identity,
                    "status": STATUS_UPDATE_FAILED,
                    "error_detail": error_detail,
                },
            )
            return result

        error_detail = _bounded_error_detail(response.stderr)
        rejection_reason_code = response.payload.get("reason_code")
        result = self._finalize_job(job.id, response.status, error_detail=error_detail)
        LOGGER.info(
            "Worker finalized job from runner response.",
            extra={
                "event": "worker.job_finalized",
                "job_id": job.id,
                "comment_identity": job.comment_identity,
                "status": response.status,
                "rejection_reason_code": rejection_reason_code,
                "error_detail": error_detail,
            },
        )
        return result

    def _finalize_job(
        self,
        job_id: int,
        status: str,
        *,
        error_detail: str | None,
    ) -> WorkerRunResult:
        finalized_job = self._repository.update_job_status(
            job_id,
            status,
            error_detail=error_detail,
        )
        return WorkerRunResult(
            invocation=InvocationOutcome(
                job=finalized_job,
                status=status,
                error_detail=error_detail,
            )
        )


def _bounded_error_detail(value: str) -> str | None:
    stripped = value.strip()
    if not stripped:
        return None
    if len(stripped) <= MAX_ERROR_DETAIL_LENGTH:
        return stripped
    return f"{stripped[: MAX_ERROR_DETAIL_LENGTH - 3]}..."
