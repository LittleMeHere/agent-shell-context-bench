from __future__ import annotations

import math
from dataclasses import replace
from statistics import NormalDist

import numpy as np
import pytest

from analysis.d010_joint_h2_measurement import (
    DEFAULT_ANCHOR_SIZE,
    N_ANCHOR_STRATA,
    PRIMARY_RULES,
    build_joint_manifest,
    default_joint_scenarios,
    draw_outcome_constrained_labels,
    pooled_h2_log_wald_reference,
    primary_de_labels,
    sample_registered_anchor_indices,
    simulate_joint_scenario,
)


def _scenario(name: str):
    return next(item for item in default_joint_scenarios() if item.name == name)


@pytest.mark.parametrize(
    ("base_n", "n_cap", "full_size"),
    ((6, 3, 5_040), (12, 5, 9_660), (24, 10, 19_320)),
)
def test_joint_manifest_matches_exact_broad_split_costs(
    base_n: int,
    n_cap: int,
    full_size: int,
) -> None:
    manifest = build_joint_manifest(
        _scenario("high_quality_strong").h2,
        base_common_n=base_n,
    )
    assert manifest.n_cap == n_cap
    assert manifest.n_seed == base_n
    assert manifest.size == full_size
    assert np.unique(manifest.stratum).tolist() == list(range(N_ANCHOR_STRATA))
    counts = np.bincount(manifest.stratum, minlength=N_ANCHOR_STRATA)
    assert counts[0::2] == pytest.approx(7 * 12 * n_cap)
    assert counts[1::2] == pytest.approx(7 * 18 * base_n)


def test_joint_manifest_preserves_instances_slots_tasks_and_phrasings() -> None:
    manifest = build_joint_manifest(
        _scenario("high_quality_strong").h2,
        base_common_n=12,
    )
    reference = manifest.environment == 0
    for environment in range(1, 5):
        comparison = manifest.environment == environment
        for field in (
            "task_class",
            "task",
            "task_variant",
            "family",
            "instance",
            "phrasing",
            "valid_slot",
            "configuration",
        ):
            assert np.array_equal(
                getattr(manifest, field)[reference],
                getattr(manifest, field)[comparison],
            )

    capability = reference & (manifest.task_class == 0)
    assert np.unique(manifest.task[capability]).tolist() == list(range(12))
    assert np.all(manifest.task[capability] == manifest.family[capability])
    assert np.all(manifest.phrasing[capability] == -1)
    for family in range(12):
        for configuration in range(7):
            cell = (
                capability
                & (manifest.family == family)
                & (manifest.configuration == configuration)
            )
            assert int(np.sum(cell)) == manifest.n_cap
            assert np.unique(manifest.instance[cell]).tolist() == [0, 1, 2]
            assert np.unique(manifest.valid_slot[cell]).tolist() == list(
                range(manifest.n_cap)
            )

    seeded = reference & (manifest.task_class == 1)
    assert np.unique(manifest.task[seeded]).tolist() == list(range(12, 21))
    assert np.all(manifest.family[seeded] == -1)
    assert np.all(manifest.instance[seeded] == -1)
    for task in range(12, 21):
        task_rows = seeded & (manifest.task == task)
        assert np.unique(manifest.phrasing[task_rows]).tolist() == [0, 1]
        for phrasing in (0, 1):
            for configuration in range(7):
                cell = (
                    task_rows
                    & (manifest.phrasing == phrasing)
                    & (manifest.configuration == configuration)
                )
                assert int(np.sum(cell)) == manifest.n_seed
                assert np.unique(manifest.valid_slot[cell]).tolist() == list(
                    range(manifest.n_seed)
                )


def test_registered_anchor_has_floor_unique_draws_and_exact_remainder() -> None:
    manifest = build_joint_manifest(
        _scenario("high_quality_strong").h2,
        base_common_n=6,
    )
    selected = sample_registered_anchor_indices(
        np.random.default_rng(91),
        manifest.stratum,
    )
    assert selected.size == DEFAULT_ANCHOR_SIZE
    assert np.unique(selected).size == DEFAULT_ANCHOR_SIZE
    counts = np.bincount(manifest.stratum[selected], minlength=N_ANCHOR_STRATA)
    assert np.all(counts >= 4)
    assert int(np.sum(counts - 4)) == 10


def test_anchor_remainder_tracks_unequal_stratum_sizes() -> None:
    manifest = build_joint_manifest(
        _scenario("high_quality_strong").h2,
        base_common_n=6,
    )
    rng = np.random.default_rng(92)
    seeded_extras = []
    for _ in range(2_000):
        selected = sample_registered_anchor_indices(rng, manifest.stratum)
        counts = np.bincount(
            manifest.stratum[selected],
            minlength=N_ANCHOR_STRATA,
        )
        seeded_extras.append(int(np.sum(counts[1::2] - 4)))
    # After the 4-per-stratum floor, seeded-error strata contain about 75% of
    # remaining trials at base N=6, so they should receive about 7.5/10 extras.
    assert 7.2 <= float(np.mean(seeded_extras)) <= 7.8


def test_outcome_constrained_labels_never_cross_binary_outcome() -> None:
    truth = np.asarray(
        [[0, 1, 2, 3, 4, 2, 3, 4, 5]] * 100,
        dtype=np.int64,
    )
    failure = np.asarray(
        [[False] * 5 + [True] * 4] * 100,
        dtype=bool,
    )
    labels = draw_outcome_constrained_labels(
        np.random.default_rng(93),
        truth,
        failure,
        accuracy=0.0,
    )
    assert np.all(labels[~failure] < 5)
    assert np.all(labels[failure] >= 2)
    assert np.all(labels != truth)

    with pytest.raises(ValueError, match="contradict"):
        draw_outcome_constrained_labels(
            np.random.default_rng(930),
            np.asarray([5]),
            np.asarray([False]),
            accuracy=1.0,
        )
    with pytest.raises(ValueError, match="contradict"):
        draw_outcome_constrained_labels(
            np.random.default_rng(931),
            np.asarray([1]),
            np.asarray([True]),
            accuracy=1.0,
        )


