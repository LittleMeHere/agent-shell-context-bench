"""Outcome-blind operating-characteristic scaffold for decision D-001.

This module compares coherent H1a decision rules on the exact finite roster
of five capability tasks by seven configurations and two focal contexts. It
does not select a rule, a smallest effect of interest, or a confirmatory
analysis family.

The interval estimators here are deliberately transparent: equal-weighted
finite-roster marginal probabilities, a non-degenerate Newcombe score
interval for the risk difference, and a log-delta risk-ratio interval using
an unbiased within-cell binomial variance estimate. Sparse-cell and
heterogeneous scenarios are expected to expose where either reference
interval does not have adequate coverage. D-003 and D-005 remain open until
the selected rule is simulated using the exact proposed confirmatory
implementation and an independent oracle.
"""

from __future__ import annotations

import argparse
import csv
import math
import sys
from dataclasses import dataclass
from enum import Enum
from statistics import NormalDist
from typing import Iterable

import numpy as np
from numpy.typing import NDArray


N_CAPABILITY_TASKS = 5
N_CONFIGURATIONS = 7
N_STRATA = N_CAPABILITY_TASKS * N_CONFIGURATIONS
DEFAULT_CONFIDENCE = 0.95
DEFAULT_RR_THRESHOLD = 1.5


class DecisionState(str, Enum):
    """Mutually exclusive result states for a threshold decision."""

    DECISION_RELEVANT = "decision_relevant"
    BOUNDED_SMALL = "bounded_small"
    INCONCLUSIVE = "inconclusive"
    UNESTIMABLE = "unestimable"


@dataclass(frozen=True)
class Scenario:
    """One finite-roster data-generating scenario.

    Logit-scale standard deviations control fixed heterogeneity across the
    registered roster. The intercepts are calibrated so that the arithmetic
    finite-roster marginal rates equal ``linux_rate`` and
    ``linux_rate + target_rd`` exactly.
    """

    linux_rate: float
    target_rd: float
    n_per_cell: int
    task_logit_sd: float = 0.50
    config_logit_sd: float = 0.35
    task_context_logit_sd: float = 0.20
    config_context_logit_sd: float = 0.15

    def __post_init__(self) -> None:
        windows_rate = self.linux_rate + self.target_rd
        if not 0.0 < self.linux_rate < 1.0:
            raise ValueError("linux_rate must be strictly between zero and one")
        if not 0.0 < windows_rate < 1.0:
            raise ValueError(
                "linux_rate + target_rd must be strictly between zero and one"
            )
        if self.n_per_cell < 2:
            raise ValueError("n_per_cell must be at least two")
        heterogeneity = (
            self.task_logit_sd,
            self.config_logit_sd,
            self.task_context_logit_sd,
            self.config_context_logit_sd,
        )
        if any(value < 0.0 for value in heterogeneity):
            raise ValueError("heterogeneity standard deviations cannot be negative")


@dataclass(frozen=True)
class IntervalEstimates:
    """Vectorized estimates for one Monte Carlo run."""

    p_linux: NDArray[np.float64]
    p_windows: NDArray[np.float64]
    rd: NDArray[np.float64]
    rd_lower: NDArray[np.float64]
    rd_upper: NDArray[np.float64]
    rr: NDArray[np.float64]
    rr_lower: NDArray[np.float64]
    rr_upper: NDArray[np.float64]


def classify_threshold_interval(
    lower: float,
    upper: float,
    threshold: float,
) -> DecisionState:
    """Classify one interval relative to a decision threshold.

    A non-finite interval is unestimable. An interval wholly above the
    threshold supports a decision-relevant effect; an interval wholly below
    it supports a bounded-small conclusion; otherwise it is inconclusive.
    """

    if not all(math.isfinite(value) for value in (lower, upper, threshold)):
        return DecisionState.UNESTIMABLE
    if lower > upper:
        raise ValueError("lower interval bound cannot exceed upper bound")
    if lower > threshold:
        return DecisionState.DECISION_RELEVANT
    if upper < threshold:
        return DecisionState.BOUNDED_SMALL
    return DecisionState.INCONCLUSIVE


