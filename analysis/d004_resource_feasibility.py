"""Prospective resource accounting for D-004 and D-006.

This module converts the candidate broad split-N roster into transparent call
counts.  It deliberately does *not* convert calls into subscription quota:
rolling vendor limits are an empirical input, and agent trials and rubric
calls can consume very different amounts of that input.

The rows distinguish:

* version-sensitive agent-under-test collection;
* AI rubric calls under the literal full-sample two-coder design;
* hypothesis-specific coding surfaces for H2 and H4;
* human review time under explicit timing assumptions.

No resource cap, N, task bank, coder backend, or hypothesis scope is selected
by this evidence scaffold.
"""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass
from typing import Iterable, Sequence

import numpy as np

from analysis.d010_joint_h2_measurement import (
    JointScenario,
    build_joint_manifest,
    default_joint_scenarios,
)
from analysis.d013_ceiling_operating_characteristics import (
    N_SEEDED_VARIANTS,
)
from analysis.d013_task_bank_design import (
    REGISTERED_CONFIG_IDS,
    REGISTERED_ENVIRONMENT_IDS,
)


N_CAPABILITY_FAMILIES = 12
N_AI_CODERS_CURRENT = 2
N_ANCHOR_LABELS = 50

CONFIG_PROVIDER = {
    "CFG1": "anthropic_subscription",
    "CFG2": "anthropic_subscription",
    "CFG3": "openai_subscription",
    "CFG4": "openai_subscription",
    "CFG5": "agy_google_subscription",
    "CFG6": "agy_google_subscription",
    "CFG7": "agy_google_subscription",
}


@dataclass(frozen=True)
class CandidateRosterCost:
    """Exact call-count identities for one broad split-N candidate roster."""

    base_common_n: int
    capability_n: int
    capability_trials_per_configuration: int
    seeded_trials_per_configuration: int
    full_trials_per_configuration: int
    capability_trials_full_matrix: int
    seeded_trials_full_matrix: int
    full_trials: int


def candidate_roster_cost(base_common_n: int) -> CandidateRosterCost:
    """Return exact candidate broad split-N trial counts."""

    if isinstance(base_common_n, bool) or not isinstance(base_common_n, int):
        raise ValueError("base_common_n must be an integer")
    if base_common_n < 6:
        raise ValueError("base_common_n must be at least six")

    capability_n = math.ceil(5 * base_common_n / 12)
    environments = len(REGISTERED_ENVIRONMENT_IDS)
    configurations = len(REGISTERED_CONFIG_IDS)
    capability_per_configuration = (
        environments * N_CAPABILITY_FAMILIES * capability_n
    )
    seeded_per_configuration = (
        environments * N_SEEDED_VARIANTS * base_common_n
    )
    full_per_configuration = (
        capability_per_configuration + seeded_per_configuration
    )
    return CandidateRosterCost(
        base_common_n=base_common_n,
        capability_n=capability_n,
        capability_trials_per_configuration=capability_per_configuration,
        seeded_trials_per_configuration=seeded_per_configuration,
        full_trials_per_configuration=full_per_configuration,
        capability_trials_full_matrix=(
            configurations * capability_per_configuration
        ),
        seeded_trials_full_matrix=configurations * seeded_per_configuration,
        full_trials=configurations * full_per_configuration,
    )


def provider_agent_calls(
    cost: CandidateRosterCost,
    *,
    scope: str,
) -> dict[str, int]:
    """Partition agent-under-test calls by subscription provider."""

    if scope == "capability_core_h1_h3":
        per_configuration = cost.capability_trials_per_configuration
    elif scope == "full_four_hypothesis_matrix":
        per_configuration = cost.full_trials_per_configuration
    else:
        raise ValueError("unknown collection scope")

    result: dict[str, int] = {}
    for config_id in REGISTERED_CONFIG_IDS:
        provider = CONFIG_PROVIDER[config_id]
        result[provider] = result.get(provider, 0) + per_configuration
    if sum(result.values()) != (
        cost.capability_trials_full_matrix
        if scope == "capability_core_h1_h3"
        else cost.full_trials
    ):
        raise RuntimeError("provider partition does not sum to the roster")
    return result


def expected_focal_failures(
    scenario: JointScenario,
    *,
    base_common_n: int,
) -> float:
    """Return the scenario-mean Windows/Linux failure population for H2."""

    manifest = build_joint_manifest(scenario.h2, base_common_n=base_common_n)
    focal = np.isin(
        manifest.environment,
        (
            REGISTERED_ENVIRONMENT_IDS.index("windows_powershell"),
            REGISTERED_ENVIRONMENT_IDS.index("linux_native"),
        ),
    )
    return float(np.sum(manifest.failure_probability[focal]))


def review_hours(
    *,
    labels: float,
    minutes_per_label: float,
    overhead_fraction: float = 0.10,
) -> float:
    """Translate an explicit review-speed assumption into active hours."""

    values = (labels, minutes_per_label, overhead_fraction)
    if any(not math.isfinite(value) for value in values):
        raise ValueError("review inputs must be finite")
    if labels < 0.0 or minutes_per_label <= 0.0 or overhead_fraction < 0.0:
        raise ValueError("review inputs are outside their valid ranges")
    return labels * minutes_per_label * (1.0 + overhead_fraction) / 60.0


