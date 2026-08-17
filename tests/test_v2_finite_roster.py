from __future__ import annotations

import dataclasses

import numpy as np
import pytest

from analysis.v2_analysis_dataset import AnalysisDatasetError, AnalysisTrial
from analysis.v2_finite_roster import (
    bonferroni_clopper_pearson_linear_interval,
    finite_roster_epoch_sensitivity,
    finite_roster_h1_candidate,
    mover_clopper_pearson_linear_interval,
    mover_wilson_linear_interval,
)


def test_mover_matches_independent_linear_combination_oracle() -> None:
    events = np.asarray([0, 2, 4, 3], dtype=np.int64)
    totals = np.asarray([3, 4, 5, 6], dtype=np.int64)
    coefficients = np.asarray([0.25, 0.25, -0.25, -0.25])
    result = mover_wilson_linear_interval(events, totals, coefficients)

    z = 1.959963984540054
    proportions = events / totals
    lower = []
    upper = []
    for count, total in zip(events, totals, strict=True):
        denominator = 1 + z**2 / total
        center = (count / total + z**2 / (2 * total)) / denominator
        half = z * (
            count / total * (1 - count / total) / total
            + z**2 / (4 * total**2)
        ) ** 0.5 / denominator
        lower.append(max(0.0, center - half))
        upper.append(min(1.0, center + half))
    components = coefficients * proportions
    lows = np.minimum(coefficients * lower, coefficients * upper)
    highs = np.maximum(coefficients * lower, coefficients * upper)
    assert result.estimate == pytest.approx(float(sum(components)))
    assert result.lower == pytest.approx(
        result.estimate - float(sum((components - lows) ** 2)) ** 0.5
    )
    assert result.upper == pytest.approx(
        result.estimate + float(sum((highs - components) ** 2)) ** 0.5
    )


def test_exact_fallback_handles_singleton_boundary_cells() -> None:
    result = bonferroni_clopper_pearson_linear_interval(
        [0, 1, 1, 0], [1, 1, 1, 1], [0.5, 0.5, -0.5, -0.5]
    )
    assert result.estimate == 0.0
    assert result.lower < 0.0 < result.upper
    assert result.minimum_cell_n == 1
    assert result.method == "bonferroni_clopper_pearson_fallback"


def test_clopper_pearson_mover_is_wider_than_falsified_wilson_comparator() -> None:
    arguments = ([0, 2, 4, 3], [3, 4, 5, 6], [0.25, 0.25, -0.25, -0.25])
    wilson = mover_wilson_linear_interval(*arguments)
    candidate = mover_clopper_pearson_linear_interval(*arguments)
    assert candidate.estimate == pytest.approx(wilson.estimate)
    assert candidate.lower < wilson.lower
    assert candidate.upper > wilson.upper


def _trial(
    *,
    env: str,
    family: str,
    instance: str,
    index: int,
    failed: bool,
    config: str = "CFG1",
) -> AnalysisTrial:
    return AnalysisTrial(
        plan_digest="a" * 64,
        cell_id=f"{env}:{family}:{instance}:{index}",
        config_id=config,
        env_id=env,
        agent_id="codex",
        model_id="model",
        task_id=f"{family}-{instance}",
        family_id=family,
        instance_id=instance,
        phrasing="canonical",
        task_category="capability",
        trial_index=index,
        valid_slot_index=index,
        attempt_id=f"{index:032x}",
        valid_analysis_trial=True,
        binary_success_final=not failed,
        failed=failed,
        transcript_analysis_eligible=True,
        agy_cwd_status=None,
    )


def _balanced_trials(repetitions: int) -> list[AnalysisTrial]:
    rows = []
    index = 0
    for env in ("windows_powershell", "linux_native"):
        for config in tuple(f"CFG{number}" for number in range(1, 8)):
            for family in ("C01", "C02"):
                for instance in ("I01", "I02"):
                    for repetition in range(repetitions):
                        failed = env == "windows_powershell" and repetition == 0
                        rows.append(
                            _trial(
                                env=env,
                                family=family,
                                instance=instance,
                                index=index,
                                failed=failed,
                                config=config,
                            )
                        )
                        index += 1
    return rows


