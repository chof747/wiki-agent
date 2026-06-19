from __future__ import annotations

from typing import Final, Literal

InvocationStatus = Literal[
    "SUCCESS",
    "ALREADY_PROCESSED",
    "REJECTED_WITH_COMMENT",
    "UPDATE_FAILED",
    "DELETE_FAILED",
]

QueueState = Literal["queued", "processing"]

STATUS_SUCCESS: Final[InvocationStatus] = "SUCCESS"
STATUS_ALREADY_PROCESSED: Final[InvocationStatus] = "ALREADY_PROCESSED"
STATUS_REJECTED_WITH_COMMENT: Final[InvocationStatus] = "REJECTED_WITH_COMMENT"
STATUS_UPDATE_FAILED: Final[InvocationStatus] = "UPDATE_FAILED"
STATUS_DELETE_FAILED: Final[InvocationStatus] = "DELETE_FAILED"

QUEUE_STATE_QUEUED: Final[QueueState] = "queued"
QUEUE_STATE_PROCESSING: Final[QueueState] = "processing"

ALLOWED_INVOCATION_STATUSES: Final[frozenset[InvocationStatus]] = frozenset(
    {
        STATUS_SUCCESS,
        STATUS_ALREADY_PROCESSED,
        STATUS_REJECTED_WITH_COMMENT,
        STATUS_UPDATE_FAILED,
        STATUS_DELETE_FAILED,
    }
)

TERMINAL_INVOCATION_STATUSES: Final[frozenset[InvocationStatus]] = frozenset(
    {
        STATUS_SUCCESS,
        STATUS_ALREADY_PROCESSED,
        STATUS_REJECTED_WITH_COMMENT,
        STATUS_UPDATE_FAILED,
        STATUS_DELETE_FAILED,
    }
)

COMPLETED_INVOCATION_STATUSES: Final[frozenset[InvocationStatus]] = frozenset(
    {
        STATUS_SUCCESS,
        STATUS_ALREADY_PROCESSED,
        STATUS_REJECTED_WITH_COMMENT,
    }
)
