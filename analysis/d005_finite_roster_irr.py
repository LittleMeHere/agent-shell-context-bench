"""Prospective operating-characteristic audit for D-005 and the H2 IRR gate.

This module does not approve a confirmatory model or a primary rubric label.
It evaluates transparent finite-roster interval candidates on the exact
12-family x 3-instance x 7-configuration design, then simulates the registered
six-category kappa demotion rule under independent and correlated rater error.

The frequentist crossed-random-effect Family A remains outside this module:
the intended R implementations are not available in the current toolchain.
The estimators below are deliberately labelled analytic Family B candidates,
not substitutes silently presented as the registered GLMM.
"""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass
from statistics import NormalDist
from typing import Iterable, Sequence

import numpy as np
from numpy.typing import NDArray
from scipy.stats import t as student_t

from analysis.d013_ceiling_operating_characteristics import (
    CONFIDENCE,
    DECISION_RD,
    FAMILIES_PER_DOMAIN,
    INSTANCES_PER_FAMILY,
    N_CONFIGURATIONS,
    N_DOMAINS,
    N_SEEDED_VARIANTS,
    ConfirmScenario,
    H2Scenario,
    broad_instance_counts,
    confirmatory_probabilities,
    default_confirm_scenarios,
    simulate_h2_design,
)


N_CELLS = (
    N_DOMAINS * FAMILIES_PER_DOMAIN * INSTANCES_PER_FAMILY * N_CONFIGURATIONS
)
N_RUBRIC_CATEGORIES = 6
N_IRR_STRATA = 10
KAPPA_THRESHOLD = 0.60
DE_CATEGORIES = (3, 4)


@dataclass(frozen=True)
class IRRScenario:
    """One synthetic six-category rater-error mechanism.

    Each rater first makes an independent symmetric error. On rubric classes
    affected by ``shared_bias_map``, ``shared_bias_probability`` can then make
    both AI raters emit the same systematically wrong class. This explicitly
    represents the failure mode in which AI-AI agreement is high because both
    coders share a bias.
    """

    name: str
    label_probabilities: tuple[float, ...]
    coder1_accuracy: float
    coder2_accuracy: float
    human_accuracy: float
    shared_bias_probability: float = 0.0
    shared_bias_map: tuple[int, ...] = (0, 1, 2, 2, 2, 5)

    def __post_init__(self) -> None:
        if len(self.label_probabilities) != N_RUBRIC_CATEGORIES:
            raise ValueError("label_probabilities must contain six values")
        if any(value <= 0.0 for value in self.label_probabilities):
            raise ValueError("all label probabilities must be positive")
        if not math.isclose(sum(self.label_probabilities), 1.0, abs_tol=1e-12):
            raise ValueError("label probabilities must sum to one")
        rates = (
            self.coder1_accuracy,
            self.coder2_accuracy,
            self.human_accuracy,
        )
        if any(not 0.0 <= value <= 1.0 for value in rates):
            raise ValueError("rater accuracies must lie in [0, 1]")
        if not 0.0 <= self.shared_bias_probability <= 1.0:
            raise ValueError("shared_bias_probability must lie in [0, 1]")
        if len(self.shared_bias_map) != N_RUBRIC_CATEGORIES:
            raise ValueError("shared_bias_map must contain six values")
        if any(
            value < 0 or value >= N_RUBRIC_CATEGORIES
            for value in self.shared_bias_map
        ):
            raise ValueError("shared bias labels must be valid category indices")


@dataclass(frozen=True)
class H2MultiwayClusterInterval:
    """One task-by-configuration sandwich interval for a marginal H2 RR.

    ``de_value`` may be a binary full-human label or an audit-corrected
    pseudo-outcome.  The latter is intentionally permitted to leave [0, 1]
    at the observation level; the resulting context means must themselves be
    valid probabilities or the interval fails closed.

    This is a transparent finite-roster candidate, not the registered GLMM.
    Seven configuration clusters also make its small-sample behavior an
    empirical question, so coverage must be simulated before use.
    """

    estimable: bool
    reason: str
    q_linux: float
    q_windows: float
    rr: float
    rr_lower: float
    rr_upper: float
    log_rr_standard_error: float
    variance: float
    degrees_of_freedom: int
    linux_failures: int
    windows_failures: int
    task_clusters: int
    configuration_clusters: int
    task_configuration_clusters: int


@dataclass(frozen=True)
class H2FiniteRosterDeltaInterval:
    """Jeffreys-stabilized fixed-cell delta interval for a marginal H2 RR."""

    estimable: bool
    reason: str
    q_linux: float
    q_windows: float
    rr: float
    rr_lower: float
    rr_upper: float
    log_rr_standard_error: float
    linux_failures: int
    windows_failures: int
    linux_cells: int
    windows_cells: int


