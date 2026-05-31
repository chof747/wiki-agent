from __future__ import annotations

from wiki_agent import wikigo_helper as _impl


def main(argv: list[str] | None = None) -> int:
    return _impl.main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