def classify_existence_plus_magnitude(
    point: float,
    lower: float,
    upper: float,
    magnitude_threshold: float = DEFAULT_RR_THRESHOLD,
) -> DecisionState:
    """Classify the memo's Option B joint existence/magnitude candidate."""

    if not all(
        math.isfinite(value)
        for value in (point, lower, upper, magnitude_threshold)
    ):
        return DecisionState.UNESTIMABLE
    if lower > upper:
        raise ValueError("lower interval bound cannot exceed upper bound")
    if lower > 1.0 and point >= magnitude_threshold:
        return DecisionState.DECISION_RELEVANT
    if upper < magnitude_threshold:
        return DecisionState.BOUNDED_SMALL
    return DecisionState.INCONCLUSIVE


def finite_roster_probabilities(
    scenario: Scenario,
) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    """Return calibrated Linux and Windows probabilities for all 35 strata."""

    task_scores = _standardized_scores(N_CAPABILITY_TASKS)
    config_scores = _standardized_scores(N_CONFIGURATIONS)
    task_grid, config_grid = np.meshgrid(
        task_scores,
        config_scores,
        indexing="ij",
    )
    baseline_offsets = (
        scenario.task_logit_sd * task_grid.ravel()
        + scenario.config_logit_sd * config_grid.ravel()
    )
    linux_intercept = _calibrated_intercept(
        baseline_offsets,
        scenario.linux_rate,
    )
    p_linux = _expit(linux_intercept + baseline_offsets)

    context_offsets = (
        scenario.task_context_logit_sd * task_grid.ravel()
        + scenario.config_context_logit_sd * config_grid.ravel()
    )
    windows_offsets = baseline_offsets + context_offsets
    windows_intercept = _calibrated_intercept(
        windows_offsets,
        scenario.linux_rate + scenario.target_rd,
    )
    p_windows = _expit(windows_intercept + windows_offsets)
    return p_linux, p_windows


