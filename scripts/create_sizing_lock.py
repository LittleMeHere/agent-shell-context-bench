"""Create the immutable R-006 sizing lock from a verified blinded pilot.

This is a V2 provenance wrapper around the frozen V1 sizing implementation.
It does not select methodology, budget, analysis, or simulation inputs; every
authoritative value is explicit and becomes part of the lock digest.
"""

from __future__ import annotations

import argparse
import getpass
import hashlib
import math
import sys
from collections.abc import Sequence
from pathlib import Path

_BENCH_ROOT = Path(__file__).resolve().parents[1]
if str(_BENCH_ROOT) not in sys.path:
    sys.path.insert(0, str(_BENCH_ROOT))

# Snapshot every sizing-path source before importing any benchmark module.
# The final write rechecks all paths, so a persistent concurrent edit cannot
# make the lock claim code bytes different from those available at import.
_CODE_SOURCE_PATHS = {
    "scripts/create_sizing_lock.py": Path(__file__).resolve(),
    "scripts/size_from_pilot.py": _BENCH_ROOT / "scripts" / "size_from_pilot.py",
    "harness/blinding.py": _BENCH_ROOT / "harness" / "blinding.py",
    "harness/sizing_lock.py": _BENCH_ROOT / "harness" / "sizing_lock.py",
}
_CODE_SOURCE_BYTES = {
    name: path.read_bytes() for name, path in _CODE_SOURCE_PATHS.items()
}
_CODE_SOURCE_HASHES = {
    name: hashlib.sha256(value).hexdigest()
    for name, value in _CODE_SOURCE_BYTES.items()
}

from harness.blinding import (
    BlindingError,
    load_blinded_export_bytes,
    load_commitment_bytes,
    load_custody,
)
from harness.sizing_lock import (
    SizingLockError,
    build_sizing_lock,
    sha256_file,
    write_sizing_lock,
)

DEFAULT_TASK_CLASS = "capability"
TASK_CLASS_CHOICES = ("capability", "seeded-error", "all")


def _positive_float(value: str) -> float:
    try:
        parsed = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be a number") from exc
    if not math.isfinite(parsed) or parsed <= 0:
        raise argparse.ArgumentTypeError("must be a positive finite number")
    return parsed


def _positive_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be an integer") from exc
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return parsed


def _passphrase(path: Path | None) -> str:
    if path is None:
        value = getpass.getpass("Blinding custody passphrase: ")
    else:
        try:
            value = path.read_text(encoding="utf-8").rstrip("\r\n")
        except OSError as exc:
            raise SizingLockError(f"cannot read passphrase file {path}: {exc}") from exc
    if len(value) < 16:
        raise SizingLockError("custody passphrase must contain at least 16 characters")
    return value


def _read_once(path: Path, *, label: str) -> bytes:
    try:
        return path.read_bytes()
    except OSError as exc:
        raise SizingLockError(f"cannot read {label} {path}: {exc}") from exc


def _size_from_snapshot(
    source_bytes: bytes,
    trials: list[dict[str, object]],
    *,
    cap_per_cell: int,
    task_class: str,
) -> dict[str, object]:
    """Execute the exact sizing-source bytes whose digest enters the lock."""
    namespace: dict[str, object] = {
        "__name__": "_frozen_size_from_pilot_snapshot",
        "__file__": str(_BENCH_ROOT / "scripts" / "size_from_pilot.py"),
    }
    try:
        exec(
            compile(source_bytes, namespace["__file__"], "exec"),
            namespace,
        )
        if (
            namespace.get("DEFAULT_TASK_CLASS") != DEFAULT_TASK_CLASS
            or tuple(namespace.get("TASK_CLASS_CHOICES", ())) != TASK_CLASS_CHOICES
        ):
            raise SizingLockError("sizing source task-class contract changed")
        size_function = namespace.get("size_from_trials")
        if not callable(size_function):
            raise SizingLockError("sizing source lacks size_from_trials")
        return size_function(
            trials,
            cap_per_cell=cap_per_cell,
            task_class=task_class,
        )
    except SizingLockError:
        raise
    except Exception as exc:
        raise SizingLockError(f"cannot execute sizing source snapshot: {exc}") from exc


