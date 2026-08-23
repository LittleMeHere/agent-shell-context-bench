from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import scripts.irr_code as irr
from analysis.v2_analysis_dataset import AnalysisTrial
from analysis.v2_analysis_manifest import (
    AnalysisManifest,
    AnalysisSourceSnapshot,
    TrialSource,
)
from harness.scheduler import CONFIRMATORY_PHASE, V2_PILOT_PHASE


PLAN_DIGEST = "a" * 64
MANIFEST_DIGEST = "b" * 64


def _snapshot(*, valid: bool, index: int = 0) -> AnalysisSourceSnapshot:
    cell_id = f"{index + 1:016x}"
    attempt_id = f"{index + 1:032x}"
    record = {
        "prompt": f"repair task {index}",
        "environment_probe": {"env_id": "secret-environment"},
        "agent": {"transcript": f"tool evidence {index}"},
        "outcome": {"success": index % 2 == 0},
    }
    raw_bytes = json.dumps(record, sort_keys=True).encode("utf-8")
    row = AnalysisTrial(
        plan_digest=PLAN_DIGEST,
        cell_id=cell_id,
        config_id="cfg-1",
        env_id="windows_powershell",
        agent_id="codex",
        model_id="gpt-5",
        task_id="C01",
        family_id="code-edit",
        instance_id="C01-I01",
        phrasing="direct",
        task_category="capability",
        trial_index=index,
        valid_slot_index=index if valid else None,
        attempt_id=attempt_id,
        valid_analysis_trial=valid,
        binary_success_final=index % 2 == 0,
        failed=index % 2 != 0 if valid else None,
        transcript_analysis_eligible=True if valid else None,
        agy_cwd_status=None,
        execution_position=index if valid else None,
        collection_epoch=1 if valid else None,
    )
    source = TrialSource(
        relative_path=f"records/trial_{index}.json",
        sha256=hashlib.sha256(raw_bytes).hexdigest(),
        cell_id=cell_id,
        trial_index=index,
        attempt_id=attempt_id,
        valid_analysis_trial=valid,
    )
    return AnalysisSourceSnapshot(
        source=source,
        raw_bytes=raw_bytes,
        record=record,
        analysis_trial=row,
    )


def _manifest(snapshots: tuple[AnalysisSourceSnapshot, ...]) -> AnalysisManifest:
    return AnalysisManifest(
        schema_version="1.0.0",
        purpose="v2_frozen_analysis_trial_sources",
        plan_digest=PLAN_DIGEST,
        trial_schema_version="2.0.0",
        sources=tuple(snapshot.source for snapshot in snapshots),
        manifest_digest=MANIFEST_DIGEST,
    )


class RecordingBackend(irr.RaterBackend):
    def __init__(self, response: object, *, model_pin: str = "model-a@1") -> None:
        self.coder_id = "coder1"
        self.model_pin = model_pin
        self.response = response
        self.calls: list[tuple[str, str]] = []

    def code_one(self, system_prompt: str, user_content: str) -> irr.RaterResponse:
        self.calls.append((system_prompt, user_content))
        if isinstance(self.response, Exception):
            raise self.response
        return self.response  # type: ignore[return-value]


def _patch_run_inputs(
    monkeypatch: pytest.MonkeyPatch,
    snapshots: tuple[AnalysisSourceSnapshot, ...],
    *,
    phase: str = CONFIRMATORY_PHASE,
) -> None:
    manifest = _manifest(snapshots)
    plan = SimpleNamespace(digest=PLAN_DIGEST, phase=phase)
    monkeypatch.setattr(irr, "check_prompt_frozen", lambda: "frozen prompt\n")
    monkeypatch.setattr(irr, "load_plan", lambda _path: plan)
    monkeypatch.setattr(
        irr,
        "load_analysis_snapshot",
        lambda _plan, _source, _manifest_path: (manifest, snapshots),
    )


def _successful_response() -> irr.RaterResponse:
    return irr.RaterResponse(
        raw_response=json.dumps(
            {"code": "C", "rationale": "The transcript shows a bounded retry."}
        ),
        observed_model_id="model-a@1",
        request_id="request-1",
    )