def finite_roster_h2_log_rr_interval(
    failure: NDArray[np.bool_],
    de_value: NDArray[np.float64],
    windows_mask: NDArray[np.bool_],
    linux_mask: NDArray[np.bool_],
    task_variant: NDArray[np.int64],
    configuration: NDArray[np.int64],
    *,
    confidence: float = CONFIDENCE,
    minimum_failures_per_context: int = 10,
) -> H2FiniteRosterDeltaInterval:
    """Return a fixed-roster multinomial delta interval for H2.

    Every context-by-task-variant-by-configuration cell is treated as a fixed
    member of the registered roster.  Within a cell, the three mutually
    exclusive outcomes are success, failed non-D/E, and failed D/E.  A
    Dirichlet(1/2, 1/2, 1/2) plug-in stabilizes the cell probabilities used
    only for the variance calculation.  The reported point estimate remains
    the unsmoothed pooled conditional D/E ratio.

    The analytic variance includes randomness in both the D/E numerator and
    the failure denominator, including their covariance.  It does not treat
    tasks or configurations as random samples from wider populations and it
    assumes fresh trials are independent conditional on their fixed cells.
    Those assumptions are why this candidate must be reported beside the
    superpopulation-oriented multiway sensitivity rather than silently
    replacing the registered GLMM.
    """

    arrays = tuple(
        np.asarray(value)
        for value in (
            failure,
            de_value,
            windows_mask,
            linux_mask,
            task_variant,
            configuration,
        )
    )
    if any(array.ndim != 1 for array in arrays) or any(
        array.shape != arrays[0].shape for array in arrays[1:]
    ):
        raise ValueError("finite-roster H2 arrays must be aligned vectors")
    if arrays[0].size == 0:
        raise ValueError("finite-roster H2 arrays must not be empty")
    failure_array = arrays[0]
    de_array = arrays[1].astype(float, copy=False)
    windows_array = arrays[2]
    linux_array = arrays[3]
    task_array = arrays[4]
    configuration_array = arrays[5]
    for label, array in (
        ("failure", failure_array),
        ("windows_mask", windows_array),
        ("linux_mask", linux_array),
    ):
        if array.dtype != np.bool_:
            raise ValueError(f"{label} must be boolean")
    for label, array in (
        ("task_variant", task_array),
        ("configuration", configuration_array),
    ):
        if not np.issubdtype(array.dtype, np.integer) or np.any(array < 0):
            raise ValueError(f"{label} must contain nonnegative integers")
    if np.any(windows_array & linux_array):
        raise ValueError("Windows and Linux masks must be disjoint")
    if not np.any(windows_array) or not np.any(linux_array):
        raise ValueError("both focal contexts must be present")
    focal = windows_array | linux_array
    if np.any(~np.isfinite(de_array[focal])):
        raise ValueError("de_value must be finite in the focal contexts")
    if not 0.0 < confidence < 1.0:
        raise ValueError("confidence must lie strictly between zero and one")
    if (
        isinstance(minimum_failures_per_context, bool)
        or not isinstance(minimum_failures_per_context, int)
        or minimum_failures_per_context < 1
    ):
        raise ValueError("minimum_failures_per_context must be a positive integer")

    n_linux = int(np.sum(failure_array & linux_array))
    n_windows = int(np.sum(failure_array & windows_array))

    def cell_count(mask: NDArray[np.bool_]) -> int:
        return int(
            np.unique(
                np.column_stack(
                    (task_array[mask], configuration_array[mask])
                ),
                axis=0,
            ).shape[0]
        )

    linux_cells = cell_count(linux_array)
    windows_cells = cell_count(windows_array)

    def unestimable(reason: str) -> H2FiniteRosterDeltaInterval:
        return H2FiniteRosterDeltaInterval(
            estimable=False,
            reason=reason,
            q_linux=math.nan,
            q_windows=math.nan,
            rr=math.nan,
            rr_lower=math.nan,
            rr_upper=math.nan,
            log_rr_standard_error=math.nan,
            linux_failures=n_linux,
            windows_failures=n_windows,
            linux_cells=linux_cells,
            windows_cells=windows_cells,
        )

    if (
        n_linux < minimum_failures_per_context
        or n_windows < minimum_failures_per_context
    ):
        return unestimable("fewer_than_minimum_failures")

    q_linux = float(
        np.sum(de_array[failure_array & linux_array]) / n_linux
    )
    q_windows = float(
        np.sum(de_array[failure_array & windows_array]) / n_windows
    )
    if not 0.0 < q_linux < 1.0 or not 0.0 < q_windows < 1.0:
        return unestimable("boundary_or_out_of_bounds_context_mean")

    def log_q_variance(mask: NDArray[np.bool_]) -> float | None:
        cells = np.column_stack(
            (task_array[mask], configuration_array[mask])
        )
        _, inverse = np.unique(cells, axis=0, return_inverse=True)
        groups = int(np.max(inverse)) + 1
        scheduled = np.bincount(inverse, minlength=groups).astype(float)
        failed = np.bincount(
            inverse,
            weights=failure_array[mask].astype(float),
            minlength=groups,
        )
        failed_de = np.bincount(
            inverse,
            weights=(failure_array[mask] * de_array[mask]),
            minlength=groups,
        )
        denominator = scheduled + 1.5
        probability_failure = (failed + 1.0) / denominator
        probability_de = (failed_de + 0.5) / denominator
        if np.any(
            (probability_de <= 0.0)
            | (probability_failure <= probability_de)
            | (probability_failure >= 1.0)
        ):
            return None
        mean_failure = float(np.sum(scheduled * probability_failure))
        mean_de = float(np.sum(scheduled * probability_de))
        variance_failure = float(
            np.sum(
                scheduled
                * probability_failure
                * (1.0 - probability_failure)
            )
        )
        variance_de = float(
            np.sum(scheduled * probability_de * (1.0 - probability_de))
        )
        covariance = float(
            np.sum(
                scheduled * probability_de * (1.0 - probability_failure)
            )
        )
        value = (
            variance_de / mean_de**2
            + variance_failure / mean_failure**2
            - 2.0 * covariance / (mean_de * mean_failure)
        )
        return value if math.isfinite(value) and value > 0.0 else None

    linux_variance = log_q_variance(linux_array)
    windows_variance = log_q_variance(windows_array)
    if linux_variance is None or windows_variance is None:
        return unestimable("invalid_smoothed_cell_probabilities")
    variance = linux_variance + windows_variance
    standard_error = math.sqrt(variance)
    critical = NormalDist().inv_cdf(0.5 + confidence / 2.0)
    log_rr = math.log(q_windows / q_linux)
    return H2FiniteRosterDeltaInterval(
        estimable=True,
        reason="estimable",
        q_linux=q_linux,
        q_windows=q_windows,
        rr=math.exp(log_rr),
        rr_lower=math.exp(log_rr - critical * standard_error),
        rr_upper=math.exp(log_rr + critical * standard_error),
        log_rr_standard_error=standard_error,
        linux_failures=n_linux,
        windows_failures=n_windows,
        linux_cells=linux_cells,
        windows_cells=windows_cells,
    )


