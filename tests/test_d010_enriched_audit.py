from __future__ import annotations

import math
from dataclasses import replace
from itertools import combinations, product

import numpy as np
import pytest
from scipy.stats import hypergeom

from analysis.d010_enriched_audit import (
    AuditDesign,
    AuditHumanMode,
    AuditSample,
    _scenario_human_reference_rate,
    ai_audit_state,
    audit_corrected_h2_reference,
    audit_corrected_h2_with_conservative_interval,
    build_audit_strata,
    default_audit_designs,
    deterministic_stratified_allocation,
    hypergeometric_success_bounds,
    run_enriched_audit_grid,
    sample_enriched_audit,
    simulate_enriched_audit_scenario,
    weighted_binary_performance,
)
from analysis.d010_joint_h2_measurement import default_joint_scenarios


def _scenario(name: str):
    if name == "shared_de_to_c_boundary":
        shared_strong = _scenario("shared_de_to_c_strong")
        return replace(
            shared_strong,
            name=name,
            h2=replace(
                shared_strong.h2,
                name=name,
                de_probability_windows=0.20,
            ),
        )
    return next(item for item in default_joint_scenarios() if item.name == name)


def test_ai_audit_states_are_exhaustive_and_fail_closed() -> None:
    coder1 = np.asarray([2, 5, 2, 2, 3, 3, 4])
    coder2 = np.asarray([2, 5, 5, 3, 3, 4, 2])
    assert ai_audit_state(coder1, coder2).tolist() == [0, 1, 2, 3, 4, 4, 3]
    with pytest.raises(ValueError, match="failure-compatible"):
        ai_audit_state(np.asarray([1]), np.asarray([2]))
    with pytest.raises(ValueError, match="failure-compatible"):
        ai_audit_state(np.asarray([2]), np.asarray([6]))


def test_audit_strata_use_context_only_or_context_by_state() -> None:
    failure = np.ones(10, dtype=bool)
    windows = np.zeros(10, dtype=bool)
    windows[:5] = True
    linux = ~windows
    coder1 = np.asarray([2, 5, 2, 2, 3] * 2)
    coder2 = np.asarray([2, 5, 5, 3, 3] * 2)
    context_design = AuditDesign("context", None)
    state_design = AuditDesign("state", (1, 1, 1, 1, 1))
    assert build_audit_strata(
        failure,
        coder1,
        coder2,
        windows,
        linux,
        context_design,
    ).tolist() == [0] * 5 + [1] * 5
    assert build_audit_strata(
        failure,
        coder1,
        coder2,
        windows,
        linux,
        state_design,
    ).tolist() == [0, 1, 2, 3, 4, 5, 6, 7, 8, 9]


def test_deterministic_allocation_has_floors_ties_and_census_redistribution() -> None:
    allocation = deterministic_stratified_allocation(
        np.asarray([100, 3, 0, 20]),
        budget=20,
        weights=np.ones(4),
        minimum_per_populated_stratum=2,
    )
    assert int(np.sum(allocation)) == 20
    assert np.all(allocation <= np.asarray([100, 3, 0, 20]))
    assert np.all(allocation[[0, 1, 3]] >= 2)
    assert deterministic_stratified_allocation(
        np.asarray([10, 10]),
        budget=5,
        weights=np.ones(2),
        minimum_per_populated_stratum=2,
    ).tolist() == [3, 2]
    assert deterministic_stratified_allocation(
        np.asarray([2, 3]),
        budget=20,
        weights=np.ones(2),
        minimum_per_populated_stratum=2,
    ).tolist() == [2, 3]
    with pytest.raises(ValueError, match="floors"):
        deterministic_stratified_allocation(
            np.asarray([10, 10, 10]),
            budget=5,
            weights=np.ones(3),
            minimum_per_populated_stratum=2,
        )


