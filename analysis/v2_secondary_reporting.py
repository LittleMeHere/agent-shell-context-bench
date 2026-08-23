"""Plan-bound descriptive A2/A4 outputs and fixed-block A3 inference.

The V2 amendment deliberately makes H2 and H4 exploratory. Their uncertainty
and A3 inference use accepted fixed complete-crossing block bootstraps. This
module implements:

* an exact one-to-one join between the validated analysis roster and the
  frozen primary-coder join result;
* the registered A2 and A4 populations, denominators, missing-label counts,
  raw D/E rates, and explicitly descriptive Wilson intervals;
* plan-bound finite-roster A3 inference and the hardcoded five-percentage-
  point inconclusive guardrail; and
* deterministic, JSON-safe report tables whose status fields prevent a raw
  descriptive comparison from being presented as a confirmatory decision.

No missing-label repair, H2 support threshold, H4 significance decision, or
generic phrasing-mechanism claim is selected here by implication.
"""

from __future__ import annotations

import dataclasses
import math
from collections import defaultdict
from dataclasses import dataclass
from typing import Mapping, Sequence

import numpy as np
from scipy.stats import norm

from analysis.d013_task_bank_design import REGISTERED_CONFIG_IDS
from analysis.v2_analysis_dataset import (
    AnalysisDatasetError,
    AnalysisTrial,
    accepted_family_domains,
)
from analysis.v2_coder_join import CoderJoinResult
from analysis.v2_finite_roster import FiniteRosterH1Candidate
from harness.scheduler import ENVIRONMENTS, SchedulePlan, validate_plan


H2_CONTEXTS = ("windows_powershell", "linux_native")
H3_CONTEXTS = ("windows_powershell", "windows_wsl2", "linux_native")
H4_PHRASINGS = ("formal", "colloquial")
FINAL_CODES = frozenset("ABCDEF")
A3_INCONCLUSIVE_GAP = 0.05
A3_BOOTSTRAP_RESAMPLES = 10_000
A3_BOOTSTRAP_SEED = 20260525
A3_CONFIG_FDR_Q = 0.05
A2_BOOTSTRAP_RESAMPLES = 10_000
A2_BOOTSTRAP_SEED = 20260526
A4_BOOTSTRAP_RESAMPLES = 10_000
A4_BOOTSTRAP_SEED = 20260527

TrialIdentity = tuple[str, str, int, str]


class SecondaryAnalysisError(ValueError):
    """The secondary analysis cannot proceed without silent repair."""


@dataclass(frozen=True)
class DescriptiveBinomialGroup:
    group: str
    denominator: int
    labelled: int
    missing_labels: int
    de_events: int
    de_rate: float | None
    lower: float | None
    upper: float | None
    interval_method: str


@dataclass(frozen=True)
class DescriptiveContrast:
    first_group: str
    second_group: str
    risk_difference: float | None
    risk_ratio: float | None
    risk_ratio_status: str
    inferential_status: str


@dataclass(frozen=True)
class BootstrapInterval:
    estimate: float | None
    lower: float | None
    upper: float | None
    defined_draws: int
    total_draws: int


@dataclass(frozen=True)
class MissingLabelBounds:
    first_rate_lower: float | None
    first_rate_upper: float | None
    second_rate_lower: float | None
    second_rate_upper: float | None
    risk_difference_lower: float | None
    risk_difference_upper: float | None
    risk_ratio_lower: float | None
    risk_ratio_upper: float | None
    risk_ratio_status: str


@dataclass(frozen=True)
class ExploratoryBootstrapResult:
    seed: int
    resamples: int
    first_rate: BootstrapInterval
    second_rate: BootstrapInterval
    risk_difference: BootstrapInterval
    risk_ratio: BootstrapInterval
    risk_ratio_infinite_draws: int
    risk_ratio_undefined_draws: int
    method: str


@dataclass(frozen=True)
class A2DescriptiveResult:
    status: str
    groups: tuple[DescriptiveBinomialGroup, ...]
    contrast: DescriptiveContrast
    by_configuration: tuple[DescriptiveBinomialGroup, ...]
    registered_population: str
    claim_scope: str
    missing_label_bounds: MissingLabelBounds | None = None
    bootstrap: ExploratoryBootstrapResult | None = None


@dataclass(frozen=True)
class A3ConfigurationResult:
    config_id: str
    windows_minus_wsl2: float
    wsl2_minus_linux: float
    windows_minus_wsl2_one_sided_p: float
    wsl2_minus_linux_one_sided_p: float
    intersection_union_p: float
    bh_reject: bool


@dataclass(frozen=True)
class A3PointResult:
    status: str
    windows_failure_rate: float
    wsl2_failure_rate: float
    linux_failure_rate: float
    windows_minus_wsl2: float
    wsl2_minus_linux: float
    distance_difference: float
    windows_linux_absolute_gap: float
    point_ordering_holds: bool
    trials: int
    inferential_status: str
    windows_minus_wsl2_lower: float | None
    windows_minus_wsl2_upper: float | None
    wsl2_minus_linux_lower: float | None
    wsl2_minus_linux_upper: float | None
    distance_difference_lower: float | None
    distance_difference_upper: float | None
    a3a_ordering_supported: bool | None
    a3b_closer_to_linux_supported: bool | None
    bootstrap_resamples: int
    bootstrap_seed: int
    per_configuration: tuple[A3ConfigurationResult, ...]


@dataclass(frozen=True)
class A4DescriptiveResult:
    status: str
    groups: tuple[DescriptiveBinomialGroup, ...]
    contrast: DescriptiveContrast
    by_task: tuple[DescriptiveBinomialGroup, ...]
    registered_population: str
    claim_scope: str
    missing_label_bounds: MissingLabelBounds | None = None
    bootstrap: ExploratoryBootstrapResult | None = None
    task_contrasts: tuple[DescriptiveContrast, ...] = ()


