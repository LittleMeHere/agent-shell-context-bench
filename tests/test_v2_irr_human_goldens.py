from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import v2_irr_human_goldens as human


def _completed_result(
    *, seed: int = 8675309
) -> tuple[dict[str, object], dict[str, object]]:
    packet, expected = human.packet_payload(seed=seed)
    rows: list[dict[str, object]] = []
    for visible in packet["cases"]:
        opaque_id = visible["worksheet_case_id"]
        case = expected[opaque_id]
        rows.append(
            {
                "worksheet_case_id": opaque_id,
                "raw_code": case["expected_raw_code"],
                "evidence": case["expected_evidence"],
                "rationale": "Independent human judgment from the displayed evidence.",
                "uncertain": False,
                "evidence_loading_ms": 1200,
                "active_coding_ms": 2300,
            }
        )
    return packet, {
        "schema_version": human.SCHEMA_VERSION,
        "purpose": human.PURPOSE,
        "analysis_excluded": True,
        "masking_claim": human.MASKING_CLAIM,
        "identity_blinded": False,
        "model_calls": 0,
        "automatic_corrections": 0,
        "selection_seed": seed,
        "suite_revision": packet["suite_revision"],
        "suite_sha256": packet["suite_sha256"],
        "supersedes_sha256": packet["supersedes_sha256"],
        "revision_lineage": packet["revision_lineage"],
        "packet_digest": packet["packet_digest"],
        "completed_cases": 12,
        "results": rows,
    }


def _write_result(tmp_path: Path, result: dict[str, object]) -> Path:
    path = tmp_path / "private" / "human-result.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return path


def test_packet_is_randomized_masked_bound_and_external(tmp_path: Path) -> None:
    output = tmp_path / "private" / "human-goldens-r001.html"
    packet = human.build_packet(
        output_path=output,
        seed=101,
    )
    assert output.is_file()
    assert packet["case_count"] == 12
    assert len(packet["suite_sha256"]) == 64
    assert packet["suite_revision"] == "r005_predata_unknown_exit_escalation"
    assert packet["supersedes_sha256"] == (
        "327882a756beaf889a83e3e5aa57309a5cab54e7eff30b337bf1b0d2ab206d30"
    )
    assert packet["revision_lineage"] == [
        {
            "revision": "r004_predata_operational_hardening",
            "sha256": "327882a756beaf889a83e3e5aa57309a5cab54e7eff30b337bf1b0d2ab206d30",
        },
        {
            "revision": "r003_predata_prompt_boundary_clarification",
            "sha256": "e20e3ce10a6d24d3a97427ee17b78a88642a712ae53bc7af5c7d0858f6ec4325",
        },
        {
            "revision": "r002_predata_adjudicated",
            "sha256": "2375ccc5a948f16c269bfb3386107959021dc967eb7af89192e508108a7a9844",
        },
        {
            "revision": "r001_predata_initial",
            "sha256": "f659404f4386af2dac12d96cf60daa8280da04951cdbd7169d5639246ecdcef4",
        },
    ]
    assert len(packet["packet_digest"]) == 64
    assert packet["masking_claim"] == "explicit_label_masking_not_identity_blinding"
    assert packet["identity_blinded"] is False
    assert packet["model_calls"] == 0
    assert packet["automatic_corrections"] == 0
    assert len({case["worksheet_case_id"] for case in packet["cases"]}) == 12

    html = output.read_text(encoding="utf-8")
    assert "not identity blinding" in html.lower()
    assert "expected_raw_code" not in html
    assert "expected_evidence" not in html
    assert "expected_join" not in html
    for case_id in (
        "G01-clean-recovery",
        "G04-escalating-spiral",
        "G06-unmeasured-canary-is-not-damage",
        "G09-confirmed-canary-E",
    ):
        assert case_id not in html

    with pytest.raises(ValueError, match="refusing to overwrite"):
        human.build_packet(
            output_path=output,
            seed=101,
        )
    with pytest.raises(ValueError, match="external private path"):
        human.build_packet(
            output_path=human._REPO_ROOT / "forbidden.html",
            seed=101,
        )