def test_probability_sample_is_unique_and_records_conditional_pi() -> None:
    strata = np.asarray([0] * 10 + [1] * 20)
    sample = sample_enriched_audit(
        np.random.default_rng(301),
        strata,
        design=AuditDesign("context", None),
        budget=10,
    )
    assert sample.size == 10
    assert np.unique(sample.indices).size == 10
    assert sample.allocation.tolist() == [5, 5]
    selected_strata = strata[sample.indices]
    assert np.all(sample.inclusion_probability[selected_strata == 0] == 0.5)
    assert np.all(sample.inclusion_probability[selected_strata == 1] == 0.25)


def test_census_difference_estimator_recovers_human_reference_exactly() -> None:
    failure = np.ones(40, dtype=bool)
    windows = np.zeros(40, dtype=bool)
    windows[:20] = True
    linux = ~windows
    predicted_de = np.zeros(40, dtype=bool)
    human_de_full = np.zeros(40, dtype=bool)
    human_de_full[:6] = True
    human_de_full[20:22] = True
    sample = AuditSample(
        indices=np.arange(40, dtype=np.int64),
        inclusion_probability=np.ones(40),
        population_stratum=np.asarray([0] * 20 + [1] * 20),
        population_counts=np.asarray([20, 20]),
        allocation=np.asarray([20, 20]),
    )
    estimate = audit_corrected_h2_reference(
        failure,
        predicted_de,
        human_de_full,
        sample,
        windows,
        linux,
    )
    assert estimate.estimable
    assert estimate.q_windows == pytest.approx(0.30)
    assert estimate.q_linux == pytest.approx(0.10)
    assert estimate.rr == pytest.approx(3.0)
    assert estimate.design_variance_windows == 0.0
    assert estimate.design_variance_linux == 0.0
    assert estimate.finite_lower == pytest.approx(3.0)
    assert estimate.finite_upper == pytest.approx(3.0)
    assert estimate.repeated_lower < 3.0 < estimate.repeated_upper

    _, conservative = audit_corrected_h2_with_conservative_interval(
        failure,
        predicted_de,
        human_de_full,
        sample,
        windows,
        linux,
    )
    assert conservative.lower_estimable
    assert conservative.finite_upper
    assert conservative.uncertain_components == 0
    assert conservative.q_windows_lower == pytest.approx(0.30)
    assert conservative.q_windows_upper == pytest.approx(0.30)
    assert conservative.q_linux_lower == pytest.approx(0.10)
    assert conservative.q_linux_upper == pytest.approx(0.10)
    assert conservative.rr_lower == pytest.approx(3.0)
    assert conservative.rr_upper == pytest.approx(3.0)


def test_hypergeometric_bounds_have_exact_finite_population_coverage() -> None:
    confidence = 0.95
    for population_size, sample_size in (
        (1, 0),
        (1, 1),
        (6, 2),
        (8, 4),
        (12, 5),
        (12, 11),
    ):
        for true_successes in range(population_size + 1):
            minimum_observed = max(
                0,
                sample_size - (population_size - true_successes),
            )
            maximum_observed = min(sample_size, true_successes)
            miss_probability = 0.0
            for observed in range(minimum_observed, maximum_observed + 1):
                lower, upper = hypergeometric_success_bounds(
                    population_size,
                    sample_size,
                    observed,
                    confidence=confidence,
                )
                if not lower <= true_successes <= upper:
                    miss_probability += float(
                        hypergeom.pmf(
                            observed,
                            population_size,
                            true_successes,
                            sample_size,
                        )
                    )
            assert miss_probability <= 1.0 - confidence + 1e-12


def test_hypergeometric_bounds_protect_zero_cells_and_fail_closed() -> None:
    lower, upper = hypergeometric_success_bounds(
        100,
        10,
        0,
        confidence=0.95,
    )
    assert lower == 0
    assert 0 < upper < 100
    assert hypergeometric_success_bounds(
        10,
        10,
        0,
        confidence=0.95,
    ) == (0, 0)
    with pytest.raises(ValueError, match="integers"):
        hypergeometric_success_bounds(10, 5, True, confidence=0.95)
    with pytest.raises(ValueError, match="invalid"):
        hypergeometric_success_bounds(10, 11, 0, confidence=0.95)


