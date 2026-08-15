"""Tests for the outcome-blind matrix scheduler.

These tests never invoke an agent CLI or the benchmark harness.  Execution
tests inject a fake child process that writes minimal immutable records into
temporary directories.
"""

from __future__ import annotations

import dataclasses
import json
import hashlib
import base64
import subprocess
import sys
from contextlib import contextmanager
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

_BENCH = Path(__file__).resolve().parents[1]
if str(_BENCH) not in sys.path:
    sys.path.insert(0, str(_BENCH))

from harness.scheduler import (
    BOUND_PLAN_NAME,
    LOCK_NAME,
    PLAN_SCHEMA_VERSION,
    CellState,
    ScheduleError,
    build_plan,
    build_run_argv,
    load_plan,
    pending_execution_units,
    run_schedule,
    scan_cell_output,
    scan_output,
    schedule_identity_for_cell,
    task_variants,
    v2_task_variants,
    validate_execution_paths,
    validate_pilot_blinding_commitment,
    write_plan,
)
from harness.attempts import (
    ATTEMPT_SCHEMA_VERSION,
    COMPLETE,
    POST_INVOCATION_INFRASTRUCTURE_FAILURE,
    AttemptJournal,
)
from harness.logging.writer import SCHEMA_VERSION as TRIAL_SCHEMA_VERSION
from harness.schedule_identity import ScheduleIdentity
from harness.sizing_lock import build_sizing_lock, write_sizing_lock
from harness.blinding import prepare_blinding_custody
from harness.types import (
    AgentRunResult,
    FilesystemDiff,
    FilesystemSnapshot,
    ProcessResult,
    SandboxHandle,
)


_SIZING_KEY = Ed25519PrivateKey.from_private_bytes(b"\x27" * 32)
_SIZING_PUBLIC_KEY_B64 = base64.b64encode(
    _SIZING_KEY.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )
).decode("ascii")


def _write_record(
    root: Path,
    plan,
    cell,
    index: int,
    *,
    valid: bool,
    schema_version: str = TRIAL_SCHEMA_VERSION,
    finalize: bool = True,
    valid_slot_index: int | None = None,
) -> Path:
    schedule_identity = schedule_identity_for_cell(
        plan, cell, valid_slot_index=valid_slot_index
    )
    journal = AttemptJournal.allocate(
        data_root=root,
        task_id=cell.task_id,
        agent_id=cell.agent_id,
        model_id=cell.model_id,
        env_id=cell.env_id,
        phrasing=cell.phrasing,
        trial_index=index,
        schedule_identity=schedule_identity,
    )
    journal.mark_launch_committed()
    journal.mark_invocation_observed()
    directory = root.joinpath(
        cell.env_id,
        cell.agent_id,
        cell.model_id,
        cell.task_id,
        cell.phrasing,
    )
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"trial_{index}__2026-07-16T00-00-{index:02d}Z.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": schema_version,
                "trial": {
                    "env_id": cell.env_id,
                    "agent_id": cell.agent_id,
                    "model_id": cell.model_id,
                    "task_id": cell.task_id,
                    "family_id": cell.family_id,
                    "instance_id": cell.instance_id,
                    "instance_sha256": cell.instance_sha256,
                    "phrasing": cell.phrasing,
                    "trial_index": index,
                },
                "attempt": journal.binding,
                "environment_probe": {"env_id": cell.env_id},
                "agent_cli_version": (
                    f"fake-cli {cell.expected_cli_version}"
                ),
                "validity": {"valid": valid, "harness_error": None},
                "measurement": {"status": "complete"},
                "schedule": schedule_identity.as_dict(),
                # Deliberately contradictory: scheduler decisions must never
                # use this field.
                "outcome": {"success": not valid},
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    if finalize:
        journal.finalize_trial(
            path,
            valid=valid,
            attribution=(
                COMPLETE if valid else POST_INVOCATION_INFRASTRUCTURE_FAILURE
            ),
        )
    return path


def _allocate_journal(root: Path, plan, cell, index: int) -> AttemptJournal:
    return AttemptJournal.allocate(
        data_root=root,
        task_id=cell.task_id,
        agent_id=cell.agent_id,
        model_id=cell.model_id,
        env_id=cell.env_id,
        phrasing=cell.phrasing,
        trial_index=index,
        schedule_identity=schedule_identity_for_cell(plan, cell),
    )


def _replace_schedule_identity(identity: ScheduleIdentity, **changes):
    payload = identity.payload()
    payload.update(changes)
    payload.pop("schema_version")
    return ScheduleIdentity.create(**payload)


def _single_pilot_cell(plan):
    return next(
        cell
        for cell in plan.cells
        if cell.env_id == "windows_powershell"
        and cell.config_id == "CFG1"
        and cell.task_id == "C01"
    )


def _sizing_lock(n_per_cell: int = 6, *, n_cells: int = 805):
    digest = "a" * 64
    return build_sizing_lock(
        source_plan_digest="b" * 64,
        source_plan_schema_version="1.1.0",
        source_trial_schema_version=TRIAL_SCHEMA_VERSION,
        blinded_input_sha256="c" * 64,
        blinded_export_digest="d" * 64,
        source_manifest_digest="e" * 64,
        commitment_digest="f" * 64,
        commitment_artifact_sha256="0" * 64,
        commitment_public_key_b64=_SIZING_PUBLIC_KEY_B64,
        signing_key=_SIZING_KEY,
        code_version="pre-data-v2-test",
        code_artifacts={
            "scripts/create_sizing_lock.py": digest,
            "scripts/size_from_pilot.py": digest,
            "harness/blinding.py": digest,
            "harness/sizing_lock.py": digest,
        },
        analysis_version="analysis-test-v1",
        analysis_artifact_sha256="1" * 64,
        simulation_config_version="simulation-test-v1",
        simulation_config_sha256="2" * 64,
        task_class="capability",
        compute_budget=float(n_per_cell * n_cells),
        per_trial_cost=1.0,
        n_cells=n_cells,
        cap_per_cell=n_per_cell,
        result={
            "n_per_cell": n_per_cell,
            "task_class": "capability",
            "mode": "pilot",
            "cap_per_cell": n_per_cell,
            "n_trials_after_filter": 100,
            "constants": {"test": True},
        },
        created_at="2026-08-09T00-00-00Z",
    )


def _sizing_anchor(lock=None):
    value = lock or _sizing_lock()
    return {
        "commitment_digest": value.commitment_digest,
        "commitment_artifact_sha256": value.commitment_artifact_sha256,
        "commitment_public_key_b64": value.commitment_public_key_b64,
    }