def multiway_cluster_h2_log_rr_interval(
    failure: NDArray[np.bool_],
    de_value: NDArray[np.float64],
    windows_mask: NDArray[np.bool_],
    linux_mask: NDArray[np.bool_],
    task: NDArray[np.int64],
    configuration: NDArray[np.int64],
    *,
    confidence: float = CONFIDENCE,
    minimum_failures_per_context: int = 10,
) -> H2MultiwayClusterInterval:
    """Return a two-way task/configuration sandwich interval for log RR.

    The point estimand is the pooled conditional D/E proportion among focal
    failures in each context.  Influence contributions for ``log(q_W/q_L)``
    are summed independently by task and configuration, with the
    task-by-configuration intersection subtracted (the standard two-way
    inclusion-exclusion construction).  A ``G/(G-1)`` correction is applied
    to each meat term and the critical value uses
    ``min(G_task, G_config)-1`` degrees of freedom.

    Trial outcomes are still conditional on the realized failure population;
    the method does not solve task-population validity, time drift, lineage,
    or human-reference error.  Nonpositive inclusion-exclusion variance and
    sparse/boundary estimates fail closed.
    """

    arrays = tuple(
        np.asarray(value)
        for value in (
            failure,
            de_value,
            windows_mask,
            linux_mask,
            task,
            configuration,
        )
    )
    if any(array.ndim != 1 for array in arrays) or any(
        array.shape != arrays[0].shape for array in arrays[1:]
    ):
        raise ValueError("H2 interval arrays must be one-dimensional and aligned")
    if arrays[0].size == 0:
        raise ValueError("H2 interval arrays must not be empty")
    failure_array = arrays[0]
    de_array = arrays[1].astype(float, copy=False)
    windows_array = arrays[2]
    linux_array = arrays[3]
    task_array = arrays[4]
    configuration_array = arrays[5]
    for label, array in (
        ("failure", failure_array),
        ("windows_mask", windows_array),
        ("linux_mask", linux_array),
    ):
        if array.dtype != np.bool_:
            raise ValueError(f"{label} must be boolean")
    for label, array in (("task", task_array), ("configuration", configuration_array)):
        if not np.issubdtype(array.dtype, np.integer) or np.any(array < 0):
            raise ValueError(f"{label} must contain nonnegative integers")
    if np.any(windows_array & linux_array):
        raise ValueError("Windows and Linux masks must be disjoint")
    focal = windows_array | linux_array
    if not np.any(windows_array) or not np.any(linux_array):
        raise ValueError("both focal contexts must be present")
    if np.any(~np.isfinite(de_array[focal])):
        raise ValueError("de_value must be finite in the focal contexts")
    if not 0.0 < confidence < 1.0:
        raise ValueError("confidence must lie strictly between zero and one")
    if (
        isinstance(minimum_failures_per_context, bool)
        or not isinstance(minimum_failures_per_context, int)
        or minimum_failures_per_context < 1
    ):
        raise ValueError("minimum_failures_per_context must be a positive integer")

    task_unique, task_inverse = np.unique(
        task_array[focal],
        return_inverse=True,
    )
    configuration_unique, configuration_inverse = np.unique(
        configuration_array[focal],
        return_inverse=True,
    )
    intersections = np.column_stack(
        (task_array[focal], configuration_array[focal])
    )
    intersection_unique, intersection_inverse = np.unique(
        intersections,
        axis=0,
        return_inverse=True,
    )
    n_task = int(task_unique.size)
    n_configuration = int(configuration_unique.size)
    n_intersection = int(intersection_unique.shape[0])

    linux_eligible = failure_array & linux_array
    windows_eligible = failure_array & windows_array
    n_linux = int(np.sum(linux_eligible))
    n_windows = int(np.sum(windows_eligible))

    def unestimable(reason: str) -> H2MultiwayClusterInterval:
        return H2MultiwayClusterInterval(
            estimable=False,
            reason=reason,
            q_linux=math.nan,
            q_windows=math.nan,
            rr=math.nan,
            rr_lower=math.nan,
            rr_upper=math.nan,
            log_rr_standard_error=math.nan,
            variance=math.nan,
            degrees_of_freedom=max(min(n_task, n_configuration) - 1, 0),
            linux_failures=n_linux,
            windows_failures=n_windows,
            task_clusters=n_task,
            configuration_clusters=n_configuration,
            task_configuration_clusters=n_intersection,
        )

    if (
        n_linux < minimum_failures_per_context
        or n_windows < minimum_failures_per_context
    ):
        return unestimable("fewer_than_minimum_failures")
    if n_task < 2 or n_configuration < 2 or n_intersection < 2:
        return unestimable("fewer_than_two_clusters")

    q_linux = float(np.sum(de_array[linux_eligible]) / n_linux)
    q_windows = float(np.sum(de_array[windows_eligible]) / n_windows)
    if not 0.0 < q_linux < 1.0 or not 0.0 < q_windows < 1.0:
        return unestimable("boundary_or_out_of_bounds_context_mean")

    influence = np.zeros(failure_array.size, dtype=float)
    influence[windows_eligible] = (
        de_array[windows_eligible] - q_windows
    ) / (n_windows * q_windows)
    influence[linux_eligible] = -(
        de_array[linux_eligible] - q_linux
    ) / (n_linux * q_linux)
    focal_influence = influence[focal]

    def corrected_meat(inverse: NDArray[np.int64], groups: int) -> float:
        sums = np.bincount(inverse, weights=focal_influence, minlength=groups)
        return groups / (groups - 1.0) * float(np.sum(sums**2))

    task_meat = corrected_meat(task_inverse, n_task)
    configuration_meat = corrected_meat(
        configuration_inverse,
        n_configuration,
    )
    intersection_meat = corrected_meat(
        intersection_inverse,
        n_intersection,
    )
    variance = task_meat + configuration_meat - intersection_meat
    if not math.isfinite(variance) or variance <= 0.0:
        return unestimable("nonpositive_two_way_cluster_variance")

    degrees_of_freedom = min(n_task, n_configuration) - 1
    critical = float(
        student_t.ppf(0.5 + confidence / 2.0, degrees_of_freedom)
    )
    standard_error = math.sqrt(variance)
    log_rr = math.log(q_windows / q_linux)
    return H2MultiwayClusterInterval(
        estimable=True,
        reason="estimable",
        q_linux=q_linux,
        q_windows=q_windows,
        rr=math.exp(log_rr),
        rr_lower=math.exp(log_rr - critical * standard_error),
        rr_upper=math.exp(log_rr + critical * standard_error),
        log_rr_standard_error=standard_error,
        variance=variance,
        degrees_of_freedom=degrees_of_freedom,
        linux_failures=n_linux,
        windows_failures=n_windows,
        task_clusters=n_task,
        configuration_clusters=n_configuration,
        task_configuration_clusters=n_intersection,
    )


