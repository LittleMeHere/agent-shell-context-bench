"""Adversarial tests for the operational V2 lock/release CLI."""

from __future__ import annotations

import json
import hashlib
from pathlib import Path

from harness.blinding import create_custody_artifacts, write_custody_artifacts
from harness.scheduler import V2_PILOT_PHASE, build_plan, write_plan
from harness.v2_design_lock import (
    build_provider_cap_authorization,
    load_v2_design_lock,
    load_v2_pilot_release,
    write_provider_cap_authorization,
)
from scripts.v2_design_lock import main


def _digest(value: object) -> str:
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _prepare_inputs(tmp_path: Path, frozen_runtime_binding):
    plan = build_plan(V2_PILOT_PHASE, runtime_binding=frozen_runtime_binding)
    plan_path = tmp_path / "pilot-plan.json"
    write_plan(plan, plan_path)

    matrix_raw = json.loads(
        (
            Path(__file__).resolve().parents[1]
            / "config"
            / "v2-runtime-matrix.candidate.json"
        ).read_text(encoding="utf-8")
    )
    matrix_raw["status"] = "frozen"
    matrix_path = tmp_path / "runtime-matrix.json"
    matrix_path.write_text(json.dumps(matrix_raw), encoding="utf-8")

    passphrase = "correct horse battery staple"
    passphrase_path = tmp_path / "passphrase.txt"
    passphrase_path.write_text(passphrase, encoding="utf-8")
    commitment, custody = create_custody_artifacts(plan, passphrase)
    commitment_path = tmp_path / "commitment.json"
    custody_path = tmp_path / "custody.json"
    write_custody_artifacts(
        commitment,
        custody,
        commitment_path=commitment_path,
        custody_path=custody_path,
    )

    provider_cap = build_provider_cap_authorization(
        as_of_date="2026-08-22",
        calendar_days_cap=30,
        human_audit_hours_cap=24,
        providers={
            provider: {
                "window_unit": "measured-subscription-unit",
                "total_window_units": 100,
                "n36_required_units": 50,
            }
            for provider in (
                "anthropic_subscription",
                "openai_subscription",
                "antigravity_subscription",
            )
        },
        inter_trial_delay_seconds={"claude_code": 1, "codex": 1, "agy": 1},
    )
    provider_path = tmp_path / "provider-cap.json"
    write_provider_cap_authorization(provider_cap, provider_path)

    analysis_path = tmp_path / "analysis.py"
    simulation_path = tmp_path / "simulation.json"
    analysis_path.write_text("# frozen analysis\n", encoding="utf-8")
    simulation_path.write_text('{"fixed_n":36}\n', encoding="utf-8")
    return {
        "plan": plan,
        "plan_path": plan_path,
        "matrix_path": matrix_path,
        "passphrase_path": passphrase_path,
        "commitment_path": commitment_path,
        "custody_path": custody_path,
        "provider_path": provider_path,
        "analysis_path": analysis_path,
        "simulation_path": simulation_path,
    }


def _design_args(inputs, output: Path) -> list[str]:
    return [
        "create-design-lock",
        "--pilot-plan",
        str(inputs["plan_path"]),
        "--runtime-matrix",
        str(inputs["matrix_path"]),
        "--analysis-artifact",
        str(inputs["analysis_path"]),
        "--simulation-artifact",
        str(inputs["simulation_path"]),
        "--provider-cap",
        str(inputs["provider_path"]),
        "--commitment",
        str(inputs["commitment_path"]),
        "--custody",
        str(inputs["custody_path"]),
        "--passphrase-file",
        str(inputs["passphrase_path"]),
        "--order-seed",
        "20260525",
        "--created-at",
        "2026-08-22T00-00-00Z",
        "--output",
        str(output),
    ]


def _release_inputs(tmp_path: Path, inputs, lock):
    manifest_payload = {
        "schema_version": "1.0.0",
        "purpose": "v2_frozen_analysis_trial_sources",
        "plan_digest": inputs["plan"].digest,
        "trial_schema_version": inputs["plan"].trial_schema_version,
        "sources": [
            {
                "relative_path": "trial_0000.json",
                "sha256": "7" * 64,
                "cell_id": inputs["plan"].cells[0].cell_id,
                "trial_index": 0,
                "attempt_id": "8" * 32,
                "valid_analysis_trial": True,
            }
        ],
    }
    manifest = {**manifest_payload, "manifest_digest": _digest(manifest_payload)}
    manifest_path = tmp_path / "analysis-manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    gate_payload = {
        "schema_version": "1.0.0",
        "plan_digest": inputs["plan"].digest,
        "analysis_manifest_digest": manifest["manifest_digest"],
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
    gate = {**gate_payload, "artifact_digest": _digest(gate_payload)}
    gate_path = tmp_path / "pilot-gate.json"
    gate_path.write_text(json.dumps(gate), encoding="utf-8")
    return manifest_path, gate_path


def _release_args(inputs, lock_path, manifest_path, gate_path, output):
    return [
        "create-pilot-release",
        "--design-lock",
        str(lock_path),
        "--pilot-gate",
        str(gate_path),
        "--analysis-manifest",
        str(manifest_path),
        "--commitment",
        str(inputs["commitment_path"]),
        "--custody",
        str(inputs["custody_path"]),
        "--passphrase-file",
        str(inputs["passphrase_path"]),
        "--created-at",
        "2026-08-23T00-00-00Z",
        "--output",
        str(output),
    ]


