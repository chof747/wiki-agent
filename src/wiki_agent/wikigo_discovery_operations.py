from __future__ import annotations

import urllib.parse
import xml.etree.ElementTree as ET
from typing import Any

from wiki_agent.wikigo_comment_operations import list_comments
from wiki_agent.wikigo_runtime import WikiGoSession


def discover_pages(session: WikiGoSession) -> list[str]:
    sitemap_xml = session.request("GET", "/sitemap.xml").decode("utf-8")
    root = ET.fromstring(sitemap_xml)
    namespace = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}

    pages: list[str] = []
    seen: set[str] = set()
    for node in root.findall(".//sm:url/sm:loc", namespace):
        value = (node.text or "").strip()
        if not value:
            continue
        path = urllib.parse.urlparse(value).path.strip("/")
        if not path or path in seen:
            continue
        seen.add(path)
        pages.append(path)
    return pages


def scan_comments(session: WikiGoSession, *, username: str) -> dict[str, Any]:
    pages = discover_pages(session)
    matches: list[dict[str, Any]] = []
    for page in pages:
        comments = list_comments(session, page, mention_only=True, mention_username=username)
        for comment in comments:
            matches.append(
                {
                    "page": page,
                    "id": comment["id"],
                    "text": comment["text"],
                    "author": comment["author"],
                    "created_at": comment["created_at"],
                }
            )

    return {
        "target_user": username,
        "scanned_pages": len(pages),
        "matched_comments": len(matches),
        "matches": matches,
    }