def _finite_value(values: NDArray[np.float64]) -> float | None:
    finite = values[np.isfinite(values)]
    return float(np.mean(finite)) if finite.size else None


def _interval_summary(
    *,
    method: str,
    estimate: NDArray[np.float64],
    standard_error: NDArray[np.float64],
    true_rd: float,
    threshold: float,
    common: dict[str, float | int | str | None],
) -> dict[str, float | int | str | None]:
    z_value = NormalDist().inv_cdf(0.5 + CONFIDENCE / 2.0)
    lower = np.clip(estimate - z_value * standard_error, -1.0, 1.0)
    upper = np.clip(estimate + z_value * standard_error, -1.0, 1.0)
    estimable = np.isfinite(lower) & np.isfinite(upper)
    covered = estimable & (lower <= true_rd) & (true_rd <= upper)
    above = estimable & (lower > threshold)
    below = estimable & (upper < threshold)
    inconclusive = estimable & ~above & ~below

    if true_rd < threshold:
        wrong = above
    elif true_rd > threshold:
        wrong = below
    else:
        wrong = above | below

    row = dict(common)
    row.update(
        {
            "record_type": "d005_finite_roster_interval",
            "interval_method": method,
            "true_rd": true_rd,
            "decision_threshold_rd": threshold,
            "estimable_probability": float(np.mean(estimable)),
            "coverage_unconditional": float(np.mean(covered)),
            "coverage_conditional_estimable": (
                float(np.mean(covered[estimable])) if np.any(estimable) else None
            ),
            "decision_relevant_probability": float(np.mean(above)),
            "bounded_small_probability": float(np.mean(below)),
            "inconclusive_probability": float(np.mean(inconclusive)),
            "wrong_threshold_declaration_probability": float(np.mean(wrong)),
            "mean_standard_error_estimable": _finite_value(standard_error),
            "zero_standard_error_probability": float(
                np.mean(estimable & (standard_error == 0.0))
            ),
        }
    )
    return row


def finite_roster_oracle_variance(
    linux_probability: NDArray[np.float64],
    windows_probability: NDArray[np.float64],
    counts: NDArray[np.int64],
) -> float:
    """Return the known-probability variance of the equal-cell-weighted RD."""

    linux_probability = np.asarray(linux_probability, dtype=float)
    windows_probability = np.asarray(windows_probability, dtype=float)
    counts = np.asarray(counts)
    if not (
        linux_probability.shape == windows_probability.shape == counts.shape
    ):
        raise ValueError("probabilities and counts must have identical shapes")
    if linux_probability.size == 0:
        raise ValueError("the finite roster must not be empty")
    if np.any((linux_probability < 0.0) | (linux_probability > 1.0)) or np.any(
        (windows_probability < 0.0) | (windows_probability > 1.0)
    ):
        raise ValueError("probabilities must lie in [0, 1]")
    if np.any(counts < 1) or not np.issubdtype(counts.dtype, np.integer):
        raise ValueError("counts must be positive integers")
    weight = 1.0 / counts.size
    return weight**2 * float(
        np.sum(
            windows_probability * (1.0 - windows_probability) / counts
            + linux_probability * (1.0 - linux_probability) / counts
        )
    )


