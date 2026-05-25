from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from wiki_agent.app import WikiAgentApp
from wiki_agent.comment_jobs import CommentJob, CommentJobRepository, EnqueueResult
from wiki_agent.config import load_config
from wiki_agent.scanner import CommentEvent


def test_repository_ensure_schema_runs_idempotent_ddl() -> None:
    database = FakeDatabase()
    repository = CommentJobRepository(
        "postgresql://example:test@localhost:5432/wiki_agent",
        connect=database.connect,
    )

    repository.ensure_schema()
    repository.ensure_schema()

    ddl_statements = [query for query, _params in database.executed if query.startswith("CREATE ")]
    assert ddl_statements == [
        "CREATE TABLE IF NOT EXISTS comment_jobs (",
        "CREATE INDEX IF NOT EXISTS comment_jobs_queued_idx ON comment_jobs (status, id)",
        "CREATE INDEX IF NOT EXISTS comment_jobs_processing_idx ON comment_jobs (status, claimed_at)",
        "CREATE TABLE IF NOT EXISTS comment_jobs (",
        "CREATE INDEX IF NOT EXISTS comment_jobs_queued_idx ON comment_jobs (status, id)",
        "CREATE INDEX IF NOT EXISTS comment_jobs_processing_idx ON comment_jobs (status, claimed_at)",
    ]


def test_repository_enqueue_refreshes_duplicate_without_second_row() -> None:
    database = FakeDatabase()
    repository = CommentJobRepository(
        "postgresql://example:test@localhost:5432/wiki_agent",
        connect=database.connect,
    )
    first_seen = datetime(2026, 5, 24, 20, 0, tzinfo=UTC)
    second_seen = first_seen + timedelta(minutes=5)

    inserted = repository.enqueue_event(
        _event(comment_identity="comment-1", prompt="tighten intro"),
        scanned_at=first_seen,
    )
    refreshed = repository.enqueue_event(
        _event(
            comment_identity="comment-1",
            prompt="tighten intro again",
            original_comment_text="@marvin tighten intro again",
            source_metadata={"source_system": "wiki-go", "author": "alice", "edit_count": 2},
        ),
        scanned_at=second_seen,
    )

    assert inserted.action == "inserted"
    assert refreshed.action == "refreshed"
    assert len(database.rows) == 1
    row = database.rows[0]
    assert row["status"] == "queued"
    assert row["receipt_count"] == 2
    assert row["first_scanned_at"] == first_seen
    assert row["last_scanned_at"] == second_seen
    assert row["prompt"] == "tighten intro again"
    assert row["original_comment_text"] == "@marvin tighten intro again"
    assert row["source_metadata"]["edit_count"] == 2


def test_repository_enqueue_keeps_terminal_job_terminal() -> None:
    database = FakeDatabase()
    repository = CommentJobRepository(
        "postgresql://example:test@localhost:5432/wiki_agent",
        connect=database.connect,
    )
    first_seen = datetime(2026, 5, 24, 20, 0, tzinfo=UTC)
    second_seen = first_seen + timedelta(minutes=10)

    inserted = repository.enqueue_event(_event(comment_identity="comment-1"), scanned_at=first_seen)
    repository.update_job_status(inserted.job.id, "UPDATE_FAILED", completed_at=first_seen + timedelta(minutes=1))
    skipped = repository.enqueue_event(
        _event(comment_identity="comment-1", prompt="retry this"),
        scanned_at=second_seen,
    )

    assert skipped.action == "skipped_terminal"
    assert len(database.rows) == 1
    row = database.rows[0]
    assert row["status"] == "UPDATE_FAILED"
    assert row["receipt_count"] == 2
    assert row["last_scanned_at"] == second_seen
    assert row["prompt"] == "retry this"


def test_repository_claims_queued_jobs_in_fifo_order() -> None:
    database = FakeDatabase()
    repository = CommentJobRepository(
        "postgresql://example:test@localhost:5432/wiki_agent",
        connect=database.connect,
    )
    scanned_at = datetime(2026, 5, 24, 20, 0, tzinfo=UTC)
    repository.enqueue_event(_event(comment_identity="comment-1"), scanned_at=scanned_at)
    repository.enqueue_event(_event(comment_identity="comment-2"), scanned_at=scanned_at + timedelta(seconds=5))

    first_claim = repository.claim_next_queued(claimed_at=scanned_at + timedelta(minutes=1))
    second_claim = repository.claim_next_queued(claimed_at=scanned_at + timedelta(minutes=2))

    assert first_claim is not None
    assert second_claim is not None
    assert first_claim.comment_identity == "comment-1"
    assert second_claim.comment_identity == "comment-2"
    assert first_claim.status == "processing"
    assert second_claim.status == "processing"


