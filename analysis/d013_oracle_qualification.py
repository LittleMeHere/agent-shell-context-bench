"""Run the frozen V2 oracle completions through real environment adapters.

This is qualification evidence, never benchmark outcome data.  It creates no
agent and makes no model call.  For each task it proves that the untouched
fixture fails and that a portable, task-author oracle completion passes the
registered executable checks in the selected environment.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import sys
import time
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from analysis.d013_task_bank import validate_task_bank  # noqa: E402
from harness.checks import evaluate_checks  # noqa: E402
from harness.fixture_setup import prepare_fixture  # noqa: E402
from harness.registry import make_environment  # noqa: E402
from harness.runner import load_task  # noqa: E402
from harness.types import SandboxHandle  # noqa: E402


SCHEMA_VERSION = "1.0.0"
TASKS_ROOT = REPO_ROOT / "tasks" / "v2"
SLATE_PATH = REPO_ROOT / "config" / "v2-family-slate.accepted.json"
ALLOWED_ENVIRONMENTS = (
    "windows_powershell",
    "windows_pwsh7",
    "windows_wsl2",
    "linux_native",
    "macos_actions",
)


class OracleQualificationError(RuntimeError):
    pass


_RENAME_SOLUTIONS = {
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

_CODE_SOLUTIONS = {
    "C06-I01": {"headers.py": "def get_header(headers, name):\n    wanted=name.casefold()\n    return next((v for k,v in headers.items() if k.casefold()==wanted), None)\n"},
    "C06-I02": {"retry.py": "def delay(attempt, base, cap):\n    if not isinstance(attempt, int) or attempt < 0: raise ValueError('attempt')\n    return min(cap, base * (2 ** attempt))\n"},
    "C06-I03": {"redact.py": "def redact(value):\n    if isinstance(value, dict):\n        return {k: ('[REDACTED]' if k.casefold() in {'password','token','secret'} else redact(v)) for k,v in value.items()}\n    if isinstance(value, list): return [redact(v) for v in value]\n    return value\n"},
    "C09-I01": {"slug.py": "import re\ndef slugify(text):\n    return re.sub(r'-+', '-', re.sub(r'[^a-z0-9]+', '-', text.lower())).strip('-')\n"},
    "C09-I02": {"config.py": "def load_config(raw):\n    out={'workers':2,'debug':False,**raw}\n    if out['workers'] <= 0: raise ValueError('workers')\n    return out\n"},
    "C09-I03": {"aggregate.py": "def aggregate(rows):\n    out={}\n    for row in rows: out[row['group']]=out.get(row['group'],0)+row['value']\n    return out\n"},
}

_GIT_MERGE_SOLUTIONS = {
    "C07-I01": ("settings.py", "def settings():\n    return {'timeout': 60, 'retries': 5, 'endpoint': '/v2', 'backoff': 2}\n"),
    "C07-I02": ("routes.json", '{"root":"/","health":"/healthz","items":"/v2/items"}\n'),
    "C07-I03": ("worker.py", "def policy():\n    return {'concurrency': 8, 'queue': 'critical', 'retry_limit': 6, 'jitter': True}\n"),
}

_GIT_RESTORE_PATHS = {
    "C08-I01": "bad.txt",
    "C08-I02": "config.ini",
    "C08-I03": "src/limit.py",
}

_PACKAGE_SPECS = {
    "C10-I01": ("dist/greeting.zip", "greeting", "greeting", "1.0.0"),
    "C10-I02": ("dist/metrics_plugin.zip", "metrics_plugin", "metrics-plugin", "2.1.0"),
    "C10-I03": ("dist/transform.zip", "transform", "transform", "0.4.0"),
}

_SERVICE_CONFIGS = {
    "C11-I01": {"path": "/health", "body": "healthy"},
    "C11-I02": {"path": "/ready", "body": "ready-v2"},
    "C11-I03": {"path": "/live", "body": "alive"},
}

_SERVICE_DIAGNOSTIC_SCRIPT = r"""
import json, subprocess, sys, time, urllib.request
port = int(open('port.txt', encoding='utf-8').read())
expected_path = sys.argv[1]
child = subprocess.Popen(
    [sys.executable, 'service.py', str(port), '--once'],
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    text=True,
)
observed = None
errors = []
try:
    for _ in range(20):
        if child.poll() is not None:
            break
        try:
            observed = urllib.request.urlopen(
                f'http://127.0.0.1:{port}{expected_path}', timeout=.2
            ).read().decode()
            break
        except Exception as exc:
            errors.append(f'{type(exc).__name__}: {exc}')
            time.sleep(.05)
