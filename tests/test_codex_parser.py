"""Regression test for CodexAdapter.parse_transcript.

Unlike `test_claude_code_parser.py` (pinned to a REAL, redacted Claude Code
capture), this suite runs against SYNTHETIC JSONL shaped to the documented
`codex exec --json` schema (the 2026-05-25 smoke characterisation recorded
in docs/VERSIONS.md: command-completion is `type == "item.completed"` whose
item carries STRUCTURED `command` / `exit_code` / `aggregated_output`
fields). A real capture needs the codex CLI + OpenAI auth and is FLAGGED FOR
LATER — at the pre-collection re-smoke a frozen real fixture replaces this
synthetic coverage, exactly as `scripts/make_parser_fixture.py` froze the
Claude Code fixture. See the PARSER STATUS block in
`harness/adapters/codex.py`.

This guards two distinct contracts:

  1. SCHEMA: the documented `item.completed` command-item shape extracts the
     command, its exit code, and its aggregated output as structured fields
     (no tool_use_id pairing). If a real capture shows the schema drifted in
     a way that nulls extraction, do NOT loosen the test — re-verify against
     a fresh real capture and freeze a fixture (the Claude Code Bash-only
     bug — zero commands extracted, H2 silently dead — is the failure mode
     this guards against for Codex).

  2. ROBUSTNESS: empty / garbled / truncated / non-command-item input must
     degrade to a best-effort partial, never raise (the adapters/base.py
     'never raise' contract — a partial transcript is still data).

Run: python -m pytest tests/ -q   (or: python tests/test_codex_parser.py)
"""

from __future__ import annotations

import sys
from pathlib import Path

_BENCH = Path(__file__).resolve().parents[1]
if str(_BENCH) not in sys.path:
    sys.path.insert(0, str(_BENCH))

from harness.adapters.codex import CodexAdapter
from harness.types import ProcessResult


def _parse(stdout: str):
    pr = ProcessResult(
        argv=("codex",), returncode=0, stdout=stdout, stderr="",
        duration_seconds=1.0,
    )
    return CodexAdapter("gpt-5.4-mini").parse_transcript(pr)


def _completed_command(
    command: str, exit_code: int, aggregated_output: str,
    *, item_type: str = "command_execution",
) -> str:
    """One `item.completed` line for a shell command, documented-schema shape."""
    import json

    return json.dumps({
        "type": "item.completed",
        "item": {
            "item_type": item_type,
            "command": command,
            "exit_code": exit_code,
            "aggregated_output": aggregated_output,
        },
    })


# === schema: structured command-item extraction ==========================


def test_single_command_item_extracted_with_structured_fields():
    """The core contract: one command-completion event -> one CommandRecord
    with command / stdout(=aggregated_output) / exit_code read as structured
    fields (no cross-event pairing)."""
    line = _completed_command("mkdir -p a/b/c", 0, "")
    transcript, commands = _parse(line)
    assert len(commands) == 1
    cmd = commands[0]
    assert cmd.index == 0
    assert cmd.command == "mkdir -p a/b/c"
    assert cmd.exit_code == 0
    assert cmd.stdout == ""
    assert transcript.strip(), "transcript should not be empty"


def test_aggregated_output_becomes_stdout():
    line = _completed_command("ls", 0, "a\nb\nc\n")
    _, commands = _parse(line)
    assert commands[0].stdout == "a\nb\nc\n"
    assert commands[0].stderr == ""  # Codex merges streams into aggregated_output


def test_nonzero_exit_code_preserved():
    """A failing command keeps its real exit code — the A1b command-error
    signal rests on it (don't coerce a failure to look like success)."""
    line = _completed_command("badcmd", 127, "badcmd: command not found\n")
    _, commands = _parse(line)
    assert commands[0].exit_code == 127
    assert "not found" in commands[0].stdout


