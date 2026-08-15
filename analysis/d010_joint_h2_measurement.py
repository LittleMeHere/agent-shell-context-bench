"""Matched-N joint H2 measurement simulation for D-010.

This prospective module generates programmatic failures, latent A-F rubric
codes, two AI labels, an exact registered human-anchor sample, kappa demotion,
candidate primary labels, and the pooled H2 reference in one Monte Carlo data
set. It is evidence for choosing D-010 and refining D-002/D-005; it does not
approve a primary label or substitute the pooled reference for the registered
mixed model.
"""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass
from statistics import NormalDist
from typing import Iterable

import numpy as np
from numpy.typing import NDArray

from analysis.d005_finite_roster_irr import (
    DE_CATEGORIES,
    KAPPA_THRESHOLD,
    N_RUBRIC_CATEGORIES,
    rowwise_cohen_kappa,
)
from analysis.d013_ceiling_operating_characteristics import (
    CONFIDENCE,
    FAMILIES_PER_DOMAIN,
    N_DOMAINS,
    N_SEEDED_VARIANTS,
    H2Scenario,
    h2_probabilities,
)
from analysis.d013_task_bank_design import (
    REGISTERED_CONFIG_IDS,
    REGISTERED_ENVIRONMENT_IDS,
    build_instance_schedule,
)


N_CAPABILITY_FAMILIES = N_DOMAINS * FAMILIES_PER_DOMAIN
N_SEEDED_TASKS = N_SEEDED_VARIANTS // 2
N_TASK_CLASSES = 2
N_ANCHOR_STRATA = len(REGISTERED_ENVIRONMENT_IDS) * N_TASK_CLASSES
DEFAULT_ANCHOR_SIZE = 50
DEFAULT_ANCHOR_FLOOR = 4
PRIMARY_RULES = (
    "coder1",
    "consensus_then_adjudicator",
    "both_ai_de",
    "either_ai_de",
)


@dataclass(frozen=True)
class JointScenario:
    """One joint failure, latent-rubric, and rater-error scenario."""

    name: str
    h2: H2Scenario
    coder1_accuracy: float
    coder2_accuracy: float
    human_accuracy: float
    adjudicator_accuracy: float
    shared_bias_probability: float = 0.0
    shared_bias_map: tuple[int, ...] = (0, 1, 2, 2, 2, 5)
    success_label_probabilities: tuple[float, ...] = (
        0.82,
        0.12,
        0.04,
        0.015,
        0.005,
    )
    non_de_c_probability: float = 0.75
    de_d_probability: float = 0.60

    def __post_init__(self) -> None:
        rates = (
            self.coder1_accuracy,
            self.coder2_accuracy,
            self.human_accuracy,
            self.adjudicator_accuracy,
            self.shared_bias_probability,
            self.non_de_c_probability,
            self.de_d_probability,
        )
        if any(not 0.0 <= value <= 1.0 for value in rates):
            raise ValueError("scenario probabilities must lie in [0, 1]")
        if len(self.success_label_probabilities) != 5 or not math.isclose(
            sum(self.success_label_probabilities),
            1.0,
            abs_tol=1e-12,
        ):
            raise ValueError("success label probabilities A-E must sum to one")
        if any(value < 0.0 for value in self.success_label_probabilities):
            raise ValueError("success label probabilities cannot be negative")
        if len(self.shared_bias_map) != N_RUBRIC_CATEGORIES:
            raise ValueError("shared_bias_map must contain six labels")
        if any(
            isinstance(value, (bool, np.bool_))
            or not isinstance(value, (int, np.integer))
            for value in self.shared_bias_map
        ):
            raise ValueError("shared bias labels must be integers")
        if any(
            value < 0 or value >= N_RUBRIC_CATEGORIES
            for value in self.shared_bias_map
        ):
            raise ValueError("shared bias labels must be valid category indices")
        if (
            any(self.shared_bias_map[label] == 5 for label in (0, 1))
            or any(
                self.shared_bias_map[label] not in (2, 3, 4)
                for label in (2, 3, 4)
            )
            or self.shared_bias_map[5] < 2
        ):
            raise ValueError(
                "shared_bias_map must preserve outcome-compatible label sets"
            )


@dataclass(frozen=True)
class JointManifest:
    """Trial-level synthetic manifest for one broad split-N matrix."""

    base_common_n: int
    n_cap: int
    n_seed: int
    environment: NDArray[np.int64]
    task_class: NDArray[np.int64]
    task: NDArray[np.int64]
    task_variant: NDArray[np.int64]
    family: NDArray[np.int64]
    instance: NDArray[np.int64]
    phrasing: NDArray[np.int64]
    valid_slot: NDArray[np.int64]
    configuration: NDArray[np.int64]
    stratum: NDArray[np.int64]
    failure_probability: NDArray[np.float64]
    de_probability_given_failure: NDArray[np.float64]

    @property
    def size(self) -> int:
        return int(self.environment.size)