def test_prior_suite_lineage_is_preserved_across_randomizations() -> None:
    first, _ = human.packet_payload(seed=44)
    second, _ = human.packet_payload(seed=45)
    assert first["suite_sha256"] == second["suite_sha256"]
    assert first["revision_lineage"] == second["revision_lineage"]
    assert first["packet_digest"] != second["packet_digest"]
    assert [case["worksheet_case_id"] for case in first["cases"]] != [
        case["worksheet_case_id"] for case in second["cases"]
    ]


def test_exact_twelve_of_twelve_validates_with_digest(tmp_path: Path) -> None:
    packet, result = _completed_result()
    result_path = _write_result(tmp_path, result)
    validation_path = tmp_path / "private" / "human-validation.json"
    validation = human.validate_result(
        result_path,
        validation_output_path=validation_path,
    )
    assert validation["passed"] == 12
    assert validation["targets"] == 12
    assert validation["qualification_passed"] is True
    assert validation["automatic_corrections"] == 0
    assert validation["suite_sha256"] == packet["suite_sha256"]
    assert validation["suite_revision"] == packet["suite_revision"]
    assert validation["supersedes_sha256"] == packet["supersedes_sha256"]
    assert validation["revision_lineage"] == packet["revision_lineage"]
    assert validation["packet_digest"] == packet["packet_digest"]
    assert len(validation["result_sha256"]) == 64
    assert len(validation["qualification_digest"]) == 64
    payload = {
        key: value
        for key, value in validation.items()
        if key != "qualification_digest"
    }
    assert validation["qualification_digest"] == human._digest(payload)
    assert json.loads(validation_path.read_text(encoding="utf-8")) == validation

    with pytest.raises(ValueError, match="refusing to overwrite"):
        human.validate_result(
            result_path,
            validation_output_path=validation_path,
        )


def test_wrong_human_label_is_rejected_without_correction(tmp_path: Path) -> None:
    _packet, result = _completed_result()
    first = result["results"][0]
    first["raw_code"] = "F" if first["raw_code"] != "F" else "A"
    result_path = _write_result(tmp_path, result)
    with pytest.raises(ValueError, match="did not pass exactly 12/12"):
        human.validate_result(result_path)
    assert first["raw_code"] in {"A", "F"}


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda result: result["results"].pop(), "roster is incomplete"),
        (
            lambda result: result["results"].__setitem__(
                1, dict(result["results"][0])
            ),
            "duplicate or invalid case identities",
        ),
        (
            lambda result: result.__setitem__("suite_sha256", "0" * 64),
            "identity or suite binding is invalid",
        ),
        (
            lambda result: result["results"][0].__setitem__(
                "evidence", {"kind": "none", "command_index": 0}
            ),
            "non-command evidence requires a null command index",
        ),
        (
            lambda result: result.__setitem__("model_calls", False),
            "identity or suite binding is invalid",
        ),
        (
            lambda result: result["results"].reverse(),
            "case order differs from its packet",
        ),
    ],
)
def test_malformed_tampered_or_incomplete_result_fails_closed(
    tmp_path: Path, mutation, message: str
) -> None:
    _packet, result = _completed_result()
    mutation(result)
    result_path = _write_result(tmp_path, result)
    with pytest.raises(ValueError, match=message):
        human.validate_result(result_path)


def test_results_and_validation_must_stay_outside_public_repo(tmp_path: Path) -> None:
    _packet, result = _completed_result()
    external = _write_result(tmp_path, result)
    with pytest.raises(ValueError, match="external private path"):
        human.validate_result(human._REPO_ROOT / "forbidden-result.json")
    with pytest.raises(ValueError, match="external private path"):
        human.validate_result(
            external,
            validation_output_path=human._REPO_ROOT / "forbidden-validation.json",
        )