@dataclass(frozen=True)
class V2AnalysisReport:
    plan_digest: str
    h1: FiniteRosterH1Candidate
    a2: A2DescriptiveResult
    a3: A3PointResult
    a4: A4DescriptiveResult
    reporting_status: str
    blocked_predata_components: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        """Return a deterministic JSON-safe payload (no NaN or infinity)."""

        payload = dataclasses.asdict(self)
        return _json_safe(payload)


def _json_safe(value: object) -> object:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def _wilson_interval(events: int, total: int, confidence: float = 0.95) -> tuple[float, float]:
    if total < 1 or events < 0 or events > total:
        raise SecondaryAnalysisError("binomial counts are invalid")
    if not 0.0 < confidence < 1.0:
        raise SecondaryAnalysisError("confidence must lie strictly between zero and one")
    z = float(norm.ppf(0.5 + confidence / 2.0))
    proportion = events / total
    denominator = 1.0 + z * z / total
    center = (proportion + z * z / (2.0 * total)) / denominator
    half = (
        z
        * math.sqrt(
            proportion * (1.0 - proportion) / total
            + z * z / (4.0 * total * total)
        )
        / denominator
    )
    return max(0.0, center - half), min(1.0, center + half)


def _validate_primary_labels(
    trials: Sequence[AnalysisTrial],
    labels: Mapping[TrialIdentity, CoderJoinResult],
    plan: SchedulePlan,
) -> dict[TrialIdentity, CoderJoinResult]:
    validate_plan(plan)
    if not trials:
        raise SecondaryAnalysisError("analysis roster is empty")
    identities = [row.identity for row in trials]
    if len(set(identities)) != len(identities):
        raise SecondaryAnalysisError("analysis roster contains duplicate identities")
    if any(not row.valid_analysis_trial for row in trials):
        raise SecondaryAnalysisError("secondary analysis accepts valid analysis rows only")
    if any(row.plan_digest != plan.digest for row in trials):
        raise SecondaryAnalysisError("analysis row belongs to another schedule plan")
    cells = {cell.cell_id: cell for cell in plan.cells}
    observed_slots: defaultdict[str, set[int]] = defaultdict(set)
    for row in trials:
        cell = cells.get(row.cell_id)
        if cell is None:
            raise SecondaryAnalysisError("analysis row has no registered plan cell")
        observed = (
            row.config_id,
            row.env_id,
            row.agent_id,
            row.model_id,
            row.task_id,
            row.family_id,
            row.instance_id,
            row.phrasing,
        )
        registered = (
            cell.config_id,
            cell.env_id,
            cell.agent_id,
            cell.model_id,
            cell.task_id,
            cell.family_id,
            cell.instance_id,
            cell.phrasing,
        )
        if observed != registered:
            raise SecondaryAnalysisError("analysis row identity differs from its plan cell")
        if row.valid_slot_index is None:
            raise SecondaryAnalysisError("analysis row lacks a valid-slot identity")
        if row.valid_slot_index in observed_slots[row.cell_id]:
            raise SecondaryAnalysisError("analysis roster duplicates a valid slot")
        observed_slots[row.cell_id].add(row.valid_slot_index)
    incomplete = [
        cell.cell_id
        for cell in plan.cells
        if observed_slots[cell.cell_id] != set(range(cell.target_valid_trials))
    ]
    if incomplete:
        raise SecondaryAnalysisError(
            f"analysis roster differs from the complete plan: {incomplete[:5]}"
        )
    expected = set(identities)
    observed = set(labels)
    if observed != expected:
        missing = len(expected - observed)
        extra = len(observed - expected)
        raise SecondaryAnalysisError(
            "primary-label roster differs from analysis roster: "
            f"missing={missing}, extra={extra}"
        )
    resolved = dict(labels)
    for identity, label in resolved.items():
        if label.status == "coded":
            if label.final_code not in FINAL_CODES:
                raise SecondaryAnalysisError(
                    f"coded primary label has invalid final code: {identity!r}"
                )
        elif label.status == "missing":
            if label.final_code is not None:
                raise SecondaryAnalysisError("missing primary label has a final code")
        else:
            raise SecondaryAnalysisError("primary label has an unknown status")
    return resolved


def _group(
    name: str,
    rows: Sequence[AnalysisTrial],
    labels: Mapping[TrialIdentity, CoderJoinResult],
) -> DescriptiveBinomialGroup:
    final = [labels[row.identity].final_code for row in rows]
    codes = [code for code in final if code is not None]
    events = sum(code in {"D", "E"} for code in codes)
    if not codes:
        rate = lower = upper = None
        method = "not_estimable_no_primary_labels"
    else:
        rate = events / len(codes)
        lower, upper = _wilson_interval(events, len(codes))
        method = "wilson_descriptive_not_design_aware"
    return DescriptiveBinomialGroup(
        group=name,
        denominator=len(rows),
        labelled=len(codes),
        missing_labels=len(rows) - len(codes),
        de_events=events,
        de_rate=rate,
        lower=lower,
        upper=upper,
        interval_method=method,
    )


def _contrast(
    first: DescriptiveBinomialGroup,
    second: DescriptiveBinomialGroup,
) -> DescriptiveContrast:
    if first.de_rate is None or second.de_rate is None:
        difference = ratio = None
        ratio_status = "not_estimable_missing_rate"
    else:
        difference = first.de_rate - second.de_rate
        if second.de_rate > 0.0:
            ratio = first.de_rate / second.de_rate
            ratio_status = "finite"
        elif first.de_rate > 0.0:
            ratio = None
            ratio_status = "infinite_zero_reference_rate"
        else:
            ratio = None
            ratio_status = "undefined_both_rates_zero"
    return DescriptiveContrast(
        first_group=first.group,
        second_group=second.group,
        risk_difference=difference,
        risk_ratio=ratio,
        risk_ratio_status=ratio_status,
        inferential_status="blocked_pending_design_aware_model_freeze",
    )


