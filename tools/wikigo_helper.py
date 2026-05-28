from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from http.cookiejar import CookieJar
from pathlib import Path
from typing import Any


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="wikigo-helper")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("config")

    api_parser = subparsers.add_parser("api")
    api_parser.add_argument("method")
    api_parser.add_argument("endpoint")
    api_parser.add_argument("body_file", nargs="?")
    api_parser.add_argument("content_type", nargs="?", default="application/json")

    comments_parser = subparsers.add_parser("comments")
    comments_subparsers = comments_parser.add_subparsers(dest="comments_command", required=True)

    comments_list_parser = comments_subparsers.add_parser("list")
    comments_list_parser.add_argument("page")
    comments_list_parser.add_argument("--mention-only", action="store_true")

    comments_delete_parser = comments_subparsers.add_parser("delete")
    comments_delete_parser.add_argument("comment_id")
    comments_delete_parser.add_argument("page")

    page_parser = subparsers.add_parser("page")
    page_subparsers = page_parser.add_subparsers(dest="page_command", required=True)

    page_get_parser = page_subparsers.add_parser("get")
    page_get_parser.add_argument("page")

    page_save_parser = page_subparsers.add_parser("save")
    page_save_parser.add_argument("page")
    page_save_parser.add_argument("content_file", type=Path)

    subparsers.add_parser("comments-scan")

    create_document_parser = subparsers.add_parser("create-document")
    create_document_parser.add_argument("title")
    create_document_parser.add_argument("path")
    create_document_parser.add_argument("content_file", type=Path)

    args = parser.parse_args(argv)
    config = load_runtime_config()

    if args.command == "config":
        print(f"base_url={config['base_url']}")
        print(f"username={config['username']}")
        print(f"config_file={config['config_file']}")
        return 0

    session = WikiGoSession(
        base_url=str(config["base_url"]),
        username=str(config["username"]),
        password=str(config["password"]),
    )

    if args.command == "api":
        body = None
        if args.body_file is not None:
            body = Path(args.body_file).read_bytes()
        response = session.request(
            args.method.upper(),
            args.endpoint,
            body=body,
            content_type=args.content_type,
        )
        sys.stdout.buffer.write(response)
        return 0

    if args.command == "comments":
        if args.comments_command == "list":
            payload = read_comments_payload(session, args.page)
            comments = normalize_comments(payload)
            if args.mention_only:
                mention = f"@{config['username']}"
                comments = [
                    item
                    for item in comments
                    if item["text"].lower().startswith(mention.lower())
                ]
            print(json.dumps(comments, ensure_ascii=False, indent=2))
            return 0

        if args.comments_command == "delete":
            delete_comment(session, args.comment_id, args.page)
            print(f"deleted comment: {args.comment_id}")
            return 0

    if args.command == "page":
        if args.page_command == "get":
            payload = read_page_source(session, args.page)
            print(json.dumps({"markdown": extract_markdown(payload)}, ensure_ascii=False))
            return 0

        if args.page_command == "save":
            session.request(
                "POST",
                f"/api/save/{quote_page(args.page)}",
                body=args.content_file.read_bytes(),
                content_type="text/markdown",
            )
            print(f"saved page: {args.page}")
            return 0

    if args.command == "comments-scan":
        pages = discover_pages(session)
        matches: list[dict[str, Any]] = []
        for page in pages:
            comments = normalize_comments(session.get_json(f"/api/comments/{quote_page(page)}"))
            for comment in comments:
                if comment["text"].lower().startswith(f"@{str(config['username']).lower()}"):
                    matches.append(
                        {
                            "page": page,
                            "id": comment["id"],
                            "text": comment["text"],
                            "author": comment["author"],
                            "created_at": comment["created_at"],
                        }
                    )
        print(
            json.dumps(
                {
                    "target_user": config["username"],
                    "scanned_pages": len(pages),
                    "matched_comments": len(matches),
                    "matches": matches,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    if args.command == "create-document":
        session.post_json(
            "/api/document/create",
            {"title": args.title, "path": args.path},
        )
        session.request(
            "POST",
            f"/api/save/{quote_page(args.path)}",
            body=args.content_file.read_bytes(),
            content_type="text/markdown",
        )
        print(f"created and saved document at path: {args.path}")
        return 0

    parser.error("unsupported command")
    return 2


def load_runtime_config() -> dict[str, str]:
    config_value = os.environ.get("WIKIGO_RUNTIME_CONFIG")
    if not config_value:
        raise SystemExit("WIKIGO_RUNTIME_CONFIG is not set")
    config_path = Path(config_value)
    if not config_path.exists():
        raise SystemExit(f"WIKIGO_RUNTIME_CONFIG does not exist: {config_path}")

    payload = json.loads(config_path.read_text(encoding="utf-8"))
    for key in ("base_url", "username", "password"):
        value = payload.get(key)
        if not isinstance(value, str) or not value:
            raise SystemExit(f"runtime config field '{key}' must be a non-empty string")
    payload["config_file"] = str(config_path)
    return payload


class WikiGoSession:
    def __init__(self, *, base_url: str, username: str, password: str) -> None:
        self._base_url = base_url.rstrip("/")
        self._username = username
        self._password = password
        self._opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(CookieJar()))
        self._login()

    def _login(self) -> None:
        payload = json.dumps(
            {
                "username": self._username,
                "password": self._password,
                "keeploggedin": False,
            }
        ).encode("utf-8")
        self.request("POST", "/api/login", body=payload, content_type="application/json")

    def request(
        self,
        method: str,
        endpoint: str,
        *,
        body: bytes | None = None,
        content_type: str | None = None,
    ) -> bytes:
        request = urllib.request.Request(
            urllib.parse.urljoin(f"{self._base_url}/", endpoint.lstrip("/")),
            method=method,
            data=body,
        )
        if content_type:
            request.add_header("Content-Type", content_type)
        try:
            with self._opener.open(request) as response:
                return response.read()
        except urllib.error.HTTPError as exc:
            error_body = exc.read().decode("utf-8", errors="replace")
            raise SystemExit(
                f"{method} {endpoint} failed with HTTP {exc.code}: {error_body}"
            ) from exc

    def get_json(self, endpoint: str) -> dict[str, Any]:
        payload = json.loads(self.request("GET", endpoint).decode("utf-8"))
        if not isinstance(payload, dict):
            raise SystemExit(f"{endpoint} did not return a JSON object")
        return payload

    def post_json(self, endpoint: str, payload: dict[str, Any]) -> dict[str, Any]:
        response = self.request(
            "POST",
            endpoint,
            body=json.dumps(payload).encode("utf-8"),
            content_type="application/json",
        )
        if not response.strip():
            return {}
        parsed = json.loads(response.decode("utf-8"))
        if not isinstance(parsed, dict):
            return {}
        return parsed


def normalize_comments(payload: dict[str, Any]) -> list[dict[str, Any]]:
    raw_items = payload.get("comments", [])
    if not isinstance(raw_items, list):
        return []

    comments: list[dict[str, Any]] = []
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        comment_id = item.get("ID")
        text = item.get("Content")
        if not isinstance(comment_id, int | str) or not isinstance(text, str):
            continue
        comments.append(
            {
                "id": str(comment_id),
                "text": text.strip(),
                "author": str(item.get("Author", "")),
                "created_at": item.get("Timestamp"),
            }
        )
    return comments


def extract_markdown(payload: bytes) -> str:
    text = payload.decode("utf-8")
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return text

    if isinstance(parsed, dict):
        for key in ("markdown", "content"):
            value = parsed.get(key)
            if isinstance(value, str):
                return value

        document = parsed.get("document")
        if isinstance(document, dict):
            for key in ("markdown", "content"):
                value = document.get(key)
                if isinstance(value, str):
                    return value

    raise SystemExit("GET page response is missing markdown content")


def read_comments_payload(session: "WikiGoSession", page: str) -> dict[str, Any]:
    encoded = urllib.parse.quote(page, safe="")
    endpoints = [
        f"/api/comments/{quote_page(page)}",
        f"/api/comments?path={encoded}",
        f"/api/comment/{quote_page(page)}",
        f"/api/comment?path={encoded}",
        f"/api/discussion/{quote_page(page)}",
        f"/api/discussions/{quote_page(page)}",
        f"/api/comments/list/{quote_page(page)}",
    ]

    last_error: BaseException | None = None
    for endpoint in endpoints:
        try:
            payload = json.loads(session.request("GET", endpoint).decode("utf-8"))
        except SystemExit as exc:
            last_error = exc
            continue
        if isinstance(payload, dict):
            return payload

    if last_error is not None:
        raise last_error
    raise SystemExit("unable to read comments")


def read_page_source(session: "WikiGoSession", page: str) -> bytes:
    endpoints = [
        f"/api/source/{quote_page(page)}",
        f"/api/document/{quote_page(page)}",
    ]
    last_error: BaseException | None = None
    for endpoint in endpoints:
        try:
            return session.request("GET", endpoint)
        except SystemExit as exc:
            last_error = exc
            continue

    if last_error is not None:
        raise last_error
    raise SystemExit("unable to read page source")


def delete_comment(session: "WikiGoSession", comment_id: str, page: str) -> None:
    delete_endpoints = []
    if page:
        delete_endpoints.append(
            ("DELETE", f"/api/comments/delete/{quote_page(page)}/{urllib.parse.quote(comment_id)}", None, None)
        )

    delete_endpoints.extend(
        [
            ("DELETE", f"/api/comment/{urllib.parse.quote(comment_id)}", None, None),
            ("DELETE", f"/api/comments/{urllib.parse.quote(comment_id)}", None, None),
            ("POST", f"/api/comment/{urllib.parse.quote(comment_id)}/delete", None, None),
            ("POST", f"/api/comments/{urllib.parse.quote(comment_id)}/delete", None, None),
            ("POST", f"/api/comment/delete/{urllib.parse.quote(comment_id)}", None, None),
            ("POST", f"/api/comments/delete/{urllib.parse.quote(comment_id)}", None, None),
        ]
    )

    for method, endpoint, body, content_type in delete_endpoints:
        try:
            session.request(method, endpoint, body=body, content_type=content_type)
            return
        except SystemExit:
            continue

    body = json.dumps({"id": comment_id}).encode("utf-8")
    for endpoint in (
        "/api/comment/delete",
        "/api/comments/delete",
        "/api/comment/remove",
        "/api/comments/remove",
    ):
        try:
            session.request("POST", endpoint, body=body, content_type="application/json")
            return
        except SystemExit:
            continue

    raise SystemExit(f"unable to delete comment id {comment_id}: no known delete endpoint worked")


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


def quote_page(page: str) -> str:
    return urllib.parse.quote(page, safe="/")


if __name__ == "__main__":
    raise SystemExit(main())
