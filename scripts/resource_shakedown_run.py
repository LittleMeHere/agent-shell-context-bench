"""Dry-run or execute calls from a bound, analysis-excluded shakedown plan.

Execution is opt-in with ``--execute`` and is refused from the methodology
checkout.  Each call receives a new output directory plus a receipt binding
the immutable trial artifacts to the shakedown-manifest digest.  Outcomes are
hidden from console output.  Raw shakedown artifacts belong in an external,
private operational root and are never inferential data.
"""

from __future__ import annotations

import argparse
import contextlib
import dataclasses
import hashlib
import json
import os
import subprocess
import sys
from collections.abc import Callable, Iterator, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from scripts.resource_shakedown_plan import (  # noqa: E402
    ShakedownCall,
    ShakedownPlan,
    load_plan,
)
from harness.logging.writer import SCHEMA_VERSION as TRIAL_SCHEMA_VERSION  # noqa: E402
from harness.schedule_identity import ScheduleIdentity  # noqa: E402

BOUND_MANIFEST = ".shakedown-manifest.json"
LOCK_NAME = ".shakedown.lock"
RECEIPT_NAME = "receipt.json"


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_execution_paths(output_root: Path, cwd: Path | None = None) -> None:
    control = (cwd or Path.cwd()).resolve()
    output = output_root.resolve()
    repo = REPO_ROOT.resolve()
    if _is_relative_to(control, repo):
        raise ValueError(
            f"refusing shakedown execution from methodology checkout {control}"
        )
    if _is_relative_to(output, repo):
        raise ValueError(
            "raw shakedown output must use an external private operational root"
        )


def validate_task_hashes(plan: ShakedownPlan) -> None:
    for call in plan.calls:
        path = (REPO_ROOT / call.task_path).resolve()
        if not _is_relative_to(path, REPO_ROOT.resolve()) or not path.is_file():
            raise ValueError(f"{call.call_id}: invalid task path {call.task_path!r}")
        observed = _sha256_file(path)
        if observed != call.task_sha256:
            raise ValueError(
                f"{call.call_id}: task hash drift for {call.task_path}: "
                f"expected {call.task_sha256}, observed {observed}"
            )


def select_calls(
    plan: ShakedownPlan,
    *,
    call_ids: set[str] | None = None,
    agents: set[str] | None = None,
    configs: set[str] | None = None,
    envs: set[str] | None = None,
    stages: set[str] | None = None,
    max_calls: int | None = None,
) -> tuple[ShakedownCall, ...]:
    if max_calls is not None and max_calls < 1:
        raise ValueError("max_calls must be >= 1")
    available = {
        "call": {call.call_id for call in plan.calls},
        "agent": {call.agent_id for call in plan.calls},
        "config": {call.config_id for call in plan.calls},
        "env": {call.env_id for call in plan.calls},
        "stage": {call.stage for call in plan.calls},
    }
    requested = {
        "call": call_ids,
        "agent": agents,
        "config": configs,
        "env": envs,
        "stage": stages,
    }
    for label, values in requested.items():
        unknown = (values or set()) - available[label]
        if unknown:
            raise ValueError(
                f"unknown {label} filter(s) {sorted(unknown)}; "
                f"available: {sorted(available[label])}"
            )
    selected = tuple(
        call
        for call in plan.calls
        if (not call_ids or call.call_id in call_ids)
        and (not agents or call.agent_id in agents)
        and (not configs or call.config_id in configs)
        and (not envs or call.env_id in envs)
        and (not stages or call.stage in stages)
    )
    return selected[:max_calls] if max_calls is not None else selected


def _schedule_identity(plan: ShakedownPlan, call: ShakedownCall) -> ScheduleIdentity:
    """Bind one analysis-excluded call to its immutable shakedown manifest.

    The regular child runner deliberately requires a schedule token whenever
    outcomes are hidden.  Shakedown calls are not collection cells, but they
    still need the same task/configuration/provenance boundary rather than an
    exception that would weaken fail-closed collection execution.
    """
    cell_id = hashlib.sha256(
        f"resource-shakedown:{plan.digest}:{call.call_id}".encode("utf-8")
    ).hexdigest()[:16]
    return ScheduleIdentity.create(
        phase="resource-shakedown",
        plan_digest=plan.digest,
        cell_id=cell_id,
        config_id=call.config_id,
        task_sha256=call.task_sha256,
        trial_schema_version=TRIAL_SCHEMA_VERSION,
        target_valid_trials=1,
        task_id=call.task_id,
        agent_id=call.agent_id,
        model_id=call.model_id,
        env_id=call.env_id,
        phrasing=call.phrasing,
        expected_cli_version=call.expected_cli_version,
        valid_slot_index=0,
    )


def build_argv(
    plan: ShakedownPlan, call: ShakedownCall, output: Path
) -> list[str]:
    schedule_identity = _schedule_identity(plan, call)
    argv = [
        sys.executable,
        "-m",
        "harness",
        "run",
        "--task",
        str((REPO_ROOT / call.task_path).resolve()),
        "--agent",
        call.agent_id,
        "--model",
        call.model_id,
        "--env",
        call.env_id,
        "--trials",
        "1",
        "--output",
        str(output.resolve()),
        "--trial-index-start",
        str(call.replicate - 1),
        "--expect-cli-version",
        call.expected_cli_version,
        "--inter-trial-delay-seconds",
        "0",
        "--hide-outcomes",
        "--schedule-token",
        schedule_identity.encode_token(),
        "--valid-slot-index",
        "0",
    ]
    if call.phrasing != "default":
        argv.extend(["--phrasing", call.phrasing])
    return argv


