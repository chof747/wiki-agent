from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from wiki_agent import wikigo_comment_operations as _comment_operations
from wiki_agent import wikigo_discovery_operations as _discovery_operations
from wiki_agent import wikigo_page_operations as _page_operations
from wiki_agent import wikigo_runtime as _runtime


SUPPORTED_WIKIGO_VERSION = "1.8.9"

WikiGoSession = _runtime.WikiGoSession
load_runtime_config = _runtime.load_runtime_config
quote_page = _runtime.quote_page

normalize_comments = _comment_operations.normalize_comments
read_comments_payload = _comment_operations.read_comments_payload
delete_comment = _comment_operations.delete_comment
create_comment = _comment_operations.create_comment

extract_markdown = _page_operations.extract_markdown
emit_page_get = _page_operations.emit_page_get
save_page = _page_operations.save_page
read_page_source = _page_operations.read_page_source

discover_pages = _discovery_operations.discover_pages


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    config = load_runtime_config()

    if args.command == "config":
        print(f"base_url={config['base_url']}")
        print(f"username={config['username']}")
        print(f"config_file={config['config_file']}")
        return 0

    if args.command == "api":
        session = create_session(config)
        response = _run_api_command(session, args)
        sys.stdout.buffer.write(response)
        return 0

    if args.command == "comments":
        return _run_comments_command(args, config=config)

    if args.command == "page":
        return run_page_command(
            args.page_command,
            args.page,
            getattr(args, "content_file", None),
            config=config,
        )

    if args.command == "comments-scan":
        session = create_session(config)
        payload = _discovery_operations.scan_comments(session, username=str(config["username"]))
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    if args.command == "create-document":
        session = create_session(config)
        _page_operations.create_document(session, args.title, args.path, args.content_file)
        return 0

    parser.error("unsupported command")
    return 2


def _build_parser() -> argparse.ArgumentParser:
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

    comments_create_parser = comments_subparsers.add_parser("create")
    comments_create_parser.add_argument("page")
    comments_create_parser.add_argument("content_file", type=Path)

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

    return parser


def _run_api_command(session: WikiGoSession, args: argparse.Namespace) -> bytes:
    body = None
    if args.body_file is not None:
        body = Path(args.body_file).read_bytes()
    return session.request(
        args.method.upper(),
        args.endpoint,
        body=body,
        content_type=args.content_type,
    )


def _run_comments_command(args: argparse.Namespace, *, config: dict[str, str]) -> int:
    session = create_session(config)
    if args.comments_command == "list":
        comments = _comment_operations.list_comments(
            session,
            args.page,
            mention_only=args.mention_only,
            mention_username=str(config["username"]),
        )
        print(json.dumps(comments, ensure_ascii=False, indent=2))
        return 0

    if args.comments_command == "delete":
        delete_comment(session, args.comment_id, args.page)
        print(f"deleted comment: {args.comment_id}")
        return 0

    if args.comments_command == "create":
        comment = create_comment(
            session,
            args.page,
            args.content_file.read_text(encoding="utf-8"),
        )
        print(json.dumps(comment, ensure_ascii=False))
        return 0

    raise SystemExit(f"unsupported comments command: {args.comments_command}")


def run_page_command(
    command: str,
    page: str,
    content_file: Path | None,
    *,
    config: dict[str, str],
) -> int:
    session = create_session(config)
    if command == "get":
        emit_page_get(session, page)
        return 0

    if command == "save":
        if content_file is None:
            raise SystemExit("page save requires a content file")
        save_page(session, page, content_file)
        return 0

    raise SystemExit(f"unsupported page command: {command}")


def create_session(config: dict[str, str]) -> WikiGoSession:
    return WikiGoSession(
        base_url=str(config["base_url"]),
        username=str(config["username"]),
        password=str(config["password"]),
    )
