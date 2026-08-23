"""Executable V2 finite-roster H1 interval candidates.

This module is implementation evidence for D-005, not an acceptance record.
It preserves the accepted equal domain/family/instance/configuration weights
and treats every registered leaf as a fixed binomial cell.  The leading
candidate is a Clopper-Pearson-MOVER interval for a linear combination of
independent binomial proportions.  The narrower Wilson-MOVER implementation
is retained only as a falsified comparator. If any leaf has fewer than the
prospectively required three observations, analysis falls back to a simultaneous
Clopper-Pearson/Bonferroni envelope rather than silently pooling sparse cells.
"""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass
from statistics import NormalDist
from typing import Mapping, Sequence

import numpy as np
from numpy.typing import NDArray
from scipy.stats import beta

from analysis.d013_ceiling_operating_characteristics import DECISION_RD
from analysis.d013_task_bank_design import REGISTERED_CONFIG_IDS
from analysis.v2_analysis_dataset import (
    FOCAL_ENVIRONMENTS,
    AnalysisDatasetError,
    AnalysisTrial,
    accepted_family_domains,
)
from harness.scheduler import SchedulePlan, validate_plan, v2_pilot_epoch_for_position


LeafKey = tuple[str, str, str, str]


def expected_h1_leaf_counts_from_plan(
    plan: SchedulePlan,
    *,
    family_domains: Mapping[str, str] | None = None,
    expected_configurations: Sequence[str] = REGISTERED_CONFIG_IDS,
) -> dict[LeafKey, int]:
    """Derive the exact H1 leaf/count roster from a validated schedule plan."""

    families = set((family_domains or accepted_family_domains()).keys())
    configurations = set(expected_configurations)
    counts: dict[LeafKey, int] = {}
    for cell in plan.cells:
        if (
            cell.env_id not in FOCAL_ENVIRONMENTS
            or cell.config_id not in configurations
            or cell.family_id not in families
        ):
            continue
        key = (cell.env_id, cell.config_id, cell.family_id, cell.instance_id)
        if key in counts:
            raise AnalysisDatasetError(
                f"schedule plan contains a duplicate H1 leaf: {key}"
            )
        counts[key] = cell.target_valid_trials
    if not counts:
        raise AnalysisDatasetError("schedule plan contains no registered H1 leaves")
    return counts


def expected_h1_cell_membership_from_plan(
    plan: SchedulePlan,
    *,
    family_domains: Mapping[str, str] | None = None,
    expected_configurations: Sequence[str] = REGISTERED_CONFIG_IDS,
) -> dict[str, LeafKey]:
    """Bind every eligible plan cell ID to its registered H1 leaf."""

    families = set((family_domains or accepted_family_domains()).keys())
    configurations = set(expected_configurations)
    membership: dict[str, LeafKey] = {}
    for cell in plan.cells:
        if (
            cell.env_id not in FOCAL_ENVIRONMENTS
            or cell.config_id not in configurations
            or cell.family_id not in families
        ):
            continue
        if cell.cell_id in membership:
            raise AnalysisDatasetError(
                f"schedule plan contains duplicate cell ID {cell.cell_id}"
            )
        membership[cell.cell_id] = (
            cell.env_id,
            cell.config_id,
            cell.family_id,
            cell.instance_id,
        )
    if not membership:
        raise AnalysisDatasetError("schedule plan contains no registered H1 cells")
    return membership


def expected_h1_leaf_counts_by_v2_pilot_epoch(
    plan: SchedulePlan,
    *,
    family_domains: Mapping[str, str] | None = None,
    expected_configurations: Sequence[str],
    expected_epochs: Sequence[int] = (0, 1, 2, 3),
) -> dict[int, dict[LeafKey, int]]:
    """Derive the exact plan-owned H1 counts for each frozen V2 pilot epoch."""

    if plan.execution_slots is None:
        raise AnalysisDatasetError("schedule plan has no execution-slot roster")
    families = set((family_domains or accepted_family_domains()).keys())
    configurations = set(expected_configurations)
    cells = {cell.cell_id: cell for cell in plan.cells}
    counts: dict[int, dict[LeafKey, int]] = {
        epoch: {} for epoch in expected_epochs
    }
    for slot in plan.execution_slots:
        cell = cells[slot.cell_id]
        if (
            cell.env_id not in FOCAL_ENVIRONMENTS
            or cell.config_id not in configurations
            or cell.family_id not in families
        ):
            continue
        epoch = v2_pilot_epoch_for_position(slot.position)
        if epoch not in counts:
            raise AnalysisDatasetError(
                f"schedule slot maps to unregistered epoch {epoch}"
            )
        key = (cell.env_id, cell.config_id, cell.family_id, cell.instance_id)
        counts[epoch][key] = counts[epoch].get(key, 0) + 1
    return counts


