from __future__ import annotations

import json
import logging

from wiki_agent.logging import JsonFormatter


def test_json_formatter_emits_operational_metadata_fields() -> None:
    formatter = JsonFormatter()
    record = logging.LogRecord(
        name="wiki_agent.worker",
        level=logging.INFO,
        pathname=__file__,
        lineno=10,
        msg="Worker finalized job from runner response.",
        args=(),
        exc_info=None,
    )
    record.event = "worker.job_finalized"
    record.job_id = 42
    record.status = "REJECTED_WITH_COMMENT"
    record.rejection_reason_code = "CROSS_PAGE_REQUEST"
    record.error_detail = "runner diagnostic"

    payload = json.loads(formatter.format(record))

    assert payload["event"] == "worker.job_finalized"
    assert payload["job_id"] == 42
    assert payload["status"] == "REJECTED_WITH_COMMENT"
    assert payload["rejection_reason_code"] == "CROSS_PAGE_REQUEST"
    assert payload["error_detail"] == "runner diagnostic"