def _strict_crossing_blocks(
    trials: Sequence[AnalysisTrial],
    *,
    plan: SchedulePlan,
    task_category: str,
) -> dict[tuple[str, str], tuple[tuple[AnalysisTrial, ...], ...]]:
    """Return exact 7x5 blocks stratified by registered variant/instance."""

    validate_plan(plan)
    if task_category not in {"capability", "seeded_error"}:
        raise SecondaryAnalysisError("unknown crossing-block task category")
    configurations = tuple(sorted({cell.config_id for cell in plan.cells}))
    if configurations != tuple(REGISTERED_CONFIG_IDS):
        raise SecondaryAnalysisError(
            "design-aware bootstrap requires the exact seven configurations"
        )
    if {cell.env_id for cell in plan.cells} != set(ENVIRONMENTS):
        raise SecondaryAnalysisError(
            "design-aware bootstrap requires the exact five environments"
        )
    category_cells = {
        cell.cell_id: cell
        for cell in plan.cells
        if ("capability" if cell.task_id.startswith("C") else "seeded_error")
        == task_category
    }
    rows = [row for row in trials if row.task_category == task_category]
    if not category_cells or not rows:
        raise SecondaryAnalysisError(f"{task_category} crossing roster is empty")
    if len({row.identity for row in rows}) != len(rows):
        raise SecondaryAnalysisError(f"{task_category} rows duplicate trial identities")

    by_cell: defaultdict[str, list[AnalysisTrial]] = defaultdict(list)
    raw_blocks: defaultdict[
        tuple[str, str, int], dict[tuple[str, str], AnalysisTrial]
    ] = defaultdict(dict)
    stratum_targets: dict[tuple[str, str], int] = {}
    for cell in category_cells.values():
        stratum = (
            (cell.family_id, cell.instance_id)
            if task_category == "capability"
            else (cell.task_id, cell.phrasing)
        )
        previous = stratum_targets.setdefault(stratum, cell.target_valid_trials)
        if previous != cell.target_valid_trials:
            raise SecondaryAnalysisError(
                f"{task_category} stratum has unequal valid-slot targets"
            )
    for row in rows:
        cell = category_cells.get(row.cell_id)
        if cell is None:
            raise SecondaryAnalysisError(
                f"{task_category} row has no registered plan cell"
            )
        if row.plan_digest != plan.digest or row.valid_slot_index is None:
            raise SecondaryAnalysisError(
                f"{task_category} row lacks plan/valid-slot binding"
            )
        observed = (
            row.config_id,
            row.env_id,
            row.task_id,
            row.family_id,
            row.instance_id,
            row.phrasing,
        )
        expected = (
            cell.config_id,
            cell.env_id,
            cell.task_id,
            cell.family_id,
            cell.instance_id,
            cell.phrasing,
        )
        if observed != expected:
            raise SecondaryAnalysisError(
                f"{task_category} row identity differs from plan cell"
            )
        by_cell[row.cell_id].append(row)
        stratum = (
            (row.family_id, row.instance_id)
            if task_category == "capability"
            else (row.task_id, row.phrasing)
        )
        block_key = (*stratum, row.valid_slot_index)
        crossing_key = (row.config_id, row.env_id)
        if crossing_key in raw_blocks[block_key]:
            raise SecondaryAnalysisError(
                f"{task_category} block duplicates a config/environment row"
            )
        raw_blocks[block_key][crossing_key] = row
    cell_mismatches = [
        (cell_id, cell.target_valid_trials, len(by_cell[cell_id]))
        for cell_id, cell in sorted(category_cells.items())
        if len(by_cell[cell_id]) != cell.target_valid_trials
    ]
    if cell_mismatches:
        raise SecondaryAnalysisError(
            f"{task_category} cell counts differ from plan: {cell_mismatches[:5]}"
        )

    crossing = {
        (configuration, environment)
        for configuration in REGISTERED_CONFIG_IDS
        for environment in ENVIRONMENTS
    }
    expected_block_keys = {
        (*stratum, valid_slot_index)
        for stratum, target in stratum_targets.items()
        for valid_slot_index in range(target)
    }
    if set(raw_blocks) != expected_block_keys:
        missing = sorted(expected_block_keys - set(raw_blocks))[:5]
        extra = sorted(set(raw_blocks) - expected_block_keys)[:5]
        raise SecondaryAnalysisError(
            f"{task_category} block roster differs from plan: "
            f"missing={missing}, extra={extra}"
        )
    incomplete = [
        key
        for key, values in sorted(raw_blocks.items())
        if set(values) != crossing
    ]
    if incomplete:
        raise SecondaryAnalysisError(
            f"{task_category} block lacks exact 35-row crossing: {incomplete[:5]}"
        )
    result: dict[tuple[str, str], tuple[tuple[AnalysisTrial, ...], ...]] = {}
    for stratum in sorted(stratum_targets):
        result[stratum] = tuple(
            tuple(
                raw_blocks[(*stratum, valid_slot_index)][key]
                for key in sorted(crossing)
            )
            for valid_slot_index in range(stratum_targets[stratum])
        )
    return result


