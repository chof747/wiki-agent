from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from wiki_agent.wikigo_helper import (
    WikiGoSession,
    extract_markdown,
    load_runtime_config,
    quote_page,
    read_page_source,
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
        payload = read_page_source(session, args.page)
        sys.stdout.write(json.dumps({"markdown": extract_markdown(payload)}, ensure_ascii=False))
        sys.stdout.write("\n")
        return 0

    if args.command == "save":
        session.request(
            "POST",
            f"/api/save/{quote_page(args.page)}",
            body=args.content_file.read_bytes(),
            content_type="text/markdown",
        )
        print(f"saved page: {args.page}")
        return 0

    parser.error("unsupported command")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
