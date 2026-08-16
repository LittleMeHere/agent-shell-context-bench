from __future__ import annotations

import pytest

from analysis.d005_h1_recovery_envelope import (
    H1RecoveryMechanism,
    default_recovery_mechanisms,
    roster_completion_probability,
    simulate_h1_recovery,
)
from analysis.d013_ceiling_operating_characteristics import (
    default_confirm_scenarios,
)


def _scenario(name: str):
    return next(item for item in default_confirm_scenarios() if item.name == name)


def _mechanism(name: str) -> H1RecoveryMechanism:
    return next(item for item in default_recovery_mechanisms() if item.name == name)


def test_recovery_simulation_is_reproducible_and_exclusive() -> None:
    kwargs = {
        "scenario": _scenario("diffuse_null"),
        "mechanism": _mechanism("combined_operational_stress"),
        "replicates": 300,
        "seed": 91,
        "batch_size": 75,
    }
    first = simulate_h1_recovery(**kwargs)
    second = simulate_h1_recovery(**kwargs)
    assert first == second
    assert first["batch_size"] == 75
    assert sum(
        float(first[key])
        for key in (
            "decision_relevant_probability",
            "bounded_small_probability",
            "inconclusive_probability",
        )
    ) == pytest.approx(1.0)


def test_independent_reference_recovers_nominal_candidate_behavior() -> None:
    row = simulate_h1_recovery(
        _scenario("diffuse_threshold"),
        _mechanism("independent_reference"),
        replicates=2_000,
        seed=92,
    )
    assert float(row["coverage_probability"]) >= 0.94
    assert float(row["wrong_threshold_declaration_probability"]) <= 0.01
    assert abs(float(row["point_rd_bias"])) <= 0.005
    assert row["screen_pass"] is True


def test_wave_rotation_changes_slot_probabilities_without_changing_roster() -> None:
    reference = simulate_h1_recovery(
        _scenario("diffuse_null"),
        _mechanism("independent_reference"),
        replicates=300,
        seed=93,
    )
    drift = simulate_h1_recovery(
        _scenario("diffuse_null"),
        _mechanism("balanced_common_calendar_drift"),
        replicates=300,
        seed=93,
    )
    assert reference["cells_per_context"] == drift["cells_per_context"] == 252
    assert reference["trials_two_contexts"] == drift["trials_two_contexts"] == 1_680
    assert reference["mean_true_slot_weighted_rd"] != drift["mean_true_slot_weighted_rd"]


def test_retry_cap_probe_never_converts_attrition_into_analysis() -> None:
    probability = roster_completion_probability(
        valid_slots=720,
        invalid_attempt_probability=0.05,
        attempts_per_slot=3,
    )
    assert 0.0 < probability < 1.0
    assert roster_completion_probability(
        valid_slots=720,
        invalid_attempt_probability=0.0,
        attempts_per_slot=1,
    ) == 1.0


@pytest.mark.parametrize(
    "kwargs",
    (
        {"name": "bad", "common_wave_logit_shifts": (0.0,)},
        {"name": "bad", "differential_domain_config_sd": -0.1},
        {"name": "bad", "matched_slot_rho": 1.0},
    ),
)
def test_invalid_recovery_mechanisms_fail_closed(kwargs) -> None:
    with pytest.raises(ValueError):
        H1RecoveryMechanism(**kwargs)


def test_invalid_retry_cap_inputs_fail_closed() -> None:
    with pytest.raises(ValueError):
        roster_completion_probability(
            valid_slots=0,
            invalid_attempt_probability=0.1,
            attempts_per_slot=2,
        )
    with pytest.raises(ValueError):
        roster_completion_probability(
            valid_slots=2,
            invalid_attempt_probability=1.1,
            attempts_per_slot=2,
        )
