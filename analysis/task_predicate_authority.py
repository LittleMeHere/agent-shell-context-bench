"""V2 executable-predicate authority across all registered task YAMLs.

The 36 new V2 capability instances carry the canonical declaration inline.
The 14 pre-registered historical YAMLs are frozen, so a digest-bound external
overlay maps every legacy top-level predicate clause to executable checks,
the common outcome rule, an explicit H2/H4-only surface, or non-outcome
historical metadata without editing those task bytes.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from harness.checks import registered_check_types
from harness.runner import load_task

from .d013_task_bank import _CANONICAL_H1_PREDICATE


class PredicateAuthorityError(ValueError):
    pass


@dataclass(frozen=True)
class PredicateAuthorityEvidence:
    task_count: int
    inline_canonical_tasks: int
    legacy_overlay_tasks: int
    executable_check_count: int
    authority_digest: str


_ROLES = {
    "executable_checks",
    "executable_checks_and_common_outcome_rule",
    "common_outcome_rule",
    "h2_h4_only",
    "historical_metadata",
    "vacuous_h1_clause",
}


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _load_object(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PredicateAuthorityError(f"cannot read {label}: {path}") from exc
    if not isinstance(value, dict):
        raise PredicateAuthorityError(f"{label} must be a JSON object")
    return value


def _validate_overlay_entry(
    *,
    task_path: Path,
    task: Mapping[str, object],
    entry: Mapping[str, object],
) -> int:
    task_id = str(task.get("id"))
    expected_fields = {
        "task_id",
        "task_sha256",
        "predicate_sha256",
        "success_checks_sha256",
        "clause_dispositions",
        "measures",
        "does_not_measure",
    }
    if set(entry) != expected_fields:
        raise PredicateAuthorityError(f"{task_id}: overlay fields are not closed")
    if entry.get("task_id") != task_id:
        raise PredicateAuthorityError(f"{task_id}: overlay task ID mismatch")
    checks = task.get("success_checks")
    predicate = task.get("binary_success_predicate")
    if not isinstance(checks, list) or not checks or not isinstance(predicate, dict):
        raise PredicateAuthorityError(f"{task_id}: task predicate/checks are malformed")
    expected_digests = {
        "task_sha256": hashlib.sha256(task_path.read_bytes()).hexdigest(),
        "predicate_sha256": _digest(predicate),
        "success_checks_sha256": _digest(checks),
    }
    for field, expected in expected_digests.items():
        if entry.get(field) != expected:
            raise PredicateAuthorityError(f"{task_id}: {field} drift")

    dispositions = entry.get("clause_dispositions")
    if not isinstance(dispositions, dict) or set(dispositions) != set(predicate):
        raise PredicateAuthorityError(f"{task_id}: legacy predicate clauses are unmapped")
    claimed: set[int] = set()
    for clause, raw in dispositions.items():
        if not isinstance(raw, dict) or set(raw) - {"role", "check_indices"}:
            raise PredicateAuthorityError(f"{task_id}.{clause}: disposition is malformed")
        role = raw.get("role")
        if role not in _ROLES:
            raise PredicateAuthorityError(f"{task_id}.{clause}: unknown disposition role")
        indices = raw.get("check_indices", [])
        if not isinstance(indices, list) or any(
            isinstance(index, bool) or not isinstance(index, int) for index in indices
        ):
            raise PredicateAuthorityError(f"{task_id}.{clause}: check indices are invalid")
        executable_role = role in {
            "executable_checks",
            "executable_checks_and_common_outcome_rule",
        }
        if executable_role and not indices:
            raise PredicateAuthorityError(f"{task_id}.{clause}: executable clause is unmapped")
        if not executable_role and indices:
            raise PredicateAuthorityError(
                f"{task_id}.{clause}: non-executable role claims checks"
            )
        if any(index < 0 or index >= len(checks) for index in indices):
            raise PredicateAuthorityError(f"{task_id}.{clause}: check index is out of range")
        if len(indices) != len(set(indices)):
            raise PredicateAuthorityError(f"{task_id}.{clause}: check index is duplicated")
        claimed.update(indices)
    expected_indices = set(range(len(checks)))
    if claimed != expected_indices:
        missing = sorted(expected_indices - claimed)
        raise PredicateAuthorityError(
            f"{task_id}: executable checks are not clause-mapped: {missing}"
        )
    for field in ("measures", "does_not_measure"):
        values = entry.get(field)
        if not isinstance(values, list) or not values or any(
            not isinstance(value, str) or not value.strip() for value in values
        ):
            raise PredicateAuthorityError(f"{task_id}: {field} review is empty")
    return len(checks)


def validate_predicate_authority(
    *,
    tasks_root: Path,
    overlay_path: Path,
) -> PredicateAuthorityEvidence:
    """Validate one outcome authority and a construct review for every task."""

    overlay = _load_object(overlay_path, "predicate authority overlay")
    if set(overlay) != {"schema_version", "authority", "legacy_tasks"}:
        raise PredicateAuthorityError("predicate authority overlay fields are not closed")
    if overlay.get("schema_version") != "1.0.0":
        raise PredicateAuthorityError("unsupported predicate authority schema")
    if overlay.get("authority") != _CANONICAL_H1_PREDICATE:
        raise PredicateAuthorityError("overlay does not declare the canonical H1 authority")
    entries = overlay.get("legacy_tasks")
    if not isinstance(entries, list):
        raise PredicateAuthorityError("legacy_tasks must be an array")
    by_id: dict[str, Mapping[str, object]] = {}
    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get("task_id"), str):
            raise PredicateAuthorityError("legacy task overlay entry is malformed")
        task_id = str(entry["task_id"])
        if task_id in by_id:
            raise PredicateAuthorityError(f"duplicate overlay task {task_id}")
        by_id[task_id] = entry

    task_paths = sorted(tasks_root.rglob("*.yaml"))
    if len(task_paths) != 50:
        raise PredicateAuthorityError(
            f"registered authority requires exactly 50 tasks, found {len(task_paths)}"
        )
    observed: set[str] = set()
    inline = 0
    check_count = 0
    known_checks = registered_check_types()
    for path in task_paths:
        task = load_task(path)
        task_id = str(task.get("id"))
        if task_id in observed:
            raise PredicateAuthorityError(f"duplicate task ID {task_id}")
        observed.add(task_id)
        checks = task.get("success_checks")
        if not isinstance(checks, list) or not checks or any(
            not isinstance(check, dict) for check in checks
        ):
            raise PredicateAuthorityError(f"{task_id}: success_checks are malformed")
        unknown = sorted(
            str(check.get("type", ""))
            for check in checks
            if str(check.get("type", "")) not in known_checks
        )
        if unknown:
            raise PredicateAuthorityError(f"{task_id}: unknown check types {unknown}")
        if task.get("binary_success_predicate") == _CANONICAL_H1_PREDICATE:
            if task_id in by_id:
                raise PredicateAuthorityError(
                    f"{task_id}: canonical inline task has a conflicting overlay"
                )
            inline += 1
            check_count += len(checks)
        else:
            entry = by_id.get(task_id)
            if entry is None:
                raise PredicateAuthorityError(f"{task_id}: legacy predicate lacks overlay")
            check_count += _validate_overlay_entry(
                task_path=path,
                task=task,
                entry=entry,
            )
    unused = sorted(set(by_id) - observed)
    if unused:
        raise PredicateAuthorityError(f"overlay contains unknown tasks: {unused}")
    return PredicateAuthorityEvidence(
        task_count=len(task_paths),
        inline_canonical_tasks=inline,
        legacy_overlay_tasks=len(by_id),
        executable_check_count=check_count,
        authority_digest=_digest(overlay),
    )