def simulate_scenario(
    scenario: Scenario,
    *,
    delta_rd: float,
    replicates: int,
    seed: int,
    confidence: float = DEFAULT_CONFIDENCE,
    rr_threshold: float = DEFAULT_RR_THRESHOLD,
) -> list[dict[str, float | int | str]]:
    """Simulate Options A, B, and D for one outcome-blind scenario."""

    if not 0.0 < delta_rd < 1.0:
        raise ValueError("delta_rd must be strictly between zero and one")
    if replicates < 1:
        raise ValueError("replicates must be positive")
    if not 0.0 < confidence < 1.0:
        raise ValueError("confidence must be strictly between zero and one")
    if rr_threshold <= 1.0:
        raise ValueError("rr_threshold must be greater than one")

    p_linux, p_windows = finite_roster_probabilities(scenario)
    rng = np.random.default_rng(seed)
    linux_counts = rng.binomial(
        scenario.n_per_cell,
        p_linux,
        size=(replicates, N_STRATA),
    )
    windows_counts = rng.binomial(
        scenario.n_per_cell,
        p_windows,
        size=(replicates, N_STRATA),
    )
    estimates = _estimate_intervals(
        linux_counts,
        windows_counts,
        scenario.n_per_cell,
        confidence,
    )

    true_linux = float(np.mean(p_linux))
    true_windows = float(np.mean(p_windows))
    true_rd = true_windows - true_linux
    true_rr = true_windows / true_linux

    option_a_states = _classify_threshold_arrays(
        estimates.rr_lower,
        estimates.rr_upper,
        rr_threshold,
    )
    option_b_states = _classify_option_b_arrays(
        estimates.rr,
        estimates.rr_lower,
        estimates.rr_upper,
        rr_threshold,
    )
    option_d_states = _classify_threshold_arrays(
        estimates.rd_lower,
        estimates.rd_upper,
        delta_rd,
    )

    common = {
        "replicates": replicates,
        "seed": seed,
        "n_per_cell": scenario.n_per_cell,
        "confirmatory_trials_h1a_contexts": (
            2 * N_STRATA * scenario.n_per_cell
        ),
        "confirmatory_trials_full_matrix": 805 * scenario.n_per_cell,
        "true_linux_rate": true_linux,
        "true_windows_rate": true_windows,
        "true_rd": true_rd,
        "true_rr": true_rr,
        "task_logit_sd": scenario.task_logit_sd,
        "config_logit_sd": scenario.config_logit_sd,
        "task_context_logit_sd": scenario.task_context_logit_sd,
        "config_context_logit_sd": scenario.config_context_logit_sd,
        "rd_bias": float(np.mean(estimates.rd - true_rd)),
        "rd_rmse": float(np.sqrt(np.mean((estimates.rd - true_rd) ** 2))),
        "rd_coverage": float(
            np.mean(
                (estimates.rd_lower <= true_rd)
                & (true_rd <= estimates.rd_upper)
            )
        ),
        "rr_estimable_probability": float(np.mean(np.isfinite(estimates.rr))),
        "rr_bias_estimable": _finite_mean(estimates.rr - true_rr),
        "rr_rmse_estimable": _finite_rmse(estimates.rr - true_rr),
        "rr_coverage_estimable": _finite_coverage(
            estimates.rr_lower,
            estimates.rr_upper,
            true_rr,
        ),
    }

    return [
        _summarize_rule(
            common,
            option="A_threshold_superiority_rr",
            scale="risk_ratio",
            threshold=rr_threshold,
            true_effect=true_rr,
            states=option_a_states,
        ),
        _summarize_rule(
            common,
            option="B_existence_plus_magnitude_rr",
            scale="risk_ratio",
            threshold=rr_threshold,
            true_effect=true_rr,
            states=option_b_states,
        ),
        _summarize_rule(
            common,
            option="D_decision_relevant_rd",
            scale="risk_difference",
            threshold=delta_rd,
            true_effect=true_rd,
            states=option_d_states,
        ),
    ]


def _estimate_intervals(
    linux_counts: NDArray[np.int64],
    windows_counts: NDArray[np.int64],
    n_per_cell: int,
    confidence: float,
) -> IntervalEstimates:
    linux_cell_rates = linux_counts / n_per_cell
    windows_cell_rates = windows_counts / n_per_cell
    p_linux = np.mean(linux_cell_rates, axis=1)
    p_windows = np.mean(windows_cell_rates, axis=1)

    linux_variance = np.sum(
        linux_cell_rates * (1.0 - linux_cell_rates) / (n_per_cell - 1),
        axis=1,
    ) / (N_STRATA**2)
    windows_variance = np.sum(
        windows_cell_rates * (1.0 - windows_cell_rates) / (n_per_cell - 1),
        axis=1,
    ) / (N_STRATA**2)

    z_value = NormalDist().inv_cdf(0.5 + confidence / 2.0)
    rd = p_windows - p_linux
    total_per_context = N_STRATA * n_per_cell
    linux_lower, linux_upper = _wilson_bounds(
        np.sum(linux_counts, axis=1),
        total_per_context,
        z_value,
    )
    windows_lower, windows_upper = _wilson_bounds(
        np.sum(windows_counts, axis=1),
        total_per_context,
        z_value,
    )
    # Newcombe's score interval combines the two one-sample Wilson intervals
    # without the zero-width failure of a plug-in Wald interval at 0/M or M/M.
    rd_lower = rd - np.sqrt(
        (p_windows - windows_lower) ** 2
        + (linux_upper - p_linux) ** 2
    )
    rd_upper = rd + np.sqrt(
        (windows_upper - p_windows) ** 2
        + (p_linux - linux_lower) ** 2
    )

    rr = np.full_like(rd, np.nan)
    rr_lower = np.full_like(rd, np.nan)
    rr_upper = np.full_like(rd, np.nan)
    estimable = (p_linux > 0.0) & (p_windows > 0.0)
    with np.errstate(divide="ignore", invalid="ignore", over="ignore"):
        rr[estimable] = p_windows[estimable] / p_linux[estimable]
        log_rr_se = np.sqrt(
            windows_variance[estimable] / (p_windows[estimable] ** 2)
            + linux_variance[estimable] / (p_linux[estimable] ** 2)
        )
        log_rr = np.log(rr[estimable])
        rr_lower[estimable] = np.exp(log_rr - z_value * log_rr_se)
        rr_upper[estimable] = np.exp(log_rr + z_value * log_rr_se)

    return IntervalEstimates(
        p_linux=p_linux,
        p_windows=p_windows,
        rd=rd,
        rd_lower=rd_lower,
        rd_upper=rd_upper,
        rr=rr,
        rr_lower=rr_lower,
        rr_upper=rr_upper,
    )


