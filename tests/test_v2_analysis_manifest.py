from __future__ import annotations

import json
import hashlib
import subprocess
import sys
from pathlib import Path

import pytest

from analysis.v2_analysis_manifest import (
    AnalysisManifestError,
    analysis_manifest_from_dict,
    build_analysis_manifest,
    load_analysis_dataset,
    load_analysis_snapshot,
    write_analysis_manifest,
)
from harness.outcomes import construct_binary_outcome
from harness.scheduler import (
    V2_PILOT_PHASE,
    build_plan,
    schedule_identity_for_cell,
)


def _record(plan, cell, index: int) -> dict:
    outcome = construct_binary_outcome(
        checks_passed=True,
        completed=True,
        timed_out=False,
    )
    attempt_id = hashlib.sha256(
        f"{cell.cell_id}:{index}".encode("utf-8")
    ).hexdigest()[:32]
    return {
        "schema_version": plan.trial_schema_version,
        "trial": {
            "task_id": cell.task_id,
            "family_id": cell.family_id,
            "instance_id": cell.instance_id,
            "instance_sha256": cell.instance_sha256,
            "task_category": (
                "capability" if cell.task_id.startswith("C") else "seeded_error"
            ),
            "agent_id": cell.agent_id,
            "model_id": cell.model_id,
            "env_id": cell.env_id,
            "phrasing": cell.phrasing,
            "trial_index": index,
        },
        "attempt": {"attempt_id": attempt_id},
        "schedule": schedule_identity_for_cell(
            plan, cell, valid_slot_index=index
        ).as_dict(),
        "environment_probe": {"env_id": cell.env_id},
        "agent": {
            "completed": True,
            "process": {"timed_out": False, "returncode": 0},
        },
        "outcome": {
            "success": outcome.success,
            "checks_passed": outcome.checks_passed,
            "decision_reason": outcome.decision_reason,
            "checks": [{"passed": True}],
        },
        "validity": {"valid": True, "harness_error": None},
        "measurement": {"status": "complete"},
    }


@pytest.fixture(scope="module")
def frozen_sources(tmp_path_factory, frozen_runtime_binding):
    root = tmp_path_factory.mktemp("v2-analysis-sources")
    plan = build_plan(
        V2_PILOT_PHASE, runtime_binding=frozen_runtime_binding
    )
    for cell in plan.cells:
        directory = root / cell.env_id / cell.agent_id / cell.model_id / cell.task_id / cell.phrasing
        directory.mkdir(parents=True, exist_ok=True)
        for index in range(cell.target_valid_trials):
            path = directory / f"trial_{index}__2026-08-12T00-00-00Z.json"
            path.write_text(
                json.dumps(_record(plan, cell, index), indent=2),
                encoding="utf-8",
            )
    manifest = build_analysis_manifest(plan, root)
    manifest_path = root.parent / "v2-analysis-manifest.json"
    write_analysis_manifest(manifest, manifest_path, source_root=root)
    return plan, root, manifest, manifest_path


def test_manifest_roundtrip_reconstructs_exact_complete_dataset(frozen_sources) -> None:
    plan, root, manifest, manifest_path = frozen_sources
    rows = load_analysis_dataset(plan, root, manifest_path)
    loaded_manifest, snapshots = load_analysis_snapshot(plan, root, manifest_path)
    assert len(rows) == 720
    assert len(manifest.sources) == 720
    assert manifest.plan_digest == plan.digest
    assert analysis_manifest_from_dict(manifest.as_dict()) == manifest
    assert loaded_manifest == manifest
    assert len(snapshots) == 720
    assert tuple(snapshot.source for snapshot in snapshots) == manifest.sources
    assert all(
        hashlib.sha256(snapshot.raw_bytes).hexdigest() == snapshot.source.sha256
        for snapshot in snapshots
    )
    assert {
        snapshot.analysis_trial.identity
        for snapshot in snapshots
        if snapshot.source.valid_analysis_trial
    } == {row.identity for row in rows}


