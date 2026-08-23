"""Validate the accepted, outcome-blind D-013 V2 family design slate.

The slate is a design contract, not task qualification. It prevents later
authors from quietly changing domains, family count, instance count, or
cross-cutting coverage while Q0-Q4 evidence is being assembled.
"""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path


SCHEMA_VERSION = "1.0.0"
DEMANDS = {
    "discovery_localization",
    "command_composition",
    "diagnosis_recovery",
    "preservation_scope",
    "verification_tests",
    "environment_adaptation",
}
EXPOSURES = {"STRONG", "CONDITIONAL", "ABSENT"}
EXPECTED_FAMILIES = {
    "A": {"C01", "C04"},
    "B": {"C02", "C05"},
    "C": {"C03", "C06"},
    "D": {"C07", "C08"},
    "E": {"C09", "C10"},
    "F": {"C11", "C12"},
}


class FamilySlateError(ValueError):
    pass


@dataclass(frozen=True)
class FamilySlate:
    family_ids: tuple[str, ...]
    domain_ids: tuple[str, ...]
    planned_instance_count: int


def _nonempty(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise FamilySlateError(f"{field} must be a non-empty trimmed string")
    return value


def load_family_slate(path: Path) -> FamilySlate:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise FamilySlateError(f"cannot load family slate: {exc}") from exc
    if not isinstance(raw, dict) or set(raw) != {
        "schema_version", "status", "decision", "construct", "domains",
        "families", "qualification", "harness_prerequisites",
    }:
        raise FamilySlateError("family slate has unknown or missing fields")
    if (
        raw["schema_version"] != SCHEMA_VERSION
        or raw["status"] != "accepted_design_unqualified"
        or raw["decision"] != "D-013"
        or raw["construct"]
        != "practitioner_facing_agent_bundle_reliability_across_execution_contexts"
    ):
        raise FamilySlateError("family slate identity is not the accepted D-013 design")

    domains = raw["domains"]
    if not isinstance(domains, list) or len(domains) != 6:
        raise FamilySlateError("exactly six domains are required")
    domain_ids: list[str] = []
    for domain in domains:
        if not isinstance(domain, dict) or set(domain) != {"id", "name", "weight"}:
            raise FamilySlateError("domain has unknown or missing fields")
        domain_id = _nonempty(domain["id"], "domain.id")
        _nonempty(domain["name"], "domain.name")
        if domain["weight"] != "1/6":
            raise FamilySlateError("every accepted domain weight must be 1/6")
        domain_ids.append(domain_id)
    if set(domain_ids) != set(EXPECTED_FAMILIES) or len(set(domain_ids)) != 6:
        raise FamilySlateError("domain IDs must be exactly A-F")

    families = raw["families"]
    if not isinstance(families, list) or len(families) != 12:
        raise FamilySlateError("exactly twelve families are required")
    by_domain: dict[str, set[str]] = defaultdict(set)
    demand_domains: dict[str, set[str]] = defaultdict(set)
    demand_families: dict[str, set[str]] = defaultdict(set)
    strong_demands: set[str] = set()
    family_ids: list[str] = []
    expected_fields = {
        "id", "domain", "origin", "title", "workflow_analogue",
        "context_link", "not_measured", "instances", "oracle",
        "counterpolicies", "demands", "qualification_status",
    }
    for family in families:
        if not isinstance(family, dict) or set(family) != expected_fields:
            raise FamilySlateError("family has unknown or missing fields")
        family_id = _nonempty(family["id"], "family.id")
        domain_id = _nonempty(family["domain"], f"{family_id}.domain")
        if family["origin"] not in {"existing_v1_fixture", "new_v2_family"}:
            raise FamilySlateError(f"{family_id}.origin is invalid")
        if family["qualification_status"] != "NOT_ASSESSED":
            raise FamilySlateError(f"{family_id} must remain unqualified")
        for field in ("title", "workflow_analogue", "context_link", "not_measured", "oracle"):
            _nonempty(family[field], f"{family_id}.{field}")
        instances = family["instances"]
        if not isinstance(instances, list) or instances != [
            f"{family_id}-I01", f"{family_id}-I02", f"{family_id}-I03"
        ]:
            raise FamilySlateError(f"{family_id} needs exactly three canonical instances")
        counterpolicies = family["counterpolicies"]
        if (
            not isinstance(counterpolicies, list)
            or len(counterpolicies) < 4
            or any(not isinstance(item, str) or not item for item in counterpolicies)
        ):
            raise FamilySlateError(f"{family_id} needs at least four counterpolicies")
        demands = family["demands"]
        if not isinstance(demands, dict) or set(demands) != DEMANDS:
            raise FamilySlateError(f"{family_id} demand map is incomplete")
        if any(value not in EXPOSURES for value in demands.values()):
            raise FamilySlateError(f"{family_id} has an invalid demand exposure")
        for demand, exposure in demands.items():
            if exposure != "ABSENT":
                demand_domains[demand].add(domain_id)
                demand_families[demand].add(family_id)
            if exposure == "STRONG":
                strong_demands.add(demand)
        family_ids.append(family_id)
        by_domain[domain_id].add(family_id)

    if len(set(family_ids)) != 12 or by_domain != EXPECTED_FAMILIES:
        raise FamilySlateError("family IDs must match the accepted two-per-domain roster")
    for demand in DEMANDS:
        if len(demand_families[demand]) < 2 or len(demand_domains[demand]) < 2:
            raise FamilySlateError(f"{demand} does not recur across families and domains")
        if demand not in strong_demands:
            raise FamilySlateError(f"{demand} lacks a STRONG exposure")

    qualification = raw["qualification"]
    if qualification != {
        "required_gates": ["Q0", "Q1", "Q2", "Q3", "Q4"],
        "current_bank_admitted": False,
        "outcome_based_selection_forbidden": True,
        "fresh_pilot_after_outcome_relevant_change": True,
    }:
        raise FamilySlateError("qualification contract differs from D-013")
    prerequisites = raw["harness_prerequisites"]
    if not isinstance(prerequisites, list) or len(prerequisites) < 2 or any(
        not isinstance(item, str) or not item for item in prerequisites
    ):
        raise FamilySlateError("harness prerequisites must be explicit")

    return FamilySlate(tuple(sorted(family_ids)), tuple(sorted(domain_ids)), 3)
