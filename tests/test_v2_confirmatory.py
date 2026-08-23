"""Prospective fixed-N V2 confirmatory authorization and schedule tests."""

from __future__ import annotations

import dataclasses
import base64
import hashlib
import json
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization

from harness.scheduler import (
    V2_CONFIRMATORY_PHASE,
    ScheduleError,
    build_plan,
    v2_confirmatory_epoch_for_position,
    v2_task_bank_digest,
    validate_plan,
    load_plan,
)
from harness.v2_design_lock import (
    V2DesignLockError,
    build_v2_design_lock,
    build_v2_pilot_release,
    validate_provider_cap_authorization,
)
from analysis.v2_finite_roster import expected_h1_leaf_counts_by_v2_pilot_epoch


KEY = Ed25519PrivateKey.from_private_bytes(b"\x42" * 32)


def _digest(value: object) -> str:
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _provider_cap(*, supported: bool = True, required: float = 50.0):
    payload = {
        "schema_version": "1.0.0",
        "purpose": "v2_n36_provider_calendar_authorization",
        "as_of_date": "2026-08-22",
        "n36_supported": supported,
        "calendar_days_cap": 30,
        "human_audit_hours_cap": 24.0,
        "providers": {
            provider: {
                "window_unit": f"{provider}-measured-unit",
                "total_window_units": 100.0,
                "planned_units": 60.0,
                "retry_units": 10.0,
                "untouched_units": 30.0,
                "n36_required_units": required,
            }
            for provider in (
                "anthropic_subscription",
                "openai_subscription",
                "antigravity_subscription",
            )
        },
        "inter_trial_delay_seconds": {
            "claude_code": 1.0,
            "codex": 1.0,
            "agy": 1.0,
        },
    }
    return {**payload, "artifact_digest": _digest(payload)}


def _authorization(frozen_runtime_binding, anchor=None):
    pilot_plan_digest = "1" * 64
    anchor = anchor or {
        "commitment_digest": "5" * 64,
        "commitment_artifact_sha256": "6" * 64,
        "commitment_public_key_b64": base64.b64encode(
            KEY.public_key().public_bytes(
                serialization.Encoding.Raw, serialization.PublicFormat.Raw
            )
        ).decode("ascii"),
    }
    lock = build_v2_design_lock(
        signing_key=KEY,
        pilot_plan_digest=pilot_plan_digest,
        runtime_matrix_digest=frozen_runtime_binding.matrix_digest,
        task_bank_digest=v2_task_bank_digest(),
        analysis_artifact_sha256="2" * 64,
        simulation_artifact_sha256="3" * 64,
        provider_cap_authorization=_provider_cap(),
        pilot_commitment_anchor=anchor,
        order_seed=20260525,
        created_at="2026-08-22T00-00-00Z",
    )
    gate = {
        "schema_version": "1.0.0",
        "plan_digest": pilot_plan_digest,
        "analysis_manifest_digest": "4" * 64,
        "capability_trials": 360,
        "failures": 100,
        "successes": 260,
        "failing_families": 8,
        "successful_families": 12,
        "failing_domains": 5,
        "successful_domains": 6,
        "domain_concentration_diagnostic": False,
        "branch": "proceed",
        "confirmatory_collection_allowed": True,
        "task_change_requires_amendment_and_fresh_pilot": False,
    }
    gate["artifact_digest"] = _digest(gate)
    release = build_v2_pilot_release(
        design_lock=lock,
        signing_key=KEY,
        pilot_gate_artifact=gate,
        analysis_manifest_digest="4" * 64,
        created_at="2026-08-23T00-00-00Z",
    )
    return lock, release, anchor


def test_provider_cap_requires_real_60_10_30_support():
    assert validate_provider_cap_authorization(_provider_cap())
    with pytest.raises(V2DesignLockError, match="approve N=36"):
        validate_provider_cap_authorization(_provider_cap(supported=False))
    with pytest.raises(V2DesignLockError, match="cannot support N=36"):
        validate_provider_cap_authorization(_provider_cap(required=61.0))
    malformed = _provider_cap()
    malformed["providers"]["openai_subscription"]["planned_units"] = 59.0
    malformed["artifact_digest"] = _digest(
        {key: value for key, value in malformed.items() if key != "artifact_digest"}
    )
    with pytest.raises(V2DesignLockError, match="60/10/30"):
        validate_provider_cap_authorization(malformed)


