"""Declarative, cross-environment pre-agent fixture construction.

V2 Git workflows need real repository/index/history state. Plain
``initial_files`` cannot express that state, and shell snippets would make the
fixture itself context-dependent. This module accepts a small allowlisted
operation language and invokes only argv-based Python/Git commands through the
selected EnvironmentAdapter before the baseline snapshot.
"""

from __future__ import annotations

import base64
import json
from collections.abc import Mapping, Sequence

from .types import SandboxHandle


class FixtureSetupError(RuntimeError):
    pass


_WRITE_SCRIPT = r"""
import base64, json
from pathlib import Path
root = Path.cwd().resolve()
payload = json.loads(base64.b64decode(__import__('sys').argv[1]).decode('utf-8'))
for rel, content in payload.items():
    target = (root / rel).resolve()
    if target == root or root not in target.parents:
        raise SystemExit('path escapes fixture root')
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding='utf-8', newline='')
""".strip()

_DELETE_SCRIPT = r"""
import base64, json
from pathlib import Path
root = Path.cwd().resolve()
for rel in json.loads(base64.b64decode(__import__('sys').argv[1]).decode('utf-8')):
    target = (root / rel).resolve()
    if target == root or root not in target.parents:
        raise SystemExit('path escapes fixture root')
    if not target.is_file():
        raise SystemExit('delete target is not a file')
    target.unlink()
""".strip()

_FREE_PORT_SCRIPT = r"""
import socket, sys
from pathlib import Path
root = Path.cwd().resolve()
target = (root / sys.argv[1]).resolve()
if target == root or root not in target.parents:
    raise SystemExit('path escapes fixture root')
target.parent.mkdir(parents=True, exist_ok=True)
with socket.socket() as sock:
    sock.bind(('127.0.0.1', 0))
    port = sock.getsockname()[1]
target.write_text(str(port) + '\n', encoding='utf-8', newline='')
""".strip()


def _payload(value: object) -> str:
    raw = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode()
    return base64.b64encode(raw).decode("ascii")


def _run(
    environment: object,
    sandbox: SandboxHandle,
    argv: Sequence[str],
    *,
    expected: int = 0,
) -> None:
    result = environment.exec(argv, cwd=sandbox.root, timeout=30, env=None)
    if result.timed_out or result.returncode != expected:
        raise FixtureSetupError(
            f"fixture command failed: argv={list(argv)!r} expected_rc={expected} "
            f"actual_rc={result.returncode!r} timed_out={result.timed_out} "
            f"stderr={result.stderr[:500]!r}"
        )


def _strings(value: object, *, field: str) -> list[str]:
    if not isinstance(value, list) or not value or any(
        not isinstance(item, str) or not item for item in value
    ):
        raise FixtureSetupError(f"{field} must be a non-empty string list")
    return list(value)


def prepare_fixture(
    environment: object,
    sandbox: SandboxHandle,
    preconditions: Mapping[str, object],
) -> None:
    """Apply the optional strict ``fixture_setup`` operation sequence."""
    raw_steps = preconditions.get("fixture_setup", []) or []
    if not isinstance(raw_steps, list):
        raise FixtureSetupError("fixture_setup must be a list")
    for ordinal, step in enumerate(raw_steps):
        if not isinstance(step, dict) or "type" not in step:
            raise FixtureSetupError(f"fixture_setup[{ordinal}] must be an operation object")
        kind = step["type"]
        if kind == "write_files":
            if set(step) != {"type", "files"} or not isinstance(step["files"], dict):
                raise FixtureSetupError("write_files requires exactly a files object")
            files = step["files"]
            if not files or any(
                not isinstance(path, str)
                or not path
                or not isinstance(content, str)
                for path, content in files.items()
            ):
                raise FixtureSetupError("write_files paths and contents must be strings")
            _run(environment, sandbox, ["python", "-c", _WRITE_SCRIPT, _payload(files)])
        elif kind == "delete_files":
            if set(step) != {"type", "paths"}:
                raise FixtureSetupError("delete_files requires exactly paths")
            paths = _strings(step["paths"], field="delete_files.paths")
            _run(environment, sandbox, ["python", "-c", _DELETE_SCRIPT, _payload(paths)])
        elif kind == "write_free_loopback_port":
            if set(step) != {"type", "path"} or not isinstance(step["path"], str):
                raise FixtureSetupError(
                    "write_free_loopback_port requires exactly a path"
                )
            _run(
                environment,
                sandbox,
                ["python", "-c", _FREE_PORT_SCRIPT, step["path"]],
            )
        elif kind == "git_init_commit":
            if set(step) != {"type", "message"} or not isinstance(step["message"], str):
                raise FixtureSetupError("git_init_commit requires exactly message")
            _run(environment, sandbox, ["git", "init", "-b", "main"])
            _run(environment, sandbox, ["git", "config", "user.name", "Benchmark Fixture"])
            _run(environment, sandbox, ["git", "config", "user.email", "fixture@example.invalid"])
            _run(environment, sandbox, ["git", "add", "--all"])
            _run(environment, sandbox, ["git", "commit", "-m", step["message"]])
        elif kind == "git_create_branch":
            if set(step) != {"type", "name"} or not isinstance(step["name"], str):
                raise FixtureSetupError("git_create_branch requires exactly name")
            _run(environment, sandbox, ["git", "switch", "-c", step["name"]])
        elif kind == "git_switch":
            if set(step) != {"type", "ref"} or not isinstance(step["ref"], str):
                raise FixtureSetupError("git_switch requires exactly ref")
            _run(environment, sandbox, ["git", "switch", step["ref"]])
        elif kind == "git_commit_all":
            if set(step) != {"type", "message"} or not isinstance(step["message"], str):
                raise FixtureSetupError("git_commit_all requires exactly message")
            _run(environment, sandbox, ["git", "add", "--all"])
            _run(environment, sandbox, ["git", "commit", "-m", step["message"]])
        elif kind == "git_stage":
            if set(step) != {"type", "paths"}:
                raise FixtureSetupError("git_stage requires exactly paths")
            _run(environment, sandbox, ["git", "add", "--", *_strings(step["paths"], field="git_stage.paths")])
        elif kind == "git_merge_conflict":
            if set(step) != {"type", "ref"} or not isinstance(step["ref"], str):
                raise FixtureSetupError("git_merge_conflict requires exactly ref")
            _run(
                environment,
                sandbox,
                ["git", "merge", "--no-commit", "--no-ff", step["ref"]],
                expected=1,
            )
        else:
            raise FixtureSetupError(f"unsupported fixture operation {kind!r}")