@dataclass(frozen=True)
class LinearBinomialInterval:
    estimate: float
    lower: float
    upper: float
    confidence: float
    method: str
    cells: int
    minimum_cell_n: int


@dataclass(frozen=True)
class FiniteRosterH1Candidate:
    windows_failure_rate: float
    linux_failure_rate: float
    risk_difference: float
    risk_difference_lower: float
    risk_difference_upper: float
    risk_ratio: float
    risk_ratio_lower: float
    risk_ratio_upper: float
    confidence: float
    interval_method: str
    fallback_used: bool
    fallback_reason: str | None
    decision: str
    cells_per_context: int
    minimum_cell_n: int
    trials: int


@dataclass(frozen=True)
class FiniteRosterEpochResult:
    epoch_index: int
    status: str
    capability_trials: int
    family_count: int
    result: FiniteRosterH1Candidate | None
    reason: str | None


def _validated_arrays(
    event_count: Sequence[int] | NDArray[np.int64],
    total_count: Sequence[int] | NDArray[np.int64],
    coefficients: Sequence[float] | NDArray[np.float64],
) -> tuple[NDArray[np.int64], NDArray[np.int64], NDArray[np.float64]]:
    events = np.asarray(event_count)
    totals = np.asarray(total_count)
    coeffs = np.asarray(coefficients, dtype=float)
    if events.ndim != 1 or totals.ndim != 1 or coeffs.ndim != 1:
        raise ValueError("events, totals, and coefficients must be one-dimensional")
    if events.size == 0 or not (events.shape == totals.shape == coeffs.shape):
        raise ValueError("events, totals, and coefficients must have equal nonzero size")
    if not np.issubdtype(events.dtype, np.integer) or not np.issubdtype(
        totals.dtype, np.integer
    ):
        raise ValueError("events and totals must be integer arrays")
    if np.any(totals < 1) or np.any(events < 0) or np.any(events > totals):
        raise ValueError("binomial counts are invalid")
    if not np.all(np.isfinite(coeffs)) or np.all(coeffs == 0.0):
        raise ValueError("coefficients must be finite and not all zero")
    return events.astype(np.int64), totals.astype(np.int64), coeffs


def _wilson_limits(
    events: NDArray[np.int64],
    totals: NDArray[np.int64],
    confidence: float,
) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    if not 0.0 < confidence < 1.0:
        raise ValueError("confidence must lie strictly between zero and one")
    z_value = NormalDist().inv_cdf(0.5 + confidence / 2.0)
    z2 = z_value**2
    proportion = events / totals
    denominator = 1.0 + z2 / totals
    center = (proportion + z2 / (2.0 * totals)) / denominator
    half_width = (
        z_value
        * np.sqrt(
            proportion * (1.0 - proportion) / totals
            + z2 / (4.0 * totals**2)
        )
        / denominator
    )
    return np.maximum(0.0, center - half_width), np.minimum(
        1.0, center + half_width
    )


def mover_wilson_linear_interval(
    event_count: Sequence[int] | NDArray[np.int64],
    total_count: Sequence[int] | NDArray[np.int64],
    coefficients: Sequence[float] | NDArray[np.float64],
    *,
    confidence: float = 0.95,
) -> LinearBinomialInterval:
    """Wilson-MOVER interval for a fixed linear combination of proportions."""

    events, totals, coeffs = _validated_arrays(
        event_count, total_count, coefficients
    )
    lower_cell, upper_cell = _wilson_limits(events, totals, confidence)
    proportion = events / totals
    component = coeffs * proportion
    low_component = np.minimum(coeffs * lower_cell, coeffs * upper_cell)
    high_component = np.maximum(coeffs * lower_cell, coeffs * upper_cell)
    estimate = float(np.sum(component))
    lower = estimate - math.sqrt(float(np.sum((component - low_component) ** 2)))
    upper = estimate + math.sqrt(float(np.sum((high_component - component) ** 2)))
    return LinearBinomialInterval(
        estimate=estimate,
        lower=lower,
        upper=upper,
        confidence=confidence,
        method="mover_wilson_fixed_roster_candidate",
        cells=int(events.size),
        minimum_cell_n=int(np.min(totals)),
    )