def test_repository_marks_stale_processing_jobs_failed() -> None:
    database = FakeDatabase()
    repository = CommentJobRepository(
        "postgresql://example:test@localhost:5432/wiki_agent",
        connect=database.connect,
    )
    scanned_at = datetime(2026, 5, 24, 20, 0, tzinfo=UTC)
    repository.enqueue_event(_event(comment_identity="comment-1"), scanned_at=scanned_at)
    repository.claim_next_queued(claimed_at=scanned_at + timedelta(minutes=1))

    marked = repository.mark_stale_processing_jobs(
        now=scanned_at + timedelta(minutes=20),
        processing_timeout=timedelta(minutes=15),
    )

    assert marked == 1
    counts = repository.get_counts()
    assert counts.queued == 0
    assert counts.processing == 0
    assert counts.by_status["UPDATE_FAILED"] == 1


def test_repository_returns_queue_and_status_counts() -> None:
    database = FakeDatabase()
    repository = CommentJobRepository(
        "postgresql://example:test@localhost:5432/wiki_agent",
        connect=database.connect,
    )
    scanned_at = datetime(2026, 5, 24, 20, 0, tzinfo=UTC)
    first = repository.enqueue_event(_event(comment_identity="comment-1"), scanned_at=scanned_at)
    repository.enqueue_event(_event(comment_identity="comment-2"), scanned_at=scanned_at + timedelta(seconds=5))
    repository.claim_next_queued(claimed_at=scanned_at + timedelta(minutes=1))
    repository.update_job_status(first.job.id, "SUCCESS", completed_at=scanned_at + timedelta(minutes=2))

    counts = repository.get_counts()

    assert counts.queued == 1
    assert counts.processing == 0
    assert counts.by_status == {"SUCCESS": 1, "queued": 1}


def test_run_once_scans_and_enqueues_before_worker() -> None:
    config = load_config(_fixture_config_path())
    repository = FakeRepository()
    worker = FakeWorker()
    scanner = FakeScanner([_event(comment_identity="comment-1"), _event(comment_identity="comment-2")])
    app = WikiAgentApp(config, scanner=scanner, worker=worker, repository=repository)

    result = app.run_once(dry_run=False)

    assert result == 0
    assert repository.schema_ensured is True
    assert [event.comment_identity for event in repository.enqueued] == ["comment-1", "comment-2"]
    assert worker.run_calls == 1


def _event(
    *,
    comment_identity: str,
    prompt: str = "tighten intro",
    target_page: str = "/pages/example",
    original_comment_text: str = "@marvin tighten intro",
    source_metadata: dict[str, Any] | None = None,
) -> CommentEvent:
    return CommentEvent(
        comment_identity=comment_identity,
        target_page=target_page,
        original_comment_text=original_comment_text,
        prompt=prompt,
        source_metadata=source_metadata or {"source_system": "wiki-go", "author": "alice"},
    )


def _fixture_config_path():
    return Path(__file__).parent / "fixtures" / "config.toml"


class FakeRepository:
    def __init__(self) -> None:
        self.schema_ensured = False
        self.enqueued: list[CommentEvent] = []

    def ensure_schema(self) -> None:
        self.schema_ensured = True

    def enqueue_event(self, event: CommentEvent, *, scanned_at=None):  # type: ignore[no-untyped-def]
        self.enqueued.append(event)
        return EnqueueResult(
            action="inserted",
            job=CommentJob(
                id=len(self.enqueued),
                source_system=str(event.source_metadata["source_system"]),
                comment_identity=event.comment_identity,
                target_page=event.target_page,
                original_comment_text=event.original_comment_text,
                prompt=event.prompt,
                source_metadata=event.source_metadata,
                status="queued",
                receipt_count=1,
                first_scanned_at=datetime(2026, 5, 24, 20, 0, tzinfo=UTC),
                last_scanned_at=datetime(2026, 5, 24, 20, 0, tzinfo=UTC),
                claimed_at=None,
                completed_at=None,
                error_detail=None,
            ),
        )


class FakeWorker:
    def __init__(self) -> None:
        self.run_calls = 0

    def run_once(self) -> None:
        self.run_calls += 1


class FakeScanner:
    def __init__(self, events: list[CommentEvent]) -> None:
        self._events = events

    def scan(self) -> list[CommentEvent]:
        return list(self._events)


class FakeDatabase:
    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []
        self.executed: list[tuple[str, tuple[Any, ...] | None]] = []
        self._next_id = 1

    def connect(self, dsn: str):  # type: ignore[no-untyped-def]
        return FakeConnection(self, dsn)


class FakeConnection:
    def __init__(self, database: FakeDatabase, dsn: str) -> None:
        self._database = database
        self.dsn = dsn

    def cursor(self) -> "FakeCursor":
        return FakeCursor(self._database)

    def commit(self) -> None:
        return None

    def rollback(self) -> None:
        return None

    def close(self) -> None:
        return None

    def __enter__(self) -> "FakeConnection":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:  # type: ignore[no-untyped-def]
        return None


