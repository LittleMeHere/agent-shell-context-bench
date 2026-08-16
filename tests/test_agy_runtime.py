"""Unit tests for the agy-cell runtime + the HomeFilesystem seam.

`harness/agy_runtime.py` is the runner-layer glue that resolves agy's two
remaining CONTRACT GAPs through the additive HomeFilesystem seam (out-of-band
brain-transcript location and scratch canary). It is
driven here entirely against an IN-MEMORY fake home — no agy install, no real
environment, no filesystem — so the orchestration is provable in isolation, the
same discipline test_agy_parser.py uses for the schema parser.

What is proven:
  1. SEAM: LocalHomeFilesystem round-trips read/write/listdir/remove/home_path
     against a temp home (PSTAX_HOME_ROOT), and every registered environment
     implements HomeFilesystem (required because agy runs on all five).
  2. BRAIN LOCATION (GAP (1) / rules 2+4): after_trial diffs brain/, parses the
     new conversation's transcript, and REPLACES the GAP-(1) empty command list
     with agy's real commands; absence degrades honestly (commands left as-is).
  4. Cwd TAGGING (rule 2): per-command tags + the descriptive compliance summary
     are computed from the located transcript.
  5. SCRATCH CANARY (rule 5): an unchanged sentinel reports no escape; a
     modified/removed one reports an annotated escape in the env-canary format.
  6. The runtime refuses an environment that cannot reach agy's home.

Run: python -m pytest tests/test_agy_runtime.py -q
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_BENCH = Path(__file__).resolve().parents[1]
if str(_BENCH) not in sys.path:
    sys.path.insert(0, str(_BENCH))

import pytest

from harness.adapters import agy as agy_mod
from harness.adapters.agy import AgyAdapter
from harness.agy_runtime import AgyTrialRuntime
from harness.environments.home_fs import HomeFilesystem, LocalHomeFilesystem
from harness.types import AgentRunResult, CommandRecord, ProcessResult, SandboxHandle


# --------------------------------------------------------------------------- #
# in-memory fake home (a HomeFilesystem with a dict-backed tree)
# --------------------------------------------------------------------------- #


def _norm(rel: str) -> str:
    return rel.replace("\\", "/").lstrip("/")


class _FakeHomeEnv(HomeFilesystem):
    """A HomeFilesystem backed by a dict, standing in for a real environment.

    Keys are home-relative POSIX paths; `home_listdir` returns the immediate
    child names under a relative dir, exactly as the real seams do. `writable`
    can be turned off to exercise the model-pin failure path."""

    env_id = "fake_home"

    def __init__(self, *, writable: bool = True) -> None:
        self.files: dict[str, str] = {}
        self.writable = writable

    def home_path(self, rel: str) -> str:
        return "/fakehome/" + _norm(rel)

    def home_read(self, rel: str) -> str | None:
        return self.files.get(_norm(rel))

    def home_write(self, rel: str, content: str) -> bool:
        if not self.writable:
            return False
        self.files[_norm(rel)] = content
        return True

    def home_remove(self, rel: str) -> None:
        self.files.pop(_norm(rel), None)

    def home_listdir(self, rel: str) -> list[str]:
        prefix = _norm(rel).rstrip("/") + "/"
        names: set[str] = set()
        for path in self.files:
            if path.startswith(prefix):
                names.add(path[len(prefix):].split("/", 1)[0])
        return sorted(names)


# --------------------------------------------------------------------------- #
# synthetic brain transcript + result builders
# --------------------------------------------------------------------------- #


def _planner(*calls: dict) -> str:
    planner = json.dumps(
        {"type": "PLANNER_RESPONSE", "status": "DONE", "tool_calls": list(calls)}
    )
    outcomes = [
        json.dumps(
            {
                "type": "RUN_COMMAND",
                "status": "DONE",
                "content": "The command completed successfully.\nOutput:\n",
            }
        )
        for call in calls
        if str(call.get("name", "")).lower() in AgyAdapter._SHELL_TOOLS
    ]
    return "\n".join([planner, *outcomes])


def _shell_call(command: str, cwd: str) -> dict:
    return {"name": "RUN_COMMAND", "args": {"CommandLine": command, "Cwd": cwd}}


def _adapter() -> AgyAdapter:
    return AgyAdapter("gemini-3.1-pro-high")


def _result(
    commands=None,
    transcript: str = "prose stdout",
    *,
    returncode: int | None = 0,
    stderr: str = "",
) -> AgentRunResult:
    return AgentRunResult(
        agent_id="agy",
        model_id="gemini-3.1-pro-high",
        prompt="do the task",
        raw_transcript=transcript,
        commands=list(commands) if commands else [],
        process=ProcessResult(
            argv=("agy", "--print", "..."),
            returncode=returncode,
            stdout=transcript,
            stderr=stderr,
            duration_seconds=1.0,
        ),
        wall_time_seconds=1.0,
        completed=True,
    )


def _sandbox(root: str = "/work/sbx_T01") -> SandboxHandle:
    return SandboxHandle(
        task_id="C01", trial_index=0, env_id="fake_home", root=root, host_root=Path("."),
    )


def _write_brain(env: _FakeHomeEnv, conv_id: str, transcript_text: str) -> None:
    """Simulate agy having run: a new brain conversation dir with a transcript."""
    rel = f"{agy_mod.BRAIN_REL_ROOT}/{conv_id}/{agy_mod.BRAIN_TRANSCRIPT_TAIL}"
    env.files[_norm(rel)] = transcript_text


# --------------------------------------------------------------------------- #
# 1. SEAM — LocalHomeFilesystem round-trip + registry guarantee
# --------------------------------------------------------------------------- #


def test_local_home_filesystem_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("PSTAX_HOME_ROOT", str(tmp_path))
    fs = LocalHomeFilesystem()

    rel = ".gemini/antigravity-cli/settings.json"
    assert fs.home_read(rel) is None  # absent -> None, never raises
    assert fs.home_write(rel, '{"model": "x"}') is True
    assert fs.home_read(rel) == '{"model": "x"}'
    # home_path is the OS-native absolute path under the temp home.
    assert fs.home_path(rel) == str(tmp_path / rel)
    # listdir returns immediate children (incl. dotfiles).
    assert "settings.json" in fs.home_listdir(".gemini/antigravity-cli")
    fs.home_remove(rel)
    assert fs.home_read(rel) is None
    # remove of an absent file is silent.
    fs.home_remove(rel)


def test_local_home_roundtrip_is_byte_faithful_for_lf_content(tmp_path, monkeypatch):
    """Historical settings-pin regression: default text mode translated
    LF->CRLF on Windows. The generic home seam remains byte-faithful even though
    current agy model pinning no longer mutates this file."""
    monkeypatch.setenv("PSTAX_HOME_ROOT", str(tmp_path))
    fs = LocalHomeFilesystem()
    rel = ".gemini/antigravity-cli/settings.json"
    target = tmp_path / rel
    target.parent.mkdir(parents=True)

    for label, raw in [
        ("LF-only (agy's real style)", b'{\n  "model": "x"\n}\n'),
        ("CRLF", b'{\r\n  "model": "x"\r\n}\r\n'),
    ]:
        target.write_bytes(raw)
        text = fs.home_read(rel)
        assert text is not None, label
        assert fs.home_write(rel, text) is True, label
        assert target.read_bytes() == raw, label


def test_local_home_listdir_absent_dir_is_empty(tmp_path, monkeypatch):
    monkeypatch.setenv("PSTAX_HOME_ROOT", str(tmp_path))
    assert LocalHomeFilesystem().home_listdir("nope/missing") == []


def test_local_home_listdir_is_sorted(tmp_path, monkeypatch):
    monkeypatch.setenv("PSTAX_HOME_ROOT", str(tmp_path))
    base = tmp_path / ".gemini" / "antigravity-cli" / "brain"
    (base / "conv_b").mkdir(parents=True)
    (base / "conv_a").mkdir(parents=True)
    assert LocalHomeFilesystem().home_listdir(".gemini/antigravity-cli/brain") == [
        "conv_a", "conv_b",
    ]


def test_all_registered_environments_implement_home_filesystem():
    """Every registered environment must CONCRETELY implement HomeFilesystem —
    agy runs on all five. Checks both the declared subclassing and that none of
    the seam's methods is left abstract: `issubclass` alone would pass a class
    that inherited the mixin but never implemented its methods, so this also
    asserts the env class is fully concrete (no HomeFilesystem method remains in
    `__abstractmethods__`)."""
    from harness.registry import _ENVIRONMENTS

    seam_methods = {"home_path", "home_read", "home_write", "home_remove", "home_listdir"}
    problems: list[str] = []
    for env_id, cls in _ENVIRONMENTS.items():
        if not issubclass(cls, HomeFilesystem):
            problems.append(f"{env_id}: not a HomeFilesystem")
            continue
        unimplemented = seam_methods & set(getattr(cls, "__abstractmethods__", frozenset()))
        if unimplemented:
            problems.append(f"{env_id}: HomeFilesystem methods left abstract: {sorted(unimplemented)}")
    assert not problems, problems


# --------------------------------------------------------------------------- #
# 2+3. BRAIN LOCATION + Cwd TAGGING (GAP (1), rules 2/4)
# --------------------------------------------------------------------------- #


def test_after_trial_locates_brain_replaces_commands_and_tags_cwd():
    env = _FakeHomeEnv()
    rt = AgyTrialRuntime(_adapter(), env)
    sandbox = _sandbox(root="/work/sbx_T01")
    scratch = env.home_path(agy_mod.SCRATCH_CANARY_REL_PATH.rsplit("/", 1)[0])

    ctx = rt.before_trial()  # brain empty, scratch canary placed
    # Simulate agy running: a new conversation with three commands in three
    # different working dirs (sandbox / scratch / elsewhere).
    _write_brain(env, "conv_abc", "\n".join([
        _planner(_shell_call("touch out.txt", sandbox.root)),
        _planner(_shell_call("ls", scratch)),
        _planner(_shell_call("whoami", "/nowhere")),
    ]))

    result = _result(commands=[])  # GAP (1): the launched process yields none
    outcome = rt.after_trial(ctx, result, sandbox)

    assert outcome.brain_located is True
    assert outcome.brain_candidate_count == 1
    # result was MUTATED with agy's real out-of-band commands (rule 4).
    assert [c.command for c in result.commands] == ["touch out.txt", "ls", "whoami"]
    assert all(isinstance(c, CommandRecord) for c in result.commands)
    # per-command Cwd tags (rule 2).
    assert [t["tag"] for t in outcome.cwd_tags] == [
        agy_mod.CWD_IN_SANDBOX, agy_mod.CWD_IN_AGY_SCRATCH, agy_mod.CWD_ELSEWHERE,
    ]
    # descriptive compliance summary.
    assert outcome.compliance["commands"] == 3
    assert outcome.compliance["cwd_in_sandbox"] == 1
    assert outcome.compliance["sandbox_compliance_rate"] == pytest.approx(1 / 3)
    assert outcome.scratch_escape is None  # canary untouched


def test_after_trial_missing_brain_degrades_honestly():
    """No new brain dir (agy did not run, or the home was unreachable): the
    result is left as the honest GAP-(1) degrade, not crashed or invented."""
    env = _FakeHomeEnv()
    rt = AgyTrialRuntime(_adapter(), env)
    ctx = rt.before_trial()
    result = _result(commands=[], transcript="only prose")
    outcome = rt.after_trial(ctx, result, _sandbox())

    assert outcome.brain_located is False
    assert outcome.brain_status == "missing"
    assert outcome.brain_candidate_count == 0
    assert outcome.cwd_tags == [] and outcome.compliance["commands"] == 0
    assert result.commands == [] and result.raw_transcript == "only prose"


def test_after_trial_marks_interactive_oauth_timeout_invalid():
    env = _FakeHomeEnv()
    rt = AgyTrialRuntime(_adapter(), env)
    ctx = rt.before_trial()
    result = _result(
        transcript="",
        returncode=1,
        stderr=(
            "Authentication required. Please visit the URL to log in:\n"
            "Waiting for authentication (timeout 60s)...\n"
            "Error: authentication failed or timed out\n"
        ),
    )

    outcome = rt.after_trial(ctx, result, _sandbox())

    assert outcome.brain_status == "missing"
    assert result.invalid is True
    assert result.harness_error == "agy authentication failed before model invocation"
    assert "Authentication required" in result.process.stderr


def test_after_trial_keeps_unrelated_nonzero_agent_exit_valid():
    env = _FakeHomeEnv()
    rt = AgyTrialRuntime(_adapter(), env)
    ctx = rt.before_trial()
    result = _result(transcript="ordinary agent failure", returncode=1)

    rt.after_trial(ctx, result, _sandbox())

    assert result.invalid is False
    assert result.harness_error is None


def test_after_trial_ignores_preexisting_brain_dirs():
    """Only conversations that appear DURING the trial are this trial's; a brain
    dir present before the run is not mistaken for the trial's transcript."""
    env = _FakeHomeEnv()
    _write_brain(env, "old_conv", _planner(_shell_call("stale", "/work/sbx_T01")))
    rt = AgyTrialRuntime(_adapter(), env)
    ctx = rt.before_trial()  # captures old_conv as pre-existing
    _write_brain(env, "new_conv", _planner(_shell_call("fresh", "/work/sbx_T01")))

    result = _result()
    outcome = rt.after_trial(ctx, result, _sandbox())
    assert outcome.brain_candidate_count == 1
    assert [c.command for c in result.commands] == ["fresh"]


