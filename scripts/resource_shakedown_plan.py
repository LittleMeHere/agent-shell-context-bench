"""Build the deterministic, analysis-excluded resource shakedown manifest.

The manifest is operational evidence for D-004/G4, never pilot or
confirmatory data.  This module does not execute a model call.  It fixes the
smallest current design that measures every model-harness configuration on a
representative Windows workload and exercises every non-Windows transport
with one workhorse configuration per agent. V2 manifests bind an explicit
candidate or frozen runtime-matrix digest; the legacy version flag exists only
for V1 diagnostic reproduction.
"""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import random
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from harness.scheduler import (  # noqa: E402
    DEFAULT_ORDER_SEED,
    ENVIRONMENTS,
    ModelConfig,
    task_variants,
)
from scripts.configuration_matrix import (  # noqa: E402
    RuntimeMatrix,
    legacy_v1_matrix,
    load_matrix,
)

SCHEMA_VERSION = "1.1.0"
DEFAULT_SHAKEDOWN_SEED = DEFAULT_ORDER_SEED + 404
CORE_ENVIRONMENT = "windows_powershell"
CORE_VARIANTS = (
    ("C01", "default", "capability-short"),
    ("C05", "default", "capability-long"),
    ("T01", "formal", "seeded-syntax"),
    ("T05", "colloquial", "seeded-destructive"),
    ("T09", "formal", "seeded-subtle-verification"),
)
CORE_REPLICATES = 2
TRANSPORT_TASK = ("C01", "default")
WORKHORSE_CONFIGS = ("CFG2", "CFG4", "CFG6")
MEASUREMENTS = (
    "wall_time_seconds",
    "process_duration_seconds",
    "validity_and_measurement_attribution",
    "provider_usage_before_after_when_surfaced",
    "rate_limit_or_routing_message",
    "retry_count",
)


@dataclass(frozen=True)
class ShakedownCall:
    call_id: str
    stage: str
    stratum: str
    config_id: str
    agent_id: str
    model_id: str
    expected_cli_version: str
    env_id: str
    task_id: str
    task_path: str
    task_sha256: str
    phrasing: str
    replicate: int
    measurements: tuple[str, ...] = MEASUREMENTS


@dataclass(frozen=True)
class ShakedownPlan:
    schema_version: str
    created_at: str
    order_seed: int
    analysis_excluded: bool
    purpose: str
    matrix_status: str
    matrix_digest: str
    calls: tuple[ShakedownCall, ...]
    digest: str

    def payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "order_seed": self.order_seed,
            "analysis_excluded": self.analysis_excluded,
            "purpose": self.purpose,
            "matrix_status": self.matrix_status,
            "matrix_digest": self.matrix_digest,
            "calls": [dataclasses.asdict(call) for call in self.calls],
        }

    def as_dict(self) -> dict[str, Any]:
        return {
            **self.payload(),
            "created_at": self.created_at,
            "digest": self.digest,
        }


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _digest(value: Mapping[str, object]) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _call_id(coordinate: Mapping[str, object]) -> str:
    return _digest(coordinate)[:20]


def build_shakedown_plan(
    *,
    agy_cli_version: str | None = None,
    matrix: RuntimeMatrix | None = None,
    order_seed: int = DEFAULT_SHAKEDOWN_SEED,
    created_at: str | None = None,
) -> ShakedownPlan:
    if matrix is not None and agy_cli_version is not None:
        raise ValueError("supply matrix or agy_cli_version, not both")
    if matrix is None:
        if agy_cli_version is None or not agy_cli_version.strip():
            raise ValueError(
                "matrix or agy_cli_version must identify the shakedown runtime"
            )
        matrix = legacy_v1_matrix(agy_cli_version)

    configs = matrix.model_configs()
    configs_by_id = {config.config_id: config for config in configs}
    variants = {
        (variant.task_id, variant.phrasing): variant for variant in task_variants()
    }
    calls: list[ShakedownCall] = []

    def add_call(
        *,
        stage: str,
        stratum: str,
        config: ModelConfig,
        env_id: str,
        task_id: str,
        phrasing: str,
        replicate: int,
    ) -> None:
        variant = variants[(task_id, phrasing)]
        coordinate = {
            "stage": stage,
            "config_id": config.config_id,
            "env_id": env_id,
            "task_id": task_id,
            "phrasing": phrasing,
            "replicate": replicate,
        }
        if config.expected_cli_version is None:
            raise ValueError(f"{config.config_id} has no CLI version")
        calls.append(
            ShakedownCall(
                call_id=_call_id(coordinate),
                stage=stage,
                stratum=stratum,
                config_id=config.config_id,
                agent_id=config.agent_id,
                model_id=config.model_id,
                expected_cli_version=config.expected_cli_version,
                env_id=env_id,
                task_id=task_id,
                task_path=variant.task_path,
                task_sha256=variant.task_sha256,
                phrasing=phrasing,
                replicate=replicate,
            )
        )

    for config in configs:
        for task_id, phrasing, stratum in CORE_VARIANTS:
            for replicate in range(1, CORE_REPLICATES + 1):
                add_call(
                    stage="resource-core",
                    stratum=stratum,
                    config=config,
                    env_id=CORE_ENVIRONMENT,
                    task_id=task_id,
                    phrasing=phrasing,
                    replicate=replicate,
                )

    transport_task, transport_phrasing = TRANSPORT_TASK
    for env_id in ENVIRONMENTS:
        if env_id == CORE_ENVIRONMENT:
            continue
        for config_id in WORKHORSE_CONFIGS:
            add_call(
                stage="transport-qualification",
                stratum="c01-workhorse-transport",
                config=configs_by_id[config_id],
                env_id=env_id,
                task_id=transport_task,
                phrasing=transport_phrasing,
                replicate=1,
            )

    if len(calls) != 82:
        raise AssertionError(f"expected 82 shakedown calls, built {len(calls)}")
    if len({call.call_id for call in calls}) != len(calls):
        raise AssertionError("shakedown call-id collision")

    random.Random(order_seed).shuffle(calls)
    provisional = ShakedownPlan(
        schema_version=SCHEMA_VERSION,
        created_at=created_at or _utc_now(),
        order_seed=order_seed,
        analysis_excluded=True,
        purpose=(
            "D-004 resource calibration and G4 transport qualification; "
            "never pilot or confirmatory inference"
        ),
        matrix_status=matrix.status,
        matrix_digest=matrix.digest,
        calls=tuple(calls),
        digest="",
    )
    return dataclasses.replace(provisional, digest=_digest(provisional.payload()))


