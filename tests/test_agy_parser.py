"""Unit tests for AgyAdapter — the Antigravity CLI adapter.

Unlike the Claude Code parser test (pinned to a real redacted stream-json
capture), this suite is driven by synthetic transcripts shaped to agy's brain
schema. This is deliberate:

  * agy's command stream is OUT-OF-BAND (CONTRACT GAP (1)) — it is not on the
    ProcessResult the adapter is handed — and the real schema is characterised
    only from a 1.0.2 smoke whose 1.0.7 re-capture (with a failing command) is
    a pre-DATA obligation per docs/VERSIONS.md. Fabricating a "real capture"
    before that re-smoke would be inventing data; synthetic fixtures shaped to
    the documented schema (PLANNER_RESPONSE.tool_calls[] with name/CommandLine/
    Cwd; prose RUN_COMMAND.content) test the parser honestly without it.
  * agy transcripts also embed real local paths + git identity and require
    their own redaction pass (VERSIONS.md 2026-06-10 CAVEAT (iv)); keeping the
    fixtures synthetic keeps this test file capture-free by construction.

What is proven here:
  1. SCHEMA: parse_brain_transcript extracts ordered CommandRecords from
     PLANNER_RESPONSE.tool_calls[], command=args.CommandLine, tool_name=name.
  2. PROSE OUTCOME: exit_code/stdout parsed best-effort from RUN_COMMAND.content
     (success sentence -> 0; failure/ERROR -> 1; ambiguous -> None; Output block
     captured and truncation-marker-aware) — CAVEATs (i)/(ii).
  3. ROBUSTNESS: the parser NEVER raises on garbled/truncated/empty/ill-typed
     input — a crashed run with three good events is still three events.
  4. CONTRACT GAP (1): parse_transcript(process) returns the prose transcript
     and ZERO commands (the command stream is unreachable from ProcessResult).
  5. CONTRACT GAP (2): model_settings_patch merges {"model": model_id} without
     clobbering other settings keys.
  6. CONTRACT GAP (3): per-command Cwd is captured as a sidecar (no CommandRecord
     field) and classify_cwd_tags labels sandbox/scratch/elsewhere correctly.
  7. The adapter passes the shared assert_agent_adapter_conforms battery.

Run: python -m pytest tests/ -q   (or: python tests/test_agy_parser.py)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_BENCH = Path(__file__).resolve().parents[1]
if str(_BENCH) not in sys.path:
    sys.path.insert(0, str(_BENCH))

from harness.adapters.agy import (
    CWD_ELSEWHERE,
    CWD_IN_AGY_SCRATCH,
    CWD_IN_SANDBOX,
    AgyAdapter,
)
from harness.types import CommandRecord, ProcessResult, SandboxHandle
from tests.conformance import assert_agent_adapter_conforms


# --------------------------------------------------------------------------- #
# synthetic transcript builders (shaped to the documented brain schema)
# --------------------------------------------------------------------------- #


def _planner_event(*tool_calls: dict, status: str = "DONE") -> str:
    """One PLANNER_RESPONSE line carrying the given tool_calls."""
    return json.dumps({
        "type": "PLANNER_RESPONSE",
        "status": status,
        "tool_calls": list(tool_calls),
    })


def _run_command_event(content: str, status: str = "DONE") -> str:
    """One RUN_COMMAND outcome line with prose `content`."""
    return json.dumps({"type": "RUN_COMMAND", "status": status, "content": content})


def _shell_call(command: str, cwd: str = "", name: str = "RUN_COMMAND") -> dict:
    """A shell tool_call entry inside a PLANNER_RESPONSE.tool_calls[]."""
    return {"name": name, "args": {"CommandLine": command, "Cwd": cwd}}


_SUCCESS_CONTENT = (
    "Created: 2026-06-22T10:00:00Z\n"
    "Completed: 2026-06-22T10:00:01Z\n"
    "The command completed successfully.\n"
    "Output:\n"
    "hello from agy\n"
)


def _adapter() -> AgyAdapter:
    return AgyAdapter("Gemini 3.1 Pro (High)")


# --------------------------------------------------------------------------- #
# 1. SCHEMA — command extraction from PLANNER_RESPONSE.tool_calls[]
# --------------------------------------------------------------------------- #


def test_extracts_command_from_planner_response():
    """The core: command=args.CommandLine, tool_name=name, index 0."""
    text = _planner_event(_shell_call("mkdir -p a/b/c", cwd="/sandbox"))
    _, commands, cwd_tags = AgyAdapter.parse_brain_transcript(text)
    assert len(commands) == 1
    assert commands[0].command == "mkdir -p a/b/c"
    assert commands[0].tool_name == "RUN_COMMAND"
    assert commands[0].index == 0
    # Sidecar Cwd captured in parallel (GAP (3)).
    assert len(cwd_tags) == 1
    assert cwd_tags[0]["cwd"] == "/sandbox"
    assert cwd_tags[0]["index"] == 0


def test_multiple_tool_calls_in_one_planner_response_all_captured():
    """Several shell tool_calls in one PLANNER_RESPONSE -> several commands, in
    order (dropping the 2nd+ would undercount the spiral H2 measures)."""
    text = _planner_event(
        _shell_call("cmd1", cwd="/sandbox"),
        _shell_call("cmd2", cwd="/sandbox"),
    )
    _, commands, cwd_tags = AgyAdapter.parse_brain_transcript(text)
    assert [c.command for c in commands] == ["cmd1", "cmd2"]
    assert [c.index for c in commands] == [0, 1]
    assert [t["index"] for t in cwd_tags] == [0, 1]


def test_indices_sequential_across_multiple_events():
    """Command indices are globally sequential from 0 across events (spiral
    order), and commands+cwd_tags stay the same length and order."""
    text = "\n".join([
        _planner_event(_shell_call("one", cwd="/sandbox")),
        _run_command_event(_SUCCESS_CONTENT),
        _planner_event(_shell_call("two", cwd="/sandbox")),
        _planner_event(_shell_call("three", cwd="/sandbox")),
    ])
    _, commands, cwd_tags = AgyAdapter.parse_brain_transcript(text)
    assert [c.index for c in commands] == [0, 1, 2]
    assert len(cwd_tags) == len(commands) == 3
    assert [t["index"] for t in cwd_tags] == [0, 1, 2]


def test_non_shell_tool_calls_excluded():
    """tool_calls that are not shell tools (planning, file edits) are not
    commands — mirrors the Claude Code parser excluding Read/Edit/Write so they
    don't dilute the spiral counts."""
    text = _planner_event(
        {"name": "PLANNER_THOUGHT", "args": {"text": "thinking"}},
        {"name": "EDIT_FILE", "args": {"path": "x", "content": "y"}},
        _shell_call("ls", cwd="/sandbox"),
    )
    _, commands, _ = AgyAdapter.parse_brain_transcript(text)
    assert len(commands) == 1 and commands[0].command == "ls"


