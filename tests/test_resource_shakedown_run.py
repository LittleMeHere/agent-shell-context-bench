from __future__ import annotations

import dataclasses
import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from harness.logging.writer import SCHEMA_VERSION as TRIAL_SCHEMA_VERSION
from harness.schedule_identity import ScheduleIdentity
from scripts.r016_receipt_audit import ReceiptAuditError, audit_receipt, expected_schedule
from scripts.resource_shakedown_plan import build_shakedown_plan, load_plan, write_plan
from scripts.resource_shakedown_run import (
    BOUND_MANIFEST,
    LOCK_NAME,
    build_argv,
    execute_calls,
    select_calls,
    validate_execution_paths,
)


def _plan():
    return build_shakedown_plan(
        agy_cli_version="1.1.10",
        created_at="2026-08-06T00-00-00Z",
    )


def test_manifest_round_trip_and_tamper_rejection(tmp_path: Path) -> None:
    path = tmp_path / "plan.json"
    write_plan(_plan(), path)
    assert load_plan(path).digest == _plan().digest
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["calls"][0]["model_id"] = "tampered"
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ValueError, match="digest mismatch"):
        load_plan(path)


def test_select_calls_preserves_manifest_order_and_validates_filters() -> None:
    plan = _plan()
    selected = select_calls(
        plan,
        agents={"codex"},
        envs={"windows_wsl2"},
        stages={"transport-qualification"},
    )
    assert len(selected) == 1
    assert selected[0].config_id == "CFG4"
    with pytest.raises(ValueError, match="unknown agent"):
        select_calls(plan, agents={"invented"})
    with pytest.raises(ValueError, match="max_calls"):
        select_calls(plan, max_calls=0)


def test_build_argv_hides_outcomes_and_pins_call() -> None:
    call = next(
        call
        for call in _plan().calls
        if call.stage == "transport-qualification" and call.config_id == "CFG4"
    )
    plan = _plan()
    argv = build_argv(plan, call, Path("output"))
    assert "--hide-outcomes" in argv
    assert argv[argv.index("--expect-cli-version") + 1] == "0.139.0"
    assert argv[argv.index("--trials") + 1] == "1"
    assert argv[argv.index("--valid-slot-index") + 1] == "0"
    assert "--phrasing" not in argv
    identity = ScheduleIdentity.decode_token(
        argv[argv.index("--schedule-token") + 1]
    )
    assert identity.phase == "resource-shakedown"
    assert identity.plan_digest == plan.digest
    assert identity.config_id == call.config_id
    assert identity.task_sha256 == call.task_sha256
    assert identity.trial_schema_version == TRIAL_SCHEMA_VERSION
    assert identity.valid_slot_index == 0


def test_execution_refuses_methodology_checkout_and_repo_output(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="methodology checkout"):
        validate_execution_paths(tmp_path, cwd=Path(__file__).resolve().parents[1])
    with pytest.raises(ValueError, match="external private"):
        validate_execution_paths(
            Path(__file__).resolve().parents[1] / "data" / "shakedown",
            cwd=tmp_path,
        )


def test_fake_execution_binds_outputs_and_writes_receipt(tmp_path: Path) -> None:
    plan = _plan()
    call = select_calls(
        plan,
        agents={"codex"},
        envs={"windows_wsl2"},
        stages={"transport-qualification"},
    )[0]
    output = tmp_path / "private-output"

    def fake_executor(argv, **kwargs):
        call_root = Path(argv[argv.index("--output") + 1])
        artifact = call_root / "fake" / "trial_0.json"
        artifact.parent.mkdir(parents=True)
        artifact.write_text('{"validity":{"valid":true}}', encoding="utf-8")
        return subprocess.CompletedProcess(argv, 0, "hidden", "")

    assert (
        execute_calls(
            plan,
            [call],
            output_root=output,
            cwd=tmp_path,
            executor=fake_executor,
        )
        == 0
    )
    assert (output / BOUND_MANIFEST).exists()
    assert not (output / LOCK_NAME).exists()
    receipt = json.loads(
        (output / "calls" / call.call_id / "receipt.json").read_text(
            encoding="utf-8"
        )
    )
    assert receipt["manifest_digest"] == plan.digest
    assert receipt["call"]["call_id"] == call.call_id
    assert len(receipt["artifacts"]) == 1
    assert len(receipt["artifacts"][0]["sha256"]) == 64

    with pytest.raises(ValueError, match="duplicate shakedown call"):
        execute_calls(
            plan,
            [call],
            output_root=output,
            cwd=tmp_path,
            executor=fake_executor,
        )


