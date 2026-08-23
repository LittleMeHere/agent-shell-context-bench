"""Named-context-blind, plan-bound V2 pilot ceiling/floor artifact."""

from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from dataclasses import asdict, dataclass
from typing import Mapping, Sequence

from analysis.v2_analysis_dataset import AnalysisDatasetError, AnalysisTrial
from harness.scheduler import SchedulePlan, validate_plan


SCHEMA_VERSION = "1.0.0"
MIN_EVENTS = 5
MIN_FAMILIES = 2


@dataclass(frozen=True)
class PilotGateResult:
    schema_version: str
    plan_digest: str
    analysis_manifest_digest: str
    capability_trials: int
    failures: int
    successes: int
    failing_families: int
    successful_families: int
    failing_domains: int
    successful_domains: int
    domain_concentration_diagnostic: bool
    branch: str
    confirmatory_collection_allowed: bool
    task_change_requires_amendment_and_fresh_pilot: bool
    artifact_digest: str


def _digest(payload: Mapping[str, object]) -> str:
    return hashlib.sha256(
        json.dumps(
            payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode("utf-8")
    ).hexdigest()


def evaluate_pilot_gate(
    trials: Sequence[AnalysisTrial],
    *,
    plan: SchedulePlan,
    analysis_manifest_digest: str,
    family_domains: Mapping[str, str],
) -> PilotGateResult:
    """Classify the accepted symmetric G2 rule without named-context output."""

    validate_plan(plan)
    if re.fullmatch(r"[0-9a-f]{64}", analysis_manifest_digest) is None:
        raise ValueError("analysis_manifest_digest must be lowercase SHA-256")
    planned_cells = {
        cell.cell_id: cell
        for cell in plan.cells
        if cell.family_id in family_domains
    }
    if not planned_cells:
        raise AnalysisDatasetError("validated plan contains no capability cells")
    expected_capability_trials = sum(
        cell.target_valid_trials for cell in planned_cells.values()
    )
    rows = [
        row
        for row in trials
        if row.valid_analysis_trial and row.task_category == "capability"
    ]
    if len(rows) != expected_capability_trials:
        raise AnalysisDatasetError(
            "pilot capability roster is incomplete or excessive: "
            f"expected={expected_capability_trials}, observed={len(rows)}"
        )
    if any(row.plan_digest != plan.digest for row in rows):
        raise AnalysisDatasetError("pilot capability row is bound to a different plan")
    if any(row.failed is None for row in rows):
        raise AnalysisDatasetError("pilot capability outcome is incomplete")
    observed_slots: defaultdict[str, set[int]] = defaultdict(set)
    for row in rows:
        cell = planned_cells.get(row.cell_id)
        observed = (
            row.config_id,
            row.agent_id,
            row.model_id,
            row.env_id,
            row.task_id,
            row.family_id,
            row.instance_id,
            row.phrasing,
        )
        if cell is None or observed != (
            cell.config_id,
            cell.agent_id,
            cell.model_id,
            cell.env_id,
            cell.task_id,
            cell.family_id,
            cell.instance_id,
            cell.phrasing,
        ):
            raise AnalysisDatasetError(
                "pilot capability row identity differs from its registered plan cell"
            )
        if row.valid_slot_index in observed_slots[row.cell_id]:
            raise AnalysisDatasetError("duplicate pilot capability valid slot")
        observed_slots[row.cell_id].add(row.valid_slot_index)
    bad_slots = [
        cell_id
        for cell_id, cell in planned_cells.items()
        if observed_slots.get(cell_id) != set(range(cell.target_valid_trials))
    ]
    if bad_slots:
        raise AnalysisDatasetError(
            f"pilot capability plan cells have incomplete valid slots: {bad_slots[:5]}"
        )
    observed_families = {row.family_id for row in rows}
    if observed_families != set(family_domains):
        raise AnalysisDatasetError(
            "pilot family roster differs from the registered family slate"
        )

    failed_rows = [row for row in rows if row.failed]
    successful_rows = [row for row in rows if not row.failed]
    failing_families = {row.family_id for row in failed_rows}
    successful_families = {row.family_id for row in successful_rows}
    failing_domains = {family_domains[family] for family in failing_families}
    successful_domains = {family_domains[family] for family in successful_families}

    if len(failed_rows) < MIN_EVENTS:
        branch = "ceiling"
    elif len(successful_rows) < MIN_EVENTS:
        branch = "floor"
    elif len(failing_families) < MIN_FAMILIES or len(successful_families) < MIN_FAMILIES:
        branch = "concentrated_one_family"
    else:
        branch = "proceed"
    payload: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "plan_digest": plan.digest,
        "analysis_manifest_digest": analysis_manifest_digest,
        "capability_trials": len(rows),
        "failures": len(failed_rows),
        "successes": len(successful_rows),
        "failing_families": len(failing_families),
        "successful_families": len(successful_families),
        "failing_domains": len(failing_domains),
        "successful_domains": len(successful_domains),
        "domain_concentration_diagnostic": (
            len(failing_domains) < 2 or len(successful_domains) < 2
        ),
        "branch": branch,
        "confirmatory_collection_allowed": branch == "proceed",
        "task_change_requires_amendment_and_fresh_pilot": branch != "proceed",
    }
    return PilotGateResult(**payload, artifact_digest=_digest(payload))


def as_verified_dict(result: PilotGateResult) -> dict[str, object]:
    raw = asdict(result)
    digest = raw.pop("artifact_digest")
    if _digest(raw) != digest:
        raise ValueError("pilot-gate artifact digest mismatch")
    return {**raw, "artifact_digest": digest}
