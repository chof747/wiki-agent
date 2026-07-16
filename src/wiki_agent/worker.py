from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from wiki_agent.contracts.runner_client import RunnerClient, RunnerInvocationError
from wiki_agent.domain import STATUS_UPDATE_FAILED
from wiki_agent.failure_feedback import TerminalFailureFeedback
from wiki_agent.jobs.comment_jobs import CommentJobRepository
from wiki_agent.ops.config import AppConfig

if TYPE_CHECKING:
    from wiki_agent.jobs.comment_jobs import CommentJob


LOGGER = logging.getLogger(__name__)
MAX_ERROR_DETAIL_LENGTH = 256
RUNNER_DIAGNOSTIC_EVENTS = {
    "runner.web_search_actions",
    "runner.web_search_output",
    "runner.web_research_budget_usage",
}


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
        failure_feedback: TerminalFailureFeedback | None = None,
    ) -> None:
        self._config = config
        self._repository = repository or CommentJobRepository(config.postgres.dsn)
        self._runner_client = runner_client or RunnerClient(config.runner)
        self._failure_feedback = failure_feedback or TerminalFailureFeedback(config)

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

        _log_runner_diagnostics(response.stderr, job=job)
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
        self._failure_feedback.ensure_for_job(finalized_job)
        return WorkerRunResult(
            invocation=InvocationOutcome(
                job=finalized_job,
                status=status,
                error_detail=error_detail,
            )
        )


def _bounded_error_detail(value: str) -> str | None:
    stripped = _prefer_user_facing_error_line(value)
    if not stripped:
        return None
    if len(stripped) <= MAX_ERROR_DETAIL_LENGTH:
        return stripped
    return f"{stripped[: MAX_ERROR_DETAIL_LENGTH - 3]}..."


def _prefer_user_facing_error_line(value: str) -> str:
    lines = [line.strip() for line in value.splitlines() if line.strip()]
    if not lines:
        return ""

    for line in reversed(lines):
        if _is_runner_diagnostic_event(line):
            continue
        return line

    return ""


def _is_runner_diagnostic_event(line: str) -> bool:
    return _runner_diagnostic_payload(line) is not None


def _runner_diagnostic_payload(line: str) -> dict[str, object] | None:
    try:
        payload = json.loads(line)
    except json.JSONDecodeError:
        return None

    if not isinstance(payload, dict):
        return None

    return payload if payload.get("event") in RUNNER_DIAGNOSTIC_EVENTS else None


def _log_runner_diagnostics(stderr: str, *, job: "CommentJob") -> None:
    for line in stderr.splitlines():
        payload = _runner_diagnostic_payload(line.strip())
        if payload is None:
            continue

        extra = dict(payload)
        extra["job_id"] = job.id
        extra["comment_identity"] = job.comment_identity
        LOGGER.info("Runner diagnostic event.", extra=extra)
