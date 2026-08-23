"""Outcome-blind operating-characteristic evidence for D-013.

This module evaluates three distinct questions without selecting a task bank,
pilot gate, effect threshold, or confirmatory model:

1. How often candidate blinded pilot gates classify a bank as ceiling-bound,
   floor-bound, concentrated, or able to proceed?
2. How much target-population error arises when five current-style probes are
   used to estimate a six-domain target, compared with a 12-family bank at
   common or approximately budget-matched split repetition counts?
3. How often H2 has its registered minimum failed-trial denominators, and how
   an optimistic pooled log-risk-ratio reference behaves before clustering,
   rater error, and the final D-005 analysis are implemented?

All scenarios are prospective and synthetic. The "oracle normal" and pooled
H2 calculations are feasibility references, not candidate confirmatory
implementations. No function reads benchmark outcomes.
"""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass
from enum import IntEnum
from statistics import NormalDist
from typing import Iterable, Sequence

import numpy as np
from numpy.typing import NDArray

from analysis.d013_task_bank_design import (
    REGISTERED_CONFIG_IDS,
    REGISTERED_ENVIRONMENT_IDS,
    build_instance_schedule,
)


N_DOMAINS = 6
FAMILIES_PER_DOMAIN = 2
INSTANCES_PER_FAMILY = 3
N_CONFIGURATIONS = 7
N_PILOT_CONFIGURATIONS = 2
N_ENVIRONMENTS = 5
N_SEEDED_VARIANTS = 18
N_PILOT_SEEDED_REPETITIONS = 2
DECISION_RD = 0.05
CONFIDENCE = 0.95

# C01/C04 in domain A, C02/C05 in B, and C03 in C. The middle instance is a
# neutral fixed-fixture stand-in; this is a synthetic construct comparison,
# not a claim that current tasks already have three real instances.
CURRENT_FAMILY_COORDS = (
    (0, 0),
    (0, 1),
    (1, 0),
    (1, 1),
    (2, 0),
)
CURRENT_INSTANCE_INDEX = 1


class GateState(IntEnum):
    PROCEED = 0
    CEILING = 1
    FLOOR = 2
    CONCENTRATED = 3


@dataclass(frozen=True)
class PilotGate:
    name: str
    min_failures: int
    min_successes: int
    min_failing_families: int
    min_successful_families: int
    min_failing_domains: int
    min_successful_domains: int

    def __post_init__(self) -> None:
        values = (
            self.min_failures,
            self.min_successes,
            self.min_failing_families,
            self.min_successful_families,
            self.min_failing_domains,
            self.min_successful_domains,
        )
        if not self.name:
            raise ValueError("gate name must not be empty")
        if any(value < 1 for value in values):
            raise ValueError("all gate minima must be positive")


@dataclass(frozen=True)
class PilotScenario:
    name: str
    domain_failure_rates: tuple[float, ...]
    family_logit_sd: float = 0.55
    instance_logit_sd: float = 0.30
    config_logit_sd: float = 0.25
    environment_logit_sd: float = 0.25

    def __post_init__(self) -> None:
        _validate_rates("domain_failure_rates", self.domain_failure_rates)
        _validate_sds(
            self.family_logit_sd,
            self.instance_logit_sd,
            self.config_logit_sd,
            self.environment_logit_sd,
        )


@dataclass(frozen=True)
class ConfirmScenario:
    name: str
    linux_domain_rates: tuple[float, ...]
    windows_domain_rates: tuple[float, ...]
    family_logit_sd: float = 0.55
    instance_logit_sd: float = 0.30
    config_logit_sd: float = 0.35
    family_context_logit_sd: float = 0.20
    instance_context_logit_sd: float = 0.15
    config_context_logit_sd: float = 0.20

    def __post_init__(self) -> None:
        _validate_rates("linux_domain_rates", self.linux_domain_rates)
        _validate_rates("windows_domain_rates", self.windows_domain_rates)
        _validate_sds(
            self.family_logit_sd,
            self.instance_logit_sd,
            self.config_logit_sd,
            self.family_context_logit_sd,
            self.instance_context_logit_sd,
            self.config_context_logit_sd,
        )


