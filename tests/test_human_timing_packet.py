from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.human_timing_packet import (
    EXPECTED_CONFIGS,
    STRATUM_BY_TASK,
    build_packet,
    discover_candidates,
    select_balanced_cases,
)


def _write_trial(root: Path, config_id: str, task_id: str, phrasing: str, replicate: int) -> None:
    path = root / config_id / task_id / f"trial_{replicate}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "schema_version": "1.7.0",
                "trial": {"task_id": task_id, "phrasing": phrasing},
                "schedule": {"config_id": config_id},
                "prompt": f"prompt {task_id}",
                "agent": {
                    "transcript": f"transcript {task_id} {replicate}",
                    "process": {"returncode": 0, "timed_out": False},
                },
                "outcome": {"success": replicate % 2 == 0},
                "validity": {"valid": True},
            }
        ),
        encoding="utf-8",
    )


def _roster(root: Path) -> None:
    for config_id in EXPECTED_CONFIGS:
        for task_id, phrasing in STRATUM_BY_TASK:
            for replicate in (1, 2):
                _write_trial(root, config_id, task_id, phrasing, replicate)


def test_selects_one_blinded_case_per_crossing(tmp_path: Path) -> None:
    source = tmp_path / "source"
    _roster(source)
    candidates = discover_candidates([source])
    selected = select_balanced_cases(candidates, seed=41)

    assert len(candidates) == 70
    assert len(selected) == 35
    assert len({(case.config_id, case.stratum) for case in selected}) == 35
    assert selected == select_balanced_cases(candidates, seed=41)


def test_builds_private_packet_without_identity_labels(tmp_path: Path) -> None:
    source = tmp_path / "source"
    output = tmp_path / "private-output"
    _roster(source)
    packet = build_packet(source_roots=[source], output_dir=output, seed=41)

    assert packet["case_count"] == 35
    assert (output / "timing-exercise.html").is_file()
    assert (output / "private-provenance.json").is_file()
    html_text = (output / "timing-exercise.html").read_text(encoding="utf-8")
    public_cases = json.dumps(packet["cases"])
    assert '"config_id"' not in public_cases
    assert '"env_id"' not in public_cases
    assert '"agent_id"' not in public_cases
    assert '"model_id"' not in public_cases
    assert "evidence_loading_ms" in html_text
    assert "active_coding_ms" in html_text


def test_rejects_nonzero_process_and_incomplete_roster(tmp_path: Path) -> None:
    source = tmp_path / "source"
    _roster(source)
    victim = next(source.rglob("trial_1.json"))
    raw = json.loads(victim.read_text(encoding="utf-8"))
    raw["agent"]["process"]["returncode"] = 1
    victim.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ValueError, match="did not exit cleanly"):
        discover_candidates([source])

    victim.unlink()
    candidates = discover_candidates([source])
    with pytest.raises(ValueError, match="fewer than two replicates"):
        select_balanced_cases(candidates, seed=41)