def _prepare_pilot_commitment(
    root: Path,
    plan,
    artifacts_root: Path,
    label: str,
) -> None:
    manifest = artifacts_root / f"{label}-plan.json"
    write_plan(plan, manifest)
    prepare_blinding_custody(
        root,
        "correct horse battery staple",
        plan_path=manifest,
        commitment_path=artifacts_root / f"{label}-commitment.json",
        custody_path=artifacts_root / f"{label}-custody.json",
    )


def test_task_variants_are_exact_v1_roster():
    variants = task_variants()
    assert len(variants) == 23
    assert {(v.task_id, v.phrasing) for v in variants} == {
        *((f"C{i:02d}", "default") for i in range(1, 6)),
        *((f"T{i:02d}", phrasing) for i in range(1, 10)
          for phrasing in ("formal", "colloquial")),
    }
    assert len({(v.task_path, v.phrasing) for v in variants}) == 23


def test_v2_pilot_roster_binds_all_instances_and_split_targets(
    frozen_runtime_binding,
):
    variants = v2_task_variants()
    assert len(variants) == 54
    capability = [variant for variant in variants if variant.task_id.startswith("C")]
    seeded = [variant for variant in variants if variant.task_id.startswith("T")]
    assert len(capability) == 36
    assert len(seeded) == 18
    assert all(
        variant.task_id == f"{variant.family_id}-{variant.instance_id}"
        and variant.instance_sha256 == variant.task_sha256
        for variant in capability
    )


def test_v2_plan_requires_frozen_runtime_binding(frozen_runtime_binding):
    with pytest.raises(ScheduleError, match="frozen --runtime-matrix"):
        build_plan("v2-pilot")
    with pytest.raises(ScheduleError, match="requires a frozen"):
        build_plan(
            "v2-pilot",
            runtime_binding=dataclasses.replace(
                frozen_runtime_binding, matrix_status="candidate"
            ),
        )


def test_v2_filtered_pending_work_preserves_registered_slot_subsequence(
    frozen_runtime_binding,
):
    plan = build_plan(
        "v2-pilot", runtime_binding=frozen_runtime_binding
    )
    selected = [
        cell
        for cell in plan.cells
        if cell.env_id == "windows_wsl2" and cell.config_id == "CFG2"
    ]
    states = {cell.cell_id: CellState() for cell in plan.cells}
    units = pending_execution_units(plan, selected, states)
    expected = [
        (slot.cell_id, slot.valid_slot_index)
        for slot in plan.execution_slots or ()
        if slot.cell_id in {cell.cell_id for cell in selected}
    ]
    assert [(cell.cell_id, index) for cell, index in units] == expected
    repeated_cell, repeated_index = next(
        (cell, index) for cell, index in units if index == 1
    )
    states[repeated_cell.cell_id] = CellState(valid=1, next_index=1)
    resumed = pending_execution_units(plan, selected, states)
    assert (repeated_cell, repeated_index) in resumed
    assert (repeated_cell, 0) not in resumed


def test_v2_scanner_enforces_retry_slot_progression(
    tmp_path: Path, frozen_runtime_binding
):
    plan = build_plan(
        "v2-pilot", runtime_binding=frozen_runtime_binding
    )
    cell = next(
        cell
        for cell in plan.cells
        if cell.task_id == "T01"
        and cell.env_id == "windows_powershell"
        and cell.config_id == "CFG1"
    )
    root = tmp_path / "valid-progression"
    _write_record(root, plan, cell, 0, valid=False, valid_slot_index=0)
    _write_record(root, plan, cell, 1, valid=True, valid_slot_index=0)
    _write_record(root, plan, cell, 2, valid=True, valid_slot_index=1)
    assert scan_cell_output(root, plan, cell) == CellState(
        valid=2, invalid=1, unresolved=0, next_index=3
    )

    forged = tmp_path / "forged-progression"
    _write_record(forged, plan, cell, 0, valid=False, valid_slot_index=1)
    with pytest.raises(ScheduleError, match="targets valid slot"):
        scan_cell_output(forged, plan, cell)


def test_v2_execution_requires_matching_external_runtime_binding(
    tmp_path: Path, frozen_runtime_binding
):
    plan = build_plan(
        "v2-pilot", runtime_binding=frozen_runtime_binding
    )
    kwargs = {
        "output_root": tmp_path / "v2-output",
        "execute": True,
        "only_envs": {"windows_powershell"},
        "only_configs": {"CFG1"},
        "only_tasks": {"C01-I01"},
        "max_cells": 1,
    }
    with pytest.raises(ScheduleError, match="independently supplied"):
        run_schedule(plan, **kwargs)
    changed = list(frozen_runtime_binding.configurations)
    changed[0] = dataclasses.replace(changed[0], model_id="substituted")
    with pytest.raises(ScheduleError, match="differs from the plan-bound"):
        run_schedule(
            plan,
            runtime_binding=dataclasses.replace(
                frozen_runtime_binding, configurations=tuple(changed)
            ),
            **kwargs,
        )

    plan = build_plan(
        "v2-pilot",
        order_seed=13,
        runtime_binding=frozen_runtime_binding,
    )
    assert len(plan.cells) == 540
    assert sum(cell.target_valid_trials for cell in plan.cells) == 720
    assert {cell.config_id for cell in plan.cells} == {"CFG1", "CFG2"}
    assert {
        cell.target_valid_trials
        for cell in plan.cells
        if cell.task_id.startswith("C")
    } == {1}
    assert {
        cell.target_valid_trials
        for cell in plan.cells
        if cell.task_id.startswith("T")
    } == {2}
    assert all(
        schedule_identity_for_cell(plan, cell).instance_sha256
        == cell.instance_sha256
        for cell in plan.cells
    )


def test_build_plan_exact_counts_and_deterministic_order():
    pilot_a = build_plan("pilot", order_seed=7)
    pilot_b = build_plan("pilot", order_seed=7)
    pilot_other = build_plan("pilot", order_seed=8)
    assert len(pilot_a.cells) == 230
    assert sum(cell.target_valid_trials for cell in pilot_a.cells) == 460
    assert {cell.config_id for cell in pilot_a.cells} == {"CFG1", "CFG2"}
    assert [cell.cell_id for cell in pilot_a.cells] == [
        cell.cell_id for cell in pilot_b.cells
    ]
    assert pilot_a.digest == pilot_b.digest
    assert [cell.cell_id for cell in pilot_a.cells] != [
        cell.cell_id for cell in pilot_other.cells
    ]
    assert {cell.cell_id for cell in pilot_a.cells} == {
        cell.cell_id for cell in pilot_other.cells
    }

    confirmatory = build_plan(
        "confirmatory",
        sizing_lock=_sizing_lock(6),
        sizing_anchor=_sizing_anchor(),
        agy_cli_version="1.0.16",
    )
    assert len(confirmatory.cells) == 805
    assert {cell.config_id for cell in confirmatory.cells} == {
        f"CFG{i}" for i in range(1, 8)
    }
    assert sum(cell.target_valid_trials for cell in confirmatory.cells) == 805 * 6
    assert confirmatory.sizing_lock == _sizing_lock(6)


