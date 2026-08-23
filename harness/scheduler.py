"""Outcome-blind, resumable scheduler for the pre-registered V1 matrix.

The scheduler automates the existing one-cell runner; it does not change
trial semantics.  A plan is written before the first paid call, then each
cell is run serially until its target number of *valid* immutable records is
present.  An append-only attempt journal is the authoritative progress ledger:
infrastructure-invalid attempts are retained and replaced, while unresolved
started attempts block automatic retry.  The scheduler never reads or prints
``outcome.success``.

Execution is deliberately conservative:

* dry-run/status is the default; a caller must explicitly request execution;
* the real harness refuses to execute from the methodology checkout;
* pilot and confirmatory logs require separate, plan-bound output roots;
* a filesystem lock prevents two schedulers from sharing an output root;
* child stdout is captured so PASS/FAIL is not exposed during collection;
* cells are serial (not concurrent), which also avoids racing agy's global
  settings file and subscription sessions.
"""

from __future__ import annotations

import dataclasses
import base64
import hashlib
import json
import math
import os
import random
import re
import subprocess
import sys
import time
from collections.abc import Callable, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from .attempts import (
    AGENT_INDUCED_MEASUREMENT_LOSS,
    ATTEMPT_DIR_NAME,
    ATTEMPT_SCHEMA_VERSION,
    COMPLETE,
    INVOCATION_START_UNKNOWN_INFRASTRUCTURE_FAILURE,
    POST_INVOCATION_INFRASTRUCTURE_FAILURE,
    PRE_INVOCATION_INFRASTRUCTURE_FAILURE,
    sha256_file as attempt_sha256_file,
)
from .logging.writer import SCHEMA_VERSION as TRIAL_SCHEMA_VERSION
from .runner import load_task
from .schedule_identity import ScheduleIdentity
from .sizing_lock import (
    SizingLock,
    SizingLockError,
    sizing_lock_from_dict,
    validate_commitment_anchor,
)


PLAN_SCHEMA_VERSION = "1.3.0"
LEGACY_PLAN_SCHEMA_VERSION = "1.2.0"
DEFAULT_ORDER_SEED = 20260525
V2_PILOT_EPOCH_BOUNDARIES = (180, 360, 540, 720)

BENCH_ROOT = Path(__file__).resolve().parents[1]
TASKS_ROOT = BENCH_ROOT / "tasks"
DATA_ROOT = BENCH_ROOT / "data"
PRE_REGISTRATION_ROOT = DATA_ROOT / "pre-registration"

BOUND_PLAN_NAME = ".scheduler-plan.json"
BOUND_COMMITMENT_NAME = ".blinding-commitment.json"
LOCK_NAME = ".scheduler.lock"

PILOT_PHASE = "pilot"
V2_PILOT_PHASE = "v2-pilot"
CODEX_MINI_PILOT_PHASE = "codex-mini-pilot"
AGY_MINI_PILOT_PHASE = "agy-mini-pilot"
CONFIRMATORY_PHASE = "confirmatory"
PHASES = (
    PILOT_PHASE,
    V2_PILOT_PHASE,
    CODEX_MINI_PILOT_PHASE,
    AGY_MINI_PILOT_PHASE,
    CONFIRMATORY_PHASE,
)

EXPECTED_CAPABILITY_TASKS = tuple(f"C{i:02d}" for i in range(1, 6))
EXPECTED_SEEDED_ERROR_TASKS = tuple(f"T{i:02d}" for i in range(1, 10))
EXPECTED_V2_CAPABILITY_TASKS = tuple(
    f"C{family:02d}-I{instance:02d}"
    for family in range(1, 13)
    for instance in range(1, 4)
)

ENVIRONMENTS = (
    "windows_powershell",
    "windows_pwsh7",
    "windows_wsl2",
    "linux_native",
    "macos_actions",
)

REQUIRED_CLAUDE_ENV_VARS = (
    "DISABLE_TELEMETRY",
    "DISABLE_ERROR_REPORTING",
    "DISABLE_FEEDBACK_COMMAND",
    "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC",
    "DISABLE_AUTOUPDATER",
)


class ScheduleError(RuntimeError):
    """A fail-closed scheduler validation or execution error."""


def v2_pilot_epoch_for_position(position: int) -> int:
    """Map a registered V2 pilot position to its accepted D-009 epoch."""

    if isinstance(position, bool) or not isinstance(position, int):
        raise TypeError("execution position must be an integer")
    if not 0 <= position < V2_PILOT_EPOCH_BOUNDARIES[-1]:
        raise ValueError("execution position lies outside the V2 pilot roster")
    return next(
        index
        for index, boundary in enumerate(V2_PILOT_EPOCH_BOUNDARIES)
        if position < boundary
    )


@dataclass(frozen=True)
class ModelConfig:
    config_id: str
    agent_id: str
    model_id: str
    expected_cli_version: str | None


@dataclass(frozen=True)
class RuntimeBinding:
    """Frozen V2 runtime identity supplied by the external matrix artifact."""

    matrix_digest: str
    matrix_status: str
    configurations: tuple[ModelConfig, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "matrix_digest": self.matrix_digest,
            "matrix_status": self.matrix_status,
            "configurations": [
                dataclasses.asdict(config) for config in self.configurations
            ],
        }


CLAUDE_CONFIGS = (
    ModelConfig("CFG1", "claude_code", "claude-opus-4-8", "2.1.176"),
    ModelConfig("CFG2", "claude_code", "claude-sonnet-4-6", "2.1.176"),
)
CODEX_CONFIGS = (
    ModelConfig("CFG3", "codex", "gpt-5.5", "0.139.0"),
    ModelConfig("CFG4", "codex", "gpt-5.4-mini", "0.139.0"),
)
AGY_CONFIG_SPECS = (
    ("CFG5", "Gemini 3.1 Pro (High)"),
    ("CFG6", "Gemini 3.5 Flash (Medium)"),
    ("CFG7", "Claude Sonnet 4.6 (Thinking)"),
)

EXPECTED_AGENT_BY_CONFIG = {
    "CFG1": "claude_code",
    "CFG2": "claude_code",
    "CFG3": "codex",
    "CFG4": "codex",
    "CFG5": "agy",
    "CFG6": "agy",
    "CFG7": "agy",
}


@dataclass(frozen=True)
class TaskVariant:
    task_id: str
    family_id: str
    instance_id: str
    instance_sha256: str
    task_path: str
    task_sha256: str
    phrasing: str


@dataclass(frozen=True)
class Cell:
    cell_id: str
    config_id: str
    agent_id: str
    model_id: str
    expected_cli_version: str
    env_id: str
    task_id: str
    family_id: str
    instance_id: str
    instance_sha256: str
    task_path: str
    task_sha256: str
    phrasing: str
    target_valid_trials: int

    @property
    def coordinate(self) -> tuple[str, str, str, str, str]:
        return (
            self.env_id,
            self.agent_id,
            self.model_id,
            self.task_id,
            self.phrasing,
        )


@dataclass(frozen=True)
class ScheduledSlot:
    """One prospectively ordered valid-trial slot in a V2 plan."""

    position: int
    round_index: int
    block_index: int
    valid_slot_index: int
    cell_id: str


@dataclass(frozen=True)
class SchedulePlan:
    schema_version: str
    created_at: str
    phase: str
    order_seed: int
    trial_schema_version: str
    sizing_lock: SizingLock | None
    runtime_binding: RuntimeBinding | None
    execution_slots: tuple[ScheduledSlot, ...] | None
    cells: tuple[Cell, ...]
    digest: str

    def payload(self) -> dict[str, Any]:
        """Hash-bearing content; timestamps do not affect plan identity."""
        payload = {
            "schema_version": self.schema_version,
            "phase": self.phase,
            "order_seed": self.order_seed,
            "trial_schema_version": self.trial_schema_version,
            "sizing_lock": (
                self.sizing_lock.as_dict()
                if self.sizing_lock is not None
                else None
            ),
            "cells": [dataclasses.asdict(cell) for cell in self.cells],
        }
        if self.schema_version != LEGACY_PLAN_SCHEMA_VERSION:
            payload["runtime_binding"] = (
                self.runtime_binding.as_dict()
                if self.runtime_binding is not None
                else None
            )
            payload["execution_slots"] = (
                [dataclasses.asdict(slot) for slot in self.execution_slots]
                if self.execution_slots is not None
                else None
            )
        return payload

    def as_dict(self) -> dict[str, Any]:
        return {
            **self.payload(),
            "created_at": self.created_at,
            "digest": self.digest,
        }


@dataclass(frozen=True)
class CellState:
    valid: int = 0
    invalid: int = 0
    unresolved: int = 0
    next_index: int = 0

    @property
    def attempts(self) -> int:
        return self.valid + self.invalid + self.unresolved


@dataclass(frozen=True)
class ScheduleSummary:
    phase: str
    digest: str
    selected_cells: int
    pending_cells: int
    complete_cells: int
    target_valid_trials: int
    existing_valid_trials: int
    existing_invalid_trials: int
    existing_unresolved_attempts: int
    execution_cells: int
    executed_attempts: int = 0


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


def _digest_payload(payload: Mapping[str, object]) -> str:
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def _find_task(task_id: str) -> Path:
    matches = sorted(TASKS_ROOT.rglob(f"{task_id}_*.yaml")) + sorted(
        TASKS_ROOT.rglob(f"{task_id}.yaml")
    )
    if len(matches) != 1:
        raise ScheduleError(
            f"expected exactly one YAML for {task_id}, found "
            f"{[str(path) for path in matches]}"
        )
    return matches[0]