finally:
    poll_before_cleanup = child.poll()
    if poll_before_cleanup is None:
        child.kill()
    stdout, stderr = child.communicate(timeout=2)
print(json.dumps({
    'port': port,
    'observed': observed,
    'errors': errors,
    'poll_before_cleanup': poll_before_cleanup,
    'returncode': child.returncode,
    'child_stdout': stdout,
    'child_stderr': stderr,
}, sort_keys=True))
""".strip()

_JOB_ENVS = {
    "C12-I01": {"JOB_MODE": "sum", "JOB_TOKEN": "violet-17"},
    "C12-I02": {"JOB_MODE": "max", "JOB_TOKEN": "amber-29"},
    "C12-I03": {"JOB_MODE": "count", "JOB_TOKEN": "silver-41"},
}

_WRITE_FILES_SCRIPT = r"""
import base64, json
from pathlib import Path
root = Path.cwd().resolve()
files = json.loads(base64.b64decode(__import__('sys').argv[1]).decode('utf-8'))
for rel, content in files.items():
    target = (root / rel).resolve()
    if target == root or root not in target.parents:
        raise SystemExit('oracle path escapes sandbox')
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding='utf-8', newline='')
""".strip()

_PACKAGE_SCRIPT = r"""
import base64, json, zipfile
from pathlib import Path
root = Path.cwd().resolve()
archive_rel, package_dir, metadata_name, version = json.loads(
    base64.b64decode(__import__('sys').argv[1]).decode('utf-8')
)
archive = (root / archive_rel).resolve()
if archive == root or root not in archive.parents:
    raise SystemExit('archive path escapes sandbox')
archive.parent.mkdir(parents=True, exist_ok=True)
module = 'core.py' if package_dir == 'greeting' else ('plugin.py' if package_dir == 'metrics_plugin' else 'text.py')
entries = {
    'METADATA.json': json.dumps({'name': metadata_name, 'version': version}, separators=(',', ':')).encode(),
    f'{package_dir}/__init__.py': (root / package_dir / '__init__.py').read_bytes(),
    f'{package_dir}/{module}': (root / package_dir / module).read_bytes(),
}
with zipfile.ZipFile(archive, 'w') as handle:
    for name in sorted(entries):
        info = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
        handle.writestr(info, entries[name])
