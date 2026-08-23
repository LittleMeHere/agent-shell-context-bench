"""R-006 sizing-lock and confirmatory-plan provenance tests.

No benchmark harness or model process is invoked.
"""

from __future__ import annotations

import json
import base64
import hashlib
from pathlib import Path
from types import SimpleNamespace

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from harness.sizing_lock import (
    SizingLockError,
    build_sizing_lock,
    digest_payload,
    load_sizing_lock,
    sizing_lock_from_dict,
    validate_commitment_anchor,
    write_sizing_lock,
)
from scripts import create_sizing_lock


_SIGNING_KEY = Ed25519PrivateKey.from_private_bytes(b"\x19" * 32)
_PUBLIC_KEY_B64 = base64.b64encode(
    _SIGNING_KEY.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )
).decode("ascii")


def _resign(raw: dict[str, object]) -> None:
    payload = {
        key: value
        for key, value in raw.items()
        if key not in {"digest", "signature_b64"}
    }
    raw["digest"] = digest_payload(payload)
    signed = json.dumps(
        {**payload, "digest": raw["digest"]},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    raw["signature_b64"] = base64.b64encode(_SIGNING_KEY.sign(signed)).decode(
        "ascii"
    )


def _lock(*, n_per_cell: int = 6, n_cells: int = 805):
    return build_sizing_lock(
        source_plan_digest="a" * 64,
        source_plan_schema_version="1.1.0",
        source_trial_schema_version="1.5.0",
        blinded_input_sha256="b" * 64,
        blinded_export_digest="c" * 64,
        source_manifest_digest="d" * 64,
        commitment_digest="e" * 64,
        commitment_artifact_sha256="f" * 64,
        commitment_public_key_b64=_PUBLIC_KEY_B64,
        signing_key=_SIGNING_KEY,
        code_version="pre-data-v2-test",
        code_artifacts={
            "scripts/create_sizing_lock.py": "0" * 64,
            "scripts/size_from_pilot.py": "1" * 64,
            "harness/blinding.py": "2" * 64,
            "harness/sizing_lock.py": "3" * 64,
        },
        analysis_version="analysis-test-v1",
        analysis_artifact_sha256="2" * 64,
        simulation_config_version="simulation-test-v1",
        simulation_config_sha256="3" * 64,
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
            "constants": {"alpha": 0.05},
        },
        created_at="2026-08-09T00-00-00Z",
    )


def test_sizing_lock_round_trip_and_refuses_overwrite(tmp_path: Path):
    lock = _lock()
    path = tmp_path / "sizing-lock.json"
    write_sizing_lock(lock, path)
    assert load_sizing_lock(path) == lock
    with pytest.raises(SizingLockError, match="refusing to overwrite"):
        write_sizing_lock(lock, path)


def test_sizing_lock_rejects_result_and_phase_tampering():
    raw = _lock().as_dict()
    raw["result"]["n_per_cell"] = 5
    _resign(raw)
    with pytest.raises(SizingLockError, match="result digest mismatch"):
        sizing_lock_from_dict(raw)

    raw = _lock().as_dict()
    raw["source_phase"] = "confirmatory"
    _resign(raw)
    with pytest.raises(SizingLockError, match="wrong source or target phase"):
        sizing_lock_from_dict(raw)


def test_sizing_lock_rejects_recomputed_budget_inconsistency():
    raw = _lock().as_dict()
    raw["compute_budget"] = 9999.0
    _resign(raw)
    with pytest.raises(SizingLockError, match="authoritative budget inputs"):
        sizing_lock_from_dict(raw)


def test_signed_lock_rejects_n_above_cap_even_after_full_redigest():
    raw = _lock().as_dict()
    raw["result"]["n_per_cell"] = 999
    raw["result_digest"] = digest_payload(raw["result"])
    _resign(raw)
    with pytest.raises(SizingLockError, match="exceeds the authoritative cap"):
        sizing_lock_from_dict(raw)


def test_external_anchor_rejects_resigned_commitment_substitution():
    original = _lock()
    raw = original.as_dict()
    raw["commitment_digest"] = "9" * 64
    _resign(raw)
    substituted = sizing_lock_from_dict(raw)
    with pytest.raises(SizingLockError, match="independently anchored"):
        validate_commitment_anchor(
            substituted,
            commitment_digest=original.commitment_digest,
            commitment_artifact_sha256=original.commitment_artifact_sha256,
            commitment_public_key_b64=original.commitment_public_key_b64,
        )


def test_actual_sizing_source_snapshot_executes_and_is_hash_bound():
    source = create_sizing_lock._CODE_SOURCE_BYTES[
        "scripts/size_from_pilot.py"
    ]
    trials = [
        {
            "blinded_group": f"E{1 + (index % 2):02d}",
            "task_id": f"C{1 + (index % 2):02d}",
            "config_id": f"CFG{1 + (index % 2)}",
            "phrasing": "default",
            "valid": True,
            "failed": index in {0, 3},
        }
        for index in range(8)
    ]
    result = create_sizing_lock._size_from_snapshot(
        source,
        trials,
        cap_per_cell=6,
        task_class="capability",
    )
    assert result["mode"] == "pilot"
    assert result["cap_per_cell"] == 6
    assert result["n_per_cell"] <= 6


def test_lock_creation_refuses_persistent_sizing_path_change(monkeypatch):
    changed = dict(create_sizing_lock._CODE_SOURCE_HASHES)
    changed["harness/blinding.py"] = "0" * 64
    monkeypatch.setattr(create_sizing_lock, "_CODE_SOURCE_HASHES", changed)
    with pytest.raises(SizingLockError, match="source changed"):
        create_sizing_lock._verify_code_sources_unchanged()


