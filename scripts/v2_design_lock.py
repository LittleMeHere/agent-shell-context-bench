"""Create and verify the signed fixed-N V2 authorization artifacts.

Signing always uses the Ed25519 key inside the encrypted R-005 custody
artifact. Passphrases may be entered interactively or read from a protected
file; neither passphrases nor decrypted custody contents are printed.
"""

from __future__ import annotations

import argparse
import getpass
import hashlib
import json
import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from analysis.v2_analysis_manifest import (  # noqa: E402
    AnalysisManifestError,
    analysis_manifest_from_dict,
)
from harness.blinding import (  # noqa: E402
    BlindingError,
    load_commitment_bytes,
    load_custody,
)
from harness.scheduler import (  # noqa: E402
    ScheduleError,
    V2_PILOT_PHASE,
    load_plan,
    v2_task_bank_digest,
)
from harness.v2_design_lock import (  # noqa: E402
    V2DesignLockError,
    build_v2_design_lock,
    build_v2_pilot_release,
    v2_design_lock_from_dict,
    v2_pilot_release_from_dict,
    validate_v2_commitment_anchor,
)
from scripts.configuration_matrix import load_matrix  # noqa: E402


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _read(path: Path, *, label: str) -> bytes:
    try:
        return path.read_bytes()
    except OSError as exc:
        raise V2DesignLockError(f"cannot read {label} {path}: {exc}") from exc


def _json(raw: bytes, *, label: str) -> object:
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise V2DesignLockError(f"cannot parse {label}: {exc}") from exc


def _passphrase(path: Path | None) -> str:
    if path is None:
        value = getpass.getpass("R-005 custody passphrase: ")
    else:
        try:
            value = path.read_text(encoding="utf-8").rstrip("\r\n")
        except OSError as exc:
            raise V2DesignLockError(
                f"cannot read custody passphrase file {path}: {exc}"
            ) from exc
    if len(value) < 16:
        raise V2DesignLockError(
            "custody passphrase must contain at least 16 characters"
        )
    return value


