"""Structural tests for the accepted time-bounded D-010 audit envelope."""

import json
from pathlib import Path

import pytest

from analysis.d010_staged_audit import (
    StagedAuditError,
    estimate_human_hours,
    load_staged_audit_policy,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
POLICY = REPO_ROOT / "config" / "v2-human-audit.candidate.json"


def test_candidate_policy_is_bounded_and_forbids_result_selected_expansion():
    policy = load_staged_audit_policy(POLICY)
    assert policy.anchor_labels == 50
    assert policy.focal_label_options == (100, 150)
    assert policy.maximum_routine_total_labels == 200
    assert "named_environment_effect_direction" in policy.forbidden_gate_inputs
    assert "forecast_significance_after_expansion" in policy.forbidden_gate_inputs
    assert policy.gate_outcomes == {
        "stop_sparse",
        "stop_invalid",
        "run_bounded_audit",
    }


@pytest.mark.parametrize(
    ("labels", "minutes", "expected"),
    [
        (50, 5, 4.583333333333333),
        (150, 5, 13.75),
        (200, 5, 18.333333333333332),
        (200, 8, 29.333333333333332),
    ],
)
def test_human_hour_envelope(labels: int, minutes: int, expected: float):
    assert estimate_human_hours(labels, minutes_per_label=minutes) == pytest.approx(
        expected
    )


def test_invalid_time_inputs_fail_closed():
    with pytest.raises(StagedAuditError):
        estimate_human_hours(0, minutes_per_label=5)
    with pytest.raises(StagedAuditError):
        estimate_human_hours(50, minutes_per_label=float("nan"))


@pytest.mark.parametrize(
    "mutate",
    [
        lambda raw: raw["focal_audit"].__setitem__(
            "sampling", "investigator_selected_significant_cases"
        ),
        lambda raw: raw["focal_audit"].__setitem__(
            "population", "significant_named_context_failures"
        ),
        lambda raw: raw["gate"]["allowed_inputs"].append(
            "named_context_h2_z_score"
        ),
        lambda raw: raw["gate"].__setitem__(
            "expansion_rule", "run_if_hypothesis_favorable"
        ),
        lambda raw: raw["human_blinding"].__setitem__(
            "may_unblind_if_interesting", True
        ),
    ],
)
def test_outcome_selected_or_unknown_policy_fields_fail_closed(
    tmp_path: Path, mutate
):
    raw = json.loads(POLICY.read_text(encoding="utf-8"))
    mutate(raw)
    candidate = tmp_path / "policy.json"
    candidate.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(StagedAuditError):
        load_staged_audit_policy(candidate)
