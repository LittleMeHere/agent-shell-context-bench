from __future__ import annotations

import hashlib
from dataclasses import replace

import pytest

from analysis.v2_analysis_dataset import AnalysisTrial
from analysis.v2_coder_join import CoderJoinResult
from analysis.v2_finite_roster import FiniteRosterH1Candidate
from analysis.v2_secondary_reporting import (
    SecondaryAnalysisError,
    a2_descriptive,
    a2_design_aware,
    a3_fixed_block_inference,
    a3_point_estimate,
    a4_descriptive,
    a4_design_aware,
    build_v2_analysis_report,
    report_tables,
)
from analysis.v2_finite_roster import finite_roster_h1_candidate
from harness.scheduler import (
    Cell,
    SchedulePlan,
    ScheduledSlot,
    V2_PILOT_PHASE,
    build_plan,
)


@pytest.fixture(autouse=True)
def _miniature_plan_boundary(monkeypatch: pytest.MonkeyPatch, request: pytest.FixtureRequest):
    if request.node.name != "test_real_v2_plan_traverses_candidate_reporting_boundary":
        monkeypatch.setattr(
            "analysis.v2_secondary_reporting.validate_plan", lambda plan: plan
        )


def _trial(
    *,
    index: int,
    env: str,
    category: str,
    task: str,
    family: str,
    instance: str,
    phrasing: str,
    failed: bool,
    config: str = "CFG1",
) -> AnalysisTrial:
    return AnalysisTrial(
        plan_digest="a" * 64,
        cell_id=f"{env}:{config}:{task}:{phrasing}",
        config_id=config,
        env_id=env,
        agent_id="codex",
        model_id="model",
        task_id=task,
        family_id=family,
        instance_id=instance,
        phrasing=phrasing,
        task_category=category,
        trial_index=index,
        valid_slot_index=0,
        attempt_id=f"{index:032x}",
        valid_analysis_trial=True,
        binary_success_final=not failed,
        failed=failed,
        transcript_analysis_eligible=True,
        agy_cwd_status=None,
    )


def _rows(*, repetitions: int = 10) -> list[AnalysisTrial]:
    rows: list[AnalysisTrial] = []
    index = 0
    for env in (
        "windows_powershell",
        "windows_pwsh7",
        "windows_wsl2",
        "linux_native",
        "macos_actions",
    ):
        for family, domain in (("C01", "D1"), ("C02", "D2")):
            del domain
            for instance in ("I01", "I02"):
                for repetition in range(repetitions):
                    threshold = {
                        "windows_powershell": 4,
                        "windows_pwsh7": 3,
                        "windows_wsl2": 2,
                        "linux_native": 1,
                        "macos_actions": 1,
                    }[env]
                    rows.append(
                        _trial(
                            index=index,
                            env=env,
                            category="capability",
                            task=f"{family}-{instance}",
                            family=family,
                            instance=instance,
                            phrasing="canonical",
                            failed=repetition < threshold,
                        )
                    )
                    index += 1
    for task in ("T01", "T02"):
        for phrasing in ("formal", "colloquial"):
            for repetition in range(4):
                rows.append(
                    _trial(
                        index=index,
                        env="windows_powershell" if repetition % 2 == 0 else "linux_native",
                        category="seeded_error",
                        task=task,
                        family=task,
                        instance="legacy",
                        phrasing=phrasing,
                        failed=True,
                    )
                )
                index += 1
    slots: dict[str, int] = {}
    normalized = []
    for row in rows:
        valid_slot = slots.get(row.cell_id, 0)
        slots[row.cell_id] = valid_slot + 1
        normalized.append(replace(row, valid_slot_index=valid_slot))
    return normalized


