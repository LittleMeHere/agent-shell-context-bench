"""Machine-check the accepted D-010 staged human-audit envelope.

This module freezes structural constraints without choosing the still-open
numeric expansion thresholds. It makes it impossible for later automation to
silently add a third stage, rewrite primary labels, or condition expansion on
named hypothesis results.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping


SCHEMA_VERSION = "1.1.0"
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
    "additional_labels",
    "maximum_routine_total_labels",
    "automatic_third_stage",
}
EXPECTED_GATE_FIELDS = {"allowed_inputs", "forbidden_inputs", "thresholds", "outcomes"}
EXPECTED_ANCHOR_SAMPLING = (
    "known_probability_stratified_by_programmatic_outcome_and_task_domain"
)
EXPECTED_FOCAL_POPULATION = "valid_failed_trials"
EXPECTED_FOCAL_SAMPLING = "label_masked_context_stratified_srs"
EXPECTED_THRESHOLDS = {
    "minimum_primary_completeness_overall": 0.95,
    "minimum_primary_completeness_per_registered_stratum": 0.90,
    "minimum_design_weighted_kappa": 0.60,
    "minimum_pooled_focal_failures": 10,
    "minimum_focal_failures_per_context": 5,
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

    additional = _positive_int(
        focal.get("additional_labels"), field="focal_audit.additional_labels"
    )
    options = (additional,)
    maximum = _positive_int(
        focal.get("maximum_routine_total_labels"),
        field="focal_audit.maximum_routine_total_labels",
    )
    if maximum != anchor_labels + max(options):
        raise StagedAuditError("routine cap must equal anchor plus largest focal option")
    if maximum > 200 or focal.get("automatic_third_stage") is not False:
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
    focal_failures_by_context: Mapping[str, int],
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
    if set(focal_failures_by_context) != {"windows_powershell", "linux_native"}:
        raise StagedAuditError("focal failure counts require both registered contexts")
    if any(
        isinstance(value, bool) or not isinstance(value, int) or value < 0
        for value in focal_failures_by_context.values()
    ):
        raise StagedAuditError("focal failure counts must be nonnegative integers")

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

    counts = tuple(focal_failures_by_context.values())
    if (
        sum(counts) < threshold["minimum_pooled_focal_failures"]
        or min(counts) < threshold["minimum_focal_failures_per_context"]
    ):
        return "stop_sparse"
    return "run_bounded_audit"