@dataclass(frozen=True)
class H2Scenario:
    name: str
    capability_failure_linux: float
    capability_failure_windows: float
    seeded_failure_linux: float
    seeded_failure_windows: float
    de_probability_linux: float
    de_probability_windows: float
    task_logit_sd: float = 0.65
    config_logit_sd: float = 0.35
    context_interaction_logit_sd: float = 0.20
    de_task_logit_sd: float = 0.35
    de_config_logit_sd: float = 0.20

    def __post_init__(self) -> None:
        _validate_rates(
            "H2 probabilities",
            (
                self.capability_failure_linux,
                self.capability_failure_windows,
                self.seeded_failure_linux,
                self.seeded_failure_windows,
                self.de_probability_linux,
                self.de_probability_windows,
            ),
            expected_length=6,
        )
        _validate_sds(
            self.task_logit_sd,
            self.config_logit_sd,
            self.context_interaction_logit_sd,
            self.de_task_logit_sd,
            self.de_config_logit_sd,
        )


PILOT_GATES = (
    PilotGate("G1_any_information", 1, 1, 1, 1, 1, 1),
    PilotGate("G2_five_events_two_families", 5, 5, 2, 2, 1, 1),
    PilotGate("G3_ten_events_cross_domain", 10, 10, 3, 3, 2, 2),
)


def _validate_rates(
    label: str,
    values: Sequence[float],
    *,
    expected_length: int = N_DOMAINS,
) -> None:
    if len(values) != expected_length:
        raise ValueError(f"{label} must contain {expected_length} values")
    if any(not 0.0 < value < 1.0 for value in values):
        raise ValueError(f"{label} values must be strictly between zero and one")


def _validate_sds(*values: float) -> None:
    if any(value < 0.0 or not math.isfinite(value) for value in values):
        raise ValueError("heterogeneity standard deviations must be finite and nonnegative")


def _standardized_scores(size: int) -> NDArray[np.float64]:
    if size == 1:
        return np.zeros(1, dtype=float)
    scores = np.arange(size, dtype=float) - (size - 1.0) / 2.0
    return scores / math.sqrt(float(np.mean(scores**2)))


def _expit(values: NDArray[np.float64] | float) -> NDArray[np.float64]:
    array = np.asarray(values, dtype=float)
    positive = array >= 0.0
    result = np.empty_like(array, dtype=float)
    result[positive] = 1.0 / (1.0 + np.exp(-array[positive]))
    exponent = np.exp(array[~positive])
    result[~positive] = exponent / (1.0 + exponent)
    return result


def _calibrated_intercept(
    offsets: NDArray[np.float64],
    target_mean: float,
    weights: NDArray[np.float64] | None = None,
) -> float:
    if weights is None:
        weights = np.ones_like(offsets, dtype=float)
    if offsets.shape != weights.shape:
        raise ValueError("offsets and weights must have identical shapes")
    if np.any(weights < 0.0) or float(np.sum(weights)) <= 0.0:
        raise ValueError("calibration weights must be nonnegative with positive sum")

    lower = -40.0
    upper = 40.0
    weight_sum = float(np.sum(weights))
    for _ in range(100):
        midpoint = (lower + upper) / 2.0
        mean = float(np.sum(weights * _expit(midpoint + offsets)) / weight_sum)
        if mean < target_mean:
            lower = midpoint
        else:
            upper = midpoint
    return (lower + upper) / 2.0


def pilot_probabilities(scenario: PilotScenario) -> NDArray[np.float64]:
    """Return D x F x I x Cpilot x E fixed failure probabilities."""

    family = _standardized_scores(FAMILIES_PER_DOMAIN)[:, None, None, None]
    instance = _standardized_scores(INSTANCES_PER_FAMILY)[None, :, None, None]
    config = _standardized_scores(N_PILOT_CONFIGURATIONS)[None, None, :, None]
    environment = _standardized_scores(N_ENVIRONMENTS)[None, None, None, :]
    offsets = (
        scenario.family_logit_sd * family
        + scenario.instance_logit_sd * instance
        + scenario.config_logit_sd * config
        + scenario.environment_logit_sd * environment
    )
    probabilities = np.empty(
        (
            N_DOMAINS,
            FAMILIES_PER_DOMAIN,
            INSTANCES_PER_FAMILY,
            N_PILOT_CONFIGURATIONS,
            N_ENVIRONMENTS,
        ),
        dtype=float,
    )
    for domain, target in enumerate(scenario.domain_failure_rates):
        intercept = _calibrated_intercept(offsets, target)
        probabilities[domain] = _expit(intercept + offsets)
    return probabilities