def _classify_threshold_arrays(
    lower: NDArray[np.float64],
    upper: NDArray[np.float64],
    threshold: float,
) -> NDArray[np.int8]:
    states = np.full(lower.shape, 2, dtype=np.int8)
    unestimable = ~np.isfinite(lower) | ~np.isfinite(upper)
    states[lower > threshold] = 0
    states[upper < threshold] = 1
    states[unestimable] = 3
    return states


def _wilson_bounds(
    successes: NDArray[np.int64],
    total: int,
    z_value: float,
) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    proportions = successes / total
    z_squared = z_value**2
    denominator = 1.0 + z_squared / total
    center = (proportions + z_squared / (2.0 * total)) / denominator
    half_width = (
        z_value
        / denominator
        * np.sqrt(
            proportions * (1.0 - proportions) / total
            + z_squared / (4.0 * total**2)
        )
    )
    return center - half_width, center + half_width


def _classify_option_b_arrays(
    point: NDArray[np.float64],
    lower: NDArray[np.float64],
    upper: NDArray[np.float64],
    magnitude_threshold: float,
) -> NDArray[np.int8]:
    states = np.full(point.shape, 2, dtype=np.int8)
    unestimable = (
        ~np.isfinite(point) | ~np.isfinite(lower) | ~np.isfinite(upper)
    )
    states[(lower > 1.0) & (point >= magnitude_threshold)] = 0
    states[upper < magnitude_threshold] = 1
    states[unestimable] = 3
    return states


def _summarize_rule(
    common: dict[str, float | int | str],
    *,
    option: str,
    scale: str,
    threshold: float,
    true_effect: float,
    states: NDArray[np.int8],
) -> dict[str, float | int | str]:
    result = dict(common)
    result.update(
        {
            "option": option,
            "decision_scale": scale,
            "threshold": threshold,
            "true_effect_on_decision_scale": true_effect,
        }
    )
    labels = (
        ("decision_relevant", 0),
        ("bounded_small", 1),
        ("inconclusive", 2),
        ("unestimable", 3),
    )
    for label, code in labels:
        probability = float(np.mean(states == code))
        result[f"{label}_probability"] = probability
        result[f"{label}_mcse"] = math.sqrt(
            probability * (1.0 - probability) / len(states)
        )
    return result


def _standardized_scores(size: int) -> NDArray[np.float64]:
    scores = np.arange(size, dtype=float) - (size - 1.0) / 2.0
    return scores / math.sqrt(float(np.mean(scores**2)))