def test_manifest_bound_run_codes_only_valid_sources_and_resumes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    valid = _snapshot(valid=True)
    invalid = _snapshot(valid=False, index=1)
    snapshots = (valid, invalid)
    _patch_run_inputs(monkeypatch, snapshots)
    source_root = tmp_path / "sources"
    out_root = tmp_path / "private-coder-output"
    source_root.mkdir()
    backend = RecordingBackend(_successful_response())

    written = irr.run_coder(
        backend,
        plan_path=tmp_path / "plan.json",
        source_root=source_root,
        manifest_path=tmp_path / "manifest.json",
        out_root=out_root,
        dry_run=False,
    )

    assert written == 1
    assert len(backend.calls) == 1
    assert "secret-environment" not in backend.calls[0][1]
    coder_dir = out_root / "coder1"
    labels = list(coder_dir.glob("*.json"))
    label_path = next(path for path in labels if path.name.endswith("__coder1.json"))
    label = json.loads(label_path.read_text(encoding="utf-8"))
    assert label["status"] == "coded"
    assert label["analysis_manifest_digest"] == MANIFEST_DIGEST
    assert label["source"] == irr._source_identity(valid)
    assert label["transcript_sha256"] == irr.prompt_sha256("tool evidence 0")
    assert label["prompt_sha256"] == irr.prompt_sha256("frozen prompt\n")
    assert label["observed_model_id"] == backend.model_pin
    assert label["request_id"] == "request-1"
    assert (coder_dir / irr._BINDING_NAME).is_file()
    assert (coder_dir / irr._COMPLETE_NAME).is_file()
    loaded = irr.load_completed_coder_run(
        plan_path=tmp_path / "plan.json",
        source_root=source_root,
        manifest_path=tmp_path / "manifest.json",
        out_root=out_root,
        coder_id="coder1",
        model_pin=backend.model_pin,
    )
    assert len(loaded) == 1
    assert loaded[0]["label_digest"] == label["label_digest"]

    assert irr.run_coder(
        backend,
        plan_path=tmp_path / "plan.json",
        source_root=source_root,
        manifest_path=tmp_path / "manifest.json",
        out_root=out_root,
        dry_run=False,
    ) == 0
    assert len(backend.calls) == 1

    unexpected = coder_dir / "unbound.json"
    unexpected.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="unexpected JSON artifacts"):
        irr.run_coder(
            backend,
            plan_path=tmp_path / "plan.json",
            source_root=source_root,
            manifest_path=tmp_path / "manifest.json",
            out_root=out_root,
            dry_run=False,
        )
    unexpected.unlink()

    label["rationale"] = "tampered"
    label_path.write_text(json.dumps(label), encoding="utf-8")
    with pytest.raises(ValueError, match="label digest mismatch"):
        irr.run_coder(
            backend,
            plan_path=tmp_path / "plan.json",
            source_root=source_root,
            manifest_path=tmp_path / "manifest.json",
            out_root=out_root,
            dry_run=False,
        )
    assert len(backend.calls) == 1


@pytest.mark.parametrize(
    ("response", "expected_status"),
    [
        (
            irr.RaterResponse(
                raw_response="not-json",
                observed_model_id="model-a@1",
            ),
            "malformed",
        ),
        (
            irr.RaterResponse(
                raw_response="policy refusal",
                observed_model_id="model-a@1",
                refused=True,
            ),
            "refused",
        ),
        (
            irr.RaterResponse(
                raw_response=json.dumps({"code": "A", "rationale": "evidence"}),
                observed_model_id="model-b@2",
            ),
            "model_substitution",
        ),
        (RuntimeError("service unavailable"), "backend_error"),
        (object(), "backend_error"),
    ],
)
def test_missing_label_states_are_recorded_once_without_fallback(
    response: object, expected_status: str
) -> None:
    snapshot = _snapshot(valid=True)
    manifest = _manifest((snapshot,))
    backend = RecordingBackend(response)
    record = irr._code_snapshot(
        snapshot=snapshot,
        manifest=manifest,
        backend=backend,
        prompt="frozen prompt\n",
        prompt_hash=irr.prompt_sha256("frozen prompt\n"),
        dry_run=False,
    )
    assert record["status"] == expected_status
    assert record["code"] is None
    assert len(backend.calls) == 1


