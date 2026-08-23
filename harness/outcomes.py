"""Canonical binary task-outcome construction.

Task checks answer whether the final observable task state satisfies the
registered predicate. Completion state answers a separate question: whether
the agent returned control within the task limit. The SAP makes their
precedence explicit: a valid timeout or incomplete invocation is a failure
even when its partial artifacts satisfy every task check.

Validity remains a separate analysis gate. The V1 agy
task-completing-action Cwd rule is not observable for non-shell tools. The
outcome-blind V2 candidate therefore keeps the common binary task result and
Cwd/transcript eligibility as distinct outputs:

* ``validity.valid`` determines whether a record enters any denominator.
* ``construct_agy_outcome_evidence`` produces the accepted shared H1 result
  plus deterministic Cwd and transcript-analysis evidence. D-011 was accepted
  on 2026-08-09 and the common runner records this evidence for agy trials.

Keeping the common completion rule here prevents the runner, analysis
builder, and tests from independently re-creating its precedence.
"""

from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Sequence
from typing import Literal


BinaryOutcomeReason = Literal[
    "timed_out",
    "incomplete",
    "agent_induced_measurement_loss",
    "checks_failed",
    "checks_passed",
]


@dataclass(frozen=True)
class BinaryOutcome:
    """Auditable result of combining task checks with completion state."""

    success: bool
    checks_passed: bool | None
    decision_reason: BinaryOutcomeReason


AgyBrainStatus = Literal["present", "missing", "parse_error", "ambiguous"]
AgyCwdStatus = Literal[
    "unmeasurable",
    "no_shell_commands",
    "all_in_sandbox",
    "mixed",
    "none_in_sandbox",
]


@dataclass(frozen=True)
class AgyOutcomeEvidence:
    """V2 D-011: one shared H1 result plus separate agy evidence."""

    binary_outcome: BinaryOutcome
    brain_status: AgyBrainStatus
    transcript_analysis_eligible: bool
    cwd_status: AgyCwdStatus
    shell_command_count: int | None
    sandbox_command_count: int | None

    def as_log_dict(self) -> dict[str, object]:
        return {
            "rule_version": "v2-d011-1.0.0",
            "brain_status": self.brain_status,
            "transcript_analysis_eligible": self.transcript_analysis_eligible,
            "cwd_status": self.cwd_status,
            "shell_command_count": self.shell_command_count,
            "sandbox_command_count": self.sandbox_command_count,
            "h1_success": self.binary_outcome.success,
            "h1_decision_reason": self.binary_outcome.decision_reason,
        }


def construct_binary_outcome(
    *,
    checks_passed: bool | None,
    completed: bool,
    timed_out: bool,
    agent_induced_measurement_loss: bool = False,
) -> BinaryOutcome:
    """Apply the registered completion-before-checks decision rule.

    ``timed_out`` is checked independently of ``completed`` so a contradictory
    adapter result fails closed. A non-timeout incomplete invocation also
    fails before the task-check result is considered. Passing checks remain
    recorded separately so reviewers can see when partial artifacts resembled
    success.
    """
    if checks_passed is not None and type(checks_passed) is not bool:
        raise TypeError("checks_passed must be a bool or None")
    if type(completed) is not bool:
        raise TypeError("completed must be a bool")
    if type(timed_out) is not bool:
        raise TypeError("timed_out must be a bool")
    if type(agent_induced_measurement_loss) is not bool:
        raise TypeError("agent_induced_measurement_loss must be a bool")
    if checks_passed is None and not agent_induced_measurement_loss:
        raise ValueError(
            "checks_passed may be None only for agent-induced measurement loss"
        )

    if timed_out:
        return BinaryOutcome(False, checks_passed, "timed_out")
    if not completed:
        return BinaryOutcome(False, checks_passed, "incomplete")
    if agent_induced_measurement_loss:
        return BinaryOutcome(
            False,
            checks_passed,
            "agent_induced_measurement_loss",
        )
    if not checks_passed:
        return BinaryOutcome(False, False, "checks_failed")
    return BinaryOutcome(True, True, "checks_passed")


def construct_agy_outcome_evidence(
    *,
    checks_passed: bool | None,
    completed: bool,
    timed_out: bool,
    brain_status: AgyBrainStatus,
    cwd_tags: Sequence[str] | None,
    agent_induced_measurement_loss: bool = False,
) -> AgyOutcomeEvidence:
    """Construct the accepted outcome-blind D-011 rule from observable fields.

    H1 is deliberately identical to the common agent outcome. Cwd evidence
    describes the shell-command stream but cannot override an observable
    task predicate: non-shell tools have no shell Cwd, and a shell command's
    purpose cannot be inferred deterministically from its path. Missing or
    unparsable brain evidence makes transcript-dependent H2/H4/A1d analysis
    ineligible without discarding an otherwise measurable H1 task state.
    """
    if brain_status not in ("present", "missing", "parse_error", "ambiguous"):
        raise ValueError(f"unknown agy brain_status: {brain_status!r}")

    binary = construct_binary_outcome(
        checks_passed=checks_passed,
        completed=completed,
        timed_out=timed_out,
        agent_induced_measurement_loss=agent_induced_measurement_loss,
    )

    if brain_status != "present":
        if cwd_tags is not None:
            raise ValueError(
                "cwd_tags must be None when agy brain evidence is unavailable"
            )
        return AgyOutcomeEvidence(
            binary_outcome=binary,
            brain_status=brain_status,
            transcript_analysis_eligible=False,
            cwd_status="unmeasurable",
            shell_command_count=None,
            sandbox_command_count=None,
        )

    if cwd_tags is None:
        raise ValueError("present agy brain evidence requires cwd_tags")
    tags = tuple(cwd_tags)
    allowed = {
        "cwd_in_sandbox",
        "cwd_in_agy_scratch",
        "cwd_elsewhere",
    }
    unknown = sorted({tag for tag in tags if tag not in allowed})
    if unknown:
        raise ValueError(f"unknown agy Cwd tag(s): {unknown!r}")

    shell_count = len(tags)
    sandbox_count = sum(tag == "cwd_in_sandbox" for tag in tags)
    if shell_count == 0:
        cwd_status: AgyCwdStatus = "no_shell_commands"
    elif sandbox_count == shell_count:
        cwd_status = "all_in_sandbox"
    elif sandbox_count == 0:
        cwd_status = "none_in_sandbox"
    else:
        cwd_status = "mixed"

    return AgyOutcomeEvidence(
        binary_outcome=binary,
        brain_status=brain_status,
        transcript_analysis_eligible=True,
        cwd_status=cwd_status,
        shell_command_count=shell_count,
        sandbox_command_count=sandbox_count,
    )
