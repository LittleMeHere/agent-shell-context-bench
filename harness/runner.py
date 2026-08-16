"""Trial orchestration: one (task, agent, model, env, phrasing) cell.

This is the only place the moving parts meet. Order is load-bearing:

  probe + cli_version   ONCE per cell (cheap, identical across trials,
                        recorded in every trial log for reproducibility)
  per trial:
    fresh sandbox  ->  snapshot BEFORE  ->  agent runs  ->  snapshot AFTER
    ->  diff  ->  success checks  ->  immutable log  ->  teardown

The BEFORE snapshot exists so a destructive over-correction (rubric D/E) is
visible as a diff against the task's clean starting state, not guessed.
Every allocated trial is journaled even if later measurement or record
assembly fails — see attempts.py and logging/.
"""

from __future__ import annotations

import dataclasses
import hashlib
import math
import re
import time
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path

import yaml

from .agy_runtime import AgyTrialRuntime
from .attempts import (
    AGENT_INDUCED_MEASUREMENT_LOSS,
    COMPLETE,
    POST_INVOCATION_INFRASTRUCTURE_FAILURE,
    AttemptJournal,
)
from .checks import evaluate_checks, requires_agent_trace
from .fs import SandboxUnreadableError
from .fixture_setup import prepare_fixture
from .logging import build_trial_record, write_trial
from .logging.writer import SCHEMA_VERSION as TRIAL_SCHEMA_VERSION
from .outcomes import construct_agy_outcome_evidence, construct_binary_outcome
from .registry import make_agent, make_environment
from .schedule_identity import ScheduleIdentity
from .types import FilesystemDiff, FilesystemSnapshot


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")


def _agy_trace_unavailable_is_outcome_determinative(
    *,
    brain_status: str,
    trace_required: bool,
    completed: bool,
    timed_out: bool,
    agent_induced_measurement_loss: bool,
) -> bool:
    """Whether missing agy trace prevents an otherwise undecided H1 result.

    Timeout, incompletion, and agent-induced filesystem measurement loss are
    already deterministic failures under the common outcome precedence. Trace
    absence must not turn those valid failures into infrastructure attrition.
    """
    return (
        brain_status != "present"
        and trace_required
        and completed
        and not timed_out
        and not agent_induced_measurement_loss
    )


def load_task(path: Path) -> dict:
    """Load + minimally validate a task YAML.

    Validation is intentionally shallow: enough to fail fast on a malformed
    task before burning an API call, not a schema framework. A capability
    task has `prompt`; a seeded-error task has `prompts: {formal, colloquial}`.
    """
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path.name}: task document must be a mapping")
    if "id" not in data or "success_checks" not in data:
        raise ValueError(f"{path.name}: task needs 'id' and 'success_checks'")
    has_single = "prompt" in data
    has_pair = "prompts" in data
    if has_single == has_pair:
        raise ValueError(
            f"{path.name}: task must have exactly one of 'prompt' "
            f"(capability) or 'prompts' (seeded-error)"
        )
    if has_pair and set(data["prompts"]) != {"formal", "colloquial"}:
        raise ValueError(
            f"{path.name}: seeded-error 'prompts' must be exactly "
            f"{{formal, colloquial}}"
        )
    family_id = data.get("family_id")
    instance_id = data.get("instance_id")
    if (family_id is None) != (instance_id is None):
        raise ValueError(
            f"{path.name}: family_id and instance_id must be declared together"
        )
    if family_id is not None:
        if not isinstance(family_id, str) or re.fullmatch(r"C\d{2}", family_id) is None:
            raise ValueError(f"{path.name}: family_id must match Cdd")
        if not isinstance(instance_id, str) or re.fullmatch(r"I\d{2}", instance_id) is None:
            raise ValueError(f"{path.name}: instance_id must match Idd")
        if data["id"] != f"{family_id}-{instance_id}":
            raise ValueError(
                f"{path.name}: id must equal family_id-instance_id"
            )
    return data


def resolve_prompt(task: Mapping[str, object], phrasing: str) -> tuple[str, str]:
    """Return (prompt_text, effective_phrasing).

    Capability tasks have one phrasing, recorded as 'default' regardless of
    the --phrasing flag (the matrix has 1 phrasing level for them).
    Seeded-error tasks require an explicit formal/colloquial choice.
    """
    if "prompt" in task:
        return str(task["prompt"]), "default"
    prompts = task["prompts"]  # type: ignore[index]
    if phrasing not in ("formal", "colloquial"):
        raise ValueError(
            f"seeded-error task {task['id']} requires --phrasing formal|colloquial"
        )
    return str(prompts[phrasing]), phrasing  # type: ignore[index]


