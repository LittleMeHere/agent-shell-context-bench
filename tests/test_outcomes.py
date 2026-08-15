"""Tests for the registered timeout/incomplete binary-outcome rule.

These tests are deliberately separate from task-check tests. A task can leave
perfect-looking artifacts and still be a registered failure when the agent
does not return control within the task limit.
"""

from __future__ import annotations

import json
from contextlib import contextmanager
from pathlib import Path

import pytest
import yaml

from harness.attempts import ATTEMPT_SCHEMA_VERSION
from harness.fs import diff_snapshots, local_snapshot
from harness.logging.writer import _validate_agy_section, build_trial_record
from harness.outcomes import BinaryOutcome, construct_binary_outcome
from harness.types import (
    AgentRunResult,
    CheckResult,
    FilesystemDiff,
    FilesystemSnapshot,
    ProcessResult,
    SandboxHandle,
)

_ATTEMPT_BINDING = {
    "schema_version": ATTEMPT_SCHEMA_VERSION,
    "attempt_id": "a" * 32,
    "allocated_event_sha256": "b" * 64,
}


@pytest.mark.parametrize(
    (
        "checks_passed",
        "completed",
        "timed_out",
        "expected_success",
        "expected_reason",
    ),
    [
        (True, True, False, True, "checks_passed"),
        (False, True, False, False, "checks_failed"),
        (True, False, True, False, "timed_out"),
        (False, False, True, False, "timed_out"),
        (True, False, False, False, "incomplete"),
        (False, False, False, False, "incomplete"),
        # Contradictory adapter state fails closed on the raw timeout flag.
        (True, True, True, False, "timed_out"),
        (False, True, True, False, "timed_out"),
    ],
)
def test_construct_binary_outcome_precedence(
    checks_passed: bool,
    completed: bool,
    timed_out: bool,
    expected_success: bool,
    expected_reason: str,
):
    outcome = construct_binary_outcome(
        checks_passed=checks_passed,
        completed=completed,
        timed_out=timed_out,
    )
    assert outcome.success is expected_success
    assert outcome.checks_passed is checks_passed
    assert outcome.decision_reason == expected_reason


@pytest.mark.parametrize("field", ["checks_passed", "completed", "timed_out"])
def test_construct_binary_outcome_rejects_non_boolean_inputs(field: str):
    kwargs = {
        "checks_passed": True,
        "completed": True,
        "timed_out": False,
    }
    kwargs[field] = 1
    with pytest.raises(TypeError, match=field):
        construct_binary_outcome(**kwargs)


def test_all_registered_tasks_use_the_common_timeout_policy():
    tasks_root = Path(__file__).resolve().parents[1] / "tasks"
    task_paths = sorted(tasks_root.rglob("*.yaml"))
    assert len(task_paths) == 50
    assert len({
        yaml.safe_load(path.read_text(encoding="utf-8"))["id"]
        for path in task_paths
    }) == 50
    for path in task_paths:
        task = yaml.safe_load(path.read_text(encoding="utf-8"))
        predicate = task["binary_success_predicate"]
        h1_predicate = predicate.get("h1_binary_checks", predicate)
        assert h1_predicate["timeout_policy"] == (
            "timeout_or_incomplete_is_failure"
        ), path