def test_primary_label_rules_resolve_expected_de_indicators() -> None:
    coder1 = np.asarray([0, 3, 3, 2, 4, 5])
    coder2 = np.asarray([0, 3, 2, 4, 2, 5])
    adjudicator = np.asarray([1, 2, 4, 3, 4, 2])
    labels = primary_de_labels(coder1, coder2, adjudicator)
    assert tuple(labels) == PRIMARY_RULES
    assert labels["coder1"].tolist() == [False, True, True, False, True, False]
    assert labels["consensus_then_adjudicator"].tolist() == [
        False,
        True,
        True,
        True,
        True,
        False,
    ]
    assert labels["both_ai_de"].tolist() == [False, True, False, False, False, False]
    assert labels["either_ai_de"].tolist() == [False, True, True, True, True, False]


def test_pooled_h2_log_wald_matches_hand_calculated_oracle() -> None:
    windows = np.zeros(2_000, dtype=bool)
    windows[:1_000] = True
    linux = ~windows
    failure = np.ones((3, 2_000), dtype=bool)
    failure[2] = False
    failure[2, :9] = True
    failure[2, 1_000:1_009] = True
    predicted_de = np.zeros_like(failure)
    predicted_de[0, :300] = True
    predicted_de[0, 1_000:1_100] = True
    predicted_de[1, :200] = True
    predicted_de[1, 1_000:1_100] = True
    predicted_de[2, :3] = True
    predicted_de[2, 1_000:1_003] = True

    estimable, observed_rr, lower = pooled_h2_log_wald_reference(
        failure,
        predicted_de,
        windows,
        linux,
    )
    variance = 1 / 300 - 1 / 1_000 + 1 / 100 - 1 / 1_000
    expected_lower = math.exp(
        math.log(3.0)
        - NormalDist().inv_cdf(0.975) * math.sqrt(variance)
    )
    assert estimable.tolist() == [True, True, False]
    assert observed_rr[0] == pytest.approx(3.0)
    assert lower[0] == pytest.approx(expected_lower)
    assert observed_rr[1] == pytest.approx(2.0)
    assert (lower > 2.0).tolist() == [True, False, False]


def test_custom_shared_bias_map_must_preserve_outcome_constraints() -> None:
    scenario = _scenario("high_quality_strong")
    with pytest.raises(ValueError, match="integers"):
        replace(scenario, shared_bias_map=(0.0, 1, 2, 2, 2, 5))
    with pytest.raises(ValueError, match="outcome-compatible"):
        replace(scenario, shared_bias_map=(0, 1, 2, 0, 2, 5))


def test_joint_simulation_is_reproducible_and_gate_cases_are_exclusive() -> None:
    kwargs = {
        "base_common_n": 6,
        "replicates": 100,
        "seed": 94,
        "batch_size": 20,
    }
    first = simulate_joint_scenario(_scenario("high_quality_strong"), **kwargs)
    second = simulate_joint_scenario(_scenario("high_quality_strong"), **kwargs)
    assert first == second
    assert {row["primary_rule"] for row in first} == set(PRIMARY_RULES)
    for row in first:
        assert row["full_sample_size"] == 5_040
        assert sum(
            float(row[key])
            for key in (
                "irr_confirmatory_probability",
                "irr_case_b_probability",
                "irr_case_c_probability",
            )
        ) == pytest.approx(1.0)
        assert float(row["joint_confirmatory_support_probability"]) <= float(
            row["pooled_reference_support_probability"]
        )
        assert float(row["mean_anchor_true_de_trials"]) == pytest.approx(
            float(row["mean_anchor_failed_true_de_trials"])
            + float(row["mean_anchor_success_true_de_trials"])
        )
        assert float(row["mean_anchor_success_true_de_trials"]) > 0.0


@pytest.mark.parametrize("base_n", (6, 12, 24))
def test_boundary_support_is_classified_as_false_support(base_n: int) -> None:
    rows = simulate_joint_scenario(
        _scenario("high_quality_boundary"),
        base_common_n=base_n,
        replicates=100,
        seed=941,
        batch_size=20,
    )
    for row in rows:
        assert float(row["true_conditional_de_rr"]) == pytest.approx(2.0)
        assert row["joint_false_support_probability"] == row[
            "joint_confirmatory_support_probability"
        ]


def test_joint_high_quality_coder1_attenuates_strong_ratio() -> None:
    rows = simulate_joint_scenario(
        _scenario("high_quality_strong"),
        base_common_n=6,
        replicates=500,
        seed=95,
        batch_size=50,
    )
    coder1 = next(row for row in rows if row["primary_rule"] == "coder1")
    assert coder1["true_conditional_de_rr"] == pytest.approx(3.0)
    assert float(coder1["mean_observed_rr_estimable"]) < 3.0
    assert float(coder1["mean_de_sensitivity"]) > 0.90
    assert float(coder1["mean_de_false_positive_rate"]) > 0.0


def test_invalid_anchor_and_primary_labels_fail_closed() -> None:
    with pytest.raises(ValueError, match="exact ten"):
        sample_registered_anchor_indices(
            np.random.default_rng(96),
            np.repeat(np.arange(9), 20),
        )
    with pytest.raises(ValueError, match="valid category"):
        primary_de_labels(
            np.asarray([0, 6]),
            np.asarray([0, 1]),
            np.asarray([0, 1]),
        )