def _write_r016_receipt(tmp_path: Path, plan, call) -> Path:
    call_root = tmp_path / "calls" / call.call_id
    base = call_root / call.env_id / call.agent_id / call.model_id / call.task_id
    if call.phrasing != "default":
        base /= call.phrasing
    base.mkdir(parents=True)
    schedule = expected_schedule(plan, call).as_dict()
    attempt_id = "a" * 32
    trial_path = base / "trial_0__2026-08-15T00-00-00Z.json"
    trial = {
        "schema_version": TRIAL_SCHEMA_VERSION,
        "schedule": schedule,
        "validity": {"valid": True, "harness_error": None},
        "trial": {
            "task_id": call.task_id,
            "agent_id": call.agent_id,
            "model_id": call.model_id,
            "env_id": call.env_id,
            "phrasing": call.phrasing,
            "trial_index": call.replicate - 1,
        },
    }
    trial_path.write_text(json.dumps(trial), encoding="utf-8")
    trial_rel = trial_path.relative_to(call_root).as_posix()
    trial_sha = hashlib.sha256(trial_path.read_bytes()).hexdigest()
    attempts = base / ".attempts"
    attempts.mkdir()
    events = ["allocated", "launch_committed", "invocation_observed", "trial_recorded"]
    for sequence, event in enumerate(events):
        row = {
            "schema_version": "1.3.0",
            "sequence": sequence,
            "event": event,
            "schedule": schedule,
            "attempt": {"attempt_id": attempt_id},
        }
        if event == "trial_recorded":
            row["result"] = {
                "trial_record": trial_rel,
                "trial_record_sha256": trial_sha,
                "valid": True,
            }
        (attempts / f"attempt__0{sequence}_{event}.json").write_text(
            json.dumps(row), encoding="utf-8"
        )
    artifacts = []
    for path in sorted(call_root.rglob("*.json")):
        artifacts.append(
            {
                "path": path.relative_to(call_root).as_posix(),
                "bytes": path.stat().st_size,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
        )
    receipt = {
        "schema_version": "1.0.0",
        "analysis_excluded": True,
        "manifest_digest": plan.digest,
        "returncode": 0,
        "call": dataclasses.asdict(call),
        "artifacts": artifacts,
    }
    receipt_path = call_root / "receipt.json"
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    return receipt_path


def test_r016_receipt_audit_reconstructs_and_falsifies_schedule(tmp_path: Path) -> None:
    plan = _plan()
    call = plan.calls[0]
    receipt_path = _write_r016_receipt(tmp_path, plan, call)

    summary = audit_receipt(receipt_path, plan=plan, call=call)

    assert summary["call_id"] == call.call_id
    assert summary["artifacts"] == 5
    assert summary["attempts"] == 4

    trial_path = next(
        path
        for path in receipt_path.parent.rglob("trial_*.json")
        if ".attempts" not in path.parts
    )
    raw = json.loads(trial_path.read_text(encoding="utf-8"))
    raw["schedule"]["phase"] = "confirmatory"
    trial_path.write_text(json.dumps(raw), encoding="utf-8")
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    row = next(
        item
        for item in receipt["artifacts"]
        if item["path"] == trial_path.relative_to(receipt_path.parent).as_posix()
    )
    row["bytes"] = trial_path.stat().st_size
    row["sha256"] = hashlib.sha256(trial_path.read_bytes()).hexdigest()
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")

    with pytest.raises(ReceiptAuditError, match="trial schedule identity is invalid"):
        audit_receipt(receipt_path, plan=plan, call=call)
