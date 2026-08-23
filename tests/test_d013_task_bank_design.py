from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path

import pytest

from analysis.d013_task_bank_design import (
    REGISTERED_CONFIG_IDS,
    REGISTERED_ENVIRONMENT_IDS,
    build_instance_schedule,
)
from harness.scheduler import (
    AGY_CONFIG_SPECS,
    CLAUDE_CONFIGS,
    CODEX_CONFIGS,
    ENVIRONMENTS as SCHEDULER_ENVIRONMENTS,
)


CONFIGS = REGISTERED_CONFIG_IDS
ENVIRONMENTS = REGISTERED_ENVIRONMENT_IDS
INSTANCES = ("I01", "I02", "I03")


def _schedule(n: int):
    return build_instance_schedule(
        family_id="F06",
        instance_ids=INSTANCES,
        config_ids=CONFIGS,
        environment_ids=ENVIRONMENTS,
        repetitions_per_cell=n,
    )


@pytest.mark.parametrize("n", [3, 5, 10])
def test_each_cell_is_balanced_and_equal_instance_weighted(n: int) -> None:
    cells: dict[tuple[str, str], list] = defaultdict(list)
    for assignment in _schedule(n):
        cells[(assignment.config_id, assignment.environment_id)].append(
            assignment
        )

    assert len(cells) == 35
    for rows in cells.values():
        assert sorted(row.valid_slot_index for row in rows) == list(range(n))
        counts = Counter(row.instance_id for row in rows)
        assert set(counts) == set(INSTANCES)
        assert max(counts.values()) - min(counts.values()) <= 1
        assert sum(row.analysis_weight for row in rows) == pytest.approx(1.0)
        for instance_id in INSTANCES:
            assert sum(
                row.analysis_weight
                for row in rows
                if row.instance_id == instance_id
            ) == pytest.approx(1 / 3)


@pytest.mark.parametrize("n", [3, 5, 10])
def test_assignment_is_matched_across_all_environments(n: int) -> None:
    by_config_rep: dict[tuple[str, int], dict[str, str]] = defaultdict(dict)
    for assignment in _schedule(n):
        by_config_rep[
            (assignment.config_id, assignment.valid_slot_index)
        ][assignment.environment_id] = assignment.instance_id

    assert len(by_config_rep) == len(CONFIGS) * n
    for environment_map in by_config_rep.values():
        assert set(environment_map) == set(ENVIRONMENTS)
        assert len(set(environment_map.values())) == 1


@pytest.mark.parametrize("n", [5, 10])
def test_remainder_assignments_are_counterbalanced_over_configs(n: int) -> None:
    schedule = _schedule(n)
    for environment in ENVIRONMENTS:
        counts = Counter(
            row.instance_id
            for row in schedule
            if row.environment_id == environment
        )
        assert max(counts.values()) - min(counts.values()) <= 1


def test_caller_order_does_not_change_schedule() -> None:
    forward = build_instance_schedule(
        family_id="F06",
        instance_ids=INSTANCES,
        config_ids=CONFIGS,
        environment_ids=ENVIRONMENTS,
        repetitions_per_cell=5,
    )
    reversed_input = build_instance_schedule(
        family_id="F06",
        instance_ids=reversed(INSTANCES),
        config_ids=reversed(CONFIGS),
        environment_ids=reversed(ENVIRONMENTS),
        repetitions_per_cell=5,
    )
    assert reversed_input == forward


def test_one_fixed_fixture_is_supported_without_false_instance_breadth() -> None:
    schedule = build_instance_schedule(
        family_id="C01",
        instance_ids=("fixed",),
        config_ids=CONFIGS,
        environment_ids=ENVIRONMENTS,
        repetitions_per_cell=2,
    )
    assert len(schedule) == 7 * 5 * 2
    assert {row.instance_id for row in schedule} == {"fixed"}
    assert {row.analysis_weight for row in schedule} == {0.5}


def test_evidence_prototype_is_not_imported_by_frozen_scheduler() -> None:
    repo = Path(__file__).resolve().parents[1]
    scheduler_source = (repo / "harness" / "scheduler.py").read_text(
        encoding="utf-8"
    )
    assert "d013_task_bank_design" not in scheduler_source


def test_candidate_roster_matches_frozen_scheduler() -> None:
    scheduler_configs = tuple(
        config.config_id for config in (*CLAUDE_CONFIGS, *CODEX_CONFIGS)
    ) + tuple(config_id for config_id, _ in AGY_CONFIG_SPECS)
    assert REGISTERED_CONFIG_IDS == scheduler_configs
    assert set(REGISTERED_ENVIRONMENT_IDS) == set(SCHEDULER_ENVIRONMENTS)


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"family_id": ""}, "family_id"),
        ({"instance_ids": ()}, "instance_ids"),
        ({"instance_ids": ("I01", "I01")}, "unique"),
        ({"instance_ids": ("I01", "I02")}, "one fixed fixture"),
        ({"repetitions_per_cell": 2}, "exercise every frozen instance"),
        ({"config_ids": ("CFG1", "CFG1")}, "unique"),
        ({"config_ids": CONFIGS[:-1]}, "exact registered seven"),
        ({"environment_ids": ()}, "environment_ids"),
        (
            {"environment_ids": ENVIRONMENTS[:-1]},
            "exact registered five",
        ),
    ],
)
def test_invalid_candidate_schedules_fail_closed(kwargs: dict, message: str) -> None:
    arguments = {
        "family_id": "F06",
        "instance_ids": INSTANCES,
        "config_ids": CONFIGS,
        "environment_ids": ENVIRONMENTS,
        "repetitions_per_cell": 3,
    }
    arguments.update(kwargs)
    with pytest.raises(ValueError, match=message):
        build_instance_schedule(**arguments)