def test_confirmatory_requires_locked_n_and_day_one_agy_version():
    with pytest.raises(ScheduleError, match="registered floor"):
        build_plan(
            "confirmatory",
            sizing_lock=_sizing_lock(5),
            sizing_anchor=_sizing_anchor(),
            agy_cli_version="1.0.16",
        )
    with pytest.raises(ScheduleError, match="verified --sizing-lock"):
        build_plan("confirmatory", agy_cli_version="1.0.16")
    with pytest.raises(ScheduleError, match="agy-cli-version"):
        build_plan(
            "confirmatory",
            sizing_lock=_sizing_lock(6),
            sizing_anchor=_sizing_anchor(),
        )
    with pytest.raises(ScheduleError, match="not provenance-bound"):
        build_plan(
            "confirmatory",
            sizing_lock=_sizing_lock(8),
            sizing_anchor=_sizing_anchor(),
            codex_trials_per_cell=9,
            agy_cli_version="1.0.16",
        )
    with pytest.raises(ScheduleError, match="n_cells"):
        build_plan(
            "confirmatory",
            sizing_lock=_sizing_lock(6, n_cells=804),
            sizing_anchor=_sizing_anchor(),
            agy_cli_version="1.0.16",
        )


def test_plan_round_trip_and_refuses_overwrite(tmp_path: Path):
    plan = build_plan("pilot", order_seed=11)
    path = tmp_path / "pilot-plan.json"
    write_plan(plan, path)
    loaded = load_plan(path)
    assert loaded == plan
    assert loaded.schema_version == PLAN_SCHEMA_VERSION
    with pytest.raises(ScheduleError, match="refusing to overwrite"):
        write_plan(plan, path)


def test_legacy_v1_plan_remains_readable_but_legacy_v2_is_rejected(
    tmp_path: Path, frozen_runtime_binding
):
    def write_legacy(plan, name: str) -> Path:
        raw = plan.as_dict()
        raw["schema_version"] = "1.2.0"
        raw.pop("runtime_binding")
        raw.pop("execution_slots")
        payload = {key: value for key, value in raw.items() if key not in {
            "created_at", "digest"
        }}
        raw["digest"] = hashlib.sha256(
            json.dumps(
                payload,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            ).encode("utf-8")
        ).hexdigest()
        path = tmp_path / name
        path.write_text(json.dumps(raw), encoding="utf-8")
        return path

    legacy_v1 = write_legacy(build_plan("pilot"), "legacy-v1.json")
    assert load_plan(legacy_v1).schema_version == "1.2.0"

    legacy_v2 = write_legacy(
        build_plan("v2-pilot", runtime_binding=frozen_runtime_binding),
        "legacy-v2.json",
    )
    with pytest.raises(ScheduleError, match="lack a frozen runtime binding"):
        load_plan(legacy_v2)


def test_plan_digest_tamper_is_rejected(tmp_path: Path):
    plan = build_plan("pilot")
    path = tmp_path / "plan.json"
    write_plan(plan, path)
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["cells"][0]["target_valid_trials"] = 99
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ScheduleError, match="digest mismatch"):
        load_plan(path)


def test_confirmatory_plan_rejects_embedded_sizing_lock_tamper(tmp_path: Path):
    plan = build_plan(
        "confirmatory",
        sizing_lock=_sizing_lock(6),
        sizing_anchor=_sizing_anchor(),
        agy_cli_version="1.0.16",
    )
    path = tmp_path / "confirmatory-plan.json"
    write_plan(plan, path)
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["sizing_lock"]["result"]["n_per_cell"] = 7
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ScheduleError, match="custodian signature"):
        load_plan(path)


def test_confirmatory_plan_rejects_redigested_vendor_n_override(tmp_path: Path):
    lock = _sizing_lock(6)
    plan = build_plan(
        "confirmatory",
        sizing_lock=lock,
        sizing_anchor=_sizing_anchor(lock),
        agy_cli_version="1.0.16",
    )
    path = tmp_path / "confirmatory-plan.json"
    raw = plan.as_dict()
    for cell in raw["cells"]:
        if cell["agent_id"] == "codex":
            cell["target_valid_trials"] = 7
    payload = {
        key: value
        for key, value in raw.items()
        if key not in {"digest", "created_at"}
    }
    raw["digest"] = hashlib.sha256(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
    ).hexdigest()
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ScheduleError, match="Codex N must equal"):
        load_plan(path)


def test_confirmatory_execution_requires_external_sizing_anchor(tmp_path: Path):
    lock = _sizing_lock(6)
    plan = build_plan(
        "confirmatory",
        sizing_lock=lock,
        sizing_anchor=_sizing_anchor(lock),
        agy_cli_version="1.0.16",
    )
    calls = 0

    def forbidden_executor(*args, **kwargs):
        nonlocal calls
        calls += 1
        raise AssertionError("executor must not run")

    with pytest.raises(ScheduleError, match="independently anchored"):
        run_schedule(
            plan,
            output_root=tmp_path / "confirmatory-output",
            execute=True,
            only_envs={"windows_powershell"},
            only_configs={"CFG1"},
            only_tasks={"C01"},
            max_cells=1,
            executor=forbidden_executor,
        )
    assert calls == 0


def test_scanner_counts_only_validity_and_advances_index(tmp_path: Path):
    plan = build_plan("pilot")
    cell = _single_pilot_cell(plan)
    _write_record(tmp_path, plan, cell, 4, valid=True)
    _write_record(tmp_path, plan, cell, 5, valid=False)
    state = scan_cell_output(tmp_path, plan, cell)
    assert state.valid == 1
    assert state.invalid == 1
    assert state.next_index == 6
    states = scan_output(tmp_path, plan)
    assert states[cell.cell_id] == state


