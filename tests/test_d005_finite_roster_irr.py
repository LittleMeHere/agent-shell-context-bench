from __future__ import annotations

import math

import numpy as np
import pytest

from analysis.d005_finite_roster_irr import (
    IRRScenario,
    cohen_kappa,
    default_finite_roster_scenarios,
    default_irr_scenarios,
    finite_roster_h2_log_rr_interval,
    finite_roster_oracle_variance,
    multiway_cluster_h2_log_rr_interval,
    simulate_finite_roster_design,
    simulate_h2_measurement_overlay,
    simulate_irr_scenario,
)
from analysis.d013_ceiling_operating_characteristics import (
    broad_instance_counts,
    default_confirm_scenarios,
)


def _confirm_scenario(name: str):
    return next(
        scenario for scenario in default_confirm_scenarios() if scenario.name == name
    )


def _irr_scenario(name: str) -> IRRScenario:
    return next(
        scenario for scenario in default_irr_scenarios() if scenario.name == name
    )


def _small_multiway_h2_case() -> tuple[np.ndarray, ...]:
    task = np.repeat([0, 0, 1, 1], 8)
    configuration = np.repeat([0, 1, 0, 1], 8)
    windows = np.tile(np.repeat([False, True], 4), 4)
    linux = ~windows
    failure = np.ones(32, dtype=bool)
    de_value = np.asarray(
        [
            0, 0, 0, 1, 0, 1, 1, 1,
            0, 0, 1, 1, 1, 1, 1, 1,
            0, 0, 0, 0, 0, 0, 1, 1,
            0, 1, 1, 1, 1, 1, 1, 1,
        ],
        dtype=float,
    )
    return failure, de_value, windows, linux, task, configuration


def test_multiway_cluster_interval_matches_independent_meat_oracle() -> None:
    failure, de_value, windows, linux, task, configuration = (
        _small_multiway_h2_case()
    )
    result = multiway_cluster_h2_log_rr_interval(
        failure,
        de_value,
        windows,
        linux,
        task,
        configuration,
        minimum_failures_per_context=1,
    )
    assert result.estimable
    assert result.q_linux == pytest.approx(6 / 16)
    assert result.q_windows == pytest.approx(13 / 16)
    assert result.rr == pytest.approx(13 / 6)

    influence = np.zeros(32, dtype=float)
    influence[windows] = (de_value[windows] - 13 / 16) / (16 * 13 / 16)
    influence[linux] = -(de_value[linux] - 6 / 16) / (16 * 6 / 16)

    def meat(keys: list[object]) -> float:
        groups = sorted(set(keys), key=str)
        raw = sum(
            sum(
                influence[index]
                for index, key in enumerate(keys)
                if key == group
            )
            ** 2
            for group in groups
        )
        return len(groups) / (len(groups) - 1) * raw

    task_keys = task.tolist()
    config_keys = configuration.tolist()
    intersection_keys = list(zip(task_keys, config_keys, strict=True))
    expected_variance = (
        meat(task_keys) + meat(config_keys) - meat(intersection_keys)
    )
    assert result.variance == pytest.approx(expected_variance)
    assert result.log_rr_standard_error == pytest.approx(
        math.sqrt(expected_variance)
    )
    assert result.degrees_of_freedom == 1


def test_multiway_cluster_interval_is_permutation_invariant() -> None:
    arrays = _small_multiway_h2_case()
    expected = multiway_cluster_h2_log_rr_interval(
        *arrays,
        minimum_failures_per_context=1,
    )
    order = np.random.default_rng(55).permutation(arrays[0].size)
    actual = multiway_cluster_h2_log_rr_interval(
        *(array[order] for array in arrays),
        minimum_failures_per_context=1,
    )
    assert actual == expected


def test_multiway_cluster_interval_fails_closed_on_sparse_and_boundary_data() -> None:
    arrays = _small_multiway_h2_case()
    sparse = multiway_cluster_h2_log_rr_interval(
        *arrays,
        minimum_failures_per_context=17,
    )
    assert not sparse.estimable
    assert sparse.reason == "fewer_than_minimum_failures"

    boundary_arrays = list(arrays)
    boundary_arrays[1] = np.zeros(32, dtype=float)
    boundary = multiway_cluster_h2_log_rr_interval(
        *boundary_arrays,
        minimum_failures_per_context=1,
    )
    assert not boundary.estimable
    assert boundary.reason == "boundary_or_out_of_bounds_context_mean"


def test_multiway_cluster_interval_rejects_malformed_inputs() -> None:
    arrays = list(_small_multiway_h2_case())
    arrays[2] = arrays[2].astype(int)
    with pytest.raises(ValueError, match="windows_mask must be boolean"):
        multiway_cluster_h2_log_rr_interval(
            *arrays,
            minimum_failures_per_context=1,
        )