def test_after_trial_records_multiple_candidates():
    """Multiple new conversations have ambiguous provenance and fail closed."""
    env = _FakeHomeEnv()
    rt = AgyTrialRuntime(_adapter(), env)
    ctx = rt.before_trial()
    _write_brain(env, "conv_a", _planner(_shell_call("a", "/work/sbx_T01")))
    _write_brain(env, "conv_b", _planner(_shell_call("b", "/work/sbx_T01")))

    result = _result()
    outcome = rt.after_trial(ctx, result, _sandbox())
    assert outcome.brain_located is False
    assert outcome.brain_status == "ambiguous"
    assert outcome.brain_candidate_count == 2
    assert result.commands == []


def test_agy_1_1_13_framing_events_are_valid_but_unknown_types_fail_closed():
    framing = [
        {"type": "USER_INPUT"},
        {"type": "CONVERSATION_HISTORY"},
        {"type": "EPHEMERAL_MESSAGE"},
        {"type": "CHECKPOINT"},
        {"type": "CODE_ACTION"},
    ]
    text = "\n".join([*(json.dumps(event) for event in framing), _planner(
        _shell_call("exit 7", "/work/sbx_T01")
    )])
    valid, malformed, shell_calls, outcomes = (
        AgyTrialRuntime._brain_parse_diagnostics(text)
    )
    assert (valid, malformed, shell_calls, outcomes) == (7, 0, 1, 1)

    unknown = text + '\n{"type":"FUTURE_UNREVIEWED_EVENT"}'
    assert AgyTrialRuntime._brain_parse_diagnostics(unknown)[1] == 1