def task_variants() -> tuple[TaskVariant, ...]:
    """Return the exact frozen V1 roster: 5 + (9 x 2) = 23 variants."""
    variants: list[TaskVariant] = []
    for task_id in (*EXPECTED_CAPABILITY_TASKS, *EXPECTED_SEEDED_ERROR_TASKS):
        path = _find_task(task_id)
        task = load_task(path)
        if task.get("id") != task_id:
            raise ScheduleError(
                f"{path}: expected task id {task_id!r}, found {task.get('id')!r}"
            )
        phrasings = ("default",) if "prompt" in task else ("formal", "colloquial")
        relpath = path.relative_to(BENCH_ROOT).as_posix()
        digest = _sha256_file(path)
        variants.extend(
            TaskVariant(task_id, task_id, "fixed", digest, relpath, digest, phrasing)
            for phrasing in phrasings
        )

    if len(variants) != 23:
        raise ScheduleError(f"V1 requires 23 task variants, found {len(variants)}")
    return tuple(variants)


def v2_task_variants() -> tuple[TaskVariant, ...]:
    """Return the accepted V2 pilot roster: 36 capability + 18 seeded."""
    variants: list[TaskVariant] = []
    for task_id in EXPECTED_V2_CAPABILITY_TASKS:
        matches = sorted((TASKS_ROOT / "v2").glob(f"{task_id}_*.yaml"))
        if len(matches) != 1:
            raise ScheduleError(
                f"expected exactly one V2 YAML for {task_id}, found "
                f"{[str(path) for path in matches]}"
            )
        path = matches[0]
        task = load_task(path)
        if task.get("id") != task_id:
            raise ScheduleError(
                f"{path}: expected task id {task_id!r}, found {task.get('id')!r}"
            )
        digest = _sha256_file(path)
        variants.append(
            TaskVariant(
                task_id=task_id,
                family_id=str(task["family_id"]),
                instance_id=str(task["instance_id"]),
                instance_sha256=digest,
                task_path=path.relative_to(BENCH_ROOT).as_posix(),
                task_sha256=digest,
                phrasing="default",
            )
        )
    for variant in task_variants():
        if variant.task_id in EXPECTED_SEEDED_ERROR_TASKS:
            variants.append(variant)
    if len(variants) != 54:
        raise ScheduleError(f"V2 pilot requires 54 variants, found {len(variants)}")
    return tuple(variants)


def _agy_configs(agy_cli_version: str | None) -> tuple[ModelConfig, ...]:
    if not agy_cli_version or not agy_cli_version.strip():
        raise ScheduleError(
            "agy phases require the exact day-one --agy-cli-version"
        )
    version = agy_cli_version.strip()
    return tuple(
        ModelConfig(config_id, "agy", model_id, version)
        for config_id, model_id in AGY_CONFIG_SPECS
    )


def validate_runtime_binding(binding: RuntimeBinding) -> None:
    """Validate the execution-facing projection of a frozen V2 matrix."""
    if re.fullmatch(r"[0-9a-f]{64}", binding.matrix_digest) is None:
        raise ScheduleError("runtime-matrix digest must be lowercase SHA-256")
    if binding.matrix_status != "frozen":
        raise ScheduleError("V2 collection requires a frozen runtime matrix")
    by_id = {config.config_id: config for config in binding.configurations}
    if len(binding.configurations) != 7 or set(by_id) != set(
        EXPECTED_AGENT_BY_CONFIG
    ):
        raise ScheduleError("runtime binding must contain exactly CFG1 through CFG7")
    for config_id, expected_agent in EXPECTED_AGENT_BY_CONFIG.items():
        config = by_id[config_id]
        if config.agent_id != expected_agent:
            raise ScheduleError(
                f"{config_id} runtime binding must use {expected_agent}"
            )
        if not config.model_id.strip() or not (
            config.expected_cli_version
            and config.expected_cli_version.strip()
        ):
            raise ScheduleError(
                f"{config_id} runtime binding has an empty model/version pin"
            )
    versions_by_agent: dict[str, set[str]] = {}
    for config in binding.configurations:
        versions_by_agent.setdefault(config.agent_id, set()).add(
            str(config.expected_cli_version)
        )
    if any(len(versions) != 1 for versions in versions_by_agent.values()):
        raise ScheduleError(
            "runtime binding assigns multiple CLI versions to one executable"
        )


def _runtime_binding_from_dict(raw: object) -> RuntimeBinding:
    if not isinstance(raw, dict) or set(raw) != {
        "matrix_digest",
        "matrix_status",
        "configurations",
    }:
        raise ScheduleError("malformed runtime binding")
    if not isinstance(raw["configurations"], list):
        raise ScheduleError("runtime binding configurations must be a list")
    configurations: list[ModelConfig] = []
    expected_fields = {
        "config_id",
        "agent_id",
        "model_id",
        "expected_cli_version",
    }
    for item in raw["configurations"]:
        if not isinstance(item, dict) or set(item) != expected_fields:
            raise ScheduleError("malformed runtime configuration")
        if not all(isinstance(item[field], str) for field in expected_fields):
            raise ScheduleError("runtime configuration fields must be strings")
        configurations.append(ModelConfig(**item))
    binding = RuntimeBinding(
        matrix_digest=raw["matrix_digest"],
        matrix_status=raw["matrix_status"],
        configurations=tuple(configurations),
    )
    if not isinstance(binding.matrix_digest, str) or not isinstance(
        binding.matrix_status, str
    ):
        raise ScheduleError("runtime binding digest/status must be strings")
    validate_runtime_binding(binding)
    return binding


def _cell_id(
    config: ModelConfig,
    env_id: str,
    variant: TaskVariant,
) -> str:
    coordinate = {
        "config_id": config.config_id,
        "agent_id": config.agent_id,
        "model_id": config.model_id,
        "env_id": env_id,
        "task_id": variant.task_id,
        "family_id": variant.family_id,
        "instance_id": variant.instance_id,
        "instance_sha256": variant.instance_sha256,
        "phrasing": variant.phrasing,
    }
    return hashlib.sha256(_canonical_json(coordinate).encode("utf-8")).hexdigest()[:16]


def build_blocked_execution_slots(
    cells: Sequence[Cell],
    *,
    seed: int,
) -> tuple[ScheduledSlot, ...]:
    """Build the accepted task-blocked, valid-slot round-robin order."""
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise ScheduleError("execution-slot seed must be an integer")
    by_key: dict[tuple[str, str], list[Cell]] = {}
    for cell in cells:
        by_key.setdefault((cell.task_id, cell.phrasing), []).append(cell)
    result: list[ScheduledSlot] = []
    global_block_index = 0
    for round_index in range(max(cell.target_valid_trials for cell in cells)):
        keys = [
            key
            for key, members in by_key.items()
            if any(cell.target_valid_trials > round_index for cell in members)
        ]
        round_seed = int.from_bytes(
            hashlib.sha256(f"{seed}:{round_index}".encode("utf-8")).digest()[:8],
            "big",
        )
        random.Random(round_seed).shuffle(keys)
        for key in keys:
            eligible = sorted(
                (
                    cell
                    for cell in by_key[key]
                    if cell.target_valid_trials > round_index
                ),
                key=lambda cell: (cell.env_id, cell.config_id, cell.cell_id),
            )
            rotation = global_block_index % len(eligible)
            eligible = eligible[rotation:] + eligible[:rotation]
            for cell in eligible:
                result.append(
                    ScheduledSlot(
                        position=len(result),
                        round_index=round_index,
                        block_index=global_block_index,
                        valid_slot_index=round_index,
                        cell_id=cell.cell_id,
                    )
                )
            global_block_index += 1
    validate_execution_slots(cells, result)
    return tuple(result)


def validate_execution_slots(
    cells: Sequence[Cell],
    slots: Sequence[ScheduledSlot],
) -> None:
    """Reject any slot list that is not the exact registered cell expansion."""
    if [slot.position for slot in slots] != list(range(len(slots))):
        raise ScheduleError("execution-slot positions must be contiguous")
    cell_map = {cell.cell_id: cell for cell in cells}
    expected = {
        (cell.cell_id, valid_slot_index)
        for cell in cells
        for valid_slot_index in range(cell.target_valid_trials)
    }
    observed = {(slot.cell_id, slot.valid_slot_index) for slot in slots}
    if len(slots) != len(expected) or observed != expected:
        raise ScheduleError("execution slots differ from the plan's valid-slot roster")
    for slot in slots:
        cell = cell_map.get(slot.cell_id)
        if cell is None:
            raise ScheduleError(f"execution slot names unknown cell {slot.cell_id}")
        if slot.round_index != slot.valid_slot_index:
            raise ScheduleError("execution-slot round and valid-slot index differ")
        if slot.block_index < 0:
            raise ScheduleError("execution-slot block index must be nonnegative")
    by_block: dict[tuple[int, int], list[Cell]] = {}
    for slot in slots:
        by_block.setdefault((slot.round_index, slot.block_index), []).append(
            cell_map[slot.cell_id]
        )
    for (round_index, _), members in by_block.items():
        task_keys = {(cell.task_id, cell.phrasing) for cell in members}
        if len(task_keys) != 1:
            raise ScheduleError("execution block mixes task/phrasing variants")
        task_key = next(iter(task_keys))
        expected_members = {
            cell.cell_id
            for cell in cells
            if (cell.task_id, cell.phrasing) == task_key
            and cell.target_valid_trials > round_index
        }
        if {cell.cell_id for cell in members} != expected_members:
            raise ScheduleError("execution block is not a complete task crossing")


