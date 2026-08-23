from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from harness.checks import evaluate_checks
from harness.fs import local_snapshot
from harness.runner import load_task
from tests.test_fixture_setup import LocalArgvEnvironment


ROOT = Path(__file__).resolve().parents[1]
TASKS = sorted((ROOT / "tasks" / "v2").glob("C0[69]-I*.yaml"))


SOLUTIONS = {
    "C06-I01": ("headers.py", "def get_header(headers, name):\n    wanted=name.casefold()\n    return next((v for k,v in headers.items() if k.casefold()==wanted), None)\n"),
    "C06-I02": ("retry.py", "def delay(attempt, base, cap):\n    if not isinstance(attempt, int) or attempt < 0: raise ValueError('attempt')\n    return min(cap, base * (2 ** attempt))\n"),
    "C06-I03": ("redact.py", "def redact(value):\n    if isinstance(value, dict):\n        return {k: ('[REDACTED]' if k.casefold() in {'password','token','secret'} else redact(v)) for k,v in value.items()}\n    if isinstance(value, list): return [redact(v) for v in value]\n    return value\n"),
    "C09-I01": ("slug.py", "import re\ndef slugify(text):\n    return re.sub(r'-+', '-', re.sub(r'[^a-z0-9]+', '-', text.lower())).strip('-')\n"),
    "C09-I02": ("config.py", "def load_config(raw):\n    out={'workers':2,'debug':False,**raw}\n    if out['workers'] <= 0: raise ValueError('workers')\n    return out\n"),
    "C09-I03": ("aggregate.py", "def aggregate(rows):\n    out={}\n    for row in rows: out[row['group']]=out.get(row['group'],0)+row['value']\n    return out\n"),
}


def _materialize(root: Path, task: dict) -> None:
    for entry in task["preconditions"]["initial_files"]:
        target = root / entry["path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(entry.get("content", ""), encoding="utf-8", newline="")


def _passes(root: Path, task: dict, env: LocalArgvEnvironment, baseline) -> bool:
    passed, _ = evaluate_checks(
        local_snapshot(root), task["success_checks"],
        sandbox_host_root=root, environment_exec=env.exec,
        environment_cwd=str(root),
        snapshot_before=baseline,
    )
    return passed


def test_v2_code_and_test_families_have_three_instances_each():
    loaded = [load_task(path) for path in TASKS]
    assert len(loaded) == 6
    assert {task["id"] for task in loaded} == set(SOLUTIONS)
    assert {task["family_id"] for task in loaded} == {"C06", "C09"}


@pytest.mark.parametrize("path", TASKS, ids=lambda path: path.stem)
def test_v2_code_noop_fails_and_oracle_solution_passes(path: Path, tmp_path: Path):
    task = yaml.safe_load(path.read_text(encoding="utf-8"))
    _materialize(tmp_path, task)
    env = LocalArgvEnvironment()
    baseline = local_snapshot(tmp_path)
    assert _passes(tmp_path, task, env, baseline) is False
    rel, content = SOLUTIONS[task["id"]]
    (tmp_path / rel).write_text(content, encoding="utf-8", newline="")
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