def _bounds_from_groups(
    first: DescriptiveBinomialGroup,
    second: DescriptiveBinomialGroup,
) -> MissingLabelBounds:
    def rate_bounds(group: DescriptiveBinomialGroup) -> tuple[float | None, float | None]:
        if group.denominator == 0:
            return None, None
        return (
            group.de_events / group.denominator,
            (group.de_events + group.missing_labels) / group.denominator,
        )

    first_lower, first_upper = rate_bounds(first)
    second_lower, second_upper = rate_bounds(second)
    if None in {first_lower, first_upper, second_lower, second_upper}:
        rd_lower = rd_upper = rr_lower = rr_upper = None
        rr_status = "not_estimable_zero_denominator"
    else:
        assert first_lower is not None and first_upper is not None
        assert second_lower is not None and second_upper is not None
        rd_lower = first_lower - second_upper
        rd_upper = first_upper - second_lower
        rr_lower = first_lower / second_upper if second_upper > 0 else None
        if second_lower > 0:
            rr_upper = first_upper / second_lower
            rr_status = "finite"
        elif first_upper > 0:
            rr_upper = math.inf
            rr_status = "upper_unbounded_zero_reference_lower_bound"
        else:
            rr_upper = None
            rr_status = "undefined_both_upper_rates_zero"
    return MissingLabelBounds(
        first_rate_lower=first_lower,
        first_rate_upper=first_upper,
        second_rate_lower=second_lower,
        second_rate_upper=second_upper,
        risk_difference_lower=rd_lower,
        risk_difference_upper=rd_upper,
        risk_ratio_lower=rr_lower,
        risk_ratio_upper=rr_upper,
        risk_ratio_status=rr_status,
    )


def _percentile_interval(
    values: np.ndarray,
    *,
    estimate: float | None,
    total_draws: int,
) -> BootstrapInterval:
    defined = values[np.isfinite(values)]
    if defined.size == 0:
        lower = upper = None
    else:
        lower, upper = (float(value) for value in np.percentile(defined, [2.5, 97.5]))
    return BootstrapInterval(
        estimate=estimate,
        lower=lower,
        upper=upper,
        defined_draws=int(defined.size),
        total_draws=total_draws,
    )


def _extended_ratio_interval(
    first_rates: np.ndarray,
    second_rates: np.ndarray,
    *,
    estimate: float | None,
    total_draws: int,
) -> tuple[BootstrapInterval, int, int]:
    finite: list[float] = []
    infinite = 0
    undefined = 0
    for first, second in zip(first_rates, second_rates, strict=True):
        if not math.isfinite(float(first)) or not math.isfinite(float(second)):
            undefined += 1
        elif second > 0:
            finite.append(float(first / second))
        elif first > 0:
            infinite += 1
        else:
            undefined += 1
    if undefined:
        lower = upper = None
    else:
        ordered = np.asarray([*finite, *([math.inf] * infinite)], dtype=float)
        lower = _extended_percentile(ordered, 2.5)
        upper = _extended_percentile(ordered, 97.5)
    return (
        BootstrapInterval(
            estimate=estimate,
            lower=lower,
            upper=upper,
            defined_draws=len(finite) + infinite,
            total_draws=total_draws,
        ),
        infinite,
        undefined,
    )


def _extended_percentile(values: np.ndarray, percentile: float) -> float | None:
    if values.size == 0:
        return None
    ordered = np.sort(values)
    position = (values.size - 1) * percentile / 100.0
    lower_index = int(math.floor(position))
    upper_index = int(math.ceil(position))
    lower = float(ordered[lower_index])
    upper = float(ordered[upper_index])
    if math.isinf(lower) or math.isinf(upper):
        return math.inf
    return lower + (position - lower_index) * (upper - lower)


def _bootstrap_from_count_draws(
    first_counts: np.ndarray,
    second_counts: np.ndarray,
    *,
    first_estimate: float | None,
    second_estimate: float | None,
    seed: int,
) -> ExploratoryBootstrapResult:
    # Count columns are [D/E events, observed labels]. Undefined rates remain
    # NaN and are counted in every reported interval rather than silently
    # disappearing.
    with np.errstate(divide="ignore", invalid="ignore"):
        first_rates = first_counts[:, 0] / first_counts[:, 1]
        second_rates = second_counts[:, 0] / second_counts[:, 1]
    first_rates[first_counts[:, 1] == 0] = np.nan
    second_rates[second_counts[:, 1] == 0] = np.nan
    difference = first_rates - second_rates
    if first_estimate is None or second_estimate is None:
        rd_estimate = ratio_estimate = None
    else:
        rd_estimate = first_estimate - second_estimate
        ratio_estimate = (
            first_estimate / second_estimate if second_estimate > 0 else None
        )
    ratio, infinite, undefined = _extended_ratio_interval(
        first_rates,
        second_rates,
        estimate=ratio_estimate,
        total_draws=first_counts.shape[0],
    )
    return ExploratoryBootstrapResult(
        seed=seed,
        resamples=first_counts.shape[0],
        first_rate=_percentile_interval(
            first_rates,
            estimate=first_estimate,
            total_draws=first_counts.shape[0],
        ),
        second_rate=_percentile_interval(
            second_rates,
            estimate=second_estimate,
            total_draws=first_counts.shape[0],
        ),
        risk_difference=_percentile_interval(
            difference,
            estimate=rd_estimate,
            total_draws=first_counts.shape[0],
        ),
        risk_ratio=ratio,
        risk_ratio_infinite_draws=infinite,
        risk_ratio_undefined_draws=undefined,
        method="stratified_complete_crossing_block_percentile",
    )


