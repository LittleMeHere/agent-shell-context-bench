"""Append-only write-ahead journal for collection attempts.

The final trial JSON is intentionally rich and therefore cannot be written
until after filesystem measurement and success-check evaluation.  A paid
agent invocation must not disappear merely because one of those later stages
fails.  This module writes a small outer journal before the invocation and
appends one terminal event afterward.

Event order for one allocated trial index:

```
00 allocated
01 launch_committed       (durable before attempting external process launch)
02 invocation_observed    (the environment returned a process result)
03 trial_recorded | infrastructure_failure
```

Every event is a separately created immutable JSON file.  A process crash may
leave a valid prefix of the sequence; the scheduler treats such a prefix as
unresolved and blocks automatic retry.  A final trial record can also
deterministically reconcile an attempt when the trial write succeeded but the
``trial_recorded`` append did not.
"""

from __future__ import annotations

import hashlib
import json
import os
import traceback
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .schedule_identity import ScheduleIdentity


ATTEMPT_SCHEMA_VERSION = "1.3.0"
ATTEMPT_DIR_NAME = ".attempts"

PRE_INVOCATION_INFRASTRUCTURE_FAILURE = (
    "pre_invocation_infrastructure_failure"
)
POST_INVOCATION_INFRASTRUCTURE_FAILURE = (
    "post_invocation_infrastructure_failure"
)
INVOCATION_START_UNKNOWN_INFRASTRUCTURE_FAILURE = (
    "invocation_start_unknown_infrastructure_failure"
)
AGENT_INDUCED_MEASUREMENT_LOSS = "agent_induced_measurement_loss"
COMPLETE = "complete"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@dataclass(frozen=True)
class AttemptIdentity:
    """Stable identity shared by every journal event and the final trial."""

    attempt_id: str
    trial_index: int
    task_id: str
    agent_id: str
    model_id: str
    env_id: str
    phrasing: str

    def as_dict(self) -> dict[str, object]:
        return {
            "attempt_id": self.attempt_id,
            "trial_index": self.trial_index,
            "task_id": self.task_id,
            "agent_id": self.agent_id,
            "model_id": self.model_id,
            "env_id": self.env_id,
            "phrasing": self.phrasing,
        }


def _write_immutable_json(path: Path, payload: dict) -> None:
    """Create and fsync one event; never replace an existing path."""

    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = (_canonical_json(payload) + "\n").encode("utf-8")
    with path.open("xb") as handle:
        handle.write(encoded)
        handle.flush()
        os.fsync(handle.fileno())