def test_difference_estimator_matches_stratified_variance_oracle() -> None:
    failure = np.ones(24, dtype=bool)
    windows = np.zeros(24, dtype=bool)
    windows[:12] = True
    linux = ~windows
    sample = AuditSample(
        indices=np.asarray([0, 1, 2, 3, 12, 13, 14, 15]),
        inclusion_probability=np.full(8, 1 / 3),
        population_stratum=np.asarray([0] * 12 + [1] * 12),
        population_counts=np.asarray([12, 12]),
        allocation=np.asarray([4, 4]),
    )
    estimate = audit_corrected_h2_reference(
        failure,
        np.zeros(24, dtype=bool),
        np.asarray([True, False, True, False, True, False, False, False]),
        sample,
        windows,
        linux,
    )
    assert estimate.estimable
    assert estimate.q_windows == pytest.approx(0.5)
    assert estimate.q_linux == pytest.approx(0.25)
    assert estimate.rr == pytest.approx(2.0)
    assert estimate.design_variance_windows == pytest.approx(1 / 18)
    assert estimate.design_variance_linux == pytest.approx(1 / 24)


def test_difference_estimator_is_design_unbiased_by_full_sample_enumeration() -> None:
    strata = np.asarray([0] * 4 + [1] * 3 + [2] * 5 + [3] * 4)
    counts = np.asarray([4, 3, 5, 4])
    allocation = np.asarray([2, 2, 2, 2])
    windows = strata < 2
    linux = ~windows
    failure = np.ones(strata.size, dtype=bool)
    predicted = np.asarray(
        [True, False, False, False, True, False, False,
         False, True, False, False, False, False, False, True, False]
    )
    human = np.asarray(
        [True, True, False, False, True, False, True,
         False, True, True, False, False, True, False, True, False]
    )
    choices = [
        tuple(combinations(np.flatnonzero(strata == stratum), sample_size))
        for stratum, sample_size in enumerate(allocation)
    ]
    q_linux: list[float] = []
    q_windows: list[float] = []
    variance_linux: list[float] = []
    variance_windows: list[float] = []
    conservative_coverage: list[bool] = []
    true_rr = float(np.mean(human[windows]) / np.mean(human[linux]))
    for selected_parts in product(*choices):
        indices = np.concatenate(selected_parts)
        pi = allocation[strata[indices]] / counts[strata[indices]]
        estimate, conservative = audit_corrected_h2_with_conservative_interval(
            failure,
            predicted,
            human[indices],
            AuditSample(indices, pi, strata, counts, allocation),
            windows,
            linux,
            minimum_failures=1,
        )
        q_linux.append(estimate.q_linux)
        q_windows.append(estimate.q_windows)
        variance_linux.append(estimate.design_variance_linux)
        variance_windows.append(estimate.design_variance_windows)
        conservative_coverage.append(
            conservative.rr_lower <= true_rr <= conservative.rr_upper
        )

    assert np.mean(q_linux) == pytest.approx(np.mean(human[linux]))
    assert np.mean(q_windows) == pytest.approx(np.mean(human[windows]))
    assert np.mean(variance_linux) == pytest.approx(np.var(q_linux, ddof=0))
    assert np.mean(variance_windows) == pytest.approx(np.var(q_windows, ddof=0))
    assert np.mean(conservative_coverage) >= 0.95