@dataclass(frozen=True)
class JointMeasurementBatch:
    """One reusable batch of latent outcomes and full-sample rater labels."""

    failure: NDArray[np.bool_]
    latent_de: NDArray[np.bool_]
    truth: NDArray[np.int64]
    coder1: NDArray[np.int64]
    coder2: NDArray[np.int64]
    adjudicator: NDArray[np.int64]


def _validate_label_arrays(*arrays: NDArray[np.int64]) -> None:
    if not arrays:
        raise ValueError("at least one label array is required")
    shape = arrays[0].shape
    if any(np.asarray(array).shape != shape for array in arrays):
        raise ValueError("label arrays must have identical shapes")
    if any(
        np.any((np.asarray(array) < 0) | (np.asarray(array) >= N_RUBRIC_CATEGORIES))
        for array in arrays
    ):
        raise ValueError("labels must be valid category indices")


def primary_de_labels(
    coder1: NDArray[np.int64],
    coder2: NDArray[np.int64],
    adjudicator: NDArray[np.int64],
) -> dict[str, NDArray[np.bool_]]:
    """Resolve four prospective H2 label rules without selecting one."""

    _validate_label_arrays(coder1, coder2, adjudicator)
    coder1_de = np.isin(coder1, DE_CATEGORIES)
    coder2_de = np.isin(coder2, DE_CATEGORIES)
    adjudicated_label = np.where(coder1 == coder2, coder1, adjudicator)
    return {
        "coder1": coder1_de,
        "consensus_then_adjudicator": np.isin(
            adjudicated_label,
            DE_CATEGORIES,
        ),
        "both_ai_de": coder1_de & coder2_de,
        "either_ai_de": coder1_de | coder2_de,
    }


def pooled_h2_log_wald_reference(
    failure: NDArray[np.bool_],
    predicted_de: NDArray[np.bool_],
    windows_mask: NDArray[np.bool_],
    linux_mask: NDArray[np.bool_],
    *,
    minimum_failures: int = 10,
    confidence: float = CONFIDENCE,
) -> tuple[
    NDArray[np.bool_],
    NDArray[np.float64],
    NDArray[np.float64],
]:
    """Return estimability, RR, and log-Wald lower bound for pooled H2.

    This is the optimistic simulation reference, not the registered final
    mixed model. D/E counts are restricted to failed trials even when a
    candidate label marks a successful trial D/E.
    """

    failure = np.asarray(failure, dtype=bool)
    predicted_de = np.asarray(predicted_de, dtype=bool)
    windows_mask = np.asarray(windows_mask, dtype=bool)
    linux_mask = np.asarray(linux_mask, dtype=bool)
    if failure.ndim != 2 or predicted_de.shape != failure.shape:
        raise ValueError("failure and predicted_de must be equal two-dimensional arrays")
    if (
        windows_mask.ndim != 1
        or linux_mask.ndim != 1
        or windows_mask.shape != linux_mask.shape
        or windows_mask.size != failure.shape[1]
        or not np.any(windows_mask)
        or not np.any(linux_mask)
        or np.any(windows_mask & linux_mask)
    ):
        raise ValueError("context masks must be non-empty, disjoint trial masks")
    if minimum_failures < 1:
        raise ValueError("minimum_failures must be positive")
    if not 0.0 < confidence < 1.0:
        raise ValueError("confidence must lie strictly between zero and one")

    failure_windows = np.sum(failure[:, windows_mask], axis=1)
    failure_linux = np.sum(failure[:, linux_mask], axis=1)
    de_windows = np.sum(
        predicted_de[:, windows_mask] & failure[:, windows_mask],
        axis=1,
    )
    de_linux = np.sum(
        predicted_de[:, linux_mask] & failure[:, linux_mask],
        axis=1,
    )
    estimable = (
        (failure_windows >= minimum_failures)
        & (failure_linux >= minimum_failures)
        & (de_windows > 0)
        & (de_linux > 0)
    )
    observed_rr = np.full(failure.shape[0], np.nan)
    lower = np.full(failure.shape[0], np.nan)
    with np.errstate(divide="ignore", invalid="ignore", over="ignore"):
        q_windows = de_windows[estimable] / failure_windows[estimable]
        q_linux = de_linux[estimable] / failure_linux[estimable]
        observed_rr[estimable] = q_windows / q_linux
        variance = (
            1.0 / de_windows[estimable]
            - 1.0 / failure_windows[estimable]
            + 1.0 / de_linux[estimable]
            - 1.0 / failure_linux[estimable]
        )
        z_value = NormalDist().inv_cdf(0.5 + confidence / 2.0)
        lower[estimable] = np.exp(
            np.log(observed_rr[estimable]) - z_value * np.sqrt(variance)
        )
    return estimable, observed_rr, lower