def _plan(rows: list[AnalysisTrial]) -> SchedulePlan:
    grouped: dict[str, list[AnalysisTrial]] = {}
    for row in rows:
        grouped.setdefault(row.cell_id, []).append(row)
    cells = []
    slots = []
    position = 0
    for cell_id, values in sorted(grouped.items()):
        row = values[0]
        cells.append(
            Cell(
                cell_id=cell_id,
                config_id=row.config_id,
                agent_id=row.agent_id,
                model_id=row.model_id,
                expected_cli_version="test",
                env_id=row.env_id,
                task_id=row.task_id,
                family_id=row.family_id,
                instance_id=row.instance_id,
                instance_sha256="b" * 64,
                task_path=f"tasks/{row.task_id}.yaml",
                task_sha256="b" * 64,
                phrasing=row.phrasing,
                target_valid_trials=len(values),
            )
        )
        for valid_slot_index in range(len(values)):
            slots.append(
                ScheduledSlot(
                    position=position,
                    round_index=valid_slot_index,
                    block_index=0,
                    valid_slot_index=valid_slot_index,
                    cell_id=cell_id,
                )
            )
            position += 1
    return SchedulePlan(
        schema_version="1.3.0",
        created_at="2026-08-22T00-00-00Z",
        phase=V2_PILOT_PHASE,
        order_seed=1,
        trial_schema_version="1.7.0",
        sizing_lock=None,
        runtime_binding=None,
        execution_slots=tuple(slots),
        cells=tuple(cells),
        digest="a" * 64,
    )


def _a3_confirmatory_rows(profile: str, repetitions: int = 20) -> list[AnalysisTrial]:
    thresholds = {
        "supported": {
            "windows_powershell": 19,
            "windows_pwsh7": 12,
            "windows_wsl2": 4,
            "linux_native": 0,
            "macos_actions": 2,
        },
        "rejected": {
            "windows_powershell": 16,
            "windows_pwsh7": 10,
            "windows_wsl2": 4,
            "linux_native": 8,
            "macos_actions": 3,
        },
        "inconclusive": {
            "windows_powershell": 4,
            "windows_pwsh7": 4,
            "windows_wsl2": 4,
            "linux_native": 4,
            "macos_actions": 4,
        },
    }[profile]
    rows = []
    index = 10_000
    for env in (
        "windows_powershell",
        "windows_pwsh7",
        "windows_wsl2",
        "linux_native",
        "macos_actions",
    ):
        for config_number in range(1, 8):
            config = f"CFG{config_number}"
            for family in ("C01", "C02"):
                for instance in ("I01", "I02"):
                    for repetition in range(repetitions):
                        rows.append(
                            replace(
                                _trial(
                                    index=index,
                                    env=env,
                                    category="capability",
                                    task=f"{family}-{instance}",
                                    family=family,
                                    instance=instance,
                                    phrasing="canonical",
                                    failed=repetition < thresholds[env],
                                    config=config,
                                ),
                                valid_slot_index=repetition,
                            )
                        )
                        index += 1
    return rows


def _design_rows() -> list[AnalysisTrial]:
    rows = _a3_confirmatory_rows("supported")
    index = 100_000
    for task in ("T01", "T02"):
        for phrasing in ("formal", "colloquial"):
            for env in (
                "windows_powershell",
                "windows_pwsh7",
                "windows_wsl2",
                "linux_native",
                "macos_actions",
            ):
                for config_number in range(1, 8):
                    for repetition in range(12):
                        rows.append(
                            replace(
                                _trial(
                                    index=index,
                                    env=env,
                                    category="seeded_error",
                                    task=task,
                                    family=task,
                                    instance="legacy",
                                    phrasing=phrasing,
                                    failed=True,
                                    config=f"CFG{config_number}",
                                ),
                                valid_slot_index=repetition,
                            )
                        )
                        index += 1
    return rows


def _designed_labels(
    rows: list[AnalysisTrial],
) -> dict[tuple[str, str, int, str], CoderJoinResult]:
    labels = {}
    for row in rows:
        if row.task_category == "seeded_error":
            de = (
                row.valid_slot_index is not None
                and row.valid_slot_index
                < (5 if row.phrasing == "colloquial" else 2)
            )
        else:
            de = row.failed is True and row.env_id == "windows_powershell"
        code = "D" if de else "A"
        labels[row.identity] = CoderJoinResult(
            status="coded",
            raw_code=code,
            final_code=code,
            evidence_class="raw_coder",
            applied_rule="preserve_raw_code",
        )
    return labels