def classify_pilot_gate(
    *,
    total_failures: NDArray[np.int64],
    total_trials: int,
    failing_families: NDArray[np.int64],
    successful_families: NDArray[np.int64],
    failing_domains: NDArray[np.int64],
    successful_domains: NDArray[np.int64],
    gate: PilotGate,
) -> NDArray[np.int8]:
    """Apply one outcome-blind gate with exclusive, ordered failure states."""

    arrays = (
        failing_families,
        successful_families,
        failing_domains,
        successful_domains,
    )
    if any(array.shape != total_failures.shape for array in arrays):
        raise ValueError("all pilot summary arrays must have identical shapes")
    states = np.full(total_failures.shape, GateState.PROCEED, dtype=np.int8)
    ceiling = total_failures < gate.min_failures
    floor = (total_trials - total_failures) < gate.min_successes
    concentrated = (
        (failing_families < gate.min_failing_families)
        | (successful_families < gate.min_successful_families)
        | (failing_domains < gate.min_failing_domains)
        | (successful_domains < gate.min_successful_domains)
    )
    states[concentrated] = GateState.CONCENTRATED
    states[floor] = GateState.FLOOR
    states[ceiling] = GateState.CEILING
    return states


def simulate_pilot_scenario(
    scenario: PilotScenario,
    *,
    replicates: int,
    seed: int,
    gates: Iterable[PilotGate] = PILOT_GATES,
) -> list[dict[str, float | int | str]]:
    if replicates < 1:
        raise ValueError("replicates must be positive")
    probabilities = pilot_probabilities(scenario)
    rng = np.random.default_rng(seed)
    failures = rng.binomial(1, probabilities, size=(replicates, *probabilities.shape))
    total_trials = int(np.prod(probabilities.shape))
    pilot_seeded_trials = (
        N_SEEDED_VARIANTS
        * N_PILOT_CONFIGURATIONS
        * N_ENVIRONMENTS
        * N_PILOT_SEEDED_REPETITIONS
    )
    total_failures = np.sum(failures, axis=(1, 2, 3, 4, 5))
    trials_per_family = INSTANCES_PER_FAMILY * N_PILOT_CONFIGURATIONS * N_ENVIRONMENTS
    family_failures = np.sum(failures, axis=(3, 4, 5))
    domain_failures = np.sum(failures, axis=(2, 3, 4, 5))
    failing_families = np.sum(family_failures > 0, axis=(1, 2))
    successful_families = np.sum(
        family_failures < trials_per_family,
        axis=(1, 2),
    )
    failing_domains = np.sum(domain_failures > 0, axis=1)
    successful_domains = np.sum(
        domain_failures < trials_per_family * FAMILIES_PER_DOMAIN,
        axis=1,
    )

    rows: list[dict[str, float | int | str]] = []
    for gate in gates:
        states = classify_pilot_gate(
            total_failures=total_failures,
            total_trials=total_trials,
            failing_families=failing_families,
            successful_families=successful_families,
            failing_domains=failing_domains,
            successful_domains=successful_domains,
            gate=gate,
        )
        row: dict[str, float | int | str] = {
            "record_type": "pilot_gate",
            "scenario": scenario.name,
            "gate": gate.name,
            "replicates": replicates,
            "seed": seed,
            "pilot_capability_trials": total_trials,
            "pilot_capability_valid_slots_per_family_cell": (
                INSTANCES_PER_FAMILY
            ),
            "pilot_seeded_trials": pilot_seeded_trials,
            "pilot_full_valid_trials": total_trials + pilot_seeded_trials,
            "true_mean_failure_rate": float(np.mean(probabilities)),
            "expected_failures": float(np.sum(probabilities)),
            "min_failures": gate.min_failures,
            "min_successes": gate.min_successes,
            "min_failing_families": gate.min_failing_families,
            "min_failing_domains": gate.min_failing_domains,
        }
        for state in GateState:
            probability = float(np.mean(states == state))
            key = state.name.lower()
            row[f"{key}_probability"] = probability
            row[f"{key}_mcse"] = math.sqrt(
                probability * (1.0 - probability) / replicates
            )
        rows.append(row)
    return rows


