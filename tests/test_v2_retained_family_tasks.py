from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
import yaml

from harness.checks import evaluate_checks
from harness.fs import local_snapshot
from harness.runner import load_task
from tests.test_fixture_setup import LocalArgvEnvironment


ROOT = Path(__file__).resolve().parents[1]
TASKS = sorted((ROOT / "tasks" / "v2").glob("C0[1-5]-I*.yaml"))


RENAME_SOLUTIONS = {
    "C03-I01": {
        "store.py": "def load_item(key):\n    return {'key': key}\n# fetch_item is the legacy documentation name\n",
        "app.py": "from store import load_item\nMESSAGE='fetch_item failed'\ndef run(): return load_item('x')\n",
    },
    "C03-I02": {
        "codec.py": "def serialize_value(value):\n    return str(value)\n# encode_value used to accept bytes\n",
        "exports.py": "from codec import serialize_value\n__all__=['serialize_value']\n",
        "api.py": "from exports import serialize_value\nERROR='encode_value failed'\ndef render(v): return serialize_value(v)\n",
    },
    "C03-I03": {
        "validator.py": "def check_row(row):\n    return 'id' in row\n# validate_row remains the audit label\n",
        "pipeline.py": "from validator import check_row\nLABEL='validate_row result'\ndef accepted(row): return check_row(row)\n",
        "test_support.py": "from validator import check_row\ndef sample(): return check_row({'id':1})\n",
    },
}


def _materialize(root: Path, task: dict) -> None:
    for entry in task["preconditions"]["initial_files"]:
        target = root / entry["path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(entry.get("content", ""), encoding="utf-8", newline="")


def _passes(root: Path, task: dict, env: LocalArgvEnvironment, baseline) -> bool:
    passed, _ = evaluate_checks(
        local_snapshot(root), task["success_checks"], sandbox_host_root=root,
        environment_exec=env.exec, environment_cwd=str(root),
        snapshot_before=baseline,
    )
    return passed


def _write(root: Path, rel: str, content: str) -> None:
    target = root / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8", newline="")


def _solve(root: Path, task: dict) -> None:
    task_id = task["id"]
    if task_id in RENAME_SOLUTIONS:
        for rel, content in RENAME_SOLUTIONS[task_id].items():
            _write(root, rel, content)
        return
    if task_id == "C04-I02":
        value = {
            ".meta": hashlib.sha256(b"x").hexdigest(),
            "data/one.txt": hashlib.sha256(b"one\n").hexdigest(),
            "data/two.txt": hashlib.sha256(b"two\n").hexdigest(),
        }
        _write(root, "inventory.json", json.dumps(value, sort_keys=True))
        return
    initial = {
        entry["path"] for entry in task["preconditions"]["initial_files"]
    }
    for check in task["success_checks"]:
        rel = check.get("path")
        if not rel or rel in initial:
            continue
        if check["type"] == "file_content_equals":
            _write(root, rel, check["content"])
        elif check["type"] == "json_content_equals":
            _write(root, rel, json.dumps(check["value"], ensure_ascii=False))
        elif check["type"] == "file_is_empty":
            _write(root, rel, "")


def test_retained_v2_families_have_exactly_three_instances_each():
    loaded = [load_task(path) for path in TASKS]
    assert len(loaded) == 15
    assert {task["id"] for task in loaded} == {
        f"C{family:02d}-I{instance:02d}"
        for family in range(1, 6)
        for instance in range(1, 4)
    }


def test_complete_v2_task_bank_has_36_unique_bound_instances():
    loaded = [load_task(path) for path in sorted((ROOT / "tasks" / "v2").glob("*.yaml"))]
    assert len(loaded) == 36
    assert len({task["id"] for task in loaded}) == 36
    assert {task["family_id"] for task in loaded} == {
        f"C{family:02d}" for family in range(1, 13)
    }
    assert all(task["id"] == f"{task['family_id']}-{task['instance_id']}" for task in loaded)


@pytest.mark.parametrize("path", TASKS, ids=lambda path: path.stem)
def test_retained_family_noop_fails_and_known_positive_passes(path: Path, tmp_path: Path):
    task = yaml.safe_load(path.read_text(encoding="utf-8"))
    _materialize(tmp_path, task)
    env = LocalArgvEnvironment()
    baseline = local_snapshot(tmp_path)
    assert _passes(tmp_path, task, env, baseline) is False
    _solve(tmp_path, task)
    assert _passes(tmp_path, task, env, baseline) is True
    extra = tmp_path / "unexpected.tmp"
    extra.write_text("extra", encoding="utf-8")
    assert _passes(tmp_path, task, env, baseline) is False
    extra.unlink()
    protected_paths = [
        check["path"]
        for check in task["success_checks"]
        if check["type"] in {"file_content_equals", "file_unchanged"}
    ]
    protected = protected_paths[0] if protected_paths else next(
        check["path"]
        for check in task["success_checks"]
        if check["type"] == "python_parses"
    )
    (tmp_path / protected).write_text("def broken(:\n", encoding="utf-8")
    assert _passes(tmp_path, task, env, baseline) is False
