"""Prospective recovery envelope for the D-005 H1 interval candidate.

This evidence module stresses the fixed-roster Clopper-Pearson-MOVER
candidate under balanced calendar drift, shared and context-specific latent
cluster shocks, and matched-slot dependence.  It never reads benchmark data
and it does not accept an interval, N, or resource cap.

The target in every replicate is the equally weighted mean of the actual
slot-level generating probabilities.  This matters when a calendar wave or
latent provider state makes trials within a fixed leaf non-identically
distributed.  The production estimator still receives only aggregate event
counts and therefore cannot condition on the simulated nuisance state.
"""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass
from typing import Iterable, Sequence

import numpy as np
from numpy.typing import NDArray
from scipy.special import expit, logit
from scipy.stats import norm

from analysis.d005_finite_roster_irr import _clopper_pearson_bounds
from analysis.d013_ceiling_operating_characteristics import (
    CONFIDENCE,
    DECISION_RD,
    ConfirmScenario,
    broad_instance_counts,
    confirmatory_probabilities,
    default_confirm_scenarios,
)


@dataclass(frozen=True)
class H1RecoveryMechanism:
    """One prospective nuisance/dependence mechanism.

    Logit shifts are ordered calendar-wave effects.  Shared cluster shocks
    apply identically to both focal contexts within a domain/configuration;
    differential shocks are independently drawn for each context.  ``rho``
    is the Gaussian-copula association between matched focal-context slots.
    """

    name: str
    common_wave_logit_shifts: tuple[float, ...] = (0.0, 0.0, 0.0, 0.0)
    windows_wave_logit_shifts: tuple[float, ...] = (0.0, 0.0, 0.0, 0.0)
    shared_domain_config_sd: float = 0.0
    differential_domain_config_sd: float = 0.0
    matched_slot_rho: float = 0.0

    def __post_init__(self) -> None:
        if not self.name or self.name.strip() != self.name:
            raise ValueError("mechanism name must be non-empty and trimmed")
        if len(self.common_wave_logit_shifts) != 4 or len(
            self.windows_wave_logit_shifts
        ) != 4:
            raise ValueError("recovery mechanisms require exactly four waves")
        shifts = self.common_wave_logit_shifts + self.windows_wave_logit_shifts
        if any(not math.isfinite(value) for value in shifts):
            raise ValueError("calendar-wave shifts must be finite")
        if (
            not math.isfinite(self.shared_domain_config_sd)
            or self.shared_domain_config_sd < 0.0
            or not math.isfinite(self.differential_domain_config_sd)
            or self.differential_domain_config_sd < 0.0
        ):
            raise ValueError("cluster standard deviations must be finite and nonnegative")
        if not -0.95 <= self.matched_slot_rho <= 0.95:
            raise ValueError("matched-slot rho must lie in [-0.95, 0.95]")


def default_recovery_mechanisms() -> tuple[H1RecoveryMechanism, ...]:
    """Return the prospective nuisance envelope, including falsification arms."""

    return (
        H1RecoveryMechanism("independent_reference"),
        H1RecoveryMechanism(
            "balanced_common_calendar_drift",
            common_wave_logit_shifts=(-0.60, -0.20, 0.20, 0.60),
        ),
        H1RecoveryMechanism(
            "balanced_differential_calendar_drift",
            common_wave_logit_shifts=(-0.30, -0.10, 0.10, 0.30),
            windows_wave_logit_shifts=(-0.30, -0.10, 0.10, 0.30),
        ),
        H1RecoveryMechanism(
            "shared_domain_configuration_state",
            shared_domain_config_sd=0.75,
        ),
        H1RecoveryMechanism(
            "context_specific_domain_configuration_state",
            differential_domain_config_sd=0.40,
        ),
        H1RecoveryMechanism(
            "positive_matched_slot_dependence",
            matched_slot_rho=0.40,
        ),
        H1RecoveryMechanism(
            "negative_matched_slot_falsification",
            matched_slot_rho=-0.40,
        ),
        H1RecoveryMechanism(
            "combined_operational_stress",
            common_wave_logit_shifts=(-0.45, -0.15, 0.15, 0.45),
            windows_wave_logit_shifts=(-0.15, -0.05, 0.05, 0.15),
            shared_domain_config_sd=0.50,
            differential_domain_config_sd=0.20,
            matched_slot_rho=0.25,
        ),
    )


def _slot_layout(counts: NDArray[np.int64]) -> tuple[NDArray[np.bool_], NDArray[np.int64]]:
    flat = counts.reshape(-1)
    slots = np.arange(int(np.max(flat)), dtype=np.int64)
    active = slots[None, :] < flat[:, None]
    # Rotate the four waves over leaves so remainder slots do not always land
    # in the same wave when a leaf has three rather than four observations.
    waves = (np.arange(flat.size)[:, None] + slots[None, :]) % 4
    return active, waves


