"""Trial-record assembly + immutable JSON writer.

SCHEMA_VERSION is bumped whenever the record shape changes. Once data
collection has begun, a bump is a methodology event and must be noted in
DEVIATIONS.md — analysis code keys on this field to stay reproducible
across a schema change.

Layout on disk:

  data/<env_id>/<agent_id>/<model_id>/<task_id>/<phrasing>/
      trial_<index>__<utc-timestamp>.json

A re-run after a harness error writes a NEW file (new timestamp). The
invalid file is never deleted — transparency about discarded data is the
whole point of pre-registration.
"""

from __future__ import annotations

import dataclasses
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

from ..attempts import ATTEMPT_SCHEMA_VERSION
from ..outcomes import BinaryOutcome, construct_binary_outcome
from ..schedule_identity import ScheduleIdentity
from ..types import AgentRunResult, CheckResult, FilesystemDiff, FilesystemSnapshot

# 1.6.0: accepted D-011 agy outcome evidence (shared H1 plus separate
# transcript/Cwd eligibility) in the additive agy section.
# 1.5.0: validated scheduled-run identity (phase, plan, cell, task hash,
# schema, target N, and coordinate-bound token) on scheduled trials.
# 1.4.0: required attempt-journal binding plus explicit filesystem
# measurement status for R-015 attempt preservation.
# 1.3.0: additive `outcome.checks_passed` and `outcome.decision_reason`
# fields make the timeout/incomplete override independently auditable.
# 1.2.0: additive, optional top-level `schedule` section binding a collected
# trial to its immutable phase/plan/cell identity. Added before data collection.
# 1.1.0: additive, optional top-level `agy` section (per-command Cwd tags,
# compliance, brain-transcript location, scratch-canary escape) present only on
# agy trials. No existing field changed — pre-data additive bump.
SCHEMA_VERSION = "1.7.0"


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")


def _snapshot_for_log(snap: FilesystemSnapshot) -> dict:
    """Compact, reproducible snapshot form.

    mtime is intentionally dropped: it changes every run and would make two
    otherwise-identical trials diff as different. size + content hash are
    what a reviewer needs to verify what the agent produced.
    """
    return {
        "files": {
            path: {"size": fp.size, "sha256": fp.sha256}
            for path, fp in sorted(snap.files.items())
        },
        "dirs": list(snap.dirs),
        "escaped_paths": list(snap.escaped_paths),
        "measurement_errors": list(snap.measurement_errors),
    }


def _json_default(obj: object) -> object:
    if isinstance(obj, Path):
        return str(obj)
    if isinstance(obj, tuple):
        return list(obj)
    raise TypeError(f"not JSON-serialisable: {type(obj).__name__}")