def simulate_finite_roster_design(
    scenario: ConfirmScenario,
    *,
    design: str,
    repetitions_per_family_config: int,
    base_common_n: int,
    replicates: int,
    seed: int,
) -> list[dict[str, float | int | str | None]]:
    """Evaluate three analytic intervals on one exact candidate design.

    ``oracle_normal`` uses the known generating probabilities and is only a
    validation reference. ``jeffreys_plugin_normal`` stabilizes cell variance
    estimates with Beta(1/2, 1/2) pseudo-counts. ``unbiased_cell_normal`` uses
    the ordinary unbiased within-cell Bernoulli variance and is explicitly
    unestimable whenever any scheduled instance has only one observation.
    """

    if repetitions_per_family_config < INSTANCES_PER_FAMILY:
        raise ValueError("every candidate instance must be exercised")
    if replicates < 1:
        raise ValueError("replicates must be positive")

    linux_probability, windows_probability = confirmatory_probabilities(scenario)
    counts = broad_instance_counts(repetitions_per_family_config)
    if counts.shape != linux_probability.shape or counts.size != N_CELLS:
        raise RuntimeError("candidate schedule and probability roster disagree")

    rng = np.random.default_rng(seed)
    linux_count = rng.binomial(
        counts,
        linux_probability,
        size=(replicates, *counts.shape),
    )
    windows_count = rng.binomial(
        counts,
        windows_probability,
        size=(replicates, *counts.shape),
    )
    axes = tuple(range(1, linux_count.ndim))
    linux_rate = linux_count / counts
    windows_rate = windows_count / counts
    p_linux = np.mean(linux_rate, axis=axes)
    p_windows = np.mean(windows_rate, axis=axes)
    estimate = p_windows - p_linux
    true_linux = float(np.mean(linux_probability))
    true_windows = float(np.mean(windows_probability))
    true_rd = true_windows - true_linux
    true_rr = true_windows / true_linux
    point_rr = np.full(replicates, np.nan)
    rr_estimable = p_linux > 0.0
    point_rr[rr_estimable] = p_windows[rr_estimable] / p_linux[rr_estimable]
    any_boundary_cell = np.any(
        (linux_count == 0)
        | (linux_count == counts)
        | (windows_count == 0)
        | (windows_count == counts),
        axis=axes,
    )
    either_context_zero = (
        np.sum(linux_count, axis=axes) == 0
    ) | (np.sum(windows_count, axis=axes) == 0)
    trials_per_context = int(np.sum(counts))
    either_context_all = (
        np.sum(linux_count, axis=axes) == trials_per_context
    ) | (np.sum(windows_count, axis=axes) == trials_per_context)

    common: dict[str, float | int | str | None] = {
        "scenario": scenario.name,
        "design": design,
        "replicates": replicates,
        "seed": seed,
        "base_common_n": base_common_n,
        "repetitions_per_family_config": repetitions_per_family_config,
        "min_instance_n": int(np.min(counts)),
        "max_instance_n": int(np.max(counts)),
        "capability_trials_two_contexts": int(2 * np.sum(counts)),
        "confirmatory_trials_full_matrix": 35
        * (
            N_DOMAINS
            * FAMILIES_PER_DOMAIN
            * repetitions_per_family_config
            + N_SEEDED_VARIANTS * base_common_n
        ),
        "true_linux_rate": true_linux,
        "true_windows_rate": true_windows,
        "point_rd_bias": float(np.mean(estimate) - true_rd),
        "true_rr": true_rr,
        "point_rr_estimable_probability": float(np.mean(rr_estimable)),
        "point_rr_bias_conditional_estimable": _finite_value(point_rr - true_rr),
        "either_context_zero_event_probability": float(
            np.mean(either_context_zero)
        ),
        "either_context_all_event_probability": float(
            np.mean(either_context_all)
        ),
        "any_boundary_instance_cell_probability": float(
            np.mean(any_boundary_cell)
        ),
    }

    weight = 1.0 / counts.size
    oracle_variance = finite_roster_oracle_variance(
        linux_probability,
        windows_probability,
        counts,
    )
    oracle_se = np.full(replicates, math.sqrt(oracle_variance))

    linux_smooth = (linux_count + 0.5) / (counts + 1.0)
    windows_smooth = (windows_count + 0.5) / (counts + 1.0)
    jeffreys_variance = weight**2 * np.sum(
        windows_smooth * (1.0 - windows_smooth) / counts
        + linux_smooth * (1.0 - linux_smooth) / counts,
        axis=axes,
    )
    jeffreys_se = np.sqrt(jeffreys_variance)

    if int(np.min(counts)) < 2:
        unbiased_se = np.full(replicates, np.nan)
    else:
        unbiased_variance = weight**2 * np.sum(
            windows_rate * (1.0 - windows_rate) / (counts - 1)
            + linux_rate * (1.0 - linux_rate) / (counts - 1),
            axis=axes,
        )
        unbiased_se = np.sqrt(unbiased_variance)

    return [
        _interval_summary(
            method="oracle_normal_reference",
            estimate=estimate,
            standard_error=oracle_se,
            true_rd=true_rd,
            threshold=DECISION_RD,
            common=common,
        ),
        _interval_summary(
            method="jeffreys_plugin_normal_candidate",
            estimate=estimate,
            standard_error=jeffreys_se,
            true_rd=true_rd,
            threshold=DECISION_RD,
            common=common,
        ),
        _interval_summary(
            method="unbiased_cell_normal_candidate",
            estimate=estimate,
            standard_error=unbiased_se,
            true_rd=true_rd,
            threshold=DECISION_RD,
            common=common,
        ),
    ]


def default_finite_roster_scenarios() -> tuple[ConfirmScenario, ...]:
    """Return the D-013 scenarios plus explicit separation stress tests."""

    return default_confirm_scenarios() + (
        ConfirmScenario(
            "near_zero_null",
            (0.001,) * N_DOMAINS,
            (0.001,) * N_DOMAINS,
        ),
        ConfirmScenario(
            "near_one_null",
            (0.999,) * N_DOMAINS,
            (0.999,) * N_DOMAINS,
        ),
    )


def run_finite_roster_grid(
    *,
    replicates: int,
    seed: int,
    base_common_ns: Iterable[int] = (6, 12, 24),
) -> list[dict[str, float | int | str | None]]:
    rows: list[dict[str, float | int | str | None]] = []
    for scenario_index, scenario in enumerate(default_finite_roster_scenarios()):
        for n_index, base_n in enumerate(base_common_ns):
            split_n = math.ceil(5 * base_n / 12)
            for design_index, (design, n_cap) in enumerate(
                (
                    ("B_broad_common_n", base_n),
                    ("C_broad_split_n", split_n),
                )
            ):
                rows.extend(
                    simulate_finite_roster_design(
                        scenario,
                        design=design,
                        repetitions_per_family_config=n_cap,
                        base_common_n=base_n,
                        replicates=replicates,
                        seed=(
                            seed
                            + 10_000 * scenario_index
                            + 100 * n_index
                            + design_index
                        ),
                    )
                )
    return rows


