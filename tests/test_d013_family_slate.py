from __future__ import annotations

import json
from pathlib import Path

import pytest

from analysis.d013_family_slate import FamilySlateError, load_family_slate


ROOT = Path(__file__).resolve().parents[1]
SLATE = ROOT / "config" / "v2-family-slate.accepted.json"


def test_accepted_family_slate_has_six_domains_twelve_families_three_instances():
    slate = load_family_slate(SLATE)
    assert slate.domain_ids == ("A", "B", "C", "D", "E", "F")
    assert slate.family_ids == tuple(f"C{i:02d}" for i in range(1, 13))
    assert slate.planned_instance_count == 3


@pytest.mark.parametrize("mutation", ["drop_family", "rename_instance", "weaken_recurrence", "admit"])
def test_slate_drift_fails_closed(tmp_path: Path, mutation: str):
    raw = json.loads(SLATE.read_text(encoding="utf-8"))
    if mutation == "drop_family":
        raw["families"].pop()
    elif mutation == "rename_instance":
        raw["families"][0]["instances"][0] = "fixture"
    elif mutation == "weaken_recurrence":
        for family in raw["families"]:
            family["demands"]["diagnosis_recovery"] = "ABSENT"
    else:
        raw["qualification"]["current_bank_admitted"] = True
    candidate = tmp_path / "slate.json"
    candidate.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(FamilySlateError):
        load_family_slate(candidate)