def _verify_code_sources_unchanged() -> None:
    for name, path in _CODE_SOURCE_PATHS.items():
        if sha256_file(path) != _CODE_SOURCE_HASHES[name]:
            raise SizingLockError(
                f"sizing-path source changed during lock creation: {name}"
            )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="create_sizing_lock.py",
        description=(
            "Create an immutable, provenance-bound confirmatory sizing lock "
            "from the signed blinded-pilot export."
        ),
    )
    parser.add_argument("--pilot-json", type=Path, required=True)
    parser.add_argument("--blinding-commitment", type=Path, required=True)
    parser.add_argument("--custody", type=Path, required=True)
    parser.add_argument("--passphrase-file", type=Path)
    parser.add_argument("--compute-budget", type=_positive_float, required=True)
    parser.add_argument("--per-trial-cost", type=_positive_float, required=True)
    parser.add_argument("--n-cells", type=_positive_int, required=True)
    parser.add_argument("--code-version", required=True)
    parser.add_argument("--analysis-version", required=True)
    parser.add_argument("--analysis-artifact", type=Path, required=True)
    parser.add_argument("--simulation-version", required=True)
    parser.add_argument("--simulation-config", type=Path, required=True)
    parser.add_argument(
        "--task-class",
        choices=TASK_CLASS_CHOICES,
        default=DEFAULT_TASK_CLASS,
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)

    if (
        not args.code_version.strip()
        or not args.analysis_version.strip()
        or not args.simulation_version.strip()
    ):
        parser.error(
            "--code-version, --analysis-version, and --simulation-version "
            "must be non-empty"
        )
    resolved_inputs = {
        args.pilot_json.resolve(),
        args.blinding_commitment.resolve(),
        args.custody.resolve(),
        args.analysis_artifact.resolve(),
        args.simulation_config.resolve(),
    }
    if args.passphrase_file is not None:
        resolved_inputs.add(args.passphrase_file.resolve())
    if args.output.resolve() in resolved_inputs:
        parser.error("--output must be separate from every input artifact")

    try:
        pilot_bytes = _read_once(args.pilot_json, label="blinded export")
        commitment_bytes = _read_once(
            args.blinding_commitment, label="blinding commitment"
        )
        trials, metadata, blinded_input_sha256 = load_blinded_export_bytes(
            pilot_bytes, commitment_bytes
        )
        commitment, commitment_artifact_sha256 = load_commitment_bytes(
            commitment_bytes
        )
        _, signing_key, _ = load_custody(
            args.custody, commitment, _passphrase(args.passphrase_file)
        )
        cap_per_cell = int(
            math.floor(
                (args.compute_budget / args.per_trial_cost) / args.n_cells
            )
        )
        sizing_source_bytes = _CODE_SOURCE_BYTES["scripts/size_from_pilot.py"]
        result = _size_from_snapshot(
            sizing_source_bytes,
            trials,
            cap_per_cell=cap_per_cell,
            task_class=args.task_class,
        )
        code_artifacts = dict(_CODE_SOURCE_HASHES)
        lock = build_sizing_lock(
            source_plan_digest=str(metadata["source_plan_digest"]),
            source_plan_schema_version=str(
                metadata["source_plan_schema_version"]
            ),
            source_trial_schema_version=str(
                metadata["source_trial_schema_version"]
            ),
            blinded_input_sha256=blinded_input_sha256,
            blinded_export_digest=str(metadata["export_digest"]),
            source_manifest_digest=str(metadata["source_manifest_digest"]),
            commitment_digest=str(metadata["commitment_digest"]),
            commitment_artifact_sha256=commitment_artifact_sha256,
            commitment_public_key_b64=commitment.public_key_b64,
            signing_key=signing_key,
            code_version=args.code_version.strip(),
            code_artifacts=code_artifacts,
            analysis_version=args.analysis_version.strip(),
            analysis_artifact_sha256=sha256_file(args.analysis_artifact),
            simulation_config_version=args.simulation_version.strip(),
            simulation_config_sha256=sha256_file(args.simulation_config),
            task_class=args.task_class,
            compute_budget=args.compute_budget,
            per_trial_cost=args.per_trial_cost,
            n_cells=args.n_cells,
            cap_per_cell=cap_per_cell,
            result=result,
        )
        _verify_code_sources_unchanged()
        write_sizing_lock(lock, args.output)
    except (BlindingError, OSError, SizingLockError, ValueError) as exc:
        parser.error(str(exc))

    print(f"sizing lock written: {args.output.resolve()}")
    print(f"  sizing_lock_digest = {lock.digest}")
    print(f"  n_per_cell = {lock.n_per_cell}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