def _labels(rows: list[AnalysisTrial]) -> dict[tuple[str, str, int, str], CoderJoinResult]:
    labels = {}
    for index, row in enumerate(rows):
        code = "D" if index % 5 == 0 else "A"
        labels[row.identity] = CoderJoinResult(
            status="coded",
            raw_code=code,
            final_code=code,
            evidence_class="raw_coder",
            applied_rule="preserve_raw_code",
        )
    return labels


def _h1(rows: list[AnalysisTrial]) -> FiniteRosterH1Candidate:
    focal = sum(
        row.task_category == "capability"
        and row.env_id in {"windows_powershell", "linux_native"}
        for row in rows
    )
    return FiniteRosterH1Candidate(
        windows_failure_rate=0.4,
        linux_failure_rate=0.1,
        risk_difference=0.3,
        risk_difference_lower=0.2,
        risk_difference_upper=0.4,
        risk_ratio=4.0,
        risk_ratio_lower=1.5,
        risk_ratio_upper=8.0,
        confidence=0.95,
        interval_method="synthetic",
        fallback_used=False,
        fallback_reason=None,
        decision="decision_relevant_context_penalty",
        cells_per_context=4,
        minimum_cell_n=10,
        trials=focal,
    )


def test_a2_uses_all_failed_trial_denominators() -> None:
    rows = _rows()
    result = a2_descriptive(rows, _labels(rows))
    windows, linux = result.groups
    assert windows.denominator == 24
    assert linux.denominator == 12
    assert result.status == "descriptive_only_primary_model_not_frozen"
    assert result.contrast.inferential_status.startswith("blocked_pending")
    assert result.registered_population == (
        "all_valid_failed_trials_in_windows_and_linux_contexts"
    )


def test_a2_seeded_error_failures_enter_the_registered_population() -> None:
    rows = _rows()
    result = a2_descriptive(rows, _labels(rows))
    expected_seeded = sum(
        row.task_category == "seeded_error"
        and row.env_id in {"windows_powershell", "linux_native"}
        and row.failed is True
        for row in rows
    )
    capability_only = sum(
        row.task_category == "capability"
        and row.env_id in {"windows_powershell", "linux_native"}
        and row.failed is True
        for row in rows
    )
    assert expected_seeded == 16
    assert sum(group.denominator for group in result.groups) == (
        capability_only + expected_seeded
    )


def test_a2_zero_failure_arm_is_not_estimable() -> None:
    rows = [
        replace(row, failed=False, binary_success_final=True)
        if row.env_id == "linux_native"
        else row
        for row in _rows()
    ]
    assert a2_descriptive(rows, _labels(rows)).status == "not_estimable_zero_failure_denominator"


def test_a2_missing_primary_is_visible_not_dropped() -> None:
    rows = _rows()
    labels = _labels(rows)
    target = next(
        row for row in rows if row.task_category == "capability" and row.failed
    )
    labels[target.identity] = CoderJoinResult(
        status="missing",
        raw_code="E",
        final_code=None,
        evidence_class="invalid_or_missing",
        applied_rule="code_E_without_valid_damage_evidence",
    )
    result = a2_descriptive(rows, labels)
    assert result.status == "measurement_incomplete_primary_labels"
    assert sum(group.missing_labels for group in result.groups) == 1


def test_a4_is_all_valid_seeded_error_and_shows_per_task_pairs() -> None:
    rows = _rows()
    result = a4_descriptive(rows, _labels(rows))
    assert [group.denominator for group in result.groups] == [8, 8]
    assert len(result.by_task) == 4
    assert result.claim_scope == "exploratory_exact_registered_prompt_pairs_only"
    assert result.contrast.inferential_status.startswith("blocked_pending")


def test_a4_rejects_unregistered_phrasing() -> None:
    rows = _rows()
    target = next(row for row in rows if row.task_category == "seeded_error")
    rows[rows.index(target)] = replace(target, phrasing="urgent")
    with pytest.raises(SecondaryAnalysisError, match="unknown phrasing"):
        a4_descriptive(rows, _labels(rows))