def resource_rows(
    *,
    base_common_ns: Iterable[int] = (6, 12, 24),
    audit_budgets: Iterable[int] = (200, 400, 600, 700, 800, 1_000),
    minutes_per_label: Iterable[float] = (3.0, 5.0, 8.0),
    scenario_name: str = "high_quality_strong",
    overhead_fraction: float = 0.10,
) -> list[dict[str, float | int | str | bool]]:
    """Build exact call counts plus scenario-indexed review-time references."""

    base_common_ns = tuple(base_common_ns)
    audit_budgets = tuple(audit_budgets)
    minutes_per_label = tuple(minutes_per_label)
    if not base_common_ns or not audit_budgets or not minutes_per_label:
        raise ValueError("N values, audit budgets, and review speeds are required")
    if len(set(base_common_ns)) != len(base_common_ns):
        raise ValueError("base_common_ns must be unique")
    if len(set(audit_budgets)) != len(audit_budgets):
        raise ValueError("audit budgets must be unique")
    if len(set(minutes_per_label)) != len(minutes_per_label):
        raise ValueError("minutes_per_label values must be unique")
    if any(value < 1 for value in audit_budgets):
        raise ValueError("audit budgets must be positive")

    scenarios = {item.name: item for item in default_joint_scenarios()}
    if scenario_name not in scenarios:
        raise ValueError("unknown joint scenario")
    scenario = scenarios[scenario_name]

    rows: list[dict[str, float | int | str | bool]] = []
    for base_n in base_common_ns:
        cost = candidate_roster_cost(base_n)
        focal_failures = expected_focal_failures(
            scenario,
            base_common_n=base_n,
        )
        full_provider = provider_agent_calls(
            cost,
            scope="full_four_hypothesis_matrix",
        )
        core_provider = provider_agent_calls(
            cost,
            scope="capability_core_h1_h3",
        )
        rows.append(
            {
                "record_type": "d004_candidate_roster_cost",
                "base_common_n": base_n,
                "capability_n": cost.capability_n,
                "capability_agent_trials": cost.capability_trials_full_matrix,
                "seeded_agent_trials": cost.seeded_trials_full_matrix,
                "full_agent_trials": cost.full_trials,
                "anthropic_agent_trials_full": full_provider[
                    "anthropic_subscription"
                ],
                "openai_agent_trials_full": full_provider[
                    "openai_subscription"
                ],
                "agy_agent_trials_full": full_provider[
                    "agy_google_subscription"
                ],
                "anthropic_agent_trials_capability_core": core_provider[
                    "anthropic_subscription"
                ],
                "openai_agent_trials_capability_core": core_provider[
                    "openai_subscription"
                ],
                "agy_agent_trials_capability_core": core_provider[
                    "agy_google_subscription"
                ],
                "current_two_ai_full_sample_grading_calls": (
                    N_AI_CODERS_CURRENT * cost.full_trials
                ),
                "h4_seeded_two_ai_grading_calls": (
                    N_AI_CODERS_CURRENT * cost.seeded_trials_full_matrix
                ),
                "h2_expected_focal_failures": focal_failures,
                "h2_expected_focal_failure_two_ai_grading_calls": (
                    N_AI_CODERS_CURRENT * focal_failures
                ),
                "literal_current_total_subscription_invocations_before_pilot_or_retries": (
                    cost.full_trials + N_AI_CODERS_CURRENT * cost.full_trials
                ),
                "judge_provider_assignment": "open_D006_not_charged_to_provider",
                "raw_calls_are_quota_estimates": False,
                "scenario_for_expected_failures": scenario_name,
            }
        )
        for budget in audit_budgets:
            expected_actual_audit = min(float(budget), focal_failures)
            labels = N_ANCHOR_LABELS + expected_actual_audit
            for minutes in minutes_per_label:
                rows.append(
                    {
                        "record_type": "d004_human_review_reference",
                        "base_common_n": base_n,
                        "scenario": scenario_name,
                        "requested_focal_audit_budget": budget,
                        "scenario_mean_focal_failure_population": focal_failures,
                        "scenario_mean_actual_audit_labels": expected_actual_audit,
                        "separate_anchor_labels": N_ANCHOR_LABELS,
                        "scenario_mean_total_human_labels": labels,
                        "minutes_per_label_assumption": minutes,
                        "overhead_fraction_assumption": overhead_fraction,
                        "active_review_hours": review_hours(
                            labels=labels,
                            minutes_per_label=minutes,
                            overhead_fraction=overhead_fraction,
                        ),
                        "timing_status": "assumption_requires_nonanalysis_shakedown",
                    }
                )
    return rows


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Emit D-004/D-006 prospective resource-accounting rows."
    )
    parser.add_argument("--base-common-ns", type=int, nargs="+", default=[6, 12, 24])
    parser.add_argument(
        "--audit-budgets",
        type=int,
        nargs="+",
        default=[200, 400, 600, 700, 800, 1_000],
    )
    parser.add_argument(
        "--minutes-per-label",
        type=float,
        nargs="+",
        default=[3.0, 5.0, 8.0],
    )
    parser.add_argument("--scenario", default="high_quality_strong")
    parser.add_argument("--overhead-fraction", type=float, default=0.10)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    rows = resource_rows(
        base_common_ns=args.base_common_ns,
        audit_budgets=args.audit_budgets,
        minutes_per_label=args.minutes_per_label,
        scenario_name=args.scenario,
        overhead_fraction=args.overhead_fraction,
    )
    for row in rows:
        print(json.dumps(row, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
