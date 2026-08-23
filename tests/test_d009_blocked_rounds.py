from __future__ import annotations

import dataclasses

import pytest

from analysis.d009_blocked_rounds import (
    block_balance_report,
    blocked_round_robin_order,
    epoch_counts,
    order_digest,
    prefix_counts,
    validate_order,
    whole_cell_order,
)
from harness.scheduler import (
    V2_PILOT_EPOCH_BOUNDARIES,
    V2_PILOT_PHASE,
    build_plan,
    v2_pilot_epoch_for_position,
)


@pytest.fixture(scope="module")
def plan(frozen_runtime_binding):
    return build_plan(
        V2_PILOT_PHASE, runtime_binding=frozen_runtime_binding
    )


def test_orders_expand_the_exact_v2_slot_roster(plan) -> None:
    whole = whole_cell_order(plan)
    blocked = blocked_round_robin_order(plan)
    assert len(whole) == len(blocked) == 720
    assert {(slot.cell_id, slot.valid_slot_index) for slot in whole} == {
        (slot.cell_id, slot.valid_slot_index) for slot in blocked
    }


def test_blocked_order_is_reproducible_seeded_and_digest_bound(plan) -> None:
    first = blocked_round_robin_order(plan, seed=91)
    second = blocked_round_robin_order(plan, seed=91)
    third = blocked_round_robin_order(plan, seed=92)
    assert first == second
    assert order_digest(first) == order_digest(second)
    assert order_digest(first) != order_digest(third)


def test_production_plan_embeds_the_exact_accepted_blocked_order(plan) -> None:
    candidate = blocked_round_robin_order(plan)
    assert plan.execution_slots is not None
    assert [
        (
            slot.position,
            slot.round_index,
            slot.block_index,
            slot.valid_slot_index,
            slot.cell_id,
        )
        for slot in candidate
    ] == [
        (
            slot.position,
            slot.round_index,
            slot.block_index,
            slot.valid_slot_index,
            slot.cell_id,
        )
        for slot in plan.execution_slots
    ]


def test_blocked_candidate_separates_repeated_cells_and_crosses_blocks(plan) -> None:
    whole_report = block_balance_report(whole_cell_order(plan))
    blocked_report = block_balance_report(blocked_round_robin_order(plan))
    assert whole_report["adjacent_same_cell_pairs"] == 180
    assert blocked_report == {
        "slots": 720,
        "blocks": 72,
        "rounds": 2,
        "incomplete_configuration_environment_crossings": 0,
        "host_block_configuration_imbalances": 0,
        "adjacent_same_cell_pairs": 0,
        "digest": blocked_report["digest"],
    }


def test_each_block_is_balanced_inside_every_host_partition(plan) -> None:
    order = blocked_round_robin_order(plan)
    by_block = {}
    for slot in order:
        by_block.setdefault((slot.round_index, slot.block_index), []).append(slot)
    for slots in by_block.values():
        assert len({slot.task_id for slot in slots}) == 1
        assert len({slot.phrasing for slot in slots}) == 1
        for host in {slot.host_partition for slot in slots}:
            host_slots = [slot for slot in slots if slot.host_partition == host]
            counts = {
                config: sum(slot.config_id == config for slot in host_slots)
                for config in {slot.config_id for slot in host_slots}
            }
            assert len(set(counts.values())) == 1


def test_validator_rejects_missing_duplicate_and_forged_coordinates(plan) -> None:
    order = list(blocked_round_robin_order(plan))
    with pytest.raises(ValueError, match="positions"):
        validate_order(plan, order[1:])

    duplicate = list(order)
    duplicate[-1] = dataclasses.replace(
        duplicate[-1],
        cell_id=duplicate[0].cell_id,
        valid_slot_index=duplicate[0].valid_slot_index,
    )
    with pytest.raises(ValueError, match="differs from plan slots"):
        validate_order(plan, duplicate)

    forged = list(order)
    forged[0] = dataclasses.replace(forged[0], config_id="CFG99")
    with pytest.raises(ValueError, match="contradicts"):
        validate_order(plan, forged)


def test_prefix_report_uses_explicit_caller_boundaries(plan) -> None:
    order = blocked_round_robin_order(plan)
    reports = prefix_counts(order, [10, 540, 720])
    assert [row["end_position_exclusive"] for row in reports] == [10, 540, 720]
    assert sum(reports[-1]["environment"].values()) == 720
    assert reports[-1]["task_category"] == {
        "capability": 360,
        "seeded_error": 360,
    }
    with pytest.raises(ValueError, match="outside"):
        prefix_counts(order, [0])


def test_fixed_180_slot_epochs_are_exactly_context_and_config_balanced(plan) -> None:
    reports = epoch_counts(
        blocked_round_robin_order(plan),
        V2_PILOT_EPOCH_BOUNDARIES,
    )
    assert len(reports) == 4
    for index, report in enumerate(reports):
        assert report["epoch_index"] == index
        assert report["end_position_exclusive"] - report["start_position_inclusive"] == 180
        assert report["environment"] == {
            "linux_native": 36,
            "macos_actions": 36,
            "windows_powershell": 36,
            "windows_pwsh7": 36,
            "windows_wsl2": 36,
        }
        assert report["configuration"] == {"CFG1": 90, "CFG2": 90}
        assert report["host_partition"] == {
            "linux_native": 36,
            "macos_actions": 36,
            "windows_local": 108,
        }
        assert report["blocks"] == 18
    assert [report["task_category"] for report in reports] == [
        {"capability": 120, "seeded_error": 60},
        {"capability": 120, "seeded_error": 60},
        {"capability": 120, "seeded_error": 60},
        {"seeded_error": 180},
    ]
    with pytest.raises(ValueError, match="complete execution order"):
        epoch_counts(blocked_round_robin_order(plan), [180, 360])
    with pytest.raises(ValueError, match="strictly increasing"):
        epoch_counts(blocked_round_robin_order(plan), [180, 180, 720])
    assert [v2_pilot_epoch_for_position(position) for position in (0, 179, 180, 719)] == [
        0,
        0,
        1,
        3,
    ]
    with pytest.raises(ValueError, match="outside"):
        v2_pilot_epoch_for_position(720)