def test_scanner_rejects_stale_trial_schema(tmp_path: Path):
    plan = build_plan("pilot")
    cell = _single_pilot_cell(plan)
    _write_record(
        tmp_path,
        plan,
        cell,
        0,
        valid=True,
        schema_version="1.1.0",
    )
    with pytest.raises(
        ScheduleError,
        match=r"trial schema '1\.1\.0' does not match plan",
    ):
        scan_cell_output(tmp_path, plan, cell)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda raw: raw.update(schema_version="9.9.9"), "trial schema"),
        (lambda raw: raw["validity"].update(valid="yes"), "JSON boolean"),
        (lambda raw: raw["trial"].update(env_id="foreign"), "trial.env_id"),
        (
            lambda raw: raw["environment_probe"].update(env_id="foreign"),
            "environment_probe.env_id",
        ),
        (lambda raw: raw.update(agent_cli_version="fake 2.1.1760"), "CLI version"),
        (lambda raw: raw["trial"].update(trial_index=99), "filename index"),
    ],
)
def test_scanner_fails_closed_on_malformed_identity(
    tmp_path: Path, mutation, message: str
):
    plan = build_plan("pilot")
    cell = _single_pilot_cell(plan)
    path = _write_record(tmp_path, plan, cell, 0, valid=True)
    raw = json.loads(path.read_text(encoding="utf-8"))
    mutation(raw)
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ScheduleError, match=message):
        scan_cell_output(tmp_path, plan, cell)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("phase", "confirmatory"),
        ("plan_digest", "f" * 64),
        ("cell_id", "f" * 16),
        ("task_sha256", "0" * 64),
        ("family_id", "C99"),
        ("instance_id", "I99"),
        ("instance_sha256", "0" * 64),
        ("trial_schema_version", "9.9.9"),
        ("target_valid_trials", 99),
    ],
)
def test_scanner_rejects_validly_rehashed_foreign_schedule_identity(
    tmp_path: Path, field: str, value
):
    plan = build_plan("pilot")
    cell = _single_pilot_cell(plan)
    path = _write_record(tmp_path, plan, cell, 0, valid=True)
    raw = json.loads(path.read_text(encoding="utf-8"))
    identity = schedule_identity_for_cell(plan, cell)
    raw["schedule"] = _replace_schedule_identity(
        identity,
        **{field: value},
    ).as_dict()
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ScheduleError, match="schedule identity does not match"):
        scan_cell_output(tmp_path, plan, cell)


def test_scanner_rejects_missing_schedule_on_trial_and_attempt(tmp_path: Path):
    plan = build_plan("pilot")
    cell = _single_pilot_cell(plan)
    path = _write_record(tmp_path, plan, cell, 0, valid=True)
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw.pop("schedule")
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ScheduleError, match="missing schedule identity"):
        scan_cell_output(tmp_path, plan, cell)

    other_root = tmp_path / "attempt-only"
    journal = _allocate_journal(other_root, plan, cell, 0)
    allocated = json.loads(journal.allocated_path.read_text(encoding="utf-8"))
    allocated.pop("schedule")
    journal.allocated_path.write_text(json.dumps(allocated), encoding="utf-8")
    with pytest.raises(ScheduleError, match="missing schedule identity"):
        scan_cell_output(other_root, plan, cell)


def test_scanner_rejects_copied_record_under_other_plan(tmp_path: Path):
    original = build_plan("pilot", order_seed=1)
    replacement = build_plan("pilot", order_seed=2)
    original_cell = _single_pilot_cell(original)
    replacement_cell = _single_pilot_cell(replacement)
    assert original_cell.coordinate == replacement_cell.coordinate
    _write_record(tmp_path, original, original_cell, 0, valid=True)
    with pytest.raises(ScheduleError, match="plan_digest"):
        scan_cell_output(tmp_path, replacement, replacement_cell)


def test_scanner_rejects_foreign_cell_token_under_matching_visible_path(
    tmp_path: Path,
):
    plan = build_plan("pilot")
    cell = _single_pilot_cell(plan)
    foreign = next(
        candidate
        for candidate in plan.cells
        if candidate.config_id == cell.config_id
        and candidate.env_id == cell.env_id
        and candidate.task_id == "C02"
    )
    path = _write_record(tmp_path, plan, cell, 0, valid=True)
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["schedule"] = schedule_identity_for_cell(plan, foreign).as_dict()
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ScheduleError, match="schedule identity does not match"):
        scan_cell_output(tmp_path, plan, cell)


def test_scanner_rejects_duplicate_indices_and_overcollection(tmp_path: Path):
    plan = build_plan("pilot")
    cell = _single_pilot_cell(plan)
    first = _write_record(tmp_path, plan, cell, 0, valid=True)
    duplicate = first.with_name("trial_0__2026-07-16T01-00-00Z.json")
    duplicate.write_text(first.read_text(encoding="utf-8"), encoding="utf-8")
    with pytest.raises(ScheduleError, match="duplicate trial_index"):
        scan_cell_output(tmp_path, plan, cell)

    duplicate.unlink()
    _write_record(tmp_path, plan, cell, 1, valid=True)
    _write_record(tmp_path, plan, cell, 2, valid=True)
    with pytest.raises(ScheduleError, match="over-collected"):
        scan_cell_output(tmp_path, plan, cell)


def test_scanner_reconciles_final_trial_when_terminal_append_is_missing(
    tmp_path: Path,
):
    plan = build_plan("pilot")
    cell = _single_pilot_cell(plan)
    _write_record(tmp_path, plan, cell, 0, valid=True, finalize=False)
    state = scan_cell_output(tmp_path, plan, cell)
    assert state.valid == 1
    assert state.invalid == 0
    assert state.unresolved == 0
    assert state.next_index == 1


def test_scanner_rejects_terminal_link_whose_final_record_is_absent(
    tmp_path: Path,
):
    plan = build_plan("pilot")
    cell = _single_pilot_cell(plan)
    trial = _write_record(tmp_path, plan, cell, 0, valid=True)
    trial.unlink()
    with pytest.raises(ScheduleError, match="has no final record"):
        scan_cell_output(tmp_path, plan, cell)


def test_unresolved_started_attempt_is_reported_and_blocks_automatic_retry(
    tmp_path: Path,
):
    plan = build_plan("pilot")
    cell = _single_pilot_cell(plan)
    journal = _allocate_journal(tmp_path, plan, cell, 0)
    journal.mark_launch_committed()
    journal.mark_invocation_observed()
    state = scan_cell_output(tmp_path, plan, cell)
    assert state.valid == 0
    assert state.invalid == 0
    assert state.unresolved == 1
    assert state.next_index == 1
    write_plan(plan, tmp_path / BOUND_PLAN_NAME)
    with pytest.raises(ScheduleError, match="unresolved attempt"):
        run_schedule(
            plan,
            output_root=tmp_path,
            execute=True,
            only_envs={cell.env_id},
            only_configs={cell.config_id},
            only_tasks={cell.task_id},
        )