def test_multiple_commands_ordered_and_indexed_from_zero():
    """Two executed commands -> two CommandRecords in stream order, indices
    sequential from 0 (the spiral order H2 is scored on — dropping or
    reordering would undercount escalation)."""
    stdout = "\n".join([
        _completed_command("cmd1", 0, "out1"),
        _completed_command("cmd2", 1, "out2"),
        _completed_command("cmd3", 0, "out3"),
    ])
    _, commands = _parse(stdout)
    assert [c.index for c in commands] == [0, 1, 2]
    assert [c.command for c in commands] == ["cmd1", "cmd2", "cmd3"]
    assert [c.exit_code for c in commands] == [0, 1, 0]


def test_command_item_type_under_type_key_also_matched():
    """The item discriminator may arrive under `type` rather than `item_type`
    depending on schema spelling; both must be recognised so a minor relabel
    doesn't null extraction."""
    import json
    line = json.dumps({
        "type": "item.completed",
        "item": {
            "type": "command_execution",
            "command": "echo hi",
            "exit_code": 0,
            "aggregated_output": "hi\n",
        },
    })
    _, commands = _parse(line)
    assert len(commands) == 1 and commands[0].command == "echo hi"


def test_tool_name_populated_when_item_exposes_one():
    """If the item carries a shell-tool name, it is recorded for SAP A1b; the
    documented schema may not, in which case None is the honest record (see
    the no-tool-field test below)."""
    import json
    line = json.dumps({
        "type": "item.completed",
        "item": {
            "item_type": "command_execution",
            "command": "ls",
            "exit_code": 0,
            "aggregated_output": "",
            "tool_name": "local_shell",
        },
    })
    _, commands = _parse(line)
    assert commands[0].tool_name == "local_shell"


def test_tool_name_is_none_when_item_has_no_tool_field():
    """Documented schema surfaces structured command fields directly, no named
    tool block -> tool_name is None (A1b degrades to None for Codex honestly,
    rather than the parser inventing a tool name)."""
    line = _completed_command("pwd", 0, "/sandbox\n")
    _, commands = _parse(line)
    assert commands[0].tool_name is None


# === exclusion: non-command items are not shell commands =================


def test_non_command_completed_items_excluded():
    """`item.completed` events for non-command items (assistant message,
    reasoning, file patch) are NOT shell commands and must not be counted —
    counting them would dilute the spiral counts the rubric measures (the
    analogue of Claude Code excluding Read/Edit/Write)."""
    import json
    stdout = "\n".join([
        json.dumps({"type": "item.completed", "item": {
            "item_type": "agent_message", "text": "I'll create the dir."}}),
        json.dumps({"type": "item.completed", "item": {
            "item_type": "reasoning", "text": "thinking..."}}),
        json.dumps({"type": "item.completed", "item": {
            "item_type": "file_change", "path": "x.txt"}}),
        _completed_command("mkdir d", 0, ""),
    ])
    _, commands = _parse(stdout)
    assert len(commands) == 1, "only the command_execution item is a command"
    assert commands[0].command == "mkdir d"


def test_non_completed_event_types_ignored():
    """Lifecycle / streaming events that are not `item.completed` (e.g.
    `item.started`, `turn.completed`) carry no executed-command record and
    must be skipped without crashing."""
    import json
    stdout = "\n".join([
        json.dumps({"type": "thread.started", "thread_id": "t1"}),
        json.dumps({"type": "item.started", "item": {
            "item_type": "command_execution", "command": "ls"}}),
        json.dumps({"type": "turn.completed", "usage": {"input_tokens": 10}}),
    ])
    _, commands = _parse(stdout)
    assert commands == [], "no item.completed command event -> no commands"


# === robustness: never raise on bad input (adapters/base.py contract) =====


def test_empty_input_degrades():
    transcript, commands = _parse("")
    assert transcript == "" and commands == []


def test_garbled_lines_survive_in_transcript_and_dont_crash():
    """A non-JSON line must be preserved in the transcript and skipped for
    extraction (robustness contract) — interleaved with a valid command."""
    stdout = (
        "this-is-not-json garbage\n"
        + _completed_command("echo ok", 0, "ok\n")
        + "\nmore trailing garbage\n"
    )
    transcript, commands = _parse(stdout)
    assert len(commands) == 1 and commands[0].command == "echo ok"
    assert "this-is-not-json garbage" in transcript
    assert "more trailing garbage" in transcript


