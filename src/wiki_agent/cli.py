from __future__ import annotations

import argparse
import logging
import os
import signal
from pathlib import Path
from types import FrameType
from typing import Callable

from wiki_agent.app import WikiAgentApp
from wiki_agent.config import ConfigError, load_config
from wiki_agent import environment
from wiki_agent.logging import configure_logging


LOGGER = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="wiki-agent")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run")
    run_parser.add_argument(
        "--config",
        type=Path,
        default=Path("config.toml"),
        help="Path to the runtime configuration file.",
    )

    run_once_parser = subparsers.add_parser("run-once")
    run_once_parser.add_argument(
        "--config",
        type=Path,
        default=Path("config.toml"),
        help="Path to the runtime configuration file.",
    )
    run_once_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Scan once and report normalized eligible comment events without mutating state.",
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    environment.load_repo_environment()
    os.environ["WIKI_AGENT_CONFIG_PATH"] = str(args.config.resolve())

    try:
        config = load_config(args.config)
    except ConfigError as exc:
        parser.exit(status=2, message=f"configuration error: {exc}\n")

    configure_logging(config.service.log_level)
    app = WikiAgentApp(config)

    if args.command == "run":
        return _run_service(app)
    if args.command == "run-once":
        return app.run_once(dry_run=args.dry_run)

    parser.error(f"unsupported command: {args.command}")
    return 2


def _run_service(app: WikiAgentApp) -> int:
    previous_int = signal.getsignal(signal.SIGINT)
    previous_term = signal.getsignal(signal.SIGTERM)

    def handle_signal(signum: int, _frame: FrameType | None) -> None:
        LOGGER.info(
            "Shutdown signal received.",
            extra={"event": "service.shutdown_requested", "signal": signum},
        )
        app.request_shutdown()

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    try:
        return app.run()
    finally:
        _restore_signal(signal.SIGINT, previous_int)
        _restore_signal(signal.SIGTERM, previous_term)


def _restore_signal(signum: int, handler: int | Callable[[int, FrameType | None], None] | None) -> None:
    signal.signal(signum, handler)
