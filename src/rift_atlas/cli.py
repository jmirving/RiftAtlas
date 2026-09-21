from __future__ import annotations

import argparse
import json
from collections.abc import Sequence

from rift_atlas.builder import build_relationship_file, read_drafts
from rift_atlas.explorer import serve_explorer
from rift_atlas.recommendation import MappingRolePolicy, RecommendationIndex


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

    recommend = subparsers.add_parser(
        "recommend",
        help="Recommend evidence-supported additions to a partial allied draft.",
    )
    recommend.add_argument("--input", required=True, help="Canonical drafts CSV.")
    recommend.add_argument(
        "--pick",
        action="append",
        required=True,
        dest="picks",
        help="Locked champion (repeatable).",
    )
    recommend.add_argument("--limit", type=int, default=20)
    recommend.add_argument(
        "--role-data",
        help="Optional JSON file mapping champion names to allowed roles.",
    )
    recommend.add_argument(
        "--include-infeasible",
        action="store_true",
        help="Return role-infeasible candidates with an explicit flag instead of rejecting them.",
    )

    explore = subparsers.add_parser(
        "explore",
        help="Explore observed champion relationships in a local web UI.",
    )
    explore.add_argument("--input", required=True, help="Canonical drafts CSV.")
    explore.add_argument(
        "--role-data",
        help="Optional JSON mapping champions to roles for graph feasibility overlays.",
    )
    explore.add_argument("--host", default="127.0.0.1")
    explore.add_argument("--port", type=int, default=8765)
    explore.add_argument(
        "--no-open",
        action="store_true",
        help="Print the local URL without opening a browser.",
    )

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.command == "build":
        stats = build_relationship_file(args.input, args.output)
        print(json.dumps(stats.as_dict(), sort_keys=True))
        return 0

    if args.command == "recommend":
        role_policy = None
        if args.role_data:
            with open(args.role_data, encoding="utf-8") as handle:
                role_data = json.load(handle)
            if not isinstance(role_data, dict):
                raise ValueError("Role data must be a JSON object mapping champions to roles.")
            role_policy = MappingRolePolicy(role_data)
        index = RecommendationIndex(read_drafts(args.input))
        result = index.recommend(
            args.picks,
            limit=args.limit,
            role_policy=role_policy,
            include_infeasible=args.include_infeasible,
        )
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return 0

    if args.command == "explore":
        role_policy = None
        if args.role_data:
            with open(args.role_data, encoding="utf-8") as handle:
                role_data = json.load(handle)
            if not isinstance(role_data, dict):
                raise ValueError("Role data must be a JSON object mapping champions to roles.")
            role_policy = MappingRolePolicy(role_data)
        serve_explorer(
            read_drafts(args.input),
            input_path=args.input,
            role_context_loaded=bool(args.role_data),
            role_policy=role_policy,
            host=args.host,
            port=args.port,
            open_browser=not args.no_open,
        )
        return 0

    raise AssertionError(f"Unhandled command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