def test_finite_roster_h2_delta_matches_cellwise_oracle() -> None:
    failure, de_value, windows, linux, task, configuration = (
        _small_multiway_h2_case()
    )
    result = finite_roster_h2_log_rr_interval(
        failure,
        de_value,
        windows,
        linux,
        task,
        configuration,
        minimum_failures_per_context=1,
    )
    assert result.estimable
    assert result.q_linux == pytest.approx(6 / 16)
    assert result.q_windows == pytest.approx(13 / 16)
    assert result.rr == pytest.approx(13 / 6)

    def context_variance(mask: np.ndarray) -> float:
        mean_failure = 0.0
        mean_de = 0.0
        variance_failure = 0.0
        variance_de = 0.0
        covariance = 0.0
        for task_id in (0, 1):
            for config_id in (0, 1):
                cell = mask & (task == task_id) & (configuration == config_id)
                scheduled = int(np.sum(cell))
                failed = int(np.sum(failure[cell]))
                failed_de = float(np.sum(de_value[cell] * failure[cell]))
                p_failure = (failed + 1.0) / (scheduled + 1.5)
                p_de = (failed_de + 0.5) / (scheduled + 1.5)
                mean_failure += scheduled * p_failure
                mean_de += scheduled * p_de
                variance_failure += scheduled * p_failure * (1 - p_failure)
                variance_de += scheduled * p_de * (1 - p_de)
                covariance += scheduled * p_de * (1 - p_failure)
        return (
            variance_de / mean_de**2
            + variance_failure / mean_failure**2
            - 2 * covariance / (mean_de * mean_failure)
        )

    expected_variance = context_variance(linux) + context_variance(windows)
    assert result.log_rr_standard_error == pytest.approx(
        math.sqrt(expected_variance)
    )
    assert result.linux_cells == result.windows_cells == 4


def test_finite_roster_h2_delta_fails_closed_for_invalid_weighted_cells() -> None:
    arrays = list(_small_multiway_h2_case())
    de_value = arrays[1].copy()
    de_value[:4] = -2.0
    arrays[1] = de_value
    result = finite_roster_h2_log_rr_interval(
        *arrays,
        minimum_failures_per_context=1,
    )
    assert not result.estimable
    assert result.reason in {
        "boundary_or_out_of_bounds_context_mean",
        "invalid_smoothed_cell_probabilities",
    }


def test_candidate_scheduler_counts_preserve_family_config_totals() -> None:
    counts = broad_instance_counts(5)
    assert counts.shape == (6, 2, 3, 7)
    assert np.min(counts) == 1
    assert np.max(counts) == 2
    assert np.all(np.sum(counts, axis=2) == 5)


def test_finite_roster_interval_rows_are_reproducible_and_exclusive() -> None:
    kwargs = {
        "design": "test",
        "repetitions_per_family_config": 6,
        "base_common_n": 6,
        "replicates": 1_000,
        "seed": 81,
    }
    first = simulate_finite_roster_design(_confirm_scenario("diffuse_null"), **kwargs)
    second = simulate_finite_roster_design(_confirm_scenario("diffuse_null"), **kwargs)
    assert first == second
    assert {row["interval_method"] for row in first} == {
        "oracle_normal_reference",
        "jeffreys_plugin_normal_candidate",
        "unbiased_cell_normal_candidate",
    }
    for row in first:
        total = sum(
            float(row[key])
            for key in (
                "decision_relevant_probability",
                "bounded_small_probability",
                "inconclusive_probability",
            )
        )
        assert total == pytest.approx(float(row["estimable_probability"]))


def test_unbiased_cell_variance_fails_closed_with_singletons() -> None:
    rows = simulate_finite_roster_design(
        _confirm_scenario("diffuse_null"),
        design="split",
        repetitions_per_family_config=3,
        base_common_n=6,
        replicates=100,
        seed=82,
    )
    unbiased = next(
        row for row in rows if row["interval_method"].startswith("unbiased")
    )
    assert unbiased["min_instance_n"] == 1
    assert unbiased["estimable_probability"] == 0.0
    assert unbiased["coverage_conditional_estimable"] is None


def test_oracle_reference_has_reasonable_coverage_in_moderate_case() -> None:
    rows = simulate_finite_roster_design(
        _confirm_scenario("diffuse_threshold"),
        design="common",
        repetitions_per_family_config=24,
        base_common_n=24,
        replicates=4_000,
        seed=83,
    )
    oracle = next(
        row for row in rows if row["interval_method"] == "oracle_normal_reference"
    )
    assert 0.92 <= float(oracle["coverage_unconditional"]) <= 0.98
    assert abs(float(oracle["point_rd_bias"])) < 0.002


