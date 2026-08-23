"""Shared data contracts for the benchmark harness.

These types are the interface boundary between EnvironmentAdapter,
AgentAdapter, and the runner. They are intentionally plain dataclasses with
no behavior so that:

  1. They serialize cleanly into the per-trial log (reproducibility).
  2. A second researcher can re-derive every reported number from the raw
     log without rerunning anything.
  3. Adapters and environments never import each other — they only share
     this module.

Field names here ARE the on-disk log schema. Renaming a field is a
methodology change and must be recorded in DEVIATIONS.md once data
collection has begun.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class ProcessResult:
    """Outcome of one launched OS process.

    This is the raw, environment-agnostic result of running *anything* inside
    an environment — the agent CLI itself, a probe command, or a success
    check. `timed_out` is distinct from a nonzero `returncode`: a timeout
    invalidates inference about the agent's intent, a nonzero exit usually
    does not.
    """

    argv: tuple[str, ...]
    returncode: int | None
    stdout: str
    stderr: str
    duration_seconds: float
    timed_out: bool = False


@dataclass(frozen=True)
class CommandRecord:
    """One shell command the agent issued, reconstructed from its transcript.

    Distinct from ProcessResult: this is what the *agent* chose to run, as
    parsed out of the agent CLI's output. `exit_code` is optional because not
    every agent CLI surfaces the exit status of its own tool calls — when it
    does not, we record None rather than guessing, because the spiral rubric
    must be applied to what is actually observable.

    `tool_name` records which shell tool the agent's CLI exposed to execute
    this command (e.g. `bash`, `powershell`, `pwsh`). Required for SAP A1b
    (per-tool stratified secondary analysis, D1 hybrid framing 2026-05-23):
    on Windows the agent has free tool choice across whatever the CLI
    exposes, and the per-shell decomposition is computed from this field.
    None when the parser couldn't determine the tool (e.g. older fixtures,
    untagged events).
    """

    index: int
    command: str
    stdout: str = ""
    stderr: str = ""
    exit_code: int | None = None
    offset_seconds: float | None = None
    tool_name: str | None = None


@dataclass(frozen=True)
class FileFingerprint:
    """Identity of a single file for before/after diffing."""

    size: int
    mtime: float
    sha256: str


@dataclass(frozen=True)
class FilesystemSnapshot:
    """State of the sandbox at one instant.

    `files` maps a sandbox-relative POSIX path to its fingerprint.
    `dirs` is the set of sandbox-relative POSIX directory paths (tracked
    separately because an empty directory has no file to imply it, yet a
    task may assert `directory_exists`).
    `escaped_paths` records any absolute path the environment was able to
    detect as touched OUTSIDE the sandbox root (best-effort sentinel
    checks). An escaped path is a strong signal for rubric codes D/E and is
    reported even when the in-sandbox diff looks clean.
    `measurement_errors` is non-empty only for an explicitly retained,
    agent-attributable loss after the clean baseline snapshot succeeded.
    """

    files: dict[str, FileFingerprint]
    dirs: tuple[str, ...] = ()
    escaped_paths: tuple[str, ...] = ()
    measurement_errors: tuple[str, ...] = ()


@dataclass(frozen=True)
class FilesystemDiff:
    """Difference between two snapshots, all paths sandbox-relative POSIX.

    `measurement_incomplete` prevents empty placeholder tuples from being
    mistaken for evidence that an unreadable post-agent sandbox was unchanged.
    """

    added: tuple[str, ...]
    removed: tuple[str, ...]
    modified: tuple[str, ...]
    escaped_sandbox: bool
    measurement_incomplete: bool = False

    @property
    def changed_any(self) -> bool:
        return bool(self.added or self.removed or self.modified)


@dataclass(frozen=True)
class SandboxHandle:
    """A live, isolated working directory for exactly one trial.

    `root` is the path as the AGENT will see it (already translated for the
    environment — e.g. a `/mnt/c/...` path for WSL, a remote path for GCP).
    `host_root` is the path the harness uses to inspect it locally, which may
    differ for non-local environments; for local environments they are equal.
    """

    task_id: str
    trial_index: int
    env_id: str
    root: str
    host_root: Path


@dataclass(frozen=True)
class CheckResult:
    """Outcome of one success check from a task YAML.

    `detail` is human-readable ("expected file 'build/output.txt' not
    found"); `evidence` carries the raw observed value so a reviewer can
    audit the verdict without rerunning. All checks for a trial are logged,
    not just the failing one — a critic must be able to see the full
    pass/fail vector behind the binary success number.
    """

    check_type: str
    passed: bool
    detail: str
    evidence: str = ""


@dataclass
class AgentRunResult:
    """Everything one agent invocation produced. The unit the runner logs.

    `harness_error` is the critical field for validity: if it is set, the
    trial is INVALID (our infrastructure broke, not the agent) and must be
    excluded from analysis and re-run, per the SAP. A trial where the agent
    failed cleanly has `harness_error is None` and `completed` reflecting
    whether the CLI exited on its own vs. was killed at timeout.
    """

    agent_id: str
    model_id: str
    prompt: str
    raw_transcript: str
    commands: list[CommandRecord]
    process: ProcessResult
    wall_time_seconds: float
    completed: bool
    harness_error: str | None = None
    agent_metadata: dict[str, str] = field(default_factory=dict)

    @property
    def invalid(self) -> bool:
        """True if this trial must be discarded and re-run (not a real datum)."""
        return self.harness_error is not None
