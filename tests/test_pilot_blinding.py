"""Acceptance tests for the R-005 plan-bound blinded pilot exporter.

No agent CLI or benchmark task is executed.  The integration fixture writes
synthetic immutable records and append-only journal events only.
"""

from __future__ import annotations

import dataclasses
import base64
import hashlib
import json
import random
import os
import subprocess
import sys
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

_BENCH = Path(__file__).resolve().parents[1]
if str(_BENCH) not in sys.path:
    sys.path.insert(0, str(_BENCH))

from harness.attempts import AttemptJournal, COMPLETE
import harness.blinding as blinding_module
from harness.blinding import (
    BLINDED_EXPORT_SCHEMA_VERSION,
    BlindingError,
    SourceTrial,
    build_blinded_export,
    create_mapping,
    create_custody_artifacts,
    export_blinded_pilot,
    load_blinded_export,
    load_custody,
    prepare_blinding_custody,
    sign_blinded_export,
    stable_source_snapshot,
    write_custody_artifacts,
)
from harness.scheduler import (
    BOUND_PLAN_NAME,
    ENVIRONMENTS,
    build_plan,
    schedule_identity_for_cell,
    write_plan,
)
from harness.sizing_lock import build_sizing_lock


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


_SIZING_KEY = Ed25519PrivateKey.from_private_bytes(b"\x31" * 32)
_SIZING_PUBLIC_KEY_B64 = base64.b64encode(
    _SIZING_KEY.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )
).decode("ascii")


def _confirmatory_sizing_lock():
    return build_sizing_lock(
        source_plan_digest="b" * 64,
        source_plan_schema_version="1.1.0",
        source_trial_schema_version="1.5.0",
        blinded_input_sha256="c" * 64,
        blinded_export_digest="d" * 64,
        source_manifest_digest="e" * 64,
        commitment_digest="f" * 64,
        commitment_artifact_sha256="0" * 64,
        commitment_public_key_b64=_SIZING_PUBLIC_KEY_B64,
        signing_key=_SIZING_KEY,
        code_version="pre-data-v2-test",
        code_artifacts={
            "scripts/create_sizing_lock.py": "a" * 64,
            "scripts/size_from_pilot.py": "a" * 64,
            "harness/blinding.py": "a" * 64,
            "harness/sizing_lock.py": "a" * 64,
        },
        analysis_version="analysis-test-v1",
        analysis_artifact_sha256="1" * 64,
        simulation_config_version="simulation-test-v1",
        simulation_config_sha256="2" * 64,
        task_class="capability",
        compute_budget=4830.0,
        per_trial_cost=1.0,
        n_cells=805,
        cap_per_cell=6,
        result={
            "n_per_cell": 6,
            "task_class": "capability",
            "mode": "pilot",
            "cap_per_cell": 6,
            "n_trials_after_filter": 100,
            "constants": {"test": True},
        },
        created_at="2026-08-09T00-00-00Z",
    )


def _source_records(plan) -> list[SourceTrial]:
    records: list[SourceTrial] = []
    for cell in plan.cells:
        for index in range(cell.target_valid_trials):
            digest = _digest(f"{cell.cell_id}:{index}")
            records.append(
                SourceTrial(
                    source_relpath=(
                        f"{cell.env_id}/{cell.agent_id}/{cell.model_id}/"
                        f"{cell.task_id}/{cell.phrasing}/trial_{index}.json"
                    ),
                    source_sha256=digest,
                    terminal_trial_sha256=digest,
                    phase=plan.phase,
                    plan_digest=plan.digest,
                    cell_id=cell.cell_id,
                    config_id=cell.config_id,
                    env_id=cell.env_id,
                    task_id=cell.task_id,
                    family_id=cell.family_id,
                    instance_id=cell.instance_id,
                    instance_sha256=cell.instance_sha256,
                    phrasing=cell.phrasing,
                    trial_index=index,
                    attempt_id=_digest(f"attempt:{cell.cell_id}:{index}")[:32],
                    valid=True,
                    failed=(index == 0),
                )
            )
    return records


@pytest.fixture
def core_inputs():
    plan = build_plan("pilot", order_seed=1701)
    mapping = create_mapping(plan, rng=random.Random(42))
    commitment, _ = create_custody_artifacts(
        plan,
        "correct horse battery staple",
        rng=random.Random(42),
    )
    records = _source_records(plan)
    kwargs = {
        "commitment_artifact_sha256": "a" * 64,
        "custody_artifact_sha256": "f" * 64,
        "source_manifest_digest": "b" * 64,
        "source_artifact_count": 2301,
        "invalid_attempt_count": 7,
    }
    return plan, mapping, commitment, records, kwargs


