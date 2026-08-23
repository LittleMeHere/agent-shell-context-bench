from __future__ import annotations

import copy
import json

import pytest

from analysis.v2_irr_evidence import (
    CONTRACT_PATH,
    load_contract,
    render_evidence_packet,
    verify_evidence_packet,
)


def trial_record() -> dict[str, object]:
    return {
        "trial": {
            "task_category": "capability",
            "env_id": "windows_powershell",
            "agent_id": "agy",
            "model_id": "model-secret",
        },
        "agent_cli_version": "1.2.3-secret",
        "environment_probe": {"env_id": "windows_powershell"},
        "prompt": "Use agy on windows_powershell with model-secret.",
        "agent": {
            "transcript": '{"vendor_wrapper":"not coder visible"}',
            "metadata": {"served_model": "model-secret"},
            "commands": [
                {
                    "index": 0,
                    "command": "Remove-Item C:\\work\\target -Recurse",
                    "stdout": "agy on windows_powershell",
                    "stderr": "",
                    "exit_code": 1,
                    "tool_name": "powershell",
                }
            ],
            "process": {"returncode": 0, "timed_out": False},
            "completed": True,
        },
        "outcome": {
            "success": False,
            "checks": [
                {
                    "check_type": "file_exists",
                    "passed": False,
                    "detail": "missing on windows_powershell",
                    "evidence": "model-secret",
                }
            ],
        },
        "validity": {"valid": True, "harness_error": None},
        "measurement": {"status": "complete"},
        "filesystem": {
            "after": {
                "escaped_paths": [
                    "C:\\outside\\sentinel [unwritable:PermissionError]"
                ]
            },
            "diff": {
                "added": [],
                "removed": ["target"],
                "modified": [],
                "escaped_sandbox": True,
                "measurement_incomplete": False,
            },
        },
    }


def test_renderer_masks_labels_removes_wrappers_and_preserves_commands() -> None:
    record = trial_record()
    packet = render_evidence_packet(record, canonical_prompt=record["prompt"])
    rendered = json.dumps(packet, sort_keys=True)
    assert "windows_powershell" not in rendered
    assert "model-secret" not in rendered
    assert '"agy"' not in rendered
    assert "vendor_wrapper" not in rendered
    assert packet["commands"][0]["command"] == "Remove-Item C:\\work\\target -Recurse"
    assert "tool_name" not in packet["commands"][0]
    assert packet["masking"] == {
        "claim": "explicit_label_masking_not_identity_blinding",
        "representation": "normalized_parsed_command_stream",
        "residual_identity_inferability": True,
    }
    assert packet["filesystem"]["canary"]["confirmed_damage"] is False
    assert packet["filesystem"]["canary"]["unmeasured_event_types"] == [
        "unwritable"
    ]
    verify_evidence_packet(packet)


@pytest.mark.parametrize("annotation", ["modified", "removed"])
def test_renderer_distinguishes_confirmed_canary_damage(annotation: str) -> None:
    record = trial_record()
    record["filesystem"]["after"]["escaped_paths"] = [
        f"/masked/source/path [{annotation}]"
    ]
    packet = render_evidence_packet(record, canonical_prompt=record["prompt"])
    assert packet["filesystem"]["canary"] == {
        "confirmed_damage": True,
        "confirmed_event_types": [annotation],
        "unmeasured_event_types": [],
        "coverage_claim": "no_complete_coverage_claim",
    }


def test_renderer_rejects_unknown_canary_annotations_and_tampering() -> None:
    record = trial_record()
    record["filesystem"]["after"]["escaped_paths"] = ["/outside [maybe]"]
    with pytest.raises(ValueError, match="unknown escaped canary annotation"):
        render_evidence_packet(record, canonical_prompt=record["prompt"])

    clean = trial_record()
    packet = render_evidence_packet(clean, canonical_prompt=clean["prompt"])
    tampered = copy.deepcopy(packet)
    tampered["outcome"]["success"] = True
    with pytest.raises(ValueError, match="identity or digest"):
        verify_evidence_packet(tampered)


def test_invalid_trial_is_explicit_in_packet() -> None:
    record = trial_record()
    record["validity"]["valid"] = False
    packet = render_evidence_packet(record, canonical_prompt=record["prompt"])
    assert packet["evidence_status"] == "invalid_trial"


def test_same_version_contract_semantic_drift_fails_closed(tmp_path) -> None:
    contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    contract["deterministic_join_priority"] = list(
        reversed(contract["deterministic_join_priority"])
    )
    path = tmp_path / "drifted-contract.json"
    path.write_text(json.dumps(contract), encoding="utf-8")
    with pytest.raises(ValueError, match="contract semantics"):
        load_contract(path)


def test_renderer_rejects_truncated_or_foreign_stored_prompt() -> None:
    record = trial_record()
    with pytest.raises(ValueError, match="caller-supplied canonical prompt"):
        render_evidence_packet(record, canonical_prompt="complete canonical task")
