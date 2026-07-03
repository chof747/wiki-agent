from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Callable

import psycopg
from psycopg.types.json import Jsonb

from wiki_agent.domain import (
    COMPLETED_INVOCATION_STATUSES,
    QUEUE_STATE_PROCESSING,
    QUEUE_STATE_QUEUED,
    STATUS_ALREADY_PROCESSED,
    STATUS_UPDATE_FAILED,
    TERMINAL_INVOCATION_STATUSES,
)
from wiki_agent.scanner import CommentEvent


SERVICE_ADVISORY_LOCK_KEY = 704_007


@dataclass(frozen=True)
class CommentJob:
    id: int
    source_system: str
    comment_identity: str
    target_page: str
    original_comment_text: str
    prompt: str
    source_metadata: dict[str, Any]
    status: str
    receipt_count: int
    first_scanned_at: datetime
    last_scanned_at: datetime
    claimed_at: datetime | None
    completed_at: datetime | None
    error_detail: str | None


@dataclass(frozen=True)
class EnqueueResult:
    action: str
    job: CommentJob


@dataclass(frozen=True)
class QueueCounts:
    queued: int
    processing: int
    by_status: dict[str, int]


@dataclass
class SingletonLockHandle:
    connection: Any

    def release(self) -> None:
        try:
            with self.connection.cursor() as cursor:
                cursor.execute("SELECT pg_advisory_unlock(%s)", (SERVICE_ADVISORY_LOCK_KEY,))
        finally:
            self.connection.close()