def build_plan(
    phase: str,
    *,
    sizing_lock: SizingLock | None = None,
    sizing_anchor: Mapping[str, str] | None = None,
    codex_trials_per_cell: int | None = None,
    agy_trials_per_cell: int | None = None,
    agy_cli_version: str | None = None,
    runtime_binding: RuntimeBinding | None = None,
    order_seed: int = DEFAULT_ORDER_SEED,
) -> SchedulePlan:
    """Build and deterministically shuffle a complete pre-outcome plan."""
    if phase not in PHASES:
        raise ScheduleError(f"unknown phase {phase!r}; expected one of {PHASES}")

    variants = task_variants()
    if phase == PILOT_PHASE:
        if any(
            value is not None
            for value in (
                sizing_lock,
                sizing_anchor,
                codex_trials_per_cell,
                agy_trials_per_cell,
                agy_cli_version,
                runtime_binding,
            )
        ):
            raise ScheduleError("pilot is fixed at 2 valid trials in Claude cells")
        configs = CLAUDE_CONFIGS
        targets = {config.config_id: 2 for config in configs}
    elif phase == V2_PILOT_PHASE:
        if any(
            value is not None
            for value in (
                sizing_lock,
                sizing_anchor,
                codex_trials_per_cell,
                agy_trials_per_cell,
                agy_cli_version,
            )
        ):
            raise ScheduleError(
                "V2 pilot is fixed at one trial per capability instance and "
                "two trials per seeded variant in Claude cells"
            )
        if runtime_binding is None:
            raise ScheduleError("V2 pilot requires a frozen --runtime-matrix")
        validate_runtime_binding(runtime_binding)
        configs = tuple(
            config
            for config in runtime_binding.configurations
            if config.config_id in {"CFG1", "CFG2"}
        )
        targets = {config.config_id: 1 for config in configs}
        variants = v2_task_variants()
    elif phase == CODEX_MINI_PILOT_PHASE:
        if any(
            value is not None
            for value in (
                sizing_lock,
                sizing_anchor,
                codex_trials_per_cell,
                agy_trials_per_cell,
                agy_cli_version,
                runtime_binding,
            )
        ):
            raise ScheduleError("Codex mini-pilot is fixed at 2 valid trials")
        configs = CODEX_CONFIGS
        targets = {config.config_id: 2 for config in configs}
    elif phase == AGY_MINI_PILOT_PHASE:
        if any(
            value is not None
            for value in (
                sizing_lock,
                sizing_anchor,
                codex_trials_per_cell,
                agy_trials_per_cell,
                runtime_binding,
            )
        ):
            raise ScheduleError("agy mini-pilot is fixed at 2 valid trials")
        configs = _agy_configs(agy_cli_version)
        targets = {config.config_id: 2 for config in configs}
    else:
        if runtime_binding is not None:
            raise ScheduleError(
                "legacy confirmatory phase does not accept a V2 runtime matrix"
            )
        if sizing_lock is None:
            raise ScheduleError(
                "confirmatory plan requires a verified --sizing-lock"
            )
        try:
            sizing_lock.validate()
            if sizing_anchor is None:
                raise SizingLockError(
                    "confirmatory plan requires the independently anchored "
                    "R-005 commitment"
                )
            validate_commitment_anchor(sizing_lock, **sizing_anchor)
        except SizingLockError as exc:
            raise ScheduleError(f"invalid confirmatory sizing lock: {exc}") from exc
        trials_per_cell = sizing_lock.n_per_cell
        if trials_per_cell < 6:
            raise ScheduleError(
                "confirmatory sizing lock produced N below the registered floor"
            )
        if codex_trials_per_cell is not None or agy_trials_per_cell is not None:
            raise ScheduleError(
                "manual vendor-specific N is not provenance-bound; provide no "
                "vendor override until a separate verified lock is implemented"
            )
        codex_n = trials_per_cell
        agy_n = trials_per_cell
        configs = (*CLAUDE_CONFIGS, *CODEX_CONFIGS, *_agy_configs(agy_cli_version))
        targets = {
            config.config_id: (
                trials_per_cell
                if config.agent_id == "claude_code"
                else codex_n
                if config.agent_id == "codex"
                else agy_n
            )
            for config in configs
        }

    cells: list[Cell] = []
    for variant in variants:
        for env_id in ENVIRONMENTS:
            for config in configs:
                if config.expected_cli_version is None:
                    raise ScheduleError(
                        f"{config.config_id} has no expected CLI version"
                    )
                cells.append(
                    Cell(
                        cell_id=_cell_id(config, env_id, variant),
                        config_id=config.config_id,
                        agent_id=config.agent_id,
                        model_id=config.model_id,
                        expected_cli_version=config.expected_cli_version,
                        env_id=env_id,
                        task_id=variant.task_id,
                        family_id=variant.family_id,
                        instance_id=variant.instance_id,
                        instance_sha256=variant.instance_sha256,
                        task_path=variant.task_path,
                        task_sha256=variant.task_sha256,
                        phrasing=variant.phrasing,
                        target_valid_trials=(
                            2
                            if phase == V2_PILOT_PHASE
                            and variant.task_id in EXPECTED_SEEDED_ERROR_TASKS
                            else targets[config.config_id]
                        ),
                    )
                )

    expected_cells = {
        PILOT_PHASE: 230,
        V2_PILOT_PHASE: 540,
        CODEX_MINI_PILOT_PHASE: 230,
        AGY_MINI_PILOT_PHASE: 345,
        CONFIRMATORY_PHASE: 805,
    }[phase]
    if len(cells) != expected_cells:
        raise ScheduleError(
            f"{phase} requires {expected_cells} cells, built {len(cells)}"
        )
    if (
        phase == CONFIRMATORY_PHASE
        and sizing_lock is not None
        and sizing_lock.n_cells != expected_cells
    ):
        raise ScheduleError(
            "sizing-lock n_cells does not match the confirmatory roster"
        )
    if len({cell.cell_id for cell in cells}) != len(cells):
        raise ScheduleError("cell-id collision in generated plan")

    random.Random(order_seed).shuffle(cells)
    execution_slots = (
        build_blocked_execution_slots(cells, seed=order_seed)
        if phase == V2_PILOT_PHASE
        else None
    )
    provisional = SchedulePlan(
        schema_version=PLAN_SCHEMA_VERSION,
        created_at=_utc_now(),
        phase=phase,
        order_seed=order_seed,
        trial_schema_version=TRIAL_SCHEMA_VERSION,
        sizing_lock=sizing_lock,
        runtime_binding=runtime_binding,
        execution_slots=execution_slots,
        cells=tuple(cells),
        digest="",
    )
    return dataclasses.replace(
        provisional,
        digest=_digest_payload(provisional.payload()),
    )


def write_plan(plan: SchedulePlan, path: Path) -> None:
    """Write a new immutable plan. Existing paths are never overwritten."""
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("x", encoding="utf-8", newline="\n") as handle:
            json.dump(plan.as_dict(), handle, indent=2, ensure_ascii=False)
            handle.write("\n")
    except FileExistsError as exc:
        raise ScheduleError(f"refusing to overwrite existing plan: {path}") from exc


def _cell_from_dict(raw: object) -> Cell:
    if not isinstance(raw, dict):
        raise ScheduleError("plan cell must be a JSON object")
    try:
        cell = Cell(**raw)
    except (TypeError, ValueError) as exc:
        raise ScheduleError(f"malformed plan cell: {exc}") from exc
    if cell.target_valid_trials < 1:
        raise ScheduleError(f"{cell.cell_id}: target_valid_trials must be >= 1")
    return cell


def _slot_from_dict(raw: object) -> ScheduledSlot:
    expected_fields = {
        "position",
        "round_index",
        "block_index",
        "valid_slot_index",
        "cell_id",
    }
    if not isinstance(raw, dict) or set(raw) != expected_fields:
        raise ScheduleError("malformed execution slot")
    if not isinstance(raw["cell_id"], str) or any(
        isinstance(raw[field], bool) or not isinstance(raw[field], int)
        for field in expected_fields - {"cell_id"}
    ):
        raise ScheduleError("execution slot has invalid field types")
    return ScheduledSlot(**raw)