def a2_descriptive(
    trials: Sequence[AnalysisTrial],
    labels: Mapping[TrialIdentity, CoderJoinResult],
) -> A2DescriptiveResult:
    """Compute the accepted conditional-failure population without inference."""

    population = [
        row
        for row in trials
        if row.env_id in H2_CONTEXTS and row.failed is True
    ]
    groups = tuple(
        _group(context, [row for row in population if row.env_id == context], labels)
        for context in H2_CONTEXTS
    )
    if any(group.denominator == 0 for group in groups):
        status = "not_estimable_zero_failure_denominator"
    elif any(group.missing_labels > 0 for group in groups):
        status = "measurement_incomplete_primary_labels"
    elif any(group.denominator < 10 for group in groups):
        status = "descriptive_sparse_below_ten_failures_per_context"
    else:
        status = "descriptive_only_primary_model_not_frozen"

    configurations = sorted({row.config_id for row in population})
    by_configuration = tuple(
        _group(
            f"{configuration}:{context}",
            [
                row
                for row in population
                if row.config_id == configuration and row.env_id == context
            ],
            labels,
        )
        for configuration in configurations
        for context in H2_CONTEXTS
    )
    return A2DescriptiveResult(
        status=status,
        groups=groups,
        contrast=_contrast(groups[0], groups[1]),
        by_configuration=by_configuration,
        registered_population="all_valid_failed_trials_in_windows_and_linux_contexts",
        claim_scope="exploratory_conditional_association_only",
    )


def a2_design_aware(
    trials: Sequence[AnalysisTrial],
    labels: Mapping[TrialIdentity, CoderJoinResult],
    *,
    plan: SchedulePlan,
) -> A2DescriptiveResult:
    """A2 exploratory complete-block percentile intervals without imputation."""

    resolved = _validate_primary_labels(trials, labels, plan)
    capability = _strict_crossing_blocks(
        trials, plan=plan, task_category="capability"
    )
    seeded = _strict_crossing_blocks(
        trials, plan=plan, task_category="seeded_error"
    )
    rng = np.random.default_rng(A2_BOOTSTRAP_SEED)
    draws = np.zeros((A2_BOOTSTRAP_RESAMPLES, 2, 2), dtype=np.int64)
    context_index = {context: index for index, context in enumerate(H2_CONTEXTS)}
    for strata in (capability, seeded):
        for _stratum, blocks in sorted(strata.items()):
            stats = np.zeros((len(blocks), 2, 2), dtype=np.int64)
            for block_index, block in enumerate(blocks):
                for row in block:
                    if row.env_id not in context_index or row.failed is not True:
                        continue
                    label = resolved[row.identity]
                    if label.final_code is None:
                        continue
                    index = context_index[row.env_id]
                    stats[block_index, index, 1] += 1
                    stats[block_index, index, 0] += int(
                        label.final_code in {"D", "E"}
                    )
            sampled = rng.integers(
                0,
                len(blocks),
                size=(A2_BOOTSTRAP_RESAMPLES, len(blocks)),
            )
            draws += np.sum(stats[sampled], axis=1)

    result = a2_descriptive(trials, resolved)
    first, second = result.groups
    if any(group.denominator == 0 for group in result.groups):
        status = "not_estimable_zero_failure_denominator"
    elif any(group.denominator < 10 for group in result.groups):
        status = (
            "measurement_incomplete_sparse_below_ten_failures_per_context"
            if any(group.missing_labels for group in result.groups)
            else "descriptive_sparse_below_ten_failures_per_context"
        )
    elif any(group.missing_labels for group in result.groups):
        status = "measurement_incomplete_primary_labels"
    else:
        status = "exploratory_design_aware_complete"
    bootstrap = _bootstrap_from_count_draws(
        draws[:, 0, :],
        draws[:, 1, :],
        first_estimate=first.de_rate,
        second_estimate=second.de_rate,
        seed=A2_BOOTSTRAP_SEED,
    )
    return dataclasses.replace(
        result,
        status=status,
        missing_label_bounds=_bounds_from_groups(first, second),
        bootstrap=bootstrap,
        contrast=dataclasses.replace(
            result.contrast,
            inferential_status="exploratory_no_support_reject_threshold",
        ),
    )


def a4_descriptive(
    trials: Sequence[AnalysisTrial],
    labels: Mapping[TrialIdentity, CoderJoinResult],
) -> A4DescriptiveResult:
    """Compute exact-prompt-set D/E summaries without inventing a mixed model."""

    population = [row for row in trials if row.task_category == "seeded_error"]
    unknown = sorted({row.phrasing for row in population} - set(H4_PHRASINGS))
    if unknown:
        raise SecondaryAnalysisError(f"seeded-error roster has unknown phrasing: {unknown}")
    groups = tuple(
        _group(phrasing, [row for row in population if row.phrasing == phrasing], labels)
        for phrasing in H4_PHRASINGS
    )
    if any(group.denominator == 0 for group in groups):
        status = "not_estimable_missing_registered_phrasing"
    elif any(group.missing_labels > 0 for group in groups):
        status = "measurement_incomplete_primary_labels"
    else:
        status = "descriptive_only_primary_model_not_frozen"
    tasks = sorted({row.task_id for row in population})
    by_task = tuple(
        _group(
            f"{task}:{phrasing}",
            [
                row
                for row in population
                if row.task_id == task and row.phrasing == phrasing
            ],
            labels,
        )
        for task in tasks
        for phrasing in H4_PHRASINGS
    )
    return A4DescriptiveResult(
        status=status,
        groups=groups,
        contrast=_contrast(groups[0], groups[1]),
        by_task=by_task,
        registered_population="all_valid_seeded_error_trials",
        claim_scope="exploratory_exact_registered_prompt_pairs_only",
    )