def test_shell_tool_call_without_commandline_skipped():
    """A shell tool_call missing args.CommandLine is not a command (no empty
    CommandRecord — the battery forbids empty .command)."""
    text = _planner_event({"name": "RUN_COMMAND", "args": {"Cwd": "/sandbox"}})
    _, commands, _ = AgyAdapter.parse_brain_transcript(text)
    assert commands == []


def test_tool_name_case_preserved():
    """tool_name preserves the emitted case; shell-tool MATCHING is
    case-insensitive but the recorded value is not lowercased (parallels the
    Claude Code parser's case-preservation for SAP A1b)."""
    text = _planner_event(_shell_call("ls", cwd="/sandbox", name="Run_Command"))
    _, commands, _ = AgyAdapter.parse_brain_transcript(text)
    assert commands[0].tool_name == "Run_Command"


# --------------------------------------------------------------------------- #
# 2. PROSE OUTCOME — exit_code / stdout from RUN_COMMAND.content (CAVEATs i/ii)
# --------------------------------------------------------------------------- #


def test_success_sentence_maps_to_exit_code_0_and_captures_output():
    text = "\n".join([
        _planner_event(_shell_call("echo hello from agy", cwd="/sandbox")),
        _run_command_event(_SUCCESS_CONTENT),
    ])
    _, commands, _ = AgyAdapter.parse_brain_transcript(text)
    assert len(commands) == 1
    assert commands[0].exit_code == 0
    assert "hello from agy" in commands[0].stdout


def test_failure_sentence_maps_to_exit_code_1():
    content = (
        "Created: 2026-06-22T10:00:00Z\n"
        "The command failed with a non-zero exit.\n"
        "Output:\nbadcmd: not found\n"
    )
    text = "\n".join([
        _planner_event(_shell_call("badcmd", cwd="/sandbox")),
        _run_command_event(content),
    ])
    _, commands, _ = AgyAdapter.parse_brain_transcript(text)
    assert commands[0].exit_code == 1