""".strip()

_JOB_SCRIPT = r"""
import base64, json, os, runpy
os.environ.update(json.loads(base64.b64decode(__import__('sys').argv[1]).decode('utf-8')))
runpy.run_path('job.py', run_name='__main__')
""".strip()


def _payload(value: object) -> str:
    return base64.b64encode(
        json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode()
    ).decode("ascii")


def _run(environment: object, sandbox: SandboxHandle, argv: Sequence[str]) -> None:
    result = environment.exec(argv, cwd=sandbox.root, timeout=60, env=None)
    if result.timed_out or result.returncode != 0:
        raise OracleQualificationError(
            f"oracle command failed: argv={list(argv)!r} "
            f"returncode={result.returncode!r} timed_out={result.timed_out} "
            f"stderr={result.stderr[:500]!r}"
        )


def _write_files(
    environment: object, sandbox: SandboxHandle, files: Mapping[str, str]
) -> None:
    _run(
        environment,
        sandbox,
        ["python", "-c", _WRITE_FILES_SCRIPT, _payload(dict(files))],
    )


def _service_diagnostic(
    environment: object,
    sandbox: SandboxHandle,
    task: Mapping[str, Any],
) -> str:
    expected = _SERVICE_CONFIGS.get(str(task["id"]))
    if expected is None:
        return ""
    result = environment.exec(
        ["python", "-c", _SERVICE_DIAGNOSTIC_SCRIPT, expected["path"]],
        cwd=sandbox.root,
        timeout=10,
        env={
            "ALL_PROXY": "",
            "HTTPS_PROXY": "",
            "HTTP_PROXY": "",
            "NO_PROXY": "127.0.0.1,localhost,::1",
            "all_proxy": "",
            "https_proxy": "",
            "http_proxy": "",
            "no_proxy": "127.0.0.1,localhost,::1",
        },
    )
    return (
        f"; service_diagnostic rc={result.returncode!r} "
        f"timed_out={result.timed_out} stdout={result.stdout[:2000]!r} "
        f"stderr={result.stderr[:2000]!r}"
    )


def _retained_solution(task: Mapping[str, Any]) -> dict[str, str]:
    task_id = str(task["id"])
    if task_id in _RENAME_SOLUTIONS:
        return dict(_RENAME_SOLUTIONS[task_id])
    if task_id == "C04-I02":
        return {
            "inventory.json": json.dumps(
                {
                    ".meta": hashlib.sha256(b"x").hexdigest(),
                    "data/one.txt": hashlib.sha256(b"one\n").hexdigest(),
                    "data/two.txt": hashlib.sha256(b"two\n").hexdigest(),
                },
                sort_keys=True,
            )
        }
    initial = {
        entry["path"] for entry in task["preconditions"].get("initial_files", [])
    }
    files: dict[str, str] = {}
    for check in task["success_checks"]:
        rel = check.get("path")
        if not rel or rel in initial:
            continue
        if check["type"] == "file_content_equals":
            files[rel] = check["content"]
        elif check["type"] == "json_content_equals":
            files[rel] = json.dumps(check["value"], ensure_ascii=False)
        elif check["type"] == "file_is_empty":
            files[rel] = ""
    return files


def apply_oracle(
    environment: object, sandbox: SandboxHandle, task: Mapping[str, Any]
) -> None:
    task_id = str(task["id"])
    family = str(task["family_id"])
    if family in {"C01", "C02", "C03", "C04", "C05"}:
        _write_files(environment, sandbox, _retained_solution(task))
    elif task_id in _CODE_SOLUTIONS:
        _write_files(environment, sandbox, _CODE_SOLUTIONS[task_id])
    elif task_id in _GIT_MERGE_SOLUTIONS:
        path, content = _GIT_MERGE_SOLUTIONS[task_id]
        _write_files(environment, sandbox, {path: content})
        _run(environment, sandbox, ["git", "add", "--", path])
    elif task_id in _GIT_RESTORE_PATHS:
        _run(
            environment,
            sandbox,
            ["git", "restore", "--", _GIT_RESTORE_PATHS[task_id]],
        )
    elif task_id in _PACKAGE_SPECS:
        _run(
            environment,
            sandbox,
            ["python", "-c", _PACKAGE_SCRIPT, _payload(_PACKAGE_SPECS[task_id])],
        )
    elif task_id in _SERVICE_CONFIGS:
        _write_files(
            environment,
            sandbox,
            {"config.json": json.dumps(_SERVICE_CONFIGS[task_id])},
        )
    elif task_id in _JOB_ENVS:
        _run(
            environment,
            sandbox,
            ["python", "-c", _JOB_SCRIPT, _payload(_JOB_ENVS[task_id])],
        )
    else:
        raise OracleQualificationError(f"no registered oracle for {task_id}")


def _evaluate(
    environment: object,
    sandbox: SandboxHandle,
    task: Mapping[str, Any],
    baseline,
    *,
    stop_on_failure: bool = False,
):
    snapshot = environment.snapshot(sandbox)
    passed, checks = evaluate_checks(
        snapshot,
        task["success_checks"],
        sandbox_host_root=sandbox.host_root,
        environment_exec=environment.exec,
        environment_cwd=sandbox.root,
        snapshot_before=baseline,
        stop_on_failure=stop_on_failure,
    )
    return passed, [asdict(check) for check in checks]


def qualify_task(
    environment: object,
    sandbox: SandboxHandle,
    task: Mapping[str, Any],
) -> dict[str, Any]:
    prepare_fixture(environment, sandbox, task["preconditions"])
    baseline = environment.snapshot(sandbox)
    noop_passed, noop_checks = _evaluate(
        environment, sandbox, task, baseline, stop_on_failure=True
    )
    if noop_passed:
        raise OracleQualificationError(f"{task['id']}: untouched fixture passed")
    apply_oracle(environment, sandbox, task)
    oracle_passed, oracle_checks = _evaluate(environment, sandbox, task, baseline)
    if not oracle_passed:
        failed = [check for check in oracle_checks if not check["passed"]]
        raise OracleQualificationError(
            f"{task['id']}: oracle failed registered checks: {failed!r}"
            + _service_diagnostic(environment, sandbox, task)
        )
    return {
        "noop_passed": False,
        "noop_checks": noop_checks,
        "oracle_passed": True,
        "oracle_checks": oracle_checks,
    }


def qualify_environment(env_id: str) -> dict[str, Any]:
    if env_id not in ALLOWED_ENVIRONMENTS:
        raise OracleQualificationError(f"unsupported environment {env_id!r}")
    environment = make_environment(env_id)
    probe = environment.probe()
    tasks = [load_task(path) for path in sorted(TASKS_ROOT.glob("*.yaml"))]
    records: list[dict[str, Any]] = []
    for ordinal, task in enumerate(tasks):
        started = time.monotonic()
        noop_sandbox = None
        oracle_sandbox = None
        try:
            noop_sandbox = environment.setup_sandbox(
                str(task["id"]), ordinal * 2, task["preconditions"]
            )
            prepare_fixture(environment, noop_sandbox, task["preconditions"])
            noop_baseline = environment.snapshot(noop_sandbox)
            noop_passed, noop_checks = _evaluate(
                environment,
                noop_sandbox,
                task,
                noop_baseline,
                stop_on_failure=True,
            )
            if noop_passed:
                raise OracleQualificationError(
                    f"{task['id']}: untouched fixture passed"
                )
            environment.teardown_sandbox(noop_sandbox)
            noop_sandbox = None

            # Use a distinct sandbox for the positive oracle.  Some checks
            # launch a one-shot loopback service; rerunning immediately on the
            # same assigned port can encounter TCP teardown state even though
            # a real trial evaluates its checks only once.
            oracle_sandbox = environment.setup_sandbox(
                str(task["id"]), ordinal * 2 + 1, task["preconditions"]
            )
            prepare_fixture(environment, oracle_sandbox, task["preconditions"])
            oracle_baseline = environment.snapshot(oracle_sandbox)
            apply_oracle(environment, oracle_sandbox, task)
            oracle_passed, oracle_checks = _evaluate(
                environment, oracle_sandbox, task, oracle_baseline
            )
            if not oracle_passed:
                failed = [check for check in oracle_checks if not check["passed"]]
                raise OracleQualificationError(
                    f"{task['id']}: oracle failed registered checks: {failed!r}"
                    + _service_diagnostic(environment, oracle_sandbox, task)
                )
            records.append(
                {
                    "task_id": task["id"],
                    "family_id": task["family_id"],
                    "status": "PASS",
                    "duration_seconds": time.monotonic() - started,
                    "noop_passed": False,
                    "noop_checks": noop_checks,
                    "oracle_passed": True,
                    "oracle_checks": oracle_checks,
                }
            )
        except Exception as exc:
            records.append(
                {
                    "task_id": task["id"],
                    "family_id": task["family_id"],
                    "status": "FAIL",
                    "duration_seconds": time.monotonic() - started,
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )
        finally:
            cleanup_errors: list[str] = []
            for sandbox in (noop_sandbox, oracle_sandbox):
                if sandbox is None:
                    continue
                try:
                    environment.teardown_sandbox(sandbox)
                except Exception as exc:
                    cleanup_errors.append(f"{type(exc).__name__}: {exc}")
            if cleanup_errors:
                records[-1]["status"] = "FAIL"
                records[-1]["teardown_error"] = cleanup_errors
    return {
        "env_id": env_id,
        "passed": all(record["status"] == "PASS" for record in records),
        "environment_probe": probe,
        "tasks": records,
    }


def build_evidence(env_ids: Sequence[str]) -> dict[str, Any]:
    bank = validate_task_bank(slate_path=SLATE_PATH, tasks_root=TASKS_ROOT)
    environments = [qualify_environment(env_id) for env_id in env_ids]
    return {
        "schema_version": SCHEMA_VERSION,
        "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "analysis_excluded": True,
        "model_calls": 0,
        "bank_digest": bank.bank_digest,
        "task_count": bank.task_count,
        "passed": all(environment["passed"] for environment in environments),
        "environments": environments,
    }


def write_evidence(evidence: Mapping[str, Any], output: Path) -> None:
    resolved = output.resolve()
    try:
        resolved.relative_to(REPO_ROOT.resolve())
    except ValueError:
        pass
    else:
        raise OracleQualificationError(
            "qualification evidence must be written outside the public repository"
        )
    resolved.parent.mkdir(parents=True, exist_ok=True)
    with resolved.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(evidence, handle, indent=2, sort_keys=True)
        handle.write("\n")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--env", action="append", required=True, choices=ALLOWED_ENVIRONMENTS
    )
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    evidence = build_evidence(args.env)
    write_evidence(evidence, args.output)
    for environment in evidence["environments"]:
        passed = sum(task["status"] == "PASS" for task in environment["tasks"])
        print(f"{environment['env_id']}: {passed}/36 oracle completions passed")
        for task in environment["tasks"]:
            if task["status"] != "PASS":
                print(f"  {task['task_id']}: {task.get('error', 'teardown failure')}")
    print(f"artifact: {args.output.resolve()}")
    return 0 if evidence["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