def test_a3_point_quantities_and_unfrozen_inference_boundary() -> None:
    rows = _rows()
    result = a3_point_estimate(
        rows,
        plan=_plan(rows),
        family_domains={"C01": "D1", "C02": "D2"},
    )
    assert result.windows_failure_rate == pytest.approx(0.4)
    assert result.wsl2_failure_rate == pytest.approx(0.2)
    assert result.linux_failure_rate == pytest.approx(0.1)
    assert result.distance_difference == pytest.approx(0.1)
    assert result.point_ordering_holds
    assert result.status == "not_applicable_nonconfirmatory_configuration_roster"


def test_a3_hard_gap_guardrail_is_applied_without_inference() -> None:
    rows = [
        replace(row, failed=False, binary_success_final=True)
        if row.task_category == "capability"
        else row
        for row in _rows()
    ]
    result = a3_point_estimate(
        rows,
        plan=_plan(rows),
        family_domains={"C01": "D1", "C02": "D2"},
    )
    assert result.status == "not_applicable_nonconfirmatory_configuration_roster"


def test_a3_rejects_count_preserving_cell_identity_swap() -> None:
    rows = _rows()
    first = next(row for row in rows if row.env_id == "windows_powershell")
    second = next(row for row in rows if row.env_id == "windows_wsl2")
    mutated = list(rows)
    mutated[mutated.index(first)] = replace(first, cell_id=second.cell_id)
    mutated[mutated.index(second)] = replace(second, cell_id=first.cell_id)
    with pytest.raises(SecondaryAnalysisError, match="identity differs"):
        a3_point_estimate(
            mutated,
            plan=_plan(rows),
            family_domains={"C01": "D1", "C02": "D2"},
        )


def test_a3_fixed_block_bootstrap_supports_strong_registered_ordering() -> None:
    rows = _a3_confirmatory_rows("supported")
    arguments = {
        "plan": _plan(rows),
        "family_domains": {"C01": "D1", "C02": "D2"},
    }
    first = a3_fixed_block_inference(rows, **arguments)
    second = a3_fixed_block_inference(rows, **arguments)
    assert first == second
    assert first.status == "supported"
    assert first.a3a_ordering_supported is True
    assert first.a3b_closer_to_linux_supported is True
    assert first.windows_minus_wsl2_lower > 0
    assert first.wsl2_minus_linux_lower > 0
    assert first.distance_difference_lower > 0
    assert first.bootstrap_resamples == 10_000
    assert first.bootstrap_seed == 20260525
    assert len(first.per_configuration) == 7
    assert all(result.bh_reject for result in first.per_configuration)
    minimum_monte_carlo_p = 1 / (first.bootstrap_resamples + 1)
    assert all(
        result.windows_minus_wsl2_one_sided_p >= minimum_monte_carlo_p
        and result.wsl2_minus_linux_one_sided_p >= minimum_monte_carlo_p
        and result.intersection_union_p >= minimum_monte_carlo_p
        for result in first.per_configuration
    )


def test_a3_fixed_block_bootstrap_rejects_wrong_ordering() -> None:
    rows = _a3_confirmatory_rows("rejected")
    result = a3_point_estimate(
        rows,
        plan=_plan(rows),
        family_domains={"C01": "D1", "C02": "D2"},
    )
    assert result.status == "rejected"
    assert result.a3a_ordering_supported is False
    assert result.wsl2_minus_linux_lower < 0


def test_a3_gap_guardrail_overrides_bootstrap_decision() -> None:
    rows = _a3_confirmatory_rows("inconclusive")
    result = a3_point_estimate(
        rows,
        plan=_plan(rows),
        family_domains={"C01": "D1", "C02": "D2"},
    )
    assert result.windows_linux_absolute_gap < 0.05
    assert result.status == "inconclusive_windows_linux_gap_below_five_points"


def test_a3_bootstrap_rejects_missing_row_inside_crossing_block() -> None:
    rows = _a3_confirmatory_rows("supported")
    plan = _plan(rows)
    missing = rows[1:]
    with pytest.raises(SecondaryAnalysisError, match="cell counts differ|exact config/environment"):
        a3_point_estimate(
            missing,
            plan=plan,
            family_domains={"C01": "D1", "C02": "D2"},
        )