def _validate_agy_section(agy: dict, binary_outcome: BinaryOutcome) -> None:
    expected = {
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
        "v2_outcome_evidence",
    }
    if set(agy) != expected:
        raise ValueError("agy section has unknown or missing fields")
    status = agy["brain_parse_status"]
    if status not in {"present", "missing", "parse_error", "ambiguous"}:
        raise ValueError("agy brain_parse_status is invalid")
    if type(agy["brain_transcript_located"]) is not bool:
        raise TypeError("agy brain_transcript_located must be a bool")
    if agy["brain_transcript_located"] is not (status == "present"):
        raise ValueError("agy transcript location contradicts parse status")
    for field in (
        "brain_conversation_candidates",
        "brain_valid_event_count",
        "brain_malformed_line_count",
        "brain_shell_call_count",
        "brain_outcome_event_count",
    ):
        if isinstance(agy[field], bool) or not isinstance(agy[field], int) or agy[field] < 0:
            raise TypeError(f"agy {field} must be a non-negative integer")
    if status == "present" and agy["brain_valid_event_count"] < 1:
        raise ValueError("present agy transcript requires at least one valid event")
    if status == "present" and agy["brain_malformed_line_count"] != 0:
        raise ValueError("present agy transcript cannot contain malformed events")
    if status == "present" and (
        agy["brain_shell_call_count"] != agy["brain_outcome_event_count"]
    ):
        raise ValueError("present agy transcript requires paired command outcomes")
    if status in {"missing", "ambiguous"} and any(
        agy[field] != 0
        for field in (
            "brain_valid_event_count",
            "brain_malformed_line_count",
            "brain_shell_call_count",
            "brain_outcome_event_count",
        )
    ):
        raise ValueError("unread agy transcript cannot claim parsed events")
    if not isinstance(agy["cwd_tags"], list) or not isinstance(
        agy["cwd_compliance"], dict
    ):
        raise TypeError("agy cwd evidence has the wrong type")

    evidence = agy["v2_outcome_evidence"]
    evidence_fields = {
        "rule_version",
        "brain_status",
        "transcript_analysis_eligible",
        "cwd_status",
        "shell_command_count",
        "sandbox_command_count",
        "h1_success",
        "h1_decision_reason",
    }
    if not isinstance(evidence, dict) or set(evidence) != evidence_fields:
        raise ValueError("agy v2 outcome evidence has unknown or missing fields")
    if evidence["rule_version"] != "v2-d011-1.0.0":
        raise ValueError("agy v2 outcome rule version is invalid")
    if evidence["brain_status"] != status:
        raise ValueError("agy parse status contradicts v2 outcome evidence")
    if evidence["h1_success"] is not binary_outcome.success or (
        evidence["h1_decision_reason"] != binary_outcome.decision_reason
    ):
        raise ValueError("agy nested H1 evidence contradicts top-level outcome")
    eligible = evidence["transcript_analysis_eligible"]
    if type(eligible) is not bool or eligible is not (status == "present"):
        raise ValueError("agy transcript eligibility contradicts parse status")
    if status == "present":
        shell_count = evidence["shell_command_count"]
        sandbox_count = evidence["sandbox_command_count"]
        if (
            isinstance(shell_count, bool)
            or not isinstance(shell_count, int)
            or isinstance(sandbox_count, bool)
            or not isinstance(sandbox_count, int)
            or not 0 <= sandbox_count <= shell_count
        ):
            raise ValueError("agy command counts are invalid")
        if shell_count != len(agy["cwd_tags"]):
            raise ValueError("agy shell-command count contradicts Cwd tags")
        allowed_tags = {"cwd_in_sandbox", "cwd_in_agy_scratch", "cwd_elsewhere"}
        actual_tags: list[str] = []
        for index, item in enumerate(agy["cwd_tags"]):
            if (
                not isinstance(item, dict)
                or set(item) != {"index", "cwd", "tag"}
                or item["index"] != index
                or item["tag"] not in allowed_tags
            ):
                raise ValueError("agy Cwd tag record is invalid")
            actual_tags.append(item["tag"])
        actual_sandbox_count = sum(tag == "cwd_in_sandbox" for tag in actual_tags)
        if sandbox_count != actual_sandbox_count:
            raise ValueError("agy sandbox-command count contradicts Cwd tags")
        if shell_count == 0:
            expected_cwd_status = "no_shell_commands"
        elif actual_sandbox_count == shell_count:
            expected_cwd_status = "all_in_sandbox"
        elif actual_sandbox_count == 0:
            expected_cwd_status = "none_in_sandbox"
        else:
            expected_cwd_status = "mixed"
        if evidence["cwd_status"] != expected_cwd_status:
            raise ValueError("agy Cwd status contradicts Cwd tags")
        compliance = agy["cwd_compliance"]
        expected_compliance = {
            "commands": shell_count,
            "cwd_in_sandbox": actual_sandbox_count,
            "cwd_in_agy_scratch": sum(
                tag == "cwd_in_agy_scratch" for tag in actual_tags
            ),
            "cwd_elsewhere": sum(tag == "cwd_elsewhere" for tag in actual_tags),
            "sandbox_compliance_rate": (
                actual_sandbox_count / shell_count if shell_count else None
            ),
        }
        if compliance != expected_compliance:
            raise ValueError("agy Cwd compliance summary contradicts Cwd tags")
    elif (
        evidence["shell_command_count"] is not None
        or evidence["sandbox_command_count"] is not None
        or agy["cwd_tags"]
    ):
        raise ValueError("unavailable agy transcript must not claim command evidence")


