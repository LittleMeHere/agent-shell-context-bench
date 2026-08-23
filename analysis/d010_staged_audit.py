"""Machine-check the accepted D-010 staged human-audit envelope.

This module freezes structural constraints without choosing the still-open
numeric expansion thresholds. It makes it impossible for later automation to
silently add a third stage, rewrite primary labels, or condition expansion on
named hypothesis results.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping, Sequence


SCHEMA_VERSION = "1.2.0"
FOCAL_CONTEXTS = ("windows_powershell", "linux_native")
EXPECTED_GATE_OUTCOMES = {
    "stop_sparse",
    "stop_invalid",
    "run_bounded_audit",
}
EXPECTED_ALLOWED_INPUTS = {
    "valid_failure_and_success_denominators",
    "primary_coder_completeness_refusal_malformed_rates",
    "golden_case_and_evidence_contract_status",
    "aggregate_de_candidate_prevalence_without_named_context_effect",
    "probability_weighted_anchor_error_diagnostics",
    "prospective_precision_feasibility",
}
EXPECTED_FORBIDDEN_INPUTS = {
    "named_environment_effect_direction",
    "hypothesis_threshold_crossing",
    "forecast_significance_after_expansion",
    "investigator_selected_interesting_cases",
}
EXPECTED_MASKING_FIELDS = {
    "explicit_environment_name_removed",
    "explicit_windows_linux_contrast_removed",
    "ai_labels_removed",
    "hypothesis_aggregate_results_removed",
    "identity_blinding_claimed",
}
EXPECTED_ANCHOR_FIELDS = {"labels", "always_run", "sampling"}
EXPECTED_FOCAL_FIELDS = {
    "population",
    "sampling",
    "allocation",
    "anchor_overlap",
    "conditional_inclusion_probabilities_recorded",
    "additional_labels",
    "maximum_routine_total_labels",
    "automatic_third_stage",
}
EXPECTED_GATE_FIELDS = {"allowed_inputs", "forbidden_inputs", "thresholds", "outcomes"}
EXPECTED_ANCHOR_SAMPLING = (
    "known_probability_stratified_by_programmatic_outcome_and_task_domain"
)
EXPECTED_FOCAL_POPULATION = (
    "eligible_unique_valid_failed_trials_excluding_anchor_identities"
)
EXPECTED_FOCAL_SAMPLING = (
    "label_masked_context_stratified_srs_without_replacement"
)
EXPECTED_FOCAL_ALLOCATION = (
    "reserve_5_per_context_then_hamilton_proportional_remaining"
)
EXPECTED_THRESHOLDS = {
    "minimum_primary_completeness_overall": 0.95,
    "minimum_primary_completeness_per_registered_stratum": 0.90,
    "minimum_design_weighted_kappa": 0.60,
    "minimum_nonanchor_pooled_focal_failures": 150,
    "minimum_nonanchor_focal_failures_per_context": 5,
}
EXPECTED_SEED_RULE = "sha256(policy_digest || analysis_manifest_digest)"


class StagedAuditError(ValueError):
    """The candidate audit policy is malformed or violates V2 constraints."""


@dataclass(frozen=True)
class StagedAuditPolicy:
    anchor_labels: int
    focal_label_options: tuple[int, ...]
    maximum_routine_total_labels: int
    allowed_gate_inputs: frozenset[str]
    forbidden_gate_inputs: frozenset[str]
    gate_outcomes: frozenset[str]
    thresholds: Mapping[str, float]

    @property
    def maximum_focal_labels(self) -> int:
        return max(self.focal_label_options)


@dataclass(frozen=True)
class StagedAuditSelection:
    """Fully auditable realization of the conditional second-stage sample."""

    outcome: str
    anchor_identities: tuple[str, ...]
    focal_identities: tuple[str, ...]
    overall_identities: tuple[str, ...]
    eligible_nonanchor_by_context: Mapping[str, int]
    focal_allocation_by_context: Mapping[str, int]
    conditional_inclusion_probability_by_context: Mapping[str, float]
    scarcity_reasons: tuple[str, ...]
    h4_assurance_scope: str
    h4_seeded_focal_identities: tuple[str, ...]

    def as_record(self) -> dict[str, object]:
        """Return a JSON-safe record containing stage and overall identities."""

        return {
            "outcome": self.outcome,
            "stage_identities": {
                "anchor": list(self.anchor_identities),
                "focal": list(self.focal_identities),
            },
            "overall_identities": list(self.overall_identities),
            "eligible_nonanchor_by_context": dict(
                self.eligible_nonanchor_by_context
            ),
            "focal_allocation_by_context": dict(self.focal_allocation_by_context),
            "conditional_inclusion_probability_by_context": dict(
                self.conditional_inclusion_probability_by_context
            ),
            "scarcity_reasons": list(self.scarcity_reasons),
            "h4_assurance": {
                "scope": self.h4_assurance_scope,
                "anchor_identities": list(self.anchor_identities),
                "seeded_focal_identities": list(self.h4_seeded_focal_identities),
            },
        }


def _positive_int(value: object, *, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise StagedAuditError(f"{field} must be a positive integer")
    return value


def load_staged_audit_policy(path: Path) -> StagedAuditPolicy:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise StagedAuditError(f"cannot load staged audit policy: {exc}") from exc
    if not isinstance(raw, dict):
        raise StagedAuditError("staged audit policy must be a JSON object")
    expected = {
        "schema_version",
        "status",
        "decision",
        "claim_scope",
        "primary_label_source",
        "adjudication_rewrites_primary",
        "label_masking",
        "anchor",
        "focal_audit",
        "gate",
        "sampling_seed",
        "larger_audit_requires_new_explicit_decision",
    }
    if set(raw) != expected:
        raise StagedAuditError("staged audit policy has unknown or missing fields")
    if (
        raw["schema_version"] != SCHEMA_VERSION
        or raw["status"] != "candidate"
        or raw["decision"] != "D-010"
        or raw["claim_scope"] != "exploratory_h2_h4"
        or raw["primary_label_source"] != "frozen_coder_1"
        or raw["adjudication_rewrites_primary"] is not False
        or raw["larger_audit_requires_new_explicit_decision"] is not True
    ):
        raise StagedAuditError("staged audit policy violates accepted D-010 scope")

    masking = raw["label_masking"]
    if not isinstance(masking, dict) or set(masking) != EXPECTED_MASKING_FIELDS:
        raise StagedAuditError("label_masking has unknown or missing fields")
    if any(
        masking[field] is not True
        for field in EXPECTED_MASKING_FIELDS - {"identity_blinding_claimed"}
    ) or masking["identity_blinding_claimed"] is not False:
        raise StagedAuditError("label-masking claims contradict the accepted boundary")
    if raw["sampling_seed"] != EXPECTED_SEED_RULE:
        raise StagedAuditError("sampling seed rule differs from the accepted design")

    anchor = raw["anchor"]
    focal = raw["focal_audit"]
    gate = raw["gate"]
    if not all(isinstance(value, dict) for value in (anchor, focal, gate)):
        raise StagedAuditError("anchor, focal_audit, and gate must be objects")
    if set(anchor) != EXPECTED_ANCHOR_FIELDS:
        raise StagedAuditError("anchor has unknown or missing fields")
    if set(focal) != EXPECTED_FOCAL_FIELDS:
        raise StagedAuditError("focal_audit has unknown or missing fields")
    if set(gate) != EXPECTED_GATE_FIELDS:
        raise StagedAuditError("gate has unknown or missing fields")
    if anchor.get("always_run") is not True:
        raise StagedAuditError("the fixed anchor must always run")
    anchor_labels = _positive_int(anchor.get("labels"), field="anchor.labels")
    if anchor.get("sampling") != EXPECTED_ANCHOR_SAMPLING:
        raise StagedAuditError("anchor sampling differs from the accepted design")

    if focal.get("population") != EXPECTED_FOCAL_POPULATION:
        raise StagedAuditError("focal population differs from the accepted design")
    if focal.get("sampling") != EXPECTED_FOCAL_SAMPLING:
        raise StagedAuditError("focal sampling differs from the accepted design")
    if focal.get("allocation") != EXPECTED_FOCAL_ALLOCATION:
        raise StagedAuditError("focal allocation differs from the accepted design")
    if focal.get("anchor_overlap") != "excluded":
        raise StagedAuditError("focal selection must exclude anchor identities")
    if focal.get("conditional_inclusion_probabilities_recorded") is not True:
        raise StagedAuditError("focal inclusion probabilities must be recorded")

    additional = _positive_int(
        focal.get("additional_labels"), field="focal_audit.additional_labels"
    )
    options = (additional,)
    maximum = _positive_int(
        focal.get("maximum_routine_total_labels"),
        field="focal_audit.maximum_routine_total_labels",
    )
    if anchor_labels != 50 or options != (150,):
        raise StagedAuditError("routine stages must contain exactly 50 and 150 labels")
    if maximum != anchor_labels + max(options):
        raise StagedAuditError("routine cap must equal anchor plus largest focal option")
    if maximum != 200 or focal.get("automatic_third_stage") is not False:
        raise StagedAuditError("routine audit exceeds the accepted time-bounded envelope")

    for field in ("allowed_inputs", "forbidden_inputs", "outcomes"):
        if not isinstance(gate.get(field), list) or not all(
            isinstance(value, str) and value for value in gate[field]
        ):
            raise StagedAuditError(f"gate.{field} must be a non-empty string list")
    allowed = frozenset(gate["allowed_inputs"])
    forbidden = frozenset(gate["forbidden_inputs"])
    outcomes = frozenset(gate["outcomes"])
    if allowed & forbidden:
        raise StagedAuditError("allowed and forbidden gate inputs overlap")
    if allowed != EXPECTED_ALLOWED_INPUTS:
        raise StagedAuditError("gate allowed inputs differ from the accepted vocabulary")
    if forbidden != EXPECTED_FORBIDDEN_INPUTS:
        raise StagedAuditError("gate forbidden inputs differ from the accepted vocabulary")
    if outcomes != EXPECTED_GATE_OUTCOMES:
        raise StagedAuditError("gate outcomes differ from the accepted three branches")
    thresholds = gate["thresholds"]
    if not isinstance(thresholds, dict) or thresholds != EXPECTED_THRESHOLDS:
        raise StagedAuditError("gate thresholds differ from the accepted candidate")

    return StagedAuditPolicy(
        anchor_labels=anchor_labels,
        focal_label_options=options,
        maximum_routine_total_labels=maximum,
        allowed_gate_inputs=allowed,
        forbidden_gate_inputs=forbidden,
        gate_outcomes=outcomes,
        thresholds=dict(thresholds),
    )


def estimate_human_hours(
    labels: int,
    *,
    minutes_per_label: float,
    overhead_fraction: float = 0.10,
) -> float:
    labels = _positive_int(labels, field="labels")
    if (
        isinstance(minutes_per_label, bool)
        or not isinstance(minutes_per_label, (int, float))
        or not math.isfinite(float(minutes_per_label))
        or minutes_per_label <= 0
    ):
        raise StagedAuditError("minutes_per_label must be positive and finite")
    if (
        isinstance(overhead_fraction, bool)
        or not isinstance(overhead_fraction, (int, float))
        or not math.isfinite(float(overhead_fraction))
        or overhead_fraction < 0
    ):
        raise StagedAuditError("overhead_fraction must be finite and non-negative")
    return labels * float(minutes_per_label) * (1 + float(overhead_fraction)) / 60


def staged_gate_decision(
    policy: StagedAuditPolicy,
    *,
    evidence_contract_qualified: bool,
    primary_completeness_overall: float,
    primary_completeness_by_stratum: Mapping[str, float],
    design_weighted_ai_kappa: float,
    minimum_design_weighted_human_ai_kappa: float,
    eligible_nonanchor_focal_failures_by_context: Mapping[str, int],
) -> str:
    """Apply the frozen precedence without reading named effect estimates."""

    if not isinstance(evidence_contract_qualified, bool):
        raise StagedAuditError("evidence_contract_qualified must be boolean")
    rates = (
        primary_completeness_overall,
        design_weighted_ai_kappa,
        minimum_design_weighted_human_ai_kappa,
        *primary_completeness_by_stratum.values(),
    )
    if any(
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        or not 0.0 <= float(value) <= 1.0
        for value in rates
    ):
        raise StagedAuditError("gate rates and kappas must lie in [0, 1]")
    if not primary_completeness_by_stratum:
        raise StagedAuditError("registered-stratum completeness is required")
    if set(eligible_nonanchor_focal_failures_by_context) != set(FOCAL_CONTEXTS):
        raise StagedAuditError(
            "eligible non-anchor focal failure counts require both contexts"
        )
    if any(
        isinstance(value, bool) or not isinstance(value, int) or value < 0
        for value in eligible_nonanchor_focal_failures_by_context.values()
    ):
        raise StagedAuditError(
            "eligible non-anchor focal failure counts must be nonnegative integers"
        )

    threshold = policy.thresholds
    if (
        not evidence_contract_qualified
        or primary_completeness_overall
        < threshold["minimum_primary_completeness_overall"]
        or min(primary_completeness_by_stratum.values())
        < threshold["minimum_primary_completeness_per_registered_stratum"]
        or design_weighted_ai_kappa < threshold["minimum_design_weighted_kappa"]
        or minimum_design_weighted_human_ai_kappa
        < threshold["minimum_design_weighted_kappa"]
    ):
        return "stop_invalid"

    counts = tuple(eligible_nonanchor_focal_failures_by_context.values())
    if (
        sum(counts) < threshold["minimum_nonanchor_pooled_focal_failures"]
        or min(counts)
        < threshold["minimum_nonanchor_focal_failures_per_context"]
    ):
        return "stop_sparse"
    return "run_bounded_audit"


def _validated_identities(
    values: Iterable[str], *, field: str
) -> tuple[str, ...]:
    identities = tuple(values)
    if any(
        not isinstance(identity, str)
        or not identity
        or identity.strip() != identity
        for identity in identities
    ):
        raise StagedAuditError(f"{field} must contain non-empty trimmed strings")
    if len(set(identities)) != len(identities):
        raise StagedAuditError(f"{field} contains duplicate trial identities")
    return identities


def _validated_digest(value: str, *, field: str) -> str:
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise StagedAuditError(f"{field} must be a lowercase SHA-256 digest")
    return value


def _hamilton_focal_allocation(
    population_by_context: Mapping[str, int],
    *,
    focal_size: int,
    reserve_per_context: int,
) -> dict[str, int]:
    """Use integer Hamilton arithmetic with a context-name tie break."""

    contexts = tuple(sorted(FOCAL_CONTEXTS))
    remaining_sample = focal_size - reserve_per_context * len(contexts)
    remaining_population = {
        context: population_by_context[context] - reserve_per_context
        for context in contexts
    }
    denominator = sum(remaining_population.values())
    floors: dict[str, int] = {}
    remainders: dict[str, int] = {}
    for context in contexts:
        numerator = remaining_sample * remaining_population[context]
        floors[context], remainders[context] = divmod(numerator, denominator)
    unassigned = remaining_sample - sum(floors.values())
    ranked = sorted(contexts, key=lambda item: (-remainders[item], item))
    for context in ranked[:unassigned]:
        floors[context] += 1
    allocation = {
        context: reserve_per_context + floors[context] for context in contexts
    }
    if sum(allocation.values()) != focal_size or any(
        allocation[context] > population_by_context[context]
        for context in contexts
    ):
        raise RuntimeError("Hamilton allocation violated the fixed audit envelope")
    return allocation


def select_staged_audit(
    policy: StagedAuditPolicy,
    *,
    anchor_identities: Sequence[str],
    eligible_failed_identities_by_context: Mapping[str, Sequence[str]],
    policy_digest: str,
    analysis_manifest_digest: str,
    seeded_error_identities: Iterable[str] = (),
) -> StagedAuditSelection:
    """Select the conditional 150-trial focal audit, or stop at the anchor.

    The eligible focal population is formed only after the 50 anchor identities
    are excluded. The focal stage is all-or-nothing: scarcity never triggers a
    census, replacement, or a sample smaller than 150.
    """

    if policy.anchor_labels != 50 or policy.maximum_focal_labels != 150:
        raise StagedAuditError("selection requires the fixed 50+150 policy")
    anchors = _validated_identities(anchor_identities, field="anchor_identities")
    if len(anchors) != policy.anchor_labels:
        raise StagedAuditError("anchor_identities must contain exactly 50 trials")
    if set(eligible_failed_identities_by_context) != set(FOCAL_CONTEXTS):
        raise StagedAuditError("eligible focal populations require both contexts")

    anchor_set = set(anchors)
    eligible: dict[str, tuple[str, ...]] = {}
    seen: set[str] = set()
    for context in FOCAL_CONTEXTS:
        raw = _validated_identities(
            eligible_failed_identities_by_context[context],
            field=f"eligible_failed_identities_by_context[{context!r}]",
        )
        filtered = tuple(identity for identity in raw if identity not in anchor_set)
        overlap = seen.intersection(filtered)
        if overlap:
            raise StagedAuditError(
                "a trial identity appears in more than one focal context"
            )
        seen.update(filtered)
        eligible[context] = filtered

    counts = {context: len(eligible[context]) for context in FOCAL_CONTEXTS}
    threshold = policy.thresholds
    reasons: list[str] = []
    if sum(counts.values()) < threshold[
        "minimum_nonanchor_pooled_focal_failures"
    ]:
        reasons.append("fewer_than_150_eligible_unique_nonanchor_failures")
    thin_contexts = tuple(
        context
        for context in FOCAL_CONTEXTS
        if counts[context]
        < threshold["minimum_nonanchor_focal_failures_per_context"]
    )
    reasons.extend(f"fewer_than_5_in_{context}" for context in thin_contexts)

    seeded = set(
        _validated_identities(seeded_error_identities, field="seeded_error_identities")
    )
    h4_scope = "exploratory_anchor_plus_any_seeded_focal_coverage"
    if reasons:
        return StagedAuditSelection(
            outcome="stop_sparse",
            anchor_identities=anchors,
            focal_identities=(),
            overall_identities=anchors,
            eligible_nonanchor_by_context=counts,
            focal_allocation_by_context={context: 0 for context in FOCAL_CONTEXTS},
            conditional_inclusion_probability_by_context={
                context: 0.0 for context in FOCAL_CONTEXTS
            },
            scarcity_reasons=tuple(reasons),
            h4_assurance_scope=h4_scope,
            h4_seeded_focal_identities=(),
        )

    allocation = _hamilton_focal_allocation(
        counts,
        focal_size=policy.maximum_focal_labels,
        reserve_per_context=threshold[
            "minimum_nonanchor_focal_failures_per_context"
        ],
    )
    policy_digest = _validated_digest(policy_digest, field="policy_digest")
    analysis_manifest_digest = _validated_digest(
        analysis_manifest_digest, field="analysis_manifest_digest"
    )
    seed = hashlib.sha256(
        (policy_digest + analysis_manifest_digest).encode("ascii")
    ).digest()
    selected: list[str] = []
    for context in sorted(FOCAL_CONTEXTS):
        ranked = sorted(
            eligible[context],
            key=lambda identity: (
                hashlib.sha256(
                    seed
                    + b"\0focal\0"
                    + context.encode("utf-8")
                    + b"\0"
                    + identity.encode("utf-8")
                ).digest(),
                identity,
            ),
        )
        selected.extend(ranked[: allocation[context]])
    focal = tuple(selected)
    overall = anchors + focal
    if (
        len(focal) != 150
        or len(overall) != 200
        or len(set(overall)) != len(overall)
    ):
        raise RuntimeError("staged audit selection violated uniqueness or fixed cap")
    return StagedAuditSelection(
        outcome="run_bounded_audit",
        anchor_identities=anchors,
        focal_identities=focal,
        overall_identities=overall,
        eligible_nonanchor_by_context=counts,
        focal_allocation_by_context=allocation,
        conditional_inclusion_probability_by_context={
            context: allocation[context] / counts[context]
            for context in FOCAL_CONTEXTS
        },
        scarcity_reasons=(),
        h4_assurance_scope=h4_scope,
        h4_seeded_focal_identities=tuple(
            identity for identity in focal if identity in seeded
        ),
    )