@pytest.mark.parametrize(
    "missing",
    [
        "--pilot-json",
        "--blinding-commitment",
        "--custody",
        "--compute-budget",
        "--per-trial-cost",
        "--n-cells",
        "--code-version",
        "--analysis-version",
        "--analysis-artifact",
        "--simulation-version",
        "--simulation-config",
        "--output",
    ],
)
def test_lock_cli_requires_every_authoritative_input(missing: str):
    argv = [
        "--pilot-json", "pilot.json",
        "--blinding-commitment", "commitment.json",
        "--custody", "custody.json",
        "--passphrase-file", "passphrase.txt",
        "--compute-budget", "4830",
        "--per-trial-cost", "1",
        "--n-cells", "805",
        "--code-version", "v2-test",
        "--analysis-version", "analysis-v1",
        "--analysis-artifact", "analysis.json",
        "--simulation-version", "simulation-v1",
        "--simulation-config", "simulation.json",
        "--output", "lock.json",
    ]
    index = argv.index(missing)
    del argv[index:index + 2]
    with pytest.raises(SystemExit) as exc_info:
        create_sizing_lock.main(argv)
    assert exc_info.value.code == 2


def test_lock_cli_binds_verified_inputs_and_result(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    pilot = tmp_path / "pilot.json"
    commitment = tmp_path / "commitment.json"
    custody = tmp_path / "custody.json"
    passphrase = tmp_path / "passphrase.txt"
    analysis = tmp_path / "analysis.json"
    simulation = tmp_path / "simulation.json"
    output = tmp_path / "sizing-lock.json"
    pilot.write_text(
        json.dumps(
            {
                "source_plan_digest": "a" * 64,
                "source_plan_schema_version": "1.1.0",
                "source_trial_schema_version": "1.5.0",
                "export_digest": "b" * 64,
                "source_manifest_digest": "c" * 64,
                "commitment_digest": "d" * 64,
                "commitment_artifact_sha256": "e" * 64,
            }
        ),
        encoding="utf-8",
    )
    commitment.write_text("commitment", encoding="utf-8")
    custody.write_text("custody", encoding="utf-8")
    passphrase.write_text("this-is-a-test-passphrase", encoding="utf-8")
    analysis.write_text('{"analysis":"candidate"}', encoding="utf-8")
    simulation.write_text('{"simulation":"candidate"}', encoding="utf-8")
    trials = [
        {
            "task_id": f"C{1 + (index % 2):02d}",
            "config_id": f"CFG{1 + (index % 2)}",
            "failed": index in {0, 3},
            "valid": True,
        }
        for index in range(8)
    ]
    monkeypatch.setattr(
        create_sizing_lock,
        "load_blinded_export_bytes",
        lambda pilot_bytes, commitment_bytes: (
            trials,
            {
                "source_plan_digest": "a" * 64,
                "source_plan_schema_version": "1.1.0",
                "source_trial_schema_version": "1.5.0",
                "export_digest": "b" * 64,
                "source_manifest_digest": "c" * 64,
                "commitment_digest": "d" * 64,
                "commitment_artifact_sha256": "e" * 64,
                "commitment_public_key_b64": _PUBLIC_KEY_B64,
            },
            hashlib.sha256(pilot_bytes).hexdigest(),
        ),
    )
    fake_commitment = SimpleNamespace(
        commitment_digest="d" * 64,
        public_key_b64=_PUBLIC_KEY_B64,
    )
    monkeypatch.setattr(
        create_sizing_lock,
        "load_commitment_bytes",
        lambda value: (fake_commitment, "e" * 64),
    )
    monkeypatch.setattr(
        create_sizing_lock,
        "load_custody",
        lambda path, commitment_value, passphrase_value: (
            None,
            _SIGNING_KEY,
            "f" * 64,
        ),
    )
    monkeypatch.setattr(
        create_sizing_lock,
        "_size_from_snapshot",
        lambda source_bytes, trial_rows, *, cap_per_cell, task_class: {
            "n_per_cell": 6,
            "task_class": task_class,
            "mode": "pilot",
            "cap_per_cell": cap_per_cell,
            "n_trials_after_filter": len(trial_rows),
            "constants": {"alpha": 0.05},
        },
    )
    read_counts: dict[Path, int] = {}
    original_read_once = create_sizing_lock._read_once

    def counted_read_once(path: Path, *, label: str) -> bytes:
        resolved = path.resolve()
        read_counts[resolved] = read_counts.get(resolved, 0) + 1
        return original_read_once(path, label=label)

    monkeypatch.setattr(create_sizing_lock, "_read_once", counted_read_once)

    assert create_sizing_lock.main([
        "--pilot-json", str(pilot),
        "--blinding-commitment", str(commitment),
        "--custody", str(custody),
        "--passphrase-file", str(passphrase),
        "--compute-budget", "4830",
        "--per-trial-cost", "1",
        "--n-cells", "805",
        "--code-version", "v2-test",
        "--analysis-version", "analysis-v1",
        "--analysis-artifact", str(analysis),
        "--simulation-version", "simulation-v1",
        "--simulation-config", str(simulation),
        "--output", str(output),
    ]) == 0
    lock = load_sizing_lock(output)
    assert lock.n_per_cell == 6
    assert lock.source_plan_digest == "a" * 64
    assert lock.blinded_export_digest == "b" * 64
    assert lock.analysis_version == "analysis-v1"
    assert lock.simulation_config_version == "simulation-v1"
    assert lock.result["mode"] == "pilot"
    assert read_counts[pilot.resolve()] == 1
    assert read_counts[commitment.resolve()] == 1
