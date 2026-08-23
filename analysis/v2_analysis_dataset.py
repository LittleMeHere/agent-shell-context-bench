"""Fail-closed V2 analysis-record reconstruction and H1 point estimation.

The collection writer is not treated as sufficient proof that later bytes are
coherent.  This module revalidates the schedule identity, raw completion and
check evidence, common binary outcome, and accepted D-011 agy evidence before
an observation can enter an analysis denominator.

It intentionally supplies only the accepted finite-roster point estimand.
The D-005 interval, epoch sensitivity, missing-slot policy, and confirmatory
decision remain separate pre-data choices and are not guessed here.
"""

from __future__ import annotations

import dataclasses
import math
import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping, Sequence

from analysis.d013_family_slate import EXPECTED_FAMILIES, load_family_slate
from harness.logging.writer import SCHEMA_VERSION as TRIAL_SCHEMA_VERSION
from harness.outcomes import construct_agy_outcome_evidence, construct_binary_outcome
from harness.schedule_identity import ScheduleIdentity
from harness.scheduler import (
    SchedulePlan,
    V2_CONFIRMATORY_PHASE,
    schedule_identity_for_cell,
    validate_plan,
    v2_confirmatory_epoch_for_position,
    v2_pilot_epoch_for_position,
)


FAMILY_SLATE_PATH = (
    Path(__file__).resolve().parents[1]
    / "config"
    / "v2-family-slate.accepted.json"
)
FOCAL_ENVIRONMENTS = ("windows_powershell", "linux_native")


class AnalysisDatasetError(ValueError):
    """A record or dataset cannot be used without silent repair."""


@dataclass(frozen=True)
class AnalysisTrial:
    plan_digest: str
    cell_id: str
    config_id: str
    env_id: str
    agent_id: str
    model_id: str
    task_id: str
    family_id: str
    instance_id: str
    phrasing: str
    task_category: str
    trial_index: int
    valid_slot_index: int | None
    attempt_id: str
    valid_analysis_trial: bool
    binary_success_final: bool
    failed: bool | None
    transcript_analysis_eligible: bool | None
    agy_cwd_status: str | None
    execution_position: int | None = None
    collection_epoch: int | None = None

    @property
    def identity(self) -> tuple[str, str, int, str]:
        return self.plan_digest, self.cell_id, self.trial_index, self.attempt_id


@dataclass(frozen=True)
class FiniteRosterH1PointEstimate:
    windows_failure_rate: float
    linux_failure_rate: float
    risk_difference: float
    risk_ratio: float
    domains: int
    families: int
    instances: int
    configurations: int
    trials: int


def _mapping(raw: object, label: str) -> Mapping[str, object]:
    if not isinstance(raw, Mapping):
        raise AnalysisDatasetError(f"{label} must be a JSON object")
    return raw


def _strict_bool(value: object, label: str) -> bool:
    if type(value) is not bool:
        raise AnalysisDatasetError(f"{label} must be a JSON boolean")
    return value