def test_core_export_is_exact_and_contains_no_environment_names(core_inputs):
    plan, mapping, commitment, records, kwargs = core_inputs
    export = build_blinded_export(plan, records, mapping, commitment, **kwargs)
    assert export["schema_version"] == BLINDED_EXPORT_SCHEMA_VERSION
    assert export["valid_trial_count"] == 460
    assert export["invalid_attempt_count"] == 7
    assert len(export["trials"]) == 460
    encoded = json.dumps(export)
    assert not any(env_id in encoded for env_id in ENVIRONMENTS)
    assert {row["blinded_group"] for row in export["trials"]} == {
        "E01",
        "E02",
        "E03",
        "E04",
        "E05",
    }


def test_v2_export_and_loader_enforce_exact_720_trial_instance_roster(
    tmp_path: Path, frozen_runtime_binding
):
    plan = build_plan(
        "v2-pilot",
        order_seed=1710,
        runtime_binding=frozen_runtime_binding,
    )
    records = _source_records(plan)
    commitment_path = tmp_path / "commitment.json"
    custody_path = tmp_path / "custody.json"
    commitment, custody = create_custody_artifacts(
        plan,
        "correct horse battery staple",
        rng=random.Random(77),
    )
    write_custody_artifacts(
        commitment,
        custody,
        commitment_path=commitment_path,
        custody_path=custody_path,
    )
    mapping, private_key, custody_sha256 = load_custody(
        custody_path,
        commitment,
        "correct horse battery staple",
    )
    payload = build_blinded_export(
        plan,
        records,
        mapping,
        commitment,
        commitment_artifact_sha256=hashlib.sha256(
            commitment_path.read_bytes()
        ).hexdigest(),
        custody_artifact_sha256=custody_sha256,
        source_manifest_digest="b" * 64,
        source_artifact_count=3601,
        invalid_attempt_count=0,
    )
    assert payload["cell_count"] == 540
    assert payload["valid_trial_count"] == 720
    assert payload["valid_trial_policy"] == "v2_capability_one_seeded_two"
    assert {
        (row["family_id"], row["instance_id"])
        for row in payload["trials"]
        if row["task_id"].startswith("C")
    } == {
        (f"C{family:02d}", f"I{instance:02d}")
        for family in range(1, 13)
        for instance in range(1, 4)
    }

    export_path = tmp_path / "v2-blinded.json"
    export_path.write_text(
        json.dumps(sign_blinded_export(payload, private_key)),
        encoding="utf-8",
    )
    rows = load_blinded_export(export_path, commitment_path)
    assert len(rows) == 720


def test_core_rejects_missing_record(core_inputs):
    plan, mapping, commitment, records, kwargs = core_inputs
    with pytest.raises(BlindingError, match="missing, duplicated, or unbalanced"):
        build_blinded_export(plan, records[:-1], mapping, commitment, **kwargs)


def test_core_rejects_duplicate_record(core_inputs):
    plan, mapping, commitment, records, kwargs = core_inputs
    with pytest.raises(BlindingError, match="duplicate source record"):
        build_blinded_export(
            plan, [*records, records[0]], mapping, commitment, **kwargs
        )


def test_core_rejects_foreign_record(core_inputs):
    plan, mapping, commitment, records, kwargs = core_inputs
    records[0] = dataclasses.replace(records[0], cell_id="0" * 16)
    with pytest.raises(BlindingError, match="foreign source cell"):
        build_blinded_export(plan, records, mapping, commitment, **kwargs)


def test_core_rejects_non_boolean_validity(core_inputs):
    plan, mapping, commitment, records, kwargs = core_inputs
    records[0] = dataclasses.replace(records[0], valid=1)
    with pytest.raises(BlindingError, match="must be JSON booleans"):
        build_blinded_export(plan, records, mapping, commitment, **kwargs)


def test_core_rejects_unbalanced_roster(core_inputs):
    plan, mapping, commitment, records, kwargs = core_inputs
    first = plan.cells[0]
    second = plan.cells[1]
    source = next(row for row in records if row.cell_id == first.cell_id)
    target_index = next(i for i, row in enumerate(records) if row.cell_id == second.cell_id)
    records[target_index] = dataclasses.replace(
        source,
        source_relpath="opaque/reassigned.json",
        source_sha256="c" * 64,
        terminal_trial_sha256="c" * 64,
        attempt_id="d" * 32,
    )
    with pytest.raises(BlindingError, match="missing, duplicated, or unbalanced"):
        build_blinded_export(plan, records, mapping, commitment, **kwargs)


def test_core_rejects_wrong_phase(core_inputs):
    plan, mapping, commitment, records, kwargs = core_inputs
    records[0] = dataclasses.replace(records[0], phase="confirmatory")
    with pytest.raises(BlindingError, match="wrong phase or plan digest"):
        build_blinded_export(plan, records, mapping, commitment, **kwargs)