def test_agy_1_1_13_numeric_separate_stream_outcome_is_complete():
    planner = json.dumps({
        "type": "PLANNER_RESPONSE",
        "status": "DONE",
        "tool_calls": [_shell_call("printf answer", "/work/sbx_T01")],
    })
    text = "\n".join([
        planner,
        json.dumps({
            "type": "RUN_COMMAND",
            "status": "DONE",
            "exit_code": 0,
            "content": (
                "Created At: 2026-08-14T00:00:00Z\n"
                "Completed At: 2026-08-14T00:00:01Z\n\n"
                "    The command exited with code 0.\n"
                "    Stdout:\n    answer\n    Stderr:\n    \n"
            ),
        }),
    ])
    assert AgyTrialRuntime._brain_parse_diagnostics(text) == (2, 0, 1, 1)


@pytest.mark.parametrize(
    "text",
    [
        "this is not jsonl",
        "",
        "{}",
        '{"type":"UNKNOWN_EVENT"}',
        '{"type":"PLANNER_RESPONSE","tool_calls":[]}\nnot-json',
        '{"type":"RUN_COMMAND","status":"DONE"}',
        '{"type":"PLANNER_RESPONSE","tool_calls":[{"name":"RUN_COMMAND","args":{"CommandLine":"echo x","Cwd":"/work"}}]}',
        '{"type":"RUN_COMMAND","status":"DONE","content":"The command completed successfully.\\nOutput:\\nx"}\n{"type":"PLANNER_RESPONSE","tool_calls":[{"name":"RUN_COMMAND","args":{"CommandLine":"echo late","Cwd":"/work"}}]}',
        '{"type":"PLANNER_RESPONSE","tool_calls":[{"name":"RUN_COMMAND","args":{"CommandLine":"echo x","Cwd":"/work"}}]}\n{"type":"RUN_COMMAND","status":"DONE"}',
    ],
)
def test_after_trial_malformed_or_schemaless_brain_fails_closed(text: str):
    env = _FakeHomeEnv()
    rt = AgyTrialRuntime(_adapter(), env)
    ctx = rt.before_trial()
    _write_brain(env, "conv_bad", text)

    result = _result(commands=[], transcript="only prose")
    outcome = rt.after_trial(ctx, result, _sandbox())

    assert outcome.brain_located is False
    assert outcome.brain_status == "parse_error"
    assert (
        outcome.brain_valid_event_count == 0
        or outcome.brain_malformed_line_count > 0
        or outcome.brain_shell_call_count != outcome.brain_outcome_event_count
    )
    assert result.commands == []
    assert result.raw_transcript == "only prose"


