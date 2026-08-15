from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from harness.logging.writer import SCHEMA_VERSION as TRIAL_SCHEMA_VERSION
from harness.schedule_identity import ScheduleIdentity
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