def test_a3_bootstrap_rejects_count_preserving_misaligned_block() -> None:
    rows = _a3_confirmatory_rows("supported")
    plan = _plan(rows)
    first = next(row for row in rows if row.valid_slot_index == 0)
    mutated = list(rows)
    mutated[mutated.index(first)] = replace(first, valid_slot_index=1)
    with pytest.raises(SecondaryAnalysisError, match="duplicates"):
        a3_fixed_block_inference(
            mutated,
            plan=plan,
            family_domains={"C01": "D1", "C02": "D2"},
        )


def test_a2_design_aware_bootstrap_is_deterministic_and_exploratory() -> None:
    rows = _design_rows()
    labels = _designed_labels(rows)
    plan = _plan(rows)
    first = a2_design_aware(rows, labels, plan=plan)
    second = a2_design_aware(rows, labels, plan=plan)
    assert first == second
    assert first.status == "exploratory_design_aware_complete"
    assert first.bootstrap is not None
    assert first.bootstrap.seed == 20260526
    assert first.bootstrap.resamples == 10_000
    assert first.bootstrap.first_rate.defined_draws == 10_000
    assert first.contrast.inferential_status == (
        "exploratory_no_support_reject_threshold"
    )


def test_a2_design_aware_enforces_sparse_and_zero_failure_branches() -> None:
    base = _design_rows()
    cleared = [replace(row, failed=False, binary_success_final=True) for row in base]
    selected = []
    counts = {"windows_powershell": 0, "linux_native": 0}
    for row in cleared:
        if row.env_id in counts and counts[row.env_id] < 5:
            row = replace(row, failed=True, binary_success_final=False)
            counts[row.env_id] += 1
        selected.append(row)
    sparse = a2_design_aware(
        selected, _designed_labels(selected), plan=_plan(selected)
    )
    assert sparse.status == "descriptive_sparse_below_ten_failures_per_context"
    assert [group.denominator for group in sparse.groups] == [5, 5]

    zero_rows = [
        replace(row, failed=False, binary_success_final=True)
        if row.env_id == "linux_native"
        else row
        for row in base
    ]
    zero = a2_design_aware(
        zero_rows, _designed_labels(zero_rows), plan=_plan(zero_rows)
    )
    assert zero.status == "not_estimable_zero_failure_denominator"
    assert zero.groups[1].denominator == 0


def test_a2_missing_primary_label_has_observed_estimate_and_worst_best_bounds() -> None:
    rows = _design_rows()
    labels = _designed_labels(rows)
    target = next(
        row
        for row in rows
        if row.failed is True and row.env_id == "windows_powershell"
    )
    labels[target.identity] = CoderJoinResult(
        status="missing",
        raw_code=None,
        final_code=None,
        evidence_class="invalid_or_missing",
        applied_rule="coder_label_missing",
    )
    result = a2_design_aware(rows, labels, plan=_plan(rows))
    assert result.status == "measurement_incomplete_primary_labels"
    assert result.groups[0].de_rate is not None
    assert result.missing_label_bounds is not None
    assert (
        result.missing_label_bounds.first_rate_upper
        > result.missing_label_bounds.first_rate_lower
    )
    assert result.bootstrap is not None


def test_a4_design_aware_reports_exact_prompt_set_and_task_heterogeneity() -> None:
    rows = _design_rows()
    labels = _designed_labels(rows)
    plan = _plan(rows)
    first = a4_design_aware(rows, labels, plan=plan)
    second = a4_design_aware(rows, labels, plan=plan)
    assert first == second
    assert first.status == "exploratory_design_aware_complete"
    assert first.bootstrap is not None
    assert first.bootstrap.seed == 20260527
    assert first.groups[1].de_rate > first.groups[0].de_rate
    assert len(first.task_contrasts) == 2
    assert all(
        contrast.inferential_status == "descriptive_task_heterogeneity_only"
        for contrast in first.task_contrasts
    )


def test_a4_missing_label_bounds_and_misaligned_block_rejection() -> None:
    rows = _design_rows()
    labels = _designed_labels(rows)
    target = next(row for row in rows if row.task_category == "seeded_error")
    labels[target.identity] = CoderJoinResult(
        status="missing",
        raw_code=None,
        final_code=None,
        evidence_class="invalid_or_missing",
        applied_rule="coder_label_missing",
    )
    result = a4_design_aware(rows, labels, plan=_plan(rows))
    assert result.status == "measurement_incomplete_primary_labels"
    assert result.missing_label_bounds is not None
    assert (
        result.missing_label_bounds.first_rate_upper
        > result.missing_label_bounds.first_rate_lower
    )

    plan = _plan(rows)
    mutated = list(rows)
    mutated[mutated.index(target)] = replace(target, valid_slot_index=1)
    with pytest.raises(SecondaryAnalysisError, match="duplicates"):
        a4_design_aware(mutated, _designed_labels(mutated), plan=plan)


