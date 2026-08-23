from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from harness.checks import evaluate_checks
from harness.fixture_setup import prepare_fixture
from harness.fs import local_snapshot
from harness.runner import load_task
from tests.test_fixture_setup import LocalArgvEnvironment, _sandbox


ROOT = Path(__file__).resolve().parents[1]
TASKS = sorted((ROOT / "tasks" / "v2").glob("C0[78]-I*.yaml"))


def _materialize(root: Path, task: dict) -> None:
    for entry in task["preconditions"]["initial_files"]:
        target = root / entry["path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(entry.get("content", ""), encoding="utf-8", newline="")


def _evaluate(root: Path, task: dict, env: LocalArgvEnvironment, baseline) -> bool:
    passed, _ = evaluate_checks(
        local_snapshot(root),
        task["success_checks"],
        sandbox_host_root=root,
        environment_exec=env.exec,
        environment_cwd=str(root),
        snapshot_before=baseline,
    )
    return passed


def _solve(root: Path, task_id: str, env: LocalArgvEnvironment) -> None:
    if task_id == "C07-I01":
        (root / "settings.py").write_text(
            "def settings():\n"
            "    return {'timeout': 60, 'retries': 5, 'endpoint': '/v2', 'backoff': 2}\n",
            encoding="utf-8",
        )
        path = "settings.py"
    elif task_id == "C07-I02":
        (root / "routes.json").write_text(
            '{"root":"/","health":"/healthz","items":"/v2/items"}\n',
            encoding="utf-8",
        )
        path = "routes.json"
    elif task_id == "C07-I03":
        (root / "worker.py").write_text(
            "def policy():\n"
            "    return {'concurrency': 8, 'queue': 'critical', "
            "'retry_limit': 6, 'jitter': True}\n",
            encoding="utf-8",
        )
        path = "worker.py"
    else:
        bad_paths = {
            "C08-I01": "bad.txt",
            "C08-I02": "config.ini",
            "C08-I03": "src/limit.py",
        }
        result = env.exec(
            ["git", "restore", "--", bad_paths[task_id]],
            cwd=str(root), timeout=30, env=None,
        )
        assert result.returncode == 0, result.stderr
        return
    result = env.exec(["git", "add", "--", path], cwd=str(root), timeout=30, env=None)
    assert result.returncode == 0, result.stderr


def test_v2_git_roster_has_three_instances_per_family():
    assert len(TASKS) == 6
    loaded = [load_task(path) for path in TASKS]
    assert {task["id"] for task in loaded} == {
        f"C{family:02d}-I{instance:02d}"
        for family in (7, 8)
        for instance in range(1, 4)
    }
    for task in loaded:
        assert task["id"] == f"{task['family_id']}-{task['instance_id']}"


@pytest.mark.parametrize("path", TASKS, ids=lambda path: path.stem)
def test_v2_git_noop_fails_and_portable_oracle_passes(path: Path, tmp_path: Path):
    task = yaml.safe_load(path.read_text(encoding="utf-8"))
    _materialize(tmp_path, task)
    env = LocalArgvEnvironment()
    prepare_fixture(env, _sandbox(tmp_path), task["preconditions"])
    baseline = local_snapshot(tmp_path)

    assert _evaluate(tmp_path, task, env, baseline) is False
    _solve(tmp_path, task["id"], env)
    assert _evaluate(tmp_path, task, env, baseline) is True
    extra = tmp_path / "unexpected.tmp"
    extra.write_text("extra", encoding="utf-8")
    assert _evaluate(tmp_path, task, env, baseline) is False
    extra.unlink()
    protected = next(
        check["path"]
        for check in task["success_checks"]
        if check["type"] in {"file_content_equals", "file_unchanged"}
    )
    with (tmp_path / protected).open("a", encoding="utf-8") as handle:
        handle.write("corruption")
    assert _evaluate(tmp_path, task, env, baseline) is False