def _calibrated_intercept(
    offsets: NDArray[np.float64],
    target_mean: float,
) -> float:
    lower = -40.0
    upper = 40.0
    for _ in range(100):
        midpoint = (lower + upper) / 2.0
        if float(np.mean(_expit(midpoint + offsets))) < target_mean:
            lower = midpoint
        else:
            upper = midpoint
    return (lower + upper) / 2.0


def _expit(values: NDArray[np.float64]) -> NDArray[np.float64]:
    positive = values >= 0.0
    result = np.empty_like(values, dtype=float)
    result[positive] = 1.0 / (1.0 + np.exp(-values[positive]))
    exponent = np.exp(values[~positive])
    result[~positive] = exponent / (1.0 + exponent)
    return result


def _finite_mean(values: NDArray[np.float64]) -> float:
    finite = values[np.isfinite(values)]
    return float(np.mean(finite)) if finite.size else math.nan


def _finite_rmse(values: NDArray[np.float64]) -> float:
    finite = values[np.isfinite(values)]
    return (
        float(np.sqrt(np.mean(finite**2)))
        if finite.size
        else math.nan
    )


def _finite_coverage(
    lower: NDArray[np.float64],
    upper: NDArray[np.float64],
    truth: float,
) -> float:
    finite = np.isfinite(lower) & np.isfinite(upper)
    if not np.any(finite):
        return math.nan
    return float(np.mean((lower[finite] <= truth) & (truth <= upper[finite])))


def _parse_float_list(raw: str) -> list[float]:
    values = [float(value.strip()) for value in raw.split(",") if value.strip()]
    if not values:
        raise argparse.ArgumentTypeError("expected at least one number")
    return values


def _parse_int_list(raw: str) -> list[int]:
    values = [int(value.strip()) for value in raw.split(",") if value.strip()]
    if not values:
        raise argparse.ArgumentTypeError("expected at least one integer")
    return values


def _iter_scenarios(args: argparse.Namespace) -> Iterable[Scenario]:
    for linux_rate in args.linux_rates:
        for target_rd in args.target_rds:
            for n_per_cell in args.n_per_cell:
                yield Scenario(
                    linux_rate=linux_rate,
                    target_rd=target_rd,
                    n_per_cell=n_per_cell,
                    task_logit_sd=args.task_logit_sd,
                    config_logit_sd=args.config_logit_sd,
                    task_context_logit_sd=args.task_context_logit_sd,
                    config_context_logit_sd=args.config_context_logit_sd,
                )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Compare outcome-blind D-001 candidate rules on the finite "
            "5-task x 7-configuration H1a roster."
        )
    )
    parser.add_argument("--linux-rates", type=_parse_float_list, default=[0.05, 0.20])
    parser.add_argument(
        "--target-rds",
        type=_parse_float_list,
        default=[0.0, 0.05, 0.10],
    )
    parser.add_argument("--n-per-cell", type=_parse_int_list, default=[6, 24])
    parser.add_argument("--delta-rd", type=float, default=0.05)
    parser.add_argument("--rr-threshold", type=float, default=1.5)
    parser.add_argument("--replicates", type=int, default=10_000)
    parser.add_argument("--seed", type=int, default=20260730)
    parser.add_argument("--confidence", type=float, default=DEFAULT_CONFIDENCE)
    parser.add_argument("--task-logit-sd", type=float, default=0.50)
    parser.add_argument("--config-logit-sd", type=float, default=0.35)
    parser.add_argument("--task-context-logit-sd", type=float, default=0.20)
    parser.add_argument("--config-context-logit-sd", type=float, default=0.15)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    rows: list[dict[str, float | int | str]] = []
    for index, scenario in enumerate(_iter_scenarios(args)):
        rows.extend(
            simulate_scenario(
                scenario,
                delta_rd=args.delta_rd,
                replicates=args.replicates,
                seed=args.seed + index,
                confidence=args.confidence,
                rr_threshold=args.rr_threshold,
            )
        )
    if not rows:
        return 0
    writer = csv.DictWriter(sys.stdout, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