def test_manifest_refuses_source_root_mutation(frozen_sources) -> None:
    plan, root, _manifest, manifest_path = frozen_sources
    path = next(root.rglob("trial_*.json"))
    original = path.read_bytes()
    try:
        raw = json.loads(original)
        raw["outcome"]["success"] = not raw["outcome"]["success"]
        path.write_text(json.dumps(raw), encoding="utf-8")
        with pytest.raises(AnalysisManifestError, match="digest mismatch"):
            load_analysis_dataset(plan, root, manifest_path)
    finally:
        path.write_bytes(original)


def test_manifest_refuses_added_or_removed_trial_sources(frozen_sources) -> None:
    plan, root, _manifest, manifest_path = frozen_sources
    extra = root / "trial_unplanned.json"
    extra.write_text("{}", encoding="utf-8")
    try:
        with pytest.raises(AnalysisManifestError, match="roster changed"):
            load_analysis_dataset(plan, root, manifest_path)
    finally:
        extra.unlink()


def test_manifest_digest_rejects_redacted_entry_without_redigest(frozen_sources) -> None:
    _plan, root, manifest, _manifest_path = frozen_sources
    raw = manifest.as_dict()
    raw["sources"][0]["valid_analysis_trial"] = False
    with pytest.raises(AnalysisManifestError, match="digest mismatch"):
        analysis_manifest_from_dict(raw)

    with pytest.raises(AnalysisManifestError, match="outside the source root"):
        write_analysis_manifest(
            manifest,
            root / "forbidden.json",
            source_root=root,
        )


def test_manifest_parser_rejects_traversal_and_unsorted_sources(frozen_sources) -> None:
    _plan, _root, manifest, _manifest_path = frozen_sources
    traversal = manifest.as_dict()
    traversal["sources"][0]["relative_path"] = "../escape.json"
    with pytest.raises(AnalysisManifestError, match="entry is malformed"):
        analysis_manifest_from_dict(traversal)

    unsorted = manifest.as_dict()
    unsorted["sources"][0], unsorted["sources"][1] = (
        unsorted["sources"][1],
        unsorted["sources"][0],
    )
    with pytest.raises(AnalysisManifestError, match="unique and sorted"):
        analysis_manifest_from_dict(unsorted)


def test_manifest_cli_self_locates_from_external_cwd(tmp_path: Path) -> None:
    script = Path(__file__).resolve().parents[1] / "scripts" / "v2_analysis_manifest.py"
    completed = subprocess.run(
        [sys.executable, str(script), "--help"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    assert "Freeze or verify" in completed.stdout


def test_manifest_uses_shared_scheduler_lock(frozen_sources) -> None:
    plan, root, _manifest, manifest_path = frozen_sources
    lock = root / ".scheduler.lock"
    lock.write_text("active\n", encoding="utf-8")
    try:
        with pytest.raises(AnalysisManifestError, match="source root is locked"):
            build_analysis_manifest(plan, root)
        with pytest.raises(AnalysisManifestError, match="source root is locked"):
            load_analysis_dataset(plan, root, manifest_path)
        assert lock.read_text(encoding="utf-8") == "active\n"
    finally:
        lock.unlink()


def test_manifest_detects_mutation_between_snapshot_passes(
    frozen_sources, monkeypatch
) -> None:
    import analysis.v2_analysis_manifest as module

    plan, root, _manifest, _manifest_path = frozen_sources
    original_reader = module._read_record
    mutated = False
    mutated_path: Path | None = None
    original: bytes | None = None

    def mutate_after_read(path: Path):
        nonlocal mutated, mutated_path, original
        result = original_reader(path)
        if not mutated:
            mutated_path = path
            original = result[0]
            path.write_bytes(result[0] + b"\n")
            mutated = True
        return result

    monkeypatch.setattr(module, "_read_record", mutate_after_read)
    try:
        with pytest.raises(AnalysisManifestError, match="changed during freeze"):
            build_analysis_manifest(plan, root)
        assert not (root / ".scheduler.lock").exists()
    finally:
        if mutated_path is not None and original is not None:
            mutated_path.write_bytes(original)
