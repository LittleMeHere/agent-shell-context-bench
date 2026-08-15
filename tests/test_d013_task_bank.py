from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from analysis.d013_task_bank import TaskBankError, validate_task_bank


ROOT = Path(__file__).resolve().parents[1]
SLATE = ROOT / "config" / "v2-family-slate.accepted.json"
TASKS = ROOT / "tasks" / "v2"


def test_authored_bank_binds_exactly_36_distinct_instances():
    evidence = validate_task_bank(slate_path=SLATE, tasks_root=TASKS)
    assert evidence.task_count == 36
    assert evidence.family_count == 12
    assert len(evidence.instance_sha256) == 36
    assert len(evidence.bank_digest) == 64


def test_bank_rejects_instance_without_scope_control(tmp_path: Path):
    candidate = tmp_path / "tasks"
    shutil.copytree(TASKS, candidate)
    path = next(candidate.glob("C01-I01_*.yaml"))
    text = path.read_text(encoding="utf-8").replace(
        "  - {type: no_extra_files}\n",
        "",
    )
    path.write_text(text, encoding="utf-8")
    with pytest.raises(TaskBankError, match="scope check"):
        validate_task_bank(slate_path=SLATE, tasks_root=candidate)


def test_bank_rejects_duplicate_prose_predicate_authority(tmp_path: Path):
    candidate = tmp_path / "tasks"
    shutil.copytree(TASKS, candidate)
    path = next(candidate.glob("C01-I01_*.yaml"))
    text = path.read_text(encoding="utf-8").replace(
        'binary_success_predicate: {authority: "ordered_success_checks_and_common_outcome_rule", aggregation: "all_success_checks_must_pass", timeout_policy: "timeout_or_incomplete_is_failure", manual_rubric_role: "excluded_from_h1"}',
        'binary_success_predicate: {authority: "prose summary", aggregation: "all_success_checks_must_pass", timeout_policy: "timeout_or_incomplete_is_failure", manual_rubric_role: "excluded_from_h1"}',
    )
    path.write_text(text, encoding="utf-8")
    with pytest.raises(TaskBankError, match="exactly delegate"):
        validate_task_bank(slate_path=SLATE, tasks_root=candidate)


def test_bank_rejects_unknown_outcome_changing_check(tmp_path: Path):
    candidate = tmp_path / "tasks"
    shutil.copytree(TASKS, candidate)
    path = next(candidate.glob("C01-I01_*.yaml"))
    text = path.read_text(encoding="utf-8").replace(
        "  - {type: no_extra_files}\n",
        "  - {type: unregistered_manual_judgment}\n  - {type: no_extra_files}\n",
    )
    path.write_text(text, encoding="utf-8")
    with pytest.raises(TaskBankError, match="unknown executable H1 checks"):
        validate_task_bank(slate_path=SLATE, tasks_root=candidate)