def test_scanner_fails_closed_on_torn_event_and_competing_terminals(
    tmp_path: Path,
):
    plan = build_plan("pilot")
    cell = _single_pilot_cell(plan)
    journal = _allocate_journal(tmp_path, plan, cell, 0)
    journal.mark_launch_committed()
    journal.mark_invocation_observed()
    invocation = next(tmp_path.rglob("*02_invocation_observed.json"))
    invocation.write_text("{", encoding="utf-8")
    with pytest.raises(ScheduleError, match="cannot parse attempt event"):
        scan_cell_output(tmp_path, plan, cell)

    invocation.write_text(
        json.dumps(
            {
                "schema_version": ATTEMPT_SCHEMA_VERSION,
                "sequence": 2,
                "event": "invocation_observed",
                "created_at": "2026-07-28T00:00:00Z",
                "attempt": journal.identity.as_dict(),
                "schedule": schedule_identity_for_cell(plan, cell).as_dict(),
            }
        ),
        encoding="utf-8",
    )
    failure = journal.finalize_infrastructure_failure(
        stage="snapshot_after",
        error=RuntimeError("injected"),
    )
    competing = failure.with_name(
        failure.name.replace(
            "03_infrastructure_failure",
            "03_trial_recorded",
        )
    )
    raw = json.loads(failure.read_text(encoding="utf-8"))
    raw["event"] = "trial_recorded"
    competing.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ScheduleError, match="duplicate sequence"):
        scan_cell_output(tmp_path, plan, cell)


def test_scanner_rejects_unframed_attempt_ledger_entry(tmp_path: Path):
    plan = build_plan("pilot")
    cell = _single_pilot_cell(plan)
    journal = _allocate_journal(tmp_path, plan, cell, 0)
    (journal.allocated_path.parent / "torn.tmp").write_text(
        "partial",
        encoding="utf-8",
    )
    with pytest.raises(ScheduleError, match="unexpected attempt-ledger entry"):
        scan_cell_output(tmp_path, plan, cell)


def test_scanner_uses_terminal_failure_as_invalid_authoritative_attempt(
    tmp_path: Path,
):
    plan = build_plan("pilot")
    cell = _single_pilot_cell(plan)
    journal = _allocate_journal(tmp_path, plan, cell, 4)
    journal.finalize_infrastructure_failure(
        stage="snapshot_before",
        error=RuntimeError("injected"),
    )
    state = scan_cell_output(tmp_path, plan, cell)
    assert state.valid == 0
    assert state.invalid == 1
    assert state.unresolved == 0
    assert state.next_index == 5


def test_scanner_counts_launch_unknown_terminal_without_calling_it_post(
    tmp_path: Path,
):
    plan = build_plan("pilot")
    cell = _single_pilot_cell(plan)
    journal = _allocate_journal(tmp_path, plan, cell, 0)
    journal.mark_launch_committed()
    terminal = journal.finalize_infrastructure_failure(
        stage="agent_invocation",
        error=FileNotFoundError("pre-spawn failure"),
    )
    raw = json.loads(terminal.read_text(encoding="utf-8"))
    assert raw["result"]["attribution"] == (
        "invocation_start_unknown_infrastructure_failure"
    )
    state = scan_cell_output(tmp_path, plan, cell)
    assert state.invalid == 1
    assert state.unresolved == 0
    assert state.next_index == 1


def test_execute_stops_when_child_returns_without_authoritative_attempt(
    tmp_path: Path,
):
    plan = build_plan("pilot")
    output = tmp_path / "pilot-output"
    control = tmp_path / "control"
    control.mkdir()
    _prepare_pilot_commitment(output, plan, tmp_path, "empty-child")
    calls = 0

    def empty_executor(argv, *, cwd, env):
        nonlocal calls
        calls += 1
        return subprocess.CompletedProcess(list(argv), 0, stdout="", stderr="")

    env = {
        name: "1"
        for name in (
            "DISABLE_TELEMETRY",
            "DISABLE_ERROR_REPORTING",
            "DISABLE_FEEDBACK_COMMAND",
            "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC",
            "DISABLE_AUTOUPDATER",
        )
    }
    with pytest.raises(ScheduleError, match="promised 1 records but produced 0"):
        run_schedule(
            plan,
            output_root=output,
            execute=True,
            only_envs={"windows_powershell"},
            only_configs={"CFG1"},
            only_tasks={"C01"},
            batch_size=1,
            inter_trial_delays={"claude_code": 0},
            executor=empty_executor,
            cwd=control,
            environment=env,
            host_platform="win32",
        )
    assert calls == 1


def test_dry_run_is_side_effect_free(tmp_path: Path):
    plan = build_plan("pilot")
    output = tmp_path / "does-not-exist"
    summary = run_schedule(plan, output_root=output)
    assert summary.selected_cells == 230
    assert summary.pending_cells == 230
    assert summary.existing_valid_trials == 0
    assert not output.exists()


def test_run_argv_preserves_space_model_and_capability_default(tmp_path: Path):
    plan = build_plan(
        "confirmatory",
        sizing_lock=_sizing_lock(6),
        sizing_anchor=_sizing_anchor(),
        agy_cli_version="1.0.16",
    )
    capability = next(
        cell for cell in plan.cells
        if cell.config_id == "CFG5" and cell.task_id == "C01"
    )
    argv = build_run_argv(
        capability,
        plan=plan,
        output_root=tmp_path,
        trials=2,
        trial_index_start=7,
        inter_trial_delay_seconds=1.5,
        max_budget_usd=None,
    )
    assert "Gemini 3.1 Pro (High)" in argv
    assert "--phrasing" not in argv
    assert argv[argv.index("--trial-index-start") + 1] == "7"
    assert argv[argv.index("--expect-cli-version") + 1] == "1.0.16"
    assert "--hide-outcomes" in argv
    identity = ScheduleIdentity.decode_token(
        argv[argv.index("--schedule-token") + 1]
    )
    assert identity == schedule_identity_for_cell(plan, capability)
    token = identity.encode_token()
    corrupted = token[:-1] + ("A" if token[-1] != "A" else "B")
    with pytest.raises(ValueError, match="schedule token|token digest"):
        ScheduleIdentity.decode_token(corrupted)

    seeded = next(
        cell for cell in plan.cells
        if cell.config_id == "CFG1" and cell.task_id == "T01"
        and cell.phrasing == "colloquial"
    )
    seeded_argv = build_run_argv(
        seeded,
        plan=plan,
        output_root=tmp_path,
        trials=1,
        trial_index_start=0,
        inter_trial_delay_seconds=0,
        max_budget_usd=1.25,
    )
    assert seeded_argv[seeded_argv.index("--phrasing") + 1] == "colloquial"
    assert seeded_argv[seeded_argv.index("--max-budget-usd") + 1] == "1.25"