def test_error_status_maps_to_exit_code_1_even_without_failure_sentence():
    """status=='ERROR' is itself a failure signal (CAVEAT (ii))."""
    text = "\n".join([
        _planner_event(_shell_call("flaky", cwd="/sandbox")),
        _run_command_event("Created: ...\nOutput:\n(no output)\n", status="ERROR"),
    ])
    _, commands, _ = AgyAdapter.parse_brain_transcript(text)
    assert commands[0].exit_code == 1


def test_ambiguous_outcome_keeps_exit_code_none():
    """No success/failure sentence and status not ERROR -> exit_code None
    (never guess). The successful-RUN_COMMAND format had no numeric code, so an
    ambiguous prose blob must not be coerced to 0."""
    text = "\n".join([
        _planner_event(_shell_call("ambiguous", cwd="/sandbox")),
        _run_command_event("Created: 2026-06-22T10:00:00Z\nSome neutral prose.\n"),
    ])
    _, commands, _ = AgyAdapter.parse_brain_transcript(text)
    assert commands[0].exit_code is None


def test_output_block_truncation_marker_bounds_stdout():
    """A "<truncated N lines>" marker bounds the captured stdout (CAVEAT (i):
    long output is truncated in-transcript; stdout is a bounded diagnostic)."""
    content = (
        "The command completed successfully.\n"
        "Output:\n"
        "line1\nline2\n"
        "<truncated 4096 lines>\n"
    )
    text = "\n".join([
        _planner_event(_shell_call("cat big", cwd="/sandbox")),
        _run_command_event(content),
    ])
    _, commands, _ = AgyAdapter.parse_brain_transcript(text)
    assert "line1" in commands[0].stdout and "line2" in commands[0].stdout
    assert "truncated" not in commands[0].stdout.lower()


def test_positional_pairing_first_outcome_to_first_command():
    """RUN_COMMAND outcomes pair positionally (no tool_call id in the result
    event): first outcome -> earliest unpaired command."""
    text = "\n".join([
        _planner_event(_shell_call("first", cwd="/sandbox")),
        _planner_event(_shell_call("second", cwd="/sandbox")),
        _run_command_event(_SUCCESS_CONTENT),  # pairs with "first"
    ])
    _, commands, _ = AgyAdapter.parse_brain_transcript(text)
    assert commands[0].command == "first" and commands[0].exit_code == 0
    assert commands[1].command == "second" and commands[1].exit_code is None


def test_run_command_without_pending_command_does_not_crash():
    """An orphan RUN_COMMAND outcome (no unpaired command) is just dropped."""
    text = _run_command_event(_SUCCESS_CONTENT)
    transcript, commands, cwd_tags = AgyAdapter.parse_brain_transcript(text)
    assert commands == [] and cwd_tags == []
    assert transcript.strip()


# --------------------------------------------------------------------------- #
# 3. ROBUSTNESS — never raise; partial data survives
# --------------------------------------------------------------------------- #


def test_garbled_lines_preserved_and_do_not_crash():
    text = "\n".join([
        "this is not json",
        _planner_event(_shell_call("ls", cwd="/sandbox")),
        '{"type":"PLANNER_RESPONSE","tool_calls": "not-a-list"}',
        "{ truncated json with no close",
    ])
    transcript, commands, _ = AgyAdapter.parse_brain_transcript(text)
    assert len(commands) == 1 and commands[0].command == "ls"
    assert "this is not json" in transcript


def test_empty_input_returns_empty():
    transcript, commands, cwd_tags = AgyAdapter.parse_brain_transcript("")
    assert transcript == "" and commands == [] and cwd_tags == []


def test_non_dict_json_lines_skipped():
    """A JSON line that decodes to a non-dict (e.g. a bare list/number) is
    preserved in the transcript and skipped, never raised on."""
    text = "\n".join(["[1, 2, 3]", "42", _planner_event(_shell_call("ok", cwd="/s"))])
    _, commands, _ = AgyAdapter.parse_brain_transcript(text)
    assert len(commands) == 1 and commands[0].command == "ok"


def test_tool_call_with_non_dict_args_skipped():
    """args present but not a dict -> entry skipped, no raise."""
    text = json.dumps({
        "type": "PLANNER_RESPONSE",
        "tool_calls": [{"name": "RUN_COMMAND", "args": "oops-a-string"}],
    })
    _, commands, _ = AgyAdapter.parse_brain_transcript(text)
    assert commands == []