def test_v2_confirmatory_requires_signed_release(frozen_runtime_binding):
    lock, release, anchor = _authorization(frozen_runtime_binding)
    with pytest.raises(ScheduleError, match="design lock.*pilot release"):
        build_plan(
            V2_CONFIRMATORY_PHASE,
            runtime_binding=frozen_runtime_binding,
            v2_design_lock=lock,
            sizing_anchor=anchor,
        )
    tampered = dataclasses.replace(release, branch="ceiling")
    with pytest.raises(ScheduleError, match="invalid V2 design authorization"):
        build_plan(
            V2_CONFIRMATORY_PHASE,
            runtime_binding=frozen_runtime_binding,
            v2_design_lock=lock,
            v2_pilot_release=tampered,
            sizing_anchor=anchor,
        )
    wrong_anchor = {**anchor, "commitment_digest": "9" * 64}
    with pytest.raises(ScheduleError, match="invalid V2 design authorization"):
        build_plan(
            V2_CONFIRMATORY_PHASE,
            runtime_binding=frozen_runtime_binding,
            v2_design_lock=lock,
            v2_pilot_release=release,
            sizing_anchor=wrong_anchor,
        )


def test_v2_confirmatory_exact_n36_roster_and_epochs(frozen_runtime_binding):
    lock, release, anchor = _authorization(frozen_runtime_binding)
    plan = build_plan(
        V2_CONFIRMATORY_PHASE,
        runtime_binding=frozen_runtime_binding,
        v2_design_lock=lock,
        v2_pilot_release=release,
        sizing_anchor=anchor,
    )
    assert validate_plan(plan) == plan
    assert len(plan.cells) == 1890
    assert len(plan.execution_slots or ()) == 28980
    capability = [cell for cell in plan.cells if cell.task_id.startswith("C")]
    seeded = [cell for cell in plan.cells if cell.task_id.startswith("T")]
    assert len(capability) == 1260
    assert len(seeded) == 630
    assert {cell.target_valid_trials for cell in capability} == {5}
    assert {cell.target_valid_trials for cell in seeded} == {36}
    assert sum(cell.target_valid_trials for cell in capability) == 6300
    assert sum(cell.target_valid_trials for cell in seeded) == 22680

    cells = {cell.cell_id: cell for cell in plan.cells}
    slots = plan.execution_slots or ()
    for epoch in range(4):
        members = [
            slot for slot in slots
            if v2_confirmatory_epoch_for_position(slot.position) == epoch
        ]
        assert len(members) == 7245
        epoch_cells = [cells[slot.cell_id] for slot in members]
        assert {cell.env_id for cell in epoch_cells} == {
            "windows_powershell", "windows_pwsh7", "windows_wsl2",
            "linux_native", "macos_actions",
        }
        assert all(
            sum(cell.env_id == env for cell in epoch_cells) == 1449
            for env in {cell.env_id for cell in epoch_cells}
        )
        assert sum(cell.task_id.startswith("C") for cell in epoch_cells) == 1575
        assert sum(cell.task_id.startswith("T") for cell in epoch_cells) == 5670
        assert all(
            sum(cell.config_id == config for cell in epoch_cells) == 1035
            for config in {cell.config_id for cell in epoch_cells}
        )
        assert len({cell.task_id for cell in epoch_cells if cell.task_id.startswith("C")}) == 36
        assert len({(cell.task_id, cell.phrasing) for cell in epoch_cells if cell.task_id.startswith("T")}) == 18


def test_v2_confirmatory_rejects_redigested_plan_target_tamper(frozen_runtime_binding):
    lock, release, anchor = _authorization(frozen_runtime_binding)
    plan = build_plan(
        V2_CONFIRMATORY_PHASE,
        runtime_binding=frozen_runtime_binding,
        v2_design_lock=lock,
        v2_pilot_release=release,
        sizing_anchor=anchor,
    )
    cells = list(plan.cells)
    cells[0] = dataclasses.replace(cells[0], target_valid_trials=6)
    forged = dataclasses.replace(plan, cells=tuple(cells), digest="")
    from harness.scheduler import _digest_payload
    forged = dataclasses.replace(forged, digest=_digest_payload(forged.payload()))
    with pytest.raises(ScheduleError):
        validate_plan(forged)


