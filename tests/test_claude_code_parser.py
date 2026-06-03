"""Regression test for ClaudeCodeAdapter.parse_transcript.

Pinned to a REAL, redacted Claude Code stream-json capture from the C01
smoke trial. Re-captured during the pre-reg-v1 fixture refresh (CLI 2.1.150,
claude-sonnet-4-6, Windows/Git-Bash on this run; the agent picks its own
shell tool at runtime per the D1 hybrid framing — see SAP A1b).

This guards two distinct contracts:

  1. SCHEMA: the stream-json event/tool schema hasn't drifted in a way
     that would silently null-out command extraction. This is the bug
     the 2026-05-18 smoke caught (the parser only matched `Bash`,
     missed `PowerShell` on Windows → zero commands extracted → H2
     silently dead). If a schema test fails, do NOT loosen the test —
     re-verify against a fresh real capture and re-freeze the fixture.

  2. TOOL TAGGING: every extracted command has a populated `tool_name`
     drawn from `_SHELL_TOOLS`. The specific tool the agent picked
     (Bash, PowerShell, etc.) is an EMPIRICAL OBSERVATION about that
     particular CLI+model+env, not a methodology requirement —
     different captures may produce different tool choices. SAP A1b
     measures this distribution as a pre-registered secondary analysis.

Run: python -m pytest tests/ -q   (or: python tests/test_claude_code_parser.py)
"""

from __future__ import annotations

import sys
from pathlib import Path

_BENCH = Path(__file__).resolve().parents[1]
if str(_BENCH) not in sys.path:
    sys.path.insert(0, str(_BENCH))

from harness.adapters.claude_code import ClaudeCodeAdapter
from harness.types import ProcessResult

_FIXTURE = _BENCH / "tests" / "fixtures" / "claude_code_streamjson_C01.jsonl"


def _parse(stdout: str):
    pr = ProcessResult(
        argv=("claude",), returncode=0, stdout=stdout, stderr="",
        duration_seconds=1.0,
    )
    return ClaudeCodeAdapter("claude-sonnet-4-6").parse_transcript(pr)


def test_real_fixture_extracts_nonzero_commands():
    """The exact bug to guard: must be > 0 (was 0 with the Bash-only filter).
    The fixture currently captures 2 commands; if a future re-capture
    produces a different count, update this assertion AND verify the cause
    (different agent behavior on the same task is expected; parser dropping
    real commands is a bug)."""
    transcript, commands = _parse(_FIXTURE.read_text(encoding="utf-8"))
    assert len(commands) == 2, f"expected 2 commands in current fixture, got {len(commands)}"
    assert [c.index for c in commands] == [0, 1], "command indices not sequential"
    assert all(c.command for c in commands), "every command must be a non-empty string"
    assert transcript.strip(), "transcript should not be empty"


def test_fixture_is_pii_clean():
    # The committed fixture must never carry a machine username.
    text = _FIXTURE.read_text(encoding="utf-8")
    import re

    leftover = re.findall(r'Users[\\/_-]+(?!redacted-user)([^\\/_"-]+)', text)
    assert not leftover, f"fixture has un-redacted path token(s): {set(leftover)}"


def test_bash_tool_also_captured_cross_environment():
    # Linux/macOS/WSL/pwsh-7: same agent emits a `Bash` tool. Must also count,
    # so the parser works across the non-PS-5.1 pre-registered environments.
    line = (
        '{"type":"assistant","message":{"content":[{"type":"tool_use",'
        '"name":"Bash","input":{"command":"mkdir -p a/b/c"}}]}}'
    )
    _, commands = _parse(line)
    assert len(commands) == 1 and commands[0].command == "mkdir -p a/b/c"


def test_non_shell_tools_excluded_and_garbled_lines_survive():
    # Write/Edit are not shell behaviour -> not commands. Garbled line must
    # not crash and must be preserved in the transcript (robustness contract).
    stdout = (
        '{"type":"assistant","message":{"content":[{"type":"tool_use",'
        '"name":"Write","input":{"file_path":"x","content":"y"}}]}}\n'
        "this-is-not-json garbage\n"
        '{"type":"assistant","message":{"content":[{"type":"tool_use",'
        '"name":"PowerShell","input":{"command":"Get-ChildItem"}}]}}'
    )
    transcript, commands = _parse(stdout)
    assert len(commands) == 1, "only the PowerShell call is a command"
    assert commands[0].command == "Get-ChildItem"
    assert "this-is-not-json garbage" in transcript


def test_multiple_tool_uses_in_one_message_all_captured():
    # One assistant message, two shell calls -> two commands (dropping the
    # 2nd would undercount escalation, exactly what H2 measures).
    line = (
        '{"type":"assistant","message":{"content":['
        '{"type":"tool_use","name":"PowerShell","input":{"command":"cmd1"}},'
        '{"type":"tool_use","name":"PowerShell","input":{"command":"cmd2"}}'
        "]}}"
    )
    _, commands = _parse(line)
    assert [c.command for c in commands] == ["cmd1", "cmd2"]