def test_oracle_variance_matches_independent_heterogeneous_loop() -> None:
    linux = np.asarray([[0.05, 0.20], [0.50, 0.80]])
    windows = np.asarray([[0.10, 0.35], [0.45, 0.90]])
    counts = np.asarray([[1, 2], [3, 5]], dtype=np.int64)
    terms = []
    for index in np.ndindex(counts.shape):
        terms.append(
            windows[index] * (1.0 - windows[index]) / counts[index]
            + linux[index] * (1.0 - linux[index]) / counts[index]
        )
    expected = sum(terms) / counts.size**2
    assert finite_roster_oracle_variance(
        linux,
        windows,
        counts,
    ) == pytest.approx(expected)


def test_near_one_stress_records_complete_event_probability() -> None:
    scenario = next(
        item
        for item in default_finite_roster_scenarios()
        if item.name == "near_one_null"
    )
    rows = simulate_finite_roster_design(
        scenario,
        design="split",
        repetitions_per_family_config=3,
        base_common_n=6,
        replicates=500,
        seed=831,
    )
    assert float(rows[0]["either_context_all_event_probability"]) > 0.85
    assert rows[0]["either_context_zero_event_probability"] == 0.0


def test_cohen_kappa_matches_perfect_and_chance_examples() -> None:
    labels = np.asarray([0, 0, 1, 1], dtype=np.int64)
    assert cohen_kappa(labels, labels, n_categories=2) == pytest.approx(1.0)
    second = np.asarray([0, 1, 0, 1], dtype=np.int64)
    assert cohen_kappa(labels, second, n_categories=2) == pytest.approx(0.0)
    three_class_first = np.asarray([0, 0, 0, 1, 1, 2], dtype=np.int64)
    three_class_second = np.asarray([0, 0, 1, 1, 2, 2], dtype=np.int64)
    assert cohen_kappa(
        three_class_first,
        three_class_second,
        n_categories=3,
    ) == pytest.approx(0.5)


def test_cohen_kappa_rejects_invalid_labels() -> None:
    with pytest.raises(ValueError, match="valid category"):
        cohen_kappa(
            np.asarray([0, 2], dtype=np.int64),
            np.asarray([0, 1], dtype=np.int64),
            n_categories=2,
        )


def test_irr_gate_cases_are_exclusive_and_reproducible() -> None:
    kwargs = {
        "replicates": 300,
        "seed": 84,
        "full_sample_size": 1_000,
        "human_anchor_size": 50,
        "batch_size": 50,
    }
    first = simulate_irr_scenario(_irr_scenario("high_quality_balanced"), **kwargs)
    second = simulate_irr_scenario(_irr_scenario("high_quality_balanced"), **kwargs)
    assert first == second
    assert sum(
        float(first[key])
        for key in (
            "case_a_confirmatory_probability",
            "case_b_shared_bias_demotion_probability",
            "case_c_ai_disagreement_demotion_probability",
        )
    ) == pytest.approx(1.0)
    assert float(first["case_a_confirmatory_probability"]) > 0.90


def test_shared_bias_can_pass_ai_ai_but_fail_human_anchor() -> None:
    row = simulate_irr_scenario(
        _irr_scenario("shared_de_to_c_bias"),
        replicates=500,
        seed=85,
        full_sample_size=1_000,
        human_anchor_size=50,
        batch_size=50,
    )
    assert float(row["mean_kappa_ai_six_category"]) >= 0.60
    assert float(row["case_b_shared_bias_demotion_probability"]) > 0.60


def test_omnibus_kappa_does_not_control_rare_de_binary_kappa() -> None:
    row = simulate_irr_scenario(
        _irr_scenario("rare_de_high_overall_accuracy"),
        replicates=500,
        seed=851,
        full_sample_size=1_000,
        human_anchor_size=50,
        batch_size=50,
    )
    assert float(row["case_a_confirmatory_probability"]) > 0.90
    assert (
        float(row["omnibus_pass_de_binary_below_threshold_probability"])
        > 0.75
    )


def test_measurement_overlay_marks_its_independence_approximation() -> None:
    irr = simulate_irr_scenario(
        _irr_scenario("high_quality_balanced"),
        replicates=100,
        seed=86,
        full_sample_size=1_000,
        human_anchor_size=50,
        batch_size=50,
    )
    row = simulate_h2_measurement_overlay(
        irr,
        latent_q_linux=0.10,
        latent_q_windows=0.20,
        base_common_n=6,
        replicates=200,
        seed=87,
    )
    assert row["latent_de_rr"] == pytest.approx(2.0)
    assert float(row["candidate_observed_de_rr"]) < 2.0
    assert "independent" in str(row["combined_probability_note"])
    for value in row.values():
        if isinstance(value, float):
            assert math.isfinite(value)


def test_invalid_irr_scenarios_fail_closed() -> None:
    with pytest.raises(ValueError):
        IRRScenario("bad", (0.20,) * 6, 0.9, 0.9, 0.9)
    with pytest.raises(ValueError):
        simulate_irr_scenario(
            _irr_scenario("high_quality_balanced"),
            replicates=1,
            seed=1,
            full_sample_size=999,
        )