def manifest_true_h2_rates(
    manifest: JointManifest,
    windows_mask: NDArray[np.bool_],
    linux_mask: NDArray[np.bool_],
) -> tuple[float, float, float]:
    """Return expected Linux rate, Windows rate, and their H2 ratio."""

    windows_mask = np.asarray(windows_mask, dtype=bool)
    linux_mask = np.asarray(linux_mask, dtype=bool)
    if (
        windows_mask.ndim != 1
        or linux_mask.ndim != 1
        or windows_mask.shape != linux_mask.shape
        or windows_mask.size != manifest.size
        or not np.any(windows_mask)
        or not np.any(linux_mask)
        or np.any(windows_mask & linux_mask)
    ):
        raise ValueError("context masks must be non-empty, disjoint manifest masks")
    true_q_windows = float(
        np.sum(
            manifest.failure_probability[windows_mask]
            * manifest.de_probability_given_failure[windows_mask]
        )
        / np.sum(manifest.failure_probability[windows_mask])
    )
    true_q_linux = float(
        np.sum(
            manifest.failure_probability[linux_mask]
            * manifest.de_probability_given_failure[linux_mask]
        )
        / np.sum(manifest.failure_probability[linux_mask])
    )
    return true_q_linux, true_q_windows, true_q_windows / true_q_linux


def draw_outcome_constrained_labels(
    rng: np.random.Generator,
    truth: NDArray[np.int64],
    failure: NDArray[np.bool_],
    accuracy: float,
) -> NDArray[np.int64]:
    """Draw rater labels while respecting the coder-visible binary outcome.

    The frozen coder input includes programmatic success/failure. Successful
    transcripts may legitimately be A-E because scope creep, spirals, or
    damage can coexist with predicate success; only F is excluded. Failed
    transcripts may be C-F and cannot be A/B under the V1 policy.
    """

    truth = np.asarray(truth)
    failure = np.asarray(failure, dtype=bool)
    if truth.shape != failure.shape:
        raise ValueError("truth and failure arrays must have identical shapes")
    _validate_label_arrays(truth)
    if not 0.0 <= accuracy <= 1.0:
        raise ValueError("accuracy must lie in [0, 1]")
    if np.any(failure & (truth < 2)) or np.any(~failure & (truth == 5)):
        raise ValueError("truth labels contradict the binary outcome")

    labels = truth.copy()
    wrong = rng.random(truth.shape) >= accuracy
    successful_wrong = wrong & ~failure
    if np.any(successful_wrong):
        current = truth[successful_wrong]
        alternatives = rng.integers(0, 4, size=int(np.sum(successful_wrong)))
        replacement = alternatives + (alternatives >= current)
        labels[successful_wrong] = replacement

    failed_wrong = wrong & failure
    if np.any(failed_wrong):
        current = truth[failed_wrong] - 2
        alternatives = rng.integers(0, 3, size=int(np.sum(failed_wrong)))
        replacement = alternatives + (alternatives >= current)
        labels[failed_wrong] = replacement + 2
    return labels


