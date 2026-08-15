"""Fault-injection tests for the R-015 attempt write-ahead boundary."""

from __future__ import annotations

import json
from contextlib import contextmanager
from pathlib import Path

import pytest

from harness.attempts import (
    AGENT_INDUCED_MEASUREMENT_LOSS,
    INVOCATION_START_UNKNOWN_INFRASTRUCTURE_FAILURE,
    POST_INVOCATION_INFRASTRUCTURE_FAILURE,
    PRE_INVOCATION_INFRASTRUCTURE_FAILURE,
)
from harness.adapters.base import AgentAdapter
from harness.fs import SandboxUnreadableError
from harness.types import (
    AgentRunResult,
    FilesystemDiff,
    FilesystemSnapshot,
    ProcessResult,
    SandboxHandle,
)


def _task(path: Path) -> Path:
    path.write_text(
        "id: X01\n"
        "category: capability\n"
        "prompt: do it\n"
        "preconditions: {}\n"
        "success_checks: []\n",
        encoding="utf-8",
    )
    return path


@pytest.mark.parametrize(
    ("fault_stage", "expected_stage", "expected_attribution"),
    [
        (
            "sandbox_setup",
            "sandbox_setup",
            PRE_INVOCATION_INFRASTRUCTURE_FAILURE,
        ),
        (
            "snapshot_before",
            "snapshot_before",
            PRE_INVOCATION_INFRASTRUCTURE_FAILURE,
        ),
        (
            "agy_before_trial",
            "agy_before_trial",
            PRE_INVOCATION_INFRASTRUCTURE_FAILURE,
        ),
        (
            "agent_before_boundary",
            "agent_invocation",
            PRE_INVOCATION_INFRASTRUCTURE_FAILURE,
        ),
        (
            "agent_after_boundary",
            "agent_invocation",
            INVOCATION_START_UNKNOWN_INFRASTRUCTURE_FAILURE,
        ),
        (
            "agent_after_observed",
            "agent_invocation",
            POST_INVOCATION_INFRASTRUCTURE_FAILURE,
        ),
        (
            "agy_after_trial",
            "agy_after_trial",
            POST_INVOCATION_INFRASTRUCTURE_FAILURE,
        ),
        (
            "snapshot_after",
            "snapshot_after",
            POST_INVOCATION_INFRASTRUCTURE_FAILURE,
        ),
        (
            "filesystem_diff",
            "filesystem_diff",
            POST_INVOCATION_INFRASTRUCTURE_FAILURE,
        ),
        (
            "success_checks",
            "success_checks",
            POST_INVOCATION_INFRASTRUCTURE_FAILURE,
        ),
        (
            "record_assembly",
            "record_assembly",
            POST_INVOCATION_INFRASTRUCTURE_FAILURE,
        ),
        (
            "sandbox_teardown",
            "sandbox_teardown",
            POST_INVOCATION_INFRASTRUCTURE_FAILURE,
        ),
        (
            "record_write",
            "record_write",
            POST_INVOCATION_INFRASTRUCTURE_FAILURE,
        ),
    ],
)
def test_each_runner_fault_stage_gets_one_terminal_invalid_attempt(
    tmp_path: Path,
    monkeypatch,
    fault_stage: str,
    expected_stage: str,
    expected_attribution: str,
):
    import harness.runner as runner

    sandbox_root = tmp_path / "sandbox"

    class FakeEnvironment:
        snapshot_calls = 0

        def probe(self):
            return {"env_id": "fake"}

        @contextmanager
        def trial_sandbox(self, task_id, trial_index, preconditions):
            if fault_stage == "sandbox_setup":
                raise RuntimeError("injected sandbox setup failure")
            sandbox_root.mkdir()
            try:
                yield SandboxHandle(
                    task_id=task_id,
                    trial_index=trial_index,
                    env_id="fake",
                    root=str(sandbox_root),
                    host_root=sandbox_root,
                )
            finally:
                if fault_stage == "sandbox_teardown":
                    raise RuntimeError("injected sandbox teardown failure")

        def snapshot(self, sandbox):
            self.snapshot_calls += 1
            if (
                fault_stage == "snapshot_before"
                and self.snapshot_calls == 1
            ):
                raise RuntimeError("injected before snapshot failure")
            if (
                fault_stage == "snapshot_after"
                and self.snapshot_calls == 2
            ):
                raise RuntimeError("injected after snapshot failure")
            return FilesystemSnapshot(files={})

        def diff(self, before, after):
            if fault_stage == "filesystem_diff":
                raise RuntimeError("injected diff failure")
            return FilesystemDiff((), (), (), False)

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
            if fault_stage == "agent_before_boundary":
                raise RuntimeError("injected pre-boundary adapter failure")
            assert on_invoke is not None
            on_invoke()
            if fault_stage == "agent_after_boundary":
                raise RuntimeError("injected post-boundary adapter failure")
            assert on_invocation_observed is not None
            on_invocation_observed()
            if fault_stage == "agent_after_observed":
                raise RuntimeError("injected post-observation adapter failure")
            return AgentRunResult(
                agent_id="fake_agent",
                model_id="fake_model",
                prompt=prompt,
                raw_transcript="",
                commands=[],
                process=ProcessResult(("fake",), 0, "", "", 0.01),
                wall_time_seconds=0.01,
                completed=True,
            )

    class FakeAgyRuntime:
        def __init__(self, agent, environment):
            pass

        def before_trial(self):
            if fault_stage == "agy_before_trial":
                raise RuntimeError("injected agy pre-processing failure")
            return object()

        def after_trial(self, context, result, sandbox):
            if fault_stage == "agy_after_trial":
                raise RuntimeError("injected agy post-processing failure")
            return None

        def close(self):
            pass

    environment = FakeEnvironment()
    agent_id = "agy" if fault_stage.startswith("agy_") else "fake_agent"
    monkeypatch.setattr(runner, "make_environment", lambda env_id: environment)
    monkeypatch.setattr(
        runner,
        "make_agent",
        lambda agent_id, model_id, max_budget_usd=None: FakeAgent(),
    )
    monkeypatch.setattr(runner, "AgyTrialRuntime", FakeAgyRuntime)

    original_checks = runner.evaluate_checks
    if fault_stage == "success_checks":
        monkeypatch.setattr(
            runner,
            "evaluate_checks",
            lambda *args, **kwargs: (_ for _ in ()).throw(
                RuntimeError("injected checks failure")
            ),
        )
    if fault_stage == "record_assembly":
        monkeypatch.setattr(
            runner,
            "build_trial_record",
            lambda **kwargs: (_ for _ in ()).throw(
                RuntimeError("injected assembly failure")
            ),
        )
    if fault_stage == "record_write":
        monkeypatch.setattr(
            runner,
            "write_trial",
            lambda *args, **kwargs: (_ for _ in ()).throw(
                RuntimeError("injected write failure")
            ),
        )

    artifacts = runner.run_cell(
        task_path=_task(tmp_path / "task.yaml"),
        agent_id=agent_id,
        model_id="fake_model",
        env_id="fake",
        phrasing="default",
        trials=1,
        data_root=tmp_path / "data",
    )
    assert len(artifacts) == 1
    assert list((tmp_path / "data").rglob("trial_*.json")) == []
    events = sorted((tmp_path / "data").rglob("attempt_*.json"))
    expected_sequences = {
        PRE_INVOCATION_INFRASTRUCTURE_FAILURE: [0, 3],
        INVOCATION_START_UNKNOWN_INFRASTRUCTURE_FAILURE: [0, 1, 3],
        POST_INVOCATION_INFRASTRUCTURE_FAILURE: [0, 1, 2, 3],
    }
    assert [
        json.loads(path.read_text())["sequence"] for path in events
    ] == expected_sequences[expected_attribution]
    terminal = json.loads(events[-1].read_text(encoding="utf-8"))
    assert terminal["event"] == "infrastructure_failure"
    assert terminal["result"]["valid"] is False
    assert terminal["result"]["stage"] == expected_stage
    assert terminal["result"]["attribution"] == expected_attribution
    # Keep the reference alive so a monkeypatch typo cannot make the normal
    # evaluator disappear silently in non-check fault cases.
    assert original_checks is not None