def test_cli_creates_and_verifies_exact_signed_artifacts_without_secrets(
    tmp_path, frozen_runtime_binding, capsys
):
    inputs = _prepare_inputs(tmp_path, frozen_runtime_binding)
    lock_path = tmp_path / "design-lock.json"
    assert main(_design_args(inputs, lock_path)) == 0
    design_output = capsys.readouterr().out
    assert "artifact_sha256" in design_output
    assert "custody_artifact_sha256" in design_output
    for forbidden in ("correct horse", "private_key_b64", "signature_b64", "providers"):
        assert forbidden not in design_output
    lock = load_v2_design_lock(lock_path)
    assert lock.base_n == 36
    assert lock.confirmatory_valid_slots == 28980

    manifest_path, gate_path = _release_inputs(tmp_path, inputs, lock)
    release_path = tmp_path / "pilot-release.json"
    assert main(
        _release_args(
            inputs, lock_path, manifest_path, gate_path, release_path
        )
    ) == 0
    release_output = capsys.readouterr().out
    assert "pilot_gate_artifact_sha256" in release_output
    assert "analysis_manifest_artifact_sha256" in release_output
    assert "signature_b64" not in release_output
    release = load_v2_pilot_release(release_path, lock)
    assert release.confirmatory_collection_allowed is True

    assert main(
        [
            "verify",
            "--design-lock",
            str(lock_path),
            "--pilot-release",
            str(release_path),
            "--commitment",
            str(inputs["commitment_path"]),
        ]
    ) == 0
    verify_output = capsys.readouterr().out
    assert lock.digest in verify_output
    assert release.digest in verify_output


def test_cli_outputs_are_exclusive_and_wrong_passphrase_fails_closed(
    tmp_path, frozen_runtime_binding
):
    inputs = _prepare_inputs(tmp_path, frozen_runtime_binding)
    lock_path = tmp_path / "design-lock.json"
    args = _design_args(inputs, lock_path)
    assert main(args) == 0
    original = lock_path.read_bytes()
    assert main(args) == 2
    assert lock_path.read_bytes() == original

    wrong = tmp_path / "wrong-passphrase.txt"
    wrong.write_text("this is definitely the wrong passphrase", encoding="utf-8")
    bad_args = _design_args(inputs, tmp_path / "must-not-exist.json")
    bad_args[bad_args.index("--passphrase-file") + 1] = str(wrong)
    assert main(bad_args) == 2
    assert not (tmp_path / "must-not-exist.json").exists()


def test_release_rejects_redigested_nonproceed_gate(
    tmp_path, frozen_runtime_binding
):
    inputs = _prepare_inputs(tmp_path, frozen_runtime_binding)
    lock_path = tmp_path / "design-lock.json"
    assert main(_design_args(inputs, lock_path)) == 0
    lock = load_v2_design_lock(lock_path)
    manifest_path, gate_path = _release_inputs(tmp_path, inputs, lock)
    gate = json.loads(gate_path.read_text(encoding="utf-8"))
    gate["branch"] = "ceiling"
    gate["confirmatory_collection_allowed"] = False
    gate["task_change_requires_amendment_and_fresh_pilot"] = True
    payload = {key: value for key, value in gate.items() if key != "artifact_digest"}
    gate["artifact_digest"] = _digest(payload)
    gate_path.write_text(json.dumps(gate), encoding="utf-8")

    output = tmp_path / "must-not-release.json"
    assert main(
        _release_args(inputs, lock_path, manifest_path, gate_path, output)
    ) == 2
    assert not output.exists()


def test_verify_rejects_substituted_valid_commitment(
    tmp_path, frozen_runtime_binding
):
    inputs = _prepare_inputs(tmp_path, frozen_runtime_binding)
    lock_path = tmp_path / "design-lock.json"
    assert main(_design_args(inputs, lock_path)) == 0

    other_commitment, other_custody = create_custody_artifacts(
        inputs["plan"], "a different secure custody passphrase"
    )
    other_commitment_path = tmp_path / "other-commitment.json"
    other_custody_path = tmp_path / "other-custody.json"
    write_custody_artifacts(
        other_commitment,
        other_custody,
        commitment_path=other_commitment_path,
        custody_path=other_custody_path,
    )
    assert main(
        [
            "verify",
            "--design-lock",
            str(lock_path),
            "--commitment",
            str(other_commitment_path),
        ]
    ) == 2


def test_cli_rejects_private_custody_inside_public_root(
    tmp_path, frozen_runtime_binding, monkeypatch, capsys
):
    import scripts.v2_design_lock as cli

    inputs = _prepare_inputs(tmp_path, frozen_runtime_binding)
    monkeypatch.setattr(cli, "_ROOT", tmp_path)
    output = tmp_path / "must-not-exist.json"
    assert cli.main(_design_args(inputs, output)) == 2
    assert "outside the public methodology repository" in capsys.readouterr().err
    assert not output.exists()