def test_difference_estimator_rejects_inconsistent_sample_metadata() -> None:
    failure = np.ones(8, dtype=bool)
    windows = np.asarray([True] * 4 + [False] * 4)
    linux = ~windows
    predicted = np.zeros(8, dtype=bool)
    indices = np.asarray([0, 1, 4, 5])
    human = np.asarray([True, False, True, False])
    valid = AuditSample(
        indices,
        np.full(4, 0.5),
        np.asarray([0] * 4 + [1] * 4),
        np.asarray([4, 4]),
        np.asarray([2, 2]),
    )
    audit_corrected_h2_reference(
        failure,
        predicted,
        human,
        valid,
        windows,
        linux,
        minimum_failures=1,
    )

    bad_counts = AuditSample(
        indices,
        np.full(4, 0.5),
        valid.population_stratum,
        np.asarray([5, 3]),
        valid.allocation,
    )
    with pytest.raises(ValueError, match="counts or allocation"):
        audit_corrected_h2_reference(
            failure,
            predicted,
            human,
            bad_counts,
            windows,
            linux,
            minimum_failures=1,
        )

    cross_context = AuditSample(
        np.asarray([0, 2, 4, 6]),
        np.full(4, 0.5),
        np.asarray([0, 0, 1, 1, 0, 0, 1, 1]),
        np.asarray([4, 4]),
        np.asarray([2, 2]),
    )
    with pytest.raises(ValueError, match="exactly one context"):
        audit_corrected_h2_reference(
            failure,
            predicted,
            human,
            cross_context,
            windows,
            linux,
            minimum_failures=1,
        )


def test_weighted_binary_performance_matches_manual_counts() -> None:
    sensitivity, specificity = weighted_binary_performance(
        np.asarray([True, False, True, False]),
        np.asarray([True, True, False, False]),
        np.asarray([0.5, 0.5, 0.5, 0.5]),
    )
    assert sensitivity == pytest.approx(0.5)
    assert specificity == pytest.approx(0.5)


def test_noisy_human_scenario_target_matches_four_class_error_rule() -> None:
    assert _scenario_human_reference_rate(0.10, 1.0) == pytest.approx(0.10)
    assert _scenario_human_reference_rate(0.10, 0.98) == pytest.approx(
        0.11066666666666669
    )
    assert _scenario_human_reference_rate(0.30, 0.98) == pytest.approx(
        0.30533333333333335
    )