def a4_design_aware(
    trials: Sequence[AnalysisTrial],
    labels: Mapping[TrialIdentity, CoderJoinResult],
    *,
    plan: SchedulePlan,
) -> A4DescriptiveResult:
    """A4 exact-prompt-set complete-block intervals and task heterogeneity."""

    resolved = _validate_primary_labels(trials, labels, plan)
    strata = _strict_crossing_blocks(
        trials, plan=plan, task_category="seeded_error"
    )
    rng = np.random.default_rng(A4_BOOTSTRAP_SEED)
    draws = np.zeros((A4_BOOTSTRAP_RESAMPLES, 2, 2), dtype=np.int64)
    phrasing_index = {
        phrasing: index for index, phrasing in enumerate(H4_PHRASINGS)
    }
    for (_task, phrasing), blocks in sorted(strata.items()):
        stats = np.zeros((len(blocks), 2), dtype=np.int64)
        for block_index, block in enumerate(blocks):
            for row in block:
                label = resolved[row.identity]
                if label.final_code is None:
                    continue
                stats[block_index, 1] += 1
                stats[block_index, 0] += int(label.final_code in {"D", "E"})
        sampled = rng.integers(
            0,
            len(blocks),
            size=(A4_BOOTSTRAP_RESAMPLES, len(blocks)),
        )
        draws[:, phrasing_index[phrasing], :] += np.sum(stats[sampled], axis=1)

    result = a4_descriptive(trials, resolved)
    first, second = result.groups
    status = (
        "measurement_incomplete_primary_labels"
        if any(group.missing_labels for group in result.groups)
        else "exploratory_design_aware_complete"
    )
    task_contrasts: list[DescriptiveContrast] = []
    by_name = {group.group: group for group in result.by_task}
    for task in sorted({row.task_id for row in trials if row.task_category == "seeded_error"}):
        task_contrasts.append(
            dataclasses.replace(
                _contrast(
                    by_name[f"{task}:formal"],
                    by_name[f"{task}:colloquial"],
                ),
                inferential_status="descriptive_task_heterogeneity_only",
            )
        )
    return dataclasses.replace(
        result,
        status=status,
        missing_label_bounds=_bounds_from_groups(first, second),
        bootstrap=_bootstrap_from_count_draws(
            draws[:, 0, :],
            draws[:, 1, :],
            first_estimate=first.de_rate,
            second_estimate=second.de_rate,
            seed=A4_BOOTSTRAP_SEED,
        ),
        task_contrasts=tuple(task_contrasts),
        contrast=dataclasses.replace(
            result.contrast,
            inferential_status="exploratory_no_significance_or_mechanism_claim",
        ),
    )


def _bh_rejections(p_values: Mapping[str, float], q: float) -> set[str]:
    ordered = sorted(p_values.items(), key=lambda item: (item[1], item[0]))
    cutoff: float | None = None
    total = len(ordered)
    for rank, (_name, value) in enumerate(ordered, start=1):
        if value <= q * rank / total:
            cutoff = value
    if cutoff is None:
        return set()
    return {name for name, value in ordered if value <= cutoff}


