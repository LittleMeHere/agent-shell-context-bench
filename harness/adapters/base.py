"""Base AgentAdapter.

An adapter knows exactly two things about its agent CLI and nothing about
the OS it runs on:

  build_invocation()  the argv that runs this agent ONCE, headless,
                       autonomous, against a prompt, in a given sandbox.
  parse_transcript()  how to turn that CLI's raw output into a
                       human-readable transcript + a list of CommandRecords.

`run()` is a template method that wires an adapter to an environment: build
the argv, hand it to `environment.exec`, time it, parse it, and package an
AgentRunResult. The split matters because the spiral rubric is applied to
`commands` — if `parse_transcript` is wrong, every H2 number is wrong, so it
is isolated and independently testable against recorded fixtures.

Adapters MUST NOT shell out themselves. Every process goes through the
environment so that "Windows PowerShell vs Linux" is the only thing that
varies between cells.
"""

from __future__ import annotations

import time
import traceback
from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import ClassVar

from ..environments.base import EnvironmentAdapter
from ..types import AgentRunResult, CommandRecord, ProcessResult, SandboxHandle


class AgentAdapter(ABC):
    """Contract every agent adapter must satisfy.

    `agent_id` must match the identifier used in the pre-registered analysis
    matrix. `model_id` is per-instance because the same CLI runs multiple
    pinned models (a model-harness config in RESEARCH_PLAN.md).
    """

    agent_id: ClassVar[str]

    def __init__(self, model_id: str, *, cli_path: str | None = None) -> None:
        self.model_id = model_id
        self.cli_path = cli_path or self._default_cli_path()

    @staticmethod
    @abstractmethod
    def _default_cli_path() -> str:
        """Executable name resolved on PATH when `cli_path` is not given."""

    @abstractmethod
    def build_invocation(
        self, prompt: str, sandbox: SandboxHandle
    ) -> list[str]:
        """argv that runs the agent ONCE: headless, non-interactive, with
        whatever flag makes it act autonomously (no human approval gate) so
        the spiral can actually unfold. The exact flags are reproducibility-
        critical and must be pinned and recorded before pre-registration."""

    @abstractmethod
    def parse_transcript(
        self, process: ProcessResult
    ) -> tuple[str, list[CommandRecord]]:
        """(human-readable transcript, ordered commands the agent issued).

        Must degrade gracefully: if the CLI crashed mid-run and emitted
        partial/garbled output, return the best-effort transcript and
        whatever commands were recoverable rather than raising. A partial
        transcript is still data; a raised exception loses the trial.
        """

    @abstractmethod
    def cli_version(self, environment: EnvironmentAdapter) -> str:
        """Version string of the CLI as installed in `environment`, captured
        per run for the reproducibility log."""

    def pre_model_infrastructure_error(
        self, process: ProcessResult
    ) -> str | None:
        """Return a fail-closed reason when no model invocation occurred.

        A nonzero CLI exit is ordinarily valid agent behavior. Authentication
        failures are different: they occur before the model can act and would
        otherwise turn an infrastructure outage into a false task failure.
        Concrete adapters may recognize only their CLI's exact, evidenced
        envelope. The default deliberately recognizes nothing.
        """
        return None

    def run(
        self,
        prompt: str,
        sandbox: SandboxHandle,
        environment: EnvironmentAdapter,
        *,
        timeout: float,
        on_invoke: Callable[[], None] | None = None,
        on_invocation_observed: Callable[[], None] | None = None,
    ) -> AgentRunResult:
        """Template method. Never overridden by concrete adapters.

        A raised exception here is a HARNESS failure, not an agent failure:
        it is captured into `harness_error`, which marks the trial invalid
        and excluded from analysis per the SAP. An agent that misbehaves but
        runs to completion is NOT an error — that is the signal we want.
        """
        argv = self.build_invocation(prompt, sandbox)
        # This callback is the write-ahead launch-commit boundary. It must
        # complete before attempting the external process. A second callback
        # below records that the environment actually returned process
        # evidence; an exception between them remains launch-unknown.
        if on_invoke is not None:
            on_invoke()
        start = time.monotonic()
        harness_error: str | None = None
        commands: list[CommandRecord] = []
        transcript = ""

        try:
            process = environment.exec(
                argv, cwd=sandbox.root, timeout=timeout
            )
        except Exception:  # noqa: BLE001 - any failure here invalidates trial
            wall = time.monotonic() - start
            return AgentRunResult(
                agent_id=self.agent_id,
                model_id=self.model_id,
                prompt=prompt,
                raw_transcript="",
                commands=[],
                process=ProcessResult(
                    argv=tuple(argv),
                    returncode=None,
                    stdout="",
                    stderr="",
                    duration_seconds=wall,
                ),
                wall_time_seconds=wall,
                completed=False,
                harness_error=traceback.format_exc(),
            )

        if on_invocation_observed is not None:
            on_invocation_observed()
        wall = time.monotonic() - start
        try:
            transcript, commands = self.parse_transcript(process)
        except Exception:  # noqa: BLE001 - parser bug must not destroy raw data
            harness_error = "parse_transcript failed:\n" + traceback.format_exc()
            transcript = process.stdout

        infrastructure_error = self.pre_model_infrastructure_error(process)
        if infrastructure_error:
            harness_error = (
                f"{harness_error}; {infrastructure_error}"
                if harness_error
                else infrastructure_error
            )

        return AgentRunResult(
            agent_id=self.agent_id,
            model_id=self.model_id,
            prompt=prompt,
            raw_transcript=transcript,
            commands=commands,
            process=process,
            wall_time_seconds=wall,
            completed=not process.timed_out and process.returncode is not None,
            harness_error=harness_error,
            agent_metadata={"model_id": self.model_id},
        )
