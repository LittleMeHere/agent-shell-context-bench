"""Trial orchestration: one (task, agent, model, env, phrasing) cell.

This is the only place the moving parts meet. Order is load-bearing:

  probe + cli_version   ONCE per cell (cheap, identical across trials,
                        recorded in every trial log for reproducibility)
  per trial:
    fresh sandbox  ->  snapshot BEFORE  ->  agent runs  ->  snapshot AFTER
    ->  diff  ->  success checks  ->  immutable log  ->  teardown

The BEFORE snapshot exists so a destructive over-correction (rubric D/E) is
visible as a diff against the task's clean starting state, not guessed.
Every trial is logged even if it errored — see logging/.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path

import yaml

from .checks import evaluate_checks
from .logging import build_trial_record, write_trial
from .registry import make_agent, make_environment


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")


def load_task(path: Path) -> dict:
    """Load + minimally validate a task YAML.

    Validation is intentionally shallow: enough to fail fast on a malformed
    task before burning an API call, not a schema framework. A capability
    task has `prompt`; a seeded-error task has `prompts: {formal, colloquial}`.
    """
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
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
) -> list[Path]:
    """Run `trials` independent trials for one cell. Returns log paths.

    A single trial raising does NOT abort the cell: it is logged (the
    template method in AgentAdapter.run captures harness errors into the
    record) and the loop continues, so one bad trial cannot silently shrink
    the sample.
    """
    task = load_task(task_path)
    prompt, eff_phrasing = resolve_prompt(task, phrasing)
    preconditions = task.get("preconditions", {}) or {}
    timeout = float(task.get("timeout_seconds", 180))

    environment = make_environment(env_id)
    agent = make_agent(agent_id, model_id, max_budget_usd=max_budget_usd)

    # Once per cell — identical across trials, logged in each record.
    env_probe = environment.probe()
    cli_version = agent.cli_version(environment)

    written: list[Path] = []
    for i in range(trials):
        started_at = _utc_now()
        with environment.trial_sandbox(
            task["id"], i, preconditions
        ) as sandbox:
            before = environment.snapshot(sandbox)
            result = agent.run(
                prompt, sandbox, environment, timeout=timeout
            )
            after = environment.snapshot(sandbox)
            diff = environment.diff(before, after)
            success, checks = evaluate_checks(
                after,
                task["success_checks"],
                sandbox_host_root=sandbox.host_root,
                agent_commands=result.commands,
            )

            record = build_trial_record(
                task_id=task["id"],
                task_category=str(task.get("category", "")),
                agent_id=agent_id,
                model_id=model_id,
                env_id=env_id,
                phrasing=eff_phrasing,
                trial_index=i,
                prompt=prompt,
                started_at=started_at,
                env_probe=env_probe,
                cli_version=cli_version,
                agent_result=result,
                snapshot_before=before,
                snapshot_after=after,
                fs_diff=diff,
                success=success,
                check_results=checks,
            )
            path = write_trial(record, data_root)
            written.append(path)

        status = (
            "INVALID" if result.invalid
            else "PASS" if success
            else "FAIL"
        )
        flags = []
        if diff.escaped_sandbox:
            flags.append("ESCAPED-SANDBOX")
        if not result.completed and not result.invalid:
            flags.append("TIMEOUT/INCOMPLETE")
        suffix = f" [{' '.join(flags)}]" if flags else ""
        print(
            f"  trial {i + 1}/{trials}: {status}{suffix}  "
            f"({result.wall_time_seconds:.1f}s)  -> {path.name}"
        )

    return written
