"""Signed prospective V2 design and post-pilot release records.

Unlike the historical sizing lock, this boundary never estimates N from pilot
outcomes.  The pre-data lock fixes base N=36 and the exact derived roster.  A
later custodian-signed release may authorize confirmatory planning only when
the plan-bound aggregate pilot gate says ``proceed``.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)


DESIGN_LOCK_SCHEMA_VERSION = "1.0.0"
PILOT_RELEASE_SCHEMA_VERSION = "1.0.0"
V2_BASE_N = 36
V2_CAPABILITY_REPETITIONS_PER_FAMILY = 15
V2_CAPABILITY_REPETITIONS_PER_INSTANCE = 5
V2_SEEDED_REPETITIONS = 36
V2_CONFIRMATORY_CELLS = 1890
V2_CONFIRMATORY_VALID_SLOTS = 28980
V2_CONFIRMATORY_EPOCH_BOUNDARIES = (7245, 14490, 21735, 28980)
PROVIDER_CAP_SCHEMA_VERSION = "1.0.0"
EXPECTED_PROVIDER_IDS = {
    "anthropic_subscription",
    "openai_subscription",
    "antigravity_subscription",
}


class V2DesignLockError(RuntimeError):
    """A malformed, inconsistent, or tampered prospective V2 artifact."""


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")


def _require_sha(value: object, *, field: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise V2DesignLockError(f"{field} must be a lowercase SHA-256 digest")
    return value


def _verify_signature(public_key_b64: str, signature_b64: str, message: bytes) -> None:
    try:
        public = base64.b64decode(public_key_b64, validate=True)
        signature = base64.b64decode(signature_b64, validate=True)
        if len(public) != 32 or len(signature) != 64:
            raise ValueError("wrong Ed25519 field length")
        Ed25519PublicKey.from_public_bytes(public).verify(signature, message)
    except (TypeError, ValueError, InvalidSignature) as exc:
        raise V2DesignLockError("custodian signature verification failed") from exc


def _public_key_b64(signing_key: Ed25519PrivateKey) -> str:
    return base64.b64encode(
        signing_key.public_key().public_bytes(
            serialization.Encoding.Raw,
            serialization.PublicFormat.Raw,
        )
    ).decode("ascii")


def validate_provider_cap_authorization(raw: object) -> str:
    """Validate private 60/10/30 capacity evidence and return its digest.

    Workload units are intentionally provider-specific; this schema does not
    pretend raw calls are comparable across subscription meters.
    """

    required = {
        "schema_version", "purpose", "as_of_date", "n36_supported",
        "calendar_days_cap", "human_audit_hours_cap", "providers",
        "inter_trial_delay_seconds", "artifact_digest",
    }
    if not isinstance(raw, Mapping) or set(raw) != required:
        raise V2DesignLockError("provider-cap authorization has unknown or missing fields")
    payload = {key: raw[key] for key in required - {"artifact_digest"}}
    if raw["artifact_digest"] != _digest(payload):
        raise V2DesignLockError("provider-cap authorization digest mismatch")
    if (
        raw["schema_version"] != PROVIDER_CAP_SCHEMA_VERSION
        or raw["purpose"] != "v2_n36_provider_calendar_authorization"
        or raw["n36_supported"] is not True
        or not isinstance(raw["as_of_date"], str)
        or not raw["as_of_date"]
    ):
        raise V2DesignLockError("provider-cap authorization does not approve N=36")
    for field in ("calendar_days_cap", "human_audit_hours_cap"):
        value = raw[field]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
            raise V2DesignLockError(f"provider-cap {field} must be positive")
    if not 18.33 <= float(raw["human_audit_hours_cap"]) <= 24.0:
        raise V2DesignLockError("human audit cap must support 200 labels within 24 hours")
    providers = raw["providers"]
    if not isinstance(providers, Mapping) or set(providers) != EXPECTED_PROVIDER_IDS:
        raise V2DesignLockError("provider-cap roster must contain the three subscription surfaces")
    provider_fields = {
        "window_unit", "total_window_units", "planned_units", "retry_units",
        "untouched_units", "n36_required_units",
    }
    for provider_id, record in providers.items():
        if not isinstance(record, Mapping) or set(record) != provider_fields:
            raise V2DesignLockError(f"{provider_id} cap record is malformed")
        if not isinstance(record["window_unit"], str) or not record["window_unit"]:
            raise V2DesignLockError(f"{provider_id} window_unit must be non-empty")
        values = []
        for field in provider_fields - {"window_unit"}:
            value = record[field]
            if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
                raise V2DesignLockError(f"{provider_id}.{field} must be positive")
            values.append(float(value))
        total = float(record["total_window_units"])
        planned = float(record["planned_units"])
        retry = float(record["retry_units"])
        untouched = float(record["untouched_units"])
        tolerance = max(1e-9, total * 1e-9)
        if (
            abs(planned - 0.60 * total) > tolerance
            or abs(retry - 0.10 * total) > tolerance
            or abs(untouched - 0.30 * total) > tolerance
            or abs(planned + retry + untouched - total) > tolerance
        ):
            raise V2DesignLockError(f"{provider_id} does not implement the accepted 60/10/30 split")
        if float(record["n36_required_units"]) > planned:
            raise V2DesignLockError(f"{provider_id} planned envelope cannot support N=36")
    delays = raw["inter_trial_delay_seconds"]
    if not isinstance(delays, Mapping) or set(delays) != {"claude_code", "codex", "agy"}:
        raise V2DesignLockError("provider-cap delays require all three agents")
    if any(
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or value < 0
        for value in delays.values()
    ):
        raise V2DesignLockError("inter-trial delays must be nonnegative numbers")
    return str(raw["artifact_digest"])


def build_provider_cap_authorization(
    *,
    as_of_date: str,
    calendar_days_cap: float,
    human_audit_hours_cap: float,
    providers: Mapping[str, Mapping[str, object]],
    inter_trial_delay_seconds: Mapping[str, float],
) -> dict[str, object]:
    """Create a strict private cap artifact, deriving the 60/10/30 split."""

    if not isinstance(providers, Mapping) or set(providers) != EXPECTED_PROVIDER_IDS:
        raise V2DesignLockError("provider inputs require all three subscription surfaces")
    records: dict[str, dict[str, object]] = {}
    for provider_id, source in providers.items():
        if not isinstance(source, Mapping) or set(source) != {
            "window_unit", "total_window_units", "n36_required_units"
        }:
            raise V2DesignLockError(f"{provider_id} input is malformed")
        total = source["total_window_units"]
        if isinstance(total, bool) or not isinstance(total, (int, float)) or total <= 0:
            raise V2DesignLockError(f"{provider_id}.total_window_units must be positive")
        records[provider_id] = {
            "window_unit": source["window_unit"],
            "total_window_units": float(total),
            "planned_units": 0.60 * float(total),
            "retry_units": 0.10 * float(total),
            "untouched_units": 0.30 * float(total),
            "n36_required_units": source["n36_required_units"],
        }
    payload: dict[str, object] = {
        "schema_version": PROVIDER_CAP_SCHEMA_VERSION,
        "purpose": "v2_n36_provider_calendar_authorization",
        "as_of_date": as_of_date,
        "n36_supported": True,
        "calendar_days_cap": calendar_days_cap,
        "human_audit_hours_cap": human_audit_hours_cap,
        "providers": records,
        "inter_trial_delay_seconds": dict(inter_trial_delay_seconds),
    }
    artifact = {**payload, "artifact_digest": _digest(payload)}
    validate_provider_cap_authorization(artifact)
    return artifact


def write_provider_cap_authorization(
    artifact: Mapping[str, object], path: Path
) -> None:
    validate_provider_cap_authorization(artifact)
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("x", encoding="utf-8", newline="\n") as handle:
            json.dump(dict(artifact), handle, indent=2, ensure_ascii=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
    except FileExistsError as exc:
        raise V2DesignLockError(
            f"refusing to overwrite provider-cap authorization: {path}"
        ) from exc


@dataclass(frozen=True)
class V2DesignLock:
    schema_version: str
    created_at: str
    phase: str
    base_n: int
    capability_repetitions_per_family: int
    capability_repetitions_per_instance: int
    seeded_repetitions: int
    confirmatory_cells: int
    confirmatory_valid_slots: int
    epoch_boundaries: tuple[int, ...]
    pilot_plan_digest: str
    runtime_matrix_digest: str
    task_bank_digest: str
    analysis_artifact_sha256: str
    simulation_artifact_sha256: str
    provider_cap_artifact_sha256: str
    provider_cap_confirmed: bool
    order_seed: int
    commitment_digest: str
    commitment_artifact_sha256: str
    custodian_public_key_b64: str
    digest: str
    signature_b64: str

    def payload(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "created_at": self.created_at,
            "phase": self.phase,
            "base_n": self.base_n,
            "capability_repetitions_per_family": self.capability_repetitions_per_family,
            "capability_repetitions_per_instance": self.capability_repetitions_per_instance,
            "seeded_repetitions": self.seeded_repetitions,
            "confirmatory_cells": self.confirmatory_cells,
            "confirmatory_valid_slots": self.confirmatory_valid_slots,
            "epoch_boundaries": list(self.epoch_boundaries),
            "pilot_plan_digest": self.pilot_plan_digest,
            "runtime_matrix_digest": self.runtime_matrix_digest,
            "task_bank_digest": self.task_bank_digest,
            "analysis_artifact_sha256": self.analysis_artifact_sha256,
            "simulation_artifact_sha256": self.simulation_artifact_sha256,
            "provider_cap_artifact_sha256": self.provider_cap_artifact_sha256,
            "provider_cap_confirmed": self.provider_cap_confirmed,
            "order_seed": self.order_seed,
            "commitment_digest": self.commitment_digest,
            "commitment_artifact_sha256": self.commitment_artifact_sha256,
            "custodian_public_key_b64": self.custodian_public_key_b64,
        }

    def as_dict(self) -> dict[str, object]:
        return {**self.payload(), "digest": self.digest, "signature_b64": self.signature_b64}

    def signed_bytes(self) -> bytes:
        return _canonical_json({**self.payload(), "digest": self.digest}).encode("utf-8")

    def validate(self) -> None:
        if self.schema_version != DESIGN_LOCK_SCHEMA_VERSION or self.phase != "v2-confirmatory":
            raise V2DesignLockError("design lock has the wrong schema or phase")
        if not isinstance(self.created_at, str) or not self.created_at:
            raise V2DesignLockError("created_at must be non-empty")
        expected = (
            V2_BASE_N,
            V2_CAPABILITY_REPETITIONS_PER_FAMILY,
            V2_CAPABILITY_REPETITIONS_PER_INSTANCE,
            V2_SEEDED_REPETITIONS,
            V2_CONFIRMATORY_CELLS,
            V2_CONFIRMATORY_VALID_SLOTS,
        )
        observed = (
            self.base_n,
            self.capability_repetitions_per_family,
            self.capability_repetitions_per_instance,
            self.seeded_repetitions,
            self.confirmatory_cells,
            self.confirmatory_valid_slots,
        )
        if observed != expected or self.epoch_boundaries != V2_CONFIRMATORY_EPOCH_BOUNDARIES:
            raise V2DesignLockError("design lock differs from the accepted N=36 roster")
        if self.provider_cap_confirmed is not True:
            raise V2DesignLockError("N=36 requires prospective provider-cap confirmation")
        if isinstance(self.order_seed, bool) or not isinstance(self.order_seed, int):
            raise V2DesignLockError("order_seed must be an integer")
        for field in (
            "pilot_plan_digest", "runtime_matrix_digest", "task_bank_digest",
            "analysis_artifact_sha256", "simulation_artifact_sha256",
            "provider_cap_artifact_sha256", "digest",
            "commitment_digest", "commitment_artifact_sha256",
        ):
            _require_sha(getattr(self, field), field=field)
        if self.digest != _digest(self.payload()):
            raise V2DesignLockError("design-lock digest mismatch")
        _verify_signature(self.custodian_public_key_b64, self.signature_b64, self.signed_bytes())


@dataclass(frozen=True)
class V2PilotRelease:
    schema_version: str
    created_at: str
    phase: str
    design_lock_digest: str
    pilot_plan_digest: str
    pilot_gate_artifact_digest: str
    analysis_manifest_digest: str
    branch: str
    confirmatory_collection_allowed: bool
    custodian_public_key_b64: str
    digest: str
    signature_b64: str

    def payload(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "created_at": self.created_at,
            "phase": self.phase,
            "design_lock_digest": self.design_lock_digest,
            "pilot_plan_digest": self.pilot_plan_digest,
            "pilot_gate_artifact_digest": self.pilot_gate_artifact_digest,
            "analysis_manifest_digest": self.analysis_manifest_digest,
            "branch": self.branch,
            "confirmatory_collection_allowed": self.confirmatory_collection_allowed,
            "custodian_public_key_b64": self.custodian_public_key_b64,
        }

    def as_dict(self) -> dict[str, object]:
        return {**self.payload(), "digest": self.digest, "signature_b64": self.signature_b64}

    def signed_bytes(self) -> bytes:
        return _canonical_json({**self.payload(), "digest": self.digest}).encode("utf-8")

    def validate(self, design_lock: V2DesignLock) -> None:
        design_lock.validate()
        if self.schema_version != PILOT_RELEASE_SCHEMA_VERSION or self.phase != "v2-pilot-release":
            raise V2DesignLockError("pilot release has the wrong schema or phase")
        if not isinstance(self.created_at, str) or not self.created_at:
            raise V2DesignLockError("release created_at must be non-empty")
        for field in (
            "design_lock_digest", "pilot_plan_digest", "pilot_gate_artifact_digest",
            "analysis_manifest_digest", "digest",
        ):
            _require_sha(getattr(self, field), field=field)
        if (
            self.design_lock_digest != design_lock.digest
            or self.pilot_plan_digest != design_lock.pilot_plan_digest
            or self.branch != "proceed"
            or self.confirmatory_collection_allowed is not True
            or self.custodian_public_key_b64 != design_lock.custodian_public_key_b64
        ):
            raise V2DesignLockError("pilot release does not authorize this fixed design")
        if self.digest != _digest(self.payload()):
            raise V2DesignLockError("pilot-release digest mismatch")
        _verify_signature(self.custodian_public_key_b64, self.signature_b64, self.signed_bytes())


def _signed(instance: object, signing_key: Ed25519PrivateKey):
    digest = _digest(instance.payload())
    signed_bytes = _canonical_json({**instance.payload(), "digest": digest}).encode("utf-8")
    return type(instance)(**{**instance.__dict__, "digest": digest, "signature_b64": base64.b64encode(signing_key.sign(signed_bytes)).decode("ascii")})


def build_v2_design_lock(*, signing_key: Ed25519PrivateKey, pilot_plan_digest: str,
                         runtime_matrix_digest: str, task_bank_digest: str,
                         analysis_artifact_sha256: str, simulation_artifact_sha256: str,
                         provider_cap_authorization: Mapping[str, object],
                         pilot_commitment_anchor: Mapping[str, str],
                         order_seed: int, created_at: str | None = None) -> V2DesignLock:
    provider_cap_artifact_sha256 = validate_provider_cap_authorization(
        provider_cap_authorization
    )
    if set(pilot_commitment_anchor) != {
        "commitment_digest", "commitment_artifact_sha256",
        "commitment_public_key_b64",
    }:
        raise V2DesignLockError("pilot commitment anchor has unknown or missing fields")
    if pilot_commitment_anchor["commitment_public_key_b64"] != _public_key_b64(signing_key):
        raise V2DesignLockError("design signing key differs from the pilot commitment")
    lock = V2DesignLock(
        DESIGN_LOCK_SCHEMA_VERSION, created_at or _utc_now(), "v2-confirmatory",
        V2_BASE_N, V2_CAPABILITY_REPETITIONS_PER_FAMILY,
        V2_CAPABILITY_REPETITIONS_PER_INSTANCE, V2_SEEDED_REPETITIONS,
        V2_CONFIRMATORY_CELLS, V2_CONFIRMATORY_VALID_SLOTS,
        V2_CONFIRMATORY_EPOCH_BOUNDARIES, pilot_plan_digest, runtime_matrix_digest,
        task_bank_digest, analysis_artifact_sha256, simulation_artifact_sha256,
        provider_cap_artifact_sha256, True, order_seed,
        pilot_commitment_anchor["commitment_digest"],
        pilot_commitment_anchor["commitment_artifact_sha256"],
        _public_key_b64(signing_key), "", "",
    )
    result = _signed(lock, signing_key)
    result.validate()
    return result


def validate_v2_commitment_anchor(
    design_lock: V2DesignLock, anchor: Mapping[str, str]
) -> None:
    """Require the separately supplied pre-pilot commitment at authorization."""

    design_lock.validate()
    if (
        anchor.get("commitment_digest") != design_lock.commitment_digest
        or anchor.get("commitment_artifact_sha256")
        != design_lock.commitment_artifact_sha256
        or anchor.get("commitment_public_key_b64")
        != design_lock.custodian_public_key_b64
    ):
        raise V2DesignLockError(
            "V2 design lock does not match the independently anchored pilot commitment"
        )


def build_v2_pilot_release(*, design_lock: V2DesignLock, signing_key: Ed25519PrivateKey,
                           pilot_gate_artifact: Mapping[str, object],
                           analysis_manifest_digest: str,
                           created_at: str | None = None) -> V2PilotRelease:
    design_lock.validate()
    gate = dict(pilot_gate_artifact)
    gate_digest = gate.pop("artifact_digest", None)
    expected_gate_fields = {
        "schema_version", "plan_digest", "analysis_manifest_digest",
        "capability_trials", "failures", "successes", "failing_families",
        "successful_families", "failing_domains", "successful_domains",
        "domain_concentration_diagnostic", "branch",
        "confirmatory_collection_allowed",
        "task_change_requires_amendment_and_fresh_pilot",
    }
    if set(gate) != expected_gate_fields or gate.get("schema_version") != "1.0.0":
        raise V2DesignLockError("pilot gate artifact has unknown or missing fields")
    if gate_digest != _digest(gate):
        raise V2DesignLockError("pilot gate artifact digest mismatch")
    if gate.get("plan_digest") != design_lock.pilot_plan_digest:
        raise V2DesignLockError("pilot gate uses a different pilot plan")
    integer_fields = {
        "capability_trials", "failures", "successes", "failing_families",
        "successful_families", "failing_domains", "successful_domains",
    }
    if any(
        isinstance(gate.get(field), bool)
        or not isinstance(gate.get(field), int)
        or gate.get(field) < 0
        for field in integer_fields
    ):
        raise V2DesignLockError("pilot gate count fields must be nonnegative integers")
    if (
        gate.get("analysis_manifest_digest") != analysis_manifest_digest
        or gate.get("capability_trials") != 360
        or gate.get("failures", -1) + gate.get("successes", -1) != 360
        or not 0 <= gate.get("failing_families") <= 12
        or not 0 <= gate.get("successful_families") <= 12
        or not 0 <= gate.get("failing_domains") <= 6
        or not 0 <= gate.get("successful_domains") <= 6
        or type(gate.get("domain_concentration_diagnostic")) is not bool
        or gate.get("branch") != "proceed"
        or gate.get("confirmatory_collection_allowed") is not True
        or gate.get("task_change_requires_amendment_and_fresh_pilot") is not False
    ):
        raise V2DesignLockError("pilot gate artifact does not authorize confirmation")
    release = V2PilotRelease(
        PILOT_RELEASE_SCHEMA_VERSION, created_at or _utc_now(), "v2-pilot-release",
        design_lock.digest, design_lock.pilot_plan_digest, str(gate_digest),
        analysis_manifest_digest, str(gate.get("branch")),
        gate.get("confirmatory_collection_allowed") is True,
        _public_key_b64(signing_key), "", "",
    )
    result = _signed(release, signing_key)
    result.validate(design_lock)
    return result


def _from_dict(raw: object, cls, fields: set[str]):
    if not isinstance(raw, dict) or set(raw) != fields:
        raise V2DesignLockError("artifact has unknown or missing fields")
    cooked = dict(raw)
    if "epoch_boundaries" in cooked:
        if not isinstance(cooked["epoch_boundaries"], list):
            raise V2DesignLockError("epoch_boundaries must be a list")
        cooked["epoch_boundaries"] = tuple(cooked["epoch_boundaries"])
    try:
        return cls(**cooked)
    except (TypeError, ValueError) as exc:
        raise V2DesignLockError(f"malformed V2 artifact: {exc}") from exc


_DESIGN_FIELDS = set(V2DesignLock.__dataclass_fields__)
_RELEASE_FIELDS = set(V2PilotRelease.__dataclass_fields__)


def v2_design_lock_from_dict(raw: object) -> V2DesignLock:
    lock = _from_dict(raw, V2DesignLock, _DESIGN_FIELDS)
    lock.validate()
    return lock


def v2_pilot_release_from_dict(raw: object, design_lock: V2DesignLock) -> V2PilotRelease:
    release = _from_dict(raw, V2PilotRelease, _RELEASE_FIELDS)
    release.validate(design_lock)
    return release


def load_v2_design_lock(path: Path) -> V2DesignLock:
    try:
        return v2_design_lock_from_dict(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError) as exc:
        raise V2DesignLockError(f"cannot read V2 design lock {path}: {exc}") from exc


def load_v2_pilot_release(path: Path, design_lock: V2DesignLock) -> V2PilotRelease:
    try:
        return v2_pilot_release_from_dict(json.loads(path.read_text(encoding="utf-8")), design_lock)
    except (OSError, json.JSONDecodeError) as exc:
        raise V2DesignLockError(f"cannot read V2 pilot release {path}: {exc}") from exc
