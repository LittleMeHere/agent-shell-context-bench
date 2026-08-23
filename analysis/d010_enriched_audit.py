"""Prospective probability-sampled H2 audit-allocation simulation.

This module compares additive human audits of focal failed trials. It retains
the registered minimum-size anchor for omnibus kappa, then applies a separate
probability sample with known first-order inclusion probabilities. The
audit-assisted estimator is a pooled two-phase difference reference. It is
not the registered mixed model and cannot resolve D-005.

The main allocation experiment treats the audit label as a perfect reference
to isolate sampling design. A 98%-accurate A-F human is a separate sensitivity
whose estimand is explicitly the potential human-reference label, not latent
truth. No function reads benchmark outcomes or changes the frozen V1 design.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from dataclasses import dataclass, replace
from functools import lru_cache
from statistics import NormalDist
from typing import Iterable, Sequence

import numpy as np
from numpy.typing import NDArray
from scipy.stats import hypergeom

from analysis.d005_finite_roster_irr import (
    DE_CATEGORIES,
    KAPPA_THRESHOLD,
    N_RUBRIC_CATEGORIES,
    finite_roster_h2_log_rr_interval,
    multiway_cluster_h2_log_rr_interval,
    rowwise_cohen_kappa,
)
from analysis.d010_joint_h2_measurement import (
    DEFAULT_ANCHOR_SIZE,
    JointScenario,
    build_joint_manifest,
    default_joint_scenarios,
    draw_joint_measurement_batch,
    draw_outcome_constrained_labels,
    manifest_true_h2_rates,
    pooled_h2_log_wald_reference,
    sample_registered_anchor_indices,
)
from analysis.d013_ceiling_operating_characteristics import CONFIDENCE
from analysis.d013_task_bank_design import REGISTERED_ENVIRONMENT_IDS


AI_AUDIT_STATE_NAMES = (
    "exact_c_agreement",
    "exact_f_agreement",
    "non_de_disagreement",
    "exactly_one_de",
    "both_de",
)
N_AI_AUDIT_STATES = len(AI_AUDIT_STATE_NAMES)
DEFAULT_AUDIT_BUDGETS = (50, 100, 200)


@dataclass(frozen=True)
class AuditDesign:
    """One fixed probability-sampling allocation rule."""

    name: str
    state_weights: tuple[float, ...] | None
    minimum_per_populated_stratum: int = 2

    def __post_init__(self) -> None:
        if not self.name or self.name.strip() != self.name:
            raise ValueError("audit design name must be non-empty and trimmed")
        if self.minimum_per_populated_stratum < 2:
            raise ValueError("audit strata require a minimum of two labels")
        if self.state_weights is not None and (
            len(self.state_weights) != N_AI_AUDIT_STATES
            or any(
                not math.isfinite(weight) or weight <= 0.0
                for weight in self.state_weights
            )
        ):
            raise ValueError("state_weights must contain five positive values")

    @property
    def stratum_weights(self) -> NDArray[np.float64]:
        if self.state_weights is None:
            return np.ones(2, dtype=float)
        return np.tile(np.asarray(self.state_weights, dtype=float), 2)


@dataclass(frozen=True)
class AuditHumanMode:
    """Potential reference labels used in the prospective audit."""

    name: str
    accuracy: float

    def __post_init__(self) -> None:
        if not self.name or self.name.strip() != self.name:
            raise ValueError("audit-human mode name must be non-empty and trimmed")
        if not 0.0 <= self.accuracy <= 1.0:
            raise ValueError("audit-human accuracy must lie in [0, 1]")


@dataclass(frozen=True)
class AuditSample:
    """One conditional probability sample and its frozen design metadata."""

    indices: NDArray[np.int64]
    inclusion_probability: NDArray[np.float64]
    population_stratum: NDArray[np.int64]
    population_counts: NDArray[np.int64]
    allocation: NDArray[np.int64]

    @property
    def size(self) -> int:
        return int(self.indices.size)


@dataclass(frozen=True)
class AuditH2Estimate:
    """Pooled audit-assisted point estimate and two distinct intervals."""

    estimable: bool
    out_of_bounds: bool
    q_linux: float
    q_windows: float
    rr: float
    design_variance_linux: float
    design_variance_windows: float
    finite_lower: float
    finite_upper: float
    repeated_lower: float
    repeated_upper: float


@dataclass(frozen=True)
class ConservativeAuditH2Interval:
    """Bonferroni-hypergeometric confidence set for the finite human ratio."""

    lower_estimable: bool
    finite_upper: bool
    q_linux_lower: float
    q_linux_upper: float
    q_windows_lower: float
    q_windows_upper: float
    rr_lower: float
    rr_upper: float
    uncertain_components: int
    component_confidence: float


def default_audit_designs() -> tuple[AuditDesign, ...]:
    """Return fixed candidates, including one intentional stress candidate."""

    return (
        AuditDesign("focal_failure_context_srs", None),
        AuditDesign("ai_state_balanced", (1.0, 1.0, 1.0, 1.0, 1.0)),
        AuditDesign(
            "positive_disagreement_enriched_stress",
            (1.0, 1.0, 2.0, 4.0, 4.0),
        ),
        AuditDesign(
            "shared_agreement_guarded",
            (4.0, 1.0, 2.0, 4.0, 4.0),
        ),
    )


def default_audit_human_modes() -> tuple[AuditHumanMode, ...]:
    return (
        AuditHumanMode("perfect_reference", 1.0),
        AuditHumanMode("noisy_98_reference", 0.98),
    )


def ai_audit_state(
    coder1: NDArray[np.int64],
    coder2: NDArray[np.int64],
) -> NDArray[np.int64]:
    """Classify failed-trial valid labels into five exhaustive AI states."""

    coder1 = np.asarray(coder1)
    coder2 = np.asarray(coder2)
    if coder1.shape != coder2.shape:
        raise ValueError("coder arrays must have identical shapes")
    if np.any((coder1 < 2) | (coder1 >= N_RUBRIC_CATEGORIES)) or np.any(
        (coder2 < 2) | (coder2 >= N_RUBRIC_CATEGORIES)
    ):
        raise ValueError(
            "audit states require valid failure-compatible C-F labels"
        )
    coder1_de = np.isin(coder1, DE_CATEGORIES)
    coder2_de = np.isin(coder2, DE_CATEGORIES)
    state = np.full(coder1.shape, -1, dtype=np.int64)
    state[(coder1 == 2) & (coder2 == 2)] = 0
    state[(coder1 == 5) & (coder2 == 5)] = 1
    state[(coder1 != coder2) & ~coder1_de & ~coder2_de] = 2
    state[coder1_de ^ coder2_de] = 3
    state[coder1_de & coder2_de] = 4
    if np.any(state < 0):
        raise RuntimeError("valid failed-trial labels did not map to an audit state")
    return state


def build_audit_strata(
    failure: NDArray[np.bool_],
    coder1: NDArray[np.int64],
    coder2: NDArray[np.int64],
    windows_mask: NDArray[np.bool_],
    linux_mask: NDArray[np.bool_],
    design: AuditDesign,
) -> NDArray[np.int64]:
    """Return -1 outside focal failures and fixed stratum IDs inside."""

    failure = np.asarray(failure, dtype=bool)
    coder1 = np.asarray(coder1)
    coder2 = np.asarray(coder2)
    windows_mask = np.asarray(windows_mask, dtype=bool)
    linux_mask = np.asarray(linux_mask, dtype=bool)
    if failure.ndim != 1 or coder1.shape != failure.shape or coder2.shape != failure.shape:
        raise ValueError("failure and coder labels must be equal one-dimensional arrays")
    if (
        windows_mask.shape != failure.shape
        or linux_mask.shape != failure.shape
        or np.any(windows_mask & linux_mask)
        or not np.any(windows_mask)
        or not np.any(linux_mask)
    ):
        raise ValueError("context masks must be non-empty and disjoint")
    strata = np.full(failure.shape, -1, dtype=np.int64)
    windows_eligible = failure & windows_mask
    linux_eligible = failure & linux_mask
    if design.state_weights is None:
        strata[windows_eligible] = 0
        strata[linux_eligible] = 1
        return strata
    for context, eligible in enumerate((windows_eligible, linux_eligible)):
        if not np.any(eligible):
            continue
        states = ai_audit_state(coder1[eligible], coder2[eligible])
        strata[eligible] = context * N_AI_AUDIT_STATES + states
    return strata


def deterministic_stratified_allocation(
    population_counts: NDArray[np.int64],
    *,
    budget: int,
    weights: NDArray[np.float64],
    minimum_per_populated_stratum: int,
) -> NDArray[np.int64]:
    """Allocate a fixed budget with floors, census caps, and stable ties.

    After assigning each populated stratum its floor (or a census when
    thinner), remaining labels are assigned one at a time by the largest
    ``weight / (allocated + 1)`` priority. Ties go to the lowest stratum ID.
    Census strata are skipped and their surplus is deterministically
    redistributed. The actual allocation is a census if the eligible
    population is smaller than the requested budget.
    """

    counts = np.asarray(population_counts)
    weights = np.asarray(weights, dtype=float)
    if counts.ndim != 1 or weights.shape != counts.shape:
        raise ValueError("counts and weights must be equal one-dimensional arrays")
    if np.any(counts < 0) or np.any(counts != np.floor(counts)):
        raise ValueError("population counts must be non-negative integers")
    if np.any(~np.isfinite(weights)) or np.any(weights <= 0.0):
        raise ValueError("allocation weights must be finite and positive")
    if budget < 1 or minimum_per_populated_stratum < 2:
        raise ValueError("budget must be positive and stratum minimum at least two")
    counts = counts.astype(np.int64)
    target = min(budget, int(np.sum(counts)))
    allocation = np.minimum(counts, minimum_per_populated_stratum)
    required = int(np.sum(allocation))
    if target < required:
        raise ValueError("budget cannot satisfy the populated-stratum floors")
    remaining = target - required
    for _ in range(remaining):
        eligible = allocation < counts
        if not np.any(eligible):
            raise RuntimeError("allocation exhausted before reaching target")
        priority = np.full(weights.shape, -np.inf)
        priority[eligible] = weights[eligible] / (allocation[eligible] + 1.0)
        allocation[int(np.argmax(priority))] += 1
    return allocation


def sample_enriched_audit(
    rng: np.random.Generator,
    population_stratum: NDArray[np.int64],
    *,
    design: AuditDesign,
    budget: int,
) -> AuditSample:
    """Draw SRSWOR inside each realized audit stratum without replacement."""

    strata = np.asarray(population_stratum)
    weights = design.stratum_weights
    if strata.ndim != 1 or np.any(strata >= weights.size) or np.any(strata < -1):
        raise ValueError("population_stratum contains invalid IDs")
    eligible = strata >= 0
    counts = np.bincount(strata[eligible], minlength=weights.size).astype(np.int64)
    allocation = deterministic_stratified_allocation(
        counts,
        budget=budget,
        weights=weights,
        minimum_per_populated_stratum=design.minimum_per_populated_stratum,
    )
    selected_parts: list[NDArray[np.int64]] = []
    probability_parts: list[NDArray[np.float64]] = []
    for stratum, sample_size in enumerate(allocation):
        if sample_size == 0:
            continue
        members = np.flatnonzero(strata == stratum)
        selected = rng.choice(members, size=int(sample_size), replace=False)
        selected_parts.append(selected)
        probability_parts.append(
            np.full(sample_size, sample_size / members.size, dtype=float)
        )
    if selected_parts:
        indices = np.concatenate(selected_parts)
        inclusion_probability = np.concatenate(probability_parts)
        order = rng.permutation(indices.size)
        indices = indices[order]
        inclusion_probability = inclusion_probability[order]
    else:
        indices = np.empty(0, dtype=np.int64)
        inclusion_probability = np.empty(0, dtype=float)
    return AuditSample(
        indices=indices,
        inclusion_probability=inclusion_probability,
        population_stratum=strata.astype(np.int64, copy=True),
        population_counts=counts,
        allocation=allocation,
    )


def _ratio_interval(
    q_windows: float,
    q_linux: float,
    variance_windows: float,
    variance_linux: float,
    confidence: float,
) -> tuple[float, float, float]:
    if (
        not 0.0 < q_windows < 1.0
        or not 0.0 < q_linux < 1.0
        or variance_windows < 0.0
        or variance_linux < 0.0
        or not all(
            math.isfinite(value)
            for value in (
                q_windows,
                q_linux,
                variance_windows,
                variance_linux,
            )
        )
    ):
        return math.nan, math.nan, math.nan
    rr = q_windows / q_linux
    standard_error = math.sqrt(
        variance_windows / q_windows**2 + variance_linux / q_linux**2
    )
    z_value = NormalDist().inv_cdf(0.5 + confidence / 2.0)
    return (
        rr,
        math.exp(math.log(rr) - z_value * standard_error),
        math.exp(math.log(rr) + z_value * standard_error),
    )


def audit_corrected_h2_reference(
    failure: NDArray[np.bool_],
    predicted_de: NDArray[np.bool_],
    human_de: NDArray[np.bool_],
    sample: AuditSample,
    windows_mask: NDArray[np.bool_],
    linux_mask: NDArray[np.bool_],
    *,
    minimum_failures: int = 10,
    confidence: float = CONFIDENCE,
) -> AuditH2Estimate:
    """Estimate pooled human-reference H2 with a difference estimator.

    The finite interval uses only conditional stratified audit variance and
    targets the realized full human-reference ratio. The repeated-study
    interval adds an optimistic conditional-binomial component and targets a
    scenario-level pooled ratio. Neither interval represents D-005's mixed
    model or task/configuration clustering.
    """

    failure = np.asarray(failure, dtype=bool)
    predicted_de = np.asarray(predicted_de, dtype=bool)
    human_de = np.asarray(human_de, dtype=bool)
    windows_mask = np.asarray(windows_mask, dtype=bool)
    linux_mask = np.asarray(linux_mask, dtype=bool)
    indices = np.asarray(sample.indices)
    inclusion_probability = np.asarray(sample.inclusion_probability, dtype=float)
    population_stratum = np.asarray(sample.population_stratum)
    population_counts = np.asarray(sample.population_counts)
    allocation = np.asarray(sample.allocation)
    if failure.ndim != 1 or predicted_de.shape != failure.shape:
        raise ValueError("failure and predicted_de must be equal one-dimensional arrays")
    if human_de.shape != indices.shape:
        raise ValueError("human_de must align with sampled indices")
    if (
        indices.ndim != 1
        or not np.issubdtype(indices.dtype, np.integer)
        or population_stratum.shape != failure.shape
        or not np.issubdtype(population_stratum.dtype, np.integer)
        or inclusion_probability.shape != indices.shape
        or population_counts.ndim != 1
        or allocation.shape != population_counts.shape
        or not np.issubdtype(population_counts.dtype, np.integer)
        or not np.issubdtype(allocation.dtype, np.integer)
        or np.unique(indices).size != indices.size
        or np.any(indices < 0)
        or np.any(indices >= failure.size)
        or np.any(inclusion_probability <= 0.0)
        or np.any(inclusion_probability > 1.0)
        or np.any(population_stratum < -1)
        or np.any(population_counts < 0)
        or np.any(allocation < 0)
        or np.any(allocation > population_counts)
    ):
        raise ValueError("audit sample metadata is invalid")
    if (
        windows_mask.shape != failure.shape
        or linux_mask.shape != failure.shape
        or np.any(windows_mask & linux_mask)
    ):
        raise ValueError("context masks must be disjoint trial masks")
    if minimum_failures < 1 or not 0.0 < confidence < 1.0:
        raise ValueError("invalid failure minimum or confidence")
    focal = failure & (windows_mask | linux_mask)
    if not np.array_equal(population_stratum >= 0, focal):
        raise ValueError("audit strata must identify exactly the focal failures")
    if np.any(population_stratum[focal] >= population_counts.size):
        raise ValueError("audit stratum IDs exceed the metadata dimensions")
    realized_counts = np.bincount(
        population_stratum[focal],
        minlength=population_counts.size,
    )
    selected_counts = np.bincount(
        population_stratum[indices],
        minlength=population_counts.size,
    )
    if not np.array_equal(realized_counts, population_counts) or not np.array_equal(
        selected_counts,
        allocation,
    ):
        raise ValueError("audit counts or allocation do not match the trial metadata")
    context_id = np.where(windows_mask, 0, np.where(linux_mask, 1, -1))
    for stratum in np.flatnonzero(population_counts):
        if np.unique(context_id[population_stratum == stratum]).size != 1:
            raise ValueError("each audit stratum must belong to exactly one context")
    expected_pi = allocation[population_stratum[indices]] / population_counts[
        population_stratum[indices]
    ]
    if not np.allclose(
        inclusion_probability,
        expected_pi,
        rtol=0.0,
        atol=1e-12,
    ):
        raise ValueError("inclusion probabilities do not match n_h/N_h")

    q_values: list[float] = []
    design_variances: list[float] = []
    denominators: list[int] = []
    variance_estimable = True
    for context_mask in (linux_mask, windows_mask):
        eligible = failure & context_mask
        denominator = int(np.sum(eligible))
        denominators.append(denominator)
        predicted_total = float(np.sum(predicted_de & eligible))
        correction_total = 0.0
        variance_total = 0.0
        for stratum in np.unique(population_stratum[eligible]):
            if stratum < 0:
                raise ValueError("eligible focal failures must have audit strata")
            population_members = np.flatnonzero(
                eligible & (population_stratum == stratum)
            )
            sampled_positions = np.flatnonzero(
                population_stratum[indices] == stratum
            )
            population_size = population_members.size
            sample_size = sampled_positions.size
            if sample_size == 0:
                variance_estimable = False
                continue
            expected_pi = sample_size / population_size
            if not np.allclose(
                inclusion_probability[sampled_positions],
                expected_pi,
                rtol=0.0,
                atol=1e-12,
            ):
                raise ValueError("inclusion probabilities do not match n_h/N_h")
            sampled_indices = indices[sampled_positions]
            residual = (
                human_de[sampled_positions].astype(float)
                - predicted_de[sampled_indices].astype(float)
            )
            correction_total += population_size * float(np.mean(residual))
            if sample_size == population_size:
                continue
            if sample_size < 2:
                variance_estimable = False
                continue
            residual_variance = float(np.var(residual, ddof=1))
            variance_total += (
                population_size**2
                * (1.0 - sample_size / population_size)
                * residual_variance
                / sample_size
            )
        q_values.append(
            math.nan
            if denominator == 0
            else (predicted_total + correction_total) / denominator
        )
        design_variances.append(
            math.nan if denominator == 0 else variance_total / denominator**2
        )

    q_linux, q_windows = q_values
    variance_linux, variance_windows = design_variances
    out_of_bounds = not (
        0.0 <= q_linux <= 1.0 and 0.0 <= q_windows <= 1.0
    )
    denominator_ok = all(value >= minimum_failures for value in denominators)
    finite_rr, finite_lower, finite_upper = _ratio_interval(
        q_windows,
        q_linux,
        variance_windows,
        variance_linux,
        confidence,
    )
    repeated_variance_linux = (
        variance_linux + q_linux * (1.0 - q_linux) / denominators[0]
        if 0.0 <= q_linux <= 1.0 and denominators[0] > 0
        else math.nan
    )
    repeated_variance_windows = (
        variance_windows + q_windows * (1.0 - q_windows) / denominators[1]
        if 0.0 <= q_windows <= 1.0 and denominators[1] > 0
        else math.nan
    )
    repeated_rr, repeated_lower, repeated_upper = _ratio_interval(
        q_windows,
        q_linux,
        repeated_variance_windows,
        repeated_variance_linux,
        confidence,
    )
    estimable = bool(
        denominator_ok
        and variance_estimable
        and not out_of_bounds
        and math.isfinite(finite_rr)
        and math.isfinite(repeated_rr)
    )
    return AuditH2Estimate(
        estimable=estimable,
        out_of_bounds=out_of_bounds,
        q_linux=float(q_linux),
        q_windows=float(q_windows),
        rr=float(finite_rr),
        design_variance_linux=float(variance_linux),
        design_variance_windows=float(variance_windows),
        finite_lower=float(finite_lower),
        finite_upper=float(finite_upper),
        repeated_lower=float(repeated_lower),
        repeated_upper=float(repeated_upper),
    )


@lru_cache(maxsize=None)
def _cached_hypergeometric_success_bounds(
    population_size: int,
    sample_size: int,
    observed_successes: int,
    confidence: float,
) -> tuple[int, int]:
    if sample_size == 0:
        return 0, population_size
    if sample_size == population_size:
        return observed_successes, observed_successes

    tail_probability = (1.0 - confidence) / 2.0
    feasible_low = observed_successes
    feasible_high = population_size - (sample_size - observed_successes)

    low = feasible_low
    high = feasible_high
    while low < high:
        candidate = (low + high) // 2
        upper_tail = float(
            hypergeom.sf(
                observed_successes - 1,
                population_size,
                candidate,
                sample_size,
            )
        )
        if upper_tail >= tail_probability:
            high = candidate
        else:
            low = candidate + 1
    lower_bound = low

    low = feasible_low
    high = feasible_high
    while low < high:
        candidate = (low + high + 1) // 2
        lower_tail = float(
            hypergeom.cdf(
                observed_successes,
                population_size,
                candidate,
                sample_size,
            )
        )
        if lower_tail >= tail_probability:
            low = candidate
        else:
            high = candidate - 1
    return lower_bound, low


def hypergeometric_success_bounds(
    population_size: int,
    sample_size: int,
    observed_successes: int,
    *,
    confidence: float,
) -> tuple[int, int]:
    """Invert equal-tailed hypergeometric tests for a finite success total."""

    values = (population_size, sample_size, observed_successes)
    if any(
        isinstance(value, (bool, np.bool_))
        or not isinstance(value, (int, np.integer))
        for value in values
    ):
        raise ValueError("population, sample, and success counts must be integers")
    population_size, sample_size, observed_successes = map(int, values)
    if (
        population_size < 0
        or sample_size < 0
        or sample_size > population_size
        or observed_successes < 0
        or observed_successes > sample_size
        or not 0.0 < confidence < 1.0
    ):
        raise ValueError("invalid finite-population confidence-set inputs")
    return _cached_hypergeometric_success_bounds(
        population_size,
        sample_size,
        observed_successes,
        float(confidence),
    )


def audit_corrected_h2_with_conservative_interval(
    failure: NDArray[np.bool_],
    predicted_de: NDArray[np.bool_],
    human_de: NDArray[np.bool_],
    sample: AuditSample,
    windows_mask: NDArray[np.bool_],
    linux_mask: NDArray[np.bool_],
    *,
    minimum_failures: int = 10,
    confidence: float = CONFIDENCE,
) -> tuple[AuditH2Estimate, ConservativeAuditH2Interval]:
    """Add simultaneous finite-population residual bounds to the point estimate.

    Within each audit stratum, sampled Coder-1-negative and Coder-1-positive
    cases are conditionally simple random samples of their full known
    subgroups. Exact hypergeometric confidence sets bound the false-negative
    and false-positive totals. Bonferroni allocation across every noncensus
    residual component gives at least ``confidence`` simultaneous conditional
    coverage of the full finite human-reference ratio. This interval contains
    audit-sampling uncertainty only; it is not a D-005 model interval.
    """

    estimate = audit_corrected_h2_reference(
        failure,
        predicted_de,
        human_de,
        sample,
        windows_mask,
        linux_mask,
        minimum_failures=minimum_failures,
        confidence=confidence,
    )
    failure = np.asarray(failure, dtype=bool)
    predicted_de = np.asarray(predicted_de, dtype=bool)
    human_de = np.asarray(human_de, dtype=bool)
    windows_mask = np.asarray(windows_mask, dtype=bool)
    linux_mask = np.asarray(linux_mask, dtype=bool)
    indices = np.asarray(sample.indices, dtype=np.int64)
    strata = np.asarray(sample.population_stratum, dtype=np.int64)

    components: list[
        tuple[int, bool, NDArray[np.int64], NDArray[np.int64]]
    ] = []
    for stratum in np.flatnonzero(sample.population_counts):
        population_members = np.flatnonzero(strata == stratum)
        sampled_positions = np.flatnonzero(strata[indices] == stratum)
        sampled_indices = indices[sampled_positions]
        for predicted_value in (False, True):
            population_subgroup = population_members[
                predicted_de[population_members] == predicted_value
            ]
            if population_subgroup.size == 0:
                continue
            sampled_subgroup_positions = sampled_positions[
                predicted_de[sampled_indices] == predicted_value
            ]
            components.append(
                (
                    int(stratum),
                    predicted_value,
                    population_subgroup,
                    sampled_subgroup_positions,
                )
            )

    uncertain_components = sum(
        len(sampled_positions) < len(population_members)
        for _, _, population_members, sampled_positions in components
    )
    component_confidence = (
        1.0
        if uncertain_components == 0
        else 1.0 - (1.0 - confidence) / uncertain_components
    )

    context_bounds: list[tuple[float, float]] = []
    for context_mask in (linux_mask, windows_mask):
        eligible = failure & context_mask
        denominator = int(np.sum(eligible))
        lower_total = int(np.sum(predicted_de & eligible))
        upper_total = lower_total
        for stratum, predicted_value, population_members, sampled_positions in components:
            if not np.any(eligible & (strata == stratum)):
                continue
            population_size = len(population_members)
            sample_size = len(sampled_positions)
            if predicted_value:
                observed = int(np.sum(~human_de[sampled_positions]))
            else:
                observed = int(np.sum(human_de[sampled_positions]))
            if sample_size == population_size:
                component_lower = component_upper = observed
            else:
                component_lower, component_upper = hypergeometric_success_bounds(
                    population_size,
                    sample_size,
                    observed,
                    confidence=component_confidence,
                )
            if predicted_value:
                lower_total -= component_upper
                upper_total -= component_lower
            else:
                lower_total += component_lower
                upper_total += component_upper
        lower_total = min(max(lower_total, 0), denominator)
        upper_total = min(max(upper_total, 0), denominator)
        context_bounds.append(
            (
                math.nan if denominator == 0 else lower_total / denominator,
                math.nan if denominator == 0 else upper_total / denominator,
            )
        )

    (q_linux_lower, q_linux_upper), (
        q_windows_lower,
        q_windows_upper,
    ) = context_bounds
    rr_lower = (
        q_windows_lower / q_linux_upper
        if q_linux_upper > 0.0
        else math.nan
    )
    if q_linux_lower > 0.0:
        rr_upper = q_windows_upper / q_linux_lower
    elif q_windows_upper > 0.0:
        rr_upper = math.inf
    else:
        rr_upper = math.nan
    denominator_ok = all(
        int(np.sum(failure & context_mask)) >= minimum_failures
        for context_mask in (linux_mask, windows_mask)
    )
    lower_estimable = bool(denominator_ok and math.isfinite(rr_lower))
    return estimate, ConservativeAuditH2Interval(
        lower_estimable=lower_estimable,
        finite_upper=bool(math.isfinite(rr_upper)),
        q_linux_lower=float(q_linux_lower),
        q_linux_upper=float(q_linux_upper),
        q_windows_lower=float(q_windows_lower),
        q_windows_upper=float(q_windows_upper),
        rr_lower=float(rr_lower),
        rr_upper=float(rr_upper),
        uncertain_components=uncertain_components,
        component_confidence=component_confidence,
    )


def weighted_binary_performance(
    predicted_de: NDArray[np.bool_],
    human_de: NDArray[np.bool_],
    inclusion_probability: NDArray[np.float64],
) -> tuple[float, float]:
    """Return HT-ratio sensitivity and specificity against human reference."""

    predicted_de = np.asarray(predicted_de, dtype=bool)
    human_de = np.asarray(human_de, dtype=bool)
    probability = np.asarray(inclusion_probability, dtype=float)
    if (
        predicted_de.shape != human_de.shape
        or probability.shape != human_de.shape
        or np.any(probability <= 0.0)
        or np.any(probability > 1.0)
    ):
        raise ValueError("weighted performance inputs must align with valid pi")
    weight = 1.0 / probability
    true_positive = float(np.sum(weight * (predicted_de & human_de)))
    false_negative = float(np.sum(weight * (~predicted_de & human_de)))
    true_negative = float(np.sum(weight * (~predicted_de & ~human_de)))
    false_positive = float(np.sum(weight * (predicted_de & ~human_de)))
    sensitivity = (
        true_positive / (true_positive + false_negative)
        if true_positive + false_negative > 0.0
        else math.nan
    )
    specificity = (
        true_negative / (true_negative + false_positive)
        if true_negative + false_positive > 0.0
        else math.nan
    )
    return sensitivity, specificity


def _finite_mean(values: Sequence[float]) -> float | None:
    array = np.asarray(values, dtype=float)
    finite = array[np.isfinite(array)]
    return float(np.mean(finite)) if finite.size else None


def _finite_median(values: Sequence[float]) -> float | None:
    array = np.asarray(values, dtype=float)
    finite = array[np.isfinite(array)]
    return float(np.median(finite)) if finite.size else None


def _conditional_probability(values: Sequence[float]) -> float | None:
    return _finite_mean(values)


def _true_realized_rate(
    latent_de: NDArray[np.bool_],
    failure: NDArray[np.bool_],
    context_mask: NDArray[np.bool_],
) -> float:
    eligible = failure & context_mask
    denominator = int(np.sum(eligible))
    return (
        math.nan
        if denominator == 0
        else float(np.sum(latent_de & eligible) / denominator)
    )


def _scenario_human_reference_rate(latent_rate: float, accuracy: float) -> float:
    """Expected D/E rate under the outcome-constrained four-class rater."""

    sensitivity = accuracy + (1.0 - accuracy) / 3.0
    false_positive_rate = 2.0 * (1.0 - accuracy) / 3.0
    return (
        sensitivity * latent_rate
        + false_positive_rate * (1.0 - latent_rate)
    )


def _replicate_rng(
    seed: int,
    replicate: int,
    purpose: str,
    *identifiers: object,
) -> np.random.Generator:
    """Return a stable stream isolated from batching and grid composition."""

    stream_name = "\x1f".join((purpose, *(str(value) for value in identifiers)))
    digest = hashlib.blake2s(
        stream_name.encode("utf-8"),
        digest_size=16,
        person=b"d010aud",
    ).digest()
    stream_words = [
        int.from_bytes(digest[offset : offset + 4], "little")
        for offset in range(0, len(digest), 4)
    ]
    return np.random.default_rng(
        np.random.SeedSequence([seed, replicate, *stream_words])
    )


def simulate_enriched_audit_scenario(
    scenario: JointScenario,
    *,
    base_common_n: int,
    replicates: int,
    seed: int,
    budgets: Iterable[int] = DEFAULT_AUDIT_BUDGETS,
    designs: Sequence[AuditDesign] | None = None,
    human_modes: Sequence[AuditHumanMode] | None = None,
    batch_size: int = 32,
) -> list[dict[str, float | int | str | None]]:
    """Run matched prospective audit allocations on shared generated trials."""

    if replicates < 1 or batch_size < 1:
        raise ValueError("replicates and batch_size must be positive")
    designs = tuple(default_audit_designs() if designs is None else designs)
    human_modes = tuple(
        default_audit_human_modes() if human_modes is None else human_modes
    )
    budgets = tuple(int(value) for value in budgets)
    if (
        not designs
        or not human_modes
        or not budgets
        or any(value < 1 for value in budgets)
    ):
        raise ValueError("designs, human modes, and positive budgets are required")
    if len(set(budgets)) != len(budgets):
        raise ValueError("audit budgets must be unique")
    if len({design.name for design in designs}) != len(designs):
        raise ValueError("audit design names must be unique")
    if len({mode.name for mode in human_modes}) != len(human_modes):
        raise ValueError("audit-human mode names must be unique")

    manifest = build_joint_manifest(scenario.h2, base_common_n=base_common_n)
    windows_id = REGISTERED_ENVIRONMENT_IDS.index("windows_powershell")
    linux_id = REGISTERED_ENVIRONMENT_IDS.index("linux_native")
    windows_mask = manifest.environment == windows_id
    linux_mask = manifest.environment == linux_id
    true_q_linux, true_q_windows, true_rr = manifest_true_h2_rates(
        manifest,
        windows_mask,
        linux_mask,
    )
    true_rr_is_null = true_rr < 2.0 or math.isclose(
        true_rr,
        2.0,
        rel_tol=0.0,
        abs_tol=1e-12,
    )
    keys = tuple(
        (design.name, budget, mode.name)
        for design in designs
        for budget in budgets
        for mode in human_modes
    )
    metric_names = (
        "actual_audit_size",
        "focal_failure_population",
        "audit_is_census",
        "minimum_inclusion_probability",
        "true_de_audited",
        "audit_zero_true_de",
        "exact_c_agreement_audited",
        "hidden_de_exact_c_population",
        "hidden_de_exact_c_audited",
        "hidden_present_no_hidden_sampled",
        "hidden_present",
        "zero_design_variance",
        "any_context_zero_design_variance",
        "human_binary_accuracy",
        "estimated_sensitivity",
        "estimated_specificity",
        "full_human_sensitivity",
        "full_human_specificity",
        "sensitivity_error",
        "specificity_error",
        "estimable",
        "out_of_bounds",
        "rr",
        "absolute_log_rr_error_vs_scenario_latent",
        "absolute_log_rr_error_vs_scenario_human_reference",
        "q_linux",
        "q_windows",
        "q_linux_error_vs_latent_realized",
        "q_windows_error_vs_latent_realized",
        "q_linux_error_vs_human_realized",
        "q_windows_error_vs_human_realized",
        "finite_coverage",
        "finite_uncovered_or_unestimable",
        "repeated_coverage",
        "repeated_uncovered_or_unestimable",
        "repeated_latent_coverage_diagnostic",
        "repeated_latent_uncovered_or_unestimable_diagnostic",
        "finite_interval_width",
        "repeated_interval_width",
        "bonferroni_lower_estimable",
        "bonferroni_finite_upper",
        "bonferroni_coverage",
        "bonferroni_uncovered_or_lower_unestimable",
        "bonferroni_rr_lower",
        "bonferroni_interval_width",
        "bonferroni_q_linux_width",
        "bonferroni_q_windows_width",
        "bonferroni_ratio_above_2",
        "bonferroni_gate_and_ratio_above_2",
        "bonferroni_uncertain_components",
        "bonferroni_component_confidence",
        "pooled_support",
        "support_given_estimable",
        "joint_support",
        "full_human_rr",
        "full_human_estimable",
        "full_human_support",
        "full_human_pooled_coverage",
        "full_human_d005_estimable",
        "full_human_d005_coverage",
        "full_human_d005_support",
        "full_human_d005_rr_lower",
        "audit_d005_estimable",
        "audit_d005_coverage",
        "audit_d005_latent_coverage_diagnostic",
        "audit_d005_support",
        "audit_d005_rr_lower",
        "d005_exact_audit_coupled_support",
        "full_human_finite_d005_estimable",
        "full_human_finite_d005_coverage",
        "full_human_finite_d005_support",
        "full_human_finite_d005_rr_lower",
        "audit_finite_d005_estimable",
        "audit_finite_d005_coverage",
        "audit_finite_d005_latent_coverage_diagnostic",
        "audit_finite_d005_support",
        "audit_finite_d005_rr_lower",
        "finite_d005_exact_audit_coupled_support",
        "pooled_d005_exact_audit_coupled_support",
    )
    metrics: dict[tuple[str, int, str], dict[str, list[float]]] = {
        key: {name: [] for name in metric_names} for key in keys
    }
    common = {
        name: []
        for name in (
            "irr_pass",
            "naive_estimable",
            "naive_rr",
            "naive_support",
            "naive_joint_support",
            "oracle_estimable",
            "oracle_rr",
            "oracle_support",
            "oracle_joint_support",
        )
    }

    remaining = replicates
    completed = 0
    while remaining:
        batch_size_now = min(batch_size, remaining)
        generated = [
            draw_joint_measurement_batch(
                _replicate_rng(seed, completed + offset, "dgp"),
                scenario,
                manifest,
                1,
            )
            for offset in range(batch_size_now)
        ]
        failure = np.concatenate([item.failure for item in generated], axis=0)
        latent_de = np.concatenate([item.latent_de for item in generated], axis=0)
        truth = np.concatenate([item.truth for item in generated], axis=0)
        coder1 = np.concatenate([item.coder1 for item in generated], axis=0)
        coder2 = np.concatenate([item.coder2 for item in generated], axis=0)
        coder1_de = np.isin(coder1, DE_CATEGORIES)
        kappa_ai = rowwise_cohen_kappa(coder1, coder2, N_RUBRIC_CATEGORIES)
        naive_estimable, naive_rr, naive_lower = pooled_h2_log_wald_reference(
            failure,
            coder1_de,
            windows_mask,
            linux_mask,
        )
        oracle_estimable, oracle_rr, oracle_lower = pooled_h2_log_wald_reference(
            failure,
            latent_de,
            windows_mask,
            linux_mask,
        )
        potential_human: dict[str, NDArray[np.int64]] = {"perfect_reference": truth}
        for mode in human_modes:
            if mode.name == "perfect_reference" and mode.accuracy == 1.0:
                continue
            potential_human[mode.name] = np.concatenate(
                [
                    draw_outcome_constrained_labels(
                        _replicate_rng(
                            seed,
                            completed + offset,
                            "potential_human",
                            mode.name,
                        ),
                        truth[offset : offset + 1],
                        failure[offset : offset + 1],
                        mode.accuracy,
                    )
                    for offset in range(batch_size_now)
                ],
                axis=0,
            )

        for replicate in range(batch_size_now):
            replicate_id = completed + replicate
            anchor = sample_registered_anchor_indices(
                _replicate_rng(seed, replicate_id, "anchor_sample"),
                manifest.stratum,
            )
            anchor_truth = truth[replicate, anchor][None, :]
            anchor_failure = failure[replicate, anchor][None, :]
            anchor_human = draw_outcome_constrained_labels(
                _replicate_rng(seed, replicate_id, "anchor_human"),
                anchor_truth,
                anchor_failure,
                scenario.human_accuracy,
            )
            human_kappa_1 = rowwise_cohen_kappa(
                anchor_human,
                coder1[replicate, anchor][None, :],
                N_RUBRIC_CATEGORIES,
            )[0]
            human_kappa_2 = rowwise_cohen_kappa(
                anchor_human,
                coder2[replicate, anchor][None, :],
                N_RUBRIC_CATEGORIES,
            )[0]
            irr_pass = bool(
                math.isfinite(float(kappa_ai[replicate]))
                and math.isfinite(float(human_kappa_1))
                and math.isfinite(float(human_kappa_2))
                and kappa_ai[replicate] >= KAPPA_THRESHOLD
                and min(human_kappa_1, human_kappa_2) >= KAPPA_THRESHOLD
            )
            naive_support = bool(
                naive_estimable[replicate] and naive_lower[replicate] > 2.0
            )
            oracle_support = bool(
                oracle_estimable[replicate] and oracle_lower[replicate] > 2.0
            )
            common["irr_pass"].append(float(irr_pass))
            common["naive_estimable"].append(float(naive_estimable[replicate]))
            common["naive_rr"].append(
                float(naive_rr[replicate])
                if naive_estimable[replicate]
                else math.nan
            )
            common["naive_support"].append(float(naive_support))
            common["naive_joint_support"].append(float(irr_pass and naive_support))
            common["oracle_estimable"].append(float(oracle_estimable[replicate]))
            common["oracle_rr"].append(
                float(oracle_rr[replicate])
                if oracle_estimable[replicate]
                else math.nan
            )
            common["oracle_support"].append(float(oracle_support))
            common["oracle_joint_support"].append(float(irr_pass and oracle_support))

            failure_row = failure[replicate]
            latent_row = latent_de[replicate]
            coder1_row = coder1[replicate]
            coder2_row = coder2[replicate]
            coder1_de_row = coder1_de[replicate]
            latent_q_linux = _true_realized_rate(
                latent_row,
                failure_row,
                linux_mask,
            )
            latent_q_windows = _true_realized_rate(
                latent_row,
                failure_row,
                windows_mask,
            )
            eligible = failure_row & (windows_mask | linux_mask)
            state_full = np.full(manifest.size, -1, dtype=np.int64)
            if np.any(eligible):
                state_full[eligible] = ai_audit_state(
                    coder1_row[eligible],
                    coder2_row[eligible],
                )

            samples: dict[tuple[str, int], AuditSample] = {}
            for design in designs:
                audit_strata = build_audit_strata(
                    failure_row,
                    coder1_row,
                    coder2_row,
                    windows_mask,
                    linux_mask,
                    design,
                )
                for budget in budgets:
                    samples[(design.name, budget)] = sample_enriched_audit(
                        _replicate_rng(
                            seed,
                            replicate_id,
                            "audit_sample",
                            design.name,
                            budget,
                        ),
                        audit_strata,
                        design=design,
                        budget=budget,
                    )

            for mode in human_modes:
                scenario_human_q_linux = _scenario_human_reference_rate(
                    true_q_linux,
                    mode.accuracy,
                )
                scenario_human_q_windows = _scenario_human_reference_rate(
                    true_q_windows,
                    mode.accuracy,
                )
                scenario_human_rr = (
                    scenario_human_q_windows / scenario_human_q_linux
                )
                human_labels_row = potential_human[mode.name][replicate]
                human_de_full = np.isin(human_labels_row, DE_CATEGORIES) & failure_row
                human_estimable, human_rr, human_lower = pooled_h2_log_wald_reference(
                    failure_row[None, :],
                    human_de_full[None, :],
                    windows_mask,
                    linux_mask,
                )
                human_q_linux = _true_realized_rate(
                    human_de_full,
                    failure_row,
                    linux_mask,
                )
                human_q_windows = _true_realized_rate(
                    human_de_full,
                    failure_row,
                    windows_mask,
                )
                human_upper = (
                    human_rr[0] ** 2 / human_lower[0]
                    if human_estimable[0] and human_lower[0] > 0.0
                    else math.nan
                )
                full_human_pooled_coverage = bool(
                    human_estimable[0]
                    and human_lower[0] <= scenario_human_rr
                    and scenario_human_rr <= human_upper
                )
                full_sensitivity, full_specificity = weighted_binary_performance(
                    coder1_de_row[eligible],
                    human_de_full[eligible],
                    np.ones(int(np.sum(eligible))),
                )
                full_human_d005 = multiway_cluster_h2_log_rr_interval(
                    failure_row,
                    human_de_full.astype(float),
                    windows_mask,
                    linux_mask,
                    manifest.task,
                    manifest.configuration,
                )
                full_human_d005_coverage = bool(
                    full_human_d005.estimable
                    and full_human_d005.rr_lower <= scenario_human_rr
                    and scenario_human_rr <= full_human_d005.rr_upper
                )
                full_human_d005_support = bool(
                    full_human_d005.estimable
                    and full_human_d005.rr_lower > 2.0
                )
                full_human_finite_d005 = finite_roster_h2_log_rr_interval(
                    failure_row,
                    human_de_full.astype(float),
                    windows_mask,
                    linux_mask,
                    manifest.task_variant,
                    manifest.configuration,
                )
                full_human_finite_d005_coverage = bool(
                    full_human_finite_d005.estimable
                    and full_human_finite_d005.rr_lower <= scenario_human_rr
                    and scenario_human_rr <= full_human_finite_d005.rr_upper
                )
                full_human_finite_d005_support = bool(
                    full_human_finite_d005.estimable
                    and full_human_finite_d005.rr_lower > 2.0
                )
                for design in designs:
                    for budget in budgets:
                        key = (design.name, budget, mode.name)
                        destination = metrics[key]
                        sample = samples[(design.name, budget)]
                        selected = sample.indices
                        audit_human_de = human_de_full[selected]
                        estimate, conservative = (
                            audit_corrected_h2_with_conservative_interval(
                                failure_row,
                                coder1_de_row,
                                audit_human_de,
                                sample,
                                windows_mask,
                                linux_mask,
                            )
                        )
                        sensitivity, specificity = weighted_binary_performance(
                            coder1_de_row[selected],
                            audit_human_de,
                            sample.inclusion_probability,
                        )
                        selected_state = state_full[selected]
                        exact_c_selected = selected_state == 0
                        hidden_population = int(
                            np.sum(eligible & (state_full == 0) & latent_row)
                        )
                        hidden_audited = int(
                            np.sum(exact_c_selected & latent_row[selected])
                        )
                        actual_size = sample.size
                        focal_failures = int(np.sum(eligible))
                        census = actual_size == focal_failures
                        finite_target_ok = bool(
                            estimate.estimable and human_estimable[0]
                        )
                        finite_coverage = bool(
                            finite_target_ok
                            and estimate.finite_lower <= human_rr[0]
                            and human_rr[0] <= estimate.finite_upper
                        )
                        repeated_coverage = bool(
                            estimate.estimable
                            and estimate.repeated_lower <= scenario_human_rr
                            and scenario_human_rr <= estimate.repeated_upper
                        )
                        repeated_latent_coverage = bool(
                            estimate.estimable
                            and estimate.repeated_lower <= true_rr
                            and true_rr <= estimate.repeated_upper
                        )
                        pooled_support = bool(
                            estimate.estimable and estimate.repeated_lower > 2.0
                        )
                        conservative_target_ok = bool(
                            conservative.lower_estimable and human_estimable[0]
                        )
                        conservative_coverage = bool(
                            conservative_target_ok
                            and conservative.rr_lower <= human_rr[0]
                            and human_rr[0] <= conservative.rr_upper
                        )
                        conservative_ratio_above_2 = bool(
                            conservative.lower_estimable
                            and conservative.rr_lower > 2.0
                        )
                        pseudo_de = coder1_de_row.astype(float)
                        pseudo_de[selected] += (
                            audit_human_de.astype(float)
                            - coder1_de_row[selected].astype(float)
                        ) / sample.inclusion_probability
                        failure_linux = failure_row & linux_mask
                        failure_windows = failure_row & windows_mask
                        n_failure_linux = int(np.sum(failure_linux))
                        n_failure_windows = int(np.sum(failure_windows))
                        if n_failure_linux and n_failure_windows:
                            pseudo_q_linux = float(
                                np.sum(pseudo_de[failure_linux]) / n_failure_linux
                            )
                            pseudo_q_windows = float(
                                np.sum(pseudo_de[failure_windows])
                                / n_failure_windows
                            )
                            if not (
                                math.isclose(
                                    pseudo_q_linux,
                                    estimate.q_linux,
                                    rel_tol=0.0,
                                    abs_tol=1e-12,
                                )
                                and math.isclose(
                                    pseudo_q_windows,
                                    estimate.q_windows,
                                    rel_tol=0.0,
                                    abs_tol=1e-12,
                                )
                            ):
                                raise RuntimeError(
                                    "audit pseudo-outcome and point estimator disagree"
                                )
                        audit_d005 = multiway_cluster_h2_log_rr_interval(
                            failure_row,
                            pseudo_de,
                            windows_mask,
                            linux_mask,
                            manifest.task,
                            manifest.configuration,
                        )
                        audit_d005_coverage = bool(
                            audit_d005.estimable
                            and audit_d005.rr_lower <= scenario_human_rr
                            and scenario_human_rr <= audit_d005.rr_upper
                        )
                        audit_d005_latent_coverage = bool(
                            audit_d005.estimable
                            and audit_d005.rr_lower <= true_rr
                            and true_rr <= audit_d005.rr_upper
                        )
                        audit_d005_support = bool(
                            audit_d005.estimable
                            and audit_d005.rr_lower > 2.0
                        )
                        d005_coupled_support = bool(
                            irr_pass
                            and conservative_ratio_above_2
                            and audit_d005_support
                        )
                        audit_finite_d005 = finite_roster_h2_log_rr_interval(
                            failure_row,
                            pseudo_de,
                            windows_mask,
                            linux_mask,
                            manifest.task_variant,
                            manifest.configuration,
                        )
                        audit_finite_d005_coverage = bool(
                            audit_finite_d005.estimable
                            and audit_finite_d005.rr_lower <= scenario_human_rr
                            and scenario_human_rr <= audit_finite_d005.rr_upper
                        )
                        audit_finite_d005_latent_coverage = bool(
                            audit_finite_d005.estimable
                            and audit_finite_d005.rr_lower <= true_rr
                            and true_rr <= audit_finite_d005.rr_upper
                        )
                        audit_finite_d005_support = bool(
                            audit_finite_d005.estimable
                            and audit_finite_d005.rr_lower > 2.0
                        )
                        finite_d005_coupled_support = bool(
                            irr_pass
                            and conservative_ratio_above_2
                            and audit_finite_d005_support
                        )
                        pooled_d005_coupled_support = bool(
                            irr_pass
                            and conservative_ratio_above_2
                            and pooled_support
                        )
                        destination["actual_audit_size"].append(float(actual_size))
                        destination["focal_failure_population"].append(float(focal_failures))
                        destination["audit_is_census"].append(float(census))
                        destination["minimum_inclusion_probability"].append(
                            float(np.min(sample.inclusion_probability))
                            if sample.size
                            else math.nan
                        )
                        destination["true_de_audited"].append(
                            float(np.sum(latent_row[selected]))
                        )
                        destination["audit_zero_true_de"].append(
                            float(not np.any(latent_row[selected]))
                        )
                        destination["exact_c_agreement_audited"].append(
                            float(np.sum(exact_c_selected))
                        )
                        destination["hidden_de_exact_c_population"].append(
                            float(hidden_population)
                        )
                        destination["hidden_de_exact_c_audited"].append(
                            float(hidden_audited)
                        )
                        destination["hidden_present"].append(float(hidden_population > 0))
                        destination["hidden_present_no_hidden_sampled"].append(
                            float(hidden_population > 0 and hidden_audited == 0)
                        )
                        destination["zero_design_variance"].append(
                            float(
                                estimate.design_variance_linux == 0.0
                                and estimate.design_variance_windows == 0.0
                            )
                        )
                        destination["any_context_zero_design_variance"].append(
                            float(
                                estimate.design_variance_linux == 0.0
                                or estimate.design_variance_windows == 0.0
                            )
                        )
                        destination["human_binary_accuracy"].append(
                            float(
                                np.mean(audit_human_de == latent_row[selected])
                            )
                            if sample.size
                            else math.nan
                        )
                        destination["estimated_sensitivity"].append(sensitivity)
                        destination["estimated_specificity"].append(specificity)
                        destination["full_human_sensitivity"].append(full_sensitivity)
                        destination["full_human_specificity"].append(full_specificity)
                        destination["sensitivity_error"].append(
                            sensitivity - full_sensitivity
                        )
                        destination["specificity_error"].append(
                            specificity - full_specificity
                        )
                        destination["estimable"].append(float(estimate.estimable))
                        destination["out_of_bounds"].append(float(estimate.out_of_bounds))
                        destination["rr"].append(
                            estimate.rr if estimate.estimable else math.nan
                        )
                        destination[
                            "absolute_log_rr_error_vs_scenario_latent"
                        ].append(
                            abs(math.log(estimate.rr / true_rr))
                            if estimate.estimable and estimate.rr > 0.0
                            else math.nan
                        )
                        destination[
                            "absolute_log_rr_error_vs_scenario_human_reference"
                        ].append(
                            abs(math.log(estimate.rr / scenario_human_rr))
                            if estimate.estimable and estimate.rr > 0.0
                            else math.nan
                        )
                        destination["q_linux"].append(estimate.q_linux)
                        destination["q_windows"].append(estimate.q_windows)
                        destination["q_linux_error_vs_latent_realized"].append(
                            estimate.q_linux - latent_q_linux
                        )
                        destination["q_windows_error_vs_latent_realized"].append(
                            estimate.q_windows - latent_q_windows
                        )
                        destination["q_linux_error_vs_human_realized"].append(
                            estimate.q_linux - human_q_linux
                        )
                        destination["q_windows_error_vs_human_realized"].append(
                            estimate.q_windows - human_q_windows
                        )
                        destination["finite_coverage"].append(
                            float(finite_coverage) if finite_target_ok else math.nan
                        )
                        destination["finite_uncovered_or_unestimable"].append(
                            float(not finite_coverage)
                        )
                        destination["repeated_coverage"].append(
                            float(repeated_coverage)
                            if estimate.estimable
                            else math.nan
                        )
                        destination["repeated_uncovered_or_unestimable"].append(
                            float(not repeated_coverage)
                        )
                        destination[
                            "repeated_latent_coverage_diagnostic"
                        ].append(
                            float(repeated_latent_coverage)
                            if estimate.estimable
                            else math.nan
                        )
                        destination[
                            "repeated_latent_uncovered_or_unestimable_diagnostic"
                        ].append(float(not repeated_latent_coverage))
                        destination["finite_interval_width"].append(
                            estimate.finite_upper - estimate.finite_lower
                            if estimate.estimable
                            else math.nan
                        )
                        destination["repeated_interval_width"].append(
                            estimate.repeated_upper - estimate.repeated_lower
                            if estimate.estimable
                            else math.nan
                        )
                        destination["bonferroni_lower_estimable"].append(
                            float(conservative.lower_estimable)
                        )
                        destination["bonferroni_finite_upper"].append(
                            float(conservative.finite_upper)
                        )
                        destination["bonferroni_coverage"].append(
                            float(conservative_coverage)
                            if conservative_target_ok
                            else math.nan
                        )
                        destination[
                            "bonferroni_uncovered_or_lower_unestimable"
                        ].append(float(not conservative_coverage))
                        destination["bonferroni_rr_lower"].append(
                            conservative.rr_lower
                            if conservative.lower_estimable
                            else math.nan
                        )
                        destination["bonferroni_interval_width"].append(
                            conservative.rr_upper - conservative.rr_lower
                            if conservative.lower_estimable
                            and conservative.finite_upper
                            else math.nan
                        )
                        destination["bonferroni_q_linux_width"].append(
                            conservative.q_linux_upper
                            - conservative.q_linux_lower
                        )
                        destination["bonferroni_q_windows_width"].append(
                            conservative.q_windows_upper
                            - conservative.q_windows_lower
                        )
                        destination["bonferroni_ratio_above_2"].append(
                            float(conservative_ratio_above_2)
                        )
                        destination[
                            "bonferroni_gate_and_ratio_above_2"
                        ].append(float(irr_pass and conservative_ratio_above_2))
                        destination["bonferroni_uncertain_components"].append(
                            float(conservative.uncertain_components)
                        )
                        destination["bonferroni_component_confidence"].append(
                            conservative.component_confidence
                        )
                        destination["pooled_support"].append(float(pooled_support))
                        destination["support_given_estimable"].append(
                            float(pooled_support) if estimate.estimable else math.nan
                        )
                        destination["joint_support"].append(
                            float(irr_pass and pooled_support)
                        )
                        destination["full_human_rr"].append(
                            float(human_rr[0])
                            if human_estimable[0]
                            else math.nan
                        )
                        destination["full_human_estimable"].append(
                            float(human_estimable[0])
                        )
                        destination["full_human_support"].append(
                            float(human_estimable[0] and human_lower[0] > 2.0)
                        )
                        destination["full_human_pooled_coverage"].append(
                            float(full_human_pooled_coverage)
                            if human_estimable[0]
                            else math.nan
                        )
                        destination["full_human_d005_estimable"].append(
                            float(full_human_d005.estimable)
                        )
                        destination["full_human_d005_coverage"].append(
                            float(full_human_d005_coverage)
                            if full_human_d005.estimable
                            else math.nan
                        )
                        destination["full_human_d005_support"].append(
                            float(full_human_d005_support)
                        )
                        destination["full_human_d005_rr_lower"].append(
                            full_human_d005.rr_lower
                            if full_human_d005.estimable
                            else math.nan
                        )
                        destination["audit_d005_estimable"].append(
                            float(audit_d005.estimable)
                        )
                        destination["audit_d005_coverage"].append(
                            float(audit_d005_coverage)
                            if audit_d005.estimable
                            else math.nan
                        )
                        destination[
                            "audit_d005_latent_coverage_diagnostic"
                        ].append(
                            float(audit_d005_latent_coverage)
                            if audit_d005.estimable
                            else math.nan
                        )
                        destination["audit_d005_support"].append(
                            float(audit_d005_support)
                        )
                        destination["audit_d005_rr_lower"].append(
                            audit_d005.rr_lower
                            if audit_d005.estimable
                            else math.nan
                        )
                        destination["d005_exact_audit_coupled_support"].append(
                            float(d005_coupled_support)
                        )
                        destination["full_human_finite_d005_estimable"].append(
                            float(full_human_finite_d005.estimable)
                        )
                        destination["full_human_finite_d005_coverage"].append(
                            float(full_human_finite_d005_coverage)
                            if full_human_finite_d005.estimable
                            else math.nan
                        )
                        destination["full_human_finite_d005_support"].append(
                            float(full_human_finite_d005_support)
                        )
                        destination["full_human_finite_d005_rr_lower"].append(
                            full_human_finite_d005.rr_lower
                            if full_human_finite_d005.estimable
                            else math.nan
                        )
                        destination["audit_finite_d005_estimable"].append(
                            float(audit_finite_d005.estimable)
                        )
                        destination["audit_finite_d005_coverage"].append(
                            float(audit_finite_d005_coverage)
                            if audit_finite_d005.estimable
                            else math.nan
                        )
                        destination[
                            "audit_finite_d005_latent_coverage_diagnostic"
                        ].append(
                            float(audit_finite_d005_latent_coverage)
                            if audit_finite_d005.estimable
                            else math.nan
                        )
                        destination["audit_finite_d005_support"].append(
                            float(audit_finite_d005_support)
                        )
                        destination["audit_finite_d005_rr_lower"].append(
                            audit_finite_d005.rr_lower
                            if audit_finite_d005.estimable
                            else math.nan
                        )
                        destination[
                            "finite_d005_exact_audit_coupled_support"
                        ].append(float(finite_d005_coupled_support))
                        destination[
                            "pooled_d005_exact_audit_coupled_support"
                        ].append(float(pooled_d005_coupled_support))
        remaining -= batch_size_now
        completed += batch_size_now

    rows: list[dict[str, float | int | str | None]] = []
    for design in designs:
        for budget in budgets:
            for mode in human_modes:
                key = (design.name, budget, mode.name)
                values = metrics[key]
                estimable_probability = float(np.mean(values["estimable"]))
                scenario_human_q_linux = _scenario_human_reference_rate(
                    true_q_linux,
                    mode.accuracy,
                )
                scenario_human_q_windows = _scenario_human_reference_rate(
                    true_q_windows,
                    mode.accuracy,
                )
                scenario_human_rr = (
                    scenario_human_q_windows / scenario_human_q_linux
                )
                row: dict[str, float | int | str | None] = {
                    "record_type": "d010_enriched_h2_audit",
                    "scenario": scenario.name,
                    "base_common_n": base_common_n,
                    "n_cap": manifest.n_cap,
                    "n_seed": manifest.n_seed,
                    "full_sample_size": manifest.size,
                    "replicates": replicates,
                    "seed": seed,
                    "audit_design": design.name,
                    "audit_design_status": (
                        "intentional_shared_agreement_failure_candidate"
                        if design.name == "positive_disagreement_enriched_stress"
                        else "candidate_not_selected"
                    ),
                    "audit_budget_requested": budget,
                    "audit_human_mode": mode.name,
                    "audit_human_accuracy": mode.accuracy,
                    "registered_anchor_size_instantiated": DEFAULT_ANCHOR_SIZE,
                    "audit_is_independent_additive_no_overlap_deduplication": True,
                    "mean_actual_audit_size": float(
                        np.mean(values["actual_audit_size"])
                    ),
                    "mean_conservative_total_human_labels": float(
                        DEFAULT_ANCHOR_SIZE + np.mean(values["actual_audit_size"])
                    ),
                    "mean_focal_failure_population": float(
                        np.mean(values["focal_failure_population"])
                    ),
                    "audit_census_probability": float(
                        np.mean(values["audit_is_census"])
                    ),
                    "mean_minimum_inclusion_probability": _finite_mean(
                        values["minimum_inclusion_probability"]
                    ),
                    "mean_true_de_audited": float(
                        np.mean(values["true_de_audited"])
                    ),
                    "audit_zero_true_de_probability": float(
                        np.mean(values["audit_zero_true_de"])
                    ),
                    "mean_exact_c_agreement_audited": float(
                        np.mean(values["exact_c_agreement_audited"])
                    ),
                    "mean_hidden_de_exact_c_population": float(
                        np.mean(values["hidden_de_exact_c_population"])
                    ),
                    "mean_hidden_de_exact_c_audited": float(
                        np.mean(values["hidden_de_exact_c_audited"])
                    ),
                    "hidden_present_probability": float(
                        np.mean(values["hidden_present"])
                    ),
                    "no_hidden_correction_sampled_probability": float(
                        np.mean(values["hidden_present_no_hidden_sampled"])
                    ),
                    "no_hidden_correction_sampled_given_hidden_present": (
                        None
                        if not np.any(values["hidden_present"])
                        else float(
                            np.sum(values["hidden_present_no_hidden_sampled"])
                            / np.sum(values["hidden_present"])
                        )
                    ),
                    "zero_design_variance_probability": float(
                        np.mean(values["zero_design_variance"])
                    ),
                    "any_context_zero_design_variance_probability": float(
                        np.mean(values["any_context_zero_design_variance"])
                    ),
                    "mean_audit_human_binary_accuracy": _finite_mean(
                        values["human_binary_accuracy"]
                    ),
                    "mean_estimated_coder1_sensitivity": _finite_mean(
                        values["estimated_sensitivity"]
                    ),
                    "mean_estimated_coder1_specificity": _finite_mean(
                        values["estimated_specificity"]
                    ),
                    "mean_full_human_coder1_sensitivity": _finite_mean(
                        values["full_human_sensitivity"]
                    ),
                    "mean_full_human_coder1_specificity": _finite_mean(
                        values["full_human_specificity"]
                    ),
                    "mean_coder1_sensitivity_estimation_error": _finite_mean(
                        values["sensitivity_error"]
                    ),
                    "mean_coder1_specificity_estimation_error": _finite_mean(
                        values["specificity_error"]
                    ),
                    "mean_absolute_coder1_sensitivity_error": _finite_mean(
                        np.abs(values["sensitivity_error"])
                    ),
                    "mean_absolute_coder1_specificity_error": _finite_mean(
                        np.abs(values["specificity_error"])
                    ),
                    "audit_estimator_estimable_probability": estimable_probability,
                    "audit_out_of_bounds_probability": float(
                        np.mean(values["out_of_bounds"])
                    ),
                    "mean_audit_rr_estimable": _finite_mean(values["rr"]),
                    "median_audit_rr_estimable": _finite_median(values["rr"]),
                    "median_absolute_log_rr_error_vs_scenario_latent": (
                        _finite_median(
                            values["absolute_log_rr_error_vs_scenario_latent"]
                        )
                    ),
                    "median_absolute_log_rr_error_vs_scenario_human_reference": (
                        _finite_median(
                            values[
                                "absolute_log_rr_error_vs_scenario_human_reference"
                            ]
                        )
                    ),
                    "audit_rr_bias_vs_scenario_latent_estimable": (
                        None
                        if _finite_mean(values["rr"]) is None
                        else float(_finite_mean(values["rr"]) - true_rr)
                    ),
                    "mean_audit_q_linux": _finite_mean(values["q_linux"]),
                    "mean_audit_q_windows": _finite_mean(values["q_windows"]),
                    "audit_q_linux_bias_vs_scenario_latent": (
                        None
                        if _finite_mean(values["q_linux"]) is None
                        else float(_finite_mean(values["q_linux"]) - true_q_linux)
                    ),
                    "audit_q_windows_bias_vs_scenario_latent": (
                        None
                        if _finite_mean(values["q_windows"]) is None
                        else float(_finite_mean(values["q_windows"]) - true_q_windows)
                    ),
                    "mean_q_linux_error_vs_latent_realized": _finite_mean(
                        values["q_linux_error_vs_latent_realized"]
                    ),
                    "mean_q_windows_error_vs_latent_realized": _finite_mean(
                        values["q_windows_error_vs_latent_realized"]
                    ),
                    "mean_q_linux_error_vs_human_realized": _finite_mean(
                        values["q_linux_error_vs_human_realized"]
                    ),
                    "mean_q_windows_error_vs_human_realized": _finite_mean(
                        values["q_windows_error_vs_human_realized"]
                    ),
                    "finite_human_reference_coverage_given_estimable": (
                        _conditional_probability(values["finite_coverage"])
                    ),
                    "finite_human_uncovered_or_unestimable_probability": float(
                        np.mean(values["finite_uncovered_or_unestimable"])
                    ),
                    "scenario_human_reference_coverage_given_estimable": (
                        _conditional_probability(values["repeated_coverage"])
                    ),
                    "scenario_human_reference_uncovered_or_unestimable_probability": (
                        float(np.mean(values["repeated_uncovered_or_unestimable"]))
                    ),
                    "scenario_latent_coverage_diagnostic_given_estimable": (
                        _conditional_probability(
                            values["repeated_latent_coverage_diagnostic"]
                        )
                    ),
                    "scenario_latent_uncovered_or_unestimable_diagnostic_probability": (
                        float(
                            np.mean(
                                values[
                                    "repeated_latent_uncovered_or_unestimable_diagnostic"
                                ]
                            )
                        )
                    ),
                    "mean_finite_human_interval_width": _finite_mean(
                        values["finite_interval_width"]
                    ),
                    "mean_optimistic_repeated_interval_width": _finite_mean(
                        values["repeated_interval_width"]
                    ),
                    "bonferroni_hypergeom_lower_estimable_probability": float(
                        np.mean(values["bonferroni_lower_estimable"])
                    ),
                    "bonferroni_hypergeom_finite_upper_probability": float(
                        np.mean(values["bonferroni_finite_upper"])
                    ),
                    "bonferroni_hypergeom_finite_human_coverage_given_lower_estimable": (
                        _conditional_probability(values["bonferroni_coverage"])
                    ),
                    "bonferroni_hypergeom_uncovered_or_lower_unestimable_probability": (
                        float(
                            np.mean(
                                values[
                                    "bonferroni_uncovered_or_lower_unestimable"
                                ]
                            )
                        )
                    ),
                    "mean_bonferroni_hypergeom_rr_lower": _finite_mean(
                        values["bonferroni_rr_lower"]
                    ),
                    "mean_bonferroni_hypergeom_interval_width_when_finite": (
                        _finite_mean(values["bonferroni_interval_width"])
                    ),
                    "mean_bonferroni_hypergeom_q_linux_width": _finite_mean(
                        values["bonferroni_q_linux_width"]
                    ),
                    "mean_bonferroni_hypergeom_q_windows_width": _finite_mean(
                        values["bonferroni_q_windows_width"]
                    ),
                    "bonferroni_hypergeom_ratio_above_2_probability": float(
                        np.mean(values["bonferroni_ratio_above_2"])
                    ),
                    "bonferroni_hypergeom_gate_and_ratio_above_2_probability": (
                        float(
                            np.mean(
                                values["bonferroni_gate_and_ratio_above_2"]
                            )
                        )
                    ),
                    "bonferroni_hypergeom_latent_null_threshold_clear_diagnostic_probability": (
                        float(
                            np.mean(
                                values["bonferroni_gate_and_ratio_above_2"]
                            )
                        )
                        if true_rr_is_null
                        else 0.0
                    ),
                    "mean_bonferroni_hypergeom_uncertain_components": float(
                        np.mean(values["bonferroni_uncertain_components"])
                    ),
                    "mean_bonferroni_hypergeom_component_confidence": float(
                        np.mean(values["bonferroni_component_confidence"])
                    ),
                    "bonferroni_hypergeom_analysis_note": (
                        "finite_human_reference_audit_only_not_D005_model"
                    ),
                    "audit_pooled_support_probability": float(
                        np.mean(values["pooled_support"])
                    ),
                    "audit_support_given_estimable": _conditional_probability(
                        values["support_given_estimable"]
                    ),
                    "audit_joint_confirmatory_support_probability": float(
                        np.mean(values["joint_support"])
                    ),
                    "audit_joint_false_support_probability": (
                        float(np.mean(values["joint_support"]))
                        if true_rr_is_null
                        else 0.0
                    ),
                    "mean_full_human_reference_rr_estimable": _finite_mean(
                        values["full_human_rr"]
                    ),
                    "full_human_reference_estimable_probability": float(
                        np.mean(values["full_human_estimable"])
                    ),
                    "full_human_reference_support_probability": float(
                        np.mean(values["full_human_support"])
                    ),
                    "full_human_pooled_scenario_coverage_given_estimable": (
                        _conditional_probability(
                            values["full_human_pooled_coverage"]
                        )
                    ),
                    "full_human_d005_multiway_estimable_probability": float(
                        np.mean(values["full_human_d005_estimable"])
                    ),
                    "full_human_d005_multiway_scenario_coverage_given_estimable": (
                        _conditional_probability(values["full_human_d005_coverage"])
                    ),
                    "full_human_d005_multiway_support_probability": float(
                        np.mean(values["full_human_d005_support"])
                    ),
                    "mean_full_human_d005_multiway_rr_lower": _finite_mean(
                        values["full_human_d005_rr_lower"]
                    ),
                    "audit_d005_multiway_estimable_probability": float(
                        np.mean(values["audit_d005_estimable"])
                    ),
                    "audit_d005_multiway_scenario_human_coverage_given_estimable": (
                        _conditional_probability(values["audit_d005_coverage"])
                    ),
                    "audit_d005_multiway_scenario_latent_coverage_diagnostic_given_estimable": (
                        _conditional_probability(
                            values["audit_d005_latent_coverage_diagnostic"]
                        )
                    ),
                    "audit_d005_multiway_support_probability": float(
                        np.mean(values["audit_d005_support"])
                    ),
                    "mean_audit_d005_multiway_rr_lower": _finite_mean(
                        values["audit_d005_rr_lower"]
                    ),
                    "d005_multiway_exact_audit_irr_coupled_support_probability": (
                        float(np.mean(values["d005_exact_audit_coupled_support"]))
                    ),
                    "d005_multiway_exact_audit_irr_coupled_latent_null_diagnostic_probability": (
                        float(np.mean(values["d005_exact_audit_coupled_support"]))
                        if true_rr_is_null
                        else 0.0
                    ),
                    "d005_multiway_candidate_note": (
                        "task_configuration_sandwich_t6_not_registered_GLMM_"
                        "requires_coverage_acceptance"
                    ),
                    "full_human_d005_finite_roster_estimable_probability": float(
                        np.mean(values["full_human_finite_d005_estimable"])
                    ),
                    "full_human_d005_finite_roster_scenario_coverage_given_estimable": (
                        _conditional_probability(
                            values["full_human_finite_d005_coverage"]
                        )
                    ),
                    "full_human_d005_finite_roster_support_probability": float(
                        np.mean(values["full_human_finite_d005_support"])
                    ),
                    "mean_full_human_d005_finite_roster_rr_lower": _finite_mean(
                        values["full_human_finite_d005_rr_lower"]
                    ),
                    "audit_d005_finite_roster_estimable_probability": float(
                        np.mean(values["audit_finite_d005_estimable"])
                    ),
                    "audit_d005_finite_roster_scenario_human_coverage_given_estimable": (
                        _conditional_probability(
                            values["audit_finite_d005_coverage"]
                        )
                    ),
                    "audit_d005_finite_roster_scenario_latent_coverage_diagnostic_given_estimable": (
                        _conditional_probability(
                            values[
                                "audit_finite_d005_latent_coverage_diagnostic"
                            ]
                        )
                    ),
                    "audit_d005_finite_roster_support_probability": float(
                        np.mean(values["audit_finite_d005_support"])
                    ),
                    "mean_audit_d005_finite_roster_rr_lower": _finite_mean(
                        values["audit_finite_d005_rr_lower"]
                    ),
                    "d005_finite_roster_exact_audit_irr_coupled_support_probability": (
                        float(
                            np.mean(
                                values["finite_d005_exact_audit_coupled_support"]
                            )
                        )
                    ),
                    "d005_finite_roster_exact_audit_irr_coupled_latent_null_diagnostic_probability": (
                        float(
                            np.mean(
                                values["finite_d005_exact_audit_coupled_support"]
                            )
                        )
                        if true_rr_is_null
                        else 0.0
                    ),
                    "d005_finite_roster_candidate_note": (
                        "falsified_cellwise_jeffreys_delta_"
                        "retained_as_negative_comparator"
                    ),
                    "d005_pooled_finite_roster_exact_audit_irr_coupled_support_probability": (
                        float(
                            np.mean(
                                values["pooled_d005_exact_audit_coupled_support"]
                            )
                        )
                    ),
                    "d005_pooled_finite_roster_exact_audit_irr_coupled_latent_null_diagnostic_probability": (
                        float(
                            np.mean(
                                values["pooled_d005_exact_audit_coupled_support"]
                            )
                        )
                        if true_rr_is_null
                        else 0.0
                    ),
                    "d005_pooled_finite_roster_candidate_note": (
                        "two_phase_pooled_normal_fixed_roster_candidate_"
                        "independent_trials_requires_coverage_acceptance"
                    ),
                    "irr_confirmatory_probability": float(
                        np.mean(common["irr_pass"])
                    ),
                    "naive_coder1_estimable_probability": float(
                        np.mean(common["naive_estimable"])
                    ),
                    "naive_coder1_mean_rr_estimable": _finite_mean(
                        common["naive_rr"]
                    ),
                    "naive_coder1_pooled_support_probability": float(
                        np.mean(common["naive_support"])
                    ),
                    "naive_coder1_joint_support_probability": float(
                        np.mean(common["naive_joint_support"])
                    ),
                    "latent_oracle_estimable_probability": float(
                        np.mean(common["oracle_estimable"])
                    ),
                    "latent_oracle_mean_rr_estimable": _finite_mean(
                        common["oracle_rr"]
                    ),
                    "latent_oracle_pooled_support_probability": float(
                        np.mean(common["oracle_support"])
                    ),
                    "latent_oracle_joint_support_probability": float(
                        np.mean(common["oracle_joint_support"])
                    ),
                    "true_conditional_de_linux": true_q_linux,
                    "true_conditional_de_windows": true_q_windows,
                    "true_conditional_de_rr": true_rr,
                    "scenario_human_reference_q_linux": scenario_human_q_linux,
                    "scenario_human_reference_q_windows": scenario_human_q_windows,
                    "scenario_human_reference_rr": scenario_human_rr,
                    "analysis_note": (
                        "two_phase_difference_pooled_reference_not_D005_mixed_model"
                    ),
                }
                rows.append(row)
    return rows


def run_enriched_audit_grid(
    *,
    replicates: int,
    seed: int,
    base_common_ns: Iterable[int] = (6, 12, 24),
    budgets: Iterable[int] = DEFAULT_AUDIT_BUDGETS,
    scenario_names: Sequence[str] | None = None,
    human_modes: Sequence[AuditHumanMode] | None = None,
    designs: Sequence[AuditDesign] | None = None,
) -> list[dict[str, float | int | str | None]]:
    canonical_scenario_names = (
        "high_quality_null",
        "high_quality_boundary",
        "shared_de_to_c_boundary",
        "high_quality_strong",
        "shared_de_to_c_strong",
    )
    scenario_names = tuple(
        canonical_scenario_names
        if scenario_names is None
        else scenario_names
    )
    human_modes = tuple(
        default_audit_human_modes() if human_modes is None else human_modes
    )
    designs = tuple(default_audit_designs() if designs is None else designs)
    scenarios = {
        scenario.name: scenario for scenario in default_joint_scenarios()
    }
    shared_strong = scenarios["shared_de_to_c_strong"]
    scenarios["shared_de_to_c_boundary"] = replace(
        shared_strong,
        name="shared_de_to_c_boundary",
        h2=replace(
            shared_strong.h2,
            name="shared_de_to_c_boundary",
            de_probability_windows=0.20,
        ),
    )
    if (
        not scenario_names
        or len(set(scenario_names)) != len(scenario_names)
        or any(name not in scenarios for name in scenario_names)
    ):
        raise ValueError("scenario names must be unique known scenarios")
    rows: list[dict[str, float | int | str | None]] = []
    for name in scenario_names:
        scenario_index = canonical_scenario_names.index(name)
        for n_index, base_n in enumerate(base_common_ns):
            rows.extend(
                simulate_enriched_audit_scenario(
                    scenarios[name],
                    base_common_n=base_n,
                    replicates=replicates,
                    seed=seed + 100_000 * scenario_index + 1_000 * n_index,
                    budgets=budgets,
                    human_modes=human_modes,
                    designs=designs,
                )
            )
    return rows


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run probability-sampled enriched H2 audit simulations."
    )
    parser.add_argument("--replicates", type=int, default=1_000)
    parser.add_argument("--seed", type=int, default=20260802)
    parser.add_argument(
        "--base-common-ns",
        nargs="+",
        type=int,
        default=[6, 12, 24],
    )
    parser.add_argument(
        "--budgets",
        nargs="+",
        type=int,
        default=list(DEFAULT_AUDIT_BUDGETS),
    )
    parser.add_argument(
        "--scenarios",
        nargs="+",
        choices=(
            "high_quality_null",
            "high_quality_boundary",
            "shared_de_to_c_boundary",
            "high_quality_strong",
            "shared_de_to_c_strong",
        ),
    )
    parser.add_argument(
        "--human-modes",
        nargs="+",
        choices=tuple(mode.name for mode in default_audit_human_modes()),
        default=[mode.name for mode in default_audit_human_modes()],
    )
    parser.add_argument(
        "--designs",
        nargs="+",
        choices=tuple(design.name for design in default_audit_designs()),
        default=[design.name for design in default_audit_designs()],
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.replicates < 1:
        raise SystemExit("--replicates must be positive")
    for row in run_enriched_audit_grid(
        replicates=args.replicates,
        seed=args.seed,
        base_common_ns=args.base_common_ns,
        budgets=args.budgets,
        scenario_names=args.scenarios,
        human_modes=tuple(
            mode
            for mode in default_audit_human_modes()
            if mode.name in args.human_modes
        ),
        designs=tuple(
            design
            for design in default_audit_designs()
            if design.name in args.designs
        ),
    ):
        print(json.dumps(row, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
