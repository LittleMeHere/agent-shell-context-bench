"""Outcome-blind blocked-round candidates for D-009.

This module compares execution orders; it does not freeze one.  A valid slot
is the unit that consumes one analysis observation.  Infrastructure-invalid
attempts remain attached to the same slot and therefore never alter this
order.

The blocked candidate separates repeated slots into rounds and keeps every
task/phrasing block crossed over the selected configurations and environments.
That makes balance auditable at block boundaries and makes the order exactly
resumable from its persisted slot list.  Production scheduling must not import
this evidence module until the researcher accepts the randomization unit and
epoch rule.
"""

from __future__ import annotations

import hashlib
import json
import random
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from typing import Iterable, Mapping, Sequence

from harness.scheduler import Cell, SchedulePlan


HOST_PARTITIONS = {
    "windows_powershell": "windows_local",
    "windows_pwsh7": "windows_local",
    "windows_wsl2": "windows_local",
    "linux_native": "linux_native",
    "macos_actions": "macos_actions",
}


@dataclass(frozen=True)
class ExecutionSlot:
    """One prospectively ordered valid-trial slot."""

    position: int
    round_index: int
    block_index: int
    valid_slot_index: int
    cell_id: str
    config_id: str
    env_id: str
    host_partition: str
    task_id: str
    family_id: str
    instance_id: str
    phrasing: str
    task_category: str

    @property
    def identity(self) -> tuple[str, int]:
        return self.cell_id, self.valid_slot_index


def _category(task_id: str) -> str:
    if task_id.startswith("C"):
        return "capability"
    if task_id.startswith("T"):
        return "seeded_error"
    raise ValueError(f"unsupported task category for {task_id!r}")


def expected_slot_multiset(plan: SchedulePlan) -> Counter[tuple[str, int]]:
    """Return the exact cell/valid-slot multiset implied by a plan."""

    return Counter(
        (cell.cell_id, slot_index)
        for cell in plan.cells
        for slot_index in range(cell.target_valid_trials)
    )


def _slot(
    cell: Cell,
    *,
    position: int,
    round_index: int,
    block_index: int,
    valid_slot_index: int,
) -> ExecutionSlot:
    try:
        partition = HOST_PARTITIONS[cell.env_id]
    except KeyError as exc:
        raise ValueError(f"unregistered environment {cell.env_id!r}") from exc
    return ExecutionSlot(
        position=position,
        round_index=round_index,
        block_index=block_index,
        valid_slot_index=valid_slot_index,
        cell_id=cell.cell_id,
        config_id=cell.config_id,
        env_id=cell.env_id,
        host_partition=partition,
        task_id=cell.task_id,
        family_id=cell.family_id,
        instance_id=cell.instance_id,
        phrasing=cell.phrasing,
        task_category=_category(cell.task_id),
    )


def whole_cell_order(plan: SchedulePlan) -> tuple[ExecutionSlot, ...]:
    """Expand the current whole-cell plan order into valid slots."""

    result: list[ExecutionSlot] = []
    for block_index, cell in enumerate(plan.cells):
        for slot_index in range(cell.target_valid_trials):
            result.append(
                _slot(
                    cell,
                    position=len(result),
                    round_index=slot_index,
                    block_index=block_index,
                    valid_slot_index=slot_index,
                )
            )
    validate_order(plan, result)
    return tuple(result)


