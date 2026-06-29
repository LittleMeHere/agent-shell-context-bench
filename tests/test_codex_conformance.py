"""Conformance battery for the Codex CLI agent adapter (configs #3/#4).

Runs the shared, infrastructure-free agent battery
(`tests/conformance.py::assert_agent_adapter_conforms`) against a real
CodexAdapter instance — the merge gate for the adapter. The battery feeds
synthetic transcripts, so it runs in CI immediately with no codex CLI or
auth, exactly like the Claude Code agent conformance check.

A second test asserts the pinned invocation shape (the reproducibility
surface in the VERSION PIN block of `harness/adapters/codex.py`): a wrong
flag here silently corrupts every H2 number, so the pins are guarded by a
test, not just prose.

Run: python -m pytest tests/ -q   (or: python tests/test_codex_conformance.py)
"""

from __future__ import annotations

import sys
from pathlib import Path

_BENCH = Path(__file__).resolve().parents[1]
if str(_BENCH) not in sys.path:
    sys.path.insert(0, str(_BENCH))

from harness.adapters.base import AgentAdapter
from harness.adapters.codex import CodexAdapter
from harness.types import SandboxHandle
from tests.conformance import assert_agent_adapter_conforms


def test_codex_agent_conforms():
    obs = assert_agent_adapter_conforms(CodexAdapter("gpt-5.4-mini"))
    assert obs["agent_id"] == "codex"
    assert obs["default_cli_path"] == "codex"


def test_codex_does_not_override_run():
    """Invariant 4 (mechanical half): the template method `run()` must be the
    base one, so the exec/parse/error-capture path is identical across cells.
    Asserted by the battery too; pinned here as the explicit report-back."""
    assert CodexAdapter.run is AgentAdapter.run


def test_codex_build_invocation_pins_documented_flags():
    """Guards the VERSION PIN block: argv[0] is the resolved CLI, and the
    pinned `codex exec --json` flag set + `-C <sandbox.root>` + trailing
    prompt are present in order. If the CLI changes a flag, fix
    build_invocation and update docs/VERSIONS.md — do not relax this test."""
    sandbox = SandboxHandle(
        task_id="conformance", trial_index=0, env_id="conformance_env",
        root="/sandbox/root", host_root=Path("."),
    )
    argv = CodexAdapter("gpt-5.5").build_invocation("do the task", sandbox)

    assert argv[0] == "codex", "argv[0] must be the resolved cli_path"
    assert argv[1] == "exec", "headless subcommand must be `exec`"
    assert "-m" in argv and argv[argv.index("-m") + 1] == "gpt-5.5", (
        "model must be passed via -m <model_id>"
    )
    assert "--dangerously-bypass-approvals-and-sandbox" in argv, (
        "approval+sandbox bypass is required or the spiral cannot unfold"
    )
    assert "--ephemeral" in argv, "no persisted session state per trial"
    assert "--json" in argv, "structured JSONL stream is required for H2"
    assert "-C" in argv and argv[argv.index("-C") + 1] == "/sandbox/root", (
        "-C must bind the sandbox root"
    )
    assert argv[-1] == "do the task", "prompt must be the trailing positional arg"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"\nall {len(fns)} codex conformance tests passed")