def cohen_kappa(
    first: NDArray[np.int64],
    second: NDArray[np.int64],
    *,
    n_categories: int = N_RUBRIC_CATEGORIES,
) -> float:
    """Calculate unweighted Cohen's kappa for two one-dimensional label arrays."""

    first = np.asarray(first)
    second = np.asarray(second)
    if first.ndim != 1 or second.ndim != 1 or first.shape != second.shape:
        raise ValueError("label arrays must be one-dimensional and equally sized")
    if first.size == 0:
        raise ValueError("label arrays must not be empty")
    if n_categories < 2:
        raise ValueError("n_categories must be at least two")
    if np.any((first < 0) | (first >= n_categories)) or np.any(
        (second < 0) | (second >= n_categories)
    ):
        raise ValueError("labels must be valid category indices")
    return float(
        rowwise_cohen_kappa(first[None, :], second[None, :], n_categories)[0]
    )


def rowwise_cohen_kappa(
    first: NDArray[np.int64],
    second: NDArray[np.int64],
    n_categories: int,
) -> NDArray[np.float64]:
    observed = np.mean(first == second, axis=1)
    expected = np.zeros(first.shape[0], dtype=float)
    for category in range(n_categories):
        expected += np.mean(first == category, axis=1) * np.mean(
            second == category,
            axis=1,
        )
    result = np.full(first.shape[0], np.nan)
    valid = expected < 1.0
    result[valid] = (observed[valid] - expected[valid]) / (1.0 - expected[valid])
    return result


def draw_symmetric_labels(
    rng: np.random.Generator,
    truth: NDArray[np.int64],
    accuracy: float,
) -> NDArray[np.int64]:
    labels = truth.copy()
    wrong = rng.random(truth.shape) >= accuracy
    alternatives = rng.integers(0, N_RUBRIC_CATEGORIES - 1, size=truth.shape)
    replacement = alternatives + (alternatives >= truth)
    labels[wrong] = replacement[wrong]
    return labels


def default_irr_scenarios() -> tuple[IRRScenario, ...]:
    return (
        IRRScenario(
            "high_quality_balanced",
            (0.20, 0.20, 0.15, 0.15, 0.10, 0.20),
            0.94,
            0.93,
            0.98,
        ),
        IRRScenario(
            "near_ai_kappa_threshold",
            (0.20, 0.20, 0.15, 0.15, 0.10, 0.20),
            0.81,
            0.81,
            0.98,
        ),
        IRRScenario(
            "shared_de_to_c_bias",
            (0.14, 0.14, 0.12, 0.25, 0.15, 0.20),
            0.97,
            0.97,
            0.98,
            shared_bias_probability=0.85,
        ),
        IRRScenario(
            "rare_de_high_overall_accuracy",
            (0.35, 0.25, 0.18, 0.015, 0.005, 0.20),
            0.94,
            0.93,
            0.98,
        ),
    )