def blocked_round_robin_order(
    plan: SchedulePlan,
    *,
    seed: int | None = None,
) -> tuple[ExecutionSlot, ...]:
    """Build a deterministic task-blocked, slot-round-robin candidate.

    In each valid-slot round, cells are grouped by exact task and phrasing.
    Block order is shuffled from the declared seed.  Every block contains the
    full eligible configuration-by-environment crossing; within-block order is
    rotated so the same configuration or environment is not always first.
    """

    resolved_seed = plan.order_seed if seed is None else seed
    if isinstance(resolved_seed, bool) or not isinstance(resolved_seed, int):
        raise TypeError("seed must be an integer")

    by_key: dict[tuple[str, str], list[Cell]] = defaultdict(list)
    for cell in plan.cells:
        by_key[(cell.task_id, cell.phrasing)].append(cell)

    result: list[ExecutionSlot] = []
    max_slots = max(cell.target_valid_trials for cell in plan.cells)
    global_block_index = 0
    for round_index in range(max_slots):
        keys = [
            key
            for key, cells in by_key.items()
            if any(cell.target_valid_trials > round_index for cell in cells)
        ]
        round_seed = int.from_bytes(
            hashlib.sha256(
                f"{resolved_seed}:{round_index}".encode("utf-8")
            ).digest()[:8],
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
            if not eligible:
                continue
            rotation = global_block_index % len(eligible)
            eligible = eligible[rotation:] + eligible[:rotation]
            for cell in eligible:
                result.append(
                    _slot(
                        cell,
                        position=len(result),
                        round_index=round_index,
                        block_index=global_block_index,
                        valid_slot_index=round_index,
                    )
                )
            global_block_index += 1

    validate_order(plan, result)
    return tuple(result)


def validate_order(
    plan: SchedulePlan,
    order: Sequence[ExecutionSlot],
) -> None:
    """Fail closed unless an order is a position-complete exact plan expansion."""

    if [slot.position for slot in order] != list(range(len(order))):
        raise ValueError("execution-slot positions must be contiguous and ordered")
    observed = Counter(slot.identity for slot in order)
    expected = expected_slot_multiset(plan)
    if observed != expected:
        missing = list((expected - observed).elements())[:5]
        extra = list((observed - expected).elements())[:5]
        raise ValueError(
            f"execution order differs from plan slots: missing={missing}, extra={extra}"
        )
    cells = {cell.cell_id: cell for cell in plan.cells}
    for slot in order:
        cell = cells[slot.cell_id]
        expected_fields = (
            cell.config_id,
            cell.env_id,
            cell.task_id,
            cell.family_id,
            cell.instance_id,
            cell.phrasing,
        )
        actual_fields = (
            slot.config_id,
            slot.env_id,
            slot.task_id,
            slot.family_id,
            slot.instance_id,
            slot.phrasing,
        )
        if actual_fields != expected_fields:
            raise ValueError(f"slot {slot.identity!r} contradicts its plan cell")


def order_digest(order: Iterable[ExecutionSlot]) -> str:
    """Hash the exact canonical execution-slot order."""

    payload = [asdict(slot) for slot in order]
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def block_balance_report(
    order: Sequence[ExecutionSlot],
) -> dict[str, object]:
    """Report exact crossing and host-subsequence balance by task block."""

    blocks: dict[tuple[int, int], list[ExecutionSlot]] = defaultdict(list)
    for slot in order:
        blocks[(slot.round_index, slot.block_index)].append(slot)

    incomplete_crossings = 0
    host_config_imbalances = 0
    for slots in blocks.values():
        configs = sorted({slot.config_id for slot in slots})
        envs = sorted({slot.env_id for slot in slots})
        observed = Counter((slot.config_id, slot.env_id) for slot in slots)
        if set(observed) != {(config, env) for config in configs for env in envs}:
            incomplete_crossings += 1
        by_host: dict[str, Counter[str]] = defaultdict(Counter)
        for slot in slots:
            by_host[slot.host_partition][slot.config_id] += 1
        if any(max(counts.values()) != min(counts.values()) for counts in by_host.values()):
            host_config_imbalances += 1

    adjacent_same_cell = sum(
        left.cell_id == right.cell_id
        for left, right in zip(order, order[1:], strict=False)
    )
    return {
        "slots": len(order),
        "blocks": len(blocks),
        "rounds": len({slot.round_index for slot in order}),
        "incomplete_configuration_environment_crossings": incomplete_crossings,
        "host_block_configuration_imbalances": host_config_imbalances,
        "adjacent_same_cell_pairs": adjacent_same_cell,
        "digest": order_digest(order),
    }


def prefix_counts(
    order: Sequence[ExecutionSlot],
    boundaries: Iterable[int],
) -> tuple[Mapping[str, object], ...]:
    """Return auditable dimension counts at caller-selected epoch boundaries."""

    reports: list[Mapping[str, object]] = []
    for boundary in boundaries:
        if isinstance(boundary, bool) or not isinstance(boundary, int):
            raise TypeError("epoch boundaries must be integers")
        if not 1 <= boundary <= len(order):
            raise ValueError("epoch boundary lies outside the execution order")
        prefix = order[:boundary]
        reports.append(
            {
                "end_position_exclusive": boundary,
                "environment": dict(sorted(Counter(s.env_id for s in prefix).items())),
                "configuration": dict(
                    sorted(Counter(s.config_id for s in prefix).items())
                ),
                "task_category": dict(
                    sorted(Counter(s.task_category for s in prefix).items())
                ),
                "phrasing": dict(sorted(Counter(s.phrasing for s in prefix).items())),
                "host_partition": dict(
                    sorted(Counter(s.host_partition for s in prefix).items())
                ),
            }
        )
    return tuple(reports)


def epoch_counts(
    order: Sequence[ExecutionSlot],
    boundaries: Iterable[int],
) -> tuple[Mapping[str, object], ...]:
    """Return non-overlapping balance reports for a complete epoch partition."""

    resolved = tuple(boundaries)
    if any(isinstance(value, bool) or not isinstance(value, int) for value in resolved):
        raise TypeError("epoch boundaries must be integers")
    if not resolved or resolved[-1] != len(order):
        raise ValueError("epoch boundaries must end at the complete execution order")
    if any(left >= right for left, right in zip((0, *resolved), resolved)):
        raise ValueError("epoch boundaries must be strictly increasing")

    reports: list[Mapping[str, object]] = []
    start = 0
    for epoch_index, end in enumerate(resolved):
        slots = order[start:end]
        reports.append(
            {
                "epoch_index": epoch_index,
                "start_position_inclusive": start,
                "end_position_exclusive": end,
                "environment": dict(
                    sorted(Counter(slot.env_id for slot in slots).items())
                ),
                "configuration": dict(
                    sorted(Counter(slot.config_id for slot in slots).items())
                ),
                "task_category": dict(
                    sorted(Counter(slot.task_category for slot in slots).items())
                ),
                "phrasing": dict(
                    sorted(Counter(slot.phrasing for slot in slots).items())
                ),
                "host_partition": dict(
                    sorted(Counter(slot.host_partition for slot in slots).items())
                ),
                "blocks": len({(slot.round_index, slot.block_index) for slot in slots}),
            }
        )
        start = end
    return tuple(reports)
