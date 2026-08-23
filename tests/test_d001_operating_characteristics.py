from __future__ import annotations

import math

import pytest

from analysis.d001_operating_characteristics import (
    DecisionState,
    Scenario,
    classify_existence_plus_magnitude,
    classify_threshold_interval,
    finite_roster_probabilities,
    simulate_scenario,
)


def _row(rows: list[dict[str, float | int | str]], option: str) -> dict:
    return next(row for row in rows if row["option"] == option)


def test_threshold_states_are_mutually_exclusive_at_boundaries() -> None:
    assert (
        classify_threshold_interval(0.06, 0.08, 0.05)
        is DecisionState.DECISION_RELEVANT
    )
    assert (
        classify_threshold_interval(0.01, 0.04, 0.05)
        is DecisionState.BOUNDED_SMALL
    )
    assert (
        classify_threshold_interval(0.01, 0.05, 0.05)
        is DecisionState.INCONCLUSIVE
    )
    assert (
        classify_threshold_interval(0.05, 0.08, 0.05)
        is DecisionState.INCONCLUSIVE
    )
    assert (
        classify_threshold_interval(math.nan, math.nan, 0.05)
        is DecisionState.UNESTIMABLE
    )
    with pytest.raises(ValueError, match="lower interval bound"):
        classify_threshold_interval(0.08, 0.06, 0.05)


def test_existence_plus_magnitude_requires_both_conditions() -> None:
    assert (
        classify_existence_plus_magnitude(1.6, 1.1, 2.0)
        is DecisionState.DECISION_RELEVANT
    )
    assert (
        classify_existence_plus_magnitude(1.4, 1.1, 1.8)
        is DecisionState.INCONCLUSIVE
    )
    assert (
        classify_existence_plus_magnitude(1.6, 0.9, 2.1)
        is DecisionState.INCONCLUSIVE
    )
    assert (
        classify_existence_plus_magnitude(1.3, 1.1, 1.4)
        is DecisionState.BOUNDED_SMALL
    )


def test_finite_roster_probabilities_hit_requested_margins() -> None:
    scenario = Scenario(
        linux_rate=0.12,
        target_rd=0.07,
        n_per_cell=6,
        task_logit_sd=0.9,
        config_logit_sd=0.7,
        task_context_logit_sd=0.5,
        config_context_logit_sd=0.4,
    )
    p_linux, p_windows = finite_roster_probabilities(scenario)

    assert len(p_linux) == 35
    assert len(p_windows) == 35
    assert float(p_linux.mean()) == pytest.approx(0.12, abs=1e-12)
    assert float(p_windows.mean()) == pytest.approx(0.19, abs=1e-12)


def test_precise_null_becomes_bounded_small_not_uninterpretable() -> None:
    common = dict(linux_rate=0.20, target_rd=0.0)
    low_n = simulate_scenario(
        Scenario(**common, n_per_cell=6),
        delta_rd=0.05,
        replicates=12_000,
        seed=73,
    )
    high_n = simulate_scenario(
        Scenario(**common, n_per_cell=96),
        delta_rd=0.05,
        replicates=12_000,
        seed=74,
    )

    low_row = _row(low_n, "D_decision_relevant_rd")
    high_row = _row(high_n, "D_decision_relevant_rd")
    assert high_row["bounded_small_probability"] > low_row["bounded_small_probability"]
    assert high_row["bounded_small_probability"] > 0.98
    assert high_row["unestimable_probability"] == 0.0


def test_boundary_scenario_is_mostly_inconclusive() -> None:
    rows = simulate_scenario(
        Scenario(linux_rate=0.20, target_rd=0.05, n_per_cell=100),
        delta_rd=0.05,
        replicates=20_000,
        seed=211,
    )
    result = _row(rows, "D_decision_relevant_rd")

    assert result["decision_relevant_probability"] < 0.04
    assert result["bounded_small_probability"] < 0.04
    assert result["inconclusive_probability"] > 0.92
    assert result["rd_coverage"] > 0.93


def test_homogeneous_rd_rmse_matches_independent_binomial_oracle() -> None:
    linux_rate = 0.20
    windows_rate = 0.25
    n_per_cell = 24
    rows = simulate_scenario(
        Scenario(
            linux_rate=linux_rate,
            target_rd=windows_rate - linux_rate,
            n_per_cell=n_per_cell,
            task_logit_sd=0.0,
            config_logit_sd=0.0,
            task_context_logit_sd=0.0,
            config_context_logit_sd=0.0,
        ),
        delta_rd=0.05,
        replicates=30_000,
        seed=616,
    )
    result = _row(rows, "D_decision_relevant_rd")
    independent_standard_error = math.sqrt(
        linux_rate * (1.0 - linux_rate) / (35 * n_per_cell)
        + windows_rate * (1.0 - windows_rate) / (35 * n_per_cell)
    )

    assert result["rd_bias"] == pytest.approx(0.0, abs=0.0003)
    assert result["rd_rmse"] == pytest.approx(
        independent_standard_error,
        rel=0.02,
    )


def test_low_event_ratio_can_be_unestimable_while_rd_remains_defined() -> None:
    rows = simulate_scenario(
        Scenario(
            linux_rate=0.001,
            target_rd=0.0005,
            n_per_cell=6,
            task_logit_sd=0.0,
            config_logit_sd=0.0,
            task_context_logit_sd=0.0,
            config_context_logit_sd=0.0,
        ),
        delta_rd=0.05,
        replicates=8_000,
        seed=991,
    )
    ratio_row = _row(rows, "A_threshold_superiority_rr")
    rd_row = _row(rows, "D_decision_relevant_rd")

    assert ratio_row["unestimable_probability"] > 0.90
    assert rd_row["unestimable_probability"] == 0.0


def test_all_zero_observations_do_not_create_zero_width_rd_certainty() -> None:
    rows = simulate_scenario(
        Scenario(
            linux_rate=1e-9,
            target_rd=0.0,
            n_per_cell=6,
            task_logit_sd=0.0,
            config_logit_sd=0.0,
            task_context_logit_sd=0.0,
            config_context_logit_sd=0.0,
        ),
        delta_rd=0.01,
        replicates=100,
        seed=441,
    )
    rd_row = _row(rows, "D_decision_relevant_rd")

    assert rd_row["bounded_small_probability"] == 0.0
    assert rd_row["inconclusive_probability"] == 1.0


def test_simulation_is_seed_reproducible() -> None:
    scenario = Scenario(linux_rate=0.10, target_rd=0.05, n_per_cell=12)
    first = simulate_scenario(
        scenario,
        delta_rd=0.05,
        replicates=500,
        seed=1234,
    )
    second = simulate_scenario(
        scenario,
        delta_rd=0.05,
        replicates=500,
        seed=1234,
    )
    assert first == second