class CommentJobRepository:
    def __init__(
        self,
        dsn: str,
        *,
        connect: Callable[..., Any] = psycopg.connect,
    ) -> None:
        self._dsn = dsn
        self._connect = connect

    def ensure_schema(self) -> None:
        with self._connection() as connection, connection.cursor() as cursor:
            cursor.execute(
                """CREATE TABLE IF NOT EXISTS comment_jobs (
id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
source_system TEXT NOT NULL,
comment_identity TEXT NOT NULL,
target_page TEXT NOT NULL,
original_comment_text TEXT NOT NULL,
prompt TEXT NOT NULL,
source_metadata JSONB NOT NULL,
status TEXT NOT NULL,
receipt_count INTEGER NOT NULL,
first_scanned_at TIMESTAMPTZ NOT NULL,
last_scanned_at TIMESTAMPTZ NOT NULL,
claimed_at TIMESTAMPTZ,
completed_at TIMESTAMPTZ,
error_detail TEXT,
UNIQUE (source_system, comment_identity)
)"""
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS comment_jobs_queued_idx ON comment_jobs (status, id)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS comment_jobs_processing_idx ON comment_jobs (status, claimed_at)"
            )
            connection.commit()

    def try_acquire_singleton_lock(self) -> SingletonLockHandle | None:
        connection = self._connection()
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_try_advisory_lock(%s)", (SERVICE_ADVISORY_LOCK_KEY,))
            row = cursor.fetchone()

        if row is None or row[0] is not True:
            connection.close()
            return None

        return SingletonLockHandle(connection=connection)

    def enqueue_event(
        self,
        event: CommentEvent,
        *,
        scanned_at: datetime | None = None,
    ) -> EnqueueResult:
        observed_at = scanned_at or datetime.now(tz=UTC)
        source_system = str(event.source_metadata.get("source_system", "wiki-go"))

        with self._connection() as connection, connection.cursor() as cursor:
            cursor.execute(
                """SELECT id, status, receipt_count FROM comment_jobs
WHERE source_system = %s AND comment_identity = %s
FOR UPDATE""",
                (source_system, event.comment_identity),
            )
            existing = cursor.fetchone()

            if existing is None:
                cursor.execute(
                    f"""INSERT INTO comment_jobs (
source_system,
comment_identity,
target_page,
original_comment_text,
prompt,
source_metadata,
first_scanned_at,
last_scanned_at,
status,
receipt_count
)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, '{QUEUE_STATE_QUEUED}', 1)
RETURNING
id,
source_system,
comment_identity,
target_page,
original_comment_text,
prompt,
source_metadata,
status,
receipt_count,
first_scanned_at,
last_scanned_at,
claimed_at,
completed_at,
error_detail""",
                    (
                        source_system,
                        event.comment_identity,
                        event.target_page,
                        event.original_comment_text,
                        event.prompt,
                        Jsonb(event.source_metadata),
                        observed_at,
                        observed_at,
                    ),
                )
                row = cursor.fetchone()
                connection.commit()
                return EnqueueResult(action="inserted", job=_deserialize_job(row))

            job_id, status, _receipt_count = existing
            update_query = """UPDATE comment_jobs SET target_page = %s,
original_comment_text = %s,
prompt = %s,
source_metadata = %s,
receipt_count = receipt_count + 1,
last_scanned_at = %s
WHERE id = %s
RETURNING
id,
source_system,
comment_identity,
target_page,
original_comment_text,
prompt,
source_metadata,
status,
receipt_count,
first_scanned_at,
last_scanned_at,
claimed_at,
completed_at,
error_detail"""
            action = "refreshed"

            if status == QUEUE_STATE_QUEUED:
                cursor.execute(
                    update_query,
                    (
                        event.target_page,
                        event.original_comment_text,
                        event.prompt,
                        Jsonb(event.source_metadata),
                        observed_at,
                        job_id,
                    ),
                )
            elif status in COMPLETED_INVOCATION_STATUSES:
                cursor.execute(
                    f"""UPDATE comment_jobs SET status = '{STATUS_ALREADY_PROCESSED}',
receipt_count = receipt_count + 1,
last_scanned_at = %s
WHERE id = %s
RETURNING
id,
source_system,
comment_identity,
target_page,
original_comment_text,
prompt,
source_metadata,
status,
receipt_count,
first_scanned_at,
last_scanned_at,
claimed_at,
completed_at,
error_detail""",
                    (observed_at, job_id),
                )
                action = "already_processed"
            else:
                cursor.execute(
                    """UPDATE comment_jobs SET receipt_count = receipt_count + 1,
last_scanned_at = %s
WHERE id = %s
RETURNING
id,
source_system,
comment_identity,
target_page,
original_comment_text,
prompt,
source_metadata,
status,
receipt_count,
first_scanned_at,
last_scanned_at,
claimed_at,
completed_at,
error_detail""",
                    (observed_at, job_id),
                )
                action = "skipped_terminal" if status in TERMINAL_INVOCATION_STATUSES else "receipt_refreshed"

            row = cursor.fetchone()
            connection.commit()
            return EnqueueResult(action=action, job=_deserialize_job(row))

    def claim_next_queued(self, *, claimed_at: datetime | None = None) -> CommentJob | None:
        started_at = claimed_at or datetime.now(tz=UTC)
        with self._connection() as connection, connection.cursor() as cursor:
            cursor.execute(
                f"""SELECT id FROM comment_jobs WHERE status = '{QUEUE_STATE_QUEUED}'
ORDER BY id
LIMIT 1
FOR UPDATE SKIP LOCKED"""
            )
            row = cursor.fetchone()
            if row is None:
                connection.commit()
                return None

            cursor.execute(
                f"""UPDATE comment_jobs SET status = '{QUEUE_STATE_PROCESSING}',
claimed_at = %s,
completed_at = NULL,
error_detail = NULL
WHERE id = %s
RETURNING
id,
source_system,
comment_identity,
target_page,
original_comment_text,
prompt,
source_metadata,
status,
receipt_count,
first_scanned_at,
last_scanned_at,
claimed_at,
completed_at,
error_detail""",
                (started_at, row[0]),
            )
            claimed = cursor.fetchone()
            connection.commit()
            return _deserialize_job(claimed)

    def update_job_status(
        self,
        job_id: int,
        status: str,
        *,
        completed_at: datetime | None = None,
        error_detail: str | None = None,
    ) -> CommentJob:
        finalized_at = completed_at or datetime.now(tz=UTC)
        with self._connection() as connection, connection.cursor() as cursor:
            cursor.execute(
                """UPDATE comment_jobs SET status = %s,
completed_at = %s,
error_detail = %s
WHERE id = %s
RETURNING
id,
source_system,
comment_identity,
target_page,
original_comment_text,
prompt,
source_metadata,
status,
receipt_count,
first_scanned_at,
last_scanned_at,
claimed_at,
completed_at,
error_detail""",
                (status, finalized_at, error_detail, job_id),
            )
            row = cursor.fetchone()
            connection.commit()
            return _deserialize_job(row)

    def mark_stale_processing_jobs(self, *, now: datetime | None = None, processing_timeout: timedelta) -> list[CommentJob]:
        observed_now = now or datetime.now(tz=UTC)
        cutoff = observed_now - processing_timeout
        with self._connection() as connection, connection.cursor() as cursor:
            cursor.execute(
                f"""UPDATE comment_jobs SET status = '{STATUS_UPDATE_FAILED}',
completed_at = %s,
error_detail = 'stale processing timeout'
WHERE status = '{QUEUE_STATE_PROCESSING}' AND claimed_at < %s
RETURNING
id,
source_system,
comment_identity,
target_page,
original_comment_text,
prompt,
source_metadata,
status,
receipt_count,
first_scanned_at,
last_scanned_at,
claimed_at,
completed_at,
error_detail""",
                (observed_now, cutoff),
            )
            marked = [_deserialize_job(row) for row in cursor.fetchall()]
            connection.commit()
            return marked

    def get_counts(self) -> QueueCounts:
        with self._connection() as connection, connection.cursor() as cursor:
            cursor.execute(
                """SELECT status, COUNT(*) FROM comment_jobs
GROUP BY status
ORDER BY status"""
            )
            by_status = {status: count for status, count in cursor.fetchall()}
            connection.commit()
            return QueueCounts(
                queued=by_status.get(QUEUE_STATE_QUEUED, 0),
                processing=by_status.get(QUEUE_STATE_PROCESSING, 0),
                by_status=by_status,
            )

    def _connection(self):
        return self._connect(self._dsn)


def _deserialize_job(row: Any) -> CommentJob:
    if row is None:
        raise ValueError("expected comment_jobs row")

    return CommentJob(
        id=int(row[0]),
        source_system=str(row[1]),
        comment_identity=str(row[2]),
        target_page=str(row[3]),
        original_comment_text=str(row[4]),
        prompt=str(row[5]),
        source_metadata=dict(row[6]),
        status=str(row[7]),
        receipt_count=int(row[8]),
        first_scanned_at=row[9],
        last_scanned_at=row[10],
        claimed_at=row[11],
        completed_at=row[12],
        error_detail=row[13],
    )