def _domain_configuration_indices(shape: Sequence[int]) -> tuple[NDArray[np.int64], NDArray[np.int64]]:
    grid = np.indices(tuple(shape), dtype=np.int64)
    return grid[0].reshape(-1), grid[-1].reshape(-1)


def simulate_h1_recovery(
    scenario: ConfirmScenario,
    mechanism: H1RecoveryMechanism,
    *,
    repetitions_per_family_config: int = 10,
    replicates: int = 5_000,
    seed: int = 20260815,
    batch_size: int = 250,
) -> dict[str, float | int | str | bool]:
    """Simulate one exact split-N H1 recovery cell.

    The screen flags, but does not silently reject or approve, mechanisms with
    coverage below 94%, wrong five-point declarations above 1%, or absolute
    point bias above five tenths of a percentage point.  The 94% screen is a
    Monte-Carlo tolerance around a nominal 95% interval, not a new inference
    confidence level.
    """

    if repetitions_per_family_config < 3:
        raise ValueError("every frozen instance must be exercised")
    if replicates < 1 or batch_size < 1:
        raise ValueError("replicates and batch_size must be positive")
    linux_base, windows_base = confirmatory_probabilities(scenario)
    counts = broad_instance_counts(repetitions_per_family_config)
    if counts.shape != linux_base.shape:
        raise RuntimeError("probability and fixed-roster shapes disagree")
    active, waves = _slot_layout(counts)
    domain_index, config_index = _domain_configuration_indices(counts.shape)
    flat_counts = counts.reshape(-1)
    cells = flat_counts.size
    slots = active.shape[1]
    active3 = active[None, :, :]
    common_wave = np.asarray(mechanism.common_wave_logit_shifts)[waves]
    windows_wave = np.asarray(mechanism.windows_wave_logit_shifts)[waves]
    linux_logit = logit(linux_base.reshape(-1))
    windows_logit = logit(windows_base.reshape(-1))
    rng = np.random.default_rng(seed)

    covered_count = 0
    wrong_count = 0
    relevant_count = 0
    bounded_count = 0
    inconclusive_count = 0
    point_error_sum = 0.0
    interval_width_sum = 0.0
    target_sum = 0.0
    completed = 0

    while completed < replicates:
        current = min(batch_size, replicates - completed)
        shared = np.zeros((current, cells), dtype=float)
        if mechanism.shared_domain_config_sd:
            effects = rng.normal(
                0.0,
                mechanism.shared_domain_config_sd,
                size=(current, counts.shape[0], counts.shape[-1]),
            )
            shared = effects[:, domain_index, config_index]
        linux_differential = np.zeros((current, cells), dtype=float)
        windows_differential = np.zeros((current, cells), dtype=float)
        if mechanism.differential_domain_config_sd:
            effects = rng.normal(
                0.0,
                mechanism.differential_domain_config_sd,
                size=(current, 2, counts.shape[0], counts.shape[-1]),
            )
            linux_differential = effects[:, 0, domain_index, config_index]
            windows_differential = effects[:, 1, domain_index, config_index]

        linux_probability = expit(
            linux_logit[None, :, None]
            + shared[:, :, None]
            + linux_differential[:, :, None]
            + common_wave[None, :, :]
        )
        windows_probability = expit(
            windows_logit[None, :, None]
            + shared[:, :, None]
            + windows_differential[:, :, None]
            + common_wave[None, :, :]
            + windows_wave[None, :, :]
        )

        first = rng.standard_normal((current, cells, slots))
        second = (
            mechanism.matched_slot_rho * first
            + math.sqrt(1.0 - mechanism.matched_slot_rho**2)
            * rng.standard_normal((current, cells, slots))
        )
        linux_event = (norm.cdf(first) < linux_probability) & active3
        windows_event = (norm.cdf(second) < windows_probability) & active3
        linux_count = np.sum(linux_event, axis=2, dtype=np.int64)
        windows_count = np.sum(windows_event, axis=2, dtype=np.int64)
        linux_rate = linux_count / flat_counts
        windows_rate = windows_count / flat_counts
        estimate = np.mean(windows_rate - linux_rate, axis=1)

        linux_slot_mean = np.sum(linux_probability * active3, axis=2) / flat_counts
        windows_slot_mean = np.sum(windows_probability * active3, axis=2) / flat_counts
        target = np.mean(windows_slot_mean - linux_slot_mean, axis=1)

        linux_lower, linux_upper = _clopper_pearson_bounds(
            linux_count, flat_counts, confidence=CONFIDENCE
        )
        windows_lower, windows_upper = _clopper_pearson_bounds(
            windows_count, flat_counts, confidence=CONFIDENCE
        )
        weight = 1.0 / cells
        lower = np.maximum(
            -1.0,
            estimate
            - np.sqrt(
                weight**2
                * np.sum(
                    (windows_rate - windows_lower) ** 2
                    + (linux_upper - linux_rate) ** 2,
                    axis=1,
                )
            ),
        )
        upper = np.minimum(
            1.0,
            estimate
            + np.sqrt(
                weight**2
                * np.sum(
                    (windows_upper - windows_rate) ** 2
                    + (linux_rate - linux_lower) ** 2,
                    axis=1,
                )
            ),
        )
        relevant = lower > DECISION_RD
        bounded = upper < DECISION_RD
        inconclusive = ~(relevant | bounded)
        wrong = np.where(
            target < DECISION_RD,
            relevant,
            np.where(target > DECISION_RD, bounded, relevant | bounded),
        )

        covered_count += int(np.sum((lower <= target) & (target <= upper)))
        wrong_count += int(np.sum(wrong))
        relevant_count += int(np.sum(relevant))
        bounded_count += int(np.sum(bounded))
        inconclusive_count += int(np.sum(inconclusive))
        point_error_sum += float(np.sum(estimate - target))
        interval_width_sum += float(np.sum(upper - lower))
        target_sum += float(np.sum(target))
        completed += current

    coverage = covered_count / replicates
    wrong_probability = wrong_count / replicates
    point_bias = point_error_sum / replicates
    screen_pass = (
        coverage >= 0.94
        and wrong_probability <= 0.01
        and abs(point_bias) <= 0.005
    )
    return {
        "record_type": "d005_h1_recovery_envelope",
        "scenario": scenario.name,
        "mechanism": mechanism.name,
        "replicates": replicates,
        "seed": seed,
        "batch_size": batch_size,
        "repetitions_per_family_config": repetitions_per_family_config,
        "cells_per_context": cells,
        "trials_two_contexts": int(2 * np.sum(counts)),
        "mean_true_slot_weighted_rd": target_sum / replicates,
        "point_rd_bias": point_bias,
        "coverage_probability": coverage,
        "wrong_threshold_declaration_probability": wrong_probability,
        "decision_relevant_probability": relevant_count / replicates,
        "bounded_small_probability": bounded_count / replicates,
        "inconclusive_probability": inconclusive_count / replicates,
        "mean_interval_width": interval_width_sum / replicates,
        "screen_coverage_floor": 0.94,
        "screen_wrong_declaration_ceiling": 0.01,
        "screen_absolute_bias_ceiling": 0.005,
        "screen_pass": screen_pass,
        "incomplete_roster_policy": "no_decision_retries_do_not_consume_valid_slot",
    }