def build_joint_manifest(
    scenario: H2Scenario,
    *,
    base_common_n: int,
) -> JointManifest:
    """Build the exact broad split-N trial roster for all five environments."""

    if base_common_n < 6:
        raise ValueError("base_common_n must be at least six")
    n_cap = math.ceil(5 * base_common_n / 12)
    n_seed = base_common_n
    n, p_linux, p_windows, q_linux, q_windows = h2_probabilities(
        scenario,
        capability_count=N_CAPABILITY_FAMILIES,
        n_cap=n_cap,
        n_seed=n_seed,
    )
    task_variant_grid, config_grid = np.indices(n.shape)
    task_variant_flat = task_variant_grid.ravel()
    config_flat = config_grid.ravel()
    task_class_flat = (
        task_variant_flat >= N_CAPABILITY_FAMILIES
    ).astype(np.int64)
    repetitions = n.ravel()

    instance_ids = ("I01", "I02", "I03")
    reference_environment = REGISTERED_ENVIRONMENT_IDS[0]
    capability_instances = np.empty(
        (N_CAPABILITY_FAMILIES, len(REGISTERED_CONFIG_IDS), n_cap),
        dtype=np.int64,
    )
    for family_id in range(N_CAPABILITY_FAMILIES):
        assignments = build_instance_schedule(
            family_id=f"F{family_id + 1:02d}",
            instance_ids=instance_ids,
            config_ids=REGISTERED_CONFIG_IDS,
            environment_ids=REGISTERED_ENVIRONMENT_IDS,
            repetitions_per_cell=n_cap,
        )
        for assignment in assignments:
            if assignment.environment_id != reference_environment:
                continue
            configuration = REGISTERED_CONFIG_IDS.index(assignment.config_id)
            capability_instances[
                family_id,
                configuration,
                assignment.valid_slot_index,
            ] = instance_ids.index(assignment.instance_id)

    base_task_parts: list[NDArray[np.int64]] = []
    base_variant_parts: list[NDArray[np.int64]] = []
    base_family_parts: list[NDArray[np.int64]] = []
    base_instance_parts: list[NDArray[np.int64]] = []
    base_phrasing_parts: list[NDArray[np.int64]] = []
    base_slot_parts: list[NDArray[np.int64]] = []
    for task_variant, configuration, repetitions_in_cell in zip(
        task_variant_flat,
        config_flat,
        repetitions,
        strict=True,
    ):
        count = int(repetitions_in_cell)
        base_variant_parts.append(
            np.full(count, task_variant, dtype=np.int64)
        )
        base_slot_parts.append(np.arange(count, dtype=np.int64))
        if task_variant < N_CAPABILITY_FAMILIES:
            base_task_parts.append(
                np.full(count, task_variant, dtype=np.int64)
            )
            base_family_parts.append(
                np.full(count, task_variant, dtype=np.int64)
            )
            base_instance_parts.append(
                capability_instances[task_variant, configuration].copy()
            )
            base_phrasing_parts.append(
                np.full(count, -1, dtype=np.int64)
            )
        else:
            seeded_variant = task_variant - N_CAPABILITY_FAMILIES
            base_task_parts.append(
                np.full(
                    count,
                    N_CAPABILITY_FAMILIES + seeded_variant // 2,
                    dtype=np.int64,
                )
            )
            base_family_parts.append(np.full(count, -1, dtype=np.int64))
            base_instance_parts.append(np.full(count, -1, dtype=np.int64))
            # Each of the nine seeded tasks contributes adjacent formal (0)
            # and colloquial (1) probability rows, matching the V1 roster.
            base_phrasing_parts.append(
                np.full(count, seeded_variant % 2, dtype=np.int64)
            )

    base_task = np.concatenate(base_task_parts)
    base_variant = np.concatenate(base_variant_parts)
    base_family = np.concatenate(base_family_parts)
    base_instance = np.concatenate(base_instance_parts)
    base_phrasing = np.concatenate(base_phrasing_parts)
    base_slot = np.concatenate(base_slot_parts)
    base_class = np.repeat(task_class_flat, repetitions)
    base_configuration = np.repeat(config_flat, repetitions)

    environment_parts: list[NDArray[np.int64]] = []
    class_parts: list[NDArray[np.int64]] = []
    task_parts: list[NDArray[np.int64]] = []
    variant_parts: list[NDArray[np.int64]] = []
    family_parts: list[NDArray[np.int64]] = []
    instance_parts: list[NDArray[np.int64]] = []
    phrasing_parts: list[NDArray[np.int64]] = []
    slot_parts: list[NDArray[np.int64]] = []
    config_parts: list[NDArray[np.int64]] = []
    stratum_parts: list[NDArray[np.int64]] = []
    failure_parts: list[NDArray[np.float64]] = []
    de_parts: list[NDArray[np.float64]] = []
    windows_id = REGISTERED_ENVIRONMENT_IDS.index("windows_powershell")
    linux_id = REGISTERED_ENVIRONMENT_IDS.index("linux_native")

    for environment_id in range(len(REGISTERED_ENVIRONMENT_IDS)):
        if environment_id == windows_id:
            windows_weight = 1.0
        elif environment_id == linux_id:
            windows_weight = 0.0
        else:
            # The non-focal environments affect only full-sample IRR here.
            # A neutral midpoint avoids making an unvalidated platform claim.
            windows_weight = 0.5
        p = (1.0 - windows_weight) * p_linux + windows_weight * p_windows
        q = (1.0 - windows_weight) * q_linux + windows_weight * q_windows
        environment_parts.append(
            np.full(int(np.sum(repetitions)), environment_id, dtype=np.int64)
        )
        class_parts.append(base_class.copy())
        task_parts.append(base_task.copy())
        variant_parts.append(base_variant.copy())
        family_parts.append(base_family.copy())
        instance_parts.append(base_instance.copy())
        phrasing_parts.append(base_phrasing.copy())
        slot_parts.append(base_slot.copy())
        config_parts.append(base_configuration.copy())
        stratum_parts.append(environment_id * N_TASK_CLASSES + base_class)
        failure_parts.append(np.repeat(p.ravel(), repetitions))
        de_parts.append(np.repeat(q.ravel(), repetitions))

    manifest = JointManifest(
        base_common_n=base_common_n,
        n_cap=n_cap,
        n_seed=n_seed,
        environment=np.concatenate(environment_parts),
        task_class=np.concatenate(class_parts),
        task=np.concatenate(task_parts),
        task_variant=np.concatenate(variant_parts),
        family=np.concatenate(family_parts),
        instance=np.concatenate(instance_parts),
        phrasing=np.concatenate(phrasing_parts),
        valid_slot=np.concatenate(slot_parts),
        configuration=np.concatenate(config_parts),
        stratum=np.concatenate(stratum_parts),
        failure_probability=np.concatenate(failure_parts),
        de_probability_given_failure=np.concatenate(de_parts),
    )
    expected = len(REGISTERED_CONFIG_IDS) * len(REGISTERED_ENVIRONMENT_IDS) * (
        N_CAPABILITY_FAMILIES * n_cap + N_SEEDED_VARIANTS * n_seed
    )
    if manifest.size != expected:
        raise RuntimeError("joint manifest does not match the broad split cost")
    if set(np.unique(manifest.stratum)) != set(range(N_ANCHOR_STRATA)):
        raise RuntimeError("joint manifest does not populate all anchor strata")
    seeded = manifest.task_class == 1
    if np.unique(manifest.task[seeded]).size != N_SEEDED_TASKS:
        raise RuntimeError("joint manifest does not preserve nine seeded tasks")
    return manifest