def confirmatory_probabilities(
    scenario: ConfirmScenario,
) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    """Return D x F x I x C probabilities calibrated by content domain."""

    family = _standardized_scores(FAMILIES_PER_DOMAIN)[:, None, None]
    instance = _standardized_scores(INSTANCES_PER_FAMILY)[None, :, None]
    config = _standardized_scores(N_CONFIGURATIONS)[None, None, :]
    baseline_offsets = (
        scenario.family_logit_sd * family
        + scenario.instance_logit_sd * instance
        + scenario.config_logit_sd * config
    )
    windows_offsets = (
        baseline_offsets
        + scenario.family_context_logit_sd * family
        - scenario.instance_context_logit_sd * instance
        + scenario.config_context_logit_sd * config
    )
    shape = (
        N_DOMAINS,
        FAMILIES_PER_DOMAIN,
        INSTANCES_PER_FAMILY,
        N_CONFIGURATIONS,
    )
    linux = np.empty(shape, dtype=float)
    windows = np.empty(shape, dtype=float)
    for domain in range(N_DOMAINS):
        linux_intercept = _calibrated_intercept(
            baseline_offsets,
            scenario.linux_domain_rates[domain],
        )
        windows_intercept = _calibrated_intercept(
            windows_offsets,
            scenario.windows_domain_rates[domain],
        )
        linux[domain] = _expit(linux_intercept + baseline_offsets)
        windows[domain] = _expit(windows_intercept + windows_offsets)
    return linux, windows


def broad_instance_counts(repetitions_per_cell: int) -> NDArray[np.int64]:
    """Return the exact per-instance counts from the candidate scheduler."""
    counts = np.zeros(
        (
            N_DOMAINS,
            FAMILIES_PER_DOMAIN,
            INSTANCES_PER_FAMILY,
            N_CONFIGURATIONS,
        ),
        dtype=np.int64,
    )
    instance_ids = tuple(f"I{i:02d}" for i in range(1, 4))
    reference_environment = REGISTERED_ENVIRONMENT_IDS[0]
    for domain in range(N_DOMAINS):
        for family in range(FAMILIES_PER_DOMAIN):
            ordinal = domain * FAMILIES_PER_DOMAIN + family + 1
            assignments = build_instance_schedule(
                family_id=f"F{ordinal:02d}",
                instance_ids=instance_ids,
                config_ids=REGISTERED_CONFIG_IDS,
                environment_ids=REGISTERED_ENVIRONMENT_IDS,
                repetitions_per_cell=repetitions_per_cell,
            )
            for assignment in assignments:
                if assignment.environment_id != reference_environment:
                    continue
                config = REGISTERED_CONFIG_IDS.index(assignment.config_id)
                instance = instance_ids.index(assignment.instance_id)
                counts[domain, family, instance, config] += 1
    if np.any(counts < 1):
        raise RuntimeError("candidate broad design left an instance unobserved")
    if not np.all(np.sum(counts, axis=2) == repetitions_per_cell):
        raise RuntimeError("candidate broad design has incorrect cell totals")
    return counts


def _summarize_h1_estimates(
    *,
    scenario: ConfirmScenario,
    design: str,
    base_common_n: int,
    n_cap: int,
    n_seed: int,
    estimates: NDArray[np.float64],
    design_roster_true_rd: float,
    replicates: int,
    seed: int,
) -> dict[str, float | int | str]:
    target_rd = float(
        np.mean(
            np.asarray(scenario.windows_domain_rates)
            - np.asarray(scenario.linux_domain_rates)
        )
    )
    sampling_sd = float(np.std(estimates, ddof=1))
    z_value = NormalDist().inv_cdf(0.5 + CONFIDENCE / 2.0)
    lower = estimates - z_value * sampling_sd
    upper = estimates + z_value * sampling_sd
    domain_rds = np.asarray(scenario.windows_domain_rates) - np.asarray(
        scenario.linux_domain_rates
    )
    leave_one_out = np.asarray(
        [np.mean(np.delete(domain_rds, index)) for index in range(N_DOMAINS)]
    )
    return {
        "record_type": "h1_target_precision",
        "scenario": scenario.name,
        "design": design,
        "replicates": replicates,
        "seed": seed,
        "base_common_n": base_common_n,
        "n_cap": n_cap,
        "n_seed": n_seed,
        "confirmatory_trials_full_matrix": 35 * (
            (5 if design == "A_current_five" else 12) * n_cap
            + N_SEEDED_VARIANTS * n_seed
        ),
        "target_six_domain_rd": target_rd,
        "design_roster_true_rd": design_roster_true_rd,
        "roster_estimand_mismatch": design_roster_true_rd - target_rd,
        "mean_estimate": float(np.mean(estimates)),
        "bias_vs_design_roster": float(np.mean(estimates) - design_roster_true_rd),
        "bias_vs_six_domain_target": float(np.mean(estimates) - target_rd),
        "rmse_vs_six_domain_target": float(
            np.sqrt(np.mean((estimates - target_rd) ** 2))
        ),
        "sampling_sd": sampling_sd,
        "estimate_q025": float(np.quantile(estimates, 0.025)),
        "estimate_q975": float(np.quantile(estimates, 0.975)),
        "reference_above_5pp_probability": float(np.mean(lower > DECISION_RD)),
        "reference_below_5pp_probability": float(np.mean(upper < DECISION_RD)),
        "reference_inconclusive_probability": float(
            np.mean((lower <= DECISION_RD) & (upper >= DECISION_RD))
        ),
        "max_abs_true_domain_rd": float(np.max(np.abs(domain_rds))),
        "leave_one_domain_out_min_rd": float(np.min(leave_one_out)),
        "leave_one_domain_out_max_rd": float(np.max(leave_one_out)),
        "true_domain_rds": ",".join(f"{value:.6f}" for value in domain_rds),
        "interval_note": "oracle_normal_reference_not_confirmatory_model",
    }


