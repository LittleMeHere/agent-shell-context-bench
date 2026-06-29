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
from datetime import datetime, timezone
from pathlib import Path

from ..types import AgentRunResult, CheckResult, FilesystemDiff, FilesystemSnapshot

# 1.1.0: additive, optional top-level `agy` section (per-command Cwd tags,
# compliance, brain-transcript location, scratch-canary escape) present only on
# agy trials. No existing field changed — pre-data additive bump.
SCHEMA_VERSION = "1.1.0"


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
    }


def _json_default(obj: object) -> object:
    if isinstance(obj, Path):
        return str(obj)
    if isinstance(obj, tuple):
        return list(obj)
    raise TypeError(f"not JSON-serialisable: {type(obj).__name__}")


def build_trial_record(
    *,
    task_id: str,
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
    success: bool,
    check_results: list[CheckResult],
    agy: dict | None = None,
) -> dict:
    """Assemble the full immutable record for one trial.

    `spiral_code` is null by design — it is applied post hoc by the
    classifier (rubric A-F) reading `agent.transcript`, never during the
    run. `valid` is the gate the SAP uses to include/exclude the trial.

    `agy` is the optional, additive section the agy runtime supplies (per-command
    Cwd tags + compliance, brain-transcript location, scratch-canary escape). It
    is present ONLY on agy trials; every other config omits the key entirely, so
    non-agy records are byte-for-byte unchanged by this field (schema 1.1.0).
    """
    record: dict = {
        "schema_version": SCHEMA_VERSION,
        "trial": {
            "task_id": task_id,
            "task_category": task_category,
            "agent_id": agent_id,
            "model_id": model_id,
            "env_id": env_id,
            "phrasing": phrasing,
            "trial_index": trial_index,
            "started_at": started_at,
            "finished_at": _utc_now(),
        },
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
            "success": success,
            "checks": [dataclasses.asdict(r) for r in check_results],
        },
        "spiral_code": None,
        "validity": {
            "valid": not agent_result.invalid,
            "harness_error": agent_result.harness_error,
        },
    }
    if agy is not None:
        record["agy"] = agy
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
    if out_path.exists():
        raise FileExistsError(
            f"refusing to overwrite existing trial log: {out_path}"
        )
    out_path.write_text(
        json.dumps(record, indent=2, default=_json_default, ensure_ascii=False),
        encoding="utf-8",
    )
    return out_path