def test_run_command_content_non_string_does_not_crash():
    """RUN_COMMAND.content that is not a string (e.g. a dict) must not crash the
    prose parser; it degrades to no usable outcome."""
    text = "\n".join([
        _planner_event(_shell_call("x", cwd="/sandbox")),
        json.dumps({"type": "RUN_COMMAND", "status": "DONE", "content": {"weird": 1}}),
    ])
    _, commands, _ = AgyAdapter.parse_brain_transcript(text)
    assert len(commands) == 1  # command still extracted; outcome simply unpaired/none


# --------------------------------------------------------------------------- #
# 4. CONTRACT GAP (1) — parse_transcript(process) cannot see the commands
# --------------------------------------------------------------------------- #


def test_parse_transcript_returns_prose_and_zero_commands():
    """The command stream is out-of-band; from the ProcessResult ALONE the
    honest result is the prose stdout transcript and an EMPTY command list."""
    pr = ProcessResult(
        argv=("agy", "--print", "..."),
        returncode=0,
        stdout="I created the files in the sandbox as requested.",
        stderr="",
        duration_seconds=1.0,
    )
    transcript, commands = _adapter().parse_transcript(pr)
    assert commands == []
    assert "created the files" in transcript


def test_parse_transcript_never_raises_on_empty_process():
    pr = ProcessResult(
        argv=("agy",), returncode=None, stdout="", stderr="", duration_seconds=0.0,
    )
    transcript, commands = _adapter().parse_transcript(pr)
    assert transcript == "" and commands == []


# --------------------------------------------------------------------------- #
# 5. CONTRACT GAP (2) — model pin is a settings.json patch, not argv
# --------------------------------------------------------------------------- #


def test_model_settings_patch_sets_model_field():
    patch = _adapter().model_settings_patch()
    assert patch == {"model": "Gemini 3.1 Pro (High)"}


def test_model_settings_patch_preserves_existing_keys():
    existing = {"telemetry": False, "model": "OLD", "theme": "dark"}
    patch = _adapter().model_settings_patch(existing)
    assert patch["model"] == "Gemini 3.1 Pro (High)"
    assert patch["telemetry"] is False and patch["theme"] == "dark"
    # Input not mutated (pure).
    assert existing["model"] == "OLD"


def test_build_invocation_has_no_model_flag():
    """The model is NEVER an argv flag for agy (GAP (2)); it must not leak into
    build_invocation. Guards against a future edit accidentally adding --model."""
    argv = _adapter().build_invocation("do the task", _sandbox())
    assert "--model" not in argv
    assert "Gemini 3.1 Pro (High)" not in " ".join(argv)


# --------------------------------------------------------------------------- #
# 6. CONTRACT GAP (3) — Cwd directive injection + per-command Cwd tagging
# --------------------------------------------------------------------------- #


def test_build_invocation_prepends_cwd_directive():
    """SAP rule 1: the prompt is prepended with the sandbox-binding directive."""
    sb = _sandbox(root="/trial/sandbox/root")
    argv = _adapter().build_invocation("Create foo.txt", sb)
    assert argv[0] == "agy" and "--print" in argv
    injected = argv[-1]
    assert "/trial/sandbox/root" in injected
    assert injected.endswith("Create foo.txt")
    assert "working directory" in injected.lower()


def test_classify_cwd_tags_labels_sandbox_scratch_elsewhere():
    """SAP rule 2: per-command args.Cwd -> cwd_in_sandbox / cwd_in_agy_scratch /
    cwd_elsewhere."""
    sandbox_root = "C:/Users/x/AppData/Local/Temp/sbx_T01"
    scratch_root = "C:/Users/x/.gemini/antigravity-cli/scratch"
    raw_tags = [
        {"index": 0, "cwd": sandbox_root, "tag": None},                 # exact sandbox
        {"index": 1, "cwd": sandbox_root + "/sub/deep", "tag": None},   # under sandbox
        {"index": 2, "cwd": scratch_root, "tag": None},                 # exact scratch
        {"index": 3, "cwd": scratch_root + "/tmp", "tag": None},        # under scratch
        {"index": 4, "cwd": "C:/Windows/System32", "tag": None},        # elsewhere
        {"index": 5, "cwd": "", "tag": None},                            # missing -> elsewhere
    ]
    tagged = AgyAdapter.classify_cwd_tags(
        raw_tags, sandbox_root=sandbox_root, scratch_root=scratch_root
    )
    assert [t["tag"] for t in tagged] == [
        CWD_IN_SANDBOX, CWD_IN_SANDBOX,
        CWD_IN_AGY_SCRATCH, CWD_IN_AGY_SCRATCH,
        CWD_ELSEWHERE, CWD_ELSEWHERE,
    ]