def test_truncated_final_line_does_not_crash():
    """A run killed mid-emit leaves a truncated last line; the good events
    before it must still be recovered (three good events of data)."""
    stdout = (
        _completed_command("cmd1", 0, "out1") + "\n"
        + '{"type":"item.completed","item":{"item_type":"command_'  # truncated
    )
    _, commands = _parse(stdout)
    assert len(commands) == 1 and commands[0].command == "cmd1"


def test_command_item_missing_exit_code_records_none():
    """A command item without an exit_code (e.g. interrupted mid-command)
    records exit_code=None rather than guessing success."""
    import json
    line = json.dumps({
        "type": "item.completed",
        "item": {
            "item_type": "command_execution",
            "command": "hanging",
            "aggregated_output": "",
        },
    })
    _, commands = _parse(line)
    assert len(commands) == 1
    assert commands[0].exit_code is None
    assert commands[0].command == "hanging"


def test_command_item_with_empty_command_skipped():
    """An item marked as a command but carrying no command string is not a
    usable record (every CommandRecord.command must be non-empty per the
    conformance battery) — skip it rather than emit an empty command."""
    import json
    stdout = "\n".join([
        json.dumps({"type": "item.completed", "item": {
            "item_type": "command_execution", "command": "",
            "exit_code": 0, "aggregated_output": ""}}),
        _completed_command("real", 0, ""),
    ])
    _, commands = _parse(stdout)
    assert [c.command for c in commands] == ["real"]


def test_list_form_command_joined():
    """Defensive: if a capture ever surfaces argv-list form, it is joined to a
    readable non-empty command rather than dropped or stringified as a list."""
    import json
    line = json.dumps({
        "type": "item.completed",
        "item": {
            "item_type": "command_execution",
            "command": ["bash", "-lc", "echo hi"],
            "exit_code": 0,
            "aggregated_output": "hi\n",
        },
    })
    _, commands = _parse(line)
    assert commands[0].command == "bash -lc echo hi"


def test_string_exit_code_coerced_to_int():
    """A stringified exit code is coerced to int; a non-numeric one degrades
    to None (the rubric is applied to what is observable)."""
    import json
    ok = json.dumps({"type": "item.completed", "item": {
        "item_type": "command_execution", "command": "a",
        "exit_code": "0", "aggregated_output": ""}})
    bad = json.dumps({"type": "item.completed", "item": {
        "item_type": "command_execution", "command": "b",
        "exit_code": "n/a", "aggregated_output": ""}})
    _, commands = _parse(ok + "\n" + bad)
    assert commands[0].exit_code == 0
    assert commands[1].exit_code is None


def test_bool_exit_code_rejected_as_none():
    """`exit_code` is an int field; a JSON bool (an int subclass in Python)
    must not be silently recorded as 0/1 — it is not a real exit code."""
    import json
    line = json.dumps({"type": "item.completed", "item": {
        "item_type": "command_execution", "command": "c",
        "exit_code": True, "aggregated_output": ""}})
    _, commands = _parse(line)
    assert commands[0].exit_code is None


def test_claude_code_shaped_json_yields_no_codex_commands():
    """Cross-schema safety: fed Claude-Code-shaped events (the conformance
    battery's 'mixed' case), the Codex parser must not raise and must extract
    zero commands — it only recognises its own `item.completed` command items,
    so it cannot mis-count another agent's transcript."""
    stdout = (
        '{"type":"assistant","message":{"content":[{"type":"tool_use",'
        '"name":"Bash","input":{"command":"echo hi"}}]}}\n'
        "trailing non-json garbage\n"
    )
    transcript, commands = _parse(stdout)
    assert commands == []
    assert transcript.strip()


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"\nall {len(fns)} codex parser tests passed")
