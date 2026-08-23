"""Independently audit R-016 bindings in analysis-excluded shakedown receipts.

Receipt roots are ordered from newest/accepted to older fallback evidence.
The first receipt for each manifest call wins; duplicate call IDs within one
root fail closed. Raw paths and model output are never emitted.
"""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any, Mapping, Sequence

from harness.logging.writer import SCHEMA_VERSION as TRIAL_SCHEMA_VERSION
from harness.schedule_identity import ScheduleIdentity
from scripts.resource_shakedown_plan import ShakedownCall, ShakedownPlan, load_plan


class ReceiptAuditError(ValueError):
    """A receipt composition or bound artifact fails closed."""


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _object(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReceiptAuditError(f"{label} is unreadable JSON") from exc
    if not isinstance(value, dict):
        raise ReceiptAuditError(f"{label} must be a JSON object")
    return value


def expected_schedule(plan: ShakedownPlan, call: ShakedownCall) -> ScheduleIdentity:
    """Reconstruct the child identity from the manifest, not the receipt."""

    cell_id = hashlib.sha256(
        f"resource-shakedown:{plan.digest}:{call.call_id}".encode("utf-8")
    ).hexdigest()[:16]
    return ScheduleIdentity.create(
        phase="resource-shakedown",
        plan_digest=plan.digest,
        cell_id=cell_id,
        config_id=call.config_id,
        task_sha256=call.task_sha256,
        trial_schema_version=TRIAL_SCHEMA_VERSION,
        target_valid_trials=1,
        task_id=call.task_id,
        agent_id=call.agent_id,
        model_id=call.model_id,
        env_id=call.env_id,
        phrasing=call.phrasing,
        expected_cli_version=call.expected_cli_version,
        valid_slot_index=0,
    )


def _declared_artifacts(receipt: Mapping[str, object]) -> dict[str, Mapping[str, object]]:
    rows = receipt.get("artifacts")
    if not isinstance(rows, list) or not rows:
        raise ReceiptAuditError("receipt artifacts must be a non-empty array")
    declared: dict[str, Mapping[str, object]] = {}
    for row in rows:
        if not isinstance(row, dict) or set(row) != {"path", "bytes", "sha256"}:
            raise ReceiptAuditError("receipt artifact row is malformed")
        rel = row.get("path")
        if not isinstance(rel, str) or not rel or rel in declared:
            raise ReceiptAuditError("receipt artifact path is invalid or duplicated")
        candidate = Path(rel)
        if candidate.is_absolute() or ".." in candidate.parts:
            raise ReceiptAuditError("receipt artifact path escapes its call root")
        declared[rel] = row
    return declared


def audit_receipt(
    receipt_path: Path,
    *,
    plan: ShakedownPlan,
    call: ShakedownCall,
) -> dict[str, object]:
    """Audit one receipt, its exact artifact inventory, and every schedule copy."""

    receipt_path = receipt_path.resolve()
    call_root = receipt_path.parent
    receipt = _object(receipt_path, "receipt")
    if receipt.get("schema_version") != "1.0.0":
        raise ReceiptAuditError("unsupported receipt schema")
    if receipt.get("analysis_excluded") is not True:
        raise ReceiptAuditError("receipt is not analysis-excluded")
    if receipt.get("manifest_digest") != plan.digest:
        raise ReceiptAuditError("receipt manifest digest mismatch")
    if receipt.get("returncode") != 0:
        raise ReceiptAuditError("receipt process did not return zero")
    expected_call = json.loads(_canonical_json(dataclasses.asdict(call)))
    if receipt.get("call") != expected_call:
        raise ReceiptAuditError("receipt call contradicts the manifest")

    declared = _declared_artifacts(receipt)
    actual = {
        path.relative_to(call_root).as_posix(): path
        for path in call_root.rglob("*")
        if path.is_file() and path.resolve() != receipt_path
    }
    if set(actual) != set(declared):
        raise ReceiptAuditError("receipt artifact inventory is incomplete or excess")
    for rel, path in actual.items():
        row = declared[rel]
        if row.get("bytes") != path.stat().st_size or row.get("sha256") != _sha256(path):
            raise ReceiptAuditError("receipt artifact byte/hash mismatch")

    trial_paths = [
        path
        for rel, path in actual.items()
        if path.suffix == ".json"
        and ".attempts" not in Path(rel).parts
        and path.name.startswith("trial_")
    ]
    attempt_paths = [
        path
        for rel, path in actual.items()
        if path.suffix == ".json" and ".attempts" in Path(rel).parts
    ]
    if len(trial_paths) != 1 or len(attempt_paths) != 4:
        raise ReceiptAuditError("accepted call must contain one trial and four attempts")

    expected = expected_schedule(plan, call).as_dict()
    trial = _object(trial_paths[0], "trial record")
    try:
        observed_trial_schedule = ScheduleIdentity.from_dict(trial.get("schedule", {}))
    except (TypeError, ValueError) as exc:
        raise ReceiptAuditError("trial schedule identity is invalid") from exc
    if observed_trial_schedule.as_dict() != expected:
        raise ReceiptAuditError("trial schedule identity contradicts the manifest")
    if trial.get("schema_version") != TRIAL_SCHEMA_VERSION:
        raise ReceiptAuditError("trial schema does not match the current writer")
    if trial.get("validity", {}).get("valid") is not True:
        raise ReceiptAuditError("accepted cross-host trial is not valid")
    trial_identity = trial.get("trial", {})
    expected_trial = {
        "task_id": call.task_id,
        "agent_id": call.agent_id,
        "model_id": call.model_id,
        "env_id": call.env_id,
        "phrasing": call.phrasing,
        "trial_index": call.replicate - 1,
    }
    if not isinstance(trial_identity, dict) or any(
        trial_identity.get(field) != value for field, value in expected_trial.items()
    ):
        raise ReceiptAuditError("trial coordinates contradict the manifest")

    attempts = [_object(path, "attempt event") for path in attempt_paths]
    attempts.sort(key=lambda row: row.get("sequence", -1))
    if [row.get("sequence") for row in attempts] != [0, 1, 2, 3]:
        raise ReceiptAuditError("attempt sequence is incomplete or reordered")
    if [row.get("event") for row in attempts] != [
        "allocated",
        "launch_committed",
        "invocation_observed",
        "trial_recorded",
    ]:
        raise ReceiptAuditError("attempt lifecycle is incomplete or contradictory")
    attempt_ids = set()
    for row in attempts:
        try:
            observed = ScheduleIdentity.from_dict(row.get("schedule", {}))
        except (TypeError, ValueError) as exc:
            raise ReceiptAuditError("attempt schedule identity is invalid") from exc
        if observed.as_dict() != expected:
            raise ReceiptAuditError("attempt schedule identity contradicts the manifest")
        attempt = row.get("attempt")
        if not isinstance(attempt, dict):
            raise ReceiptAuditError("attempt identity is missing")
        attempt_ids.add(attempt.get("attempt_id"))
    if len(attempt_ids) != 1:
        raise ReceiptAuditError("attempt lifecycle changes attempt identity")

    terminal = attempts[-1].get("result")
    if not isinstance(terminal, dict):
        raise ReceiptAuditError("terminal attempt result is missing")
    trial_rel = trial_paths[0].relative_to(call_root).as_posix()
    if (
        terminal.get("trial_record") != trial_rel
        or terminal.get("trial_record_sha256") != _sha256(trial_paths[0])
        or terminal.get("valid") is not True
    ):
        raise ReceiptAuditError("terminal attempt does not bind the valid trial")

    return {
        "call_id": call.call_id,
        "receipt_sha256": _sha256(receipt_path),
        "artifacts": len(actual),
        "attempts": len(attempt_paths),
        "env_id": call.env_id,
        "config_id": call.config_id,
    }


def audit_composition(
    plan: ShakedownPlan,
    receipt_roots: Sequence[Path],
) -> dict[str, object]:
    """Select a complete precedence-ordered composition and audit all calls."""

    if not receipt_roots:
        raise ReceiptAuditError("at least one receipt root is required")
    calls = {call.call_id: call for call in plan.calls}
    selected: dict[str, tuple[Path, int]] = {}
    superseded = 0
    for priority, root in enumerate(receipt_roots):
        root = root.resolve()
        if not root.is_dir():
            raise ReceiptAuditError("receipt root does not exist")
        local: dict[str, Path] = {}
        for path in sorted(root.rglob("receipt.json")):
            raw = _object(path, "receipt")
            if raw.get("manifest_digest") != plan.digest:
                raise ReceiptAuditError("supplied root contains a foreign manifest")
            call = raw.get("call")
            call_id = call.get("call_id") if isinstance(call, dict) else None
            if call_id not in calls:
                raise ReceiptAuditError("supplied root contains an unknown call")
            if call_id in local:
                raise ReceiptAuditError("one receipt root duplicates a call ID")
            local[call_id] = path
        for call_id, path in local.items():
            if call_id in selected:
                superseded += 1
            else:
                selected[call_id] = (path, priority)
    missing = sorted(set(calls) - set(selected))
    if missing:
        raise ReceiptAuditError(f"receipt composition is missing {len(missing)} calls")

    rows = []
    for call in plan.calls:
        path, priority = selected[call.call_id]
        row = audit_receipt(path, plan=plan, call=call)
        rows.append({**row, "root_priority": priority})
    digest_rows = [
        {
            "call_id": row["call_id"],
            "receipt_sha256": row["receipt_sha256"],
            "root_priority": row["root_priority"],
        }
        for row in rows
    ]
    return {
        "schema_version": "1.0.0",
        "manifest_digest": plan.digest,
        "calls": len(rows),
        "artifacts": sum(int(row["artifacts"]) for row in rows),
        "attempts": sum(int(row["attempts"]) for row in rows),
        "environments": dict(sorted(Counter(row["env_id"] for row in rows).items())),
        "configurations": dict(
            sorted(Counter(row["config_id"] for row in rows).items())
        ),
        "superseded_receipts": superseded,
        "composition_sha256": hashlib.sha256(
            _canonical_json(digest_rows).encode("utf-8")
        ).hexdigest(),
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--root", type=Path, action="append", required=True)
    args = parser.parse_args(argv)
    summary = audit_composition(load_plan(args.manifest), args.root)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