def _nonnegative_int(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise AnalysisDatasetError(f"{label} must be a non-negative integer")
    return value


def _validate_agy(
    raw: Mapping[str, object],
    *,
    expected_outcome: object,
    agent_induced_measurement_loss: bool,
) -> tuple[bool, str]:
    status = raw.get("brain_parse_status")
    if status not in {"present", "missing", "parse_error", "ambiguous"}:
        raise AnalysisDatasetError("agy brain_parse_status is invalid")
    located = _strict_bool(
        raw.get("brain_transcript_located"),
        "agy.brain_transcript_located",
    )
    if located is not (status == "present"):
        raise AnalysisDatasetError("agy transcript location contradicts parse status")
    counts = {
        field: _nonnegative_int(raw.get(field), f"agy.{field}")
        for field in (
            "brain_conversation_candidates",
            "brain_valid_event_count",
            "brain_malformed_line_count",
            "brain_shell_call_count",
            "brain_outcome_event_count",
        )
    }
    if status == "present":
        if (
            counts["brain_valid_event_count"] < 1
            or counts["brain_malformed_line_count"] != 0
            or counts["brain_shell_call_count"]
            != counts["brain_outcome_event_count"]
        ):
            raise AnalysisDatasetError("agy present transcript diagnostics are incomplete")
    elif counts["brain_valid_event_count"] != 0:
        raise AnalysisDatasetError("unavailable agy transcript claims valid events")

    cwd_rows = raw.get("cwd_tags")
    if not isinstance(cwd_rows, list):
        raise AnalysisDatasetError("agy.cwd_tags must be a JSON array")
    tags: list[str] = []
    for index, row in enumerate(cwd_rows):
        item = _mapping(row, f"agy.cwd_tags[{index}]")
        if set(item) != {"index", "cwd", "tag"} or item.get("index") != index:
            raise AnalysisDatasetError("agy Cwd tag record is malformed")
        tag = item.get("tag")
        if tag not in {"cwd_in_sandbox", "cwd_in_agy_scratch", "cwd_elsewhere"}:
            raise AnalysisDatasetError("agy Cwd tag is invalid")
        tags.append(str(tag))
    if status != "present" and tags:
        raise AnalysisDatasetError("unavailable agy transcript claims Cwd evidence")

    evidence = _mapping(raw.get("v2_outcome_evidence"), "agy.v2_outcome_evidence")
    reconstructed = construct_agy_outcome_evidence(
        checks_passed=expected_outcome.checks_passed,
        completed=(expected_outcome.decision_reason not in {"timed_out", "incomplete"}),
        timed_out=(expected_outcome.decision_reason == "timed_out"),
        brain_status=status,
        cwd_tags=tags if status == "present" else None,
        agent_induced_measurement_loss=agent_induced_measurement_loss,
    )
    if evidence != reconstructed.as_log_dict():
        raise AnalysisDatasetError("agy D-011 evidence contradicts raw H1/Cwd evidence")

    compliance = _mapping(raw.get("cwd_compliance"), "agy.cwd_compliance")
    expected_compliance = {
        "commands": len(tags),
        "cwd_in_sandbox": tags.count("cwd_in_sandbox"),
        "cwd_in_agy_scratch": tags.count("cwd_in_agy_scratch"),
        "cwd_elsewhere": tags.count("cwd_elsewhere"),
        "sandbox_compliance_rate": (
            tags.count("cwd_in_sandbox") / len(tags) if tags else None
        ),
    }
    if dict(compliance) != expected_compliance:
        raise AnalysisDatasetError("agy Cwd compliance contradicts raw tags")
    return reconstructed.transcript_analysis_eligible, reconstructed.cwd_status


def derive_analysis_trial(record: Mapping[str, object]) -> AnalysisTrial:
    """Reconstruct one scheduled analysis row or fail without repair."""

    if record.get("schema_version") != TRIAL_SCHEMA_VERSION:
        raise AnalysisDatasetError("unsupported trial schema")
    try:
        schedule = ScheduleIdentity.from_dict(
            _mapping(record.get("schedule"), "schedule")
        )
    except (TypeError, ValueError) as exc:
        raise AnalysisDatasetError(f"invalid schedule identity: {exc}") from exc
    if schedule.trial_schema_version != TRIAL_SCHEMA_VERSION:
        raise AnalysisDatasetError("schedule/trial schema mismatch")

    trial = _mapping(record.get("trial"), "trial")
    expected_trial = {
        "task_id": schedule.task_id,
        "family_id": schedule.family_id,
        "instance_id": schedule.instance_id,
        "instance_sha256": schedule.instance_sha256,
        "agent_id": schedule.agent_id,
        "model_id": schedule.model_id,
        "env_id": schedule.env_id,
        "phrasing": schedule.phrasing,
    }
    for field, expected in expected_trial.items():
        if trial.get(field) != expected:
            raise AnalysisDatasetError(f"trial.{field} contradicts schedule identity")
    trial_index = _nonnegative_int(trial.get("trial_index"), "trial.trial_index")
    task_category = trial.get("task_category")
    expected_category = "capability" if schedule.task_id.startswith("C") else "seeded_error"
    if task_category != expected_category:
        raise AnalysisDatasetError("trial task category contradicts task identity")
    env_probe = _mapping(record.get("environment_probe"), "environment_probe")
    if env_probe.get("env_id") != schedule.env_id:
        raise AnalysisDatasetError("environment probe contradicts schedule identity")

    attempt = _mapping(record.get("attempt"), "attempt")
    attempt_id = attempt.get("attempt_id")
    if not isinstance(attempt_id, str) or re.fullmatch(r"[0-9a-f]{32}", attempt_id) is None:
        raise AnalysisDatasetError("attempt_id is malformed")

    validity = _mapping(record.get("validity"), "validity")
    valid = _strict_bool(validity.get("valid"), "validity.valid")
    measurement = _mapping(record.get("measurement"), "measurement")
    measurement_status = measurement.get("status")
    if measurement_status not in {"complete", "agent_induced_measurement_loss"}:
        raise AnalysisDatasetError("measurement.status is invalid")
    if measurement_status == "agent_induced_measurement_loss" and not valid:
        raise AnalysisDatasetError("agent-induced measurement loss cannot be invalid")

    agent = _mapping(record.get("agent"), "agent")
    process = _mapping(agent.get("process"), "agent.process")
    completed = _strict_bool(agent.get("completed"), "agent.completed")
    timed_out = _strict_bool(process.get("timed_out"), "agent.process.timed_out")
    expected_completed = not timed_out and process.get("returncode") is not None
    if completed is not expected_completed:
        raise AnalysisDatasetError("agent completion contradicts process evidence")

    outcome = _mapping(record.get("outcome"), "outcome")
    checks = outcome.get("checks")
    if not isinstance(checks, list):
        raise AnalysisDatasetError("outcome.checks must be a JSON array")
    check_values: list[bool] = []
    for index, check in enumerate(checks):
        item = _mapping(check, f"outcome.checks[{index}]")
        check_values.append(_strict_bool(item.get("passed"), f"check[{index}].passed"))
    measurement_loss = measurement_status == "agent_induced_measurement_loss"
    checks_passed: bool | None = None if measurement_loss else all(check_values)
    if measurement_loss and checks:
        raise AnalysisDatasetError("measurement-loss record must not contain checks")
    reconstructed = construct_binary_outcome(
        checks_passed=checks_passed,
        completed=completed,
        timed_out=timed_out,
        agent_induced_measurement_loss=measurement_loss,
    )
    expected_outcome = {
        "success": reconstructed.success,
        "checks_passed": reconstructed.checks_passed,
        "decision_reason": reconstructed.decision_reason,
    }
    for field, expected in expected_outcome.items():
        if outcome.get(field) != expected:
            raise AnalysisDatasetError(f"outcome.{field} contradicts raw evidence")

    transcript_eligible: bool | None = None
    cwd_status: str | None = None
    if schedule.agent_id == "agy":
        transcript_eligible, cwd_status = _validate_agy(
            _mapping(record.get("agy"), "agy"),
            expected_outcome=reconstructed,
            agent_induced_measurement_loss=measurement_loss,
        )
    elif "agy" in record:
        raise AnalysisDatasetError("non-agy record contains agy evidence")

    return AnalysisTrial(
        plan_digest=schedule.plan_digest,
        cell_id=schedule.cell_id,
        config_id=schedule.config_id,
        env_id=schedule.env_id,
        agent_id=schedule.agent_id,
        model_id=schedule.model_id,
        task_id=schedule.task_id,
        family_id=schedule.family_id,
        instance_id=schedule.instance_id,
        phrasing=schedule.phrasing,
        task_category=str(task_category),
        trial_index=trial_index,
        valid_slot_index=schedule.valid_slot_index,
        attempt_id=attempt_id,
        valid_analysis_trial=valid,
        binary_success_final=reconstructed.success,
        failed=(not reconstructed.success) if valid else None,
        transcript_analysis_eligible=transcript_eligible,
        agy_cwd_status=cwd_status,
    )


def build_analysis_dataset(
    plan: SchedulePlan,
    records: Iterable[Mapping[str, object]],
) -> tuple[AnalysisTrial, ...]:
    """Validate a complete plan roster and return its valid analysis trials."""

    validate_plan(plan)

    cells = {cell.cell_id: cell for cell in plan.cells}
    rows: list[AnalysisTrial] = []
    identities: set[tuple[str, str, int, str]] = set()
    attempt_ids: set[str] = set()
    indices: set[tuple[str, int]] = set()
    valid_counts: defaultdict[str, int] = defaultdict(int)
    valid_slots: defaultdict[str, set[int]] = defaultdict(set)
    slot_position = {
        (slot.cell_id, slot.valid_slot_index): slot.position
        for slot in plan.execution_slots or ()
    }

    for record in records:
        row = derive_analysis_trial(record)
        if row.plan_digest != plan.digest or row.cell_id not in cells:
            raise AnalysisDatasetError("record is foreign to the supplied plan")
        expected_schedule = schedule_identity_for_cell(
            plan,
            cells[row.cell_id],
            valid_slot_index=row.valid_slot_index,
        ).as_dict()
        if dict(_mapping(record.get("schedule"), "schedule")) != expected_schedule:
            raise AnalysisDatasetError("record schedule differs from its plan cell")
        if row.identity in identities:
            raise AnalysisDatasetError("duplicate analysis-trial identity")
        identities.add(row.identity)
        if row.attempt_id in attempt_ids:
            raise AnalysisDatasetError("duplicate attempt_id across trial records")
        attempt_ids.add(row.attempt_id)
        index_key = (row.cell_id, row.trial_index)
        if index_key in indices:
            raise AnalysisDatasetError("duplicate trial index within a cell")
        indices.add(index_key)
        if row.valid_analysis_trial:
            if row.valid_slot_index is None:
                raise AnalysisDatasetError("V2 record is missing valid-slot identity")
            if row.valid_slot_index in valid_slots[row.cell_id]:
                raise AnalysisDatasetError("duplicate valid slot within a cell")
            valid_slots[row.cell_id].add(row.valid_slot_index)
            valid_counts[row.cell_id] += 1
            if valid_counts[row.cell_id] > cells[row.cell_id].target_valid_trials:
                raise AnalysisDatasetError("cell contains excess valid trials")
            position = slot_position.get((row.cell_id, row.valid_slot_index))
            if position is None:
                raise AnalysisDatasetError("valid slot has no registered position")
            rows.append(
                dataclasses.replace(
                    row,
                    execution_position=position,
                    collection_epoch=(
                        v2_confirmatory_epoch_for_position(position)
                        if plan.phase == V2_CONFIRMATORY_PHASE
                        else v2_pilot_epoch_for_position(position)
                    ),
                )
            )

    incomplete = [
        cell.cell_id
        for cell in plan.cells
        if valid_counts[cell.cell_id] != cell.target_valid_trials
        or valid_slots[cell.cell_id] != set(range(cell.target_valid_trials))
    ]
    if incomplete:
        raise AnalysisDatasetError(
            f"analysis roster has incomplete valid slots: {incomplete[:5]}"
        )
    return tuple(
        sorted(
            rows,
            key=lambda row: (
                slot_position[(row.cell_id, row.valid_slot_index)],
                row.trial_index,
            ),
        )
    )


def accepted_family_domains() -> dict[str, str]:
    """Load and validate the accepted D-013 family/domain roster."""

    load_family_slate(FAMILY_SLATE_PATH)
    return {
        family_id: domain_id
        for domain_id, family_ids in EXPECTED_FAMILIES.items()
        for family_id in family_ids
    }


def finite_roster_h1_point_estimate(
    trials: Sequence[AnalysisTrial],
    *,
    plan: SchedulePlan,
    family_domains: Mapping[str, str] | None = None,
) -> FiniteRosterH1PointEstimate:
    """Compute the plan-bound equal domain/family/instance/config H1 point RD."""

    validate_plan(plan)
    domains = dict(family_domains or accepted_family_domains())
    focal = [
        row
        for row in trials
        if row.valid_analysis_trial
        and row.task_category == "capability"
        and row.env_id in FOCAL_ENVIRONMENTS
    ]
    if not focal:
        raise AnalysisDatasetError("no valid focal capability trials")
    if any(row.failed is None for row in focal):
        raise AnalysisDatasetError("valid focal trial has no failure outcome")
    if any(row.plan_digest != plan.digest for row in focal):
        raise AnalysisDatasetError("focal trial is bound to a different schedule plan")
    unknown = sorted({row.family_id for row in focal} - set(domains))
    if unknown:
        raise AnalysisDatasetError(f"unknown capability families: {unknown}")

    planned_cells = {
        cell.cell_id: (
            cell.env_id,
            cell.config_id,
            cell.family_id,
            cell.instance_id,
            cell.target_valid_trials,
        )
        for cell in plan.cells
        if cell.env_id in FOCAL_ENVIRONMENTS and cell.family_id in domains
    }
    if not planned_cells:
        raise AnalysisDatasetError("validated plan contains no focal capability cells")
    leaf: defaultdict[tuple[str, str, str, str], list[float]] = defaultdict(list)
    for row in focal:
        planned = planned_cells.get(row.cell_id)
        observed = (row.env_id, row.config_id, row.family_id, row.instance_id)
        if planned is None or planned[:4] != observed:
            raise AnalysisDatasetError(
                "focal row identity differs from its registered plan cell"
            )
        leaf[observed].append(float(row.failed))
    configs = sorted({value[1] for value in planned_cells.values()})
    families = sorted(domains)
    instances = sorted({value[3] for value in planned_cells.values()})
    expected = {
        (env, config, family, instance)
        for env in FOCAL_ENVIRONMENTS
        for config in configs
        for family in families
        for instance in instances
    }
    if set(leaf) != expected:
        missing = sorted(expected - set(leaf))[:5]
        extra = sorted(set(leaf) - expected)[:5]
        raise AnalysisDatasetError(
            f"focal finite roster is not a complete crossing: missing={missing}, extra={extra}"
        )
    planned_counts = {
        value[:4]: value[4]
        for value in planned_cells.values()
    }
    mismatches = [
        (key, planned_counts[key], len(leaf[key]))
        for key in sorted(expected)
        if planned_counts.get(key) != len(leaf[key])
    ]
    if mismatches:
        raise AnalysisDatasetError(
            "focal point-estimator leaf counts differ from the registered plan: "
            f"{mismatches[:5]}"
        )

    instance_means = {key: sum(values) / len(values) for key, values in leaf.items()}
    by_family: defaultdict[tuple[str, str, str], list[float]] = defaultdict(list)
    for (env, config, family, _instance), value in instance_means.items():
        by_family[(env, config, family)].append(value)
    family_means = {key: sum(values) / len(values) for key, values in by_family.items()}
    by_domain: defaultdict[tuple[str, str, str], list[float]] = defaultdict(list)
    for (env, config, family), value in family_means.items():
        by_domain[(env, config, domains[family])].append(value)
    domain_means = {key: sum(values) / len(values) for key, values in by_domain.items()}
    by_context: defaultdict[str, list[float]] = defaultdict(list)
    for (env, _config, _domain), value in domain_means.items():
        by_context[env].append(value)
    rates = {env: sum(values) / len(values) for env, values in by_context.items()}
    windows = rates["windows_powershell"]
    linux = rates["linux_native"]
    ratio = windows / linux if linux > 0.0 else math.inf if windows > 0.0 else math.nan
    return FiniteRosterH1PointEstimate(
        windows_failure_rate=windows,
        linux_failure_rate=linux,
        risk_difference=windows - linux,
        risk_ratio=ratio,
        domains=len(set(domains.values())),
        families=len(families),
        instances=len(instances),
        configurations=len(configs),
        trials=len(focal),
    )
