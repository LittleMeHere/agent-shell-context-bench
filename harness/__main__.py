"""CLI entrypoint:  python -m harness run --task C01 --agent claude_code ...

Thin by design: argument parsing + task-id resolution only. All real work
is in runner.run_cell so the orchestration logic stays unit-testable
without spawning a process.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .runner import run_cell
from .schedule_identity import ScheduleIdentity

_BENCH_ROOT = Path(__file__).resolve().parents[1]
_TASKS_DIR = _BENCH_ROOT / "tasks"


def _resolve_task(task_arg: str) -> Path:
    """Accept a path or a bare task id (C01 / T01). Ids are searched under
    tasks/capability and tasks/trap (legacy folder name retained for the
    seeded-error tasks per 2026-05-30 DECISIONS rename) so the caller need
    not know the layout.
    """
    p = Path(task_arg)
    if p.is_file():
        return p
    matches = sorted(_TASKS_DIR.rglob(f"{task_arg}_*.yaml")) + sorted(
        _TASKS_DIR.rglob(f"{task_arg}.yaml")
    )
    if not matches:
        raise SystemExit(
            f"no task file for {task_arg!r} under {_TASKS_DIR} "
            f"(looked for {task_arg}_*.yaml / {task_arg}.yaml)"
        )
    if len(matches) > 1:
        raise SystemExit(
            f"ambiguous task id {task_arg!r}: {[m.name for m in matches]}"
        )
    return matches[0]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="harness")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="run one (task,agent,model,env) cell")
    run.add_argument("--task", required=True, help="task id (C01) or path")
    run.add_argument("--agent", required=True, help="e.g. claude_code")
    run.add_argument("--model", required=True, help="pinned model id")
    run.add_argument("--env", required=True, help="e.g. windows_powershell")
    run.add_argument(
        "--trials", type=int, default=6, help="trials this cell (default 6)"
    )
    run.add_argument(
        "--phrasing",
        default="formal",
        choices=["formal", "colloquial"],
        help="seeded-error tasks only; ignored for capability tasks",
    )
    run.add_argument(
        "--output",
        default=str(_BENCH_ROOT / "data"),
        help="data root for trial logs (default: benchmark/data)",
    )
    run.add_argument(
        "--max-budget-usd",
        type=float,
        default=None,
        help="hard per-trial API spend cap passed to the agent CLI "
        "(kill-switch; omit for no cap)",
    )
    run.add_argument(
        "--trial-index-start",
        type=int,
        default=0,
        help="first immutable trial index (scheduler/resume seam; default 0)",
    )
    run.add_argument(
        "--expect-cli-version",
        default=None,
        help="refuse the cell before trial 1 unless the CLI probe contains "
        "this exact version token",
    )
    run.add_argument(
        "--inter-trial-delay-seconds",
        type=float,
        default=0.0,
        help="conservative delay after each trial except the last",
    )
    run.add_argument(
        "--hide-outcomes",
        action="store_true",
        help="print RECORDED/INVALID only (used by outcome-blind scheduling)",
    )
    run.add_argument(
        "--schedule-token",
        default=None,
        help=argparse.SUPPRESS,
    )
    run.add_argument(
        "--valid-slot-index",
        type=int,
        default=None,
        help=argparse.SUPPRESS,
    )

    schedule = sub.add_parser(
        "schedule",
        help="plan, dry-run, and resume serial V1/V2 collection matrices",
    )
    schedule_sub = schedule.add_subparsers(dest="schedule_action", required=True)

    schedule_plan = schedule_sub.add_parser(
        "plan", help="write an immutable, pre-outcome collection plan"
    )
    schedule_plan.add_argument(
        "--phase",
        required=True,
        choices=[
            "pilot",
            "v2-pilot",
            "v2-confirmatory",
            "codex-mini-pilot",
            "agy-mini-pilot",
            "confirmatory",
        ],
    )
    schedule_plan.add_argument("--manifest", required=True, help="new plan JSON")
    schedule_plan.add_argument(
        "--runtime-matrix",
        type=Path,
        default=None,
        help="frozen V2 runtime matrix (required for v2-pilot)",
    )
    schedule_plan.add_argument(
        "--sizing-lock",
        type=Path,
        default=None,
        help="verified R-006 sizing lock (required for confirmatory plans)",
    )
    schedule_plan.add_argument(
        "--v2-design-lock",
        type=Path,
        default=None,
        help="signed prospective N=36 design lock (required for v2-confirmatory)",
    )
    schedule_plan.add_argument(
        "--v2-pilot-release",
        type=Path,
        default=None,
        help="signed plan-bound pilot release (required for v2-confirmatory)",
    )
    schedule_plan.add_argument(
        "--blinding-commitment",
        type=Path,
        default=None,
        help="independently anchored R-005 commitment (required for confirmatory)",
    )
    schedule_plan.add_argument(
        "--agy-cli-version",
        default=None,
        help="exact day-one agy version (required for plans containing agy)",
    )
    schedule_plan.add_argument(
        "--seed",
        type=int,
        default=20260525,
        help="deterministic cell-order seed (default 20260525)",
    )

    schedule_run = schedule_sub.add_parser(
        "run",
        help="show status by default; add --execute to make paid calls",
    )
    schedule_run.add_argument("--manifest", required=True, help="plan JSON")
    schedule_run.add_argument(
        "--output", required=True, help="dedicated output root for this phase"
    )
    schedule_run.add_argument(
        "--runtime-matrix",
        type=Path,
        default=None,
        help="independently supplied frozen V2 runtime matrix",
    )
    schedule_run.add_argument(
        "--execute",
        action="store_true",
        help="execute missing cells (without this flag, status is read-only)",
    )
    schedule_run.add_argument(
        "--only-env", action="append", default=[], help="repeatable env filter"
    )
    schedule_run.add_argument(
        "--only-config",
        action="append",
        default=[],
        help="repeatable CFG1..CFG7 filter",
    )
    schedule_run.add_argument(
        "--only-task", action="append", default=[], help="repeatable C01/T01 filter"
    )
    schedule_run.add_argument(
        "--max-cells",
        type=int,
        default=None,
        help="run at most this many pending cells in persisted plan order",
    )
    schedule_run.add_argument(
        "--batch-size",
        type=int,
        default=6,
        help="maximum trials per child cell invocation (default 6)",
    )
    schedule_run.add_argument(
        "--max-zero-progress-batches",
        type=int,
        default=3,
        help="stop after this many consecutive all-invalid batches (default 3)",
    )
    schedule_run.add_argument(
        "--inter-trial-delay",
        action="append",
        default=[],
        metavar="AGENT=SECONDS",
        help="required per selected agent for --execute; repeat as needed",
    )
    schedule_run.add_argument(
        "--max-budget-usd",
        type=float,
        default=None,
        help="optional per-trial hard cap passed through to supported agents",
    )
    schedule_run.add_argument(
        "--blinding-commitment",
        type=Path,
        default=None,
        help="independently anchored R-005 commitment (required for confirmatory execution)",
    )

    args = parser.parse_args(argv)

    if args.command == "run":
        task_path = _resolve_task(args.task)
        print(
            f"cell: task={task_path.name} agent={args.agent} "
            f"model={args.model} env={args.env} "
            f"phrasing={args.phrasing} trials={args.trials}"
        )
        # Expected config errors (typo'd / unbuilt env or agent, malformed
        # task) get a one-line message, not a stack trace. An UNEXPECTED
        # error still raises with full traceback — that's a real bug we want
        # to see, not hide.
        try:
            schedule_identity = (
                ScheduleIdentity.decode_token(args.schedule_token)
                if args.schedule_token is not None
                else None
            )
            paths = run_cell(
                task_path=task_path,
                agent_id=args.agent,
                model_id=args.model,
                env_id=args.env,
                phrasing=args.phrasing,
                trials=args.trials,
                data_root=Path(args.output),
                max_budget_usd=args.max_budget_usd,
                trial_index_start=args.trial_index_start,
                show_outcomes=not args.hide_outcomes,
                expected_cli_version=args.expect_cli_version,
                inter_trial_delay_seconds=args.inter_trial_delay_seconds,
                schedule_identity=schedule_identity,
                valid_slot_index=args.valid_slot_index,
            )
        except (KeyError, NotImplementedError, ValueError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        print(f"done: {len(paths)} terminal attempt artifact(s) under {args.output}")
        return 0

    if args.command == "schedule":
        from .scheduler import (
            ScheduleError,
            build_plan,
            load_plan,
            run_schedule,
            write_plan,
        )
        from .sizing_lock import SizingLockError, load_sizing_lock
        from .v2_design_lock import (
            V2DesignLockError,
            load_v2_design_lock,
            load_v2_pilot_release,
        )
        from .blinding import BlindingError, load_commitment

        try:
            if args.schedule_action == "plan":
                runtime_binding = None
                if args.runtime_matrix is not None:
                    from scripts.configuration_matrix import load_matrix

                    runtime_binding = load_matrix(
                        args.runtime_matrix
                    ).scheduler_binding()
                sizing_lock = (
                    load_sizing_lock(args.sizing_lock)
                    if args.sizing_lock is not None
                    else None
                )
                v2_design_lock = (
                    load_v2_design_lock(args.v2_design_lock)
                    if args.v2_design_lock is not None
                    else None
                )
                v2_pilot_release = (
                    load_v2_pilot_release(args.v2_pilot_release, v2_design_lock)
                    if args.v2_pilot_release is not None
                    and v2_design_lock is not None
                    else None
                )
                if args.v2_pilot_release is not None and v2_design_lock is None:
                    raise V2DesignLockError(
                        "--v2-pilot-release requires --v2-design-lock"
                    )
                sizing_anchor = None
                if args.blinding_commitment is not None:
                    commitment, commitment_sha256 = load_commitment(
                        args.blinding_commitment
                    )
                    sizing_anchor = {
                        "commitment_digest": commitment.commitment_digest,
                        "commitment_artifact_sha256": commitment_sha256,
                        "commitment_public_key_b64": commitment.public_key_b64,
                    }
                plan = build_plan(
                    args.phase,
                    sizing_lock=sizing_lock,
                    sizing_anchor=sizing_anchor,
                    agy_cli_version=args.agy_cli_version,
                    runtime_binding=runtime_binding,
                    v2_design_lock=v2_design_lock,
                    v2_pilot_release=v2_pilot_release,
                    order_seed=args.seed,
                )
                write_plan(plan, Path(args.manifest))
                print(
                    f"planned {plan.phase}: {len(plan.cells)} cells, "
                    f"{sum(cell.target_valid_trials for cell in plan.cells)} "
                    f"valid trials; digest {plan.digest}"
                )
                print(f"manifest: {Path(args.manifest).resolve()}")
                return 0

            delays: dict[str, float] = {}
            for entry in args.inter_trial_delay:
                if "=" not in entry:
                    raise ScheduleError(
                        f"invalid --inter-trial-delay {entry!r}; "
                        "expected AGENT=SECONDS"
                    )
                agent_id, raw_seconds = entry.split("=", 1)
                if agent_id in delays:
                    raise ScheduleError(
                        f"duplicate inter-trial delay for {agent_id!r}"
                    )
                try:
                    delays[agent_id] = float(raw_seconds)
                except ValueError as exc:
                    raise ScheduleError(
                        f"invalid delay seconds in {entry!r}"
                    ) from exc

            plan = load_plan(Path(args.manifest))
            runtime_binding = None
            if args.runtime_matrix is not None:
                from scripts.configuration_matrix import load_matrix

                runtime_binding = load_matrix(args.runtime_matrix).scheduler_binding()
            sizing_anchor = None
            if args.blinding_commitment is not None:
                commitment, commitment_sha256 = load_commitment(
                    args.blinding_commitment
                )
                sizing_anchor = {
                    "commitment_digest": commitment.commitment_digest,
                    "commitment_artifact_sha256": commitment_sha256,
                    "commitment_public_key_b64": commitment.public_key_b64,
                }
            summary = run_schedule(
                plan,
                output_root=Path(args.output),
                execute=args.execute,
                only_envs=set(args.only_env) or None,
                only_configs=set(args.only_config) or None,
                only_tasks=set(args.only_task) or None,
                max_cells=args.max_cells,
                batch_size=args.batch_size,
                max_zero_progress_batches=args.max_zero_progress_batches,
                inter_trial_delays=delays,
                max_budget_usd=args.max_budget_usd,
                sizing_anchor=sizing_anchor,
                runtime_binding=runtime_binding,
            )
            mode = "executed" if args.execute else "status (no execution)"
            print(
                f"{mode}: phase={summary.phase} "
                f"selected={summary.selected_cells} "
                f"complete={summary.complete_cells} "
                f"pending={summary.pending_cells} "
                f"valid={summary.existing_valid_trials}/"
                f"{summary.target_valid_trials} "
                f"invalid={summary.existing_invalid_trials} "
                f"unresolved={summary.existing_unresolved_attempts} "
                f"execution_cells={summary.execution_cells} "
                f"new_attempts={summary.executed_attempts}"
            )
            return 0
        except (
            BlindingError,
            ScheduleError,
            SizingLockError,
            V2DesignLockError,
            ValueError,
        ) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2

    return 1


if __name__ == "__main__":
    sys.exit(main())