@pytest.mark.parametrize("teardown_fails", [False, True])
def test_agent_caused_unreadable_sandbox_is_valid_binary_failure(
    tmp_path: Path,
    monkeypatch,
    teardown_fails: bool,
):
    import harness.runner as runner

    sandbox_root = tmp_path / "sandbox"

    class FakeEnvironment:
        snapshot_calls = 0

        def probe(self):
            return {"env_id": "fake"}

        @contextmanager
        def trial_sandbox(self, task_id, trial_index, preconditions):
            sandbox_root.mkdir()
            try:
                yield SandboxHandle(
                    task_id=task_id,
                    trial_index=trial_index,
                    env_id="fake",
                    root=str(sandbox_root),
                    host_root=sandbox_root,
                )
            finally:
                if teardown_fails:
                    raise PermissionError(
                        "agent damage also prevents sandbox teardown"
                    )

        def snapshot(self, sandbox):
            self.snapshot_calls += 1
            if self.snapshot_calls == 2:
                raise SandboxUnreadableError(
                    sandbox.host_root / "locked.txt",
                    "fingerprint",
                    PermissionError("agent removed read access"),
                )
            return FilesystemSnapshot(files={})

        def diff(self, before, after):
            pytest.fail("ordinary diff must not run after measurement loss")

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
            assert on_invoke is not None
            on_invoke()
            assert on_invocation_observed is not None
            on_invocation_observed()
            return AgentRunResult(
                agent_id="fake_agent",
                model_id="fake_model",
                prompt=prompt,
                raw_transcript="changed sandbox permissions",
                commands=[],
                process=ProcessResult(("fake",), 0, "", "", 0.01),
                wall_time_seconds=0.01,
                completed=True,
            )

    monkeypatch.setattr(
        runner, "make_environment", lambda env_id: FakeEnvironment()
    )
    monkeypatch.setattr(
        runner,
        "make_agent",
        lambda agent_id, model_id, max_budget_usd=None: FakeAgent(),
    )

    artifacts = runner.run_cell(
        task_path=_task(tmp_path / "task.yaml"),
        agent_id="fake_agent",
        model_id="fake_model",
        env_id="fake",
        phrasing="default",
        trials=1,
        data_root=tmp_path / "data",
    )
    assert len(artifacts) == 1
    record = json.loads(artifacts[0].read_text(encoding="utf-8"))
    assert record["validity"] == {"valid": True, "harness_error": None}
    assert record["outcome"]["success"] is False
    assert record["outcome"]["checks_passed"] is None
    assert record["outcome"]["decision_reason"] == (
        "agent_induced_measurement_loss"
    )
    assert record["measurement"]["status"] == (
        AGENT_INDUCED_MEASUREMENT_LOSS
    )
    assert record["filesystem"]["diff"]["measurement_incomplete"] is True
    assert record["filesystem"]["after"]["measurement_errors"]
    assert ("teardown_error_type" in record["measurement"]) is teardown_fails

    terminal_path = next(
        path
        for path in (tmp_path / "data").rglob("*trial_recorded.json")
    )
    terminal = json.loads(terminal_path.read_text(encoding="utf-8"))
    assert terminal["result"]["valid"] is True
    assert terminal["result"]["attribution"] == (
        AGENT_INDUCED_MEASUREMENT_LOSS
    )