def a3_point_estimate(
    trials: Sequence[AnalysisTrial],
    *,
    plan: SchedulePlan,
    family_domains: Mapping[str, str] | None = None,
) -> A3PointResult:
    """Run the fixed-block A3 bootstrap, or mark a pilot roster noninferential."""

    validate_plan(plan)
    domains = dict(family_domains or accepted_family_domains())
    all_capability_rows = [
        row
        for row in trials
        if row.task_category == "capability"
        and row.family_id in domains
    ]
    if not all_capability_rows or any(row.failed is None for row in all_capability_rows):
        raise SecondaryAnalysisError("A3 capability outcomes are absent or incomplete")
    if any(row.plan_digest != plan.digest for row in all_capability_rows):
        raise SecondaryAnalysisError("A3 row belongs to another schedule plan")
    if len({row.identity for row in all_capability_rows}) != len(all_capability_rows):
        raise SecondaryAnalysisError("A3 rows contain duplicate trial identities")

    planned = {
        cell.cell_id: (
            cell.env_id,
            cell.config_id,
            cell.family_id,
            cell.instance_id,
            cell.target_valid_trials,
        )
        for cell in plan.cells
        if cell.env_id in ENVIRONMENTS and cell.family_id in domains
    }
    if not planned:
        raise SecondaryAnalysisError("validated plan contains no A3 capability cells")
    blocks: defaultdict[
        tuple[str, str, int], dict[tuple[str, str], bool]
    ] = defaultdict(dict)
    observed_by_cell: defaultdict[str, int] = defaultdict(int)
    for row in all_capability_rows:
        expected = planned.get(row.cell_id)
        observed = (row.env_id, row.config_id, row.family_id, row.instance_id)
        if expected is None or expected[:4] != observed:
            raise SecondaryAnalysisError("A3 row identity differs from its plan cell")
        if row.valid_slot_index is None:
            raise SecondaryAnalysisError("A3 row lacks a valid-slot identity")
        block_key = (row.family_id, row.instance_id, row.valid_slot_index)
        crossing_key = (row.config_id, row.env_id)
        if crossing_key in blocks[block_key]:
            raise SecondaryAnalysisError("A3 block duplicates a config/environment row")
        blocks[block_key][crossing_key] = bool(row.failed)
        observed_by_cell[row.cell_id] += 1
    if set(observed_by_cell) != set(planned):
        raise SecondaryAnalysisError("A3 row cell roster differs from the plan")
    cell_mismatches = [
        (cell_id, expected[4], observed_by_cell[cell_id])
        for cell_id, expected in sorted(planned.items())
        if observed_by_cell[cell_id] != expected[4]
    ]
    if cell_mismatches:
        raise SecondaryAnalysisError(
            f"A3 cell counts differ from plan: {cell_mismatches[:5]}"
        )

    configurations = sorted({value[1] for value in planned.values()})
    environments = sorted({value[0] for value in planned.values()})
    if set(environments) != set(ENVIRONMENTS):
        raise SecondaryAnalysisError("A3 plan lacks the exact phase environment roster")
    instances = {
        family: sorted(
            {value[3] for value in planned.values() if value[2] == family}
        )
        for family in domains
    }
    expected_crossing = {
        (configuration, environment)
        for configuration in configurations
        for environment in ENVIRONMENTS
    }
    expected_blocks = {
        (family, instance, valid_slot_index)
        for family in domains
        for instance in instances[family]
        for valid_slot_index in range(
            next(
                value[4]
                for value in planned.values()
                if value[2] == family and value[3] == instance
            )
        )
    }
    if set(blocks) != expected_blocks:
        missing = sorted(expected_blocks - set(blocks))[:5]
        extra = sorted(set(blocks) - expected_blocks)[:5]
        raise SecondaryAnalysisError(
            f"A3 block roster differs from plan: missing={missing}, extra={extra}"
        )
    incomplete_blocks = [
        (key, sorted(expected_crossing - set(values))[:3], sorted(set(values) - expected_crossing)[:3])
        for key, values in sorted(blocks.items())
        if set(values) != expected_crossing
    ]
    if incomplete_blocks:
        raise SecondaryAnalysisError(
            f"A3 block lacks the exact config/environment crossing: {incomplete_blocks[:3]}"
        )

    families_by_domain = {
        domain: sorted(family for family, value in domains.items() if value == domain)
        for domain in sorted(set(domains.values()))
    }
    context_indices = {context: index for index, context in enumerate(H3_CONTEXTS)}
    configuration_indices = {
        configuration: index for index, configuration in enumerate(configurations)
    }
    rng = np.random.default_rng(A3_BOOTSTRAP_SEED)
    point_by_config = np.zeros((len(configurations), len(H3_CONTEXTS)), dtype=float)
    replicate_by_config = np.zeros(
        (A3_BOOTSTRAP_RESAMPLES, len(configurations), len(H3_CONTEXTS)),
        dtype=float,
    )
    domain_count = len(families_by_domain)
    for domain, families in families_by_domain.items():
        for family in families:
            weight = (
                1.0
                / domain_count
                / len(families)
                / len(instances[family])
            )
            for instance in instances[family]:
                block_keys = sorted(
                    key for key in blocks if key[:2] == (family, instance)
                )
                values = np.asarray(
                    [
                        [
                            [blocks[key][(configuration, context)] for context in H3_CONTEXTS]
                            for configuration in configurations
                        ]
                        for key in block_keys
                    ],
                    dtype=float,
                )
                point_by_config += weight * np.mean(values, axis=0)
                sampled = rng.integers(
                    0,
                    len(block_keys),
                    size=(A3_BOOTSTRAP_RESAMPLES, len(block_keys)),
                )
                replicate_by_config += weight * np.mean(values[sampled], axis=1)
    point_rates = np.mean(point_by_config, axis=0)
    replicate_rates = np.mean(replicate_by_config, axis=1)
    rates = {
        context: float(point_rates[index])
        for context, index in context_indices.items()
    }

    windows = rates["windows_powershell"]
    wsl2 = rates["windows_wsl2"]
    linux = rates["linux_native"]
    gap = abs(windows - linux)
    inferential = tuple(configurations) == tuple(REGISTERED_CONFIG_IDS)
    if inferential:
        win_wsl_reps = (
            replicate_rates[:, context_indices["windows_powershell"]]
            - replicate_rates[:, context_indices["windows_wsl2"]]
        )
        wsl_linux_reps = (
            replicate_rates[:, context_indices["windows_wsl2"]]
            - replicate_rates[:, context_indices["linux_native"]]
        )
        distance_reps = np.abs(
            replicate_rates[:, context_indices["windows_wsl2"]]
            - replicate_rates[:, context_indices["windows_powershell"]]
        ) - np.abs(
            replicate_rates[:, context_indices["windows_wsl2"]]
            - replicate_rates[:, context_indices["linux_native"]]
        )
        win_wsl_lower, win_wsl_upper = (
            float(value) for value in np.percentile(win_wsl_reps, [2.5, 97.5])
        )
        wsl_linux_lower, wsl_linux_upper = (
            float(value) for value in np.percentile(wsl_linux_reps, [2.5, 97.5])
        )
        distance_lower, distance_upper = (
            float(value) for value in np.percentile(distance_reps, [2.5, 97.5])
        )
        a3a = win_wsl_lower > 0.0 and wsl_linux_lower > 0.0
        a3b = distance_lower > 0.0

        config_p: dict[str, float] = {}
        raw_config: dict[str, tuple[float, float, float, float]] = {}
        for configuration, config_index in configuration_indices.items():
            first_reps = (
                replicate_by_config[:, config_index, context_indices["windows_powershell"]]
                - replicate_by_config[:, config_index, context_indices["windows_wsl2"]]
            )
            second_reps = (
                replicate_by_config[:, config_index, context_indices["windows_wsl2"]]
                - replicate_by_config[:, config_index, context_indices["linux_native"]]
            )
            # Add-one Monte Carlo p-values keep finite-bootstrap inference
            # conservative and prevent an impossible reported p-value of zero.
            first_p = float(
                (1 + np.count_nonzero(first_reps <= 0.0))
                / (len(first_reps) + 1)
            )
            second_p = float(
                (1 + np.count_nonzero(second_reps <= 0.0))
                / (len(second_reps) + 1)
            )
            config_p[configuration] = max(first_p, second_p)
            raw_config[configuration] = (
                float(
                    point_by_config[config_index, context_indices["windows_powershell"]]
                    - point_by_config[config_index, context_indices["windows_wsl2"]]
                ),
                float(
                    point_by_config[config_index, context_indices["windows_wsl2"]]
                    - point_by_config[config_index, context_indices["linux_native"]]
                ),
                first_p,
                second_p,
            )
        rejected = _bh_rejections(config_p, A3_CONFIG_FDR_Q)
        per_configuration = tuple(
            A3ConfigurationResult(
                config_id=configuration,
                windows_minus_wsl2=raw_config[configuration][0],
                wsl2_minus_linux=raw_config[configuration][1],
                windows_minus_wsl2_one_sided_p=raw_config[configuration][2],
                wsl2_minus_linux_one_sided_p=raw_config[configuration][3],
                intersection_union_p=config_p[configuration],
                bh_reject=configuration in rejected,
            )
            for configuration in configurations
        )
        if gap < A3_INCONCLUSIVE_GAP:
            status = "inconclusive_windows_linux_gap_below_five_points"
        elif a3a and a3b:
            status = "supported"
        else:
            status = "rejected"
        inferential_status = "complete_fixed_block_bootstrap"
    else:
        win_wsl_lower = win_wsl_upper = None
        wsl_linux_lower = wsl_linux_upper = None
        distance_lower = distance_upper = None
        a3a = a3b = None
        per_configuration = ()
        status = "not_applicable_nonconfirmatory_configuration_roster"
        inferential_status = "not_run_requires_exact_registered_seven_configurations"
    return A3PointResult(
        status=status,
        windows_failure_rate=windows,
        wsl2_failure_rate=wsl2,
        linux_failure_rate=linux,
        windows_minus_wsl2=windows - wsl2,
        wsl2_minus_linux=wsl2 - linux,
        distance_difference=abs(wsl2 - windows) - abs(wsl2 - linux),
        windows_linux_absolute_gap=gap,
        point_ordering_holds=linux < wsl2 < windows,
        trials=len(blocks) * len(configurations) * len(H3_CONTEXTS),
        inferential_status=inferential_status,
        windows_minus_wsl2_lower=win_wsl_lower,
        windows_minus_wsl2_upper=win_wsl_upper,
        wsl2_minus_linux_lower=wsl_linux_lower,
        wsl2_minus_linux_upper=wsl_linux_upper,
        distance_difference_lower=distance_lower,
        distance_difference_upper=distance_upper,
        a3a_ordering_supported=a3a,
        a3b_closer_to_linux_supported=a3b,
        bootstrap_resamples=A3_BOOTSTRAP_RESAMPLES,
        bootstrap_seed=A3_BOOTSTRAP_SEED,
        per_configuration=per_configuration,
    )