def _load_bound_manifest(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read bound shakedown manifest {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"bound shakedown manifest is not an object: {path}")
    return value


def bind_output(output_root: Path, plan: ShakedownPlan) -> None:
    output_root.mkdir(parents=True, exist_ok=True)
    bound = output_root / BOUND_MANIFEST
    if bound.exists():
        raw = _load_bound_manifest(bound)
        if raw.get("digest") != plan.digest:
            raise ValueError(
                f"output root is bound to {raw.get('digest')}, not {plan.digest}"
            )
        return
    if any(output_root.iterdir()):
        raise ValueError(f"unbound shakedown output root is not empty: {output_root}")
    try:
        with bound.open("x", encoding="utf-8", newline="\n") as handle:
            json.dump(plan.as_dict(), handle, indent=2, sort_keys=True)
            handle.write("\n")
    except FileExistsError as exc:
        raise ValueError(f"shakedown output was concurrently bound: {bound}") from exc


@contextlib.contextmanager
def output_lock(output_root: Path, plan: ShakedownPlan) -> Iterator[None]:
    lock = output_root / LOCK_NAME
    try:
        with lock.open("x", encoding="utf-8", newline="\n") as handle:
            json.dump(
                {"manifest_digest": plan.digest, "pid": os.getpid(), "at": _utc_now()},
                handle,
                sort_keys=True,
            )
            handle.write("\n")
    except FileExistsError as exc:
        raise ValueError(
            f"shakedown lock already exists: {lock}; verify no run is active"
        ) from exc
    try:
        yield
    finally:
        lock.unlink(missing_ok=True)


def _artifact_hashes(call_root: Path) -> list[dict[str, object]]:
    artifacts = []
    for path in sorted(call_root.rglob("*")):
        if path.is_file() and path.name != RECEIPT_NAME:
            artifacts.append(
                {
                    "path": path.relative_to(call_root).as_posix(),
                    "bytes": path.stat().st_size,
                    "sha256": _sha256_file(path),
                }
            )
    return artifacts


def _write_receipt(
    call_root: Path,
    *,
    plan: ShakedownPlan,
    call: ShakedownCall,
    started_at: str,
    returncode: int,
) -> Path:
    call_root.mkdir(parents=True, exist_ok=True)
    receipt = call_root / RECEIPT_NAME
    payload = {
        "schema_version": "1.0.0",
        "manifest_digest": plan.digest,
        "analysis_excluded": True,
        "call": dataclasses.asdict(call),
        "started_at": started_at,
        "finished_at": _utc_now(),
        "returncode": returncode,
        "artifacts": _artifact_hashes(call_root),
    }
    try:
        with receipt.open("x", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
    except FileExistsError as exc:
        raise ValueError(f"refusing to overwrite shakedown receipt: {receipt}") from exc
    return receipt


def execute_calls(
    plan: ShakedownPlan,
    calls: Sequence[ShakedownCall],
    *,
    output_root: Path,
    cwd: Path | None = None,
    executor: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> int:
    validate_execution_paths(output_root, cwd)
    validate_task_hashes(plan)
    bind_output(output_root, plan)
    control = (cwd or Path.cwd()).resolve()
    process_env = dict(os.environ)
    existing_pythonpath = process_env.get("PYTHONPATH")
    process_env["PYTHONPATH"] = (
        str(REPO_ROOT)
        if not existing_pythonpath
        else str(REPO_ROOT) + os.pathsep + existing_pythonpath
    )
    completed = 0
    with output_lock(output_root, plan):
        for call in calls:
            call_root = output_root / "calls" / call.call_id
            if call_root.exists():
                raise ValueError(
                    f"refusing duplicate shakedown call; output exists: {call_root}"
                )
            started_at = _utc_now()
            result = executor(
                build_argv(plan, call, call_root),
                cwd=control,
                env=process_env,
                capture_output=True,
                text=True,
                timeout=1200,
                check=False,
            )
            _write_receipt(
                call_root,
                plan=plan,
                call=call,
                started_at=started_at,
                returncode=result.returncode,
            )
            print(
                f"{call.call_id} {call.env_id}/{call.config_id}: "
                f"{'RECORDED' if result.returncode == 0 else 'EXECUTION_ERROR'}"
            )
            completed += 1
            if result.returncode != 0:
                stderr = (result.stderr or "").strip()[-1000:]
                if stderr:
                    print(f"  stderr: {stderr}", file=sys.stderr)
                return 1
    return 0 if completed == len(calls) else 1


def _print_dry_run(
    plan: ShakedownPlan,
    calls: Sequence[ShakedownCall],
    output_root: Path,
) -> None:
    print(
        f"DRY RUN: {len(calls)} analysis-excluded call(s), "
        f"manifest={plan.digest}"
    )
    for call in calls:
        print(
            f"  {call.call_id} {call.stage} {call.env_id}/{call.config_id}/"
            f"{call.task_id}/{call.phrasing} -> {output_root / 'calls' / call.call_id}"
        )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--call-id", action="append")
    parser.add_argument("--agent", action="append")
    parser.add_argument("--config", action="append")
    parser.add_argument("--env", action="append")
    parser.add_argument("--stage", action="append")
    parser.add_argument("--max-calls", type=int)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args(argv)
    plan = load_plan(args.manifest)
    calls = select_calls(
        plan,
        call_ids=set(args.call_id or []),
        agents=set(args.agent or []),
        configs=set(args.config or []),
        envs=set(args.env or []),
        stages=set(args.stage or []),
        max_calls=args.max_calls,
    )
    if not calls:
        parser.error("filters selected zero shakedown calls")
    if not args.execute:
        _print_dry_run(plan, calls, args.output)
        return 0
    return execute_calls(plan, calls, output_root=args.output)


if __name__ == "__main__":
    raise SystemExit(main())
