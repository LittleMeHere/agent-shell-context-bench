"""Executable V2 finite-roster H1 interval candidates.

This module is implementation evidence for D-005, not an acceptance record.
It preserves the accepted equal domain/family/instance/configuration weights
and treats every registered leaf as a fixed binomial cell.  The leading
candidate is a Clopper-Pearson-MOVER interval for a linear combination of
independent binomial proportions.  The narrower Wilson-MOVER implementation
is retained only as a falsified comparator. If any leaf has fewer than the
prospectively required three observations, analysis falls back to a simultaneous
Clopper-Pearson/Bonferroni envelope and therefore becomes safely
inconclusive rather than silently pooling sparse cells.
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
from analysis.v2_analysis_dataset import (
    FOCAL_ENVIRONMENTS,
    AnalysisDatasetError,
    AnalysisTrial,
    accepted_family_domains,
)


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
    unknown = sorted({row.family_id for row in focal} - set(family_domains))
    if unknown:
        raise AnalysisDatasetError(f"unknown capability families: {unknown}")

    configurations = sorted({row.config_id for row in focal})
    domains = sorted(set(family_domains.values()))
    families_by_domain = {
        domain: sorted(
            family for family, value in family_domains.items() if value == domain
        )
        for domain in domains
    }
    instances_by_family = {
        family: sorted(
            {row.instance_id for row in focal if row.family_id == family}
        )
        for family in family_domains
    }
    if any(not values for values in instances_by_family.values()):
        raise AnalysisDatasetError("one or more accepted families have no instances")

    leaf: defaultdict[tuple[str, str, str, str], list[bool]] = defaultdict(list)
    for row in focal:
        leaf[(row.env_id, row.config_id, row.family_id, row.instance_id)].append(
            bool(row.failed)
        )

    ordered_keys: list[tuple[str, str, str]] = []
    weights: list[float] = []
    for configuration in configurations:
        for domain in domains:
            for family in families_by_domain[domain]:
                for instance in instances_by_family[family]:
                    ordered_keys.append((configuration, family, instance))
                    weights.append(
                        1.0
                        / len(configurations)
                        / len(domains)
                        / len(families_by_domain[domain])
                        / len(instances_by_family[family])
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


def finite_roster_h1_candidate(
    trials: Sequence[AnalysisTrial],
    *,
    family_domains: Mapping[str, str] | None = None,
    confidence: float = 0.95,
    minimum_primary_cell_n: int = 3,
) -> FiniteRosterH1Candidate:
    """Evaluate the executable D-005 candidate and deterministic fallback."""

    if minimum_primary_cell_n < 1:
        raise ValueError("minimum_primary_cell_n must be positive")
    events, totals, weights = _finite_roster_cells(
        trials, dict(family_domains or accepted_family_domains())
    )
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


def finite_roster_epoch_sensitivity(
    trials: Sequence[AnalysisTrial],
    *,
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

    resolved_epochs = tuple(expected_epochs)
    if (
        not resolved_epochs
        or any(type(epoch) is not int or epoch < 0 for epoch in resolved_epochs)
        or len(set(resolved_epochs)) != len(resolved_epochs)
    ):
        raise ValueError("expected_epochs must be unique nonnegative integers")
    accepted_domains = dict(family_domains or accepted_family_domains())
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
            result = finite_roster_h1_candidate(
                capability_rows,
                family_domains=epoch_domains,
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