def roster_completion_probability(
    *,
    valid_slots: int,
    invalid_attempt_probability: float,
    attempts_per_slot: int,
) -> float:
    """Return P(all slots complete) under an operational retry-cap probe.

    This is an availability calculation only.  A cap-exhausted roster has no
    decision-bearing analysis under D-009 and is never analyzed as attrition.
    """

    if valid_slots < 1 or attempts_per_slot < 1:
        raise ValueError("valid_slots and attempts_per_slot must be positive")
    if not 0.0 <= invalid_attempt_probability <= 1.0:
        raise ValueError("invalid_attempt_probability must lie in [0, 1]")
    per_slot = 1.0 - invalid_attempt_probability**attempts_per_slot
    return per_slot**valid_slots


def _scenario(name: str) -> ConfirmScenario:
    try:
        return next(item for item in default_confirm_scenarios() if item.name == name)
    except StopIteration as exc:
        raise ValueError(f"unknown confirmatory scenario {name!r}") from exc


def run_recovery_grid(
    *,
    replicates: int,
    seed: int,
    scenario_names: Iterable[str] = (
        "diffuse_null",
        "diffuse_threshold",
        "diffuse_strong",
        "opposing_domain_mechanisms",
    ),
) -> list[dict[str, float | int | str | bool]]:
    rows: list[dict[str, float | int | str | bool]] = []
    mechanisms = default_recovery_mechanisms()
    for scenario_index, name in enumerate(scenario_names):
        scenario = _scenario(name)
        for mechanism_index, mechanism in enumerate(mechanisms):
            rows.append(
                simulate_h1_recovery(
                    scenario,
                    mechanism,
                    replicates=replicates,
                    seed=seed + 10_000 * scenario_index + mechanism_index,
                )
            )
    return rows


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run the prospective D-005 H1 recovery envelope."
    )
    parser.add_argument("--replicates", type=int, default=5_000)
    parser.add_argument("--seed", type=int, default=20260815)
    args = parser.parse_args(argv)
    for row in run_recovery_grid(replicates=args.replicates, seed=args.seed):
        print(json.dumps(row, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
