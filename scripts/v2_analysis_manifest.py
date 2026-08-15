"""Create or verify the immutable V2 analysis-source manifest."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


BENCH_ROOT = Path(__file__).resolve().parents[1]
if str(BENCH_ROOT) not in sys.path:
    sys.path.insert(0, str(BENCH_ROOT))

from analysis.v2_analysis_manifest import (  # noqa: E402
    build_analysis_manifest,
    load_analysis_dataset,
    write_analysis_manifest,
)
from harness.scheduler import load_plan  # noqa: E402


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Freeze or verify the complete V2 trial-record byte roster."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("create", "verify"):
        sub = subparsers.add_parser(command)
        sub.add_argument("--plan", type=Path, required=True)
        sub.add_argument("--source-root", type=Path, required=True)
        if command == "create":
            sub.add_argument("--output", type=Path, required=True)
        else:
            sub.add_argument("--manifest", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    plan = load_plan(args.plan)
    if args.command == "create":
        manifest = build_analysis_manifest(plan, args.source_root)
        write_analysis_manifest(
            manifest,
            args.output,
            source_root=args.source_root,
        )
        print(
            f"manifest_digest={manifest.manifest_digest} "
            f"sources={len(manifest.sources)}"
        )
        return 0
    rows = load_analysis_dataset(plan, args.source_root, args.manifest)
    print(f"verified_plan_digest={plan.digest} valid_analysis_trials={len(rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
