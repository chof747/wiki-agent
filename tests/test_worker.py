from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path

from wiki_agent.comment_jobs import CommentJob
from wiki_agent.config import load_config
from wiki_agent.runner_client import RunnerInvocationError, RunnerResponse
from wiki_agent.worker import InvocationOutcome, Worker, WorkerRunResult


def test_worker_claims_job_and_persists_runner_status() -> None:
    repository = FakeRepository(job=_job())
    runner_client = FakeRunnerClient(response=RunnerResponse(status="DELETE_FAILED", payload={"status": "DELETE_FAILED"}, stderr="diagnostic\n"))

    worker = Worker(_config(), repository=repository, runner_client=runner_client)
    result = worker.run_once()

    assert result == WorkerRunResult(
        invocation=InvocationOutcome(
            job=repository.updated_jobs[-1],
            status="DELETE_FAILED",
            error_detail="diagnostic",
        )
    )
    assert repository.claimed is True
    assert repository.updated == [(1, "DELETE_FAILED", "diagnostic")]
    assert runner_client.jobs == [_job()]


def test_worker_maps_runner_invocation_failure_to_update_failed() -> None:
    repository = FakeRepository(job=_job())
    runner_client = FakeRunnerClient(error=RunnerInvocationError("runner emitted invalid JSON on stdout"))

    worker = Worker(_config(), repository=repository, runner_client=runner_client)
    result = worker.run_once()

    assert result == WorkerRunResult(
        invocation=InvocationOutcome(
            job=repository.updated_jobs[-1],
            status="UPDATE_FAILED",
            error_detail="runner emitted invalid JSON on stdout",
        )
    )
    assert repository.updated == [(1, "UPDATE_FAILED", "runner emitted invalid JSON on stdout")]


def test_worker_noops_when_queue_is_empty() -> None:
    repository = FakeRepository(job=None)
    runner_client = FakeRunnerClient(response=RunnerResponse(status="SUCCESS", payload={"status": "SUCCESS"}, stderr=""))

    worker = Worker(_config(), repository=repository, runner_client=runner_client)
    result = worker.run_once()

    assert result == WorkerRunResult(invocation=None)
    assert repository.updated == []
    assert runner_client.jobs == []


def test_worker_logs_reason_code_and_bounded_error_detail(caplog) -> None:
    repository = FakeRepository(job=_job())
    runner_client = FakeRunnerClient(
        response=RunnerResponse(
            status="REJECTED_WITH_COMMENT",
            payload={"status": "REJECTED_WITH_COMMENT", "reason_code": "CROSS_PAGE_REQUEST"},
            stderr="x" * 400,
        )
    )
    worker = Worker(_config(), repository=repository, runner_client=runner_client)

    with caplog.at_level(logging.INFO):
        worker.run_once()

    finalized = next(record for record in caplog.records if getattr(record, "event", None) == "worker.job_finalized")
    assert finalized.rejection_reason_code == "CROSS_PAGE_REQUEST"
    assert isinstance(finalized.error_detail, str)
    assert len(finalized.error_detail) <= 256
    assert finalized.error_detail.endswith("...")


def _config():
    return load_config(Path(__file__).parent / "fixtures" / "config.toml")


def _job() -> CommentJob:
    scanned_at = datetime(2026, 5, 24, 20, 0, tzinfo=UTC)
    return CommentJob(
        id=1,
        source_system="wiki-go",
        comment_identity="comment-1",
        target_page="/pages/example",
        original_comment_text="@marvin tighten intro",
        prompt="tighten intro",
        source_metadata={"source_system": "wiki-go", "author": "alice"},
        status="processing",
        receipt_count=1,
        first_scanned_at=scanned_at,
        last_scanned_at=scanned_at,
        claimed_at=scanned_at,
        completed_at=None,
        error_detail=None,
    )


class FakeRepository:
    def __init__(self, *, job: CommentJob | None) -> None:
        self._job = job
        self.claimed = False
        self.updated: list[tuple[int, str, str | None]] = []
        self.updated_jobs: list[CommentJob] = []

    def claim_next_queued(self) -> CommentJob | None:
        self.claimed = True
        return self._job

    def update_job_status(
        self,
        job_id: int,
        status: str,
        *,
        completed_at=None,
        error_detail: str | None = None,
    ) -> CommentJob:  # type: ignore[no-untyped-def]
        self.updated.append((job_id, status, error_detail))
        if self._job is None:
            raise AssertionError("update_job_status should not run without a claimed job")
        updated_job = CommentJob(
            id=self._job.id,
            source_system=self._job.source_system,
            comment_identity=self._job.comment_identity,
            target_page=self._job.target_page,
            original_comment_text=self._job.original_comment_text,
            prompt=self._job.prompt,
            source_metadata=self._job.source_metadata,
            status=status,
            receipt_count=self._job.receipt_count,
            first_scanned_at=self._job.first_scanned_at,
            last_scanned_at=self._job.last_scanned_at,
            claimed_at=self._job.claimed_at,
            completed_at=completed_at,
            error_detail=error_detail,
        )
        self.updated_jobs.append(updated_job)
        return updated_job


class FakeRunnerClient:
    def __init__(
        self,
        *,
        response: RunnerResponse | None = None,
        error: RunnerInvocationError | None = None,
    ) -> None:
        self._response = response
        self._error = error
        self.jobs: list[CommentJob] = []

    def invoke(self, job: CommentJob) -> RunnerResponse:
        self.jobs.append(job)
        if self._error is not None:
            raise self._error
        if self._response is None:
            raise AssertionError("fake runner client requires response or error")
        return self._response