def mover_clopper_pearson_linear_interval(
    event_count: Sequence[int] | NDArray[np.int64],
    total_count: Sequence[int] | NDArray[np.int64],
    coefficients: Sequence[float] | NDArray[np.float64],
    *,
    confidence: float = 0.95,
) -> LinearBinomialInterval:
    """Clopper-Pearson-MOVER candidate for a fixed linear combination."""

    events, totals, coeffs = _validated_arrays(
        event_count, total_count, coefficients
    )
    if not 0.0 < confidence < 1.0:
        raise ValueError("confidence must lie strictly between zero and one")
    tail = (1.0 - confidence) / 2.0
    lower_cell = np.zeros(events.size, dtype=float)
    upper_cell = np.ones(events.size, dtype=float)
    positive = events > 0
    below_total = events < totals
    lower_cell[positive] = beta.ppf(
        tail, events[positive], totals[positive] - events[positive] + 1
    )
    upper_cell[below_total] = beta.ppf(
        1.0 - tail,
        events[below_total] + 1,
        totals[below_total] - events[below_total],
    )
    proportion = events / totals
    component = coeffs * proportion
    low_component = np.minimum(coeffs * lower_cell, coeffs * upper_cell)
    high_component = np.maximum(coeffs * lower_cell, coeffs * upper_cell)
    estimate = float(np.sum(component))
    lower = estimate - math.sqrt(float(np.sum((component - low_component) ** 2)))
    upper = estimate + math.sqrt(float(np.sum((high_component - component) ** 2)))
    return LinearBinomialInterval(
        estimate=estimate,
        lower=lower,
        upper=upper,
        confidence=confidence,
        method="mover_clopper_pearson_fixed_roster_candidate",
        cells=int(events.size),
        minimum_cell_n=int(np.min(totals)),
    )


def bonferroni_clopper_pearson_linear_interval(
    event_count: Sequence[int] | NDArray[np.int64],
    total_count: Sequence[int] | NDArray[np.int64],
    coefficients: Sequence[float] | NDArray[np.float64],
    *,
    confidence: float = 0.95,
) -> LinearBinomialInterval:
    """Simultaneous exact-cell envelope for a linear binomial estimand."""

    events, totals, coeffs = _validated_arrays(
        event_count, total_count, coefficients
    )
    if not 0.0 < confidence < 1.0:
        raise ValueError("confidence must lie strictly between zero and one")
    tail = (1.0 - confidence) / (2.0 * events.size)
    lower_cell = np.zeros(events.size, dtype=float)
    upper_cell = np.ones(events.size, dtype=float)
    positive = events > 0
    below_total = events < totals
    lower_cell[positive] = beta.ppf(
        tail, events[positive], totals[positive] - events[positive] + 1
    )
    upper_cell[below_total] = beta.ppf(
        1.0 - tail,
        events[below_total] + 1,
        totals[below_total] - events[below_total],
    )
    proportion = events / totals
    estimate = float(np.sum(coeffs * proportion))
    lower = float(
        np.sum(np.minimum(coeffs * lower_cell, coeffs * upper_cell))
    )
    upper = float(
        np.sum(np.maximum(coeffs * lower_cell, coeffs * upper_cell))
    )
    return LinearBinomialInterval(
        estimate=estimate,
        lower=lower,
        upper=upper,
        confidence=confidence,
        method="bonferroni_clopper_pearson_fallback",
        cells=int(events.size),
        minimum_cell_n=int(np.min(totals)),
    )