def simulate_h1_scenario(
    scenario: ConfirmScenario,
    *,
    base_common_ns: Iterable[int],
    replicates: int,
    seed: int,
) -> list[dict[str, float | int | str]]:
    if replicates < 2:
        raise ValueError("replicates must be at least two")
    linux, windows = confirmatory_probabilities(scenario)
    rows: list[dict[str, float | int | str]] = []
    rng = np.random.default_rng(seed)

    current_linux = np.stack(
        [
            linux[domain, family, CURRENT_INSTANCE_INDEX, :]
            for domain, family in CURRENT_FAMILY_COORDS
        ]
    )
    current_windows = np.stack(
        [
            windows[domain, family, CURRENT_INSTANCE_INDEX, :]
            for domain, family in CURRENT_FAMILY_COORDS
        ]
    )
    current_true_rd = float(np.mean(current_windows) - np.mean(current_linux))
    target_true_rd = float(np.mean(windows) - np.mean(linux))

    for base_n in base_common_ns:
        if base_n < 3:
            raise ValueError("base common N must be at least three")
        split_n = math.ceil(5 * base_n / 12)
        if split_n < INSTANCES_PER_FAMILY:
            raise ValueError("split N must exercise every candidate instance")

        current_l_counts = rng.binomial(
            base_n,
            current_linux,
            size=(replicates, *current_linux.shape),
        )
        current_w_counts = rng.binomial(
            base_n,
            current_windows,
            size=(replicates, *current_windows.shape),
        )
        current_estimates = np.mean(
            current_w_counts / base_n - current_l_counts / base_n,
            axis=(1, 2),
        )
        rows.append(
            _summarize_h1_estimates(
                scenario=scenario,
                design="A_current_five",
                base_common_n=base_n,
                n_cap=base_n,
                n_seed=base_n,
                estimates=current_estimates,
                design_roster_true_rd=current_true_rd,
                replicates=replicates,
                seed=seed,
            )
        )

        for design, n_cap in (
            ("B_broad_common_n", base_n),
            ("C_broad_split_n", split_n),
        ):
            counts = broad_instance_counts(n_cap)
            linux_counts = rng.binomial(
                counts,
                linux,
                size=(replicates, *linux.shape),
            )
            windows_counts = rng.binomial(
                counts,
                windows,
                size=(replicates, *windows.shape),
            )
            estimates = np.mean(
                windows_counts / counts - linux_counts / counts,
                axis=(1, 2, 3, 4),
            )
            rows.append(
                _summarize_h1_estimates(
                    scenario=scenario,
                    design=design,
                    base_common_n=base_n,
                    n_cap=n_cap,
                    n_seed=base_n,
                    estimates=estimates,
                    design_roster_true_rd=target_true_rd,
                    replicates=replicates,
                    seed=seed,
                )
            )
    return rows


def _task_config_offsets(
    task_count: int,
    *,
    task_sd: float,
    config_sd: float,
) -> NDArray[np.float64]:
    task = _standardized_scores(task_count)[:, None]
    config = _standardized_scores(N_CONFIGURATIONS)[None, :]
    return task_sd * task + config_sd * config