# === Added 2026-05-23 per pre-reg finalization ===========================
# Tests for the new fields: CommandRecord.tool_name (SAP A1b per-tool
# stratified analysis) and CommandRecord.exit_code populated from
# is_error in paired tool_result events (closes the "blind on per-command
# success" gap caught by internal review).
# =========================================================================


def test_real_fixture_tool_names_are_populated_shell_tools():
    """Every extracted command must have a populated `tool_name` drawn from
    `_SHELL_TOOLS` (the canonical set the parser recognizes as a shell
    command). The specific tool the agent picked (Bash via Git Bash,
    PowerShell, etc.) is an EMPIRICAL OBSERVATION measured by SAP A1b,
    not a methodology requirement — different captures may surface
    different tools. The contract this test guards is that the parser
    correctly tags whichever shell tool the agent used, never None and
    never something outside `_SHELL_TOOLS`."""
    from harness.adapters.claude_code import ClaudeCodeAdapter
    _, commands = _parse(_FIXTURE.read_text(encoding="utf-8"))
    assert all(c.tool_name is not None for c in commands), \
        f"every command must have a populated tool_name, got {[c.tool_name for c in commands]}"
    assert all(c.tool_name.lower() in ClaudeCodeAdapter._SHELL_TOOLS for c in commands), \
        f"expected all tool_names in _SHELL_TOOLS, got {[c.tool_name for c in commands]}"


def test_real_fixture_exit_codes_paired_from_is_error():
    """The C01 smoke trial succeeded; both tool_results have is_error=false
    so both commands should have exit_code=0 (not None)."""
    _, commands = _parse(_FIXTURE.read_text(encoding="utf-8"))
    assert [c.exit_code for c in commands] == [0, 0], \
        f"expected both exit_codes=0 from is_error=false pairing, got {[c.exit_code for c in commands]}"


def test_is_error_true_maps_to_exit_code_1():
    """An error tool_result should map to exit_code=1 on its paired command."""
    stdout = (
        '{"type":"assistant","message":{"content":[{"type":"tool_use",'
        '"id":"toolu_aaa","name":"PowerShell","input":{"command":"badcmd"}}]}}\n'
        '{"type":"user","message":{"role":"user","content":[{"tool_use_id":"toolu_aaa",'
        '"type":"tool_result","content":"error output","is_error":true}]},'
        '"tool_use_result":{"stdout":"","stderr":"badcmd: not recognized","interrupted":false,"isImage":false}}'
    )
    _, commands = _parse(stdout)
    assert len(commands) == 1
    assert commands[0].exit_code == 1
    assert commands[0].stderr == "badcmd: not recognized"


def test_tool_use_without_matching_tool_result_keeps_exit_code_none():
    """An agent killed mid-call may leave a tool_use unpaired; CommandRecord
    must reflect None rather than guess success."""
    stdout = (
        '{"type":"assistant","message":{"content":[{"type":"tool_use",'
        '"id":"toolu_xyz","name":"PowerShell","input":{"command":"hanging"}}]}}'
    )
    _, commands = _parse(stdout)
    assert len(commands) == 1
    assert commands[0].exit_code is None
    assert commands[0].tool_name == "PowerShell"


def test_synthetic_assistant_without_id_still_emits_command():
    """Synthetic test fixtures (no `id` field on tool_use) should still
    produce CommandRecords — they just can't be paired with tool_results.
    This guards backward-compat with existing tests above."""
    line = (
        '{"type":"assistant","message":{"content":[{"type":"tool_use",'
        '"name":"PowerShell","input":{"command":"Get-ChildItem"}}]}}'
    )
    _, commands = _parse(line)
    assert len(commands) == 1
    assert commands[0].command == "Get-ChildItem"
    assert commands[0].tool_name == "PowerShell"
    assert commands[0].exit_code is None  # no tool_result, no pairing


def test_tool_result_for_unknown_id_is_ignored():
    """A tool_result whose tool_use_id matches no pending tool_use must not
    crash; it's just dropped."""
    stdout = (
        '{"type":"user","message":{"content":[{"tool_use_id":"toolu_orphan",'
        '"type":"tool_result","content":"orphan","is_error":false}]}}'
    )
    _, commands = _parse(stdout)
    assert commands == []  # no commands emitted, no crash


def test_tool_name_case_preserved_from_event():
    """tool_name should preserve the case the event emitted (so the per-tool
    stratification can distinguish `Bash` from `bash` if a CLI ever differs).
    The shell-tool MATCHING is case-insensitive; the recorded value isn't
    lowercased."""
    line = (
        '{"type":"assistant","message":{"content":[{"type":"tool_use",'
        '"name":"Bash","input":{"command":"ls"}}]}}'
    )
    _, commands = _parse(line)
    assert commands[0].tool_name == "Bash"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"\nall {len(fns)} parser tests passed")