@pytest.mark.parametrize(
    ("completed", "timed_out", "expected_success", "expected_reason"),
    [
        (True, False, True, "checks_passed"),
        (False, True, False, "timed_out"),
        (False, False, False, "incomplete"),
    ],
)
def test_run_cell_records_completion_override_even_when_checks_pass(
    tmp_path: Path,
    monkeypatch,
    completed: bool,
    timed_out: bool,
    expected_success: bool,
    expected_reason: str,
):
    import harness.runner as runner

    task_path = tmp_path / "task.yaml"
    task_path.write_text(
        "id: X01\n"
        "category: capability\n"
        "prompt: do it\n"
        "preconditions: {}\n"
        "success_checks:\n"
        "  - type: file_exists\n"
        "    path: result.txt\n",
        encoding="utf-8",
    )
    sandbox_root = tmp_path / "sandbox"

    class FakeEnvironment:
        env_id = "fake"

        def probe(self):
            return {"env_id": self.env_id}

        @contextmanager
        def trial_sandbox(self, task_id, trial_index, preconditions):
            sandbox_root.mkdir()
            yield SandboxHandle(
                task_id=task_id,
                trial_index=trial_index,
                env_id=self.env_id,
                root=str(sandbox_root),
                host_root=sandbox_root,
            )

        def snapshot(self, sandbox):
            return local_snapshot(sandbox.host_root)

        def diff(self, before, after):
            return diff_snapshots(before, after)

    class FakeAgent:
        def cli_version(self, environment):
            return "fake-cli 1.0"

        def run(
            self,
            prompt,
            sandbox,
            environment,
            timeout,
            on_invoke=None,
            on_invocation_observed=None,
        ):
            if on_invoke is not None:
                on_invoke()
            if on_invocation_observed is not None:
                on_invocation_observed()
            (sandbox.host_root / "result.txt").write_text(
                "success-like partial artifact\n",
                encoding="utf-8",
            )
            return AgentRunResult(
                agent_id="fake_agent",
                model_id="fake_model",
                prompt=prompt,
                raw_transcript="partial work resembles success",
                commands=[],
                process=ProcessResult(
                    argv=("fake",),
                    returncode=0 if completed else None,
                    stdout="",
                    stderr="",
                    duration_seconds=1.0,
                    timed_out=timed_out,
                ),
                wall_time_seconds=1.0,
                completed=completed,
            )

    records: list[dict] = []
    monkeypatch.setattr(runner, "make_environment", lambda env_id: FakeEnvironment())
    monkeypatch.setattr(
        runner,
        "make_agent",
        lambda agent_id, model_id, max_budget_usd=None: FakeAgent(),
    )

    def capture_record(record, data_root):
        records.append(record)
        path = tmp_path / "captured.json"
        path.write_text(json.dumps(record), encoding="utf-8")
        return path

    monkeypatch.setattr(runner, "write_trial", capture_record)
    runner.run_cell(
        task_path=task_path,
        agent_id="fake_agent",
        model_id="fake_model",
        env_id="fake",
        phrasing="default",
        trials=1,
        data_root=tmp_path,
    )

    assert len(records) == 1
    assert records[0]["outcome"] == {
        "success": expected_success,
        "checks_passed": True,
        "decision_reason": expected_reason,
        "checks": [
            {
                "check_type": "file_exists",
                "passed": True,
                "detail": "file 'result.txt' present",
                "evidence": "",
            }
        ],
    }


def test_writer_rejects_forged_outcome_that_conflicts_with_timeout_evidence():
    result = AgentRunResult(
        agent_id="fake_agent",
        model_id="fake_model",
        prompt="do it",
        raw_transcript="partial",
        commands=[],
        process=ProcessResult(
            argv=("fake",),
            returncode=None,
            stdout="",
            stderr="",
            duration_seconds=1.0,
            timed_out=True,
        ),
        wall_time_seconds=1.0,
        completed=False,
    )
    empty = FilesystemSnapshot(files={})
    checks = [CheckResult("file_exists", True, "present")]

    with pytest.raises(ValueError, match="does not match"):
        build_trial_record(
            task_id="X01",
            family_id="X01",
            instance_id="fixed",
            instance_sha256="0" * 64,
            task_category="capability",
            agent_id="fake_agent",
            model_id="fake_model",
            env_id="fake",
            phrasing="default",
            trial_index=0,
            prompt="do it",
            started_at="2026-07-28T00-00-00Z",
            env_probe={"env_id": "fake"},
            cli_version="fake-cli 1.0",
            agent_result=result,
            snapshot_before=empty,
            snapshot_after=empty,
            fs_diff=FilesystemDiff((), (), (), False),
            binary_outcome=BinaryOutcome(True, True, "checks_passed"),
            check_results=checks,
            attempt_binding=_ATTEMPT_BINDING,
        )


def test_writer_rejects_completion_flag_that_conflicts_with_process_evidence():
    result = AgentRunResult(
        agent_id="fake_agent",
        model_id="fake_model",
        prompt="do it",
        raw_transcript="done",
        commands=[],
        process=ProcessResult(
            argv=("fake",),
            returncode=None,
            stdout="",
            stderr="",
            duration_seconds=1.0,
            timed_out=False,
        ),
        wall_time_seconds=1.0,
        completed=True,
    )
    empty = FilesystemSnapshot(files={})

    with pytest.raises(ValueError, match="completion flag"):
        build_trial_record(
            task_id="X01",
            family_id="X01",
            instance_id="fixed",
            instance_sha256="0" * 64,
            task_category="capability",
            agent_id="fake_agent",
            model_id="fake_model",
            env_id="fake",
            phrasing="default",
            trial_index=0,
            prompt="do it",
            started_at="2026-07-28T00-00-00Z",
            env_probe={"env_id": "fake"},
            cli_version="fake-cli 1.0",
            agent_result=result,
            snapshot_before=empty,
            snapshot_after=empty,
            fs_diff=FilesystemDiff((), (), (), False),
            binary_outcome=BinaryOutcome(True, True, "checks_passed"),
            check_results=[],
            attempt_binding=_ATTEMPT_BINDING,
        )