def _class_failure_probabilities(
    task_count: int,
    *,
    linux_mean: float,
    windows_mean: float,
    scenario: H2Scenario,
) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    offsets = _task_config_offsets(
        task_count,
        task_sd=scenario.task_logit_sd,
        config_sd=scenario.config_logit_sd,
    )
    task = _standardized_scores(task_count)[:, None]
    config = _standardized_scores(N_CONFIGURATIONS)[None, :]
    windows_offsets = offsets + scenario.context_interaction_logit_sd * (
        task - config
    )
    linux_intercept = _calibrated_intercept(offsets, linux_mean)
    windows_intercept = _calibrated_intercept(windows_offsets, windows_mean)
    return (
        _expit(linux_intercept + offsets),
        _expit(windows_intercept + windows_offsets),
    )


def h2_probabilities(
    scenario: H2Scenario,
    *,
    capability_count: int,
    n_cap: int,
    n_seed: int,
) -> tuple[
    NDArray[np.int64],
    NDArray[np.float64],
    NDArray[np.float64],
    NDArray[np.float64],
    NDArray[np.float64],
]:
    cap_l, cap_w = _class_failure_probabilities(
        capability_count,
        linux_mean=scenario.capability_failure_linux,
        windows_mean=scenario.capability_failure_windows,
        scenario=scenario,
    )
    seed_l, seed_w = _class_failure_probabilities(
        N_SEEDED_VARIANTS,
        linux_mean=scenario.seeded_failure_linux,
        windows_mean=scenario.seeded_failure_windows,
        scenario=scenario,
    )
    p_l = np.concatenate((cap_l, seed_l), axis=0)
    p_w = np.concatenate((cap_w, seed_w), axis=0)
    n = np.concatenate(
        (
            np.full(cap_l.shape, n_cap, dtype=np.int64),
            np.full(seed_l.shape, n_seed, dtype=np.int64),
        ),
        axis=0,
    )

    de_offsets = _task_config_offsets(
        capability_count + N_SEEDED_VARIANTS,
        task_sd=scenario.de_task_logit_sd,
        config_sd=scenario.de_config_logit_sd,
    )
    q_l_intercept = _calibrated_intercept(
        de_offsets,
        scenario.de_probability_linux,
        weights=n * p_l,
    )
    q_w_intercept = _calibrated_intercept(
        -de_offsets,
        scenario.de_probability_windows,
        weights=n * p_w,
    )
    q_l = _expit(q_l_intercept + de_offsets)
    q_w = _expit(q_w_intercept - de_offsets)
    return n, p_l, p_w, q_l, q_w


