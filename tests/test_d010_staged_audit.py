"""Structural tests for the accepted time-bounded D-010 audit envelope."""

import json
from pathlib import Path

import pytest

from analysis.d010_staged_audit import (
    StagedAuditError,
    estimate_human_hours,
    load_staged_audit_policy,
    select_staged_audit,
    staged_gate_decision,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
POLICY = REPO_ROOT / "config" / "v2-human-audit.candidate.json"


def test_candidate_policy_is_bounded_and_forbids_result_selected_expansion():
    policy = load_staged_audit_policy(POLICY)
    assert policy.anchor_labels == 50
    assert policy.focal_label_options == (150,)
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
        lambda raw: raw["label_masking"].__setitem__(
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


def _gate(policy, **overrides):
    values = {
        "evidence_contract_qualified": True,
        "primary_completeness_overall": 0.99,
        "primary_completeness_by_stratum": {"s1": 0.95, "s2": 1.0},
        "design_weighted_ai_kappa": 0.75,
        "minimum_design_weighted_human_ai_kappa": 0.70,
        "eligible_nonanchor_focal_failures_by_context": {
            "windows_powershell": 100,
            "linux_native": 100,
        },
    }
    values.update(overrides)
    return staged_gate_decision(policy, **values)


def test_gate_precedence_and_sparse_boundaries():
    policy = load_staged_audit_policy(POLICY)
    assert _gate(policy) == "run_bounded_audit"
    assert _gate(policy, evidence_contract_qualified=False) == "stop_invalid"
    assert _gate(
        policy,
        evidence_contract_qualified=False,
        eligible_nonanchor_focal_failures_by_context={
            "windows_powershell": 0,
            "linux_native": 0,
        },
    ) == "stop_invalid"
    assert _gate(
        policy,
        eligible_nonanchor_focal_failures_by_context={
            "windows_powershell": 4,
            "linux_native": 146,
        },
    ) == "stop_sparse"
    assert _gate(
        policy,
        eligible_nonanchor_focal_failures_by_context={
            "windows_powershell": 5,
            "linux_native": 144,
        },
    ) == "stop_sparse"
    assert _gate(
        policy,
        eligible_nonanchor_focal_failures_by_context={
            "windows_powershell": 5,
            "linux_native": 145,
        },
    ) == "run_bounded_audit"


def test_zero_de_candidates_does_not_stop_the_focal_audit():
    policy = load_staged_audit_policy(POLICY)
    assert "aggregate_de_candidate_prevalence_without_named_context_effect" in (
        policy.allowed_gate_inputs
    )
    assert _gate(policy) == "run_bounded_audit"


def test_gate_rejects_nonboolean_contract_status():
    policy = load_staged_audit_policy(POLICY)
    with pytest.raises(StagedAuditError, match="must be boolean"):
        _gate(policy, evidence_contract_qualified=1)


def _identities(prefix: str, count: int) -> list[str]:
    return [f"{prefix}-{index:04d}" for index in range(count)]


def _select(
    policy,
    *,
    windows: int,
    linux: int,
    anchors: list[str] | None = None,
    seeded: list[str] | None = None,
):
    return select_staged_audit(
        policy,
        anchor_identities=anchors or _identities("anchor", 50),
        eligible_failed_identities_by_context={
            "windows_powershell": _identities("windows", windows),
            "linux_native": _identities("linux", linux),
        },
        policy_digest="a" * 64,
        analysis_manifest_digest="b" * 64,
        seeded_error_identities=seeded or (),
    )


def test_focal_stage_is_exact_disjoint_srswor_with_recorded_probabilities():
    policy = load_staged_audit_policy(POLICY)
    selection = _select(policy, windows=200, linux=100)

    assert selection.outcome == "run_bounded_audit"
    assert selection.focal_allocation_by_context == {
        "windows_powershell": 99,
        "linux_native": 51,
    }
    assert selection.conditional_inclusion_probability_by_context == {
        "windows_powershell": pytest.approx(99 / 200),
        "linux_native": pytest.approx(51 / 100),
    }
    assert len(selection.anchor_identities) == 50
    assert len(selection.focal_identities) == 150
    assert len(selection.overall_identities) == 200
    assert len(set(selection.overall_identities)) == 200
    assert not set(selection.anchor_identities) & set(selection.focal_identities)

    record = selection.as_record()
    assert record["stage_identities"]["anchor"] == list(
        selection.anchor_identities
    )
    assert record["stage_identities"]["focal"] == list(selection.focal_identities)
    assert record["overall_identities"] == list(selection.overall_identities)


def test_anchor_identities_are_excluded_before_scarcity_and_sampling():
    policy = load_staged_audit_policy(POLICY)
    anchors = _identities("anchor", 50)
    eligible = {
        "windows_powershell": anchors[:20] + _identities("windows", 100),
        "linux_native": anchors[20:30] + _identities("linux", 50),
    }
    selection = select_staged_audit(
        policy,
        anchor_identities=anchors,
        eligible_failed_identities_by_context=eligible,
        policy_digest="a" * 64,
        analysis_manifest_digest="b" * 64,
    )
    assert selection.eligible_nonanchor_by_context == {
        "windows_powershell": 100,
        "linux_native": 50,
    }
    assert len(selection.overall_identities) == 200
    assert not set(anchors) & set(selection.focal_identities)


@pytest.mark.parametrize(
    ("windows", "linux", "reason"),
    [
        (100, 49, "fewer_than_150_eligible_unique_nonanchor_failures"),
        (4, 200, "fewer_than_5_in_windows_powershell"),
    ],
)
def test_scarcity_stops_at_anchor_without_census_or_replacement(
    windows: int, linux: int, reason: str
):
    policy = load_staged_audit_policy(POLICY)
    selection = _select(policy, windows=windows, linux=linux)
    assert selection.outcome == "stop_sparse"
    assert selection.focal_identities == ()
    assert len(selection.overall_identities) == 50
    assert selection.focal_allocation_by_context == {
        "windows_powershell": 0,
        "linux_native": 0,
    }
    assert reason in selection.scarcity_reasons


def test_hamilton_tie_break_is_stable_by_context_name():
    policy = load_staged_audit_policy(POLICY)
    selection = _select(policy, windows=146, linux=144)
    # Remaining capacities are 141 and 139. Both Hamilton remainders are 0.5;
    # linux_native wins the stable lexical tie break.
    assert selection.focal_allocation_by_context == {
        "windows_powershell": 75,
        "linux_native": 75,
    }


def test_selection_is_deterministic_and_seed_bound():
    policy = load_staged_audit_policy(POLICY)
    first = _select(policy, windows=200, linux=100)
    second = _select(policy, windows=200, linux=100)
    changed = select_staged_audit(
        policy,
        anchor_identities=_identities("anchor", 50),
        eligible_failed_identities_by_context={
            "windows_powershell": _identities("windows", 200),
            "linux_native": _identities("linux", 100),
        },
        policy_digest="c" * 64,
        analysis_manifest_digest="b" * 64,
    )
    assert first.focal_identities == second.focal_identities
    assert first.focal_identities != changed.focal_identities


def test_cross_context_duplicates_fail_closed():
    policy = load_staged_audit_policy(POLICY)
    with pytest.raises(StagedAuditError, match="more than one focal context"):
        select_staged_audit(
            policy,
            anchor_identities=_identities("anchor", 50),
            eligible_failed_identities_by_context={
                "windows_powershell": ["shared"] + _identities("windows", 100),
                "linux_native": ["shared"] + _identities("linux", 100),
            },
            policy_digest="a" * 64,
            analysis_manifest_digest="b" * 64,
        )


def test_h4_assurance_is_exploratory_anchor_plus_selected_seeded_focal_only():
    policy = load_staged_audit_policy(POLICY)
    seeded = _identities("windows", 200)
    selection = _select(policy, windows=200, linux=100, seeded=seeded)
    assert selection.h4_assurance_scope == (
        "exploratory_anchor_plus_any_seeded_focal_coverage"
    )
    assert set(selection.h4_seeded_focal_identities) == (
        set(selection.focal_identities) & set(seeded)
    )
    record = selection.as_record()
    assert record["h4_assurance"]["scope"] == selection.h4_assurance_scope