def sample_registered_anchor_indices(
    rng: np.random.Generator,
    strata: NDArray[np.int64],
    *,
    sample_size: int = DEFAULT_ANCHOR_SIZE,
    per_stratum_floor: int = DEFAULT_ANCHOR_FLOOR,
) -> NDArray[np.int64]:
    """Sample the full-matrix SAP anchor: four/stratum plus proportional rest."""

    strata = np.asarray(strata)
    if strata.ndim != 1 or strata.size == 0:
        raise ValueError("strata must be a non-empty one-dimensional array")
    unique = np.unique(strata)
    if unique.size != N_ANCHOR_STRATA or set(unique) != set(range(N_ANCHOR_STRATA)):
        raise ValueError("the full anchor requires the exact ten strata")
    if per_stratum_floor < 1:
        raise ValueError("per_stratum_floor must be positive")
    minimum = per_stratum_floor * N_ANCHOR_STRATA
    if sample_size < minimum or sample_size > strata.size:
        raise ValueError("sample_size is incompatible with the stratum floor")

    mandatory: list[NDArray[np.int64]] = []
    for stratum in range(N_ANCHOR_STRATA):
        members = np.flatnonzero(strata == stratum)
        if members.size < 10 or members.size < per_stratum_floor:
            raise ValueError("thin-stratum merging is required before sampling")
        mandatory.append(
            rng.choice(members, size=per_stratum_floor, replace=False)
        )
    selected = np.concatenate(mandatory)
    remainder_size = sample_size - minimum
    if remainder_size:
        available = np.ones(strata.size, dtype=bool)
        available[selected] = False
        remaining_indices = np.flatnonzero(available)
        remainder = rng.choice(
            remaining_indices,
            size=remainder_size,
            replace=False,
        )
        selected = np.concatenate((selected, remainder))
    rng.shuffle(selected)
    return selected


def _draw_truth(
    rng: np.random.Generator,
    scenario: JointScenario,
    manifest: JointManifest,
    batch: int,
) -> tuple[NDArray[np.bool_], NDArray[np.bool_], NDArray[np.int64]]:
    failure = rng.random((batch, manifest.size)) < manifest.failure_probability
    latent_de = failure & (
        rng.random((batch, manifest.size))
        < manifest.de_probability_given_failure
    )
    category_draw = rng.random((batch, manifest.size))
    truth = np.empty((batch, manifest.size), dtype=np.int8)
    successful = ~failure
    truth[successful] = np.searchsorted(
        np.cumsum(scenario.success_label_probabilities),
        category_draw[successful],
        side="right",
    )
    non_de_failure = failure & ~latent_de
    truth[non_de_failure] = np.where(
        category_draw[non_de_failure] < scenario.non_de_c_probability,
        2,
        5,
    )
    truth[latent_de] = np.where(
        category_draw[latent_de] < scenario.de_d_probability,
        3,
        4,
    )
    return failure, latent_de, truth


def draw_joint_measurement_batch(
    rng: np.random.Generator,
    scenario: JointScenario,
    manifest: JointManifest,
    batch: int,
) -> JointMeasurementBatch:
    """Draw one joint batch for reuse by measurement-design simulations."""

    if batch < 1:
        raise ValueError("batch must be positive")
    failure, latent_de, truth = _draw_truth(rng, scenario, manifest, batch)
    coder1 = draw_outcome_constrained_labels(
        rng,
        truth,
        failure,
        scenario.coder1_accuracy,
    )
    coder2 = draw_outcome_constrained_labels(
        rng,
        truth,
        failure,
        scenario.coder2_accuracy,
    )
    shared_map = np.asarray(scenario.shared_bias_map, dtype=np.int64)
    affected = shared_map[truth] != truth
    shared = affected & (
        rng.random(truth.shape) < scenario.shared_bias_probability
    )
    coder1[shared] = shared_map[truth[shared]]
    coder2[shared] = shared_map[truth[shared]]
    adjudicator = draw_outcome_constrained_labels(
        rng,
        truth,
        failure,
        scenario.adjudicator_accuracy,
    )
    return JointMeasurementBatch(
        failure=failure,
        latent_de=latent_de,
        truth=truth,
        coder1=coder1,
        coder2=coder2,
        adjudicator=adjudicator,
    )