def _finite_roster_cells(
    trials: Sequence[AnalysisTrial],
    family_domains: Mapping[str, str],
    expected_configurations: Sequence[str],
    plan: SchedulePlan,
    expected_leaf_counts: Mapping[LeafKey, int] | None = None,
) -> tuple[
    dict[str, NDArray[np.int64]],
    dict[str, NDArray[np.int64]],
    NDArray[np.float64],
]:
    focal = [
        row
        for row in trials
        if row.valid_analysis_trial
        and row.task_category == "capability"
        and row.env_id in FOCAL_ENVIRONMENTS
    ]
    if not focal or any(row.failed is None for row in focal):
        raise AnalysisDatasetError("valid focal capability outcomes are incomplete")
    if any(row.plan_digest != plan.digest for row in focal):
        raise AnalysisDatasetError("analysis row is bound to a different schedule plan")
    if expected_leaf_counts is None:
        expected_leaf_counts = expected_h1_leaf_counts_from_plan(
            plan,
            family_domains=family_domains,
            expected_configurations=expected_configurations,
        )
    expected_cell_membership = expected_h1_cell_membership_from_plan(
        plan,
        family_domains=family_domains,
        expected_configurations=expected_configurations,
    )
    for row in focal:
        observed_leaf = (
            row.env_id,
            row.config_id,
            row.family_id,
            row.instance_id,
        )
        expected_leaf = expected_cell_membership.get(row.cell_id)
        if expected_leaf is None or expected_leaf != observed_leaf:
            raise AnalysisDatasetError(
                "analysis row identity differs from its registered plan cell: "
                f"cell_id={row.cell_id!r}, expected={expected_leaf!r}, "
                f"observed={observed_leaf!r}"
            )
    unknown = sorted({row.family_id for row in focal} - set(family_domains))
    if unknown:
        raise AnalysisDatasetError(f"unknown capability families: {unknown}")

    configurations = tuple(expected_configurations)
    if not configurations or len(set(configurations)) != len(configurations):
        raise ValueError("expected_configurations must be nonempty and unique")
    observed_configurations = {row.config_id for row in focal}
    registered_configurations = set(configurations)
    if observed_configurations != registered_configurations:
        missing = sorted(registered_configurations - observed_configurations)
        extra = sorted(observed_configurations - registered_configurations)
        raise AnalysisDatasetError(
            "focal configuration roster differs from the registered roster: "
            f"missing={missing}, extra={extra}"
        )
    domains = sorted(set(family_domains.values()))
    families_by_domain = {
        domain: sorted(
            family for family, value in family_domains.items() if value == domain
        )
        for domain in domains
    }
    if not expected_leaf_counts:
        raise ValueError("expected_leaf_counts must be nonempty")
    for key, count in expected_leaf_counts.items():
        if (
            not isinstance(key, tuple)
            or len(key) != 4
            or not all(isinstance(value, str) and value for value in key)
            or isinstance(count, bool)
            or not isinstance(count, int)
            or count < 1
        ):
            raise ValueError(
                "expected_leaf_counts must map four-string leaf keys to "
                "positive integers"
            )

    registered_families = set(family_domains)
    registered_instances = {
        family: sorted(
            {
                instance
                for (_env, _config, observed_family, instance) in expected_leaf_counts
                if observed_family == family
            }
        )
        for family in family_domains
    }
    if any(not values for values in registered_instances.values()):
        raise AnalysisDatasetError(
            "registered leaf-count roster omits one or more accepted families"
        )

    leaf: defaultdict[LeafKey, list[bool]] = defaultdict(list)
    for row in focal:
        leaf[(row.env_id, row.config_id, row.family_id, row.instance_id)].append(
            bool(row.failed)
        )

    ordered_keys: list[tuple[str, str, str]] = []
    weights: list[float] = []
    for configuration in configurations:
        for domain in domains:
            for family in families_by_domain[domain]:
                for instance in registered_instances[family]:
                    ordered_keys.append((configuration, family, instance))
                    weights.append(
                        1.0
                        / len(configurations)
                        / len(domains)
                        / len(families_by_domain[domain])
                        / len(registered_instances[family])
                    )
    expected = {
        (environment, configuration, family, instance)
        for environment in FOCAL_ENVIRONMENTS
        for configuration, family, instance in ordered_keys
    }
    if set(leaf) != expected:
        missing = sorted(expected - set(leaf))[:5]
        extra = sorted(set(leaf) - expected)[:5]
        raise AnalysisDatasetError(
            f"focal finite roster is not a complete crossing: missing={missing}, extra={extra}"
        )
    if set(expected_leaf_counts) != expected:
        missing = sorted(expected - set(expected_leaf_counts))[:5]
        extra = sorted(set(expected_leaf_counts) - expected)[:5]
        raise AnalysisDatasetError(
            "registered leaf-count roster differs from the finite estimand: "
            f"missing={missing}, extra={extra}"
        )
    count_mismatches = [
        (key, expected_leaf_counts[key], len(leaf[key]))
        for key in sorted(expected)
        if len(leaf[key]) != expected_leaf_counts[key]
    ]
    if count_mismatches:
        raise AnalysisDatasetError(
            "focal leaf counts differ from the registered plan: "
            f"expected/observed={count_mismatches[:5]}"
        )

    totals: dict[str, NDArray[np.int64]] = {}
    events: dict[str, NDArray[np.int64]] = {}
    for environment in FOCAL_ENVIRONMENTS:
        values = [leaf[(environment, *key)] for key in ordered_keys]
        totals[environment] = np.asarray([len(item) for item in values], dtype=np.int64)
        events[environment] = np.asarray(
            [sum(item) for item in values], dtype=np.int64
        )
    weight_array = np.asarray(weights, dtype=float)
    if not math.isclose(float(np.sum(weight_array)), 1.0, abs_tol=1e-12):
        raise AnalysisDatasetError("finite-roster weights do not sum to one")
    return events, totals, weight_array


