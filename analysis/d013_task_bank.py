"""Structural qualification evidence for the accepted D-013 V2 task bank.

This validator binds the 36 authored YAML instances to the accepted family
slate and checks minimum fail-closed predicate structure. It does not claim
cross-host equivalence, human solvability, alternate-solution validity, or
difficulty calibration; those remain Q1-Q3 evidence.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from harness.checks import registered_check_types
from harness.runner import load_task

from .d013_family_slate import load_family_slate


class TaskBankError(ValueError):
    pass


@dataclass(frozen=True)
class TaskBankEvidence:
    task_count: int
    family_count: int
    instance_sha256: tuple[tuple[str, str], ...]
    bank_digest: str


_PATH_ASSERTIONS = {
    "file_exists",
    "file_is_empty",
    "file_unchanged",
    "python_parses",
    "file_contains_substring_count",
    "file_content_equals",
    "json_content_equals",
}

_CANONICAL_H1_PREDICATE = {
    "authority": "ordered_success_checks_and_common_outcome_rule",
    "aggregation": "all_success_checks_must_pass",
    "timeout_policy": "timeout_or_incomplete_is_failure",
    "manual_rubric_role": "excluded_from_h1",
}


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


def _has_exact_scope_check(checks: list[dict]) -> bool:
    if any(check.get("type") == "no_extra_files" for check in checks):
        return True
    return any(
        check.get("type") == "environment_command"
        and isinstance(check.get("argv"), list)
        and check["argv"][:3] == ["git", "status", "--porcelain=v1"]
        and "--untracked-files=all" in check["argv"]
        for check in checks
    )


def validate_task_bank(*, slate_path: Path, tasks_root: Path) -> TaskBankEvidence:
    slate = load_family_slate(slate_path)
    paths = sorted(tasks_root.glob("*.yaml"))
    if len(paths) != 36:
        raise TaskBankError(f"V2 bank requires exactly 36 YAMLs, found {len(paths)}")

    expected_ids = {
        f"{family_id}-I{instance:02d}"
        for family_id in slate.family_ids
        for instance in range(1, 4)
    }
    observed_ids: set[str] = set()
    digests: list[tuple[str, str]] = []
    for path in paths:
        try:
            task = load_task(path)
        except (OSError, ValueError) as exc:
            raise TaskBankError(str(exc)) from exc
        task_id = str(task["id"])
        if task_id in observed_ids:
            raise TaskBankError(f"duplicate V2 task id {task_id}")
        observed_ids.add(task_id)
        if task.get("category") != "capability" or "prompt" not in task:
            raise TaskBankError(f"{task_id}: V2 instances must be capability tasks")
        predicate = task.get("binary_success_predicate")
        if predicate != _CANONICAL_H1_PREDICATE:
            raise TaskBankError(
                f"{task_id}: binary_success_predicate must exactly delegate "
                "to ordered success_checks and the common outcome rule"
            )
        checks = task.get("success_checks")
        if not isinstance(checks, list) or not checks or any(
            not isinstance(check, dict) for check in checks
        ):
            raise TaskBankError(f"{task_id}: success_checks must be non-empty objects")
        unknown_checks = sorted(
            {
                str(check.get("type", ""))
                for check in checks
                if str(check.get("type", "")) not in registered_check_types()
            }
        )
        if unknown_checks:
            raise TaskBankError(
                f"{task_id}: unknown executable H1 checks: {unknown_checks}"
            )
        if not _has_exact_scope_check(checks):
            raise TaskBankError(f"{task_id}: no exact extra-artifact scope check")
        preconditions = task.get("preconditions")
        initial_files = (
            preconditions.get("initial_files", [])
            if isinstance(preconditions, dict)
            else None
        )
        if not isinstance(initial_files, list):
            raise TaskBankError(f"{task_id}: initial_files must be a list")
        initial_paths = {
            entry.get("path")
            for entry in initial_files
            if isinstance(entry, dict)
        }
        if None in initial_paths or len(initial_paths) != len(initial_files):
            raise TaskBankError(f"{task_id}: initial file paths must be unique")
        asserted_paths = {
            check.get("path")
            for check in checks
            if check.get("type") in _PATH_ASSERTIONS
        }
        if not initial_paths.issubset(asserted_paths):
            missing = sorted(initial_paths - asserted_paths)
            raise TaskBankError(
                f"{task_id}: initial files lack post-run assertions: {missing}"
            )
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        digests.append((task_id, digest))

    if observed_ids != expected_ids:
        raise TaskBankError(
            "authored task IDs differ from the accepted 12x3 instance roster"
        )
    if len({digest for _, digest in digests}) != 36:
        raise TaskBankError("every V2 instance must have distinct frozen bytes")
    ordered = tuple(sorted(digests))
    bank_digest = hashlib.sha256(
        _canonical_json(ordered).encode("utf-8")
    ).hexdigest()
    return TaskBankEvidence(36, 12, ordered, bank_digest)
