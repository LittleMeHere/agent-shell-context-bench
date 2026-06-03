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
            paths = run_cell(
                task_path=task_path,
                agent_id=args.agent,
                model_id=args.model,
                env_id=args.env,
                phrasing=args.phrasing,
                trials=args.trials,
                data_root=Path(args.output),
                max_budget_usd=args.max_budget_usd,
            )
        except (KeyError, NotImplementedError, ValueError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        print(f"done: {len(paths)} trial log(s) under {args.output}")
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
