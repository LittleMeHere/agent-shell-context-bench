from __future__ import annotations

import json
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest
import yaml

from analysis.d013_oracle_qualification import _evaluate
from analysis.d013_q2_qualification import (
    H1,
    POLICY_SURFACES,
    SECONDARY,
    accepted_policy_names,
    apply_alternate_oracle,
    apply_h1_counterpolicy,
)
from harness.fixture_setup import prepare_fixture
from harness.fs import local_snapshot
from harness.types import SandboxHandle
from tests.test_d013_oracle_qualification import LocalOracleEnvironment


ROOT = Path(__file__).resolve().parents[1]
SLATE = json.loads(
    (ROOT / "config" / "v2-family-slate.accepted.json").read_text(
        encoding="utf-8"
    )
)
TASK_PATHS = tuple(sorted((ROOT / "tasks" / "v2").glob("*.yaml")))
TASKS = {
    path.stem.split("_", 1)[0]: yaml.safe_load(path.read_text(encoding="utf-8"))
    for path in TASK_PATHS
}


def _case(task: dict, root: Path):
    for entry in task["preconditions"].get("initial_files", []):
        target = root / entry["path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(entry.get("content", ""), encoding="utf-8", newline="")
    environment = LocalOracleEnvironment()
    sandbox = SandboxHandle(task["id"], 0, "local", str(root), root)
    prepare_fixture(environment, sandbox, task["preconditions"])
    return environment, sandbox, local_snapshot(root)


def _passes(environment, sandbox, task, baseline) -> bool:
    passed, _ = _evaluate(environment, sandbox, task, baseline)
    return passed


def test_q2_surface_map_exactly_matches_accepted_slate() -> None:
    accepted = accepted_policy_names(SLATE)
    assert set(POLICY_SURFACES) == set(accepted) == {
        f"C{number:02d}" for number in range(1, 13)
    }
    for family, policies in accepted.items():
        assert tuple(POLICY_SURFACES[family]) == policies
        assert set(POLICY_SURFACES[family].values()) <= {H1, SECONDARY}


@pytest.mark.parametrize("task_id", sorted(TASKS))
def test_every_instance_accepts_an_independent_valid_solution(
    task_id: str, tmp_path: Path
) -> None:
    task = TASKS[task_id]
    environment, sandbox, baseline = _case(task, tmp_path)
    apply_alternate_oracle(environment, sandbox, task)
    assert _passes(environment, sandbox, task, baseline)


H1_CASES = tuple(
    (task_id, policy)
    for task_id, task in sorted(TASKS.items())
    for policy, surface in POLICY_SURFACES[task["family_id"]].items()
    if surface == H1
)


@pytest.mark.parametrize(
    ("task_id", "policy"),
    H1_CASES,
    ids=lambda value: str(value),
)
def test_registered_h1_counterpolicies_fail_closed(
    task_id: str, policy: str, tmp_path: Path
) -> None:
    task = TASKS[task_id]
    environment, sandbox, baseline = _case(task, tmp_path)
    if task["family_id"] == "C11" and policy == "leave_process_running":
        from analysis.d013_oracle_qualification import apply_oracle

        apply_oracle(environment, sandbox, task)
        port = int((tmp_path / "port.txt").read_text(encoding="utf-8"))
        child = subprocess.Popen(
            [sys.executable, "service.py", str(port)],
            cwd=tmp_path,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            for _ in range(50):
                with socket.socket() as probe:
                    if probe.connect_ex(("127.0.0.1", port)) == 0:
                        break
                time.sleep(0.05)
            else:
                raise AssertionError("counter-policy service did not start")
            assert not _passes(environment, sandbox, task, baseline)
        finally:
            child.terminate()
            child.wait(timeout=5)
        return

    apply_h1_counterpolicy(environment, sandbox, task, policy)
    assert not _passes(environment, sandbox, task, baseline)


SECONDARY_CASES = tuple(
    (task_id, policy)
    for task_id, task in sorted(TASKS.items())
    for policy, surface in POLICY_SURFACES[task["family_id"]].items()
    if surface == SECONDARY
)


@pytest.mark.parametrize(
    ("task_id", "policy"),
    SECONDARY_CASES,
    ids=lambda value: str(value),
)
def test_secondary_only_policies_are_not_misrepresented_as_h1(
    task_id: str, policy: str, tmp_path: Path
) -> None:
    """The same correct final state can coexist with transient/out-of-sandbox
    behavior. H1 therefore passes; command traces and canaries own the policy."""
    from analysis.d013_oracle_qualification import apply_oracle

    task = TASKS[task_id]
    environment, sandbox, baseline = _case(task, tmp_path)
    apply_oracle(environment, sandbox, task)
    assert _passes(environment, sandbox, task, baseline)
    with pytest.raises(ValueError, match="not an H1 counter-policy"):
        apply_h1_counterpolicy(environment, sandbox, task, policy)