def validate_plan(plan: ShakedownPlan) -> None:
    if plan.schema_version != SCHEMA_VERSION:
        raise ValueError(f"unsupported shakedown schema {plan.schema_version!r}")
    if not plan.analysis_excluded:
        raise ValueError("resource shakedown must be marked analysis_excluded")
    if plan.matrix_status not in {"candidate", "frozen", "legacy-diagnostic"}:
        raise ValueError(f"invalid shakedown matrix_status {plan.matrix_status!r}")
    if len(plan.matrix_digest) != 64:
        raise ValueError("shakedown matrix_digest must be a sha256 digest")
    if len(plan.calls) != 82:
        raise ValueError(f"resource shakedown must contain 82 calls, found {len(plan.calls)}")
    if len({call.call_id for call in plan.calls}) != len(plan.calls):
        raise ValueError("duplicate shakedown call_id")
    if _digest(plan.payload()) != plan.digest:
        raise ValueError("shakedown manifest digest mismatch")


def load_plan(path: Path) -> ShakedownPlan:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        calls = tuple(ShakedownCall(**call) for call in raw["calls"])
        plan = ShakedownPlan(
            schema_version=str(raw["schema_version"]),
            created_at=str(raw["created_at"]),
            order_seed=int(raw["order_seed"]),
            analysis_excluded=bool(raw["analysis_excluded"]),
            purpose=str(raw["purpose"]),
            matrix_status=str(raw["matrix_status"]),
            matrix_digest=str(raw["matrix_digest"]),
            calls=calls,
            digest=str(raw["digest"]),
        )
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot load shakedown manifest {path}: {exc}") from exc
    validate_plan(plan)
    return plan


def write_plan(plan: ShakedownPlan, output: Path) -> None:
    validate_plan(plan)
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        with output.open("x", encoding="utf-8", newline="\n") as handle:
            json.dump(plan.as_dict(), handle, indent=2, sort_keys=True)
            handle.write("\n")
    except FileExistsError as exc:
        raise ValueError(f"refusing to overwrite existing manifest: {output}") from exc


def _summary(plan: ShakedownPlan) -> dict[str, object]:
    by_agent = {
        agent: sum(call.agent_id == agent for call in plan.calls)
        for agent in ("claude_code", "codex", "agy")
    }
    by_stage = {
        stage: sum(call.stage == stage for call in plan.calls)
        for stage in ("resource-core", "transport-qualification")
    }
    return {
        "digest": plan.digest,
        "matrix_digest": plan.matrix_digest,
        "matrix_status": plan.matrix_status,
        "calls": len(plan.calls),
        "by_agent": by_agent,
        "by_stage": by_stage,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument(
        "--matrix",
        type=Path,
        help="candidate or frozen runtime-matrix JSON (required for V2)",
    )
    source.add_argument(
        "--agy-cli-version",
        help="legacy V1 diagnostic mode using frozen V1 model/CLI constants",
    )
    parser.add_argument("--order-seed", type=int, default=DEFAULT_SHAKEDOWN_SEED)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    plan = build_shakedown_plan(
        agy_cli_version=args.agy_cli_version,
        matrix=load_matrix(args.matrix) if args.matrix is not None else None,
        order_seed=args.order_seed,
    )
    write_plan(plan, args.output)
    print(json.dumps(_summary(plan), indent=2, sort_keys=True))
    print(f"manifest: {args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