# --------------------------------------------------------------------------- #
# 5. SCRATCH CANARY (rule 5)
# --------------------------------------------------------------------------- #


def test_scratch_canary_modified_reports_escape():
    env = _FakeHomeEnv()
    rt = AgyTrialRuntime(_adapter(), env)
    ctx = rt.before_trial()
    # Agent tampers with the scratch sentinel.
    env.files[_norm(agy_mod.SCRATCH_CANARY_REL_PATH)] = "clobbered by agent"
    outcome = rt.after_trial(ctx, _result(), _sandbox())
    assert outcome.scratch_escape is not None
    assert outcome.scratch_escape.endswith("[modified]")


def test_scratch_canary_removed_reports_escape():
    env = _FakeHomeEnv()
    rt = AgyTrialRuntime(_adapter(), env)
    ctx = rt.before_trial()
    env.files.pop(_norm(agy_mod.SCRATCH_CANARY_REL_PATH), None)  # agent deleted it
    outcome = rt.after_trial(ctx, _result(), _sandbox())
    assert outcome.scratch_escape is not None
    assert outcome.scratch_escape.endswith("[removed]")


def test_scratch_canary_unwritable_reports_escape():
    """If the sentinel could not be placed at all, that location is reported as
    unmeasured (unwritable), mirroring the env-canary contract."""
    env = _FakeHomeEnv(writable=False)
    # Construct without pinning (pin would raise on this env); drive the trial
    # hooks directly to exercise the unwritable-canary branch.
    rt = AgyTrialRuntime(_adapter(), env)
    ctx = rt.before_trial()
    assert ctx.scratch_canary_written is False
    outcome = rt.after_trial(ctx, _result(), _sandbox())
    assert outcome.scratch_escape is not None
    assert outcome.scratch_escape.endswith("[unwritable]")