def test_execution_refuses_repo_cwd_and_unsafe_output(tmp_path: Path):
    with pytest.raises(ScheduleError, match="methodology checkout"):
        validate_execution_paths(tmp_path / "output", cwd=_BENCH)
    with pytest.raises(ScheduleError, match="dedicated phase"):
        validate_execution_paths(_BENCH / "data", cwd=tmp_path)
    with pytest.raises(ScheduleError, match="pre-registration"):
        validate_execution_paths(
            _BENCH / "data" / "pre-registration" / "bad",
            cwd=tmp_path,
        )
    with pytest.raises(ScheduleError, match="only below data"):
        validate_execution_paths(_BENCH / "harness" / "bad", cwd=tmp_path)


def test_pilot_execution_requires_commitment_before_attempt_one(tmp_path: Path):
    plan = build_plan("pilot")
    output = tmp_path / "pilot-output"
    control = tmp_path / "control"
    control.mkdir()
    calls = 0

    def forbidden_executor(argv, *, cwd, env):
        nonlocal calls
        calls += 1
        return subprocess.CompletedProcess(list(argv), 0, stdout="", stderr="")

    env = {name: "1" for name in (
        "DISABLE_TELEMETRY",
        "DISABLE_ERROR_REPORTING",
        "DISABLE_FEEDBACK_COMMAND",
        "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC",
        "DISABLE_AUTOUPDATER",
    )}
    with pytest.raises(ScheduleError, match="pre-outcome blinding commitment"):
        run_schedule(
            plan,
            output_root=output,
            execute=True,
            only_envs={"windows_powershell"},
            only_configs={"CFG1"},
            only_tasks={"C01"},
            batch_size=1,
            inter_trial_delays={"claude_code": 0},
            executor=forbidden_executor,
            cwd=control,
            environment=env,
            host_platform="win32",
        )
    assert calls == 0
    assert (output / BOUND_PLAN_NAME).exists()
    assert not any(output.rglob("attempt_*.json"))
    assert not (output / LOCK_NAME).exists()


def test_scheduler_rejects_commitment_type_exporter_would_reject(tmp_path: Path):
    plan = build_plan("pilot", order_seed=1705)
    output = tmp_path / "pilot-output"
    _prepare_pilot_commitment(output, plan, tmp_path, "typed")
    path = output / ".blinding-commitment.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["mapping_digest"] = int("1" * 64)
    payload = {
        key: value for key, value in raw.items() if key != "commitment_digest"
    }
    raw["commitment_digest"] = hashlib.sha256(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
    ).hexdigest()
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ScheduleError, match="malformed or plan-mismatched"):
        validate_pilot_blinding_commitment(output, plan)


def test_execute_resumes_invalid_with_monotonic_index_and_hides_outcomes(
    tmp_path: Path, capsys
):
    plan = build_plan("pilot")
    cell = _single_pilot_cell(plan)
    output = tmp_path / "pilot-output"
    control = tmp_path / "control"
    control.mkdir()
    _prepare_pilot_commitment(output, plan, tmp_path, "resume")
    calls: list[list[str]] = []

    def fake_executor(argv, *, cwd, env):
        assert cwd == control.resolve()
        assert str(_BENCH) in env["PYTHONPATH"]
        assert (output / BOUND_PLAN_NAME).exists()
        assert (output / LOCK_NAME).exists()
        args = list(argv)
        calls.append(args)
        trials = int(args[args.index("--trials") + 1])
        start = int(args[args.index("--trial-index-start") + 1])
        for offset in range(trials):
            index = start + offset
            # First batch: one valid, one invalid. Replacement is valid.
            valid = not (len(calls) == 1 and offset == 1)
            _write_record(output, plan, cell, index, valid=valid)
        return subprocess.CompletedProcess(args, 0, stdout="PASS FAIL SECRET", stderr="")

    env = {
        "DISABLE_TELEMETRY": "1",
        "DISABLE_ERROR_REPORTING": "1",
        "DISABLE_FEEDBACK_COMMAND": "1",
        "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
        "DISABLE_AUTOUPDATER": "1",
    }
    summary = run_schedule(
        plan,
        output_root=output,
        execute=True,
        only_envs={"windows_powershell"},
        only_configs={"CFG1"},
        only_tasks={"C01"},
        batch_size=2,
        inter_trial_delays={"claude_code": 0},
        executor=fake_executor,
        cwd=control,
        environment=env,
        host_platform="win32",
    )
    assert len(calls) == 2
    assert calls[0][calls[0].index("--trial-index-start") + 1] == "0"
    assert calls[1][calls[1].index("--trial-index-start") + 1] == "2"
    assert summary.existing_valid_trials == 2
    assert summary.existing_invalid_trials == 1
    assert summary.executed_attempts == 3
    assert not (output / LOCK_NAME).exists()
    captured = capsys.readouterr()
    assert "PASS" not in captured.out
    assert "FAIL" not in captured.out
    assert "SECRET" not in captured.out


def test_execute_bounds_all_invalid_batches_and_remains_resumable(
    tmp_path: Path,
):
    plan = build_plan("pilot")
    cell = _single_pilot_cell(plan)
    output = tmp_path / "pilot-output"
    control = tmp_path / "control"
    control.mkdir()
    _prepare_pilot_commitment(output, plan, tmp_path, "invalid")
    calls = 0

    def invalid_executor(argv, *, cwd, env):
        nonlocal calls
        calls += 1
        args = list(argv)
        start = int(args[args.index("--trial-index-start") + 1])
        _write_record(output, plan, cell, start, valid=False)
        return subprocess.CompletedProcess(args, 0, stdout="FAIL", stderr="")

    env = {name: "1" for name in (
        "DISABLE_TELEMETRY",
        "DISABLE_ERROR_REPORTING",
        "DISABLE_FEEDBACK_COMMAND",
        "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC",
        "DISABLE_AUTOUPDATER",
    )}
    with pytest.raises(ScheduleError, match="no valid progress"):
        run_schedule(
            plan,
            output_root=output,
            execute=True,
            only_envs={"windows_powershell"},
            only_configs={"CFG1"},
            only_tasks={"C01"},
            batch_size=1,
            max_zero_progress_batches=2,
            inter_trial_delays={"claude_code": 0},
            executor=invalid_executor,
            cwd=control,
            environment=env,
            host_platform="win32",
        )
    assert calls == 2
    assert scan_cell_output(output, plan, cell).invalid == 2
    assert not (output / LOCK_NAME).exists()


