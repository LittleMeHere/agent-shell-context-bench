"""Immutable R-006 sizing-lock records.

The lock is deliberately about provenance, not statistical policy.  It binds
the already-selected sizing inputs and result so the scheduler cannot accept a
manually copied confirmatory N.  Selection of those inputs remains outside this
module and must follow the accepted pre-data methodology.
"""

from __future__ import annotations

import hashlib
import json
import math
import base64
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)


SIZING_LOCK_SCHEMA_VERSION = "1.1.0"
SIZING_LOCK_PHASE = "confirmatory-sizing"
SOURCE_PHASE = "pilot"


class SizingLockError(RuntimeError):
    """A malformed, inconsistent, or tampered sizing lock."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")


def canonical_json(value: object) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


def digest_payload(value: object) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _require_hex(value: object, *, field: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise SizingLockError(f"{field} must be a lowercase SHA-256 hex digest")
    return value


def _require_positive_number(value: object, *, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SizingLockError(f"{field} must be a positive finite number")
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise SizingLockError(f"{field} must be a positive finite number")
    return number


def _require_positive_int(value: object, *, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise SizingLockError(f"{field} must be a positive integer")
    return value


@dataclass(frozen=True)
class SizingLock:
    schema_version: str
    created_at: str
    phase: str
    source_phase: str
    source_plan_digest: str
    source_plan_schema_version: str
    source_trial_schema_version: str
    blinded_input_sha256: str
    blinded_export_digest: str
    source_manifest_digest: str
    commitment_digest: str
    commitment_artifact_sha256: str
    commitment_public_key_b64: str
    code_version: str
    code_artifacts: Mapping[str, str]
    analysis_version: str
    analysis_artifact_sha256: str
    simulation_config_version: str
    simulation_config_sha256: str
    task_class: str
    compute_budget: float
    per_trial_cost: float
    n_cells: int
    cap_per_cell: int
    result: Mapping[str, Any]
    result_digest: str
    digest: str
    signature_b64: str

    @property
    def n_per_cell(self) -> int:
        value = self.result.get("n_per_cell")
        return _require_positive_int(value, field="result.n_per_cell")

    def payload(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "created_at": self.created_at,
            "phase": self.phase,
            "source_phase": self.source_phase,
            "source_plan_digest": self.source_plan_digest,
            "source_plan_schema_version": self.source_plan_schema_version,
            "source_trial_schema_version": self.source_trial_schema_version,
            "blinded_input_sha256": self.blinded_input_sha256,
            "blinded_export_digest": self.blinded_export_digest,
            "source_manifest_digest": self.source_manifest_digest,
            "commitment_digest": self.commitment_digest,
            "commitment_artifact_sha256": self.commitment_artifact_sha256,
            "commitment_public_key_b64": self.commitment_public_key_b64,
            "code_version": self.code_version,
            "code_artifacts": dict(self.code_artifacts),
            "analysis_version": self.analysis_version,
            "analysis_artifact_sha256": self.analysis_artifact_sha256,
            "simulation_config_version": self.simulation_config_version,
            "simulation_config_sha256": self.simulation_config_sha256,
            "task_class": self.task_class,
            "compute_budget": self.compute_budget,
            "per_trial_cost": self.per_trial_cost,
            "n_cells": self.n_cells,
            "cap_per_cell": self.cap_per_cell,
            "result": dict(self.result),
            "result_digest": self.result_digest,
        }

    def as_dict(self) -> dict[str, object]:
        return {
            **self.payload(),
            "digest": self.digest,
            "signature_b64": self.signature_b64,
        }

    def signed_bytes(self) -> bytes:
        return canonical_json({**self.payload(), "digest": self.digest}).encode("utf-8")

    def validate(self) -> None:
        if self.schema_version != SIZING_LOCK_SCHEMA_VERSION:
            raise SizingLockError(
                f"unsupported sizing-lock schema {self.schema_version!r}"
            )
        if self.phase != SIZING_LOCK_PHASE or self.source_phase != SOURCE_PHASE:
            raise SizingLockError("sizing lock has the wrong source or target phase")
        if not isinstance(self.created_at, str) or not self.created_at:
            raise SizingLockError("created_at must be a non-empty string")
        for field in (
            "source_plan_digest",
            "blinded_input_sha256",
            "blinded_export_digest",
            "source_manifest_digest",
            "commitment_digest",
            "commitment_artifact_sha256",
            "analysis_artifact_sha256",
            "simulation_config_sha256",
            "result_digest",
            "digest",
        ):
            _require_hex(getattr(self, field), field=field)
        if not isinstance(self.commitment_public_key_b64, str):
            raise SizingLockError("commitment_public_key_b64 must be a string")
        if not isinstance(self.signature_b64, str):
            raise SizingLockError("signature_b64 must be a string")
        try:
            public_key_bytes = base64.b64decode(
                self.commitment_public_key_b64, validate=True
            )
            signature = base64.b64decode(self.signature_b64, validate=True)
            if len(public_key_bytes) != 32 or len(signature) != 64:
                raise ValueError("wrong Ed25519 field length")
            Ed25519PublicKey.from_public_bytes(public_key_bytes).verify(
                signature, self.signed_bytes()
            )
        except (ValueError, InvalidSignature) as exc:
            raise SizingLockError(
                "sizing-lock custodian signature verification failed"
            ) from exc
        if not self.source_plan_schema_version or not self.source_trial_schema_version:
            raise SizingLockError("source schema versions must be non-empty")
        if not self.code_version or not self.analysis_version:
            raise SizingLockError("code and analysis versions must be non-empty")
        if not self.simulation_config_version:
            raise SizingLockError("simulation_config_version must be non-empty")
        if not isinstance(self.code_artifacts, Mapping) or not self.code_artifacts:
            raise SizingLockError("code_artifacts must be a non-empty mapping")
        required_code_artifacts = {
            "scripts/create_sizing_lock.py",
            "scripts/size_from_pilot.py",
            "harness/blinding.py",
            "harness/sizing_lock.py",
        }
        if not required_code_artifacts.issubset(self.code_artifacts):
            raise SizingLockError("code_artifacts omit required sizing-path files")
        for name, value in self.code_artifacts.items():
            if not isinstance(name, str) or not name or Path(name).is_absolute():
                raise SizingLockError("code artifact names must be relative strings")
            _require_hex(value, field=f"code_artifacts[{name!r}]")
        budget = _require_positive_number(self.compute_budget, field="compute_budget")
        cost = _require_positive_number(self.per_trial_cost, field="per_trial_cost")
        n_cells = _require_positive_int(self.n_cells, field="n_cells")
        if isinstance(self.cap_per_cell, bool) or not isinstance(self.cap_per_cell, int):
            raise SizingLockError("cap_per_cell must be a non-negative integer")
        expected_cap = int(math.floor((budget / cost) / n_cells))
        if self.cap_per_cell != expected_cap or self.cap_per_cell < 0:
            raise SizingLockError("cap_per_cell does not match authoritative budget inputs")
        if not isinstance(self.result, Mapping):
            raise SizingLockError("result must be a JSON object")
        self.n_per_cell
        if self.result.get("mode") != "pilot":
            raise SizingLockError("sizing result must come from pilot mode")
        if self.result.get("task_class") != self.task_class:
            raise SizingLockError("result task_class does not match sizing-lock input")
        if self.result.get("cap_per_cell") != self.cap_per_cell:
            raise SizingLockError("result cap_per_cell does not match the budget lock")
        if self.n_per_cell > self.cap_per_cell:
            raise SizingLockError("result.n_per_cell exceeds the authoritative cap")
        constants = self.result.get("constants")
        if not isinstance(constants, Mapping) or not constants:
            raise SizingLockError("sizing result must bind non-empty constants")
        _require_positive_int(
            self.result.get("n_trials_after_filter"),
            field="result.n_trials_after_filter",
        )
        if self.result_digest != digest_payload(dict(self.result)):
            raise SizingLockError("sizing result digest mismatch")
        if self.digest != digest_payload(self.payload()):
            raise SizingLockError("sizing-lock digest mismatch")


_FIELDS = {
    "schema_version",
    "created_at",
    "phase",
    "source_phase",
    "source_plan_digest",
    "source_plan_schema_version",
    "source_trial_schema_version",
    "blinded_input_sha256",
    "blinded_export_digest",
    "source_manifest_digest",
    "commitment_digest",
    "commitment_artifact_sha256",
    "commitment_public_key_b64",
    "code_version",
    "code_artifacts",
    "analysis_version",
    "analysis_artifact_sha256",
    "simulation_config_version",
    "simulation_config_sha256",
    "task_class",
    "compute_budget",
    "per_trial_cost",
    "n_cells",
    "cap_per_cell",
    "result",
    "result_digest",
    "digest",
    "signature_b64",
}


def sizing_lock_from_dict(raw: object) -> SizingLock:
    if not isinstance(raw, dict) or set(raw) != _FIELDS:
        raise SizingLockError("sizing lock has unknown or missing fields")
    try:
        lock = SizingLock(**raw)
    except (TypeError, ValueError) as exc:
        raise SizingLockError(f"malformed sizing lock: {exc}") from exc
    lock.validate()
    return lock


def build_sizing_lock(
    *,
    source_plan_digest: str,
    source_plan_schema_version: str,
    source_trial_schema_version: str,
    blinded_input_sha256: str,
    blinded_export_digest: str,
    source_manifest_digest: str,
    commitment_digest: str,
    commitment_artifact_sha256: str,
    commitment_public_key_b64: str,
    signing_key: Ed25519PrivateKey,
    code_version: str,
    code_artifacts: Mapping[str, str],
    analysis_version: str,
    analysis_artifact_sha256: str,
    simulation_config_version: str,
    simulation_config_sha256: str,
    task_class: str,
    compute_budget: float,
    per_trial_cost: float,
    n_cells: int,
    cap_per_cell: int,
    result: Mapping[str, Any],
    created_at: str | None = None,
) -> SizingLock:
    provisional = SizingLock(
        schema_version=SIZING_LOCK_SCHEMA_VERSION,
        created_at=created_at or _utc_now(),
        phase=SIZING_LOCK_PHASE,
        source_phase=SOURCE_PHASE,
        source_plan_digest=source_plan_digest,
        source_plan_schema_version=source_plan_schema_version,
        source_trial_schema_version=source_trial_schema_version,
        blinded_input_sha256=blinded_input_sha256,
        blinded_export_digest=blinded_export_digest,
        source_manifest_digest=source_manifest_digest,
        commitment_digest=commitment_digest,
        commitment_artifact_sha256=commitment_artifact_sha256,
        commitment_public_key_b64=commitment_public_key_b64,
        code_version=code_version,
        code_artifacts=dict(code_artifacts),
        analysis_version=analysis_version,
        analysis_artifact_sha256=analysis_artifact_sha256,
        simulation_config_version=simulation_config_version,
        simulation_config_sha256=simulation_config_sha256,
        task_class=task_class,
        compute_budget=compute_budget,
        per_trial_cost=per_trial_cost,
        n_cells=n_cells,
        cap_per_cell=cap_per_cell,
        result=dict(result),
        result_digest=digest_payload(dict(result)),
        digest="",
        signature_b64="",
    )
    digest = digest_payload(provisional.payload())
    signed_bytes = canonical_json({**provisional.payload(), "digest": digest}).encode(
        "utf-8"
    )
    signature_b64 = base64.b64encode(signing_key.sign(signed_bytes)).decode("ascii")
    observed_public_key = base64.b64encode(
        signing_key.public_key().public_bytes(
            serialization.Encoding.Raw,
            serialization.PublicFormat.Raw,
        )
    ).decode("ascii")
    if observed_public_key != commitment_public_key_b64:
        raise SizingLockError("signing key does not match the committed public key")
    lock = SizingLock(
        **{
            **provisional.__dict__,
            "digest": digest,
            "signature_b64": signature_b64,
        }
    )
    lock.validate()
    return lock


def load_sizing_lock(path: Path) -> SizingLock:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SizingLockError(f"cannot read sizing lock {path}: {exc}") from exc
    return sizing_lock_from_dict(raw)


def validate_commitment_anchor(
    lock: SizingLock,
    *,
    commitment_digest: str,
    commitment_artifact_sha256: str,
    commitment_public_key_b64: str,
) -> None:
    """Bind a signed lock to the independently anchored R-005 commitment."""
    lock.validate()
    if (
        lock.commitment_digest != commitment_digest
        or lock.commitment_artifact_sha256 != commitment_artifact_sha256
        or lock.commitment_public_key_b64 != commitment_public_key_b64
    ):
        raise SizingLockError(
            "sizing lock does not match the independently anchored commitment"
        )


def write_sizing_lock(lock: SizingLock, path: Path) -> None:
    lock.validate()
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("x", encoding="utf-8", newline="\n") as handle:
            json.dump(lock.as_dict(), handle, indent=2, ensure_ascii=False)
            handle.write("\n")
    except FileExistsError as exc:
        raise SizingLockError(f"refusing to overwrite sizing lock: {path}") from exc