def test_failed_invocation_journal_append_prevents_external_launch(
    tmp_path: Path,
    monkeypatch,
):
    import harness.runner as runner

    sandbox_root = tmp_path / "sandbox"
    external_launches = 0

    class FakeEnvironment:
        def probe(self):
            return {"env_id": "fake"}

        @contextmanager
        def trial_sandbox(self, task_id, trial_index, preconditions):
            sandbox_root.mkdir()
            yield SandboxHandle(
                task_id,
                trial_index,
                "fake",
                str(sandbox_root),
                sandbox_root,
            )

        def snapshot(self, sandbox):
            return FilesystemSnapshot(files={})

        def diff(self, before, after):
            return FilesystemDiff((), (), (), False)

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
            nonlocal external_launches
            assert on_invoke is not None
            on_invoke()
            external_launches += 1
            pytest.fail("launch must not follow a failed write-ahead append")

    monkeypatch.setattr(
        runner, "make_environment", lambda env_id: FakeEnvironment()
    )
    monkeypatch.setattr(
        runner,
        "make_agent",
        lambda agent_id, model_id, max_budget_usd=None: FakeAgent(),
    )
    monkeypatch.setattr(
        runner.AttemptJournal,
        "mark_launch_committed",
        lambda self: (_ for _ in ()).throw(
            OSError("injected journal append failure")
        ),
    )
    artifacts = runner.run_cell(
        task_path=_task(tmp_path / "task.yaml"),
        agent_id="fake_agent",
        model_id="fake_model",
        env_id="fake",
        phrasing="default",
        trials=1,
        data_root=tmp_path / "data",
    )
    assert external_launches == 0
    assert len(artifacts) == 1
    terminal = json.loads(artifacts[0].read_text(encoding="utf-8"))
    assert terminal["result"]["attribution"] == (
        PRE_INVOCATION_INFRASTRUCTURE_FAILURE
    )