def simulate_irr_scenario(
    scenario: IRRScenario,
    *,
    replicates: int,
    seed: int,
    full_sample_size: int = 5_040,
    human_anchor_size: int = 50,
    batch_size: int = 128,
) -> dict[str, float | int | str | None]:
    """Simulate the registered six-category kappa gate and D/E distortion.

    The full sample is represented as ten equal-sized environment x task-class
    strata. The human anchor takes an equal number from every stratum; at the
    registered minimum of 50 this is five per stratum. Real unequal stratum
    sizes and the proportional remainder require a separate manifest-level
    simulation once collection counts are fixed.
    """

    if replicates < 1:
        raise ValueError("replicates must be positive")
    if full_sample_size < human_anchor_size:
        raise ValueError("full sample cannot be smaller than the human anchor")
    if full_sample_size % N_IRR_STRATA != 0:
        raise ValueError("full sample must divide evenly across ten strata")
    if human_anchor_size % N_IRR_STRATA != 0:
        raise ValueError("human anchor must divide evenly across ten strata")
    if batch_size < 1:
        raise ValueError("batch_size must be positive")

    per_full_stratum = full_sample_size // N_IRR_STRATA
    per_anchor_stratum = human_anchor_size // N_IRR_STRATA
    anchor_indices = np.concatenate(
        [
            np.arange(
                stratum * per_full_stratum,
                stratum * per_full_stratum + per_anchor_stratum,
            )
            for stratum in range(N_IRR_STRATA)
        ]
    )
    rng = np.random.default_rng(seed)
    shared_map = np.asarray(scenario.shared_bias_map, dtype=np.int64)
    accumulators: dict[str, list[NDArray[np.float64]]] = {
        key: []
        for key in (
            "kappa_ai",
            "kappa_human_1",
            "kappa_human_2",
            "kappa_de_ai",
            "kappa_de_human_1",
            "kappa_de_human_2",
            "sensitivity",
            "false_positive_rate",
        )
    }

    remaining = replicates
    probabilities = np.asarray(scenario.label_probabilities)
    while remaining:
        current = min(batch_size, remaining)
        truth = rng.choice(
            N_RUBRIC_CATEGORIES,
            size=(current, full_sample_size),
            p=probabilities,
        )
        coder1 = draw_symmetric_labels(rng, truth, scenario.coder1_accuracy)
        coder2 = draw_symmetric_labels(rng, truth, scenario.coder2_accuracy)
        affected = shared_map[truth] != truth
        shared = affected & (
            rng.random(truth.shape) < scenario.shared_bias_probability
        )
        coder1[shared] = shared_map[truth[shared]]
        coder2[shared] = shared_map[truth[shared]]

        anchor_truth = truth[:, anchor_indices]
        anchor_coder1 = coder1[:, anchor_indices]
        anchor_coder2 = coder2[:, anchor_indices]
        human = draw_symmetric_labels(rng, anchor_truth, scenario.human_accuracy)

        accumulators["kappa_ai"].append(
            rowwise_cohen_kappa(coder1, coder2, N_RUBRIC_CATEGORIES)
        )
        accumulators["kappa_human_1"].append(
            rowwise_cohen_kappa(human, anchor_coder1, N_RUBRIC_CATEGORIES)
        )
        accumulators["kappa_human_2"].append(
            rowwise_cohen_kappa(human, anchor_coder2, N_RUBRIC_CATEGORIES)
        )

        truth_de = np.isin(truth, DE_CATEGORIES)
        coder1_de = np.isin(coder1, DE_CATEGORIES)
        coder2_de = np.isin(coder2, DE_CATEGORIES)
        anchor_truth_de = truth_de[:, anchor_indices]
        human_de = np.isin(human, DE_CATEGORIES)
        accumulators["kappa_de_ai"].append(
            rowwise_cohen_kappa(coder1_de, coder2_de, 2)
        )
        accumulators["kappa_de_human_1"].append(
            rowwise_cohen_kappa(human_de, coder1_de[:, anchor_indices], 2)
        )
        accumulators["kappa_de_human_2"].append(
            rowwise_cohen_kappa(human_de, coder2_de[:, anchor_indices], 2)
        )

        true_de_count = np.sum(truth_de, axis=1)
        true_non_de_count = full_sample_size - true_de_count
        sensitivity = np.divide(
            np.sum(coder1_de & truth_de, axis=1),
            true_de_count,
            out=np.full(current, np.nan),
            where=true_de_count > 0,
        )
        false_positive_rate = np.divide(
            np.sum(coder1_de & ~truth_de, axis=1),
            true_non_de_count,
            out=np.full(current, np.nan),
            where=true_non_de_count > 0,
        )
        accumulators["sensitivity"].append(sensitivity)
        accumulators["false_positive_rate"].append(false_positive_rate)
        remaining -= current

    values = {key: np.concatenate(parts) for key, parts in accumulators.items()}
    kappa_human_min = np.minimum(
        values["kappa_human_1"],
        values["kappa_human_2"],
    )
    ai_pass = np.isfinite(values["kappa_ai"]) & (
        values["kappa_ai"] >= KAPPA_THRESHOLD
    )
    human_pass = np.isfinite(kappa_human_min) & (
        kappa_human_min >= KAPPA_THRESHOLD
    )
    case_a = ai_pass & human_pass
    case_b = ai_pass & ~human_pass
    case_c = ~ai_pass
    kappa_de_human_min = np.minimum(
        values["kappa_de_human_1"],
        values["kappa_de_human_2"],
    )
    de_binary_pass = (
        np.isfinite(values["kappa_de_ai"])
        & np.isfinite(kappa_de_human_min)
        & (values["kappa_de_ai"] >= KAPPA_THRESHOLD)
        & (kappa_de_human_min >= KAPPA_THRESHOLD)
    )

    latent_q_linux = 0.10
    latent_q_windows = 0.20
    observed_q_linux = (
        values["sensitivity"] * latent_q_linux
        + values["false_positive_rate"] * (1.0 - latent_q_linux)
    )
    observed_q_windows = (
        values["sensitivity"] * latent_q_windows
        + values["false_positive_rate"] * (1.0 - latent_q_windows)
    )
    measurement_rr = observed_q_windows / observed_q_linux

    return {
        "record_type": "h2_irr_gate",
        "scenario": scenario.name,
        "replicates": replicates,
        "seed": seed,
        "full_sample_size": full_sample_size,
        "human_anchor_size": human_anchor_size,
        "irr_strata": N_IRR_STRATA,
        "human_per_stratum": per_anchor_stratum,
        "mean_kappa_ai_six_category": _finite_value(values["kappa_ai"]),
        "mean_kappa_human_min_six_category": _finite_value(kappa_human_min),
        "mean_kappa_ai_de_binary": _finite_value(values["kappa_de_ai"]),
        "mean_kappa_human_min_de_binary": _finite_value(
            kappa_de_human_min
        ),
        "case_a_confirmatory_probability": float(np.mean(case_a)),
        "case_b_shared_bias_demotion_probability": float(np.mean(case_b)),
        "case_c_ai_disagreement_demotion_probability": float(np.mean(case_c)),
        "any_demotion_probability": float(np.mean(~case_a)),
        "de_binary_threshold_pass_probability": float(np.mean(de_binary_pass)),
        "omnibus_pass_de_binary_below_threshold_probability": float(
            np.mean(case_a & ~de_binary_pass)
        ),
        "undefined_kappa_probability": float(
            np.mean(
                ~np.isfinite(values["kappa_ai"])
                | ~np.isfinite(kappa_human_min)
            )
        ),
        "mean_primary_de_sensitivity": float(np.mean(values["sensitivity"])),
        "mean_primary_de_false_positive_rate": float(
            np.mean(values["false_positive_rate"])
        ),
        "reference_latent_de_rr": latent_q_windows / latent_q_linux,
        "mean_measurement_only_de_rr": float(np.mean(measurement_rr)),
        "measurement_only_point_rr_ge2_probability": float(
            np.mean(measurement_rr >= 2.0)
        ),
        "primary_label_assumption": (
            "coder1_candidate_only_R017_unresolved_nondifferential_error"
        ),
        "irr_sampling_note": (
            "ten_equal_strata_five_human_labels_each_not_manifest_specific"
        ),
    }


