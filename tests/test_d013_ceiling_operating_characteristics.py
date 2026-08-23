from __future__ import annotations

import math

import numpy as np
import pytest

from analysis.d013_ceiling_operating_characteristics import (
    GateState,
    H2Scenario,
    PilotGate,
    PilotScenario,
    classify_pilot_gate,
    confirmatory_probabilities,
    default_confirm_scenarios,
    pilot_probabilities,
    run_default_grid,
    simulate_h1_scenario,
    simulate_h2_design,
    simulate_h2_scenario,
    simulate_pilot_scenario,
)


def _scenario(name: str):
    return next(item for item in default_confirm_scenarios() if item.name == name)


def _row(rows: list[dict], design: str, base_n: int) -> dict:
    return next(
        row
        for row in rows
        if row["design"] == design and row["base_common_n"] == base_n
    )


def test_pilot_probabilities_hit_each_domain_target() -> None:
    targets = (0.005, 0.01, 0.02, 0.05, 0.10, 0.20)
    probabilities = pilot_probabilities(
        PilotScenario("calibration", targets)
    )
    assert probabilities.shape == (6, 2, 3, 2, 5)
    assert np.mean(probabilities, axis=(1, 2, 3, 4)) == pytest.approx(
        targets,
        abs=1e-12,
    )


def test_confirmatory_probabilities_hit_each_domain_target() -> None:
    scenario = _scenario("diffuse_threshold")
    linux, windows = confirmatory_probabilities(scenario)
    assert linux.shape == (6, 2, 3, 7)
    assert np.mean(linux, axis=(1, 2, 3)) == pytest.approx(
        scenario.linux_domain_rates,
        abs=1e-12,
    )
    assert np.mean(windows, axis=(1, 2, 3)) == pytest.approx(
        scenario.windows_domain_rates,
        abs=1e-12,
    )


def test_pilot_gate_states_are_exclusive_and_ordered() -> None:
    gate = PilotGate("test", 5, 5, 2, 2, 2, 2)
    failures = np.asarray([0, 100, 10, 10], dtype=np.int64)
    states = classify_pilot_gate(
        total_failures=failures,
        total_trials=100,
        failing_families=np.asarray([0, 12, 1, 3]),
        successful_families=np.asarray([12, 0, 12, 12]),
        failing_domains=np.asarray([0, 6, 1, 2]),
        successful_domains=np.asarray([6, 0, 6, 6]),
        gate=gate,
    )
    assert states.tolist() == [
        GateState.CEILING,
        GateState.FLOOR,
        GateState.CONCENTRATED,
        GateState.PROCEED,
    ]


def test_pilot_state_probabilities_sum_to_one_and_are_reproducible() -> None:
    scenario = PilotScenario("diffuse", (0.05,) * 6)
    first = simulate_pilot_scenario(scenario, replicates=2_000, seed=71)
    second = simulate_pilot_scenario(scenario, replicates=2_000, seed=71)
    assert first == second
    for row in first:
        assert row["pilot_capability_trials"] == 360
        assert row["pilot_capability_valid_slots_per_family_cell"] == 3
        assert row["pilot_seeded_trials"] == 360
        assert row["pilot_full_valid_trials"] == 720
        assert sum(
            row[f"{state.name.lower()}_probability"] for state in GateState
        ) == pytest.approx(1.0)


def test_current_five_miss_an_effect_confined_to_omitted_domain() -> None:
    rows = simulate_h1_scenario(
        _scenario("effect_only_in_omitted_domain_D"),
        base_common_ns=(6,),
        replicates=4_000,
        seed=72,
    )
    current = _row(rows, "A_current_five", 6)
    broad = _row(rows, "C_broad_split_n", 6)
    assert current["target_six_domain_rd"] == pytest.approx(0.05)
    assert current["design_roster_true_rd"] == pytest.approx(0.0, abs=1e-12)
    assert current["roster_estimand_mismatch"] == pytest.approx(-0.05)
    assert broad["design_roster_true_rd"] == pytest.approx(0.05)
    assert abs(broad["bias_vs_six_domain_target"]) < 0.003


