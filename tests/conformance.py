"""Reusable adapter conformance batteries.

This module is imported by every per-adapter conformance test
(`tests/test_<id>_conformance.py`). It is NOT a `test_*` file, so pytest
does not collect it directly — it is the shared definition of "a correct
adapter" that keeps independently-built adapters from diverging. The prose
companion is `docs/ADAPTER_CONTRACT.md`; this is the executable version.

Two batteries:

  assert_agent_adapter_conforms(adapter)
      Infrastructure-free. Feeds synthetic transcripts, so it runs in CI for
      every agent the moment its adapter class exists.

  assert_environment_conforms(env, live=...)
      Structural mode (default) needs no infrastructure. `live=True`
      exercises the real sandbox/snapshot/exec path and must be gated by the
      caller on infrastructure availability (e.g. skip when the GCP creds or
      WSL distro are absent), exactly as the Windows reference env is only
      fully exercised on a Windows host.

Each battery raises AssertionError on the first violation (with a message
naming the invariant) and returns a small observations dict on success.

What these batteries deliberately do NOT check, because it is review-
enforced rather than mechanically decidable:
  * that an agent adapter never shells out directly (invariant 4) — caught
    in code review; the mechanically-checkable half (`run()` not overridden)
    IS asserted here.
"""

from __future__ import annotations

import sys
from collections.abc import Sequence
from pathlib import Path

_BENCH = Path(__file__).resolve().parents[1]
if str(_BENCH) not in sys.path:
    sys.path.insert(0, str(_BENCH))

from harness.adapters.base import AgentAdapter
from harness.environments.base import EnvironmentAdapter
from harness.types import (
    CommandRecord,
    FilesystemSnapshot,
    ProcessResult,
    SandboxHandle,
)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _is_relative_posix(key: str) -> bool:
    """True iff `key` is a sandbox-relative POSIX path (invariant 1).

    Rejects backslashes, absolute paths, and Windows drive prefixes — the
    exact shapes that would make a remote/Windows env's snapshot keys fail to
    match the frozen, sandbox-relative-POSIX lookups in `checks.py`.
    """
    if "\\" in key:
        return False
    if key.startswith("/"):
        return False
    first = key.split("/", 1)[0]
    if len(first) >= 2 and first[1] == ":":  # e.g. "C:..."
        return False
    return True


def _synthetic_sandbox() -> SandboxHandle:
    """A SandboxHandle for invoking build_invocation without real infra."""
    return SandboxHandle(
        task_id="conformance",
        trial_index=0,
        env_id="conformance_env",
        root="/conformance/sandbox",
        host_root=Path("."),
    )


# ---------------------------------------------------------------------------
# agent adapter battery
# ---------------------------------------------------------------------------


def assert_agent_adapter_conforms(adapter: AgentAdapter) -> dict[str, object]:
    """Run the AgentAdapter contract battery. Infrastructure-free.

    Verifies the invariants that keep H2's command stream comparable across
    agents: `run()` is the untouched template, `build_invocation` produces a
    well-formed argv, and `parse_transcript` degrades to partial data instead
    of raising on garbled/empty/truncated output.
    """
    agent_id = getattr(type(adapter), "agent_id", None)
    assert isinstance(agent_id, str) and agent_id, (
        "agent_id must be a non-empty class str matching the matrix id"
    )

    default_path = type(adapter)._default_cli_path()
    assert isinstance(default_path, str) and default_path, (
        "_default_cli_path() must return a non-empty executable name"
    )

    # Invariant 4 (mechanical half): the template method is never overridden,
    # so the exec/parse/error-capture path is identical across every cell.
    assert type(adapter).run is AgentAdapter.run, (
        f"{type(adapter).__name__} overrides run(); the template method must "
        "not be overridden (see docs/ADAPTER_CONTRACT.md)"
    )

    # build_invocation: a well-formed argv whose first element is the CLI.
    # We assert only what is true for EVERY agent — the model may be passed
    # via argv (Claude Code) or via config injection (agy), so model presence
    # in argv is NOT asserted here.
    argv = adapter.build_invocation("do the task", _synthetic_sandbox())
    assert isinstance(argv, list) and argv, "build_invocation must return a non-empty list"
    assert all(isinstance(a, str) for a in argv), "every argv element must be str"
    assert argv[0] == adapter.cli_path, (
        "argv[0] must be the resolved cli_path so the harness launches the "
        "pinned binary"
    )

    # parse_transcript robustness (invariant 7 / the 'never raise' contract):
    # empty, pure-garbage, and truncated output must all degrade gracefully.
    cases = {
        "empty": "",
        "garbage": "this is not json\nneither is this\n",
        "truncated": '{"type":"assistant","message":{"content":[{"type":"tool_',
        "mixed": (
            '{"type":"assistant","message":{"content":[{"type":"tool_use",'
            '"name":"Bash","input":{"command":"echo hi"}}]}}\n'
            "trailing non-json garbage\n"
        ),
    }
    total_commands = 0
    for label, stdout in cases.items():
        process = ProcessResult(
            argv=("agent",), returncode=0, stdout=stdout, stderr="",
            duration_seconds=0.1,
        )
        try:
            transcript, commands = adapter.parse_transcript(process)
        except Exception as exc:  # noqa: BLE001 - the whole point is it must not raise
            raise AssertionError(
                f"parse_transcript raised on {label!r} input "
                f"({type(exc).__name__}: {exc}); it must degrade to a "
                "best-effort partial instead"
            ) from exc
        assert isinstance(transcript, str), f"{label}: transcript must be str"
        assert isinstance(commands, list), f"{label}: commands must be a list"
        for i, cmd in enumerate(commands):
            assert isinstance(cmd, CommandRecord), (
                f"{label}: command {i} is not a CommandRecord"
            )
            assert cmd.index == i, (
                f"{label}: command indices must be sequential from 0 "
                f"(the spiral order H2 scores); got index={cmd.index} at "
                f"position {i}"
            )
            assert isinstance(cmd.command, str) and cmd.command, (
                f"{label}: every CommandRecord.command must be a non-empty str"
            )
            assert cmd.tool_name is None or isinstance(cmd.tool_name, str)
            assert cmd.exit_code is None or isinstance(cmd.exit_code, int)
        total_commands += len(commands)

    return {
        "agent_id": agent_id,
        "default_cli_path": default_path,
        "parse_transcript_total_commands": total_commands,
    }