def a3_fixed_block_inference(
    trials: Sequence[AnalysisTrial],
    *,
    plan: SchedulePlan,
    family_domains: Mapping[str, str] | None = None,
) -> A3PointResult:
    """Explicit public name for the preregistered A3 inferential procedure."""

    return a3_point_estimate(
        trials,
        plan=plan,
        family_domains=family_domains,
    )


def build_v2_analysis_report(
    trials: Sequence[AnalysisTrial],
    primary_labels: Mapping[TrialIdentity, CoderJoinResult],
    *,
    plan: SchedulePlan,
    h1: FiniteRosterH1Candidate,
    family_domains: Mapping[str, str] | None = None,
) -> V2AnalysisReport:
    """Build the currently defensible machine-generated V2 report boundary."""

    labels = _validate_primary_labels(trials, primary_labels, plan)
    focal_count = sum(
        row.task_category == "capability" and row.env_id in H2_CONTEXTS
        for row in trials
    )
    if h1.trials != focal_count:
        raise SecondaryAnalysisError(
            "H1 result trial count differs from the supplied analysis roster"
        )
    confirmatory_configurations = tuple(sorted({cell.config_id for cell in plan.cells}))
    if confirmatory_configurations == tuple(REGISTERED_CONFIG_IDS):
        a2 = a2_design_aware(trials, labels, plan=plan)
        a4 = a4_design_aware(trials, labels, plan=plan)
    else:
        a2 = a2_descriptive(trials, labels)
        a4 = a4_descriptive(trials, labels)
    a3 = a3_fixed_block_inference(
        trials, plan=plan, family_domains=family_domains
    )
    return V2AnalysisReport(
        plan_digest=plan.digest,
        h1=h1,
        a2=a2,
        a3=a3,
        a4=a4,
        reporting_status=(
            "predata_candidate_machine_generated_a1_a4"
            if confirmatory_configurations == tuple(REGISTERED_CONFIG_IDS)
            else "nonconfirmatory_descriptive_only"
        ),
        blocked_predata_components=(),
    )


def report_tables(report: V2AnalysisReport) -> dict[str, tuple[dict[str, object], ...]]:
    """Return deterministic table rows suitable for CSV/JSON renderers."""

    h1 = {
        "analysis": "A1",
        "windows_failure_rate": report.h1.windows_failure_rate,
        "linux_failure_rate": report.h1.linux_failure_rate,
        "risk_difference": report.h1.risk_difference,
        "risk_difference_lower": report.h1.risk_difference_lower,
        "risk_difference_upper": report.h1.risk_difference_upper,
        "risk_ratio": report.h1.risk_ratio,
        "decision": report.h1.decision,
    }
    return {
        "a1": (_json_safe(h1),),
        "a2_context": tuple(_json_safe(dataclasses.asdict(row)) for row in report.a2.groups),
        "a2_configuration": tuple(
            _json_safe(dataclasses.asdict(row)) for row in report.a2.by_configuration
        ),
        "a3": (_json_safe(dataclasses.asdict(report.a3)),),
        "a4_phrasing": tuple(_json_safe(dataclasses.asdict(row)) for row in report.a4.groups),
        "a4_task": tuple(_json_safe(dataclasses.asdict(row)) for row in report.a4.by_task),
    }