def test_execute_requires_explicit_delay_and_claude_hygiene(tmp_path: Path):
    plan = build_plan("pilot")
    kwargs = dict(
        output_root=tmp_path / "output",
        execute=True,
        only_envs={"windows_powershell"},
        only_configs={"CFG1"},
        only_tasks={"C01"},
        cwd=tmp_path,
        environment={},
        host_platform="win32",
    )
    with pytest.raises(ScheduleError, match="explicit inter-trial delay"):
        run_schedule(plan, **kwargs)
    with pytest.raises(ScheduleError, match="hygiene is incomplete"):
        run_schedule(plan, inter_trial_delays={"claude_code": 0}, **kwargs)


def test_execute_rejects_incompatible_host_partition(tmp_path: Path):
    plan = build_plan("pilot")
    with pytest.raises(ScheduleError, match="Windows-local"):
        run_schedule(
            plan,
            output_root=tmp_path / "output",
            execute=True,
            only_envs={"windows_powershell"},
            only_configs={"CFG1"},
            only_tasks={"C01"},
            cwd=tmp_path,
            host_platform="linux",
        )
    with pytest.raises(ScheduleError, match="macos_actions"):
        run_schedule(
            plan,
            output_root=tmp_path / "output",
            execute=True,
            only_envs={"macos_actions"},
            only_configs={"CFG1"},
            only_tasks={"C01"},
            cwd=tmp_path,
            host_platform="win32",
        )


def test_run_cell_start_index_and_version_gate(tmp_path: Path, monkeypatch, capsys):
    import harness.runner as runner

    task_path = tmp_path / "X01_task.yaml"
    task_path.write_text(
        "id: X01\ncategory: capability\nprompt: do it\nsuccess_checks: []\n",
        encoding="utf-8",
    )
    sandbox_indices: list[int] = []
    record_indices: list[int] = []
    empty_snapshot = FilesystemSnapshot(files={})

    class FakeEnvironment:
        def probe(self):
            return {"env_id": "fake"}

        @contextmanager
        def trial_sandbox(self, task_id, trial_index, preconditions):
            sandbox_indices.append(trial_index)
            yield SandboxHandle(
                task_id=task_id,
                trial_index=trial_index,
                env_id="fake",
                root=str(tmp_path),
                host_root=tmp_path,
            )

        def snapshot(self, sandbox):
            return empty_snapshot

        def diff(self, before, after):
            return FilesystemDiff((), (), (), False)

    class FakeAgent:
        def cli_version(self, environment):
            return "fake-cli 1.2.3"

        def run(
            self,
            prompt,
            sandbox,
            environment,
            timeout,
            on_invoke=None,
            on_invocation_observed=None,
        ):
            if on_invoke is not None:
                on_invoke()
            if on_invocation_observed is not None:
                on_invocation_observed()
            return AgentRunResult(
                agent_id="fake_agent",
                model_id="fake_model",
                prompt=prompt,
                raw_transcript="",
                commands=[],
                process=ProcessResult(("fake",), 0, "", "", 0.01),
                wall_time_seconds=0.01,
                completed=True,
            )

    monkeypatch.setattr(runner, "make_environment", lambda env_id: FakeEnvironment())
    monkeypatch.setattr(
        runner,
        "make_agent",
        lambda agent_id, model_id, max_budget_usd=None: FakeAgent(),
    )
    monkeypatch.setattr(runner, "evaluate_checks", lambda *args, **kwargs: (True, []))

    def fake_write(record, data_root):
        index = record["trial"]["trial_index"]
        record_indices.append(index)
        path = tmp_path / f"trial_{index}.json"
        path.write_text(json.dumps(record), encoding="utf-8")
        return path

    monkeypatch.setattr(runner, "write_trial", fake_write)
    schedule_identity = ScheduleIdentity.create(
        phase="pilot",
        plan_digest="a" * 64,
        cell_id="b" * 16,
        config_id="CFGX",
        task_sha256=hashlib.sha256(task_path.read_bytes()).hexdigest(),
        trial_schema_version=TRIAL_SCHEMA_VERSION,
        target_valid_trials=2,
        task_id="X01",
        agent_id="fake_agent",
        model_id="fake_model",
        env_id="fake",
        phrasing="default",
        expected_cli_version="1.2.3",
    )
    paths = runner.run_cell(
        task_path=task_path,
        agent_id="fake_agent",
        model_id="fake_model",
        env_id="fake",
        phrasing="formal",
        trials=2,
        data_root=tmp_path,
        trial_index_start=7,
        expected_cli_version="1.2.3",
        show_outcomes=False,
        schedule_identity=schedule_identity,
    )
    assert sandbox_indices == [7, 8]
    assert record_indices == [7, 8]
    assert len(paths) == 2
    assert json.loads(paths[0].read_text(encoding="utf-8"))["schedule"] == (
        schedule_identity.as_dict()
    )
    output = capsys.readouterr().out
    assert "RECORDED" in output
    assert "PASS" not in output

    with pytest.raises(ValueError, match="version mismatch"):
        runner.run_cell(
            task_path=task_path,
            agent_id="fake_agent",
            model_id="fake_model",
            env_id="fake",
            phrasing="formal",
            trials=1,
            data_root=tmp_path,
            expected_cli_version="1.2.30",
        )


def test_run_cell_rejects_invalid_counts_before_adapter_creation(
    tmp_path: Path, monkeypatch
):
    import harness.runner as runner

    monkeypatch.setattr(
        runner,
        "make_environment",
        lambda env_id: pytest.fail("adapter should not be constructed"),
    )
    with pytest.raises(ValueError, match="trials must be"):
        runner.run_cell(
            task_path=tmp_path / "unused.yaml",
            agent_id="unused",
            model_id="unused",
            env_id="unused",
            phrasing="formal",
            trials=0,
            data_root=tmp_path,
        )
    with pytest.raises(ValueError, match="trial_index_start"):
        runner.run_cell(
            task_path=tmp_path / "unused.yaml",
            agent_id="unused",
            model_id="unused",
            env_id="unused",
            phrasing="formal",
            trials=1,
            data_root=tmp_path,
            trial_index_start=-1,
        )