class AttemptJournal:
    """Stateful writer for one append-only attempt event sequence."""

    def __init__(
        self,
        *,
        data_root: Path,
        identity: AttemptIdentity,
        allocated_path: Path,
        allocated_sha256: str,
        schedule_identity: ScheduleIdentity | None,
    ) -> None:
        self.data_root = data_root.resolve()
        self.identity = identity
        self.allocated_path = allocated_path
        self.allocated_sha256 = allocated_sha256
        self.schedule_identity = schedule_identity
        self.launch_committed = False
        self.invocation_observed = False
        self.terminal_written = False

    @classmethod
    def allocate(
        cls,
        *,
        data_root: Path,
        task_id: str,
        agent_id: str,
        model_id: str,
        env_id: str,
        phrasing: str,
        trial_index: int,
        schedule_identity: ScheduleIdentity | None = None,
    ) -> "AttemptJournal":
        if schedule_identity is not None:
            schedule_identity.validate_integrity()
        identity = AttemptIdentity(
            attempt_id=uuid.uuid4().hex,
            trial_index=trial_index,
            task_id=task_id,
            agent_id=agent_id,
            model_id=model_id,
            env_id=env_id,
            phrasing=phrasing,
        )
        data_root = data_root.resolve()
        directory = (
            data_root
            / env_id
            / agent_id
            / model_id
            / task_id
            / phrasing
            / ATTEMPT_DIR_NAME
        )
        path = directory / cls._event_name(identity, 0, "allocated")
        payload = cls._event_payload(
            identity,
            0,
            "allocated",
            schedule_identity=schedule_identity,
        )
        _write_immutable_json(path, payload)
        return cls(
            data_root=data_root,
            identity=identity,
            allocated_path=path,
            allocated_sha256=sha256_file(path),
            schedule_identity=schedule_identity,
        )

    @staticmethod
    def _event_name(
        identity: AttemptIdentity, sequence: int, event: str
    ) -> str:
        return (
            f"attempt_{identity.trial_index}__{identity.attempt_id}"
            f"__{sequence:02d}_{event}.json"
        )

    @staticmethod
    def _event_payload(
        identity: AttemptIdentity,
        sequence: int,
        event: str,
        *,
        result: dict | None = None,
        schedule_identity: ScheduleIdentity | None = None,
    ) -> dict:
        payload: dict = {
            "schema_version": ATTEMPT_SCHEMA_VERSION,
            "sequence": sequence,
            "event": event,
            "created_at": _utc_now(),
            "attempt": identity.as_dict(),
        }
        if result is not None:
            payload["result"] = result
        if schedule_identity is not None:
            payload["schedule"] = schedule_identity.as_dict()
        return payload

    @property
    def binding(self) -> dict[str, str]:
        return {
            "schema_version": ATTEMPT_SCHEMA_VERSION,
            "attempt_id": self.identity.attempt_id,
            "allocated_event_sha256": self.allocated_sha256,
        }

    def _append(
        self,
        sequence: int,
        event: str,
        *,
        result: dict | None = None,
    ) -> Path:
        path = self.allocated_path.with_name(
            self._event_name(self.identity, sequence, event)
        )
        payload = self._event_payload(
            self.identity,
            sequence,
            event,
            result=result,
            schedule_identity=self.schedule_identity,
        )
        _write_immutable_json(path, payload)
        return path

    def mark_launch_committed(self) -> None:
        """Durably record intent to launch before the external exec call."""

        if self.launch_committed:
            raise RuntimeError("launch_committed already recorded")
        if self.terminal_written:
            raise RuntimeError("cannot start an already terminal attempt")
        self._append(1, "launch_committed")
        self.launch_committed = True

    def mark_invocation_observed(self) -> None:
        """Record that the environment returned an external process result."""

        if not self.launch_committed:
            raise RuntimeError("cannot observe invocation before launch commitment")
        if self.invocation_observed:
            raise RuntimeError("invocation_observed already recorded")
        if self.terminal_written:
            raise RuntimeError("cannot observe an already terminal attempt")
        self._append(2, "invocation_observed")
        self.invocation_observed = True

    def finalize_trial(
        self,
        trial_path: Path,
        *,
        valid: bool,
        attribution: str,
    ) -> Path:
        """Append the one authoritative terminal link to a final trial."""

        if self.terminal_written:
            raise RuntimeError("attempt already has a terminal event")
        resolved_trial = trial_path.resolve()
        try:
            relative = resolved_trial.relative_to(self.data_root)
        except ValueError as exc:
            raise ValueError(
                f"trial record is outside attempt data root: {trial_path}"
            ) from exc
        result = {
            "status": "trial_recorded",
            "valid": valid,
            "attribution": attribution,
            "trial_record": relative.as_posix(),
            "trial_record_sha256": sha256_file(resolved_trial),
        }
        path = self._append(3, "trial_recorded", result=result)
        self.terminal_written = True
        return path

    def finalize_infrastructure_failure(
        self,
        *,
        stage: str,
        error: BaseException,
    ) -> Path:
        """Append a terminal invalid result, classified by launch boundary."""

        if self.terminal_written:
            raise RuntimeError("attempt already has a terminal event")
        if self.invocation_observed:
            attribution = POST_INVOCATION_INFRASTRUCTURE_FAILURE
        elif self.launch_committed:
            attribution = INVOCATION_START_UNKNOWN_INFRASTRUCTURE_FAILURE
        else:
            attribution = PRE_INVOCATION_INFRASTRUCTURE_FAILURE
        result = {
            "status": "infrastructure_failure",
            "valid": False,
            "attribution": attribution,
            "stage": stage,
            "error_type": type(error).__name__,
            "error": "".join(
                traceback.format_exception(type(error), error, error.__traceback__)
            ),
        }
        path = self._append(3, "infrastructure_failure", result=result)
        self.terminal_written = True
        return path