def test_dry_run_is_explicitly_invalid_label() -> None:
    snapshot = _snapshot(valid=True)
    manifest = _manifest((snapshot,))
    backend = irr.DryRunBackend("coder2")
    record = irr._code_snapshot(
        snapshot=snapshot,
        manifest=manifest,
        backend=backend,
        prompt="frozen prompt\n",
        prompt_hash=irr.prompt_sha256("frozen prompt\n"),
        dry_run=True,
    )
    assert record["status"] == "dry_run"
    assert record["dry_run"] is True
    assert record["coder_id"] == "coder2"


def test_run_requires_prospectively_assigned_backend_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    snapshot = _snapshot(valid=True)
    _patch_run_inputs(monkeypatch, (snapshot,))
    source_root = tmp_path / "sources"
    source_root.mkdir()

    placeholder = RecordingBackend(
        _successful_response(),
        model_pin="PIN-AT-START:lineage-A-model@version",
    )
    with pytest.raises(ValueError, match="model identity is not frozen"):
        irr.run_coder(
            placeholder,
            plan_path=tmp_path / "plan.json",
            source_root=source_root,
            manifest_path=tmp_path / "manifest.json",
            out_root=tmp_path / "private-coder-output",
            dry_run=False,
        )

    dry_output = tmp_path / "dry-output"
    assert irr.run_coder(
        irr.DryRunBackend("coder2"),
        plan_path=tmp_path / "plan.json",
        source_root=source_root,
        manifest_path=tmp_path / "manifest.json",
        out_root=dry_output,
        dry_run=True,
    ) == 1
    label = next((dry_output / "coder2").glob("*__coder2.json"))
    assert json.loads(label.read_text(encoding="utf-8"))["status"] == "dry_run"
    loaded = irr.load_completed_coder_run(
        plan_path=tmp_path / "plan.json",
        source_root=source_root,
        manifest_path=tmp_path / "manifest.json",
        out_root=dry_output,
        coder_id="coder2",
        model_pin=irr.DryRunBackend.model_pin,
        dry_run=True,
    )
    assert len(loaded) == 1
    label.unlink()
    with pytest.raises(ValueError, match="completed coder run has a missing"):
        irr.run_coder(
            irr.DryRunBackend("coder2"),
            plan_path=tmp_path / "plan.json",
            source_root=source_root,
            manifest_path=tmp_path / "manifest.json",
            out_root=dry_output,
            dry_run=True,
        )
    assert not label.exists()


def test_parser_and_blinding_are_strict() -> None:
    snapshot = _snapshot(valid=True)
    content = irr._blind_user_content(snapshot.record)
    assert "repair task 0" in content
    assert "tool evidence 0" in content
    assert "secret-environment" not in content
    assert irr._parse_code('{"code":"f","rationale":"shown"}') == ("F", "shown")
    for raw in (
        "not-json",
        '{"code":"A","rationale":"ok","extra":true}',
        '{"code":"G","rationale":"ok"}',
        json.dumps({"code": "A", "rationale": "x" * 401}),
        '{"code":"A","rationale":""}',
    ):
        with pytest.raises(ValueError):
            irr._parse_code(raw)


def test_output_paths_must_be_private_and_separate(tmp_path: Path) -> None:
    source_root = tmp_path / "sources"
    source_root.mkdir()
    with pytest.raises(ValueError, match="must be separate"):
        irr.validate_coder_paths(source_root, source_root / "labels")
    with pytest.raises(ValueError, match="external private root"):
        irr.validate_coder_paths(source_root, irr._BENCH_ROOT / "analysis" / "irr")


def test_real_coding_refuses_nonconfirmatory_plan(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    snapshot = _snapshot(valid=True)
    _patch_run_inputs(monkeypatch, (snapshot,), phase=V2_PILOT_PHASE)
    source_root = tmp_path / "sources"
    source_root.mkdir()
    with pytest.raises(ValueError, match="requires a confirmatory plan"):
        irr.run_coder(
            RecordingBackend(_successful_response()),
            plan_path=tmp_path / "plan.json",
            source_root=source_root,
            manifest_path=tmp_path / "manifest.json",
            out_root=tmp_path / "private-coder-output",
            dry_run=False,
        )


def test_cli_requires_explicit_real_backend_pins(tmp_path: Path) -> None:
    with pytest.raises(SystemExit):
        irr.main(
            [
                "--coder", "coder1",
                "--plan", str(tmp_path / "plan.json"),
                "--source-root", str(tmp_path / "sources"),
                "--manifest", str(tmp_path / "manifest.json"),
                "--out", str(tmp_path / "output"),
            ]
        )
