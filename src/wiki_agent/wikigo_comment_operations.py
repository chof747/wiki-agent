from __future__ import annotations

import json
from typing import Any

from wiki_agent.wikigo_adapter import normalize_comments_payload
from wiki_agent.wikigo_runtime import WikiGoSession, quote_page


def normalize_comments(payload: dict[str, Any]) -> list[dict[str, Any]]:
    return normalize_comments_payload(payload)


def list_comments(
    session: WikiGoSession,
    page: str,
    *,
    mention_only: bool = False,
    mention_username: str | None = None,
) -> list[dict[str, Any]]:
    comments = normalize_comments_payload(read_comments_payload(session, page))
    if mention_only:
        if mention_username is None:
            raise SystemExit("mention-only comment listing requires a username")
        mention = f"@{mention_username}"
        comments = [item for item in comments if item["text"].lower().startswith(mention.lower())]
    return comments


def read_comments_payload(session: WikiGoSession, page: str) -> dict[str, Any]:
    endpoint = f"/api/comments/{quote_page(page)}"
    payload = json.loads(session.request("GET", endpoint).decode("utf-8"))
    if not isinstance(payload, dict):
        raise SystemExit(f"GET {endpoint} did not return a JSON object")
    return payload


def delete_comment(session: WikiGoSession, comment_id: str, page: str) -> None:
    endpoint = f"/api/comments/delete/{quote_page(page)}/{quote_page(comment_id)}"
    session.request("DELETE", endpoint)


def create_comment(session: WikiGoSession, page: str, content: str) -> dict[str, Any]:
    endpoint = f"/api/comments/add/{quote_page(page)}"
    return session.post_json(endpoint, {"content": content})