def run_cell(
    *,
    task_path: Path,
    agent_id: str,
    model_id: str,
    env_id: str,
    phrasing: str,
    trials: int,
    data_root: Path,
    max_budget_usd: float | None = None,
    trial_index_start: int = 0,
    show_outcomes: bool = True,
    expected_cli_version: str | None = None,
    inter_trial_delay_seconds: float = 0.0,
    schedule_identity: ScheduleIdentity | None = None,
    valid_slot_index: int | None = None,
) -> list[Path]:
    """Run `trials` independent trials for one cell. Returns log paths.

    A single per-attempt infrastructure exception is appended as an invalid
    terminal journal event and the loop continues. A failure of the journal
    itself stops collection before launch or leaves a durable unresolved
    prefix; it is never silently retried.
    """
    if trials < 1:
        raise ValueError("trials must be >= 1")
    if trial_index_start < 0:
        raise ValueError("trial_index_start must be >= 0")
    if (
        not math.isfinite(inter_trial_delay_seconds)
        or inter_trial_delay_seconds < 0
    ):
        raise ValueError("inter_trial_delay_seconds must be finite and >= 0")
    if not show_outcomes and schedule_identity is None:
        raise ValueError(
            "outcome-blind scheduled execution requires a schedule token"
        )
    if valid_slot_index is not None and schedule_identity is None:
        raise ValueError("valid_slot_index requires a schedule token")
    if valid_slot_index is not None and trials != 1:
        raise ValueError("a scheduled valid slot must use exactly one attempt")

    task = load_task(task_path)
    family_id = str(task.get("family_id", task["id"]))
    instance_id = str(task.get("instance_id", "fixed"))
    instance_sha256 = hashlib.sha256(task_path.read_bytes()).hexdigest()
    prompt, eff_phrasing = resolve_prompt(task, phrasing)
    if schedule_identity is not None:
        schedule_identity.validate_run(
            task_id=str(task["id"]),
            agent_id=agent_id,
            model_id=model_id,
            env_id=env_id,
            phrasing=eff_phrasing,
            task_sha256=instance_sha256,
            family_id=family_id,
            instance_id=instance_id,
            instance_sha256=instance_sha256,
            trial_schema_version=TRIAL_SCHEMA_VERSION,
            expected_cli_version=expected_cli_version,
            valid_slot_index=valid_slot_index,
        )
    preconditions = task.get("preconditions", {}) or {}
    timeout = float(task.get("timeout_seconds", 180))

    environment = make_environment(env_id)
    agent = make_agent(agent_id, model_id, max_budget_usd=max_budget_usd)

    # Once per cell — identical across trials, logged in each record.
    env_probe = environment.probe()
    cli_version = agent.cli_version(environment)
    if expected_cli_version is not None:
        version_pattern = (
            rf"(?<![0-9.]){re.escape(expected_cli_version)}(?![0-9.])"
        )
        if re.search(version_pattern, cli_version) is None:
            raise ValueError(
                f"{agent_id} CLI version mismatch: expected "
                f"{expected_cli_version!r}, observed {cli_version!r}; "
                "refusing to collect this cell"
            )

    # agy is the one configuration whose command stream lives out-of-band in
    # the agent's home, not on the launched process. Its runtime drives brain-
    # transcript location and the scratch canary through HomeFilesystem; its
    # model is pinned directly in build_invocation via --model.
    agy_rt = AgyTrialRuntime(agent, environment) if agent_id == "agy" else None

    written: list[Path] = []
    try:
        for offset in range(trials):
            trial_index = trial_index_start + offset
            started_at = _utc_now()
            journal = AttemptJournal.allocate(
                data_root=data_root,
                task_id=task["id"],
                agent_id=agent_id,
                model_id=model_id,
                env_id=env_id,
                phrasing=eff_phrasing,
                trial_index=trial_index,
                schedule_identity=schedule_identity,
            )
            stage = "sandbox_setup"
            trial_written = False
            result = None
            record = None
            measurement_loss = None
            try:
                with environment.trial_sandbox(
                    task["id"], trial_index, preconditions
                ) as sandbox:
                    stage = "fixture_setup"
                    prepare_fixture(environment, sandbox, preconditions)
                    stage = "snapshot_before"
                    before = environment.snapshot(sandbox)
                    stage = "agy_before_trial"
                    agy_ctx = (
                        agy_rt.before_trial() if agy_rt is not None else None
                    )
                    stage = "agent_invocation"
                    result = agent.run(
                        prompt,
                        sandbox,
                        environment,
                        timeout=timeout,
                        on_invoke=journal.mark_launch_committed,
                        on_invocation_observed=(
                            journal.mark_invocation_observed
                        ),
                    )
                    if not journal.invocation_observed:
                        raise RuntimeError(
                            "agent adapter returned without observed external "
                            f"process evidence; harness_error="
                            f"{result.harness_error!r}"
                        )

                    # For agy, recover the out-of-band command stream + Cwd
                    # tags and scratch-canary result. This mutates result so
                    # later checks and the rubric see agy's real commands.
                    stage = "agy_after_trial"
                    agy_outcome = (
                        agy_rt.after_trial(agy_ctx, result, sandbox)
                        if agy_rt is not None
                        else None
                    )
                    stage = "snapshot_after"
                    try:
                        after = environment.snapshot(sandbox)
                    except SandboxUnreadableError as exc:
                        try:
                            affected_relative = exc.path.resolve().relative_to(
                                sandbox.host_root.resolve()
                            )
                        except ValueError as boundary_exc:
                            raise RuntimeError(
                                "snapshot unreadability is outside the trial "
                                "sandbox and cannot be attributed to the agent"
                            ) from boundary_exc
                        if not exc.agent_attributable:
                            raise RuntimeError(
                                "snapshot failure is not a mutation-shaped "
                                "unreadability and remains infrastructure"
                            ) from exc
                        # The same fresh sandbox was readable immediately
                        # before the agent ran. A path-level unreadability
                        # error afterward is therefore attributable agent
                        # damage under the registered validity rule.
                        measurement_loss = {
                            "stage": stage,
                            "error_type": type(exc).__name__,
                            "evidence": exc.evidence,
                            "error": str(exc),
                            "affected_path": (
                                affected_relative.as_posix() or "."
                            ),
                            "attribution_basis": (
                                "readable_baseline_then_post_invocation_"
                                "mutation_shaped_unreadability"
                            ),
                        }
                        escaped_paths = tuple(
                            getattr(
                                environment,
                                "check_canaries",
                                lambda: (),
                            )()
                        )
                        if (
                            agy_outcome is not None
                            and agy_outcome.scratch_escape
                        ):
                            escaped_paths += (agy_outcome.scratch_escape,)
                        after = FilesystemSnapshot(
                            files={},
                            escaped_paths=escaped_paths,
                            measurement_errors=(exc.evidence,),
                        )

                    if measurement_loss is not None:
                        diff = FilesystemDiff(
                            added=(),
                            removed=(),
                            modified=(),
                            escaped_sandbox=bool(
                                before.escaped_paths
                                or after.escaped_paths
                            ),
                            measurement_incomplete=True,
                        )
                        checks_passed = None
                        checks = []
                    else:
                        # Fold an agy scratch-canary escape into the same
                        # escaped_paths channel used by environment canaries.
                        if (
                            agy_outcome is not None
                            and agy_outcome.scratch_escape
                        ):
                            after = dataclasses.replace(
                                after,
                                escaped_paths=after.escaped_paths
                                + (agy_outcome.scratch_escape,),
                            )
                        if agy_outcome is not None and (
                            _agy_trace_unavailable_is_outcome_determinative(
                                brain_status=agy_outcome.brain_status,
                                trace_required=requires_agent_trace(
                                    task["success_checks"]
                                ),
                                completed=result.completed,
                                timed_out=result.process.timed_out,
                                agent_induced_measurement_loss=(
                                    measurement_loss is not None
                                ),
                            )
                        ):
                            trace_error = (
                                "agy brain transcript evidence is "
                                f"{agy_outcome.brain_status}; registered H1 "
                                "checks require the command trace"
                            )
                            result.harness_error = (
                                f"{result.harness_error}; {trace_error}"
                                if result.harness_error
                                else trace_error
                            )
                        stage = "filesystem_diff"
                        diff = environment.diff(before, after)
                        stage = "success_checks"
                        checks_passed, checks = evaluate_checks(
                            after,
                            task["success_checks"],
                            sandbox_host_root=sandbox.host_root,
                            agent_commands=result.commands,
                            trial_started_at=started_at,
                            environment_exec=getattr(environment, "exec", None),
                            environment_cwd=sandbox.root,
                            snapshot_before=before,
                        )
                    agy_outcome_evidence = None
                    if agy_outcome is not None:
                        brain_status = agy_outcome.brain_status
                        cwd_tags = (
                            [str(item.get("tag")) for item in agy_outcome.cwd_tags]
                            if agy_outcome.brain_located
                            else None
                        )
                        agy_outcome_evidence = construct_agy_outcome_evidence(
                            checks_passed=checks_passed,
                            completed=result.completed,
                            timed_out=result.process.timed_out,
                            brain_status=brain_status,
                            cwd_tags=cwd_tags,
                            agent_induced_measurement_loss=(
                                measurement_loss is not None
                            ),
                        )
                        binary_outcome = agy_outcome_evidence.binary_outcome
                    else:
                        binary_outcome = construct_binary_outcome(
                            checks_passed=checks_passed,
                            completed=result.completed,
                            timed_out=result.process.timed_out,
                            agent_induced_measurement_loss=(
                                measurement_loss is not None
                            ),
                        )

                    stage = "record_assembly"
                    record = build_trial_record(
                        task_id=task["id"],
                        family_id=family_id,
                        instance_id=instance_id,
                        instance_sha256=instance_sha256,
                        task_category=str(task.get("category", "")),
                        agent_id=agent_id,
                        model_id=model_id,
                        env_id=env_id,
                        phrasing=eff_phrasing,
                        trial_index=trial_index,
                        prompt=prompt,
                        started_at=started_at,
                        env_probe=env_probe,
                        cli_version=cli_version,
                        agent_result=result,
                        snapshot_before=before,
                        snapshot_after=after,
                        fs_diff=diff,
                        binary_outcome=binary_outcome,
                        check_results=checks,
                        attempt_binding=journal.binding,
                        measurement_loss=measurement_loss,
                        agy=(
                            agy_outcome.as_log_dict(agy_outcome_evidence)
                            if agy_outcome is not None
                            else None
                        ),
                        schedule_identity=schedule_identity,
                    )
                    stage = "sandbox_teardown"

                stage = "record_write"
                path = write_trial(record, data_root)
                trial_written = True
                attribution = (
                    AGENT_INDUCED_MEASUREMENT_LOSS
                    if measurement_loss is not None
                    else (
                        POST_INVOCATION_INFRASTRUCTURE_FAILURE
                        if result.invalid
                        else COMPLETE
                    )
                )
                stage = "attempt_finalize"
                journal.finalize_trial(
                    path,
                    valid=not result.invalid,
                    attribution=attribution,
                )
                written.append(path)
            except Exception as exc:  # noqa: BLE001 - preserve every attempt
                # If the final trial write returned successfully, it is an
                # authoritative reconciliation artifact even if the terminal
                # append failed. Do not append a competing terminal class.
                if trial_written:
                    raise
                # A teardown failure cannot erase an agent-induced measurement
                # loss that was already established by the readable baseline,
                # the durable invocation event, and the post-agent unreadable
                # path evidence. Preserve the valid failure and attach the
                # teardown error instead of reclassifying it as attrition.
                if (
                    stage == "sandbox_teardown"
                    and measurement_loss is not None
                    and record is not None
                    and result is not None
                ):
                    record["measurement"].update(
                        {
                            "teardown_error_type": type(exc).__name__,
                            "teardown_error": str(exc),
                        }
                    )
                    stage = "record_write"
                    path = write_trial(record, data_root)
                    trial_written = True
                    stage = "attempt_finalize"
                    journal.finalize_trial(
                        path,
                        valid=True,
                        attribution=AGENT_INDUCED_MEASUREMENT_LOSS,
                    )
                    written.append(path)
                else:
                    failure_path = journal.finalize_infrastructure_failure(
                        stage=stage,
                        error=exc,
                    )
                    written.append(failure_path)
                    print(
                        f"  trial {offset + 1}/{trials} "
                        f"(index {trial_index}): INVALID "
                        f"[{stage}] -> {failure_path.name}"
                    )
                    if (
                        journal.launch_committed
                        and offset + 1 < trials
                        and inter_trial_delay_seconds
                    ):
                        time.sleep(inter_trial_delay_seconds)
                    continue

            if show_outcomes:
                status = (
                    "INVALID" if result.invalid
                    else "PASS" if binary_outcome.success
                    else "FAIL"
                )
                flags = []
                if diff.escaped_sandbox:
                    flags.append("ESCAPED-SANDBOX")
                if measurement_loss is not None:
                    flags.append("AGENT-MEASUREMENT-LOSS")
                if not result.completed and not result.invalid:
                    flags.append("TIMEOUT/INCOMPLETE")
                suffix = f" [{' '.join(flags)}]" if flags else ""
            else:
                # Collection scheduling is outcome-blind. Validity is the
                # only status needed to replace infrastructure-invalid runs;
                # PASS/FAIL and failure-mode signals stay sealed in the log.
                status = "INVALID" if result.invalid else "RECORDED"
                suffix = ""
            print(
                f"  trial {offset + 1}/{trials} "
                f"(index {trial_index}): {status}{suffix}  "
                f"({result.wall_time_seconds:.1f}s)  -> {path.name}"
            )
            if (
                journal.launch_committed
                and offset + 1 < trials
                and inter_trial_delay_seconds
            ):
                time.sleep(inter_trial_delay_seconds)
    finally:
        if agy_rt is not None:
            agy_rt.close()

    return written