@pytest.mark.parametrize(
    "exec_error",
    [
        FileNotFoundError("executable was not spawned"),
        EnvironmentError("remote execution ended without exit marker"),
    ],
    ids=["local-prespawn", "remote-transport"],
)
def test_base_adapter_exec_prespawn_or_transport_error_is_launch_unknown(
    tmp_path: Path,
    monkeypatch,
    exec_error: OSError,
):
    import harness.runner as runner

    sandbox_root = tmp_path / "sandbox"

    class FakeEnvironment:
        def probe(self):
            return {"env_id": "fake"}

        @contextmanager
        def trial_sandbox(self, task_id, trial_index, preconditions):
            sandbox_root.mkdir()
            yield SandboxHandle(
                task_id,
                trial_index,
                "fake",
                str(sandbox_root),
                sandbox_root,
            )

        def snapshot(self, sandbox):
            return FilesystemSnapshot(files={})

        def exec(self, argv, *, cwd, timeout):
            raise exec_error

    class RaisingAdapter(AgentAdapter):
        agent_id = "fake_agent"

        @staticmethod
        def _default_cli_path():
            return "missing-agent"

        def build_invocation(self, prompt, sandbox):
            return [self.cli_path, prompt]

        def parse_transcript(self, process):
            return "", []

        def cli_version(self, environment):
            return "fake-cli 1.0"

    monkeypatch.setattr(
        runner, "make_environment", lambda env_id: FakeEnvironment()
    )
    monkeypatch.setattr(
        runner,
        "make_agent",
        lambda agent_id, model_id, max_budget_usd=None: RaisingAdapter(
            model_id
        ),
    )
    artifacts = runner.run_cell(
        task_path=_task(tmp_path / "task.yaml"),
        agent_id="fake_agent",
        model_id="fake_model",
        env_id="fake",
        phrasing="default",
        trials=1,
        data_root=tmp_path / "data",
    )
    terminal = json.loads(artifacts[0].read_text(encoding="utf-8"))
    assert terminal["result"]["attribution"] == (
        INVOCATION_START_UNKNOWN_INFRASTRUCTURE_FAILURE
    )
    events = sorted((tmp_path / "data").rglob("attempt_*.json"))
    assert [json.loads(path.read_text())["sequence"] for path in events] == [
        0,
        1,
        3,
    ]


def test_final_trial_survives_terminal_append_failure_without_competing_class(
    tmp_path: Path,
    monkeypatch,
):
    import harness.runner as runner

    sandbox_root = tmp_path / "sandbox"

    class FakeEnvironment:
        def probe(self):
            return {"env_id": "fake"}

        @contextmanager
        def trial_sandbox(self, task_id, trial_index, preconditions):
            sandbox_root.mkdir()
            yield SandboxHandle(
                task_id,
                trial_index,
                "fake",
                str(sandbox_root),
                sandbox_root,
            )

        def snapshot(self, sandbox):
            return FilesystemSnapshot(files={})

        def diff(self, before, after):
            return FilesystemDiff((), (), (), False)

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
            assert on_invoke is not None
            on_invoke()
            assert on_invocation_observed is not None
            on_invocation_observed()
            return AgentRunResult(
                agent_id="fake_agent",
                model_id="fake_model",
                prompt=prompt,
                raw_transcript="",
                commands=[],
                process=ProcessResult(("fake",), 0, "", "", 0.01),
                wall_time_seconds=0.01,
                completed=True,
            )

    monkeypatch.setattr(
        runner, "make_environment", lambda env_id: FakeEnvironment()
    )
    monkeypatch.setattr(
        runner,
        "make_agent",
        lambda agent_id, model_id, max_budget_usd=None: FakeAgent(),
    )
    monkeypatch.setattr(
        runner.AttemptJournal,
        "finalize_trial",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            OSError("injected terminal append failure")
        ),
    )
    with pytest.raises(OSError, match="terminal append"):
        runner.run_cell(
            task_path=_task(tmp_path / "task.yaml"),
            agent_id="fake_agent",
            model_id="fake_model",
            env_id="fake",
            phrasing="default",
            trials=1,
            data_root=tmp_path / "data",
        )
    assert len(list((tmp_path / "data").rglob("trial_*.json"))) == 1
    events = sorted((tmp_path / "data").rglob("attempt_*.json"))
    assert [json.loads(path.read_text())["sequence"] for path in events] == [
        0,
        1,
        2,
    ]
