"""Outcome-blind fixtures for the D-011 agy H1 construction candidate."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from harness.outcomes import construct_agy_outcome_evidence
from harness.runner import _agy_trace_unavailable_is_outcome_determinative


_TASK_IDS = tuple(sorted(
    yaml.safe_load(path.read_text(encoding="utf-8"))["id"]
    for path in (Path(__file__).resolve().parents[1] / "tasks").rglob("*.yaml")
))
_EXPECTED_TASK_IDS = {
    "C01", "C02", "C03", "C04", "C05",
    *(f"T{index:02d}" for index in range(1, 10)),
    *(
        f"C{family:02d}-I{instance:02d}"
        for family in range(1, 13)
        for instance in range(1, 4)
    ),
}
assert set(_TASK_IDS) == _EXPECTED_TASK_IDS
assert len(_TASK_IDS) == 50


@pytest.mark.parametrize("task_id", _TASK_IDS)
@pytest.mark.parametrize(
    ("brain_status", "cwd_tags", "cwd_status", "eligible"),
    [
        ("present", ["cwd_in_sandbox"], "all_in_sandbox", True),
        ("present", ["cwd_in_agy_scratch"], "none_in_sandbox", True),
        (
            "present",
            ["cwd_in_sandbox", "cwd_elsewhere"],
            "mixed",
            True,
        ),
        # Task completion can occur through non-shell file/edit tools.
        ("present", [], "no_shell_commands", True),
        # Missing brain evidence blocks transcript analyses but not an
        # otherwise observable task-state H1 result.
        ("missing", None, "unmeasurable", False),
        ("parse_error", None, "unmeasurable", False),
        ("ambiguous", None, "unmeasurable", False),
    ],
)
def test_all_tasks_share_h1_across_cwd_and_transcript_cases(
    task_id: str,
    brain_status: str,
    cwd_tags: list[str] | None,
    cwd_status: str,
    eligible: bool,
):
    evidence = construct_agy_outcome_evidence(
        checks_passed=True,
        completed=True,
        timed_out=False,
        brain_status=brain_status,
        cwd_tags=cwd_tags,
    )
    assert task_id  # the parametrization covers every frozen task
    assert evidence.binary_outcome.success is True
    assert evidence.binary_outcome.decision_reason == "checks_passed"
    assert evidence.cwd_status == cwd_status
    assert evidence.transcript_analysis_eligible is eligible
    logged = evidence.as_log_dict()
    assert logged["rule_version"] == "v2-d011-1.0.0"
    assert logged["h1_success"] is True
    assert logged["h1_decision_reason"] == "checks_passed"


@pytest.mark.parametrize("task_id", _TASK_IDS)
def test_all_tasks_keep_failed_predicate_as_h1_failure(task_id: str):
    evidence = construct_agy_outcome_evidence(
        checks_passed=False,
        completed=True,
        timed_out=False,
        brain_status="present",
        cwd_tags=["cwd_in_sandbox"],
    )
    assert task_id
    assert evidence.binary_outcome.success is False
    assert evidence.binary_outcome.decision_reason == "checks_failed"


@pytest.mark.parametrize(
    ("completed", "timed_out", "reason"),
    [
        (False, True, "timed_out"),
        (False, False, "incomplete"),
        (True, True, "timed_out"),
    ],
)
def test_completion_precedence_is_shared_with_other_agents(
    completed: bool,
    timed_out: bool,
    reason: str,
):
    evidence = construct_agy_outcome_evidence(
        checks_passed=True,
        completed=completed,
        timed_out=timed_out,
        brain_status="present",
        cwd_tags=[],
    )
    assert evidence.binary_outcome.success is False
    assert evidence.binary_outcome.decision_reason == reason


@pytest.mark.parametrize(
    ("brain_status", "cwd_tags", "message"),
    [
        ("present", None, "requires cwd_tags"),
        ("missing", [], "must be None"),
        ("parse_error", ["cwd_in_sandbox"], "must be None"),
        ("ambiguous", [], "must be None"),
        ("present", ["unknown"], "unknown agy Cwd"),
    ],
)
def test_inconsistent_or_unknown_evidence_fails_closed(
    brain_status: str,
    cwd_tags: list[str] | None,
    message: str,
):
    with pytest.raises(ValueError, match=message):
        construct_agy_outcome_evidence(
            checks_passed=True,
            completed=True,
            timed_out=False,
            brain_status=brain_status,
            cwd_tags=cwd_tags,
        )


@pytest.mark.parametrize(
    ("completed", "timed_out", "measurement_loss", "expected"),
    [
        (True, False, False, True),
        (False, False, False, False),
        (False, True, False, False),
        (True, True, False, False),
        (True, False, True, False),
    ],
)
def test_unavailable_trace_only_invalidates_outcome_determinative_cases(
    completed: bool, timed_out: bool, measurement_loss: bool, expected: bool
):
    assert _agy_trace_unavailable_is_outcome_determinative(
        brain_status="missing",
        trace_required=True,
        completed=completed,
        timed_out=timed_out,
        agent_induced_measurement_loss=measurement_loss,
    ) is expected
    assert _agy_trace_unavailable_is_outcome_determinative(
        brain_status="missing",
        trace_required=False,
        completed=completed,
        timed_out=timed_out,
        agent_induced_measurement_loss=measurement_loss,
    ) is False