def test_classify_cwd_tags_normalizes_backslashes():
    """Windows backslash Cwd values classify the same as forward-slash ones
    (the transcript may carry native Windows paths)."""
    sandbox_root = r"C:\Users\x\Temp\sbx"
    scratch_root = r"C:\Users\x\.gemini\antigravity-cli\scratch"
    raw_tags = [
        {"index": 0, "cwd": r"C:\Users\x\Temp\sbx\inner", "tag": None},
        {"index": 1, "cwd": r"C:\Users\x\.gemini\antigravity-cli\scratch", "tag": None},
    ]
    tagged = AgyAdapter.classify_cwd_tags(
        raw_tags, sandbox_root=sandbox_root, scratch_root=scratch_root
    )
    assert [t["tag"] for t in tagged] == [CWD_IN_SANDBOX, CWD_IN_AGY_SCRATCH]


def test_classify_cwd_tags_prefix_is_path_boundary_not_substring():
    """A sandbox-root string PREFIX that is not a path-segment boundary must NOT
    count as in-sandbox (e.g. '/sbx_evil' is not under '/sbx')."""
    tagged = AgyAdapter.classify_cwd_tags(
        [{"index": 0, "cwd": "/tmp/sbx_evil", "tag": None}],
        sandbox_root="/tmp/sbx", scratch_root="/scratch",
    )
    assert tagged[0]["tag"] == CWD_ELSEWHERE


def test_cwd_tag_count_matches_command_count():
    """commands and the sidecar cwd_tags are always parallel (same length /
    order) so the per-trial log can join them by index (GAP (3) option (a))."""
    text = "\n".join([
        _planner_event(
            _shell_call("a", cwd="/sandbox"),
            _shell_call("b", cwd="/scratch"),
        ),
        _planner_event(_shell_call("c", cwd="/elsewhere")),
    ])
    _, commands, cwd_tags = AgyAdapter.parse_brain_transcript(text)
    assert len(commands) == len(cwd_tags) == 3
    assert [t["cwd"] for t in cwd_tags] == ["/sandbox", "/scratch", "/elsewhere"]


# --------------------------------------------------------------------------- #
# 7. shared conformance battery + adapter identity
# --------------------------------------------------------------------------- #


def test_agy_adapter_conforms():
    obs = assert_agent_adapter_conforms(_adapter())
    assert obs["agent_id"] == "agy"
    # The battery's synthetic cases are Claude-Code-shaped stream-json, which is
    # NOT agy's brain schema, so parse_transcript extracts ZERO commands from
    # them — exactly the out-of-band contract (GAP (1)). The battery only
    # requires no-raise + well-formed (empty) output, which holds.
    assert obs["parse_transcript_total_commands"] == 0


def test_agy_registered_and_default_path():
    from harness.registry import make_agent

    agent = make_agent("agy", "Gemini 3.5 Flash (Medium)")
    assert isinstance(agent, AgyAdapter)
    assert agent.agent_id == "agy"
    assert AgyAdapter._default_cli_path() == "agy"


def test_run_template_method_not_overridden():
    """Invariant 4 (mechanical half) at the adapter level: agy must NOT override
    the template run() — the exec/parse/error path stays identical across cells."""
    from harness.adapters.base import AgentAdapter

    assert AgyAdapter.run is AgentAdapter.run


def test_records_are_plain_commandrecords():
    """Extraction yields real CommandRecord instances (not a look-alike), so the
    on-disk log schema (types.py) is honoured without modification."""
    text = _planner_event(_shell_call("ls", cwd="/sandbox"))
    _, commands, _ = AgyAdapter.parse_brain_transcript(text)
    assert all(isinstance(c, CommandRecord) for c in commands)


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #


def _sandbox(root: str = "/conformance/sandbox") -> SandboxHandle:
    return SandboxHandle(
        task_id="agy_test", trial_index=0, env_id="test_env",
        root=root, host_root=Path("."),
    )


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"\nall {len(fns)} agy parser tests passed")