def load_plan(path: Path) -> SchedulePlan:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ScheduleError(f"cannot read plan {path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise ScheduleError(f"plan {path} must contain a JSON object")
    try:
        cells = tuple(_cell_from_dict(item) for item in raw["cells"])
        sizing_raw = raw["sizing_lock"]
        try:
            sizing_lock = (
                None
                if sizing_raw is None
                else sizing_lock_from_dict(sizing_raw)
            )
        except SizingLockError as exc:
            raise ScheduleError(f"invalid embedded sizing lock: {exc}") from exc
        runtime_raw = raw.get("runtime_binding")
        runtime_binding = (
            None
            if runtime_raw is None
            else _runtime_binding_from_dict(runtime_raw)
        )
        slots_raw = raw.get("execution_slots")
        if slots_raw is not None and not isinstance(slots_raw, list):
            raise ScheduleError("plan execution_slots must be a list or null")
        execution_slots = (
            None
            if slots_raw is None
            else tuple(_slot_from_dict(item) for item in slots_raw)
        )
        plan = SchedulePlan(
            schema_version=str(raw["schema_version"]),
            created_at=str(raw["created_at"]),
            phase=str(raw["phase"]),
            order_seed=int(raw["order_seed"]),
            trial_schema_version=str(raw["trial_schema_version"]),
            sizing_lock=sizing_lock,
            runtime_binding=runtime_binding,
            execution_slots=execution_slots,
            cells=cells,
            digest=str(raw["digest"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ScheduleError(f"malformed plan {path}: {exc}") from exc

    return validate_plan(plan)


def validate_plan(plan: SchedulePlan) -> SchedulePlan:
    """Validate an in-memory plan with the same checks used by ``load_plan``."""

    if not isinstance(plan, SchedulePlan):
        raise ScheduleError("plan must be a SchedulePlan")
    if plan.schema_version not in {
        LEGACY_PLAN_SCHEMA_VERSION,
        PLAN_SCHEMA_VERSION,
    }:
        raise ScheduleError(
            f"unsupported plan schema {plan.schema_version!r}; "
            f"expected {LEGACY_PLAN_SCHEMA_VERSION!r} or "
            f"{PLAN_SCHEMA_VERSION!r}"
        )
    if (
        plan.schema_version == LEGACY_PLAN_SCHEMA_VERSION
        and plan.phase == V2_PILOT_PHASE
    ):
        raise ScheduleError(
            "legacy V2 plans lack a frozen runtime binding and cannot be used"
        )
    if plan.phase not in PHASES:
        raise ScheduleError(f"unknown phase in plan: {plan.phase!r}")
    if plan.trial_schema_version != TRIAL_SCHEMA_VERSION:
        raise ScheduleError(
            f"plan expects trial schema {plan.trial_schema_version!r}, "
            f"current writer is {TRIAL_SCHEMA_VERSION!r}"
        )
    expected_digest = _digest_payload(plan.payload())
    if plan.digest != expected_digest:
        raise ScheduleError(
            f"plan digest mismatch: stored {plan.digest}, computed {expected_digest}"
        )
    if len({cell.cell_id for cell in plan.cells}) != len(plan.cells):
        raise ScheduleError("plan contains duplicate cell ids")
    if len({cell.coordinate for cell in plan.cells}) != len(plan.cells):
        raise ScheduleError("plan contains duplicate cell coordinates")
    _validate_plan_roster(plan)
    validate_task_hashes(plan)
    return plan


def _validate_plan_roster(plan: SchedulePlan) -> None:
    expected_count = {
        PILOT_PHASE: 230,
        V2_PILOT_PHASE: 540,
        CODEX_MINI_PILOT_PHASE: 230,
        AGY_MINI_PILOT_PHASE: 345,
        CONFIRMATORY_PHASE: 805,
    }[plan.phase]
    if len(plan.cells) != expected_count:
        raise ScheduleError(
            f"{plan.phase} plan must contain {expected_count} cells, "
            f"found {len(plan.cells)}"
        )
    if {cell.env_id for cell in plan.cells} != set(ENVIRONMENTS):
        raise ScheduleError("plan environment roster differs from V1")
    expected_configs = {
        PILOT_PHASE: {"CFG1", "CFG2"},
        V2_PILOT_PHASE: {"CFG1", "CFG2"},
        CODEX_MINI_PILOT_PHASE: {"CFG3", "CFG4"},
        AGY_MINI_PILOT_PHASE: {"CFG5", "CFG6", "CFG7"},
        CONFIRMATORY_PHASE: {f"CFG{i}" for i in range(1, 8)},
    }[plan.phase]
    if {cell.config_id for cell in plan.cells} != expected_configs:
        raise ScheduleError("plan configuration roster differs from V1")
    variants = (
        v2_task_variants()
        if plan.phase == V2_PILOT_PHASE
        else task_variants()
    )
    variant_keys = {(v.task_id, v.phrasing) for v in variants}
    if {(cell.task_id, cell.phrasing) for cell in plan.cells} != variant_keys:
        raise ScheduleError("plan task/phrasing roster differs from its phase")
    variant_map = {(v.task_id, v.phrasing): v for v in variants}

    if plan.phase == V2_PILOT_PHASE:
        if plan.runtime_binding is None:
            raise ScheduleError("V2 plan is missing its frozen runtime binding")
        validate_runtime_binding(plan.runtime_binding)
        expected_config_map = {
            config.config_id: config
            for config in plan.runtime_binding.configurations
        }
        if plan.execution_slots is None:
            raise ScheduleError("V2 plan is missing its blocked execution slots")
        validate_execution_slots(plan.cells, plan.execution_slots)
        expected_slots = build_blocked_execution_slots(
            plan.cells, seed=plan.order_seed
        )
        if plan.execution_slots != expected_slots:
            raise ScheduleError(
                "V2 execution slots differ from the registered blocked order"
            )
    else:
        if plan.runtime_binding is not None:
            raise ScheduleError(
                f"{plan.phase} plan must not contain a V2 runtime binding"
            )
        if plan.execution_slots is not None:
            raise ScheduleError(
                f"{plan.phase} plan must not contain V2 execution slots"
            )
        agy_versions = {
            cell.expected_cli_version
            for cell in plan.cells
            if cell.agent_id == "agy"
        }
        if len(agy_versions) > 1:
            raise ScheduleError("all agy cells must use one day-one CLI version")
        agy_version = next(iter(agy_versions), None)
        expected_config_map = {
            config.config_id: config
            for config in (
                *CLAUDE_CONFIGS,
                *CODEX_CONFIGS,
                *(_agy_configs(agy_version) if agy_version is not None else ()),
            )
        }
    for cell in plan.cells:
        variant = variant_map[(cell.task_id, cell.phrasing)]
        if (
            cell.family_id,
            cell.instance_id,
            cell.instance_sha256,
            cell.task_path,
            cell.task_sha256,
        ) != (
            variant.family_id,
            variant.instance_id,
            variant.instance_sha256,
            variant.task_path,
            variant.task_sha256,
        ):
            raise ScheduleError(
                f"{cell.cell_id}: task path/hash differs from locked "
                f"{cell.task_id}/{cell.phrasing}"
            )
        config = expected_config_map.get(cell.config_id)
        if config is None or (
            cell.agent_id,
            cell.model_id,
            cell.expected_cli_version,
        ) != (
            config.agent_id,
            config.model_id,
            config.expected_cli_version,
        ):
            raise ScheduleError(
                f"{cell.cell_id}: configuration fields differ from "
                f"locked {cell.config_id}"
            )
        expected_id = _cell_id(
            config,
            cell.env_id,
            TaskVariant(
                task_id=cell.task_id,
                family_id=cell.family_id,
                instance_id=cell.instance_id,
                instance_sha256=cell.instance_sha256,
                task_path=cell.task_path,
                task_sha256=cell.task_sha256,
                phrasing=cell.phrasing,
            ),
        )
        if cell.cell_id != expected_id:
            raise ScheduleError(
                f"cell id {cell.cell_id!r} does not match its coordinate"
            )

    actual_product = {
        (cell.config_id, cell.env_id, cell.task_id, cell.phrasing)
        for cell in plan.cells
    }
    expected_product = {
        (config_id, env_id, task_id, phrasing)
        for config_id in expected_configs
        for env_id in ENVIRONMENTS
        for task_id, phrasing in variant_keys
    }
    if actual_product != expected_product:
        raise ScheduleError("plan is not the complete phase Cartesian product")
    if plan.phase != CONFIRMATORY_PHASE:
        if plan.sizing_lock is not None:
            raise ScheduleError(f"{plan.phase} plan must not contain a sizing lock")
        expected_targets = (
            {
                cell.task_id: (
                    2 if cell.task_id in EXPECTED_SEEDED_ERROR_TASKS else 1
                )
                for cell in plan.cells
            }
            if plan.phase == V2_PILOT_PHASE
            else {cell.task_id: 2 for cell in plan.cells}
        )
        if any(
            cell.target_valid_trials != expected_targets[cell.task_id]
            for cell in plan.cells
        ):
            raise ScheduleError(
                f"{plan.phase} has a target-valid-trial count outside its frozen rule"
            )
    else:
        if plan.sizing_lock is None:
            raise ScheduleError("confirmatory plan is missing its sizing lock")
        try:
            plan.sizing_lock.validate()
        except SizingLockError as exc:
            raise ScheduleError(f"invalid embedded sizing lock: {exc}") from exc
        if plan.sizing_lock.n_cells != len(plan.cells):
            raise ScheduleError(
                "sizing-lock n_cells does not match the confirmatory roster"
            )
        by_agent: dict[str, set[int]] = {}
        for cell in plan.cells:
            by_agent.setdefault(cell.agent_id, set()).add(cell.target_valid_trials)
        if any(len(values) != 1 for values in by_agent.values()):
            raise ScheduleError("confirmatory N must be constant within each vendor")
        claude_n = next(iter(by_agent["claude_code"]))
        if claude_n != plan.sizing_lock.n_per_cell:
            raise ScheduleError(
                "confirmatory Claude N does not match the embedded sizing lock"
            )
        if claude_n < 6:
            raise ScheduleError("confirmatory Claude-derived N must be >= 6")
        if next(iter(by_agent["codex"])) != claude_n:
            raise ScheduleError("confirmatory Codex N must equal the signed locked N")
        if next(iter(by_agent["agy"])) != claude_n:
            raise ScheduleError("confirmatory agy N must equal the signed locked N")


def validate_task_hashes(plan: SchedulePlan) -> None:
    checked: dict[str, str] = {}
    for cell in plan.cells:
        task_path = (BENCH_ROOT / cell.task_path).resolve()
        if not _is_relative_to(task_path, TASKS_ROOT.resolve()):
            raise ScheduleError(
                f"{cell.cell_id}: task path escapes tasks/: {cell.task_path}"
            )
        current = checked.setdefault(cell.task_path, _sha256_file(task_path))
        if current != cell.task_sha256:
            raise ScheduleError(
                f"{cell.task_path} changed after plan creation; expected "
                f"{cell.task_sha256}, observed {current}"
            )


def schedule_identity_for_cell(
    plan: SchedulePlan,
    cell: Cell,
    *,
    valid_slot_index: int | None = None,
) -> ScheduleIdentity:
    """Build the one child/record identity authorized by ``plan``."""

    if cell not in plan.cells:
        raise ScheduleError(
            f"cell {cell.cell_id} is not a member of plan {plan.digest}"
        )
    return ScheduleIdentity.create(
        phase=plan.phase,
        plan_digest=plan.digest,
        cell_id=cell.cell_id,
        config_id=cell.config_id,
        task_sha256=cell.task_sha256,
        family_id=cell.family_id,
        instance_id=cell.instance_id,
        instance_sha256=cell.instance_sha256,
        trial_schema_version=plan.trial_schema_version,
        target_valid_trials=cell.target_valid_trials,
        task_id=cell.task_id,
        agent_id=cell.agent_id,
        model_id=cell.model_id,
        env_id=cell.env_id,
        phrasing=cell.phrasing,
        expected_cli_version=cell.expected_cli_version,
        valid_slot_index=valid_slot_index,
    )


def _validate_record_schedule(
    raw: object,
    *,
    plan: SchedulePlan,
    cell: Cell,
    path: Path,
) -> ScheduleIdentity:
    if not isinstance(raw, dict):
        raise ScheduleError(f"{path}: missing schedule identity")
    try:
        observed = ScheduleIdentity.from_dict(raw)
    except ValueError as exc:
        raise ScheduleError(f"{path}: invalid schedule identity: {exc}") from exc
    expected = schedule_identity_for_cell(
        plan,
        cell,
        valid_slot_index=observed.valid_slot_index,
    )
    if observed != expected:
        mismatches = [
            field
            for field, value in expected.as_dict().items()
            if observed.as_dict().get(field) != value
        ]
        raise ScheduleError(
            f"{path}: schedule identity does not match plan cell; "
            f"mismatched fields {mismatches}"
        )
    return observed


def _cell_dir(output_root: Path, cell: Cell) -> Path:
    return output_root.joinpath(
        cell.env_id,
        cell.agent_id,
        cell.model_id,
        cell.task_id,
        cell.phrasing,
    )


_TRIAL_FILENAME = re.compile(r"^trial_(\d+)__.+\.json$")
_ATTEMPT_FILENAME = re.compile(
    r"^attempt_(\d+)__([0-9a-f]{32})__(\d{2})_([a-z_]+)\.json$"
)


def _version_token_present(observed: str, expected: str) -> bool:
    pattern = rf"(?<![0-9.]){re.escape(expected)}(?![0-9.])"
    return re.search(pattern, observed) is not None


def _read_trial_identity(
    path: Path,
    *,
    output_root: Path,
    plan: SchedulePlan,
    cell: Cell,
) -> tuple[int, bool, str, str, str, int | None]:
    expected_parent = _cell_dir(output_root, cell).resolve()
    if path.parent.resolve() != expected_parent:
        raise ScheduleError(f"trial log is under the wrong cell path: {path}")
    match = _TRIAL_FILENAME.match(path.name)
    if match is None:
        raise ScheduleError(f"malformed trial filename: {path}")
    filename_index = int(match.group(1))
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ScheduleError(f"cannot parse trial log {path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise ScheduleError(f"trial log must be a JSON object: {path}")
    if raw.get("schema_version") != plan.trial_schema_version:
        raise ScheduleError(
            f"{path}: trial schema {raw.get('schema_version')!r} does not "
            f"match plan {plan.trial_schema_version!r}"
        )
    schedule = _validate_record_schedule(
        raw.get("schedule"),
        plan=plan,
        cell=cell,
        path=path,
    )
    trial = raw.get("trial")
    if not isinstance(trial, dict):
        raise ScheduleError(f"{path}: missing trial object")
    expected = {
        "env_id": cell.env_id,
        "agent_id": cell.agent_id,
        "model_id": cell.model_id,
        "task_id": cell.task_id,
        "family_id": cell.family_id,
        "instance_id": cell.instance_id,
        "instance_sha256": cell.instance_sha256,
        "phrasing": cell.phrasing,
    }
    for field, value in expected.items():
        if trial.get(field) != value:
            raise ScheduleError(
                f"{path}: trial.{field}={trial.get(field)!r}, expected {value!r}"
            )
    env_probe = raw.get("environment_probe")
    if not isinstance(env_probe, dict) or env_probe.get("env_id") != cell.env_id:
        raise ScheduleError(
            f"{path}: environment_probe.env_id does not match {cell.env_id!r}"
        )
    observed_cli_version = raw.get("agent_cli_version")
    if not isinstance(observed_cli_version, str) or not _version_token_present(
        observed_cli_version, cell.expected_cli_version
    ):
        raise ScheduleError(
            f"{path}: CLI version {observed_cli_version!r} does not contain "
            f"expected token {cell.expected_cli_version!r}"
        )
    trial_index = trial.get("trial_index")
    if not isinstance(trial_index, int) or isinstance(trial_index, bool):
        raise ScheduleError(f"{path}: trial_index must be a non-negative integer")
    if trial_index < 0 or trial_index != filename_index:
        raise ScheduleError(
            f"{path}: filename index {filename_index} != record index {trial_index}"
        )
    validity = raw.get("validity")
    if not isinstance(validity, dict) or type(validity.get("valid")) is not bool:
        raise ScheduleError(f"{path}: validity.valid must be a JSON boolean")
    attempt = raw.get("attempt")
    if not isinstance(attempt, dict):
        raise ScheduleError(f"{path}: missing attempt binding")
    if attempt.get("schema_version") != ATTEMPT_SCHEMA_VERSION:
        raise ScheduleError(
            f"{path}: attempt schema {attempt.get('schema_version')!r} does "
            f"not match {ATTEMPT_SCHEMA_VERSION!r}"
        )
    attempt_id = attempt.get("attempt_id")
    allocated_sha256 = attempt.get("allocated_event_sha256")
    if (
        not isinstance(attempt_id, str)
        or re.fullmatch(r"[0-9a-f]{32}", attempt_id) is None
    ):
        raise ScheduleError(f"{path}: malformed attempt_id")
    if (
        not isinstance(allocated_sha256, str)
        or re.fullmatch(r"[0-9a-f]{64}", allocated_sha256) is None
    ):
        raise ScheduleError(f"{path}: malformed allocated_event_sha256")
    measurement = raw.get("measurement")
    if not isinstance(measurement, dict):
        raise ScheduleError(f"{path}: missing measurement status")
    measurement_status = measurement.get("status")
    if measurement_status not in {"complete", AGENT_INDUCED_MEASUREMENT_LOSS}:
        raise ScheduleError(
            f"{path}: unknown measurement status {measurement_status!r}"
        )
    return (
        trial_index,
        validity["valid"],
        attempt_id,
        allocated_sha256,
        measurement_status,
        schedule.valid_slot_index,
    )


def _read_attempt_event(
    path: Path,
    *,
    output_root: Path,
    plan: SchedulePlan,
    cell: Cell,
) -> tuple[int, str, int, str, dict, str, int | None]:
    expected_parent = (_cell_dir(output_root, cell) / ATTEMPT_DIR_NAME).resolve()
    if path.parent.resolve() != expected_parent:
        raise ScheduleError(f"attempt event is under the wrong cell path: {path}")
    match = _ATTEMPT_FILENAME.match(path.name)
    if match is None:
        raise ScheduleError(f"malformed attempt-event filename: {path}")
    filename_index = int(match.group(1))
    filename_attempt_id = match.group(2)
    filename_sequence = int(match.group(3))
    filename_event = match.group(4)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ScheduleError(f"cannot parse attempt event {path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise ScheduleError(f"attempt event must be a JSON object: {path}")
    if raw.get("schema_version") != ATTEMPT_SCHEMA_VERSION:
        raise ScheduleError(
            f"{path}: attempt schema {raw.get('schema_version')!r} does not "
            f"match {ATTEMPT_SCHEMA_VERSION!r}"
        )
    schedule = _validate_record_schedule(
        raw.get("schedule"),
        plan=plan,
        cell=cell,
        path=path,
    )
    sequence = raw.get("sequence")
    event = raw.get("event")
    if sequence != filename_sequence or event != filename_event:
        raise ScheduleError(
            f"{path}: filename event identity does not match payload"
        )
    expected_event = {
        0: {"allocated"},
        1: {"launch_committed"},
        2: {"invocation_observed"},
        3: {"trial_recorded", "infrastructure_failure"},
    }
    if event not in expected_event.get(sequence, set()):
        raise ScheduleError(
            f"{path}: invalid event {event!r} at sequence {sequence!r}"
        )
    identity = raw.get("attempt")
    if not isinstance(identity, dict):
        raise ScheduleError(f"{path}: missing attempt identity")
    expected = {
        "env_id": cell.env_id,
        "agent_id": cell.agent_id,
        "model_id": cell.model_id,
        "task_id": cell.task_id,
        "phrasing": cell.phrasing,
    }
    for field, value in expected.items():
        if identity.get(field) != value:
            raise ScheduleError(
                f"{path}: attempt.{field}={identity.get(field)!r}, "
                f"expected {value!r}"
            )
    trial_index = identity.get("trial_index")
    attempt_id = identity.get("attempt_id")
    if (
        not isinstance(trial_index, int)
        or isinstance(trial_index, bool)
        or trial_index < 0
        or trial_index != filename_index
    ):
        raise ScheduleError(f"{path}: malformed or inconsistent trial_index")
    if attempt_id != filename_attempt_id:
        raise ScheduleError(f"{path}: filename attempt_id does not match payload")
    result = raw.get("result", {})
    if not isinstance(result, dict):
        raise ScheduleError(f"{path}: result must be a JSON object")
    return (
        trial_index,
        attempt_id,
        sequence,
        event,
        result,
        attempt_sha256_file(path),
        schedule.valid_slot_index,
    )


def scan_cell_output(
    output_root: Path,
    plan: SchedulePlan,
    cell: Cell,
) -> CellState:
    directory = _cell_dir(output_root, cell)
    if not directory.exists():
        return CellState()
    trial_indices: set[int] = set()
    trials_by_attempt: dict[
        str, tuple[Path, int, bool, str, str, int | None]
    ] = {}
    for path in sorted(directory.glob("trial_*.json")):
        (
            trial_index,
            is_valid,
            attempt_id,
            allocated_sha256,
            measurement_status,
            valid_slot_index,
        ) = _read_trial_identity(
            path,
            output_root=output_root,
            plan=plan,
            cell=cell,
        )
        if trial_index in trial_indices:
            raise ScheduleError(
                f"{cell.cell_id}: duplicate trial_index {trial_index}"
            )
        if attempt_id in trials_by_attempt:
            raise ScheduleError(
                f"{cell.cell_id}: duplicate trial record for attempt {attempt_id}"
            )
        trial_indices.add(trial_index)
        trials_by_attempt[attempt_id] = (
            path,
            trial_index,
            is_valid,
            allocated_sha256,
            measurement_status,
            valid_slot_index,
        )

    events_by_attempt: dict[
        str, dict[int, tuple[Path, int, str, dict, str, int | None]]
    ] = {}
    attempt_dir = directory / ATTEMPT_DIR_NAME
    if attempt_dir.exists():
        for path in sorted(attempt_dir.iterdir()):
            if not path.is_file() or _ATTEMPT_FILENAME.match(path.name) is None:
                raise ScheduleError(
                    f"unexpected attempt-ledger entry: {path}"
                )
            (
                trial_index,
                attempt_id,
                sequence,
                event,
                result,
                event_sha256,
                valid_slot_index,
            ) = _read_attempt_event(
                path,
                output_root=output_root,
                plan=plan,
                cell=cell,
            )
            events = events_by_attempt.setdefault(attempt_id, {})
            if sequence in events:
                raise ScheduleError(
                    f"{cell.cell_id}: duplicate sequence {sequence} for "
                    f"attempt {attempt_id}"
                )
            events[sequence] = (
                path,
                trial_index,
                event,
                result,
                event_sha256,
                valid_slot_index,
            )

    attempt_indices: set[int] = set()
    valid = 0
    invalid = 0
    unresolved = 0
    max_index = -1
    ordered_attempts = sorted(
        events_by_attempt.items(),
        key=lambda item: item[1].get(0, (None, math.inf))[1],
    )
    for attempt_id, events in ordered_attempts:
        allocated = events.get(0)
        if allocated is None or allocated[2] != "allocated":
            raise ScheduleError(
                f"{cell.cell_id}: attempt {attempt_id} has no allocated event"
            )
        (
            _,
            trial_index,
            _,
            _,
            allocated_event_sha256,
            valid_slot_index,
        ) = allocated
        if any(event_data[1] != trial_index for event_data in events.values()):
            raise ScheduleError(
                f"{cell.cell_id}: inconsistent trial_index across events for "
                f"attempt {attempt_id}"
            )
        if any(
            event_data[5] != valid_slot_index for event_data in events.values()
        ):
            raise ScheduleError(
                f"{cell.cell_id}: valid-slot identity changed within attempt "
                f"{attempt_id}"
            )
        expected_valid_slot = valid if plan.phase == V2_PILOT_PHASE else None
        if valid_slot_index != expected_valid_slot:
            raise ScheduleError(
                f"{cell.cell_id}: attempt {attempt_id} targets valid slot "
                f"{valid_slot_index!r}, expected {expected_valid_slot!r}"
            )
        if trial_index in attempt_indices:
            raise ScheduleError(
                f"{cell.cell_id}: duplicate trial_index {trial_index}"
            )
        attempt_indices.add(trial_index)
        max_index = max(max_index, trial_index)
        launch_commit = events.get(1)
        invocation = events.get(2)
        terminal = events.get(3)
        if invocation is not None and launch_commit is None:
            raise ScheduleError(
                f"{cell.cell_id}: invocation observed without launch "
                f"commitment for attempt {attempt_id}"
            )
        trial = trials_by_attempt.pop(attempt_id, None)
        if trial is not None:
            (
                trial_path,
                record_index,
                is_valid,
                bound_allocated_sha256,
                measurement_status,
                trial_valid_slot_index,
            ) = trial
            if record_index != trial_index:
                raise ScheduleError(
                    f"{cell.cell_id}: attempt/trial index mismatch for "
                    f"{attempt_id}"
                )
            if bound_allocated_sha256 != allocated_event_sha256:
                raise ScheduleError(
                    f"{trial_path}: allocated-event digest mismatch"
                )
            if trial_valid_slot_index != valid_slot_index:
                raise ScheduleError(
                    f"{trial_path}: trial and attempt valid-slot identities differ"
                )

        if terminal is None:
            # Crash window: the final trial is authoritative when its attempt
            # binding validates, even if the terminal append never completed.
            if trial is not None:
                if invocation is None:
                    raise ScheduleError(
                        f"{cell.cell_id}: final trial without invocation event "
                        f"for attempt {attempt_id}"
                    )
                valid += int(is_valid)
                invalid += int(not is_valid)
            else:
                unresolved += 1
            continue

        terminal_path, _, terminal_event, result, _, _ = terminal
        status = result.get("status")
        attribution = result.get("attribution")
        result_valid = result.get("valid")
        if type(result_valid) is not bool:
            raise ScheduleError(
                f"{terminal_path}: terminal result.valid must be a JSON boolean"
            )
        if terminal_event == "infrastructure_failure":
            if status != "infrastructure_failure" or result_valid:
                raise ScheduleError(
                    f"{terminal_path}: malformed infrastructure terminal"
                )
            if trial is not None:
                raise ScheduleError(
                    f"{cell.cell_id}: competing failure terminal and final "
                    f"trial for attempt {attempt_id}"
                )
            expected_attribution = (
                POST_INVOCATION_INFRASTRUCTURE_FAILURE
                if invocation is not None
                else (
                    INVOCATION_START_UNKNOWN_INFRASTRUCTURE_FAILURE
                    if launch_commit is not None
                    else PRE_INVOCATION_INFRASTRUCTURE_FAILURE
                )
            )
            if attribution != expected_attribution:
                raise ScheduleError(
                    f"{terminal_path}: attribution {attribution!r} does not "
                    f"match invocation evidence"
                )
            invalid += 1
            continue

        if terminal_event != "trial_recorded" or status != "trial_recorded":
            raise ScheduleError(f"{terminal_path}: malformed trial terminal")
        if invocation is None:
            raise ScheduleError(
                f"{terminal_path}: trial terminal has no invocation event"
            )
        if trial is None:
            # A terminal link without its named immutable record is never
            # converted into an invalid replacement; collection must stop.
            raise ScheduleError(
                f"{terminal_path}: terminal trial link has no final record"
            )
        trial_path, _, is_valid, _, measurement_status, _ = trial
        try:
            relative_trial = trial_path.resolve().relative_to(
                output_root.resolve()
            ).as_posix()
        except ValueError as exc:
            raise ScheduleError(
                f"trial path escapes output root: {trial_path}"
            ) from exc
        if result.get("trial_record") != relative_trial:
            raise ScheduleError(
                f"{terminal_path}: terminal trial path does not match record"
            )
        if result.get("trial_record_sha256") != _sha256_file(trial_path):
            raise ScheduleError(
                f"{terminal_path}: terminal trial digest mismatch"
            )
        if result_valid is not is_valid:
            raise ScheduleError(
                f"{terminal_path}: terminal validity does not match record"
            )
        allowed_attribution = {
            COMPLETE,
            POST_INVOCATION_INFRASTRUCTURE_FAILURE,
            AGENT_INDUCED_MEASUREMENT_LOSS,
        }
        if attribution not in allowed_attribution:
            raise ScheduleError(
                f"{terminal_path}: unknown trial attribution {attribution!r}"
            )
        expected_measurement_status = (
            AGENT_INDUCED_MEASUREMENT_LOSS
            if attribution == AGENT_INDUCED_MEASUREMENT_LOSS
            else COMPLETE
        )
        if measurement_status != expected_measurement_status:
            raise ScheduleError(
                f"{terminal_path}: terminal attribution does not match "
                "trial measurement status"
            )
        if attribution == COMPLETE and not is_valid:
            raise ScheduleError(
                f"{terminal_path}: invalid record cannot have complete attribution"
            )
        if (
            attribution == AGENT_INDUCED_MEASUREMENT_LOSS
            and not is_valid
        ):
            raise ScheduleError(
                f"{terminal_path}: agent-induced measurement loss must be valid"
            )
        if (
            attribution == POST_INVOCATION_INFRASTRUCTURE_FAILURE
            and is_valid
        ):
            raise ScheduleError(
                f"{terminal_path}: post-invocation infrastructure record "
                "must be invalid"
            )
        valid += int(is_valid)
        invalid += int(not is_valid)

    if trials_by_attempt:
        orphan = next(iter(trials_by_attempt.values()))[0]
        raise ScheduleError(f"final trial has no attempt ledger: {orphan}")
    if valid > cell.target_valid_trials:
        raise ScheduleError(
            f"{cell.cell_id}: over-collected {valid} valid trials; "
            f"target is {cell.target_valid_trials}"
        )
    return CellState(
        valid=valid,
        invalid=invalid,
        unresolved=unresolved,
        next_index=max_index + 1,
    )


def scan_output(output_root: Path, plan: SchedulePlan) -> dict[str, CellState]:
    states = {cell.cell_id: CellState() for cell in plan.cells}
    if not output_root.exists():
        return states

    cells_by_coordinate = {cell.coordinate: cell for cell in plan.cells}
    for path in sorted(output_root.rglob("trial_*.json")):
        try:
            rel = path.relative_to(output_root)
        except ValueError as exc:
            raise ScheduleError(f"trial path escapes output root: {path}") from exc
        if len(rel.parts) != 6:
            raise ScheduleError(f"unexpected trial-log layout: {path}")
        coordinate = tuple(rel.parts[:5])
        cell = cells_by_coordinate.get(coordinate)  # type: ignore[arg-type]
        if cell is None:
            raise ScheduleError(f"foreign cell log under plan-bound output: {path}")
    for path in sorted(output_root.rglob("attempt_*.json")):
        try:
            rel = path.relative_to(output_root)
        except ValueError as exc:
            raise ScheduleError(
                f"attempt path escapes output root: {path}"
            ) from exc
        if len(rel.parts) != 7 or rel.parts[5] != ATTEMPT_DIR_NAME:
            raise ScheduleError(f"unexpected attempt-log layout: {path}")
        coordinate = tuple(rel.parts[:5])
        if coordinate not in cells_by_coordinate:
            raise ScheduleError(
                f"foreign attempt log under plan-bound output: {path}"
            )
    for attempt_dir in sorted(output_root.rglob(ATTEMPT_DIR_NAME)):
        if not attempt_dir.is_dir():
            raise ScheduleError(
                f"attempt ledger path is not a directory: {attempt_dir}"
            )
        try:
            rel = attempt_dir.relative_to(output_root)
        except ValueError as exc:
            raise ScheduleError(
                f"attempt directory escapes output root: {attempt_dir}"
            ) from exc
        if len(rel.parts) != 6:
            raise ScheduleError(
                f"unexpected attempt-ledger layout: {attempt_dir}"
            )
        coordinate = tuple(rel.parts[:5])
        if coordinate not in cells_by_coordinate:
            raise ScheduleError(
                f"foreign attempt ledger under plan-bound output: {attempt_dir}"
            )

    for cell in plan.cells:
        states[cell.cell_id] = scan_cell_output(output_root, plan, cell)
    return states


def _bound_plan_path(output_root: Path) -> Path:
    return output_root / BOUND_PLAN_NAME


def validate_output_binding(output_root: Path, plan: SchedulePlan) -> None:
    if not output_root.exists():
        return
    bound_path = _bound_plan_path(output_root)
    if bound_path.exists():
        bound = load_plan(bound_path)
        if bound.digest != plan.digest:
            raise ScheduleError(
                f"output root is bound to plan {bound.digest}, not {plan.digest}"
            )
        return
    if (
        any(output_root.rglob("trial_*.json"))
        or any(output_root.rglob("attempt_*.json"))
        or any(output_root.rglob(ATTEMPT_DIR_NAME))
    ):
        raise ScheduleError(
            f"{output_root} contains attempt/trial logs but no "
            f"{BOUND_PLAN_NAME}; "
            "refusing to adopt ambiguous data"
        )


def bind_output(output_root: Path, plan: SchedulePlan) -> None:
    output_root.mkdir(parents=True, exist_ok=True)
    bound_path = _bound_plan_path(output_root)
    if bound_path.exists():
        validate_output_binding(output_root, plan)
        return
    contents = list(output_root.iterdir())
    if contents:
        raise ScheduleError(
            f"unbound output root is not empty: {output_root}; found "
            f"{[item.name for item in contents[:5]]}"
        )
    write_plan(plan, bound_path)


def validate_pilot_blinding_commitment(
    output_root: Path,
    plan: SchedulePlan,
) -> None:
    """Fail before pilot attempt 1 unless the pre-outcome commitment is valid."""
    if plan.phase not in {PILOT_PHASE, V2_PILOT_PHASE}:
        return
    path = output_root / BOUND_COMMITMENT_NAME
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ScheduleError(
            "pilot execution requires a readable pre-outcome blinding "
            f"commitment at {path}"
        ) from exc
    expected = {
        "schema_version",
        "purpose",
        "created_at",
        "plan_digest",
        "mapping_digest",
        "public_key_b64",
        "commitment_digest",
    }
    if not isinstance(raw, dict) or set(raw) != expected:
        raise ScheduleError("pilot blinding commitment has unknown or missing fields")
    payload = {field: raw[field] for field in expected - {"commitment_digest"}}
    if (
        raw["schema_version"] != "1.0.0"
        or raw["purpose"] != "pilot_blinding_public_commitment"
        or not isinstance(raw["created_at"], str)
        or not raw["created_at"]
        or raw["plan_digest"] != plan.digest
        or not isinstance(raw["mapping_digest"], str)
        or re.fullmatch(r"[0-9a-f]{64}", raw["mapping_digest"]) is None
        or not isinstance(raw["commitment_digest"], str)
        or not isinstance(raw["public_key_b64"], str)
        or raw["commitment_digest"] != _digest_payload(payload)
    ):
        raise ScheduleError("pilot blinding commitment is malformed or plan-mismatched")
    try:
        public_key = base64.b64decode(raw["public_key_b64"], validate=True)
    except (TypeError, ValueError) as exc:
        raise ScheduleError("pilot blinding commitment public key is malformed") from exc
    if len(public_key) != 32:
        raise ScheduleError("pilot blinding commitment public key is malformed")


@contextmanager
def output_lock(output_root: Path, plan: SchedulePlan) -> Iterator[None]:
    lock_path = output_root / LOCK_NAME
    try:
        with lock_path.open("x", encoding="utf-8", newline="\n") as handle:
            json.dump(
                {
                    "plan_digest": plan.digest,
                    "pid": os.getpid(),
                    "created_at": _utc_now(),
                },
                handle,
                indent=2,
            )
            handle.write("\n")
    except FileExistsError as exc:
        raise ScheduleError(
            f"scheduler lock already exists: {lock_path}; if no scheduler is "
            "running, review and remove that exact stale lock manually"
        ) from exc
    try:
        yield
    finally:
        lock_path.unlink(missing_ok=True)


def validate_execution_paths(output_root: Path, cwd: Path | None = None) -> None:
    root = BENCH_ROOT.resolve()
    control_cwd = (cwd or Path.cwd()).resolve()
    output = output_root.resolve()
    if _is_relative_to(control_cwd, root):
        raise ScheduleError(
            f"refusing to execute from methodology checkout {control_cwd}; "
            "change to an external control directory first"
        )
    if output == root:
        raise ScheduleError("output root may not be the repository root")
    if output == DATA_ROOT.resolve():
        raise ScheduleError("use a dedicated phase output below data/, not bare data/")
    if _is_relative_to(output, PRE_REGISTRATION_ROOT.resolve()):
        raise ScheduleError("collection output may not use data/pre-registration/")
    if _is_relative_to(output, root) and not _is_relative_to(
        output, DATA_ROOT.resolve()
    ):
        raise ScheduleError(
            "output inside the repository is allowed only below data/"
        )


def _select_cells(
    plan: SchedulePlan,
    *,
    only_envs: set[str] | None,
    only_configs: set[str] | None,
    only_tasks: set[str] | None,
) -> list[Cell]:
    filters = (
        ("environment", only_envs, {cell.env_id for cell in plan.cells}),
        ("configuration", only_configs, {cell.config_id for cell in plan.cells}),
        ("task", only_tasks, {cell.task_id for cell in plan.cells}),
    )
    for label, requested, available in filters:
        unknown = (requested or set()) - available
        if unknown:
            raise ScheduleError(
                f"unknown {label} filter(s) {sorted(unknown)}; "
                f"available: {sorted(available)}"
            )
    return [
        cell
        for cell in plan.cells
        if (not only_envs or cell.env_id in only_envs)
        and (not only_configs or cell.config_id in only_configs)
        and (not only_tasks or cell.task_id in only_tasks)
    ]


def pending_execution_units(
    plan: SchedulePlan,
    selected: Sequence[Cell],
    states: Mapping[str, CellState],
) -> list[tuple[Cell, int | None]]:
    """Return pending work in the exact plan-bound execution order."""
    if plan.phase != V2_PILOT_PHASE:
        return [
            (cell, None)
            for cell in selected
            if states[cell.cell_id].valid < cell.target_valid_trials
        ]
    if plan.execution_slots is None:
        raise ScheduleError("V2 plan is missing blocked execution slots")
    selected_ids = {cell.cell_id for cell in selected}
    cell_map = {cell.cell_id: cell for cell in plan.cells}
    return [
        (cell_map[slot.cell_id], slot.valid_slot_index)
        for slot in plan.execution_slots
        if slot.cell_id in selected_ids
        and states[slot.cell_id].valid <= slot.valid_slot_index
    ]


def _validate_collection_environment(
    selected: Sequence[Cell],
    environment: Mapping[str, str],
    inter_trial_delays: Mapping[str, float],
) -> None:
    agents = {cell.agent_id for cell in selected}
    missing_delays = agents - set(inter_trial_delays)
    if missing_delays:
        raise ScheduleError(
            "execution requires an explicit inter-trial delay for each selected "
            f"agent (zero is allowed when justified): {sorted(missing_delays)}"
        )
    for agent_id, seconds in inter_trial_delays.items():
        if not math.isfinite(seconds) or seconds < 0:
            raise ScheduleError(
                f"inter-trial delay for {agent_id} must be finite and >= 0"
            )
    if "claude_code" in agents:
        missing = [name for name in REQUIRED_CLAUDE_ENV_VARS if not environment.get(name)]
        if missing:
            raise ScheduleError(
                "Claude collection hygiene is incomplete; missing environment "
                f"variables: {missing}"
            )


def _validate_host_partition(selected: Sequence[Cell], platform: str) -> None:
    envs = {cell.env_id for cell in selected}
    windows_local = {"windows_powershell", "windows_pwsh7", "windows_wsl2"}
    if envs & windows_local and not platform.startswith("win"):
        raise ScheduleError(
            "Windows-local cells require a Windows collection host; filter "
            "the persisted plan with --only-env"
        )
    if "macos_actions" in envs and platform != "darwin":
        raise ScheduleError(
            "macos_actions cells require the pinned macOS runner; filter the "
            "persisted plan with --only-env"
        )


def build_run_argv(
    cell: Cell,
    *,
    plan: SchedulePlan,
    output_root: Path,
    trials: int,
    trial_index_start: int,
    inter_trial_delay_seconds: float,
    max_budget_usd: float | None,
    valid_slot_index: int | None = None,
) -> list[str]:
    if trials < 1:
        raise ScheduleError("child trials must be >= 1")
    task_path = (BENCH_ROOT / cell.task_path).resolve()
    argv = [
        sys.executable,
        "-m",
        "harness",
        "run",
        "--task",
        str(task_path),
        "--agent",
        cell.agent_id,
        "--model",
        cell.model_id,
        "--env",
        cell.env_id,
        "--trials",
        str(trials),
        "--output",
        str(output_root.resolve()),
        "--trial-index-start",
        str(trial_index_start),
        "--expect-cli-version",
        cell.expected_cli_version,
        "--inter-trial-delay-seconds",
        str(inter_trial_delay_seconds),
        "--hide-outcomes",
        "--schedule-token",
        schedule_identity_for_cell(
            plan, cell, valid_slot_index=valid_slot_index
        ).encode_token(),
    ]
    if valid_slot_index is not None:
        argv.extend(["--valid-slot-index", str(valid_slot_index)])
    if cell.phrasing != "default":
        argv.extend(["--phrasing", cell.phrasing])
    if max_budget_usd is not None:
        argv.extend(["--max-budget-usd", str(max_budget_usd)])
    return argv


def _child_environment(base: Mapping[str, str]) -> dict[str, str]:
    env = dict(base)
    existing = env.get("PYTHONPATH")
    env["PYTHONPATH"] = (
        str(BENCH_ROOT) if not existing else str(BENCH_ROOT) + os.pathsep + existing
    )
    return env


def _default_executor(
    argv: Sequence[str],
    *,
    cwd: Path,
    env: Mapping[str, str],
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(argv),
        cwd=cwd,
        env=dict(env),
        capture_output=True,
        text=True,
        check=False,
    )


def summarize(
    plan: SchedulePlan,
    selected: Sequence[Cell],
    states: Mapping[str, CellState],
    execution_cells: Sequence[Cell],
    *,
    executed_attempts: int = 0,
) -> ScheduleSummary:
    complete = sum(
        states[cell.cell_id].valid == cell.target_valid_trials
        for cell in selected
    )
    return ScheduleSummary(
        phase=plan.phase,
        digest=plan.digest,
        selected_cells=len(selected),
        pending_cells=len(selected) - complete,
        complete_cells=complete,
        target_valid_trials=sum(cell.target_valid_trials for cell in selected),
        existing_valid_trials=sum(states[cell.cell_id].valid for cell in selected),
        existing_invalid_trials=sum(states[cell.cell_id].invalid for cell in selected),
        existing_unresolved_attempts=sum(
            states[cell.cell_id].unresolved for cell in selected
        ),
        execution_cells=len(execution_cells),
        executed_attempts=executed_attempts,
    )


def run_schedule(
    plan: SchedulePlan,
    *,
    output_root: Path,
    execute: bool = False,
    only_envs: set[str] | None = None,
    only_configs: set[str] | None = None,
    only_tasks: set[str] | None = None,
    max_cells: int | None = None,
    batch_size: int = 6,
    max_zero_progress_batches: int = 3,
    inter_trial_delays: Mapping[str, float] | None = None,
    max_budget_usd: float | None = None,
    executor: Callable[..., subprocess.CompletedProcess[str]] = _default_executor,
    cwd: Path | None = None,
    environment: Mapping[str, str] | None = None,
    host_platform: str | None = None,
    sizing_anchor: Mapping[str, str] | None = None,
    runtime_binding: RuntimeBinding | None = None,
) -> ScheduleSummary:
    """Inspect or execute a plan, preserving its pre-generated order."""
    if max_cells is not None and max_cells < 1:
        raise ScheduleError("max_cells must be >= 1")
    if batch_size < 1:
        raise ScheduleError("batch_size must be >= 1")
    if max_zero_progress_batches < 1:
        raise ScheduleError("max_zero_progress_batches must be >= 1")
    validate_task_hashes(plan)
    validate_output_binding(output_root, plan)
    states = scan_output(output_root, plan)
    selected = _select_cells(
        plan,
        only_envs=only_envs,
        only_configs=only_configs,
        only_tasks=only_tasks,
    )
    pending_units = pending_execution_units(plan, selected, states)
    execution_units = (
        pending_units[:max_cells] if max_cells is not None else pending_units
    )
    execution_cells = [cell for cell, _ in execution_units]
    before = summarize(plan, selected, states, execution_cells)
    if not execute:
        return before
    unresolved_cells = [
        cell.cell_id
        for cell in selected
        if states[cell.cell_id].unresolved
    ]
    if unresolved_cells:
        raise ScheduleError(
            "refusing automatic retry with unresolved attempt journal "
            f"entries in cells {unresolved_cells[:5]}; reconcile the durable "
            "prefix before collection resumes"
        )
    if not execution_cells:
        return before

    if plan.phase == CONFIRMATORY_PHASE:
        if plan.sizing_lock is None or sizing_anchor is None:
            raise ScheduleError(
                "confirmatory execution requires the independently anchored "
                "R-005 commitment"
            )
        try:
            validate_commitment_anchor(plan.sizing_lock, **sizing_anchor)
        except SizingLockError as exc:
            raise ScheduleError(f"invalid confirmatory sizing anchor: {exc}") from exc
    if plan.phase == V2_PILOT_PHASE:
        if runtime_binding is None:
            raise ScheduleError(
                "V2 execution requires the independently supplied frozen "
                "--runtime-matrix"
            )
        validate_runtime_binding(runtime_binding)
        if runtime_binding != plan.runtime_binding:
            raise ScheduleError(
                "execution runtime matrix differs from the plan-bound matrix"
            )
    elif runtime_binding is not None:
        raise ScheduleError(
            f"{plan.phase} execution does not accept a V2 runtime matrix"
        )

    control_cwd = (cwd or Path.cwd()).resolve()
    process_env = dict(environment or os.environ)
    delays = dict(inter_trial_delays or {})
    validate_execution_paths(output_root, control_cwd)
    _validate_host_partition(execution_cells, host_platform or sys.platform)
    _validate_collection_environment(execution_cells, process_env, delays)
    bind_output(output_root, plan)

    executed_attempts = 0
    with output_lock(output_root, plan):
        # Re-scan only after the plan is bound and the lock is held. This
        # closes the race between dry-run/status and the first paid child.
        validate_pilot_blinding_commitment(output_root, plan)
        states = scan_output(output_root, plan)
        child_env = _child_environment(process_env)
        last_batch_finished: dict[str, float] = {}
        for position, (cell, valid_slot_index) in enumerate(
            execution_units, start=1
        ):
            state = states[cell.cell_id]
            if state.unresolved:
                raise ScheduleError(
                    f"cell {cell.cell_id} has {state.unresolved} unresolved "
                    "attempt(s); refusing automatic retry"
                )
            target_valid = (
                cell.target_valid_trials
                if valid_slot_index is None
                else valid_slot_index + 1
            )
            if state.valid >= target_valid:
                continue
            zero_progress_batches = 0
            slot_detail = (
                ""
                if valid_slot_index is None
                else f"scheduled_slot={valid_slot_index}, "
            )
            print(
                f"cell {position}/{len(execution_cells)} {cell.cell_id} "
                f"{cell.env_id}/{cell.config_id}/{cell.task_id}/{cell.phrasing}: "
                f"valid {state.valid}/{cell.target_valid_trials}, "
                f"{slot_detail}invalid {state.invalid}"
            )
            while state.valid < target_valid:
                deficit = target_valid - state.valid
                batch = min(deficit, batch_size)
                argv = build_run_argv(
                    cell,
                    plan=plan,
                    output_root=output_root,
                    trials=batch,
                    trial_index_start=state.next_index,
                    inter_trial_delay_seconds=delays[cell.agent_id],
                    max_budget_usd=max_budget_usd,
                    valid_slot_index=valid_slot_index,
                )
                previous_finish = last_batch_finished.get(cell.agent_id)
                if previous_finish is not None:
                    remaining_delay = delays[cell.agent_id] - (
                        time.monotonic() - previous_finish
                    )
                    if remaining_delay > 0:
                        time.sleep(remaining_delay)
                completed = executor(
                    argv,
                    cwd=control_cwd,
                    env=child_env,
                )
                last_batch_finished[cell.agent_id] = time.monotonic()
                if completed.returncode != 0:
                    # Child stdout is intentionally never surfaced: even an
                    # earlier runner could include PASS/FAIL lines there.
                    stderr_tail = (completed.stderr or "").strip()[-2000:]
                    detail = f"; stderr: {stderr_tail}" if stderr_tail else ""
                    raise ScheduleError(
                        f"cell {cell.cell_id} child exited "
                        f"{completed.returncode}{detail}"
                    )
                new_state = scan_cell_output(output_root, plan, cell)
                if new_state.unresolved:
                    raise ScheduleError(
                        f"cell {cell.cell_id} child left "
                        f"{new_state.unresolved} unresolved attempt(s)"
                    )
                new_attempts = new_state.attempts - state.attempts
                new_valid = new_state.valid - state.valid
                if new_attempts != batch:
                    raise ScheduleError(
                        f"cell {cell.cell_id} child promised {batch} records but "
                        f"produced {new_attempts}"
                    )
                executed_attempts += new_attempts
                zero_progress_batches = (
                    zero_progress_batches + 1 if new_valid == 0 else 0
                )
                state = new_state
                states[cell.cell_id] = state
                print(
                    f"  recorded {new_attempts} attempt(s): "
                    f"valid {state.valid}/{cell.target_valid_trials}, "
                    f"invalid {state.invalid}"
                )
                if (
                    state.valid < target_valid
                    and zero_progress_batches >= max_zero_progress_batches
                ):
                    raise ScheduleError(
                        f"cell {cell.cell_id} made no valid progress in "
                        f"{zero_progress_batches} consecutive batches; stopping "
                        "with immutable invalid logs preserved (resume after "
                        "fixing the infrastructure)"
                    )

    final_states = scan_output(output_root, plan)
    return summarize(
        plan,
        selected,
        final_states,
        execution_cells,
        executed_attempts=executed_attempts,
    )