def _candidate_from_cells(
    events: Mapping[str, NDArray[np.int64]],
    totals: Mapping[str, NDArray[np.int64]],
    weights: NDArray[np.float64],
    *,
    confidence: float,
    minimum_primary_cell_n: int,
) -> FiniteRosterH1Candidate:
    windows_events = events["windows_powershell"]
    linux_events = events["linux_native"]
    windows_totals = totals["windows_powershell"]
    linux_totals = totals["linux_native"]
    combined_events = np.concatenate((windows_events, linux_events))
    combined_totals = np.concatenate((windows_totals, linux_totals))
    rd_coefficients = np.concatenate((weights, -weights))
    minimum_cell_n = int(np.min(combined_totals))
    fallback_used = minimum_cell_n < minimum_primary_cell_n
    interval_fn = (
        bonferroni_clopper_pearson_linear_interval
        if fallback_used
        else mover_clopper_pearson_linear_interval
    )
    rd = interval_fn(
        combined_events,
        combined_totals,
        rd_coefficients,
        confidence=confidence,
    )

    # Use two marginal intervals with Bonferroni confidence allocation to
    # provide a boundary-safe companion RR envelope.
    marginal_confidence = 1.0 - (1.0 - confidence) / 2.0
    windows = interval_fn(
        windows_events, windows_totals, weights, confidence=marginal_confidence
    )
    linux = interval_fn(
        linux_events, linux_totals, weights, confidence=marginal_confidence
    )
    windows_lower = max(0.0, windows.lower)
    windows_upper = min(1.0, windows.upper)
    linux_lower = max(0.0, linux.lower)
    linux_upper = min(1.0, linux.upper)
    ratio = (
        windows.estimate / linux.estimate
        if linux.estimate > 0.0
        else math.inf if windows.estimate > 0.0 else math.nan
    )
    ratio_lower = windows_lower / linux_upper if linux_upper > 0.0 else math.nan
    ratio_upper = windows_upper / linux_lower if linux_lower > 0.0 else math.inf

    rd_lower = max(-1.0, rd.lower)
    rd_upper = min(1.0, rd.upper)
    if rd_lower > DECISION_RD:
        decision = "decision_relevant_context_penalty"
    elif rd_upper < DECISION_RD:
        decision = "bounded_below_five_points"
    else:
        decision = "inconclusive"
    return FiniteRosterH1Candidate(
        windows_failure_rate=windows.estimate,
        linux_failure_rate=linux.estimate,
        risk_difference=rd.estimate,
        risk_difference_lower=rd_lower,
        risk_difference_upper=rd_upper,
        risk_ratio=ratio,
        risk_ratio_lower=ratio_lower,
        risk_ratio_upper=ratio_upper,
        confidence=confidence,
        interval_method=rd.method,
        fallback_used=fallback_used,
        fallback_reason=(
            f"minimum_cell_n_below_{minimum_primary_cell_n}"
            if fallback_used
            else None
        ),
        decision=decision,
        cells_per_context=int(weights.size),
        minimum_cell_n=minimum_cell_n,
        trials=int(np.sum(combined_totals)),
    )


def finite_roster_h1_candidate(
    trials: Sequence[AnalysisTrial],
    *,
    plan: SchedulePlan,
    family_domains: Mapping[str, str] | None = None,
    confidence: float = 0.95,
    minimum_primary_cell_n: int = 3,
    expected_configurations: Sequence[str] = REGISTERED_CONFIG_IDS,
) -> FiniteRosterH1Candidate:
    """Evaluate the plan-bound D-005 candidate and deterministic fallback."""

    validate_plan(plan)
    if minimum_primary_cell_n < 1:
        raise ValueError("minimum_primary_cell_n must be positive")
    events, totals, weights = _finite_roster_cells(
        trials,
        dict(family_domains or accepted_family_domains()),
        expected_configurations,
        plan,
    )
    return _candidate_from_cells(
        events,
        totals,
        weights,
        confidence=confidence,
        minimum_primary_cell_n=minimum_primary_cell_n,
    )