def run_irr_grid(
    *,
    replicates: int,
    seed: int,
    full_sample_size: int = 5_040,
) -> list[dict[str, float | int | str | None]]:
    return [
        simulate_irr_scenario(
            scenario,
            replicates=replicates,
            seed=seed + index,
            full_sample_size=full_sample_size,
        )
        for index, scenario in enumerate(default_irr_scenarios())
    ]


def simulate_h2_measurement_overlay(
    irr_row: dict[str, float | int | str | None],
    *,
    latent_q_linux: float,
    latent_q_windows: float,
    base_common_n: int,
    replicates: int,
    seed: int,
) -> dict[str, float | int | str | None]:
    """Layer a candidate Coder-1 error transform onto the pooled H2 reference."""

    sensitivity = float(irr_row["mean_primary_de_sensitivity"])
    false_positive_rate = float(irr_row["mean_primary_de_false_positive_rate"])
    observed_q_linux = (
        sensitivity * latent_q_linux
        + false_positive_rate * (1.0 - latent_q_linux)
    )
    observed_q_windows = (
        sensitivity * latent_q_windows
        + false_positive_rate * (1.0 - latent_q_windows)
    )
    split_n = math.ceil(5 * base_common_n / 12)
    h2 = simulate_h2_design(
        H2Scenario(
            name="measurement_overlay",
            capability_failure_linux=0.05,
            capability_failure_windows=0.08,
            seeded_failure_linux=0.10,
            seeded_failure_windows=0.15,
            de_probability_linux=observed_q_linux,
            de_probability_windows=observed_q_windows,
        ),
        design="C_broad_split_n",
        capability_count=N_DOMAINS * FAMILIES_PER_DOMAIN,
        n_cap=split_n,
        n_seed=base_common_n,
        base_common_n=base_common_n,
        replicates=replicates,
        seed=seed,
    )
    confirmatory_probability = float(
        irr_row["case_a_confirmatory_probability"]
    )
    reference_support = float(h2["reference_lower_ci_above2_probability"])
    return {
        "record_type": "h2_measurement_overlay",
        "irr_scenario": str(irr_row["scenario"]),
        "replicates": replicates,
        "seed": seed,
        "base_common_n": base_common_n,
        "n_cap": split_n,
        "n_seed": base_common_n,
        "latent_de_probability_linux": latent_q_linux,
        "latent_de_probability_windows": latent_q_windows,
        "latent_de_rr": latent_q_windows / latent_q_linux,
        "candidate_observed_de_probability_linux": observed_q_linux,
        "candidate_observed_de_probability_windows": observed_q_windows,
        "candidate_observed_de_rr": observed_q_windows / observed_q_linux,
        "irr_reference_full_sample_size": irr_row["full_sample_size"],
        "irr_reference_human_anchor_size": irr_row["human_anchor_size"],
        "irr_confirmatory_probability": confirmatory_probability,
        "pooled_reference_estimable_probability": h2[
            "ratio_estimable_probability"
        ],
        "pooled_reference_lower_ci_above2_probability": reference_support,
        "combined_confirmatory_support_probability": (
            confirmatory_probability * reference_support
        ),
        "combined_probability_note": (
            "product_assumes_independent_irr_and_h2_sampling"
        ),
        "analysis_note": (
            "pooled_log_wald_plus_mean_nondifferential_coder1_error_not_D005"
        ),
    }


def run_h2_measurement_overlay_grid(
    irr_rows: Sequence[dict[str, float | int | str | None]],
    *,
    replicates: int,
    seed: int,
    base_common_ns: Iterable[int] = (6, 12, 24),
) -> list[dict[str, float | int | str | None]]:
    latent_pairs = ((0.15, 0.15), (0.10, 0.20), (0.10, 0.30))
    rows: list[dict[str, float | int | str | None]] = []
    for irr_index, irr_row in enumerate(irr_rows):
        for pair_index, (q_linux, q_windows) in enumerate(latent_pairs):
            for n_index, base_n in enumerate(base_common_ns):
                rows.append(
                    simulate_h2_measurement_overlay(
                        irr_row,
                        latent_q_linux=q_linux,
                        latent_q_windows=q_windows,
                        base_common_n=base_n,
                        replicates=replicates,
                        seed=(
                            seed
                            + 10_000 * irr_index
                            + 100 * pair_index
                            + n_index
                        ),
                    )
                )
    return rows


def _parse_sections(raw: str) -> set[str]:
    sections = {value.strip() for value in raw.split(",") if value.strip()}
    allowed = {"finite", "irr", "overlay"}
    if not sections or not sections <= allowed:
        raise argparse.ArgumentTypeError(
            "sections must be a comma-separated subset of finite,irr,overlay"
        )
    if "overlay" in sections:
        sections.add("irr")
    return sections


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run prospective D-005 finite-roster and H2 IRR audits."
    )
    parser.add_argument(
        "--sections",
        type=_parse_sections,
        default={"finite", "irr", "overlay"},
    )
    parser.add_argument("--replicates", type=int, default=5_000)
    parser.add_argument("--seed", type=int, default=20260801)
    parser.add_argument("--full-sample-size", type=int, default=5_040)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.replicates < 1:
        raise SystemExit("--replicates must be positive")
    rows: list[dict[str, float | int | str | None]] = []
    if "finite" in args.sections:
        rows.extend(
            run_finite_roster_grid(replicates=args.replicates, seed=args.seed)
        )
    irr_rows: list[dict[str, float | int | str | None]] = []
    if "irr" in args.sections:
        irr_rows = run_irr_grid(
            replicates=args.replicates,
            seed=args.seed + 100_000,
            full_sample_size=args.full_sample_size,
        )
        rows.extend(irr_rows)
    if "overlay" in args.sections:
        rows.extend(
            run_h2_measurement_overlay_grid(
                irr_rows,
                replicates=args.replicates,
                seed=args.seed + 200_000,
            )
        )
    for row in rows:
        print(json.dumps(row, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
