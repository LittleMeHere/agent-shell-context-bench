"""Outcome-blind instance-assignment prototype for decision D-013.

This module does not modify the frozen V1 task roster or collection scheduler.
It makes one candidate D-013 invariant executable: frozen instances are
rotated deterministically within a family, matched across environments, and
weighted equally within each family even when the repetition count is not a
multiple of the instance count.

The accepted D-013 decision may replace this algorithm. Until then, this file
is evidence code only and must not be imported by ``harness.scheduler``.
It binds instances to valid slots; it does not randomize execution order,
define missing-data handling, or justify treating matched slots as independent.
"""

from __future__ import annotations

import hashlib
from collections import Counter
from dataclasses import dataclass
from typing import Iterable


REGISTERED_CONFIG_IDS = tuple(f"CFG{i}" for i in range(1, 8))
REGISTERED_ENVIRONMENT_IDS = (
    "windows_powershell",
    "windows_pwsh7",
    "windows_wsl2",
    "linux_native",
    "macos_actions",
)


@dataclass(frozen=True)
class InstanceAssignment:
    """One candidate family/configuration/environment valid-slot binding."""

    family_id: str
    config_id: str
    environment_id: str
    valid_slot_index: int
    instance_id: str
    analysis_weight: float


def _canonical_ids(label: str, values: Iterable[str]) -> tuple[str, ...]:
    ids = tuple(sorted(values))
    if not ids:
        raise ValueError(f"{label} must not be empty")
    if any(not value or value.strip() != value for value in ids):
        raise ValueError(f"{label} must contain non-empty, trimmed identifiers")
    if len(set(ids)) != len(ids):
        raise ValueError(f"{label} must contain unique identifiers")
    return ids


def _family_offset(family_id: str, instance_count: int) -> int:
    """Return a stable rotation offset, not an inferential randomization."""

    digest = hashlib.sha256(family_id.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") % instance_count


def build_instance_schedule(
    *,
    family_id: str,
    instance_ids: Iterable[str],
    config_ids: Iterable[str],
    environment_ids: Iterable[str],
    repetitions_per_cell: int,
) -> tuple[InstanceAssignment, ...]:
    """Build the candidate D-013 instance schedule for one task family.

    Identifiers are canonicalized so caller ordering cannot change the plan.
    For a configuration, the instance sequence is reused in every environment;
    therefore ``(family, config, valid_slot)`` always names the same instance
    in every registered context. Configuration offsets rotate which instances
    receive remainder valid slots.

    ``analysis_weight`` makes each frozen instance contribute exactly
    ``1 / instance_count`` to its family-cell mean. The weights in every
    family/configuration/environment cell sum to one.
    """

    if not family_id or family_id.strip() != family_id:
        raise ValueError("family_id must be a non-empty, trimmed identifier")
    instances = _canonical_ids("instance_ids", instance_ids)
    configs = _canonical_ids("config_ids", config_ids)
    environments = _canonical_ids("environment_ids", environment_ids)
    if configs != tuple(sorted(REGISTERED_CONFIG_IDS)):
        raise ValueError(
            "config_ids must equal the exact registered seven-configuration "
            "roster"
        )
    if environments != tuple(sorted(REGISTERED_ENVIRONMENT_IDS)):
        raise ValueError(
            "environment_ids must equal the exact registered five-environment "
            "roster"
        )
    if repetitions_per_cell < 1:
        raise ValueError("repetitions_per_cell must be positive")
    if len(instances) == 2:
        raise ValueError(
            "candidate D-013 policy permits one fixed fixture or at least "
            "three frozen instances"
        )
    if repetitions_per_cell < len(instances):
        raise ValueError(
            "repetitions_per_cell must exercise every frozen instance in "
            "every family/configuration/environment cell"
        )

    instance_count = len(instances)
    base_offset = _family_offset(family_id, instance_count)
    assignments: list[InstanceAssignment] = []

    for config_index, config_id in enumerate(configs):
        offset = (base_offset + config_index) % instance_count
        sequence = tuple(
            instances[(offset + repetition) % instance_count]
            for repetition in range(repetitions_per_cell)
        )
        counts = Counter(sequence)

        for environment_id in environments:
            for valid_slot_index, instance_id in enumerate(sequence):
                analysis_weight = 1.0 / (
                    instance_count * counts[instance_id]
                )
                assignments.append(
                    InstanceAssignment(
                        family_id=family_id,
                        config_id=config_id,
                        environment_id=environment_id,
                        valid_slot_index=valid_slot_index,
                        instance_id=instance_id,
                        analysis_weight=analysis_weight,
                    )
                )

    return tuple(assignments)