def build_trial_record(
    *,
    task_id: str,
    family_id: str,
    instance_id: str,
    instance_sha256: str,
    task_category: str,
    agent_id: str,
    model_id: str,
    env_id: str,
    phrasing: str,
    trial_index: int,
    prompt: str,
    started_at: str,
    env_probe: dict[str, str],
    cli_version: str,
    agent_result: AgentRunResult,
    snapshot_before: FilesystemSnapshot,
    snapshot_after: FilesystemSnapshot,
    fs_diff: FilesystemDiff,
    binary_outcome: BinaryOutcome,
    check_results: list[CheckResult],
    attempt_binding: dict[str, str],
    measurement_loss: dict[str, str] | None = None,
    agy: dict | None = None,
    schedule_identity: ScheduleIdentity | None = None,
) -> dict:
    """Assemble the full immutable record for one trial.

    `spiral_code` is null by design — it is applied post hoc by the
    classifier (rubric A-F) reading `agent.transcript`, never during the
    run. `valid` is the gate the SAP uses to include/exclude the trial.

    The writer independently reconstructs the expected binary outcome from
    the check vector and process completion state. This prevents any caller
    from persisting a contradictory combination such as
    `success=true`/`decision_reason=timed_out`.

    `agy` is the optional, additive section the agy runtime supplies
    (per-command Cwd tags + compliance, brain-transcript location, scratch-
    canary escape). It is present ONLY on agy trials.

    `schedule_identity` is required by the scheduled child path and is
    independently integrity-checked here before it is serialized. Direct,
    unscheduled diagnostic runs may omit it.
    """
    if set(attempt_binding) != {
        "schema_version",
        "attempt_id",
        "allocated_event_sha256",
    }:
        raise ValueError("attempt binding has unknown or missing fields")
    if attempt_binding["schema_version"] != ATTEMPT_SCHEMA_VERSION:
        raise ValueError("attempt binding schema does not match writer")
    if re.fullmatch(r"[0-9a-f]{32}", attempt_binding["attempt_id"]) is None:
        raise ValueError("attempt_id must be 32 lowercase hexadecimal characters")
    if (
        re.fullmatch(
            r"[0-9a-f]{64}",
            attempt_binding["allocated_event_sha256"],
        )
        is None
    ):
        raise ValueError(
            "allocated_event_sha256 must be 64 lowercase hexadecimal characters"
        )

    for name, value in (
        ("task_id", task_id),
        ("family_id", family_id),
        ("instance_id", instance_id),
    ):
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{name} must be a non-empty string")
    if re.fullmatch(r"[0-9a-f]{64}", instance_sha256) is None:
        raise ValueError(
            "instance_sha256 must be 64 lowercase hexadecimal characters"
        )
    if schedule_identity is not None and (
        schedule_identity.task_id,
        schedule_identity.family_id,
        schedule_identity.instance_id,
        schedule_identity.instance_sha256,
    ) != (task_id, family_id, instance_id, instance_sha256):
        raise ValueError(
            "schedule identity contradicts trial task-instance identity"
        )

    expected_completed = (
        not agent_result.process.timed_out
        and agent_result.process.returncode is not None
    )
    if agent_result.completed != expected_completed:
        raise ValueError(
            "agent completion flag does not match process evidence: "
            f"completed={agent_result.completed!r}, "
            f"timed_out={agent_result.process.timed_out!r}, "
            f"returncode={agent_result.process.returncode!r}"
        )
    if any(type(result.passed) is not bool for result in check_results):
        raise TypeError("every CheckResult.passed must be a bool")
    has_measurement_loss = measurement_loss is not None
    if has_measurement_loss:
        if agent_result.invalid:
            raise ValueError(
                "agent-induced measurement loss cannot also be infrastructure-invalid"
            )
        if check_results:
            raise ValueError(
                "success checks must be unevaluated after measurement loss"
            )
        if not snapshot_after.measurement_errors:
            raise ValueError(
                "measurement-loss record requires snapshot measurement evidence"
            )
        if not fs_diff.measurement_incomplete:
            raise ValueError(
                "measurement-loss record requires an incomplete filesystem diff"
            )
        expected_checks_passed: bool | None = None
    else:
        if snapshot_before.measurement_errors or snapshot_after.measurement_errors:
            raise ValueError(
                "snapshot measurement errors require measurement-loss attribution"
            )
        if fs_diff.measurement_incomplete:
            raise ValueError(
                "incomplete filesystem diff requires measurement-loss attribution"
            )
        expected_checks_passed = all(
            result.passed for result in check_results
        )
    expected_outcome = construct_binary_outcome(
        checks_passed=expected_checks_passed,
        completed=agent_result.completed,
        timed_out=agent_result.process.timed_out,
        agent_induced_measurement_loss=has_measurement_loss,
    )
    if binary_outcome != expected_outcome:
        raise ValueError(
            "binary outcome does not match check/completion evidence: "
            f"received {binary_outcome!r}, expected {expected_outcome!r}"
        )

    if (agent_id == "agy") != (agy is not None):
        raise ValueError("agy trials require an agy section; other agents forbid it")
    if agy is not None:
        _validate_agy_section(agy, binary_outcome)

    record: dict = {
        "schema_version": SCHEMA_VERSION,
        "trial": {
            "task_id": task_id,
            "family_id": family_id,
            "instance_id": instance_id,
            "instance_sha256": instance_sha256,
            "task_category": task_category,
            "agent_id": agent_id,
            "model_id": model_id,
            "env_id": env_id,
            "phrasing": phrasing,
            "trial_index": trial_index,
            "started_at": started_at,
            "finished_at": _utc_now(),
        },
        "attempt": dict(attempt_binding),
        "environment_probe": env_probe,
        "agent_cli_version": cli_version,
        "prompt": prompt,
        "agent": {
            "transcript": agent_result.raw_transcript,
            "commands": [
                dataclasses.asdict(c) for c in agent_result.commands
            ],
            "process": dataclasses.asdict(agent_result.process),
            "wall_time_seconds": agent_result.wall_time_seconds,
            "completed": agent_result.completed,
            "metadata": agent_result.agent_metadata,
        },
        "filesystem": {
            "before": _snapshot_for_log(snapshot_before),
            "after": _snapshot_for_log(snapshot_after),
            "diff": dataclasses.asdict(fs_diff),
        },
        "outcome": {
            "success": binary_outcome.success,
            "checks_passed": binary_outcome.checks_passed,
            "decision_reason": binary_outcome.decision_reason,
            "checks": [dataclasses.asdict(r) for r in check_results],
        },
        "spiral_code": None,
        "validity": {
            "valid": not agent_result.invalid,
            "harness_error": agent_result.harness_error,
        },
        "measurement": (
            {
                "status": "agent_induced_measurement_loss",
                **measurement_loss,
            }
            if measurement_loss is not None
            else {"status": "complete"}
        ),
    }
    if agy is not None:
        record["agy"] = agy
    if schedule_identity is not None:
        schedule_identity.validate_integrity()
        record["schedule"] = schedule_identity.as_dict()
    return record


def write_trial(record: dict, data_root: Path) -> Path:
    """Write one trial record. Refuses to overwrite an existing file.

    The path is timestamped to the second; a collision means two trials were
    written within one second — raising rather than clobbering protects the
    open-data guarantee.
    """
    t = record["trial"]
    out_dir = (
        data_root
        / t["env_id"]
        / t["agent_id"]
        / t["model_id"]
        / t["task_id"]
        / t["phrasing"]
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"trial_{t['trial_index']}__{t['finished_at']}.json"
    encoded = json.dumps(
        record,
        indent=2,
        default=_json_default,
        ensure_ascii=False,
    )
    try:
        with out_path.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
    except FileExistsError as exc:
        raise FileExistsError(
            f"refusing to overwrite existing trial log: {out_path}"
        ) from exc
    return out_path