# ---------------------------------------------------------------------------
# environment adapter battery
# ---------------------------------------------------------------------------


def assert_environment_conforms(
    env: EnvironmentAdapter,
    *,
    live: bool = False,
    exercise_canaries: bool = False,
    exec_ok_argv: Sequence[str] | None = None,
    exec_sleep_argv: Sequence[str] | None = None,
    exec_timeout_seconds: float = 0.5,
) -> dict[str, object]:
    """Run the EnvironmentAdapter contract battery.

    Structural checks (always) need no infrastructure. `live=True` exercises
    the real sandbox lifecycle, snapshot, and process seams and so requires
    the environment's infrastructure to be reachable from the test host — the
    caller is responsible for gating it (skip if unavailable).

    `exec_ok_argv` / `exec_sleep_argv` let a non-local environment supply a
    trivially-succeeding command and a long-sleeping command in its own
    native terms; they default to the host Python interpreter, correct for
    local environments.

    `exercise_canaries=True` performs real sentinel writes at the
    environment's canary paths (side-effecting external locations such as the
    home/temp dirs) and is only needed for environments that override
    `_write_canary` with non-local write semantics (e.g. WSL). Off by default.
    """
    obs: dict[str, object] = {}

    # --- structural (no infrastructure) ---------------------------------
    env_id = getattr(type(env), "env_id", None)
    assert isinstance(env_id, str) and env_id, (
        "env_id must be a non-empty class str matching the matrix id"
    )
    assert isinstance(getattr(type(env), "description", None), str) and type(env).description, (
        "description must be a non-empty class str"
    )
    canaries = env.canary_paths()
    assert isinstance(canaries, list), "canary_paths() must return a list"
    for p in canaries:
        assert isinstance(p, Path) and p.is_absolute(), (
            f"canary path {p!r} must be an absolute Path (it lives OUTSIDE "
            "any sandbox)"
        )
    obs["env_id"] = env_id
    obs["canary_count"] = len(canaries)

    if not live:
        obs["live"] = False
        return obs
    obs["live"] = True

    if exec_ok_argv is None:
        exec_ok_argv = [sys.executable, "-c", "pass"]
    if exec_sleep_argv is None:
        exec_sleep_argv = [sys.executable, "-c", "import time; time.sleep(30)"]

    preconditions = {
        "initial_files": [
            {"path": "keep.txt", "content": "hello\n"},
            {"path": "sub/nested.txt", "content": "x"},
        ],
        "required_tools": [],
    }

    s0 = env.setup_sandbox("conformance", 0, preconditions)
    try:
        assert isinstance(s0, SandboxHandle), "setup_sandbox must return a SandboxHandle"
        assert s0.env_id == env_id, "SandboxHandle.env_id must match the env"
        assert s0.task_id == "conformance" and s0.trial_index == 0

        # Invariant 2: host_root is a locally-readable dir holding the files.
        host_root = Path(s0.host_root)
        assert host_root.is_dir(), (
            f"host_root {host_root} must be a locally-readable directory at "
            "check time (remote envs must sync/mount the sandbox back)"
        )
        assert (host_root / "keep.txt").is_file(), "initial_files not materialised in host_root"
        assert (host_root / "keep.txt").read_text(encoding="utf-8") == "hello\n", (
            "materialised initial_file content must be locally readable and exact"
        )
        assert (host_root / "sub" / "nested.txt").is_file(), (
            "nested initial_file not materialised at its relative path"
        )

        # Invariant 1: snapshot keys are sandbox-relative POSIX.
        snap = env.snapshot(s0)
        assert isinstance(snap, FilesystemSnapshot)
        assert "keep.txt" in snap.files, "snapshot must key files by sandbox-relative POSIX path"
        assert "sub/nested.txt" in snap.files, "nested file must use forward-slash POSIX key"
        for key in snap.files:
            assert _is_relative_posix(key), (
                f"snapshot key {key!r} is not sandbox-relative POSIX (no "
                "backslashes / absolute / drive prefixes) — checks.py would "
                "silently misfire"
            )
        for d in snap.dirs:
            assert _is_relative_posix(d), f"snapshot dir {d!r} is not sandbox-relative POSIX"

        # Invariant 3: escape detection is wired into snapshot.
        assert isinstance(snap.escaped_paths, tuple), (
            "snapshot must populate escaped_paths (from check_canaries()) — "
            "an empty tuple is fine, a missing one means escape detection is "
            "not wired in"
        )

        # Canaries live OUTSIDE the sandbox.
        resolved_root = host_root.resolve()
        for p in env.canary_paths():
            assert resolved_root not in Path(p).resolve().parents and Path(p).resolve() != resolved_root, (
                f"canary {p} must be outside the sandbox root {resolved_root}"
            )

        # Invariant 5: a timeout is data, never a raised exception.
        slow = env.exec(
            exec_sleep_argv,
            cwd=s0.root,
            timeout=exec_timeout_seconds,
        )
        assert isinstance(slow, ProcessResult) and slow.timed_out is True, (
            "exec() exceeding its timeout must return ProcessResult(timed_out="
            "True), never raise (a hung agent is rubric F, not a harness error)"
        )

        # A normal exec completes with a real returncode.
        ok = env.exec(exec_ok_argv, cwd=s0.root, timeout=30)
        assert isinstance(ok, ProcessResult) and ok.returncode is not None and not ok.timed_out, (
            "a fast exec() must return a ProcessResult with a real returncode"
        )

        # probe() fingerprints the context and tags it with env_id.
        info = env.probe()
        assert isinstance(info, dict) and info.get("env_id") == env_id, (
            "probe() must return a dict carrying env_id for the log header"
        )

        # Fresh sandbox per trial: a second setup yields a different root.
        s1 = env.setup_sandbox("conformance", 1, preconditions)
        try:
            assert s1.root != s0.root, "each trial must get a NEW sandbox (distinct root)"
        finally:
            env.teardown_sandbox(s1)

        # Invariant 6: a missing required tool is refused loudly.
        raised = False
        try:
            env.setup_sandbox(
                "conformance", 2,
                {"required_tools": ["__definitely_absent_tool_xyz__"]},
            )
        except Exception:  # noqa: BLE001 - any raise satisfies the contract
            raised = True
        assert raised, (
            "setup_sandbox must raise when a required_tool is missing (a "
            "silently-degraded run would confound the cell)"
        )

        obs["snapshot_file_keys"] = len(snap.files)
        obs["probe_keys"] = sorted(info)
    finally:
        # teardown must be safe to call twice.
        env.teardown_sandbox(s0)
        env.teardown_sandbox(s0)
    assert not Path(s0.host_root).exists(), "teardown_sandbox must destroy the sandbox"

    if exercise_canaries:
        env.set_canaries()
        assert env.check_canaries() == (), "freshly-set canaries must report no escape"
        targets = env.canary_paths()
        if targets:
            targets[0].write_bytes(b"conformance: simulated escape")
            escaped = env.check_canaries()
            assert any(str(targets[0]) in e and "[modified]" in e for e in escaped), (
                "a modified canary must be detected as an escape"
            )
        env.cleanup_canaries()
        env.cleanup_canaries()  # idempotent
        obs["exercised_canaries"] = True

    return obs