def test_run_cell_refuses_missing_or_mismatched_schedule_before_adapter(
    tmp_path: Path, monkeypatch
):
    import harness.runner as runner

    task_path = tmp_path / "X01_task.yaml"
    task_path.write_text(
        "id: X01\ncategory: capability\nprompt: do it\nsuccess_checks: []\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        runner,
        "make_environment",
        lambda env_id: pytest.fail("adapter should not be constructed"),
    )
    kwargs = {
        "task_path": task_path,
        "agent_id": "fake_agent",
        "model_id": "fake_model",
        "env_id": "fake",
        "phrasing": "formal",
        "trials": 1,
        "data_root": tmp_path,
        "show_outcomes": False,
        "expected_cli_version": "1.2.3",
    }
    with pytest.raises(ValueError, match="requires a schedule token"):
        runner.run_cell(**kwargs)

    mismatched = ScheduleIdentity.create(
        phase="pilot",
        plan_digest="a" * 64,
        cell_id="b" * 16,
        config_id="CFGX",
        task_sha256=hashlib.sha256(task_path.read_bytes()).hexdigest(),
        trial_schema_version=TRIAL_SCHEMA_VERSION,
        target_valid_trials=1,
        task_id="X01",
        agent_id="fake_agent",
        model_id="fake_model",
        env_id="foreign",
        phrasing="default",
        expected_cli_version="1.2.3",
    )
    with pytest.raises(ValueError, match="schedule identity env_id"):
        runner.run_cell(**kwargs, schedule_identity=mismatched)

    wrong_task_hash = _replace_schedule_identity(
        mismatched,
        env_id="fake",
        task_sha256="0" * 64,
    )
    with pytest.raises(ValueError, match="schedule identity task_sha256"):
        runner.run_cell(**kwargs, schedule_identity=wrong_task_hash)


def test_schedule_cli_plan_and_status_are_non_executing(tmp_path: Path, capsys):
    from harness.__main__ import main

    manifest = tmp_path / "pilot-plan.json"
    output = tmp_path / "pilot-output"
    assert main([
        "schedule",
        "plan",
        "--phase",
        "pilot",
        "--manifest",
        str(manifest),
    ]) == 0
    assert manifest.exists()
    assert main([
        "schedule",
        "run",
        "--manifest",
        str(manifest),
        "--output",
        str(output),
    ]) == 0
    assert not output.exists()
    text = capsys.readouterr().out
    assert "planned pilot: 230 cells, 460 valid trials" in text
    assert "status (no execution)" in text


def test_schedule_cli_derives_confirmatory_n_from_sizing_lock(
    tmp_path: Path,
    capsys,
    monkeypatch: pytest.MonkeyPatch,
):
    from harness.__main__ import main

    lock_path = tmp_path / "sizing-lock.json"
    commitment_path = tmp_path / "commitment.json"
    manifest = tmp_path / "confirmatory-plan.json"
    lock = _sizing_lock(7)
    write_sizing_lock(lock, lock_path)
    commitment_path.write_text("anchored", encoding="utf-8")
    import harness.blinding as blinding
    monkeypatch.setattr(
        blinding,
        "load_commitment",
        lambda path: (
            type(
                "Commitment",
                (),
                {
                    "commitment_digest": lock.commitment_digest,
                    "public_key_b64": lock.commitment_public_key_b64,
                },
            )(),
            lock.commitment_artifact_sha256,
        ),
    )
    assert main([
        "schedule",
        "plan",
        "--phase",
        "confirmatory",
        "--sizing-lock",
        str(lock_path),
        "--blinding-commitment",
        str(commitment_path),
        "--agy-cli-version",
        "1.0.16",
        "--manifest",
        str(manifest),
    ]) == 0
    plan = load_plan(manifest)
    assert {
        cell.target_valid_trials
        for cell in plan.cells
        if cell.agent_id == "claude_code"
    } == {7}
    assert plan.sizing_lock is not None
    assert plan.sizing_lock.digest == _sizing_lock(7).digest
    assert "planned confirmatory" in capsys.readouterr().out


def test_schedule_cli_writes_accepted_v2_pilot_plan(tmp_path: Path, capsys):
    from harness.__main__ import main
    from scripts.configuration_matrix import load_matrix, write_matrix

    manifest = tmp_path / "v2-pilot-plan.json"
    candidate = load_matrix(
        _BENCH / "config" / "v2-runtime-matrix.candidate.json"
    )
    frozen = tmp_path / "v2-runtime-matrix.frozen.json"
    write_matrix(dataclasses.replace(candidate, status="frozen"), frozen)
    assert main([
        "schedule",
        "plan",
        "--phase",
        "v2-pilot",
        "--runtime-matrix",
        str(frozen),
        "--manifest",
        str(manifest),
    ]) == 0
    plan = load_plan(manifest)
    assert len(plan.cells) == 540
    assert sum(cell.target_valid_trials for cell in plan.cells) == 720
    assert plan.runtime_binding is not None
    assert plan.runtime_binding.matrix_digest == candidate.digest
    assert "planned v2-pilot: 540 cells, 720 valid trials" in capsys.readouterr().out


def test_one_cell_cli_forwards_scheduler_seams(tmp_path: Path, monkeypatch):
    import harness.__main__ as cli

    observed = {}

    def fake_run_cell(**kwargs):
        observed.update(kwargs)
        return []

    monkeypatch.setattr(cli, "run_cell", fake_run_cell)
    plan = build_plan("pilot")
    cell = _single_pilot_cell(plan)
    schedule_identity = schedule_identity_for_cell(plan, cell)
    assert cli.main([
        "run",
        "--task",
        "C01",
        "--agent",
        "claude_code",
        "--model",
        "claude-opus-4-8",
        "--env",
        "windows_powershell",
        "--trials",
        "2",
        "--output",
        str(tmp_path),
        "--trial-index-start",
        "7",
        "--expect-cli-version",
        "2.1.176",
        "--inter-trial-delay-seconds",
        "3.5",
        "--hide-outcomes",
        "--schedule-token",
        schedule_identity.encode_token(),
    ]) == 0
    assert observed["trial_index_start"] == 7
    assert observed["expected_cli_version"] == "2.1.176"
    assert observed["inter_trial_delay_seconds"] == 3.5
    assert observed["show_outcomes"] is False
    assert observed["schedule_identity"] == schedule_identity