def test_v2_confirmatory_rechecks_live_task_bytes(
    frozen_runtime_binding, monkeypatch
):
    lock, release, anchor = _authorization(frozen_runtime_binding)
    plan = build_plan(
        V2_CONFIRMATORY_PHASE,
        runtime_binding=frozen_runtime_binding,
        v2_design_lock=lock,
        v2_pilot_release=release,
        sizing_anchor=anchor,
    )
    monkeypatch.setattr("harness.scheduler._sha256_file", lambda _path: "0" * 64)
    with pytest.raises(
        ScheduleError, match="task bank|changed after plan|differs from its design lock"
    ):
        validate_plan(plan)


def test_v2_confirmatory_cli_creates_and_loads_plan(
    tmp_path, frozen_runtime_binding
):
    from harness.__main__ import main

    matrix_path = tmp_path / "matrix.json"
    source_matrix = json.loads(
        (
            Path(__file__).resolve().parents[1]
            / "config"
            / "v2-runtime-matrix.candidate.json"
        ).read_text(encoding="utf-8")
    )
    source_matrix["status"] = "frozen"
    matrix_path.write_text(json.dumps(source_matrix), encoding="utf-8")
    public_key_b64 = base64.b64encode(
        KEY.public_key().public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw
        )
    ).decode("ascii")
    commitment_payload = {
        "schema_version": "1.0.0",
        "purpose": "pilot_blinding_public_commitment",
        "created_at": "2026-08-22T00-00-00Z",
        "plan_digest": "1" * 64,
        "mapping_digest": "7" * 64,
        "public_key_b64": public_key_b64,
    }
    commitment = {
        **commitment_payload,
        "commitment_digest": _digest(commitment_payload),
    }
    commitment_path = tmp_path / "commitment.json"
    commitment_bytes = json.dumps(commitment).encode("utf-8")
    commitment_path.write_bytes(commitment_bytes)
    anchor = {
        "commitment_digest": commitment["commitment_digest"],
        "commitment_artifact_sha256": hashlib.sha256(commitment_bytes).hexdigest(),
        "commitment_public_key_b64": public_key_b64,
    }
    lock, release, _ = _authorization(frozen_runtime_binding, anchor)
    lock_path = tmp_path / "design.json"
    release_path = tmp_path / "release.json"
    manifest = tmp_path / "plan.json"
    lock_path.write_text(json.dumps(lock.as_dict()), encoding="utf-8")
    release_path.write_text(json.dumps(release.as_dict()), encoding="utf-8")

    assert main([
        "schedule", "plan", "--phase", V2_CONFIRMATORY_PHASE,
        "--runtime-matrix", str(matrix_path),
        "--v2-design-lock", str(lock_path),
        "--v2-pilot-release", str(release_path),
        "--blinding-commitment", str(commitment_path),
        "--manifest", str(manifest),
    ]) == 0
    plan = load_plan(manifest)
    assert plan.phase == V2_CONFIRMATORY_PHASE
    assert len(plan.execution_slots or ()) == 28980


def test_v2_confirmatory_epoch_sensitivity_roster_is_phase_aware(
    frozen_runtime_binding,
):
    lock, release, anchor = _authorization(frozen_runtime_binding)
    plan = build_plan(
        V2_CONFIRMATORY_PHASE,
        runtime_binding=frozen_runtime_binding,
        v2_design_lock=lock,
        v2_pilot_release=release,
        sizing_anchor=anchor,
    )
    counts = expected_h1_leaf_counts_by_v2_pilot_epoch(
        plan,
        expected_configurations=tuple(f"CFG{i}" for i in range(1, 8)),
    )
    assert set(counts) == {0, 1, 2, 3}
    for epoch_counts in counts.values():
        assert len(epoch_counts) == 2 * 7 * 36
        assert set(epoch_counts.values()) <= {1, 2}
        assert sum(epoch_counts.values()) == 45 * 2 * 7


def test_provider_cap_cli_is_exclusive_and_verifiable(tmp_path, capsys):
    from scripts.v2_provider_cap import main

    output = tmp_path / "private-cap.json"
    create_args = [
        "create", "--as-of-date", "2026-08-22",
        "--calendar-days-cap", "30", "--human-audit-hours-cap", "24",
        "--provider", "anthropic_subscription=measured-meter,100,50",
        "--provider", "openai_subscription=measured-meter,100,50",
        "--provider", "antigravity_subscription=measured-meter,100,50",
        "--delay", "claude_code=1", "--delay", "codex=1", "--delay", "agy=1",
        "--output", str(output),
    ]
    assert main(create_args) == 0
    assert "providers" not in capsys.readouterr().out
    assert main(["verify", "--artifact", str(output)]) == 0
    assert main(create_args) == 2