# ---------------------------------------------------------------------------
# registry consistency
# ---------------------------------------------------------------------------


def assert_registry_consistency() -> dict[str, object]:
    """The registry maps each id to a class whose own id matches, and the
    implemented and planned sets never overlap. Guards the registry edit every
    new adapter makes (move an id from _PLANNED_* into the live map)."""
    from harness import registry as reg

    for rid, cls in reg._ENVIRONMENTS.items():
        assert cls.env_id == rid, f"env registry key {rid!r} != class env_id {cls.env_id!r}"
    for rid, cls in reg._AGENTS.items():
        assert cls.agent_id == rid, f"agent registry key {rid!r} != class agent_id {cls.agent_id!r}"
    assert reg._ENVIRONMENTS.keys().isdisjoint(reg._PLANNED_ENVIRONMENTS), (
        "an env id is both implemented and listed as planned"
    )
    assert reg._AGENTS.keys().isdisjoint(reg._PLANNED_AGENTS), (
        "an agent id is both implemented and listed as planned"
    )
    return {
        "implemented_envs": sorted(reg._ENVIRONMENTS),
        "implemented_agents": sorted(reg._AGENTS),
        "planned_envs": sorted(reg._PLANNED_ENVIRONMENTS),
        "planned_agents": sorted(reg._PLANNED_AGENTS),
    }