def finite_roster_epoch_sensitivity(
    trials: Sequence[AnalysisTrial],
    *,
    expected_configurations: Sequence[str],
    plan: SchedulePlan,
    family_domains: Mapping[str, str] | None = None,
    expected_epochs: Sequence[int] = (0, 1, 2, 3),
    confidence: float = 0.95,
    minimum_primary_cell_n: int = 3,
) -> tuple[FiniteRosterEpochResult, ...]:
    """Report the fixed-roster H1 contrast separately in each planned epoch.

    Epochs are never pooled or reweighted across task compositions. An epoch
    without focal capability trials is explicitly not applicable; an epoch
    with a partial environment/configuration/family/instance crossing is
    explicitly not estimable.
    """

    validate_plan(plan)
    resolved_epochs = tuple(expected_epochs)
    if (
        not resolved_epochs
        or any(type(epoch) is not int or epoch < 0 for epoch in resolved_epochs)
        or len(set(resolved_epochs)) != len(resolved_epochs)
    ):
        raise ValueError("expected_epochs must be unique nonnegative integers")
    accepted_domains = dict(family_domains or accepted_family_domains())
    expected_leaf_counts_by_epoch = expected_h1_leaf_counts_by_v2_pilot_epoch(
        plan,
        family_domains=family_domains,
        expected_configurations=expected_configurations,
        expected_epochs=resolved_epochs,
    )
    if set(expected_leaf_counts_by_epoch) != set(resolved_epochs):
        raise ValueError(
            "expected_leaf_counts_by_epoch must define every registered epoch"
        )
    unknown_epoch_rows = sorted(
        {
            row.collection_epoch
            for row in trials
            if row.valid_analysis_trial
            and row.collection_epoch is not None
            and row.collection_epoch not in resolved_epochs
        }
    )
    if unknown_epoch_rows:
        raise AnalysisDatasetError(
            f"analysis rows contain unexpected collection epochs: {unknown_epoch_rows}"
        )

    reports: list[FiniteRosterEpochResult] = []
    for epoch in resolved_epochs:
        epoch_rows = [
            row
            for row in trials
            if row.valid_analysis_trial and row.collection_epoch == epoch
        ]
        capability_rows = [
            row
            for row in epoch_rows
            if row.task_category == "capability" and row.env_id in FOCAL_ENVIRONMENTS
        ]
        families = sorted({row.family_id for row in capability_rows})
        if not capability_rows:
            reports.append(
                FiniteRosterEpochResult(
                    epoch_index=epoch,
                    status="not_applicable_no_capability_trials",
                    capability_trials=0,
                    family_count=0,
                    result=None,
                    reason="planned_epoch_contains_no_focal_capability_trials",
                )
            )
            continue
        unknown_families = sorted(set(families) - set(accepted_domains))
        if unknown_families:
            raise AnalysisDatasetError(
                f"epoch {epoch} contains unknown capability families: {unknown_families}"
            )
        epoch_domains = {family: accepted_domains[family] for family in families}
        try:
            events, totals, weights = _finite_roster_cells(
                capability_rows,
                epoch_domains,
                expected_configurations,
                plan,
                expected_leaf_counts_by_epoch[epoch],
            )
            result = _candidate_from_cells(
                events,
                totals,
                weights,
                confidence=confidence,
                minimum_primary_cell_n=minimum_primary_cell_n,
            )
        except AnalysisDatasetError as exc:
            reports.append(
                FiniteRosterEpochResult(
                    epoch_index=epoch,
                    status="not_estimable_incomplete_crossing",
                    capability_trials=len(capability_rows),
                    family_count=len(families),
                    result=None,
                    reason=str(exc),
                )
            )
        else:
            reports.append(
                FiniteRosterEpochResult(
                    epoch_index=epoch,
                    status="estimated",
                    capability_trials=len(capability_rows),
                    family_count=len(families),
                    result=result,
                    reason=None,
                )
            )
    return tuple(reports)
