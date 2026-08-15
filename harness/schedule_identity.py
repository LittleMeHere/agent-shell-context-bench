"""Tamper-evident identity for one scheduled collection cell.

The scheduler passes this token across the child-process boundary.  The child
validates it against the requested coordinates and the task bytes before it
constructs an agent adapter, and every attempt event and final trial carries
the same identity.  The digest is not an authentication secret; it makes
accidental edits, argument corruption, and copied/mismatched artifacts
detectable while the plan digest binds the identity to the immutable plan.
"""

from __future__ import annotations

import base64
import hashlib
import json
import re
import secrets
from dataclasses import dataclass
from typing import Any, Mapping


SCHEDULE_IDENTITY_SCHEMA_VERSION = "1.2.0"


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


def _digest(payload: Mapping[str, object]) -> str:
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ScheduleIdentity:
    schema_version: str
    phase: str
    plan_digest: str
    cell_id: str
    config_id: str
    task_sha256: str
    family_id: str
    instance_id: str
    instance_sha256: str
    trial_schema_version: str
    target_valid_trials: int
    task_id: str
    agent_id: str
    model_id: str
    env_id: str
    phrasing: str
    expected_cli_version: str
    valid_slot_index: int | None
    token_sha256: str

    def payload(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "phase": self.phase,
            "plan_digest": self.plan_digest,
            "cell_id": self.cell_id,
            "config_id": self.config_id,
            "task_sha256": self.task_sha256,
            "family_id": self.family_id,
            "instance_id": self.instance_id,
            "instance_sha256": self.instance_sha256,
            "trial_schema_version": self.trial_schema_version,
            "target_valid_trials": self.target_valid_trials,
            "task_id": self.task_id,
            "agent_id": self.agent_id,
            "model_id": self.model_id,
            "env_id": self.env_id,
            "phrasing": self.phrasing,
            "expected_cli_version": self.expected_cli_version,
            "valid_slot_index": self.valid_slot_index,
        }

    def as_dict(self) -> dict[str, object]:
        return {**self.payload(), "token_sha256": self.token_sha256}

    @classmethod
    def create(
        cls,
        *,
        phase: str,
        plan_digest: str,
        cell_id: str,
        config_id: str,
        task_sha256: str,
        family_id: str | None = None,
        instance_id: str | None = None,
        instance_sha256: str | None = None,
        trial_schema_version: str,
        target_valid_trials: int,
        task_id: str,
        agent_id: str,
        model_id: str,
        env_id: str,
        phrasing: str,
        expected_cli_version: str,
        valid_slot_index: int | None = None,
    ) -> "ScheduleIdentity":
        resolved_family = task_id if family_id is None else family_id
        resolved_instance = "fixed" if instance_id is None else instance_id
        resolved_instance_sha = (
            task_sha256 if instance_sha256 is None else instance_sha256
        )
        payload: dict[str, object] = {
            "schema_version": SCHEDULE_IDENTITY_SCHEMA_VERSION,
            "phase": phase,
            "plan_digest": plan_digest,
            "cell_id": cell_id,
            "config_id": config_id,
            "task_sha256": task_sha256,
            "family_id": resolved_family,
            "instance_id": resolved_instance,
            "instance_sha256": resolved_instance_sha,
            "trial_schema_version": trial_schema_version,
            "target_valid_trials": target_valid_trials,
            "task_id": task_id,
            "agent_id": agent_id,
            "model_id": model_id,
            "env_id": env_id,
            "phrasing": phrasing,
            "expected_cli_version": expected_cli_version,
            "valid_slot_index": valid_slot_index,
        }
        return cls.from_dict({**payload, "token_sha256": _digest(payload)})

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "ScheduleIdentity":
        expected_fields = {
            "schema_version",
            "phase",
            "plan_digest",
            "cell_id",
            "config_id",
            "task_sha256",
            "family_id",
            "instance_id",
            "instance_sha256",
            "trial_schema_version",
            "target_valid_trials",
            "task_id",
            "agent_id",
            "model_id",
            "env_id",
            "phrasing",
            "expected_cli_version",
            "valid_slot_index",
            "token_sha256",
        }
        if set(raw) != expected_fields:
            missing = sorted(expected_fields - set(raw))
            unknown = sorted(set(raw) - expected_fields)
            raise ValueError(
                "schedule identity has unknown or missing fields: "
                f"missing={missing}, unknown={unknown}"
            )
        text_fields = expected_fields - {
            "target_valid_trials",
            "valid_slot_index",
        }
        if any(not isinstance(raw[field], str) for field in text_fields):
            raise ValueError("schedule identity text fields must be strings")
        identity = cls(**{field: raw[field] for field in expected_fields})
        identity.validate_integrity()
        return identity

    def validate_integrity(self) -> None:
        if self.schema_version != SCHEDULE_IDENTITY_SCHEMA_VERSION:
            raise ValueError(
                "unsupported schedule identity schema "
                f"{self.schema_version!r}"
            )
        for name in (
            "phase",
            "config_id",
            "trial_schema_version",
            "task_id",
            "family_id",
            "instance_id",
            "agent_id",
            "model_id",
            "env_id",
            "phrasing",
            "expected_cli_version",
        ):
            if not getattr(self, name).strip():
                raise ValueError(f"schedule identity {name} must be non-empty")
        for name, length in (
            ("plan_digest", 64),
            ("cell_id", 16),
            ("task_sha256", 64),
            ("instance_sha256", 64),
            ("token_sha256", 64),
        ):
            value = getattr(self, name)
            if re.fullmatch(rf"[0-9a-f]{{{length}}}", value) is None:
                raise ValueError(
                    f"schedule identity {name} must be {length} lowercase hex"
                )
        if (
            not isinstance(self.target_valid_trials, int)
            or isinstance(self.target_valid_trials, bool)
            or self.target_valid_trials < 1
        ):
            raise ValueError(
                "schedule identity target_valid_trials must be a positive integer"
            )
        if self.valid_slot_index is not None and (
            isinstance(self.valid_slot_index, bool)
            or not isinstance(self.valid_slot_index, int)
            or self.valid_slot_index < 0
            or self.valid_slot_index >= self.target_valid_trials
        ):
            raise ValueError(
                "schedule identity valid_slot_index must be null or lie within N"
            )
        expected = _digest(self.payload())
        if not secrets.compare_digest(self.token_sha256, expected):
            raise ValueError("schedule identity token digest mismatch")

    def encode_token(self) -> str:
        encoded = base64.urlsafe_b64encode(
            _canonical_json(self.as_dict()).encode("utf-8")
        ).decode("ascii")
        return encoded.rstrip("=")

    @classmethod
    def decode_token(cls, token: str) -> "ScheduleIdentity":
        if not isinstance(token, str) or not token:
            raise ValueError("schedule token must be a non-empty string")
        try:
            padded = token + "=" * (-len(token) % 4)
            decoded = base64.b64decode(
                padded,
                altchars=b"-_",
                validate=True,
            )
            raw = json.loads(decoded.decode("utf-8"))
        except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("schedule token is not valid base64url JSON") from exc
        if not isinstance(raw, dict):
            raise ValueError("schedule token payload must be a JSON object")
        return cls.from_dict(raw)

    def validate_run(
        self,
        *,
        task_id: str,
        agent_id: str,
        model_id: str,
        env_id: str,
        phrasing: str,
        task_sha256: str,
        family_id: str,
        instance_id: str,
        instance_sha256: str,
        trial_schema_version: str,
        expected_cli_version: str | None,
        valid_slot_index: int | None,
    ) -> None:
        self.validate_integrity()
        expected: dict[str, object] = {
            "task_id": task_id,
            "agent_id": agent_id,
            "model_id": model_id,
            "env_id": env_id,
            "phrasing": phrasing,
            "task_sha256": task_sha256,
            "family_id": family_id,
            "instance_id": instance_id,
            "instance_sha256": instance_sha256,
            "trial_schema_version": trial_schema_version,
            "expected_cli_version": expected_cli_version,
            "valid_slot_index": valid_slot_index,
        }
        for field, value in expected.items():
            if getattr(self, field) != value:
                raise ValueError(
                    f"schedule identity {field}={getattr(self, field)!r}, "
                    f"requested {value!r}"
                )
