from __future__ import annotations

import json
import socket
import subprocess
import sys
import time
import zipfile
from pathlib import Path

import pytest
import yaml

from harness.checks import evaluate_checks
from harness.fixture_setup import prepare_fixture
from harness.fs import local_snapshot
from harness.runner import load_task
from tests.test_fixture_setup import LocalArgvEnvironment, _sandbox


ROOT = Path(__file__).resolve().parents[1]
TASKS = sorted((ROOT / "tasks" / "v2").glob("C1[012]-I*.yaml"))


PACKAGE_SPECS = {
    "C10-I01": ("dist/greeting.zip", "greeting", "greeting", "1.0.0"),
    "C10-I02": ("dist/metrics_plugin.zip", "metrics_plugin", "metrics-plugin", "2.1.0"),
    "C10-I03": ("dist/transform.zip", "transform", "transform", "0.4.0"),
}
SERVICE_CONFIGS = {
    "C11-I01": {"path": "/health", "body": "healthy"},
    "C11-I02": {"path": "/ready", "body": "ready-v2"},
    "C11-I03": {"path": "/live", "body": "alive"},
}
JOB_ENVS = {
    "C12-I01": {"JOB_MODE": "sum", "JOB_TOKEN": "violet-17"},
    "C12-I02": {"JOB_MODE": "max", "JOB_TOKEN": "amber-29"},
    "C12-I03": {"JOB_MODE": "count", "JOB_TOKEN": "silver-41"},
}


def _materialize(root: Path, task: dict) -> None:
    for entry in task["preconditions"]["initial_files"]:
        target = root / entry["path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(entry.get("content", ""), encoding="utf-8", newline="")


def _passes(
    root: Path,
    task: dict,
    env: LocalArgvEnvironment,
    baseline,
    *,
    stop_on_failure: bool = False,
) -> bool:
    passed, _ = evaluate_checks(
        local_snapshot(root), task["success_checks"], sandbox_host_root=root,
        environment_exec=env.exec, environment_cwd=str(root),
        snapshot_before=baseline,
        stop_on_failure=stop_on_failure,
    )
    return passed


def _solve(root: Path, task_id: str, env: LocalArgvEnvironment) -> None:
    if task_id in PACKAGE_SPECS:
        archive_rel, package_dir, metadata_name, version = PACKAGE_SPECS[task_id]
        archive = root / archive_rel
        archive.parent.mkdir(parents=True, exist_ok=True)
        entries = {
            "METADATA.json": json.dumps(
                {"name": metadata_name, "version": version}, separators=(",", ":")
            ).encode(),
            f"{package_dir}/__init__.py": (root / package_dir / "__init__.py").read_bytes(),
            f"{package_dir}/{('core.py' if package_dir == 'greeting' else 'plugin.py' if package_dir == 'metrics_plugin' else 'text.py')}": (
                root / package_dir / (
                    "core.py" if package_dir == "greeting"
                    else "plugin.py" if package_dir == "metrics_plugin"
                    else "text.py"
                )
            ).read_bytes(),
        }
        with zipfile.ZipFile(archive, "w") as handle:
            for name in sorted(entries):
                info = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
                handle.writestr(info, entries[name])
    elif task_id in SERVICE_CONFIGS:
        (root / "config.json").write_text(
            json.dumps(SERVICE_CONFIGS[task_id]), encoding="utf-8", newline=""
        )
    else:
        result = env.exec(
            ["python", "job.py"], cwd=str(root), timeout=30, env=JOB_ENVS[task_id]
        )
        assert result.returncode == 0, result.stderr


def test_v2_package_and_runtime_roster_is_complete():
    loaded = [load_task(path) for path in TASKS]
    assert len(loaded) == 9
    assert {task["family_id"] for task in loaded} == {"C10", "C11", "C12"}
    assert all(task["id"] == f"{task['family_id']}-{task['instance_id']}" for task in loaded)


@pytest.mark.parametrize("path", TASKS, ids=lambda path: path.stem)
def test_noop_fails_and_portable_oracle_solution_passes(path: Path, tmp_path: Path):
    task = yaml.safe_load(path.read_text(encoding="utf-8"))
    _materialize(tmp_path, task)
    env = LocalArgvEnvironment()
    prepare_fixture(env, _sandbox(tmp_path), task["preconditions"])
    baseline = local_snapshot(tmp_path)
    assert _passes(
        tmp_path, task, env, baseline, stop_on_failure=True
    ) is False
    _solve(tmp_path, task["id"], env)
    assert _passes(tmp_path, task, env, baseline) is True
    extra = tmp_path / "unexpected.tmp"
    extra.write_text("extra", encoding="utf-8")
    assert _passes(tmp_path, task, env, baseline) is False
    extra.unlink()
    protected = next(
        check["path"]
        for check in task["success_checks"]
        if check["type"] in {"file_content_equals", "file_unchanged"}
    )
    with (tmp_path / protected).open("a", encoding="utf-8") as handle:
        handle.write("corruption")
    assert _passes(tmp_path, task, env, baseline) is False


@pytest.mark.parametrize(
    "path",
    sorted((ROOT / "tasks" / "v2").glob("C11-I*.yaml")),
    ids=lambda path: path.stem,
)
def test_service_task_rejects_leftover_listener(path: Path, tmp_path: Path):
    task = yaml.safe_load(path.read_text(encoding="utf-8"))
    _materialize(tmp_path, task)
    env = LocalArgvEnvironment()
    prepare_fixture(env, _sandbox(tmp_path), task["preconditions"])
    baseline = local_snapshot(tmp_path)
    _solve(tmp_path, task["id"], env)
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
            raise AssertionError("fixture service did not start")
        assert _passes(tmp_path, task, env, baseline) is False
    finally:
        child.terminate()
        child.wait(timeout=5)