def test_h1_candidate_uses_mover_at_three_per_leaf() -> None:
    result = finite_roster_h1_candidate(
        _balanced_trials(3), family_domains={"C01": "A", "C02": "B"}
    )
    assert result.windows_failure_rate == pytest.approx(1 / 3)
    assert result.linux_failure_rate == 0.0
    assert result.risk_difference == pytest.approx(1 / 3)
    assert result.interval_method == "mover_clopper_pearson_fixed_roster_candidate"
    assert not result.fallback_used
    assert result.minimum_cell_n == 3
    assert result.cells_per_context == 28


@pytest.mark.parametrize("mutation", ["missing", "extra"])
def test_h1_candidate_rejects_configuration_roster_drift(mutation: str) -> None:
    rows = _balanced_trials(3)
    if mutation == "missing":
        rows = [row for row in rows if row.config_id != "CFG2"]
        pattern = "missing=\\['CFG2'\\], extra=\\[\\]"
    else:
        rows.extend(
            dataclasses.replace(
                row,
                config_id="CFG8",
                cell_id=f"{row.cell_id}:CFG8",
                attempt_id=f"8{row.attempt_id[1:]}",
            )
            for row in rows
            if row.config_id == "CFG1"
        )
        pattern = "missing=\\[\\], extra=\\['CFG8'\\]"
    with pytest.raises(AnalysisDatasetError, match=pattern):
        finite_roster_h1_candidate(
            rows,
            family_domains={"C01": "A", "C02": "B"},
        )


def test_h1_candidate_fails_safe_to_exact_envelope_for_singletons() -> None:
    result = finite_roster_h1_candidate(
        _balanced_trials(1), family_domains={"C01": "A", "C02": "B"}
    )
    assert result.fallback_used
    assert result.interval_method == "bonferroni_clopper_pearson_fallback"
    assert result.decision == "inconclusive"
    assert result.risk_difference_lower <= result.risk_difference
    assert result.risk_difference <= result.risk_difference_upper


def test_candidate_is_permutation_invariant() -> None:
    rows = _balanced_trials(3)
    expected = finite_roster_h1_candidate(
        rows, family_domains={"C01": "A", "C02": "B"}
    )
    actual = finite_roster_h1_candidate(
        list(reversed(rows)), family_domains={"C01": "A", "C02": "B"}
    )
    assert dataclasses.asdict(actual) == dataclasses.asdict(expected)


def test_epoch_sensitivity_preserves_planned_task_composition() -> None:
    rows = [
        dataclasses.replace(row, collection_epoch=0) for row in _balanced_trials(3)
    ]
    reports = finite_roster_epoch_sensitivity(
        rows,
        family_domains={"C01": "A", "C02": "B"},
    )
    assert [report.status for report in reports] == [
        "estimated",
        "not_applicable_no_capability_trials",
        "not_applicable_no_capability_trials",
        "not_applicable_no_capability_trials",
    ]
    assert reports[0].result is not None
    assert reports[0].result.risk_difference == pytest.approx(1 / 3)
    assert reports[1].result is None


def test_epoch_sensitivity_fails_closed_on_partial_crossing() -> None:
    rows = [
        dataclasses.replace(row, collection_epoch=0)
        for row in _balanced_trials(3)
        if not (row.env_id == "linux_native" and row.family_id == "C02")
    ]
    reports = finite_roster_epoch_sensitivity(
        rows,
        family_domains={"C01": "A", "C02": "B"},
        expected_epochs=(0,),
    )
    assert reports[0].status == "not_estimable_incomplete_crossing"
    assert reports[0].result is None
    assert "complete crossing" in str(reports[0].reason)


def test_epoch_sensitivity_rejects_unregistered_epoch() -> None:
    rows = [
        dataclasses.replace(row, collection_epoch=4) for row in _balanced_trials(3)
    ]
    with pytest.raises(AnalysisDatasetError, match="unexpected collection epochs"):
        finite_roster_epoch_sensitivity(
            rows,
            family_domains={"C01": "A", "C02": "B"},
        )