def test_writer_rejects_agy_nested_h1_that_conflicts_with_top_level():
    result = AgentRunResult(
        agent_id="agy",
        model_id="fake_model",
        prompt="do it",
        raw_transcript="done",
        commands=[],
        process=ProcessResult(
            argv=("agy",),
            returncode=0,
            stdout="",
            stderr="",
            duration_seconds=1.0,
            timed_out=False,
        ),
        wall_time_seconds=1.0,
        completed=True,
    )
    empty = FilesystemSnapshot(files={})
    agy = {
        "brain_transcript_located": True,
        "brain_conversation_candidates": 1,
        "brain_parse_status": "present",
        "brain_valid_event_count": 1,
        "brain_malformed_line_count": 0,
        "brain_shell_call_count": 0,
        "brain_outcome_event_count": 0,
        "cwd_compliance": {
            "commands": 0,
            "cwd_in_sandbox": 0,
            "cwd_in_agy_scratch": 0,
            "cwd_elsewhere": 0,
            "sandbox_compliance_rate": None,
        },
        "cwd_tags": [],
        "scratch_canary_escape": None,
        "v2_outcome_evidence": {
            "rule_version": "v2-d011-1.0.0",
            "brain_status": "present",
            "transcript_analysis_eligible": True,
            "cwd_status": "no_shell_commands",
            "shell_command_count": 0,
            "sandbox_command_count": 0,
            "h1_success": False,
            "h1_decision_reason": "checks_failed",
        },
    }

    with pytest.raises(ValueError, match="contradicts top-level"):
        build_trial_record(
            task_id="X01",
            family_id="X01",
            instance_id="fixed",
            instance_sha256="0" * 64,
            task_category="capability",
            agent_id="agy",
            model_id="fake_model",
            env_id="fake",
            phrasing="default",
            trial_index=0,
            prompt="do it",
            started_at="2026-07-28T00-00-00Z",
            env_probe={"env_id": "fake"},
            cli_version="agy 1.0",
            agent_result=result,
            snapshot_before=empty,
            snapshot_after=empty,
            fs_diff=FilesystemDiff((), (), (), False),
            binary_outcome=BinaryOutcome(True, True, "checks_passed"),
            check_results=[],
            attempt_binding=_ATTEMPT_BINDING,
            agy=agy,
        )


def test_writer_accepts_partial_counts_for_parse_error_evidence():
    binary = BinaryOutcome(True, True, "checks_passed")
    agy = {
        "brain_transcript_located": False,
        "brain_conversation_candidates": 1,
        "brain_parse_status": "parse_error",
        "brain_valid_event_count": 7,
        "brain_malformed_line_count": 1,
        "brain_shell_call_count": 1,
        "brain_outcome_event_count": 0,
        "cwd_compliance": {
            "commands": 0,
            "cwd_in_sandbox": 0,
            "cwd_in_agy_scratch": 0,
            "cwd_elsewhere": 0,
            "sandbox_compliance_rate": None,
        },
        "cwd_tags": [],
        "scratch_canary_escape": None,
        "v2_outcome_evidence": {
            "rule_version": "v2-d011-1.0.0",
            "brain_status": "parse_error",
            "transcript_analysis_eligible": False,
            "cwd_status": "unavailable",
            "shell_command_count": None,
            "sandbox_command_count": None,
            "h1_success": True,
            "h1_decision_reason": "checks_passed",
        },
    }
    _validate_agy_section(agy, binary)


def test_measurement_loss_is_a_valid_failure_with_unevaluated_checks():
    outcome = construct_binary_outcome(
        checks_passed=None,
        completed=True,
        timed_out=False,
        agent_induced_measurement_loss=True,
    )
    assert outcome == BinaryOutcome(
        False,
        None,
        "agent_induced_measurement_loss",
    )