def test_enriched_simulation_is_reproducible_and_separates_human_modes() -> None:
    kwargs = {
        "base_common_n": 6,
        "replicates": 20,
        "seed": 302,
        "budgets": (50,),
        "designs": (AuditDesign("context", None),),
        "human_modes": (
            AuditHumanMode("perfect_reference", 1.0),
            AuditHumanMode("noisy_98_reference", 0.98),
        ),
        "batch_size": 5,
    }
    first = simulate_enriched_audit_scenario(_scenario("high_quality_strong"), **kwargs)
    second = simulate_enriched_audit_scenario(_scenario("high_quality_strong"), **kwargs)
    assert first == second
    assert len(first) == 2
    rows = {row["audit_human_mode"]: row for row in first}
    assert rows["perfect_reference"]["mean_audit_human_binary_accuracy"] == 1.0
    assert rows["perfect_reference"]["scenario_human_reference_rr"] == pytest.approx(
        rows["perfect_reference"]["true_conditional_de_rr"]
    )
    assert rows["noisy_98_reference"]["scenario_human_reference_rr"] < float(
        rows["noisy_98_reference"]["true_conditional_de_rr"]
    )
    assert 0.90 < float(
        rows["noisy_98_reference"]["mean_audit_human_binary_accuracy"]
    ) < 1.0
    for row in first:
        assert row["mean_actual_audit_size"] == 50.0
        assert row["mean_conservative_total_human_labels"] == 100.0
        assert float(row["audit_joint_confirmatory_support_probability"]) <= float(
            row["audit_pooled_support_probability"]
        )
        assert row["analysis_note"] == (
            "two_phase_difference_pooled_reference_not_D005_mixed_model"
        )
        for field in (
            "audit_estimator_estimable_probability",
            "full_human_reference_estimable_probability",
            "full_human_d005_multiway_estimable_probability",
            "audit_d005_multiway_estimable_probability",
            "full_human_d005_finite_roster_estimable_probability",
            "audit_d005_finite_roster_estimable_probability",
            "naive_coder1_estimable_probability",
            "latent_oracle_estimable_probability",
        ):
            assert 0.0 <= float(row[field]) <= 1.0
        assert float(
            row["d005_multiway_exact_audit_irr_coupled_support_probability"]
        ) <= float(row["audit_d005_multiway_support_probability"])
        assert float(
            row["d005_multiway_exact_audit_irr_coupled_support_probability"]
        ) <= float(row["bonferroni_hypergeom_ratio_above_2_probability"])
        assert row["d005_multiway_candidate_note"] == (
            "task_configuration_sandwich_t6_not_registered_GLMM_"
            "requires_coverage_acceptance"
        )
        assert float(
            row[
                "d005_finite_roster_exact_audit_irr_coupled_support_probability"
            ]
        ) <= float(row["audit_d005_finite_roster_support_probability"])
        assert row["d005_finite_roster_candidate_note"] == (
            "falsified_cellwise_jeffreys_delta_"
            "retained_as_negative_comparator"
        )
        assert float(
            row[
                "d005_pooled_finite_roster_exact_audit_irr_coupled_support_probability"
            ]
        ) <= float(row["audit_pooled_support_probability"])
        assert row["d005_pooled_finite_roster_candidate_note"] == (
            "two_phase_pooled_normal_fixed_roster_candidate_"
            "independent_trials_requires_coverage_acceptance"
        )
        assert "scenario_human_reference_coverage_given_estimable" in row
        assert "scenario_latent_coverage_diagnostic_given_estimable" in row
        assert 0.0 <= float(
            row["bonferroni_hypergeom_lower_estimable_probability"]
        ) <= 1.0
        assert 0.0 <= float(
            row[
                "bonferroni_hypergeom_finite_human_coverage_given_lower_estimable"
            ]
        ) <= 1.0
        assert row["bonferroni_hypergeom_analysis_note"] == (
            "finite_human_reference_audit_only_not_D005_model"
        )


def test_enriched_cells_are_invariant_to_batching_and_grid_composition() -> None:
    scenario = _scenario("shared_de_to_c_boundary")
    designs = default_audit_designs()[:2]
    modes = (
        AuditHumanMode("perfect_reference", 1.0),
        AuditHumanMode("noisy_98_reference", 0.98),
    )
    common = {
        "base_common_n": 6,
        "replicates": 20,
        "seed": 306,
    }
    full = simulate_enriched_audit_scenario(
        scenario,
        budgets=(50, 100),
        designs=designs,
        human_modes=modes,
        batch_size=5,
        **common,
    )
    different_batch = simulate_enriched_audit_scenario(
        scenario,
        budgets=(50, 100),
        designs=designs,
        human_modes=modes,
        batch_size=20,
        **common,
    )
    assert full == different_batch

    target = next(
        row
        for row in full
        if row["audit_design"] == designs[0].name
        and row["audit_budget_requested"] == 50
        and row["audit_human_mode"] == modes[1].name
    )
    subset = simulate_enriched_audit_scenario(
        scenario,
        budgets=(50,),
        designs=(designs[0],),
        human_modes=(modes[1],),
        batch_size=7,
        **common,
    )
    assert subset == [target]


