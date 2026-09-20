from __future__ import annotations

import argparse
import json
from collections.abc import Sequence

from rift_atlas.builder import build_relationship_file


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="rift-atlas",
        description="Build context-preserving relationships from canonical League drafts.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    build = subparsers.add_parser(
        "build",
        help="Build relationship observations from a drafts schema v1 CSV.",
    )
    build.add_argument("--input", required=True, help="Canonical drafts CSV.")
    build.add_argument("--output", required=True, help="Relationship JSONL output.")

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.command == "build":
        stats = build_relationship_file(args.input, args.output)
        print(json.dumps(stats.as_dict(), sort_keys=True))
        return 0

    raise AssertionError(f"Unhandled command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