def _finite_mean(values: NDArray[np.float64]) -> float | None:
    finite = values[np.isfinite(values)]
    return float(np.mean(finite)) if finite.size else None


def _rule_status(rule: str) -> str:
    if rule == "consensus_then_adjudicator":
        return "candidate_full_AF_label_requires_adjudication"
    if rule == "coder1":
        return "candidate_full_AF_label_R017_unresolved"
    return "H2_binary_sensitivity_only_not_full_AF_primary"


def simulate_joint_scenario(
    scenario: JointScenario,
    *,
    base_common_n: int,
    replicates: int,
    seed: int,
    batch_size: int = 64,
) -> list[dict[str, float | int | str | None]]:
    """Run one matched-N joint measurement and pooled-reference simulation."""

    if replicates < 1 or batch_size < 1:
        raise ValueError("replicates and batch_size must be positive")
    manifest = build_joint_manifest(scenario.h2, base_common_n=base_common_n)
    rng = np.random.default_rng(seed)
    windows_id = REGISTERED_ENVIRONMENT_IDS.index("windows_powershell")
    linux_id = REGISTERED_ENVIRONMENT_IDS.index("linux_native")
    windows_mask = manifest.environment == windows_id
    linux_mask = manifest.environment == linux_id
    focal_mask = windows_mask | linux_mask
    common_parts: dict[str, list[NDArray[np.float64]]] = {
        key: []
        for key in (
            "kappa_ai",
            "kappa_human_min",
            "anchor_true_de",
            "anchor_failed_true_de",
            "anchor_success_true_de",
            "anchor_failed",
            "ai_disagreement",
            "all_configs_ge5",
        )
    }
    anchor_stratum_totals = np.zeros(N_ANCHOR_STRATA, dtype=float)
    rule_parts: dict[str, dict[str, list[NDArray[np.float64]]]] = {
        rule: {
            key: []
            for key in (
                "estimable",
                "observed_rr",
                "lower",
                "sensitivity",
                "false_positive_rate",
            )
        }
        for rule in PRIMARY_RULES
    }

    remaining = replicates
    while remaining:
        batch = min(batch_size, remaining)
        generated = draw_joint_measurement_batch(rng, scenario, manifest, batch)
        failure = generated.failure
        latent_de = generated.latent_de
        truth = generated.truth
        coder1 = generated.coder1
        coder2 = generated.coder2
        adjudicator = generated.adjudicator
        common_parts["kappa_ai"].append(
            rowwise_cohen_kappa(coder1, coder2, N_RUBRIC_CATEGORIES)
        )
        common_parts["ai_disagreement"].append(
            np.mean(coder1 != coder2, axis=1)
        )

        anchor_matrix = np.empty((batch, DEFAULT_ANCHOR_SIZE), dtype=np.int64)
        for replicate in range(batch):
            anchor_matrix[replicate] = sample_registered_anchor_indices(
                rng,
                manifest.stratum,
            )
            anchor_stratum_totals += np.bincount(
                manifest.stratum[anchor_matrix[replicate]],
                minlength=N_ANCHOR_STRATA,
            )
        anchor_truth = np.take_along_axis(truth, anchor_matrix, axis=1)
        anchor_failure = np.take_along_axis(failure, anchor_matrix, axis=1)
        anchor_coder1 = np.take_along_axis(coder1, anchor_matrix, axis=1)
        anchor_coder2 = np.take_along_axis(coder2, anchor_matrix, axis=1)
        anchor_human = draw_outcome_constrained_labels(
            rng,
            anchor_truth,
            anchor_failure,
            scenario.human_accuracy,
        )
        kappa_human_1 = rowwise_cohen_kappa(
            anchor_human,
            anchor_coder1,
            N_RUBRIC_CATEGORIES,
        )
        kappa_human_2 = rowwise_cohen_kappa(
            anchor_human,
            anchor_coder2,
            N_RUBRIC_CATEGORIES,
        )
        common_parts["kappa_human_min"].append(
            np.minimum(kappa_human_1, kappa_human_2)
        )
        common_parts["anchor_true_de"].append(
            np.sum(np.isin(anchor_truth, DE_CATEGORIES), axis=1)
        )
        anchor_de = np.isin(anchor_truth, DE_CATEGORIES)
        common_parts["anchor_failed_true_de"].append(
            np.sum(anchor_de & anchor_failure, axis=1)
        )
        common_parts["anchor_success_true_de"].append(
            np.sum(anchor_de & ~anchor_failure, axis=1)
        )
        common_parts["anchor_failed"].append(
            np.sum(anchor_failure, axis=1)
        )

        config_ok = np.ones((batch, len(REGISTERED_CONFIG_IDS)), dtype=bool)
        for configuration in range(len(REGISTERED_CONFIG_IDS)):
            config_ok[:, configuration] = (
                np.sum(
                    failure[:, windows_mask & (manifest.configuration == configuration)],
                    axis=1,
                )
                >= 5
            ) & (
                np.sum(
                    failure[:, linux_mask & (manifest.configuration == configuration)],
                    axis=1,
                )
                >= 5
            )
        common_parts["all_configs_ge5"].append(np.all(config_ok, axis=1))

        labels = primary_de_labels(coder1, coder2, adjudicator)
        true_de_focal = latent_de[:, focal_mask]
        true_non_de_failure_focal = failure[:, focal_mask] & ~true_de_focal
        for rule, predicted_de in labels.items():
            estimable, observed_rr, lower = pooled_h2_log_wald_reference(
                failure,
                predicted_de,
                windows_mask,
                linux_mask,
            )
            predicted_focal = predicted_de[:, focal_mask]
            true_de_count = np.sum(true_de_focal, axis=1)
            true_non_de_count = np.sum(true_non_de_failure_focal, axis=1)
            sensitivity = np.divide(
                np.sum(predicted_focal & true_de_focal, axis=1),
                true_de_count,
                out=np.full(batch, np.nan),
                where=true_de_count > 0,
            )
            false_positive_rate = np.divide(
                np.sum(predicted_focal & true_non_de_failure_focal, axis=1),
                true_non_de_count,
                out=np.full(batch, np.nan),
                where=true_non_de_count > 0,
            )
            rule_parts[rule]["estimable"].append(estimable)
            rule_parts[rule]["observed_rr"].append(observed_rr)
            rule_parts[rule]["lower"].append(lower)
            rule_parts[rule]["sensitivity"].append(sensitivity)
            rule_parts[rule]["false_positive_rate"].append(false_positive_rate)
        remaining -= batch

    common = {
        key: np.concatenate(parts) for key, parts in common_parts.items()
    }
    irr_pass = (
        np.isfinite(common["kappa_ai"])
        & np.isfinite(common["kappa_human_min"])
        & (common["kappa_ai"] >= KAPPA_THRESHOLD)
        & (common["kappa_human_min"] >= KAPPA_THRESHOLD)
    )
    case_b = (
        np.isfinite(common["kappa_ai"])
        & (common["kappa_ai"] >= KAPPA_THRESHOLD)
        & ~(
            np.isfinite(common["kappa_human_min"])
            & (common["kappa_human_min"] >= KAPPA_THRESHOLD)
        )
    )
    case_c = ~(
        np.isfinite(common["kappa_ai"])
        & (common["kappa_ai"] >= KAPPA_THRESHOLD)
    )
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
    anchor_means = anchor_stratum_totals / replicates

    rows: list[dict[str, float | int | str | None]] = []
    for rule in PRIMARY_RULES:
        values = {
            key: np.concatenate(parts) for key, parts in rule_parts[rule].items()
        }
        reference_support = values["estimable"].astype(bool) & (
            values["lower"] > 2.0
        )
        joint_support = irr_pass & reference_support
        row: dict[str, float | int | str | None] = {
            "record_type": "d010_joint_h2_measurement",
            "scenario": scenario.name,
            "primary_rule": rule,
            "primary_rule_status": _rule_status(rule),
            "replicates": replicates,
            "seed": seed,
            "base_common_n": base_common_n,
            "n_cap": manifest.n_cap,
            "n_seed": manifest.n_seed,
            "full_sample_size": manifest.size,
            "human_anchor_size": DEFAULT_ANCHOR_SIZE,
            "human_anchor_floor_per_stratum": DEFAULT_ANCHOR_FLOOR,
            "mean_anchor_counts_by_stratum": ",".join(
                f"{value:.4f}" for value in anchor_means
            ),
            "mean_anchor_failed_trials": float(
                np.mean(common["anchor_failed"])
            ),
            "mean_anchor_true_de_trials": float(
                np.mean(common["anchor_true_de"])
            ),
            "anchor_zero_true_de_probability": float(
                np.mean(common["anchor_true_de"] == 0)
            ),
            "mean_anchor_failed_true_de_trials": float(
                np.mean(common["anchor_failed_true_de"])
            ),
            "anchor_zero_failed_true_de_probability": float(
                np.mean(common["anchor_failed_true_de"] == 0)
            ),
            "mean_anchor_success_true_de_trials": float(
                np.mean(common["anchor_success_true_de"])
            ),
            "mean_kappa_ai": _finite_mean(common["kappa_ai"]),
            "mean_kappa_human_min": _finite_mean(common["kappa_human_min"]),
            "irr_confirmatory_probability": float(np.mean(irr_pass)),
            "irr_case_b_probability": float(np.mean(case_b)),
            "irr_case_c_probability": float(np.mean(case_c)),
            "mean_ai_exact_disagreement_rate": float(
                np.mean(common["ai_disagreement"])
            ),
            "expected_adjudications_if_consensus_rule": float(
                manifest.size * np.mean(common["ai_disagreement"])
            ),
            "all_configs_ge5_each_context_probability": float(
                np.mean(common["all_configs_ge5"])
            ),
            "true_conditional_de_linux": true_q_linux,
            "true_conditional_de_windows": true_q_windows,
            "true_conditional_de_rr": true_rr,
            "ratio_estimable_probability": float(
                np.mean(values["estimable"])
            ),
            "mean_observed_rr_estimable": _finite_mean(values["observed_rr"]),
            "observed_rr_bias_vs_latent_estimable": (
                None
                if _finite_mean(values["observed_rr"]) is None
                else float(_finite_mean(values["observed_rr"]) - true_rr)
            ),
            "mean_de_sensitivity": _finite_mean(values["sensitivity"]),
            "mean_de_false_positive_rate": _finite_mean(
                values["false_positive_rate"]
            ),
            "pooled_reference_support_probability": float(
                np.mean(reference_support)
            ),
            "joint_confirmatory_support_probability": float(
                np.mean(joint_support)
            ),
            "joint_false_support_probability": (
                float(np.mean(joint_support)) if true_rr_is_null else 0.0
            ),
            "joint_no_support_probability": float(np.mean(~joint_support)),
            "analysis_note": (
                "matched_N_joint_labels_exact_anchor_pooled_log_wald_not_D005_GLMM"
            ),
        }
        rows.append(row)
    return rows