def test_boundary_joint_support_is_classified_as_false_support() -> None:
    row = simulate_enriched_audit_scenario(
        _scenario("high_quality_boundary"),
        base_common_n=6,
        replicates=30,
        seed=303,
        budgets=(50,),
        designs=(default_audit_designs()[0],),
        human_modes=(AuditHumanMode("perfect_reference", 1.0),),
        batch_size=10,
    )[0]
    assert float(row["true_conditional_de_rr"]) == pytest.approx(2.0)
    assert row["audit_joint_false_support_probability"] == row[
        "audit_joint_confirmatory_support_probability"
    ]
    assert row[
        "bonferroni_hypergeom_latent_null_threshold_clear_diagnostic_probability"
    ] == row["bonferroni_hypergeom_gate_and_ratio_above_2_probability"]
    assert row[
        "d005_multiway_exact_audit_irr_coupled_latent_null_diagnostic_probability"
    ] == row["d005_multiway_exact_audit_irr_coupled_support_probability"]
    assert row[
        "d005_finite_roster_exact_audit_irr_coupled_latent_null_diagnostic_probability"
    ] == row[
        "d005_finite_roster_exact_audit_irr_coupled_support_probability"
    ]
    assert row[
        "d005_pooled_finite_roster_exact_audit_irr_coupled_latent_null_diagnostic_probability"
    ] == row[
        "d005_pooled_finite_roster_exact_audit_irr_coupled_support_probability"
    ]


def test_shared_bias_boundary_is_also_classified_as_false_support() -> None:
    row = simulate_enriched_audit_scenario(
        _scenario("shared_de_to_c_boundary"),
        base_common_n=6,
        replicates=10,
        seed=307,
        budgets=(50,),
        designs=(default_audit_designs()[0],),
        human_modes=(AuditHumanMode("perfect_reference", 1.0),),
        batch_size=4,
    )[0]
    assert float(row["true_conditional_de_rr"]) == pytest.approx(2.0)
    assert row["audit_joint_false_support_probability"] == row[
        "audit_joint_confirmatory_support_probability"
    ]
    assert row[
        "bonferroni_hypergeom_latent_null_threshold_clear_diagnostic_probability"
    ] == row["bonferroni_hypergeom_gate_and_ratio_above_2_probability"]
    assert row[
        "d005_multiway_exact_audit_irr_coupled_latent_null_diagnostic_probability"
    ] == row["d005_multiway_exact_audit_irr_coupled_support_probability"]
    assert row[
        "d005_finite_roster_exact_audit_irr_coupled_latent_null_diagnostic_probability"
    ] == row[
        "d005_finite_roster_exact_audit_irr_coupled_support_probability"
    ]
    assert row[
        "d005_pooled_finite_roster_exact_audit_irr_coupled_latent_null_diagnostic_probability"
    ] == row[
        "d005_pooled_finite_roster_exact_audit_irr_coupled_support_probability"
    ]


def test_invalid_simulation_grid_fails_closed() -> None:
    with pytest.raises(ValueError, match="unique"):
        simulate_enriched_audit_scenario(
            _scenario("high_quality_strong"),
            base_common_n=6,
            replicates=1,
            seed=304,
            budgets=(50, 50),
        )
    with pytest.raises(ValueError, match="five positive"):
        AuditDesign("bad", (1.0, 1.0))
    with pytest.raises(ValueError, match="design names"):
        simulate_enriched_audit_scenario(
            _scenario("high_quality_strong"),
            base_common_n=6,
            replicates=1,
            seed=305,
            budgets=(50,),
            designs=(AuditDesign("same", None), AuditDesign("same", None)),
        )
    assert math.isfinite(float(default_audit_designs()[0].stratum_weights[0]))


def test_grid_filters_human_modes_without_changing_scenario_seed() -> None:
    perfect = AuditHumanMode("perfect_reference", 1.0)
    rows = run_enriched_audit_grid(
        replicates=2,
        seed=401,
        base_common_ns=(6,),
        budgets=(50,),
        scenario_names=("high_quality_strong",),
        human_modes=(perfect,),
    )
    assert len(rows) == len(default_audit_designs())
    assert {row["audit_human_mode"] for row in rows} == {perfect.name}
    assert {row["seed"] for row in rows} == {300_401}
    with pytest.raises(ValueError, match="known scenarios"):
        run_enriched_audit_grid(
            replicates=1,
            seed=401,
            base_common_ns=(6,),
            budgets=(50,),
            scenario_names=("unknown",),
            human_modes=(perfect,),
        )