def _write_exclusive(path: Path, value: dict[str, object]) -> str:
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = (
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode("utf-8")
    try:
        with path.open("xb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
    except FileExistsError as exc:
        raise V2DesignLockError(f"refusing to overwrite artifact: {path}") from exc
    return _sha256(encoded)


def _require_output_absent(path: Path) -> None:
    if path.exists():
        raise V2DesignLockError(
            f"refusing to overwrite artifact: {path.resolve()}"
        )


def _require_private_external_path(path: Path, *, label: str) -> None:
    try:
        path.resolve().relative_to(_ROOT.resolve())
    except ValueError:
        return
    raise V2DesignLockError(
        f"{label} must remain outside the public methodology repository"
    )


def _require_unchanged(snapshots: dict[Path, bytes]) -> None:
    for path, expected in snapshots.items():
        if _read(path, label="input artifact") != expected:
            raise V2DesignLockError(
                f"input artifact changed during authorization: {path}"
            )


def _custody_key(
    *,
    commitment_path: Path,
    custody_path: Path,
    passphrase_file: Path | None,
    expected_plan_digest: str,
):
    commitment_raw = _read(commitment_path, label="R-005 commitment")
    commitment, commitment_sha256 = load_commitment_bytes(
        commitment_raw, plan_digest=expected_plan_digest
    )
    custody_raw = _read(custody_path, label="R-005 custody")
    _, signing_key, observed_custody_sha256 = load_custody(
        custody_path,
        commitment,
        _passphrase(passphrase_file),
    )
    if observed_custody_sha256 != _sha256(custody_raw):
        raise V2DesignLockError("R-005 custody changed while it was being loaded")
    anchor = {
        "commitment_digest": commitment.commitment_digest,
        "commitment_artifact_sha256": commitment_sha256,
        "commitment_public_key_b64": commitment.public_key_b64,
    }
    return signing_key, anchor, commitment_raw, custody_raw


def _create_design_lock(args: argparse.Namespace) -> int:
    _require_output_absent(args.output)
    _require_private_external_path(args.provider_cap, label="provider cap")
    _require_private_external_path(args.custody, label="R-005 custody")
    if args.passphrase_file is not None:
        _require_private_external_path(
            args.passphrase_file, label="custody passphrase file"
        )
    paths = (
        args.pilot_plan,
        args.runtime_matrix,
        args.analysis_artifact,
        args.simulation_artifact,
        args.provider_cap,
    )
    snapshots = {path.resolve(): _read(path, label="input artifact") for path in paths}
    plan = load_plan(args.pilot_plan)
    if plan.phase != V2_PILOT_PHASE:
        raise V2DesignLockError("design lock requires the fixed V2 pilot plan")
    matrix = load_matrix(args.runtime_matrix)
    runtime_binding = matrix.scheduler_binding()
    provider_cap = _json(snapshots[args.provider_cap.resolve()], label="provider cap")
    if not isinstance(provider_cap, dict):
        raise V2DesignLockError("provider cap must contain a JSON object")
    signing_key, anchor, commitment_raw, custody_raw = _custody_key(
        commitment_path=args.commitment,
        custody_path=args.custody,
        passphrase_file=args.passphrase_file,
        expected_plan_digest=plan.digest,
    )
    snapshots[args.commitment.resolve()] = commitment_raw
    snapshots[args.custody.resolve()] = custody_raw
    task_bank_digest = v2_task_bank_digest()
    lock = build_v2_design_lock(
        signing_key=signing_key,
        pilot_plan_digest=plan.digest,
        runtime_matrix_digest=runtime_binding.matrix_digest,
        task_bank_digest=task_bank_digest,
        analysis_artifact_sha256=_sha256(
            snapshots[args.analysis_artifact.resolve()]
        ),
        simulation_artifact_sha256=_sha256(
            snapshots[args.simulation_artifact.resolve()]
        ),
        provider_cap_authorization=provider_cap,
        pilot_commitment_anchor=anchor,
        order_seed=args.order_seed,
        created_at=args.created_at,
    )
    _require_unchanged(snapshots)
    if v2_task_bank_digest() != task_bank_digest:
        raise V2DesignLockError(
            "V2 task bank changed during design-lock creation"
        )
    artifact_sha256 = _write_exclusive(args.output, lock.as_dict())
    print(
        "created V2 design lock: "
        f"digest {lock.digest}; artifact_sha256 {artifact_sha256}"
    )
    print(
        "bound inputs: "
        f"pilot_plan_digest {lock.pilot_plan_digest}; "
        f"pilot_plan_artifact_sha256 "
        f"{_sha256(snapshots[args.pilot_plan.resolve()])}; "
        f"runtime_matrix_digest {lock.runtime_matrix_digest}; "
        f"runtime_matrix_artifact_sha256 "
        f"{_sha256(snapshots[args.runtime_matrix.resolve()])}; "
        f"task_bank_digest {lock.task_bank_digest}; "
        f"analysis_artifact_sha256 {lock.analysis_artifact_sha256}; "
        f"simulation_artifact_sha256 {lock.simulation_artifact_sha256}; "
        f"provider_cap_authorization_digest "
        f"{lock.provider_cap_artifact_sha256}; "
        f"provider_cap_artifact_sha256 "
        f"{_sha256(snapshots[args.provider_cap.resolve()])}; "
        f"commitment_digest {lock.commitment_digest}; "
        f"commitment_artifact_sha256 {lock.commitment_artifact_sha256}; "
        f"custody_artifact_sha256 {_sha256(custody_raw)}"
    )
    return 0


def _create_pilot_release(args: argparse.Namespace) -> int:
    _require_output_absent(args.output)
    _require_private_external_path(args.custody, label="R-005 custody")
    if args.passphrase_file is not None:
        _require_private_external_path(
            args.passphrase_file, label="custody passphrase file"
        )
    paths = (args.design_lock, args.pilot_gate, args.analysis_manifest)
    snapshots = {path.resolve(): _read(path, label="input artifact") for path in paths}
    lock = v2_design_lock_from_dict(
        _json(snapshots[args.design_lock.resolve()], label="V2 design lock")
    )
    gate = _json(snapshots[args.pilot_gate.resolve()], label="pilot gate")
    if not isinstance(gate, dict):
        raise V2DesignLockError("pilot gate must contain a JSON object")
    try:
        manifest = analysis_manifest_from_dict(
            _json(
                snapshots[args.analysis_manifest.resolve()],
                label="analysis manifest",
            )
        )
    except AnalysisManifestError as exc:
        raise V2DesignLockError(f"invalid analysis manifest: {exc}") from exc
    if manifest.plan_digest != lock.pilot_plan_digest:
        raise V2DesignLockError("analysis manifest uses a different pilot plan")
    signing_key, anchor, commitment_raw, custody_raw = _custody_key(
        commitment_path=args.commitment,
        custody_path=args.custody,
        passphrase_file=args.passphrase_file,
        expected_plan_digest=lock.pilot_plan_digest,
    )
    validate_v2_commitment_anchor(lock, anchor)
    snapshots[args.commitment.resolve()] = commitment_raw
    snapshots[args.custody.resolve()] = custody_raw
    release = build_v2_pilot_release(
        design_lock=lock,
        signing_key=signing_key,
        pilot_gate_artifact=gate,
        analysis_manifest_digest=manifest.manifest_digest,
        created_at=args.created_at,
    )
    _require_unchanged(snapshots)
    artifact_sha256 = _write_exclusive(args.output, release.as_dict())
    print(
        "created V2 pilot release: "
        f"digest {release.digest}; artifact_sha256 {artifact_sha256}"
    )
    print(
        "bound inputs: "
        f"design_lock_digest {release.design_lock_digest}; "
        f"design_lock_artifact_sha256 "
        f"{_sha256(snapshots[args.design_lock.resolve()])}; "
        f"pilot_gate_digest {release.pilot_gate_artifact_digest}; "
        f"pilot_gate_artifact_sha256 "
        f"{_sha256(snapshots[args.pilot_gate.resolve()])}; "
        f"analysis_manifest_digest {release.analysis_manifest_digest}; "
        f"analysis_manifest_artifact_sha256 "
        f"{_sha256(snapshots[args.analysis_manifest.resolve()])}; "
        f"commitment_artifact_sha256 {lock.commitment_artifact_sha256}; "
        f"custody_artifact_sha256 {_sha256(custody_raw)}"
    )
    return 0


def _verify(args: argparse.Namespace) -> int:
    lock_raw = _read(args.design_lock, label="V2 design lock")
    lock = v2_design_lock_from_dict(_json(lock_raw, label="V2 design lock"))
    commitment_raw = _read(args.commitment, label="R-005 commitment")
    commitment, commitment_sha256 = load_commitment_bytes(
        commitment_raw, plan_digest=lock.pilot_plan_digest
    )
    validate_v2_commitment_anchor(
        lock,
        {
            "commitment_digest": commitment.commitment_digest,
            "commitment_artifact_sha256": commitment_sha256,
            "commitment_public_key_b64": commitment.public_key_b64,
        },
    )
    print(
        "verified V2 design lock: "
        f"digest {lock.digest}; artifact_sha256 {_sha256(lock_raw)}"
    )
    if args.pilot_release is not None:
        release_raw = _read(args.pilot_release, label="V2 pilot release")
        release = v2_pilot_release_from_dict(
            _json(release_raw, label="V2 pilot release"), lock
        )
        print(
            "verified V2 pilot release: "
            f"digest {release.digest}; artifact_sha256 {_sha256(release_raw)}; "
            f"pilot_gate_digest {release.pilot_gate_artifact_digest}; "
            f"analysis_manifest_digest {release.analysis_manifest_digest}"
        )
    return 0


def _custody_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--commitment", type=Path, required=True)
    parser.add_argument("--custody", type=Path, required=True)
    parser.add_argument(
        "--passphrase-file",
        type=Path,
        help="read the R-005 custody passphrase from a protected file",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)

    design = sub.add_parser("create-design-lock")
    design.add_argument("--pilot-plan", type=Path, required=True)
    design.add_argument("--runtime-matrix", type=Path, required=True)
    design.add_argument("--analysis-artifact", type=Path, required=True)
    design.add_argument("--simulation-artifact", type=Path, required=True)
    design.add_argument("--provider-cap", type=Path, required=True)
    design.add_argument("--order-seed", type=int, required=True)
    design.add_argument("--created-at")
    design.add_argument("--output", type=Path, required=True)
    _custody_arguments(design)

    release = sub.add_parser("create-pilot-release")
    release.add_argument("--design-lock", type=Path, required=True)
    release.add_argument("--pilot-gate", type=Path, required=True)
    release.add_argument("--analysis-manifest", type=Path, required=True)
    release.add_argument("--created-at")
    release.add_argument("--output", type=Path, required=True)
    _custody_arguments(release)

    verify = sub.add_parser("verify")
    verify.add_argument("--design-lock", type=Path, required=True)
    verify.add_argument("--pilot-release", type=Path)
    verify.add_argument("--commitment", type=Path, required=True)

    args = parser.parse_args(argv)
    try:
        if args.action == "create-design-lock":
            return _create_design_lock(args)
        if args.action == "create-pilot-release":
            return _create_pilot_release(args)
        return _verify(args)
    except (
        AnalysisManifestError,
        BlindingError,
        OSError,
        ScheduleError,
        V2DesignLockError,
        ValueError,
    ) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
