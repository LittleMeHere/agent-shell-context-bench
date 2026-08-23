from __future__ import annotations

import dataclasses

import pytest

from analysis.v2_analysis_dataset import (
    AnalysisDatasetError,
    AnalysisTrial,
    accepted_family_domains,
)
from analysis.v2_pilot_gate import as_verified_dict, evaluate_pilot_gate
from harness.scheduler import ScheduleError, V2_PILOT_PHASE, build_plan


DOMAINS = accepted_family_domains()


def _rows(plan) -> list[AnalysisTrial]:
    rows = []
    trial_index = 0
    for cell in plan.cells:
        if cell.family_id not in DOMAINS:
            continue
        for valid_slot_index in range(cell.target_valid_trials):
            rows.append(
                AnalysisTrial(
                    plan_digest=plan.digest,
                    cell_id=cell.cell_id,
                    config_id=cell.config_id,
                    env_id=cell.env_id,
                    agent_id=cell.agent_id,
                    model_id=cell.model_id,
                    task_id=cell.task_id,
                    family_id=cell.family_id,
                    instance_id=cell.instance_id,
                    phrasing=cell.phrasing,
                    task_category="capability",
                    trial_index=trial_index,
                    valid_slot_index=valid_slot_index,
                    attempt_id=f"{trial_index:032x}",
                    valid_analysis_trial=True,
                    binary_success_final=True,
                    failed=False,
                    transcript_analysis_eligible=True,
                    agy_cwd_status=None,
                )
            )
            trial_index += 1
    return rows


def _fail(rows: list[AnalysisTrial], indices: list[int]) -> list[AnalysisTrial]:
    failed = set(indices)
    return [
        dataclasses.replace(
            row,
            failed=index in failed,
            binary_success_final=index not in failed,
        )
        for index, row in enumerate(rows)
    ]


def _indices_for_families(
    rows: list[AnalysisTrial], counts: dict[str, int]
) -> list[int]:
    result = []
    for family_id, count in counts.items():
        matches = [
            index for index, row in enumerate(rows) if row.family_id == family_id
        ]
        result.extend(matches[:count])
    return result


@pytest.fixture(scope="module")
def v2_plan(frozen_runtime_binding):
    return build_plan(V2_PILOT_PHASE, runtime_binding=frozen_runtime_binding)


@pytest.mark.parametrize("failures", [0, 4])
def test_ceiling_boundaries(v2_plan, failures: int):
    rows = _fail(_rows(v2_plan), list(range(failures)))
    result = evaluate_pilot_gate(
        rows,
        plan=v2_plan,
        analysis_manifest_digest="b" * 64,
        family_domains=DOMAINS,
    )
    assert result.branch == "ceiling"
    assert not result.confirmatory_collection_allowed


def test_five_events_across_two_families_proceeds_even_in_one_domain(v2_plan):
    base = _rows(v2_plan)
    rows = _fail(base, _indices_for_families(base, {"C01": 3, "C04": 2}))
    result = evaluate_pilot_gate(
        rows,
        plan=v2_plan,
        analysis_manifest_digest="b" * 64,
        family_domains=DOMAINS,
    )
    assert result.branch == "proceed"
    assert result.domain_concentration_diagnostic
    assert result.confirmatory_collection_allowed
    assert as_verified_dict(result)["artifact_digest"] == result.artifact_digest


def test_five_events_in_one_family_is_concentrated_and_stops(v2_plan):
    base = _rows(v2_plan)
    rows = _fail(base, _indices_for_families(base, {"C01": 5}))
    result = evaluate_pilot_gate(
        rows,
        plan=v2_plan,
        analysis_manifest_digest="b" * 64,
        family_domains=DOMAINS,
    )
    assert result.branch == "concentrated_one_family"
    assert not result.confirmatory_collection_allowed


def test_floor_is_symmetric(v2_plan):
    base = _rows(v2_plan)
    rows = _fail(base, list(range(len(base) - 4)))
    result = evaluate_pilot_gate(
        rows,
        plan=v2_plan,
        analysis_manifest_digest="b" * 64,
        family_domains=DOMAINS,
    )
    assert result.branch == "floor"


def test_missing_or_foreign_roster_fails_closed(v2_plan):
    base = _rows(v2_plan)
    with pytest.raises(AnalysisDatasetError, match="incomplete or excessive"):
        evaluate_pilot_gate(
            base[:-1],
            plan=v2_plan,
            analysis_manifest_digest="b" * 64,
            family_domains=DOMAINS,
        )
    rows = list(base)
    rows[0] = dataclasses.replace(rows[0], plan_digest="c" * 64)
    with pytest.raises(AnalysisDatasetError, match="different plan"):
        evaluate_pilot_gate(
            rows,
            plan=v2_plan,
            analysis_manifest_digest="b" * 64,
            family_domains=DOMAINS,
        )


def test_identity_swap_and_forged_plan_fail_closed(v2_plan):
    rows = _rows(v2_plan)
    foreign_task = next(row.task_id for row in rows if row.task_id != rows[0].task_id)
    rows[0] = dataclasses.replace(rows[0], task_id=foreign_task)
    with pytest.raises(AnalysisDatasetError, match="registered plan cell"):
        evaluate_pilot_gate(
            rows,
            plan=v2_plan,
            analysis_manifest_digest="b" * 64,
            family_domains=DOMAINS,
        )

    forged = dataclasses.replace(v2_plan, digest="c" * 64)
    with pytest.raises(ScheduleError, match="plan digest mismatch"):
        evaluate_pilot_gate(
            _rows(v2_plan),
            plan=forged,
            analysis_manifest_digest="b" * 64,
            family_domains=DOMAINS,
        )