class FakeCursor:
    def __init__(self, database: FakeDatabase) -> None:
        self._database = database
        self._result: list[Any] = []

    def execute(self, query: str, params: tuple[Any, ...] | None = None) -> None:
        head = query.strip().splitlines()[0]
        self._database.executed.append((head, params))

        if query.startswith("CREATE TABLE IF NOT EXISTS comment_jobs"):
            self._result = []
            return
        if query.startswith("CREATE INDEX IF NOT EXISTS comment_jobs_queued_idx"):
            self._result = []
            return
        if query.startswith("CREATE INDEX IF NOT EXISTS comment_jobs_processing_idx"):
            self._result = []
            return
        if query.startswith("SELECT id, status, receipt_count FROM comment_jobs"):
            source_system, comment_identity = params or (None, None)
            for row in self._database.rows:
                if row["source_system"] == source_system and row["comment_identity"] == comment_identity:
                    self._result = [(row["id"], row["status"], row["receipt_count"])]
                    break
            else:
                self._result = []
            return
        if query.startswith("INSERT INTO comment_jobs"):
            assert params is not None
            row = {
                "id": self._database._next_id,
                "source_system": params[0],
                "comment_identity": params[1],
                "target_page": params[2],
                "original_comment_text": params[3],
                "prompt": params[4],
                "source_metadata": _unwrap_json_param(params[5]),
                "status": "queued",
                "receipt_count": 1,
                "first_scanned_at": params[6],
                "last_scanned_at": params[7],
                "claimed_at": None,
                "completed_at": None,
                "error_detail": None,
            }
            self._database._next_id += 1
            self._database.rows.append(row)
            self._result = [_row_tuple(row)]
            return
        if query.startswith("UPDATE comment_jobs SET target_page = %s"):
            assert params is not None
            row = _find_row(self._database.rows, params[-1])
            row["target_page"] = params[0]
            row["original_comment_text"] = params[1]
            row["prompt"] = params[2]
            row["source_metadata"] = _unwrap_json_param(params[3])
            row["receipt_count"] += 1
            row["last_scanned_at"] = params[4]
            self._result = [_row_tuple(row)]
            return
        if query.startswith("SELECT id FROM comment_jobs WHERE status = 'queued'"):
            queued_rows = [row for row in self._database.rows if row["status"] == "queued"]
            queued_rows.sort(key=lambda row: row["id"])
            self._result = [(queued_rows[0]["id"],)] if queued_rows else []
            return
        if query.startswith("UPDATE comment_jobs SET status = 'processing'"):
            assert params is not None
            row = _find_row(self._database.rows, params[1])
            row["status"] = "processing"
            row["claimed_at"] = params[0]
            row["completed_at"] = None
            row["error_detail"] = None
            self._result = [_row_tuple(row)]
            return
        if query.startswith("UPDATE comment_jobs SET status = %s"):
            assert params is not None
            row = _find_row(self._database.rows, params[3])
            row["status"] = params[0]
            row["completed_at"] = params[1]
            row["error_detail"] = params[2]
            self._result = [_row_tuple(row)]
            return
        if query.startswith("UPDATE comment_jobs SET status = 'UPDATE_FAILED'"):
            assert params is not None
            completed_at, cutoff = params
            marked = 0
            for row in self._database.rows:
                if row["status"] == "processing" and row["claimed_at"] is not None and row["claimed_at"] < cutoff:
                    row["status"] = "UPDATE_FAILED"
                    row["completed_at"] = completed_at
                    row["error_detail"] = "stale processing timeout"
                    marked += 1
            self._result = [(marked,)]
            return
        if query.startswith("SELECT status, COUNT(*) FROM comment_jobs"):
            counts: dict[str, int] = {}
            for row in self._database.rows:
                counts[row["status"]] = counts.get(row["status"], 0) + 1
            self._result = sorted(counts.items())
            return

        raise AssertionError(f"Unhandled query: {query}")

    def fetchone(self):  # type: ignore[no-untyped-def]
        if not self._result:
            return None
        return self._result.pop(0)

    def fetchall(self):  # type: ignore[no-untyped-def]
        result = list(self._result)
        self._result.clear()
        return result

    def __enter__(self) -> "FakeCursor":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:  # type: ignore[no-untyped-def]
        return None


def _find_row(rows: list[dict[str, Any]], row_id: int) -> dict[str, Any]:
    for row in rows:
        if row["id"] == row_id:
            return row
    raise AssertionError(f"row {row_id} not found")


def _row_tuple(row: dict[str, Any]) -> tuple[Any, ...]:
    return (
        row["id"],
        row["source_system"],
        row["comment_identity"],
        row["target_page"],
        row["original_comment_text"],
        row["prompt"],
        row["source_metadata"],
        row["status"],
        row["receipt_count"],
        row["first_scanned_at"],
        row["last_scanned_at"],
        row["claimed_at"],
        row["completed_at"],
        row["error_detail"],
    )


def _unwrap_json_param(value: Any) -> Any:
    return getattr(value, "obj", value)
