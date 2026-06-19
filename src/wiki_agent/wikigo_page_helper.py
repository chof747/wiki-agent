from __future__ import annotations

import argparse
from pathlib import Path

from wiki_agent.wikigo_helper import (
    WikiGoSession,
    emit_page_get,
    load_runtime_config,
    save_page,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="wikigo-page")
    subparsers = parser.add_subparsers(dest="command", required=True)

    get_parser = subparsers.add_parser("get")
    get_parser.add_argument("page")

    save_parser = subparsers.add_parser("save")
    save_parser.add_argument("page")
    save_parser.add_argument("content_file", type=Path)

    args = parser.parse_args(argv)
    config = load_runtime_config()
    session = WikiGoSession(
        base_url=str(config["base_url"]),
        username=str(config["username"]),
        password=str(config["password"]),
    )

    if args.command == "get":
        emit_page_get(session, args.page)
        return 0

    if args.command == "save":
        save_page(session, args.page, args.content_file)
        return 0

    parser.error("unsupported command")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
