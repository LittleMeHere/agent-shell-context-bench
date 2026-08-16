from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from analysis.d013_task_bank import TaskBankError, validate_task_bank
from analysis.task_predicate_authority import (
    PredicateAuthorityError,
    validate_predicate_authority,
)


ROOT = Path(__file__).resolve().parents[1]
SLATE = ROOT / "config" / "v2-family-slate.accepted.json"
TASKS = ROOT / "tasks" / "v2"
ALL_TASKS = ROOT / "tasks"
AUTHORITY = ROOT / "config" / "v2-legacy-predicate-authority.json"


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


def test_all_50_tasks_have_one_digest_bound_executable_authority() -> None:
    evidence = validate_predicate_authority(
        tasks_root=ALL_TASKS,
        overlay_path=AUTHORITY,
    )
    assert evidence.task_count == 50
    assert evidence.inline_canonical_tasks == 36
    assert evidence.legacy_overlay_tasks == 14
    assert evidence.executable_check_count > 200
    assert len(evidence.authority_digest) == 64


def test_authority_overlay_rejects_unmapped_legacy_clause(tmp_path: Path) -> None:
    raw = json.loads(AUTHORITY.read_text(encoding="utf-8"))
    raw["legacy_tasks"][0]["clause_dispositions"].pop("allowed_final_files")
    candidate = tmp_path / "authority.json"
    candidate.write_text(json.dumps(raw), encoding="utf-8")

    with pytest.raises(PredicateAuthorityError, match="clauses are unmapped"):
        validate_predicate_authority(tasks_root=ALL_TASKS, overlay_path=candidate)


def test_authority_overlay_rejects_unclaimed_executable_check(tmp_path: Path) -> None:
    raw = json.loads(AUTHORITY.read_text(encoding="utf-8"))
    raw["legacy_tasks"][0]["clause_dispositions"]["required_final_files"][
        "check_indices"
    ].remove(0)
    candidate = tmp_path / "authority.json"
    candidate.write_text(json.dumps(raw), encoding="utf-8")

    with pytest.raises(PredicateAuthorityError, match="checks are not clause-mapped"):
        validate_predicate_authority(tasks_root=ALL_TASKS, overlay_path=candidate)


def test_authority_overlay_rejects_legacy_task_or_check_drift(tmp_path: Path) -> None:
    candidate_tasks = tmp_path / "tasks"
    shutil.copytree(ALL_TASKS, candidate_tasks)
    path = candidate_tasks / "trap" / "T01_ampersand_chain.yaml"
    path.write_text(path.read_text(encoding="utf-8") + "\n# drift\n", encoding="utf-8")

    with pytest.raises(PredicateAuthorityError, match="task_sha256 drift"):
        validate_predicate_authority(
            tasks_root=candidate_tasks,
            overlay_path=AUTHORITY,
        )


def test_authority_rejects_inline_timeout_or_manual_role_drift(tmp_path: Path) -> None:
    candidate_tasks = tmp_path / "tasks"
    shutil.copytree(ALL_TASKS, candidate_tasks)
    path = next((candidate_tasks / "v2").glob("C01-I01_*.yaml"))
    text = path.read_text(encoding="utf-8").replace(
        'manual_rubric_role: "excluded_from_h1"',
        'manual_rubric_role: "may_change_h1"',
    )
    path.write_text(text, encoding="utf-8")

    with pytest.raises(PredicateAuthorityError, match="lacks overlay"):
        validate_predicate_authority(
            tasks_root=candidate_tasks,
            overlay_path=AUTHORITY,
        )