def test_current_five_overweight_an_effect_in_domain_a() -> None:
    rows = simulate_h1_scenario(
        _scenario("effect_only_in_overweighted_domain_A"),
        base_common_ns=(6,),
        replicates=2_000,
        seed=73,
    )
    current = _row(rows, "A_current_five", 6)
    assert current["target_six_domain_rd"] == pytest.approx(0.05)
    assert current["design_roster_true_rd"] == pytest.approx(0.12)
    assert current["roster_estimand_mismatch"] == pytest.approx(0.07)


def test_opposing_domains_cancel_in_average_but_not_diagnostics() -> None:
    rows = simulate_h1_scenario(
        _scenario("opposing_domain_mechanisms"),
        base_common_ns=(6,),
        replicates=2_000,
        seed=74,
    )
    broad = _row(rows, "C_broad_split_n", 6)
    assert broad["target_six_domain_rd"] == pytest.approx(0.0, abs=1e-12)
    assert broad["max_abs_true_domain_rd"] == pytest.approx(0.12)
    assert broad["leave_one_domain_out_min_rd"] < 0.0
    assert broad["leave_one_domain_out_max_rd"] > 0.0


@pytest.mark.parametrize(
    ("base_n", "split_n", "trials"),
    [(6, 3, 5_040), (12, 5, 9_660), (24, 10, 19_320)],
)
def test_split_n_costs_match_cost_memo(
    base_n: int,
    split_n: int,
    trials: int,
) -> None:
    rows = simulate_h1_scenario(
        _scenario("diffuse_null"),
        base_common_ns=(base_n,),
        replicates=100,
        seed=75,
    )
    split = _row(rows, "C_broad_split_n", base_n)
    assert split["n_cap"] == split_n
    assert split["confirmatory_trials_full_matrix"] == trials


def test_h2_sparse_failures_are_less_estimable_than_moderate_failures() -> None:
    sparse = H2Scenario(
        "sparse", 0.005, 0.005, 0.01, 0.01, 0.10, 0.20
    )
    moderate = H2Scenario(
        "moderate", 0.05, 0.08, 0.10, 0.15, 0.10, 0.20
    )
    sparse_row = _row(
        simulate_h2_scenario(
            sparse,
            base_common_ns=(6,),
            replicates=4_000,
            seed=76,
        ),
        "C_broad_split_n",
        6,
    )
    moderate_row = _row(
        simulate_h2_scenario(
            moderate,
            base_common_ns=(6,),
            replicates=4_000,
            seed=77,
        ),
        "C_broad_split_n",
        6,
    )
    assert (
        moderate_row["both_pooled_denominators_ge10_probability"]
        > sparse_row["both_pooled_denominators_ge10_probability"] + 0.50
    )
    assert moderate_row["true_conditional_de_rr"] == pytest.approx(2.0)


def test_h2_all_de_events_remain_ratio_estimable() -> None:
    row = simulate_h2_design(
        H2Scenario(
            "almost_all_de",
            0.50,
            0.50,
            0.50,
            0.50,
            0.99999,
            0.99999,
        ),
        design="test",
        capability_count=12,
        n_cap=24,
        n_seed=24,
        base_common_n=24,
        replicates=500,
        seed=771,
    )
    assert row["ratio_estimable_probability"] > 0.99
    assert row["true_conditional_de_rr"] == pytest.approx(1.0)


def test_default_grid_has_expected_records_and_finite_numbers() -> None:
    rows = run_default_grid(
        sections={"pilot", "h1", "h2"},
        replicates=20,
        seed=78,
    )
    assert len(rows) == 30 + 54 + 45
    assert {row["record_type"] for row in rows} == {
        "pilot_gate",
        "h1_target_precision",
        "h2_reference",
    }
    for row in rows:
        for value in row.values():
            if isinstance(value, float):
                assert math.isfinite(value)


@pytest.mark.parametrize(
    "scenario",
    [
        PilotScenario,
    ],
)
def test_invalid_scenarios_fail_closed(scenario) -> None:
    with pytest.raises(ValueError):
        scenario("bad_length", (0.10,) * 5)
    with pytest.raises(ValueError):
        scenario("bad_rate", (0.10,) * 5 + (1.0,))