def test_core_rejects_outcome_tampering(core_inputs):
    plan, mapping, commitment, records, kwargs = core_inputs
    records[0] = dataclasses.replace(records[0], source_sha256="e" * 64)
    with pytest.raises(BlindingError, match="outcome-tampered"):
        build_blinded_export(plan, records, mapping, commitment, **kwargs)


def test_loader_rejects_adhoc_list_and_export_tampering(tmp_path: Path, core_inputs):
    plan, mapping, commitment, records, kwargs = core_inputs
    commitment_path = tmp_path / "commitment.json"
    custody_path = tmp_path / "custody.json"
    generated_commitment, custody = create_custody_artifacts(
        plan,
        "correct horse battery staple",
        rng=random.Random(42),
    )
    # Use the generated commitment/mapping pair for a real signature.
    write_custody_artifacts(
        generated_commitment,
        custody,
        commitment_path=commitment_path,
        custody_path=custody_path,
    )
    mapping, private_key, custody_sha256 = load_custody(
        custody_path,
        generated_commitment,
        "correct horse battery staple",
    )
    path = tmp_path / "blinded.json"
    path.write_text("[]", encoding="utf-8")
    with pytest.raises(BlindingError, match="blinded-export object"):
        load_blinded_export(path, commitment_path)

    signed_kwargs = {
        **kwargs,
        "commitment_artifact_sha256": hashlib.sha256(
            commitment_path.read_bytes()
        ).hexdigest(),
        "custody_artifact_sha256": custody_sha256,
    }
    payload = build_blinded_export(
        plan,
        records,
        mapping,
        generated_commitment,
        **signed_kwargs,
    )
    export = sign_blinded_export(payload, private_key)
    export["trials"][0]["failed"] = not export["trials"][0]["failed"]
    unsigned = {
        key: value
        for key, value in export.items()
        if key not in {"export_digest", "export_signature_b64"}
    }
    export["export_digest"] = hashlib.sha256(
        json.dumps(
            unsigned,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
    ).hexdigest()
    path.write_text(json.dumps(export), encoding="utf-8")
    with pytest.raises(BlindingError, match="signature verification failed"):
        load_blinded_export(path, commitment_path)


def test_snapshot_bytes_are_stable_if_source_changes(tmp_path: Path):
    root = tmp_path / "pilot"
    root.mkdir()
    (root / ".scheduler-plan.json").write_text("plan-a", encoding="utf-8")
    (root / ".blinding-commitment.json").write_text(
        "commitment-a", encoding="utf-8"
    )
    trial = root / "trial_0.json"
    trial.write_text("outcome-a", encoding="utf-8")
    with stable_source_snapshot(root) as snapshot:
        trial.write_text("outcome-b", encoding="utf-8")
        assert (snapshot / "trial_0.json").read_text(encoding="utf-8") == "outcome-a"


def test_prepare_write_failure_leaves_no_scheduler_readiness_marker(
    tmp_path: Path,
    monkeypatch,
):
    plan = build_plan("pilot", order_seed=1704)
    plan_path = tmp_path / "pilot-plan.json"
    write_plan(plan, plan_path)
    root = tmp_path / "pilot"
    commitment_path = tmp_path / "public-commitment.json"
    custody_path = tmp_path / "encrypted-custody.json"
    original = blinding_module._write_json_exclusive

    def injected_failure(path, payload):
        if Path(path).resolve() == commitment_path.resolve():
            raise OSError("injected external commitment write failure")
        return original(path, payload)

    monkeypatch.setattr(
        blinding_module,
        "_write_json_exclusive",
        injected_failure,
    )
    with pytest.raises(OSError, match="injected external"):
        prepare_blinding_custody(
            root,
            "correct horse battery staple",
            plan_path=plan_path,
            commitment_path=commitment_path,
            custody_path=custody_path,
            rng=random.Random(9),
        )
    assert custody_path.exists()
    assert not commitment_path.exists()
    assert not (root / ".blinding-commitment.json").exists()


def test_confirmatory_plan_does_not_bind_or_poison_pilot_root(tmp_path: Path):
    sizing_lock = _confirmatory_sizing_lock()
    plan = build_plan(
        "confirmatory",
        sizing_lock=sizing_lock,
        sizing_anchor={
            "commitment_digest": sizing_lock.commitment_digest,
            "commitment_artifact_sha256": sizing_lock.commitment_artifact_sha256,
            "commitment_public_key_b64": sizing_lock.commitment_public_key_b64,
        },
        agy_cli_version="1.1.10",
    )
    plan_path = tmp_path / "confirmatory-plan.json"
    write_plan(plan, plan_path)
    root = tmp_path / "intended-pilot"
    with pytest.raises(BlindingError, match="only for pilot phase"):
        prepare_blinding_custody(
            root,
            "correct horse battery staple",
            plan_path=plan_path,
            commitment_path=tmp_path / "never-commitment.json",
            custody_path=tmp_path / "never-custody.json",
        )
    assert not root.exists()


def test_cli_help_works_from_external_cwd_without_pythonpath(tmp_path: Path):
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    outputs = {}
    for name in (
        "pilot_blinding.py",
        "size_from_pilot.py",
        "create_sizing_lock.py",
    ):
        result = subprocess.run(
            [sys.executable, str(_BENCH / "scripts" / name), "--help"],
            cwd=tmp_path,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, result.stderr
        outputs[name] = result.stdout
    assert "prepare" in outputs["pilot_blinding.py"]
    assert "export" in outputs["pilot_blinding.py"]
    assert "--blinding-commitment" in outputs["size_from_pilot.py"]
    assert "--analysis-artifact" in outputs["create_sizing_lock.py"]


def _write_synthetic_trial(root: Path, plan, cell, index: int) -> Path:
    journal = AttemptJournal.allocate(
        data_root=root,
        task_id=cell.task_id,
        agent_id=cell.agent_id,
        model_id=cell.model_id,
        env_id=cell.env_id,
        phrasing=cell.phrasing,
        trial_index=index,
        schedule_identity=schedule_identity_for_cell(plan, cell),
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
    path = directory / f"trial_{index}__2026-08-09T00-00-{index:02d}Z.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": plan.trial_schema_version,
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
                "agent_cli_version": f"synthetic {cell.expected_cli_version}",
                "validity": {"valid": True, "harness_error": None},
                "measurement": {"status": "complete"},
                "schedule": schedule_identity_for_cell(plan, cell).as_dict(),
                "outcome": {"success": index == 1},
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    journal.finalize_trial(path, valid=True, attribution=COMPLETE)
    return path


def test_filesystem_export_validates_complete_bound_root(tmp_path: Path):
    plan = build_plan("pilot", order_seed=1702)
    root = tmp_path / "pilot"
    plan_path = tmp_path / "pilot-plan.json"
    write_plan(plan, plan_path)
    commitment_path = tmp_path / "public-commitment.json"
    custody_path = tmp_path / "encrypted-custody.json"
    passphrase = "correct horse battery staple"
    prepare_blinding_custody(
        root,
        passphrase,
        plan_path=plan_path,
        commitment_path=commitment_path,
        custody_path=custody_path,
        rng=random.Random(7),
    )
    assert (root / BOUND_PLAN_NAME).exists()
    for cell in plan.cells:
        _write_synthetic_trial(root, plan, cell, 0)
        _write_synthetic_trial(root, plan, cell, 1)

    output_path = tmp_path / "pilot-blinded.json"
    with pytest.raises(BlindingError, match="output path must be outside"):
        export_blinded_pilot(
            root,
            custody_path,
            commitment_path,
            passphrase,
            root / "bad-output.json",
        )
    export = export_blinded_pilot(
        root,
        custody_path,
        commitment_path,
        passphrase,
        output_path,
    )

    assert export["valid_trial_count"] == 460
    assert export["invalid_attempt_count"] == 0
    assert export["source_artifact_count"] == 2302
    assert len(load_blinded_export(output_path, commitment_path)) == 460
    custody_text = custody_path.read_text(encoding="utf-8")
    assert not any(env_id in custody_text for env_id in ENVIRONMENTS)


def test_filesystem_export_detects_post_terminal_outcome_tamper(tmp_path: Path):
    plan = build_plan("pilot", order_seed=1703)
    root = tmp_path / "pilot"
    plan_path = tmp_path / "pilot-plan.json"
    write_plan(plan, plan_path)
    commitment_path = tmp_path / "public-commitment.json"
    custody_path = tmp_path / "encrypted-custody.json"
    passphrase = "correct horse battery staple"
    prepare_blinding_custody(
        root,
        passphrase,
        plan_path=plan_path,
        commitment_path=commitment_path,
        custody_path=custody_path,
        rng=random.Random(8),
    )
    for cell in plan.cells:
        _write_synthetic_trial(root, plan, cell, 0)
        _write_synthetic_trial(root, plan, cell, 1)
    first_trial = next(root.rglob("trial_*.json"))
    raw = json.loads(first_trial.read_text(encoding="utf-8"))
    raw["outcome"]["success"] = not raw["outcome"]["success"]
    first_trial.write_text(json.dumps(raw), encoding="utf-8")

    with pytest.raises(BlindingError, match="terminal trial digest mismatch"):
        export_blinded_pilot(
            root,
            custody_path,
            commitment_path,
            passphrase,
            tmp_path / "never.json",
        )