def simulate_h2_design(
    scenario: H2Scenario,
    *,
    design: str,
    capability_count: int,
    n_cap: int,
    n_seed: int,
    base_common_n: int,
    replicates: int,
    seed: int,
) -> dict[str, float | int | str]:
    if replicates < 1:
        raise ValueError("replicates must be positive")
    n, p_l, p_w, q_l, q_w = h2_probabilities(
        scenario,
        capability_count=capability_count,
        n_cap=n_cap,
        n_seed=n_seed,
    )
    rng = np.random.default_rng(seed)
    failure_l = rng.binomial(n, p_l, size=(replicates, *p_l.shape))
    failure_w = rng.binomial(n, p_w, size=(replicates, *p_w.shape))
    de_l = rng.binomial(failure_l, q_l)
    de_w = rng.binomial(failure_w, q_w)

    pooled_failure_l = np.sum(failure_l, axis=(1, 2))
    pooled_failure_w = np.sum(failure_w, axis=(1, 2))
    pooled_de_l = np.sum(de_l, axis=(1, 2))
    pooled_de_w = np.sum(de_w, axis=(1, 2))
    denominator_ok = (pooled_failure_l >= 10) & (pooled_failure_w >= 10)
    ratio_estimable = (
        denominator_ok
        & (pooled_de_l > 0)
        & (pooled_de_w > 0)
    )

    observed_q_l = np.full(replicates, np.nan)
    observed_q_w = np.full(replicates, np.nan)
    observed_rr = np.full(replicates, np.nan)
    rr_lower = np.full(replicates, np.nan)
    with np.errstate(divide="ignore", invalid="ignore", over="ignore"):
        observed_q_l[ratio_estimable] = (
            pooled_de_l[ratio_estimable] / pooled_failure_l[ratio_estimable]
        )
        observed_q_w[ratio_estimable] = (
            pooled_de_w[ratio_estimable] / pooled_failure_w[ratio_estimable]
        )
        observed_rr[ratio_estimable] = (
            observed_q_w[ratio_estimable] / observed_q_l[ratio_estimable]
        )
        variance = (
            1.0 / pooled_de_w[ratio_estimable]
            - 1.0 / pooled_failure_w[ratio_estimable]
            + 1.0 / pooled_de_l[ratio_estimable]
            - 1.0 / pooled_failure_l[ratio_estimable]
        )
        z_value = NormalDist().inv_cdf(0.5 + CONFIDENCE / 2.0)
        rr_lower[ratio_estimable] = np.exp(
            np.log(observed_rr[ratio_estimable]) - z_value * np.sqrt(variance)
        )

    per_config_ok = (
        (np.sum(failure_l, axis=1) >= 5)
        & (np.sum(failure_w, axis=1) >= 5)
    )
    true_q_l = float(np.sum(n * p_l * q_l) / np.sum(n * p_l))
    true_q_w = float(np.sum(n * p_w * q_w) / np.sum(n * p_w))
    reference_support = ratio_estimable & (rr_lower > 2.0)

    return {
        "record_type": "h2_reference",
        "scenario": scenario.name,
        "design": design,
        "replicates": replicates,
        "seed": seed,
        "base_common_n": base_common_n,
        "capability_count": capability_count,
        "n_cap": n_cap,
        "n_seed": n_seed,
        "confirmatory_trials_full_matrix": 35 * (
            capability_count * n_cap + N_SEEDED_VARIANTS * n_seed
        ),
        "expected_failures_linux": float(np.sum(n * p_l)),
        "expected_failures_windows": float(np.sum(n * p_w)),
        "both_pooled_denominators_ge10_probability": float(
            np.mean(denominator_ok)
        ),
        "either_pooled_denominator_zero_probability": float(
            np.mean((pooled_failure_l == 0) | (pooled_failure_w == 0))
        ),
        "ratio_estimable_probability": float(np.mean(ratio_estimable)),
        "mean_estimable_configs_ge5_each_context": float(
            np.mean(np.sum(per_config_ok, axis=1))
        ),
        "all_configs_ge5_each_context_probability": float(
            np.mean(np.all(per_config_ok, axis=1))
        ),
        "true_conditional_de_linux": true_q_l,
        "true_conditional_de_windows": true_q_w,
        "true_conditional_de_rr": true_q_w / true_q_l,
        "observed_point_rr_ge2_probability": float(
            np.mean(ratio_estimable & (observed_rr >= 2.0))
        ),
        "reference_lower_ci_above2_probability": float(
            np.mean(reference_support)
        ),
        "reference_note": (
            "pooled_log_wald_ignores_clustering_irr_and_model_convergence"
        ),
    }


def simulate_h2_scenario(
    scenario: H2Scenario,
    *,
    base_common_ns: Iterable[int],
    replicates: int,
    seed: int,
) -> list[dict[str, float | int | str]]:
    rows: list[dict[str, float | int | str]] = []
    for base_n in base_common_ns:
        split_n = math.ceil(5 * base_n / 12)
        designs = (
            ("A_current_five", 5, base_n, base_n),
            ("B_broad_common_n", 12, base_n, base_n),
            ("C_broad_split_n", 12, split_n, base_n),
        )
        for index, (design, cap_count, n_cap, n_seed) in enumerate(designs):
            rows.append(
                simulate_h2_design(
                    scenario,
                    design=design,
                    capability_count=cap_count,
                    n_cap=n_cap,
                    n_seed=n_seed,
                    base_common_n=base_n,
                    replicates=replicates,
                    seed=seed + 100 * base_n + index,
                )
            )
    return rows


def default_pilot_scenarios() -> tuple[PilotScenario, ...]:
    diffuse_rates = (0.005, 0.01, 0.02, 0.05, 0.10, 0.50, 0.95, 0.99)
    diffuse = tuple(
        PilotScenario(
            name=f"diffuse_{rate:.3f}",
            domain_failure_rates=(rate,) * N_DOMAINS,
        )
        for rate in diffuse_rates
    )
    concentrated = (
        PilotScenario(
            "one_domain_mean_0.05",
            (0.275, 0.005, 0.005, 0.005, 0.005, 0.005),
        ),
        PilotScenario(
            "one_domain_mean_0.10",
            (0.575, 0.005, 0.005, 0.005, 0.005, 0.005),
        ),
    )
    return diffuse + concentrated