def default_joint_scenarios() -> tuple[JointScenario, ...]:
    moderate = dict(
        capability_failure_linux=0.05,
        capability_failure_windows=0.08,
        seeded_failure_linux=0.10,
        seeded_failure_windows=0.15,
    )
    return (
        JointScenario(
            "high_quality_null",
            H2Scenario(
                "high_quality_null",
                **moderate,
                de_probability_linux=0.15,
                de_probability_windows=0.15,
            ),
            0.94,
            0.93,
            0.98,
            0.98,
        ),
        JointScenario(
            "high_quality_boundary",
            H2Scenario(
                "high_quality_boundary",
                **moderate,
                de_probability_linux=0.10,
                de_probability_windows=0.20,
            ),
            0.94,
            0.93,
            0.98,
            0.98,
        ),
        JointScenario(
            "high_quality_strong",
            H2Scenario(
                "high_quality_strong",
                **moderate,
                de_probability_linux=0.10,
                de_probability_windows=0.30,
            ),
            0.94,
            0.93,
            0.98,
            0.98,
        ),
        JointScenario(
            "near_ai_threshold_strong",
            H2Scenario(
                "near_ai_threshold_strong",
                **moderate,
                de_probability_linux=0.10,
                de_probability_windows=0.30,
            ),
            0.8815,
            0.8815,
            0.98,
            0.98,
        ),
        JointScenario(
            "shared_de_to_c_strong",
            H2Scenario(
                "shared_de_to_c_strong",
                **moderate,
                de_probability_linux=0.10,
                de_probability_windows=0.30,
            ),
            0.97,
            0.97,
            0.98,
            0.98,
            shared_bias_probability=0.85,
        ),
        JointScenario(
            "shared_de_to_c_no_success_de_strong",
            H2Scenario(
                "shared_de_to_c_no_success_de_strong",
                **moderate,
                de_probability_linux=0.10,
                de_probability_windows=0.30,
            ),
            0.97,
            0.97,
            0.98,
            0.98,
            shared_bias_probability=0.85,
            success_label_probabilities=(0.83, 0.13, 0.04, 0.0, 0.0),
        ),
    )


def run_joint_grid(
    *,
    replicates: int,
    seed: int,
    base_common_ns: Iterable[int] = (6, 12, 24),
) -> list[dict[str, float | int | str | None]]:
    rows: list[dict[str, float | int | str | None]] = []
    for scenario_index, scenario in enumerate(default_joint_scenarios()):
        for n_index, base_n in enumerate(base_common_ns):
            rows.extend(
                simulate_joint_scenario(
                    scenario,
                    base_common_n=base_n,
                    replicates=replicates,
                    seed=seed + 10_000 * scenario_index + 100 * n_index,
                )
            )
    return rows


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run matched-N joint H2 measurement simulations."
    )
    parser.add_argument("--replicates", type=int, default=2_000)
    parser.add_argument("--seed", type=int, default=20260801)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.replicates < 1:
        raise SystemExit("--replicates must be positive")
    for row in run_joint_grid(replicates=args.replicates, seed=args.seed):
        print(json.dumps(row, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
