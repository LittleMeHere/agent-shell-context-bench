"""Prepare encrypted pilot custody and export signed blinded outcomes.

The script locates the checkout from its own path, so it works from the
required external control directory without a caller-supplied ``PYTHONPATH``.
Neither command invokes an agent or makes a model call.
"""

from __future__ import annotations

import argparse
import getpass
import sys
from collections.abc import Sequence
from pathlib import Path

_BENCH_ROOT = Path(__file__).resolve().parents[1]
if str(_BENCH_ROOT) not in sys.path:
    sys.path.insert(0, str(_BENCH_ROOT))

from harness.blinding import (  # noqa: E402
    BlindingError,
    export_blinded_pilot,
    prepare_blinding_custody,
)
from harness.scheduler import ScheduleError  # noqa: E402


def _passphrase(path: Path | None, *, confirm: bool) -> str:
    if path is not None:
        try:
            value = path.read_text(encoding="utf-8").rstrip("\r\n")
        except OSError as exc:
            raise SystemExit(f"cannot read passphrase file {path}: {exc}") from exc
    else:
        value = getpass.getpass("Blinding custody passphrase: ")
        if confirm and value != getpass.getpass("Confirm passphrase: "):
            raise SystemExit("passphrases do not match")
    if len(value) < 16:
        raise SystemExit("custody passphrase must contain at least 16 characters")
    return value


def _prepare(
    plan: Path,
    pilot_root: Path,
    commitment_output: Path,
    custody_output: Path,
    passphrase_file: Path | None,
) -> int:
    try:
        commitment, _ = prepare_blinding_custody(
            pilot_root,
            _passphrase(passphrase_file, confirm=True),
            plan_path=plan,
            commitment_path=commitment_output,
            custody_path=custody_output,
        )
    except (BlindingError, ScheduleError) as exc:
        raise SystemExit(str(exc)) from exc
    print(f"public commitment written to {commitment_output}")
    print(f"encrypted custody artifact written to {custody_output}")
    print(f"  plan_digest = {commitment.plan_digest}")
    print(f"  commitment_digest = {commitment.commitment_digest}")
    print("  anchor the public commitment before the first pilot attempt")
    print("  keep custody and its passphrase with the independent custodian")
    return 0


def _export(
    pilot_root: Path,
    custody: Path,
    commitment: Path,
    passphrase_file: Path | None,
    output: Path,
) -> int:
    try:
        record = export_blinded_pilot(
            pilot_root,
            custody,
            commitment,
            _passphrase(passphrase_file, confirm=False),
            output,
        )
    except (BlindingError, ScheduleError) as exc:
        raise SystemExit(str(exc)) from exc
    print(f"signed blinded pilot export written to {output}")
    print(f"  source_plan_digest = {record['source_plan_digest']}")
    print(f"  source_manifest_digest = {record['source_manifest_digest']}")
    print(f"  valid_trial_count = {record['valid_trial_count']}")
    print(f"  invalid_attempt_count = {record['invalid_attempt_count']}")
    print(f"  export_digest = {record['export_digest']}")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Prepare and apply the plan-bound R-005 custody boundary."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    prepare_parser = subparsers.add_parser(
        "prepare",
        help="commit a mapping and encrypt custody before the first pilot attempt",
    )
    prepare_parser.add_argument("--plan", type=Path, required=True)
    prepare_parser.add_argument("--pilot-root", type=Path, required=True)
    prepare_parser.add_argument("--commitment-output", type=Path, required=True)
    prepare_parser.add_argument("--custody-output", type=Path, required=True)
    prepare_parser.add_argument(
        "--passphrase-file",
        type=Path,
        help="read passphrase from a protected file instead of an interactive prompt",
    )

    export_parser = subparsers.add_parser(
        "export",
        help="snapshot a completed pilot root and emit a signed blinded export",
    )
    export_parser.add_argument("--pilot-root", type=Path, required=True)
    export_parser.add_argument("--custody", type=Path, required=True)
    export_parser.add_argument("--commitment", type=Path, required=True)
    export_parser.add_argument("--output", type=Path, required=True)
    export_parser.add_argument("--passphrase-file", type=Path)

    args = parser.parse_args(argv)
    if args.command == "prepare":
        return _prepare(
            args.plan,
            args.pilot_root,
            args.commitment_output,
            args.custody_output,
            args.passphrase_file,
        )
    return _export(
        args.pilot_root,
        args.custody,
        args.commitment,
        args.passphrase_file,
        args.output,
    )


if __name__ == "__main__":
    sys.exit(main())