def default_confirm_scenarios() -> tuple[ConfirmScenario, ...]:
    return (
        ConfirmScenario("diffuse_null", (0.10,) * 6, (0.10,) * 6),
        ConfirmScenario("diffuse_threshold", (0.10,) * 6, (0.15,) * 6),
        ConfirmScenario("diffuse_strong", (0.10,) * 6, (0.20,) * 6),
        ConfirmScenario(
            "effect_only_in_omitted_domain_D",
            (0.10,) * 6,
            (0.10, 0.10, 0.10, 0.40, 0.10, 0.10),
            family_logit_sd=0.0,
            instance_logit_sd=0.0,
            config_logit_sd=0.0,
            family_context_logit_sd=0.0,
            instance_context_logit_sd=0.0,
            config_context_logit_sd=0.0,
        ),
        ConfirmScenario(
            "effect_only_in_overweighted_domain_A",
            (0.10,) * 6,
            (0.40, 0.10, 0.10, 0.10, 0.10, 0.10),
            family_logit_sd=0.0,
            instance_logit_sd=0.0,
            config_logit_sd=0.0,
            family_context_logit_sd=0.0,
            instance_context_logit_sd=0.0,
            config_context_logit_sd=0.0,
        ),
        ConfirmScenario(
            "opposing_domain_mechanisms",
            (0.20,) * 6,
            (0.32, 0.20, 0.20, 0.08, 0.20, 0.20),
            family_logit_sd=0.0,
            instance_logit_sd=0.0,
            config_logit_sd=0.0,
            family_context_logit_sd=0.0,
            instance_context_logit_sd=0.0,
            config_context_logit_sd=0.0,
        ),
    )


def default_h2_scenarios() -> tuple[H2Scenario, ...]:
    return (
        H2Scenario("sparse_boundary", 0.005, 0.005, 0.01, 0.01, 0.10, 0.20),
        H2Scenario("low_boundary", 0.01, 0.015, 0.02, 0.03, 0.10, 0.20),
        H2Scenario("moderate_boundary", 0.05, 0.08, 0.10, 0.15, 0.10, 0.20),
        H2Scenario("moderate_strong", 0.05, 0.08, 0.10, 0.15, 0.10, 0.30),
        H2Scenario("moderate_null", 0.05, 0.08, 0.10, 0.15, 0.15, 0.15),
    )


def run_default_grid(
    *,
    sections: set[str],
    replicates: int,
    seed: int,
    base_common_ns: tuple[int, ...] = (6, 12, 24),
) -> list[dict[str, float | int | str]]:
    rows: list[dict[str, float | int | str]] = []
    if "pilot" in sections:
        for index, scenario in enumerate(default_pilot_scenarios()):
            rows.extend(
                simulate_pilot_scenario(
                    scenario,
                    replicates=replicates,
                    seed=seed + index,
                )
            )
    if "h1" in sections:
        for index, scenario in enumerate(default_confirm_scenarios()):
            rows.extend(
                simulate_h1_scenario(
                    scenario,
                    base_common_ns=base_common_ns,
                    replicates=replicates,
                    seed=seed + 1_000 + index,
                )
            )
    if "h2" in sections:
        for index, scenario in enumerate(default_h2_scenarios()):
            rows.extend(
                simulate_h2_scenario(
                    scenario,
                    base_common_ns=base_common_ns,
                    replicates=replicates,
                    seed=seed + 2_000 + index,
                )
            )
    return rows


def _parse_sections(raw: str) -> set[str]:
    values = {value.strip() for value in raw.split(",") if value.strip()}
    allowed = {"pilot", "h1", "h2"}
    if not values or not values <= allowed:
        raise argparse.ArgumentTypeError(
            "sections must be a comma-separated subset of pilot,h1,h2"
        )
    return values


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run prospective D-013 pilot, H1, and H2 reference grids."
    )
    parser.add_argument(
        "--sections",
        type=_parse_sections,
        default={"pilot", "h1", "h2"},
    )
    parser.add_argument("--replicates", type=int, default=10_000)
    parser.add_argument("--seed", type=int, default=20260801)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.replicates < 2:
        raise SystemExit("--replicates must be at least two")
    rows = run_default_grid(
        sections=args.sections,
        replicates=args.replicates,
        seed=args.seed,
    )
    for row in rows:
        print(json.dumps(row, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