def test_synthetic_end_to_end_report_is_json_safe_and_bounded() -> None:
    rows = _rows()
    plan = _plan(rows)
    report = build_v2_analysis_report(
        rows,
        _labels(rows),
        plan=plan,
        h1=_h1(rows),
        family_domains={"C01": "D1", "C02": "D2"},
    )
    payload = report.as_dict()
    tables = report_tables(report)
    assert payload["reporting_status"] == "nonconfirmatory_descriptive_only"
    assert len(payload["blocked_predata_components"]) == 0
    assert tables["a1"][0]["decision"] == "decision_relevant_context_penalty"
    assert len(tables["a4_task"]) == 4


def test_report_rejects_missing_or_extra_label_roster() -> None:
    rows = _rows()
    labels = _labels(rows)
    labels.pop(rows[0].identity)
    with pytest.raises(SecondaryAnalysisError, match="primary-label roster differs"):
        build_v2_analysis_report(
            rows,
            labels,
            plan=_plan(rows),
            h1=_h1(rows),
            family_domains={"C01": "D1", "C02": "D2"},
        )


def test_report_rejects_complete_labels_for_incomplete_analysis_roster() -> None:
    rows = _rows()
    plan = _plan(rows)
    rows = rows[1:]
    with pytest.raises(SecondaryAnalysisError, match="complete plan"):
        build_v2_analysis_report(
            rows,
            _labels(rows),
            plan=plan,
            h1=replace(
                _h1(rows),
                trials=sum(
                    row.task_category == "capability"
                    and row.env_id in {"windows_powershell", "linux_native"}
                    for row in rows
                ),
            ),
            family_domains={"C01": "D1", "C02": "D2"},
        )


def test_report_rejects_h1_from_another_roster() -> None:
    rows = _rows()
    with pytest.raises(SecondaryAnalysisError, match="H1 result trial count"):
        build_v2_analysis_report(
            rows,
            _labels(rows),
            plan=_plan(rows),
            h1=replace(_h1(rows), trials=1),
            family_domains={"C01": "D1", "C02": "D2"},
        )


def test_real_v2_plan_traverses_candidate_reporting_boundary(
    frozen_runtime_binding,
) -> None:
    plan = build_plan(V2_PILOT_PHASE, runtime_binding=frozen_runtime_binding)
    cells = {cell.cell_id: cell for cell in plan.cells}
    rows = []
    for slot in plan.execution_slots or ():
        cell = cells[slot.cell_id]
        category = "capability" if cell.task_id.startswith("C") else "seeded_error"
        failed = (
            category == "seeded_error"
            or (
                cell.env_id == "windows_powershell"
                and int(cell.family_id[1:]) <= 2
            )
        )
        attempt_id = hashlib.sha256(
            f"{cell.cell_id}:{slot.valid_slot_index}".encode("utf-8")
        ).hexdigest()[:32]
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
                task_category=category,
                trial_index=slot.valid_slot_index,
                valid_slot_index=slot.valid_slot_index,
                attempt_id=attempt_id,
                valid_analysis_trial=True,
                binary_success_final=not failed,
                failed=failed,
                transcript_analysis_eligible=True,
                agy_cwd_status=None,
                execution_position=slot.position,
                collection_epoch=slot.position // 180,
            )
        )
    labels = _labels(rows)
    h1 = finite_roster_h1_candidate(
        rows, plan=plan, expected_configurations=("CFG1", "CFG2")
    )

    report = build_v2_analysis_report(rows, labels, plan=plan, h1=h1)

    assert report.plan_digest == plan.digest
    assert report.h1.trials == 144
    assert report.a3.trials == 216
    assert sum(group.denominator for group in report.a4.groups) == 360
