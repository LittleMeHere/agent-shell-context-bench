from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from analysis.d013_oracle_qualification import _evaluate, apply_oracle, qualify_task
from harness.fs import local_snapshot
from harness.types import SandboxHandle
from tests.test_fixture_setup import LocalArgvEnvironment


ROOT = Path(__file__).resolve().parents[1]
TASKS = sorted((ROOT / "tasks" / "v2").glob("*.yaml"))

_ALTERNATE_SOLUTIONS = {
    "C06-I01": {"headers.py": "def get_header(headers, name):\n    for key in headers:\n        if key.lower() == name.lower(): return headers[key]\n    return None\n"},
    "C06-I02": {"retry.py": "def delay(attempt, base, cap):\n    if type(attempt) is not int or attempt < 0: raise ValueError('attempt')\n    value=base\n    for _ in range(attempt): value *= 2\n    return cap if value > cap else value\n"},
    "C06-I03": {"redact.py": "def redact(value):\n    if isinstance(value, list): return [redact(item) for item in value]\n    if not isinstance(value, dict): return value\n    out={}\n    for key,item in value.items():\n        out[key] = '[REDACTED]' if key.lower() in ('password','token','secret') else redact(item)\n    return out\n"},
    "C09-I01": {"slug.py": "import string\ndef slugify(text):\n    allowed=set(string.ascii_lowercase + string.digits)\n    out=[]\n    for char in text.lower():\n        if char in allowed: out.append(char)\n        elif out and out[-1] != '-': out.append('-')\n    return ''.join(out).strip('-')\n"},
    "C09-I02": {"config.py": "def load_config(raw):\n    result=dict(raw)\n    result.setdefault('workers',2); result.setdefault('debug',False)\n    if result['workers'] <= 0: raise ValueError('workers')\n    return result\n"},
    "C09-I03": {"aggregate.py": "def aggregate(rows):\n    result={}\n    for item in rows:\n        group=item['group']\n        result[group]=result.setdefault(group,0)+item['value']\n    return result\n"},
}

_SPECIAL_CASE_SOLUTIONS = {
    "C06-I01": {"headers.py": "def get_header(headers, name):\n    return {'content-type':'json','x-id':'7','missing':None}[name]\n"},
    "C06-I02": {"retry.py": "def delay(attempt, base, cap):\n    if attempt < 0: raise ValueError('attempt')\n    return [3,6,12,20,20][attempt]\n"},
    "C06-I03": {"redact.py": "def redact(value):\n    return {'User':'a','Token':'[REDACTED]','nested':[{'password':'[REDACTED]','keep':2}],'secret_note':'visible'}\n"},
    "C09-I01": {"slug.py": "def slugify(text):\n    return {'  Hello,   World!  ':'hello-world','A_B C':'a-b-c'}[text]\n"},
    "C09-I02": {"config.py": "def load_config(raw):\n    if raw.get('workers') == 0: raise ValueError('workers')\n    if raw == {'name':'x'}: return {'name':'x','workers':2,'debug':False}\n    return dict(raw)\n"},
    "C09-I03": {"aggregate.py": "def aggregate(rows):\n    if not rows: return {}\n    return {'b':7,'a':3}\n"},
}


class LocalOracleEnvironment(LocalArgvEnvironment):
    def snapshot(self, sandbox: SandboxHandle):
        return local_snapshot(sandbox.host_root)


def _materialize(root: Path, task: dict) -> None:
    for entry in task["preconditions"].get("initial_files", []):
        target = root / entry["path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(entry.get("content", ""), encoding="utf-8", newline="")


@pytest.mark.parametrize("path", TASKS, ids=lambda path: path.stem)
def test_every_registered_oracle_fails_noop_and_passes_checks(path: Path, tmp_path: Path):
    task = yaml.safe_load(path.read_text(encoding="utf-8"))
    _materialize(tmp_path, task)
    environment = LocalOracleEnvironment()
    sandbox = SandboxHandle(task["id"], 0, "local", str(tmp_path), tmp_path)
    evidence = qualify_task(environment, sandbox, task)
    assert evidence["noop_passed"] is False
    assert evidence["oracle_passed"] is True


def test_unknown_task_has_no_implicit_oracle(tmp_path: Path):
    environment = LocalArgvEnvironment()
    sandbox = SandboxHandle("unknown", 0, "local", str(tmp_path), tmp_path)
    with pytest.raises(Exception, match="no registered oracle"):
        apply_oracle(
            environment,
            sandbox,
            {"id": "C99-I01", "family_id": "C99"},
        )


@pytest.mark.parametrize("task_id", sorted(_ALTERNATE_SOLUTIONS))
def test_behavioral_tasks_accept_independent_implementations(
    task_id: str, tmp_path: Path
):
    path = next(path for path in TASKS if path.stem.startswith(task_id))
    task = yaml.safe_load(path.read_text(encoding="utf-8"))
    _materialize(tmp_path, task)
    for relpath, content in _ALTERNATE_SOLUTIONS[task_id].items():
        (tmp_path / relpath).write_text(content, encoding="utf-8", newline="")
    environment = LocalOracleEnvironment()
    sandbox = SandboxHandle(task_id, 0, "local", str(tmp_path), tmp_path)
    baseline = local_snapshot(tmp_path)
    passed, checks = _evaluate(environment, sandbox, task, baseline)
    assert passed, [check for check in checks if not check["passed"]]


@pytest.mark.parametrize("task_id", sorted(_SPECIAL_CASE_SOLUTIONS))
def test_behavioral_tasks_reject_visible_example_special_cases(
    task_id: str, tmp_path: Path
):
    path = next(path for path in TASKS if path.stem.startswith(task_id))
    task = yaml.safe_load(path.read_text(encoding="utf-8"))
    _materialize(tmp_path, task)
    for relpath, content in _SPECIAL_CASE_SOLUTIONS[task_id].items():
        (tmp_path / relpath).write_text(content, encoding="utf-8", newline="")
    environment = LocalOracleEnvironment()
    sandbox = SandboxHandle(task_id, 0, "local", str(tmp_path), tmp_path)
    baseline = local_snapshot(tmp_path)
    passed, _ = _evaluate(environment, sandbox, task, baseline)
    assert not passed
