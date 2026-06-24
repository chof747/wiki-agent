from __future__ import annotations

import json
from pathlib import Path

from wiki_agent.wikigo_adapter import WikiGoAdapterError, extract_markdown as _extract_markdown
from wiki_agent.wikigo_runtime import WikiGoSession, quote_page


def extract_markdown(payload: bytes) -> str:
    try:
        return _extract_markdown(payload)
    except WikiGoAdapterError as exc:
        raise SystemExit("GET page response is missing markdown content") from exc


def emit_page_get(session: WikiGoSession, page: str) -> None:
    payload = read_page_source(session, page)
    print(json.dumps({"markdown": extract_markdown(payload)}, ensure_ascii=False))


def save_page(session: WikiGoSession, page: str, content_file: Path) -> None:
    session.request(
        "POST",
        f"/api/save/{quote_page(page)}",
        body=content_file.read_bytes(),
        content_type="text/markdown",
    )
    print(f"saved page: {page}")


def create_document(session: WikiGoSession, title: str, path: str, content_file: Path) -> None:
    session.post_json(
        "/api/document/create",
        {"title": title, "path": path},
    )
    session.request(
        "POST",
        f"/api/save/{quote_page(path)}",
        body=content_file.read_bytes(),
        content_type="text/markdown",
    )
    print(f"created and saved document at path: {path}")


def read_page_source(session: WikiGoSession, page: str) -> bytes:
    endpoint = f"/api/source/{quote_page(page)}"
    return session.request("GET", endpoint)