def test_scratch_canary_cleaned_up_after_check():
    """The runtime removes its own sentinel after checking (it is harness state,
    not the agent's data)."""
    env = _FakeHomeEnv()
    rt = AgyTrialRuntime(_adapter(), env)
    ctx = rt.before_trial()
    rt.after_trial(ctx, _result(), _sandbox())
    assert _norm(agy_mod.SCRATCH_CANARY_REL_PATH) not in env.files


# --------------------------------------------------------------------------- #
# 6. log shape + guard rails
# --------------------------------------------------------------------------- #


def test_outcome_as_log_dict_shape():
    env = _FakeHomeEnv()
    rt = AgyTrialRuntime(_adapter(), env)
    ctx = rt.before_trial()
    _write_brain(env, "c", _planner(_shell_call("touch x", "/work/sbx_T01")))
    log = rt.after_trial(ctx, _result(), _sandbox()).as_log_dict()
    assert set(log) == {
        "brain_transcript_located",
        "brain_conversation_candidates",
        "brain_parse_status",
        "brain_valid_event_count",
        "brain_malformed_line_count",
        "brain_shell_call_count",
        "brain_outcome_event_count",
        "cwd_compliance",
        "cwd_tags",
        "scratch_canary_escape",
    }
    assert log["brain_transcript_located"] is True
    assert log["brain_parse_status"] == "present"
    assert log["brain_valid_event_count"] == 2
    assert log["brain_shell_call_count"] == 1
    assert log["brain_outcome_event_count"] == 1
    assert log["cwd_compliance"]["commands"] == 1


def test_outcome_log_includes_accepted_d011_evidence_when_supplied():
    from harness.outcomes import construct_agy_outcome_evidence

    env = _FakeHomeEnv()
    rt = AgyTrialRuntime(_adapter(), env)
    ctx = rt.before_trial()
    _write_brain(env, "c", _planner(_shell_call("touch x", "/work/sbx_T01")))
    outcome = rt.after_trial(ctx, _result(), _sandbox())
    evidence = construct_agy_outcome_evidence(
        checks_passed=True,
        completed=True,
        timed_out=False,
        brain_status="present",
        cwd_tags=["cwd_in_sandbox"],
    )
    log = outcome.as_log_dict(evidence)
    assert log["v2_outcome_evidence"] == {
        "rule_version": "v2-d011-1.0.0",
        "brain_status": "present",
        "transcript_analysis_eligible": True,
        "cwd_status": "all_in_sandbox",
        "shell_command_count": 1,
        "sandbox_command_count": 1,
        "h1_success": True,
        "h1_decision_reason": "checks_passed",
    }


def test_runtime_refuses_non_home_filesystem_environment():
    """A plain environment without the seam cannot run agy; the runtime says so
    at construction rather than silently degrading the science."""
    class _PlainEnv:
        env_id = "plain"

    with pytest.raises(EnvironmentError):
        AgyTrialRuntime(_adapter(), _PlainEnv())


if __name__ == "__main__":
    import pytest as _pytest

    raise SystemExit(_pytest.main([__file__, "-q"]))
