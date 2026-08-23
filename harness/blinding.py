"""Fail-closed pilot custody, blinding, and provenance export (R-005).

Before outcomes exist, preparation encrypts the mapping and Ed25519 signing
key and binds a public commitment into the pilot root. The signed export
contains no environment names or source paths: only sealed group labels,
public task/configuration coordinates, aggregate validity counts, and digests
that bind it to one stable snapshot of the immutable collection artifacts.
"""

from __future__ import annotations

import dataclasses
import base64
import hashlib
import json
import os
import random
import re
import secrets
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

from .scheduler import (
    ATTEMPT_DIR_NAME,
    BOUND_COMMITMENT_NAME,
    BOUND_PLAN_NAME,
    ENVIRONMENTS,
    LOCK_NAME,
    PILOT_PHASE,
    V2_PILOT_PHASE,
    Cell,
    ScheduleError,
    SchedulePlan,
    bind_output,
    load_plan,
    output_lock,
    scan_output,
    validate_output_binding,
)


MAPPING_SCHEMA_VERSION = "1.0.0"
COMMITMENT_SCHEMA_VERSION = "1.0.0"
CUSTODY_SCHEMA_VERSION = "1.0.0"
BLINDED_EXPORT_SCHEMA_VERSION = "1.1.0"
MAPPING_PURPOSE = "pilot_environment_blinding"
COMMITMENT_PURPOSE = "pilot_blinding_public_commitment"
CUSTODY_PURPOSE = "pilot_blinding_encrypted_custody"
EXPECTED_PILOT_CELLS = 230
EXPECTED_VALID_TRIALS = 460
EXPECTED_VALID_PER_CELL = 2
PILOT_PHASES = frozenset({PILOT_PHASE, V2_PILOT_PHASE})
# Export and collection deliberately share one atomic lock name. Separate lock
# files would leave a check-then-create race in which both processes start.
EXPORT_LOCK_NAME = LOCK_NAME


class BlindingError(RuntimeError):
    """A fail-closed mapping, source, or export validation error."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _digest(value: object) -> str:
    return _sha256_bytes(_canonical_json(value).encode("utf-8"))


def _b64encode(value: bytes) -> str:
    return base64.b64encode(value).decode("ascii")


def _b64decode(value: object, *, field: str) -> bytes:
    if not isinstance(value, str):
        raise BlindingError(f"{field} must be base64 text")
    try:
        return base64.b64decode(value, validate=True)
    except ValueError as exc:
        raise BlindingError(f"{field} is not valid base64") from exc


def _require_hex(value: object, *, field: str, length: int = 64) -> str:
    if not isinstance(value, str) or re.fullmatch(
        rf"[0-9a-f]{{{length}}}", value
    ) is None:
        raise BlindingError(f"{field} must be {length} lowercase hexadecimal characters")
    return value


def _write_json_exclusive(path: Path, payload: Mapping[str, object]) -> None:
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    try:
        with path.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
    except FileExistsError as exc:
        raise BlindingError(f"refusing to overwrite existing artifact: {path}") from exc


@dataclass(frozen=True)
class BlindingMapping:
    schema_version: str
    purpose: str
    created_at: str
    plan_digest: str
    environment_to_label: Mapping[str, str]
    mapping_digest: str

    def payload(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "purpose": self.purpose,
            "plan_digest": self.plan_digest,
            "environment_to_label": dict(self.environment_to_label),
        }

    def as_dict(self) -> dict[str, object]:
        return {
            **self.payload(),
            "created_at": self.created_at,
            "mapping_digest": self.mapping_digest,
        }

    def validate(self, *, plan_digest: str | None = None) -> None:
        if self.schema_version != MAPPING_SCHEMA_VERSION:
            raise BlindingError(
                f"unsupported mapping schema {self.schema_version!r}"
            )
        if self.purpose != MAPPING_PURPOSE:
            raise BlindingError(f"unexpected mapping purpose {self.purpose!r}")
        if not isinstance(self.created_at, str) or not self.created_at:
            raise BlindingError("mapping created_at must be non-empty text")
        _require_hex(self.plan_digest, field="mapping plan_digest")
        if plan_digest is not None and self.plan_digest != plan_digest:
            raise BlindingError("mapping is bound to a different pilot plan")
        mapping = dict(self.environment_to_label)
        if set(mapping) != set(ENVIRONMENTS):
            raise BlindingError("mapping environment roster is not exact")
        expected_labels = {f"E{i:02d}" for i in range(1, 6)}
        if set(mapping.values()) != expected_labels or len(mapping) != len(
            set(mapping.values())
        ):
            raise BlindingError("mapping labels must be a one-to-one E01-E05 roster")
        if self.mapping_digest != _digest(self.payload()):
            raise BlindingError("mapping digest mismatch")


def create_mapping(plan: SchedulePlan, *, rng: random.Random | None = None) -> BlindingMapping:
    """Create a plan-bound mapping without reading any collection outcomes."""
    if plan.phase not in PILOT_PHASES:
        raise BlindingError("a blinding mapping may be created only for a pilot plan")
    labels = [f"E{i:02d}" for i in range(1, 6)]
    (rng or random.SystemRandom()).shuffle(labels)
    provisional = BlindingMapping(
        schema_version=MAPPING_SCHEMA_VERSION,
        purpose=MAPPING_PURPOSE,
        created_at=_utc_now(),
        plan_digest=plan.digest,
        environment_to_label=dict(zip(ENVIRONMENTS, labels, strict=True)),
        mapping_digest="",
    )
    mapping = dataclasses.replace(
        provisional,
        mapping_digest=_digest(provisional.payload()),
    )
    mapping.validate(plan_digest=plan.digest)
    return mapping


@dataclass(frozen=True)
class BlindingCommitment:
    schema_version: str
    purpose: str
    created_at: str
    plan_digest: str
    mapping_digest: str
    public_key_b64: str
    commitment_digest: str

    def payload(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "purpose": self.purpose,
            "created_at": self.created_at,
            "plan_digest": self.plan_digest,
            "mapping_digest": self.mapping_digest,
            "public_key_b64": self.public_key_b64,
        }

    def as_dict(self) -> dict[str, object]:
        return {**self.payload(), "commitment_digest": self.commitment_digest}

    def validate(self, *, plan_digest: str | None = None) -> None:
        if self.schema_version != COMMITMENT_SCHEMA_VERSION:
            raise BlindingError("unsupported blinding commitment schema")
        if self.purpose != COMMITMENT_PURPOSE:
            raise BlindingError("unexpected blinding commitment purpose")
        if not isinstance(self.created_at, str) or not self.created_at:
            raise BlindingError("commitment created_at must be non-empty text")
        _require_hex(self.plan_digest, field="commitment plan_digest")
        _require_hex(self.mapping_digest, field="commitment mapping_digest")
        public_key = _b64decode(self.public_key_b64, field="public_key_b64")
        if len(public_key) != 32:
            raise BlindingError("Ed25519 public key must be 32 bytes")
        if plan_digest is not None and self.plan_digest != plan_digest:
            raise BlindingError("commitment is bound to a different pilot plan")
        if self.commitment_digest != _digest(self.payload()):
            raise BlindingError("blinding commitment digest mismatch")


def _commitment_from_raw(raw: object, *, plan_digest: str | None = None) -> BlindingCommitment:
    expected = {
        "schema_version",
        "purpose",
        "created_at",
        "plan_digest",
        "mapping_digest",
        "public_key_b64",
        "commitment_digest",
    }
    if not isinstance(raw, dict) or set(raw) != expected:
        raise BlindingError("commitment artifact has unknown or missing fields")
    commitment = BlindingCommitment(**raw)
    commitment.validate(plan_digest=plan_digest)
    return commitment


def load_commitment_bytes(
    raw_bytes: bytes, *, plan_digest: str | None = None
) -> tuple[BlindingCommitment, str]:
    try:
        raw = json.loads(raw_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BlindingError(f"cannot parse commitment artifact: {exc}") from exc
    return _commitment_from_raw(raw, plan_digest=plan_digest), _sha256_bytes(raw_bytes)


def load_commitment(path: Path, *, plan_digest: str | None = None) -> tuple[BlindingCommitment, str]:
    try:
        raw_bytes = path.read_bytes()
    except OSError as exc:
        raise BlindingError(f"cannot read commitment artifact {path}: {exc}") from exc
    return load_commitment_bytes(raw_bytes, plan_digest=plan_digest)


def _derive_custody_key(passphrase: str, salt: bytes) -> bytes:
    if not isinstance(passphrase, str) or len(passphrase) < 16:
        raise BlindingError("custody passphrase must contain at least 16 characters")
    return Scrypt(salt=salt, length=32, n=2**14, r=8, p=1).derive(
        passphrase.encode("utf-8")
    )


def create_custody_artifacts(
    plan: SchedulePlan,
    passphrase: str,
    *,
    rng: random.Random | None = None,
) -> tuple[BlindingCommitment, dict[str, object]]:
    """Create a public commitment and encrypted private custody artifact."""
    mapping = create_mapping(plan, rng=rng)
    private_key = Ed25519PrivateKey.generate()
    private_bytes = private_key.private_bytes(
        serialization.Encoding.Raw,
        serialization.PrivateFormat.Raw,
        serialization.NoEncryption(),
    )
    public_bytes = private_key.public_key().public_bytes(
        serialization.Encoding.Raw,
        serialization.PublicFormat.Raw,
    )
    provisional = BlindingCommitment(
        schema_version=COMMITMENT_SCHEMA_VERSION,
        purpose=COMMITMENT_PURPOSE,
        created_at=_utc_now(),
        plan_digest=plan.digest,
        mapping_digest=mapping.mapping_digest,
        public_key_b64=_b64encode(public_bytes),
        commitment_digest="",
    )
    commitment = dataclasses.replace(
        provisional,
        commitment_digest=_digest(provisional.payload()),
    )
    commitment.validate(plan_digest=plan.digest)
    plaintext = _canonical_json(
        {
            "mapping": mapping.as_dict(),
            "private_key_b64": _b64encode(private_bytes),
            "commitment_digest": commitment.commitment_digest,
        }
    ).encode("utf-8")
    salt = secrets.token_bytes(16)
    nonce = secrets.token_bytes(12)
    ciphertext = AESGCM(_derive_custody_key(passphrase, salt)).encrypt(
        nonce,
        plaintext,
        commitment.commitment_digest.encode("ascii"),
    )
    custody: dict[str, object] = {
        "schema_version": CUSTODY_SCHEMA_VERSION,
        "purpose": CUSTODY_PURPOSE,
        "created_at": _utc_now(),
        "plan_digest": plan.digest,
        "commitment_digest": commitment.commitment_digest,
        "kdf": {
            "name": "scrypt",
            "salt_b64": _b64encode(salt),
            "n": 2**14,
            "r": 8,
            "p": 1,
        },
        "encryption": {
            "name": "aes-256-gcm",
            "nonce_b64": _b64encode(nonce),
            "ciphertext_b64": _b64encode(ciphertext),
        },
    }
    return commitment, custody


def write_custody_artifacts(
    commitment: BlindingCommitment,
    custody: Mapping[str, object],
    *,
    commitment_path: Path,
    custody_path: Path,
) -> None:
    if commitment_path.resolve() == custody_path.resolve():
        raise BlindingError("commitment and custody paths must differ")
    commitment.validate()
    _write_json_exclusive(commitment_path, commitment.as_dict())
    try:
        _write_json_exclusive(custody_path, custody)
    except Exception:
        # Do not delete the already-written public commitment. Its presence
        # makes a partial preparation visible and prevents a silent remap.
        raise


def prepare_blinding_custody(
    root: Path,
    passphrase: str,
    *,
    plan_path: Path,
    commitment_path: Path,
    custody_path: Path,
    rng: random.Random | None = None,
) -> tuple[BlindingCommitment, dict[str, object]]:
    """Prepare and bind custody before the first pilot attempt exists."""
    root = root.resolve()
    for label, path in (
        ("commitment", commitment_path),
        ("custody", custody_path),
    ):
        if _is_within(path, root):
            raise BlindingError(f"{label} path must be outside the pilot root")
    try:
        plan = load_plan(plan_path)
        if plan.phase not in PILOT_PHASES:
            raise BlindingError(
                "blinding custody may be prepared only for pilot phase"
            )
        bind_output(root, plan)
        validate_output_binding(root, plan)
    except ScheduleError as exc:
        raise BlindingError(str(exc)) from exc
    destinations = (
        custody_path.resolve(),
        commitment_path.resolve(),
        (root / BOUND_COMMITMENT_NAME).resolve(),
    )
    existing = [str(path) for path in destinations if path.exists()]
    if existing:
        raise BlindingError(
            f"refusing preparation because destination already exists: {existing}"
        )
    try:
        with output_lock(root, plan):
            if any(root.rglob("trial_*.json")) or any(root.rglob("attempt_*.json")):
                raise BlindingError(
                    "blinding custody must be prepared before the first pilot attempt"
                )
            commitment, custody = create_custody_artifacts(
                plan,
                passphrase,
                rng=rng,
            )
            # All writes are exclusive. A partial preparation remains visible
            # and blocks a silent second mapping instead of being cleaned up.
            _write_json_exclusive(custody_path, custody)
            _write_json_exclusive(commitment_path, commitment.as_dict())
            # This root copy is the scheduler's readiness marker and is
            # deliberately last. Any earlier write failure therefore leaves
            # pilot execution fail-closed rather than collection-authorized.
            _write_json_exclusive(
                root / BOUND_COMMITMENT_NAME,
                commitment.as_dict(),
            )
    except ScheduleError as exc:
        raise BlindingError(str(exc)) from exc
    return commitment, custody


def load_custody(
    custody_path: Path,
    commitment: BlindingCommitment,
    passphrase: str,
) -> tuple[BlindingMapping, Ed25519PrivateKey, str]:
    try:
        raw_bytes = custody_path.read_bytes()
        raw = json.loads(raw_bytes.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BlindingError(f"cannot read custody artifact {custody_path}: {exc}") from exc
    expected = {
        "schema_version",
        "purpose",
        "created_at",
        "plan_digest",
        "commitment_digest",
        "kdf",
        "encryption",
    }
    if not isinstance(raw, dict) or set(raw) != expected:
        raise BlindingError("custody artifact has unknown or missing fields")
    if (
        raw["schema_version"] != CUSTODY_SCHEMA_VERSION
        or raw["purpose"] != CUSTODY_PURPOSE
        or raw["plan_digest"] != commitment.plan_digest
        or raw["commitment_digest"] != commitment.commitment_digest
    ):
        raise BlindingError("custody artifact does not match the commitment")
    kdf = raw["kdf"]
    encryption = raw["encryption"]
    if not isinstance(kdf, dict) or kdf != {
        "name": "scrypt",
        "salt_b64": kdf.get("salt_b64"),
        "n": 2**14,
        "r": 8,
        "p": 1,
    }:
        raise BlindingError("unsupported or malformed custody KDF")
    if not isinstance(encryption, dict) or set(encryption) != {
        "name",
        "nonce_b64",
        "ciphertext_b64",
    } or encryption.get("name") != "aes-256-gcm":
        raise BlindingError("unsupported or malformed custody encryption")
    salt = _b64decode(kdf["salt_b64"], field="custody salt")
    nonce = _b64decode(encryption["nonce_b64"], field="custody nonce")
    ciphertext = _b64decode(
        encryption["ciphertext_b64"], field="custody ciphertext"
    )
    try:
        plaintext = AESGCM(_derive_custody_key(passphrase, salt)).decrypt(
            nonce,
            ciphertext,
            commitment.commitment_digest.encode("ascii"),
        )
        secret = json.loads(plaintext.decode("utf-8"))
    except Exception as exc:
        raise BlindingError("custody decryption or authentication failed") from exc
    if not isinstance(secret, dict) or set(secret) != {
        "mapping",
        "private_key_b64",
        "commitment_digest",
    }:
        raise BlindingError("decrypted custody payload is malformed")
    if secret["commitment_digest"] != commitment.commitment_digest:
        raise BlindingError("decrypted custody commitment mismatch")
    mapping_raw = secret["mapping"]
    if not isinstance(mapping_raw, dict):
        raise BlindingError("decrypted mapping is malformed")
    mapping = BlindingMapping(
        schema_version=mapping_raw.get("schema_version"),
        purpose=mapping_raw.get("purpose"),
        created_at=mapping_raw.get("created_at"),
        plan_digest=mapping_raw.get("plan_digest"),
        environment_to_label=mapping_raw.get("environment_to_label"),
        mapping_digest=mapping_raw.get("mapping_digest"),
    )
    mapping.validate(plan_digest=commitment.plan_digest)
    if mapping.mapping_digest != commitment.mapping_digest:
        raise BlindingError("decrypted mapping does not match public commitment")
    private_bytes = _b64decode(secret["private_key_b64"], field="private key")
    try:
        private_key = Ed25519PrivateKey.from_private_bytes(private_bytes)
    except ValueError as exc:
        raise BlindingError("decrypted Ed25519 private key is malformed") from exc
    observed_public = private_key.public_key().public_bytes(
        serialization.Encoding.Raw,
        serialization.PublicFormat.Raw,
    )
    if observed_public != _b64decode(commitment.public_key_b64, field="public key"):
        raise BlindingError("custody private key does not match commitment public key")
    return mapping, private_key, _sha256_bytes(raw_bytes)


@dataclass(frozen=True)
class SourceTrial:
    source_relpath: str
    source_sha256: str
    terminal_trial_sha256: str
    phase: str
    plan_digest: str
    cell_id: str
    config_id: str
    env_id: str
    task_id: str
    family_id: str
    instance_id: str
    instance_sha256: str
    phrasing: str
    trial_index: int
    attempt_id: str
    valid: bool
    failed: bool


def _cell_directory(root: Path, cell: Cell) -> Path:
    return root.joinpath(
        cell.env_id,
        cell.agent_id,
        cell.model_id,
        cell.task_id,
        cell.phrasing,
    )


def _terminal_digest(cell_dir: Path, *, trial_index: int, attempt_id: str) -> str:
    path = cell_dir / ATTEMPT_DIR_NAME / (
        f"attempt_{trial_index}__{attempt_id}__03_trial_recorded.json"
    )
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BlindingError(
            f"trial {trial_index}/{attempt_id} lacks a readable terminal journal event"
        ) from exc
    result = raw.get("result") if isinstance(raw, dict) else None
    if (
        raw.get("event") != "trial_recorded"
        or not isinstance(result, dict)
        or result.get("status") != "trial_recorded"
    ):
        raise BlindingError(f"malformed terminal journal event: {path}")
    return _require_hex(
        result.get("trial_record_sha256"),
        field=f"{path} terminal trial digest",
    )


def _read_source_trial(root: Path, plan: SchedulePlan, cell: Cell, path: Path) -> SourceTrial:
    try:
        raw_bytes = path.read_bytes()
        raw = json.loads(raw_bytes.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BlindingError(f"cannot read source trial {path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise BlindingError(f"source trial must be a JSON object: {path}")
    trial = raw.get("trial")
    validity = raw.get("validity")
    outcome = raw.get("outcome")
    schedule = raw.get("schedule")
    attempt = raw.get("attempt")
    if not all(isinstance(item, dict) for item in (trial, validity, outcome, schedule, attempt)):
        raise BlindingError(f"source trial lacks required objects: {path}")
    assert isinstance(trial, dict)
    assert isinstance(validity, dict)
    assert isinstance(outcome, dict)
    assert isinstance(schedule, dict)
    assert isinstance(attempt, dict)
    valid = validity.get("valid")
    success = outcome.get("success")
    if type(valid) is not bool:
        raise BlindingError(f"{path}: validity.valid must be a JSON boolean")
    if type(success) is not bool:
        raise BlindingError(f"{path}: outcome.success must be a JSON boolean")
    trial_index = trial.get("trial_index")
    if not isinstance(trial_index, int) or isinstance(trial_index, bool) or trial_index < 0:
        raise BlindingError(f"{path}: trial_index must be a non-negative integer")
    attempt_id = attempt.get("attempt_id")
    if not isinstance(attempt_id, str) or re.fullmatch(r"[0-9a-f]{32}", attempt_id) is None:
        raise BlindingError(f"{path}: malformed attempt_id")
    source_sha256 = _sha256_bytes(raw_bytes)
    terminal_sha256 = _terminal_digest(
        path.parent,
        trial_index=trial_index,
        attempt_id=attempt_id,
    )
    return SourceTrial(
        source_relpath=path.relative_to(root).as_posix(),
        source_sha256=source_sha256,
        terminal_trial_sha256=terminal_sha256,
        phase=schedule.get("phase"),
        plan_digest=schedule.get("plan_digest"),
        cell_id=schedule.get("cell_id"),
        config_id=schedule.get("config_id"),
        env_id=trial.get("env_id"),
        task_id=trial.get("task_id"),
        family_id=schedule.get("family_id"),
        instance_id=schedule.get("instance_id"),
        instance_sha256=schedule.get("instance_sha256"),
        phrasing=trial.get("phrasing"),
        trial_index=trial_index,
        attempt_id=attempt_id,
        valid=valid,
        failed=not success,
    )


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True


def _allowed_source_artifact(path: Path, root: Path) -> bool:
    rel = path.relative_to(root).as_posix()
    return rel in {BOUND_PLAN_NAME, BOUND_COMMITMENT_NAME} or (
        path.name.startswith("trial_") and path.suffix == ".json"
    ) or (
        path.parent.name == ATTEMPT_DIR_NAME
        and path.name.startswith("attempt_")
        and path.suffix == ".json"
    )


@contextmanager
def stable_source_snapshot(root: Path):
    """Copy each allowed source byte once under an exclusive exporter lock.

    Validation, outcome extraction, and manifest hashing all operate on this
    same private snapshot. A cooperative concurrent exporter/collector is
    excluded, and coherent source changes before or after a read cannot create
    a rows-from-A/manifest-from-B binding.
    """
    root = root.resolve()
    lock = root / EXPORT_LOCK_NAME
    try:
        with lock.open("x", encoding="ascii", newline="\n") as handle:
            handle.write(f"pid={os.getpid()} created_at={_utc_now()}\n")
            handle.flush()
            os.fsync(handle.fileno())
    except FileExistsError as exc:
        raise BlindingError("pilot collection or another export is active") from exc
    try:
        with tempfile.TemporaryDirectory(prefix="pstax-blinding-snapshot-") as tmp:
            snapshot = Path(tmp) / "pilot"
            snapshot.mkdir()
            for path in sorted(root.rglob("*")):
                if path == lock or not path.is_file():
                    continue
                if path.is_symlink():
                    raise BlindingError(
                        f"source artifact may not be a symlink: {path}"
                    )
                if not _allowed_source_artifact(path, root):
                    raise BlindingError(
                        f"unexpected artifact under pilot root: "
                        f"{path.relative_to(root).as_posix()}"
                    )
                destination = snapshot / path.relative_to(root)
                destination.parent.mkdir(parents=True, exist_ok=True)
                # read_bytes() is the single authoritative read. All later
                # parsing and hashing use the copied bytes.
                destination.write_bytes(path.read_bytes())
            yield snapshot
    finally:
        try:
            lock.unlink()
        except FileNotFoundError:
            pass


def _source_manifest(root: Path) -> tuple[str, int]:
    entries: list[dict[str, str]] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if path.is_symlink():
            raise BlindingError(f"source artifact may not be a symlink: {path}")
        rel = path.relative_to(root).as_posix()
        if not _allowed_source_artifact(path, root):
            raise BlindingError(f"unexpected artifact under pilot root: {rel}")
        entries.append({"path": rel, "sha256": _sha256_file(path)})
    manifest_paths = {entry["path"] for entry in entries}
    if not {BOUND_PLAN_NAME, BOUND_COMMITMENT_NAME}.issubset(manifest_paths):
        raise BlindingError("source manifest lacks the bound plan or commitment")
    return _digest(entries), len(entries)


def collect_source_trials(root: Path, plan: SchedulePlan) -> tuple[list[SourceTrial], int, str, int]:
    """Validate the immutable root and return trials plus aggregate provenance."""
    root = root.resolve()
    try:
        validate_output_binding(root, plan)
        states = scan_output(root, plan)
    except ScheduleError as exc:
        raise BlindingError(str(exc)) from exc
    incomplete = [
        cell.cell_id
        for cell in plan.cells
        if states[cell.cell_id].valid != cell.target_valid_trials
        or states[cell.cell_id].unresolved
    ]
    if incomplete:
        raise BlindingError(
            f"pilot roster is incomplete or unresolved in {len(incomplete)} cell(s)"
        )
    records: list[SourceTrial] = []
    for cell in plan.cells:
        for path in sorted(_cell_directory(root, cell).glob("trial_*.json")):
            records.append(_read_source_trial(root, plan, cell, path))
    manifest_digest, artifact_count = _source_manifest(root)
    invalid_attempts = sum(state.invalid for state in states.values())
    return records, invalid_attempts, manifest_digest, artifact_count


def build_blinded_export(
    plan: SchedulePlan,
    records: Sequence[SourceTrial],
    mapping: BlindingMapping,
    commitment: BlindingCommitment,
    *,
    commitment_artifact_sha256: str,
    custody_artifact_sha256: str,
    source_manifest_digest: str,
    source_artifact_count: int,
    invalid_attempt_count: int,
) -> dict[str, object]:
    """Validate the exact pilot roster and construct a non-unblinding export."""
    if plan.phase not in PILOT_PHASES:
        raise BlindingError("blinded export requires a pilot-phase plan")
    mapping.validate(plan_digest=plan.digest)
    commitment.validate(plan_digest=plan.digest)
    if mapping.mapping_digest != commitment.mapping_digest:
        raise BlindingError("mapping does not match public commitment")
    _require_hex(
        commitment_artifact_sha256,
        field="commitment_artifact_sha256",
    )
    _require_hex(custody_artifact_sha256, field="custody_artifact_sha256")
    _require_hex(source_manifest_digest, field="source_manifest_digest")
    if not isinstance(source_artifact_count, int) or source_artifact_count < 1:
        raise BlindingError("source_artifact_count must be a positive integer")
    if not isinstance(invalid_attempt_count, int) or invalid_attempt_count < 0:
        raise BlindingError("invalid_attempt_count must be a non-negative integer")

    cells = {cell.cell_id: cell for cell in plan.cells}
    seen_sources: set[str] = set()
    seen_attempts: set[str] = set()
    valid_counts = {cell.cell_id: 0 for cell in plan.cells}
    blinded_rows: list[dict[str, object]] = []
    for record in records:
        if type(record.valid) is not bool or type(record.failed) is not bool:
            raise BlindingError("source valid/failed fields must be JSON booleans")
        _require_hex(record.source_sha256, field="source_sha256")
        _require_hex(record.terminal_trial_sha256, field="terminal_trial_sha256")
        if record.source_sha256 != record.terminal_trial_sha256:
            raise BlindingError(
                f"outcome-tampered or otherwise modified source: {record.source_relpath}"
            )
        if record.source_relpath in seen_sources:
            raise BlindingError(f"duplicate source record: {record.source_relpath}")
        if record.attempt_id in seen_attempts:
            raise BlindingError(f"duplicate attempt identity: {record.attempt_id}")
        seen_sources.add(record.source_relpath)
        seen_attempts.add(record.attempt_id)
        if record.phase != plan.phase or record.plan_digest != plan.digest:
            raise BlindingError("source record has wrong phase or plan digest")
        cell = cells.get(record.cell_id)
        if cell is None:
            raise BlindingError(f"foreign source cell {record.cell_id!r}")
        observed = (
            record.config_id,
            record.env_id,
            record.task_id,
            record.family_id,
            record.instance_id,
            record.instance_sha256,
            record.phrasing,
        )
        expected = (
            cell.config_id,
            cell.env_id,
            cell.task_id,
            cell.family_id,
            cell.instance_id,
            cell.instance_sha256,
            cell.phrasing,
        )
        if observed != expected:
            raise BlindingError(f"source coordinates do not match cell {cell.cell_id}")
        if not record.valid:
            continue
        valid_counts[cell.cell_id] += 1
        blinded_rows.append(
            {
                "blinded_group": mapping.environment_to_label[record.env_id],
                "task_id": record.task_id,
                "family_id": record.family_id,
                "instance_id": record.instance_id,
                "instance_sha256": record.instance_sha256,
                "config_id": record.config_id,
                "phrasing": record.phrasing,
                "valid": True,
                "failed": record.failed,
            }
        )

    wrong_counts = {
        cell_id: count
        for cell_id, count in valid_counts.items()
        if count != cells[cell_id].target_valid_trials
    }
    if wrong_counts:
        raise BlindingError(
            f"pilot valid roster is missing, duplicated, or unbalanced in {len(wrong_counts)} cell(s)"
        )
    expected_valid_trials = sum(cell.target_valid_trials for cell in plan.cells)
    if len(blinded_rows) != expected_valid_trials:
        raise BlindingError(
            f"expected exactly {expected_valid_trials} valid pilot trials, "
            f"found {len(blinded_rows)}"
        )
    blinded_rows.sort(
        key=lambda row: (
            row["blinded_group"],
            row["config_id"],
            row["task_id"],
            row["family_id"],
            row["instance_id"],
            row["phrasing"],
            row["failed"],
        )
    )
    payload: dict[str, object] = {
        "schema_version": BLINDED_EXPORT_SCHEMA_VERSION,
        "source_plan_digest": plan.digest,
        "source_plan_schema_version": plan.schema_version,
        "source_trial_schema_version": plan.trial_schema_version,
        "mapping_digest": mapping.mapping_digest,
        "commitment_digest": commitment.commitment_digest,
        "commitment_artifact_sha256": commitment_artifact_sha256,
        "custody_artifact_sha256": custody_artifact_sha256,
        "source_manifest_digest": source_manifest_digest,
        "source_artifact_count": source_artifact_count,
        "valid_trial_count": len(blinded_rows),
        "invalid_attempt_count": invalid_attempt_count,
        "cell_count": len(plan.cells),
        "valid_trial_policy": (
            "v2_capability_one_seeded_two"
            if plan.phase == V2_PILOT_PHASE
            else "v1_two_per_cell"
        ),
        "blinded_group_count": len(set(mapping.environment_to_label.values())),
        "trials": blinded_rows,
    }
    return payload


def sign_blinded_export(
    payload: Mapping[str, object],
    private_key: Ed25519PrivateKey,
) -> dict[str, object]:
    encoded = _canonical_json(payload).encode("utf-8")
    return {
        **payload,
        "export_digest": _sha256_bytes(encoded),
        "export_signature_b64": _b64encode(private_key.sign(encoded)),
    }


def export_blinded_pilot(
    root: Path,
    custody_path: Path,
    commitment_path: Path,
    passphrase: str,
    output_path: Path,
) -> dict[str, object]:
    root = root.resolve()
    for label, path in (
        ("custody", custody_path),
        ("commitment", commitment_path),
        ("output", output_path),
    ):
        if _is_within(path, root):
            raise BlindingError(f"{label} path must be outside the pilot root")
    commitment, commitment_artifact_sha256 = load_commitment(commitment_path)
    mapping, private_key, custody_artifact_sha256 = load_custody(
        custody_path,
        commitment,
        passphrase,
    )
    with stable_source_snapshot(root) as snapshot:
        try:
            plan = load_plan(snapshot / BOUND_PLAN_NAME)
        except ScheduleError as exc:
            raise BlindingError(str(exc)) from exc
        if plan.phase not in PILOT_PHASES:
            raise BlindingError("bound output root is not pilot phase")
        commitment.validate(plan_digest=plan.digest)
        bound_commitment, bound_commitment_sha256 = load_commitment(
            snapshot / BOUND_COMMITMENT_NAME,
            plan_digest=plan.digest,
        )
        if (
            bound_commitment != commitment
            or bound_commitment_sha256 != commitment_artifact_sha256
        ):
            raise BlindingError(
                "pilot-root commitment differs from the independently anchored artifact"
            )
        records, invalid_count, manifest_digest, artifact_count = (
            collect_source_trials(snapshot, plan)
        )
        payload = build_blinded_export(
            plan,
            records,
            mapping,
            commitment,
            commitment_artifact_sha256=commitment_artifact_sha256,
            custody_artifact_sha256=custody_artifact_sha256,
            source_manifest_digest=manifest_digest,
            source_artifact_count=artifact_count,
            invalid_attempt_count=invalid_count,
        )
        export = sign_blinded_export(payload, private_key)
    _write_json_exclusive(output_path, export)
    return export


def load_blinded_export_bytes(
    raw_bytes: bytes,
    commitment_bytes: bytes,
) -> tuple[list[dict[str, object]], dict[str, object], str]:
    """Verify one immutable export/commitment snapshot for sizing."""
    try:
        raw = json.loads(raw_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BlindingError(f"cannot parse blinded export: {exc}") from exc
    if not isinstance(raw, dict):
        raise BlindingError("pilot sizing input must be a blinded-export object")
    expected = {
        "schema_version",
        "source_plan_digest",
        "source_plan_schema_version",
        "source_trial_schema_version",
        "mapping_digest",
        "commitment_digest",
        "commitment_artifact_sha256",
        "custody_artifact_sha256",
        "source_manifest_digest",
        "source_artifact_count",
        "valid_trial_count",
        "invalid_attempt_count",
        "cell_count",
        "valid_trial_policy",
        "blinded_group_count",
        "trials",
        "export_digest",
        "export_signature_b64",
    }
    if set(raw) != expected:
        raise BlindingError("blinded export has unknown or missing fields")
    signature_b64 = raw.pop("export_signature_b64")
    digest = raw.pop("export_digest")
    encoded = _canonical_json(raw).encode("utf-8")
    if digest != _sha256_bytes(encoded):
        raise BlindingError("blinded export digest mismatch")
    commitment, commitment_artifact_sha256 = load_commitment_bytes(commitment_bytes)
    if raw["commitment_digest"] != commitment.commitment_digest:
        raise BlindingError("blinded export commitment mismatch")
    if raw["commitment_artifact_sha256"] != commitment_artifact_sha256:
        raise BlindingError("blinded export commitment artifact hash mismatch")
    if raw["source_plan_digest"] != commitment.plan_digest:
        raise BlindingError("blinded export plan does not match commitment")
    if raw["mapping_digest"] != commitment.mapping_digest:
        raise BlindingError("blinded export mapping does not match commitment")
    signature = _b64decode(signature_b64, field="export_signature_b64")
    try:
        public_key = Ed25519PublicKey.from_public_bytes(
            _b64decode(commitment.public_key_b64, field="public_key_b64")
        )
        public_key.verify(signature, encoded)
    except (ValueError, InvalidSignature) as exc:
        raise BlindingError("blinded export signature verification failed") from exc
    if raw["schema_version"] != BLINDED_EXPORT_SCHEMA_VERSION:
        raise BlindingError("unsupported blinded export schema")
    if not all(
        isinstance(raw[field], str) and raw[field]
        for field in (
            "source_plan_schema_version",
            "source_trial_schema_version",
        )
    ):
        raise BlindingError("blinded export source schema fields are malformed")
    for field in (
        "source_plan_digest",
        "mapping_digest",
        "commitment_digest",
        "commitment_artifact_sha256",
        "custody_artifact_sha256",
        "source_manifest_digest",
    ):
        _require_hex(raw[field], field=field)
    if (
        not isinstance(raw["source_artifact_count"], int)
        or isinstance(raw["source_artifact_count"], bool)
        or raw["source_artifact_count"] < 1
        or not isinstance(raw["invalid_attempt_count"], int)
        or isinstance(raw["invalid_attempt_count"], bool)
        or raw["invalid_attempt_count"] < 0
        or raw["blinded_group_count"] != 5
    ):
        raise BlindingError("blinded export does not describe the exact pilot roster")
    policy = raw["valid_trial_policy"]
    if policy == "v1_two_per_cell":
        expected_cells = EXPECTED_PILOT_CELLS
        expected_trials = EXPECTED_VALID_TRIALS
        expected_variants = {
            *((f"C{i:02d}", f"C{i:02d}", "fixed", "default", 2) for i in range(1, 6)),
            *((f"T{i:02d}", f"T{i:02d}", "fixed", phrasing, 2)
              for i in range(1, 10)
              for phrasing in ("formal", "colloquial")),
        }
    elif policy == "v2_capability_one_seeded_two":
        expected_cells = 540
        expected_trials = 720
        expected_variants = {
            *((f"C{family:02d}-I{instance:02d}", f"C{family:02d}", f"I{instance:02d}", "default", 1)
              for family in range(1, 13) for instance in range(1, 4)),
            *((f"T{i:02d}", f"T{i:02d}", "fixed", phrasing, 2)
              for i in range(1, 10)
              for phrasing in ("formal", "colloquial")),
        }
    else:
        raise BlindingError("blinded export has an unknown valid-trial policy")
    if raw["valid_trial_count"] != expected_trials or raw["cell_count"] != expected_cells:
        raise BlindingError("blinded export does not describe the exact pilot roster")
    trials = raw["trials"]
    if not isinstance(trials, list) or len(trials) != expected_trials:
        raise BlindingError("blinded export trials are malformed or incomplete")
    groups: set[str] = set()
    coordinate_counts: dict[tuple[str, str, str, str], int] = {}
    for row in trials:
        if not isinstance(row, dict) or set(row) != {
            "blinded_group",
            "task_id",
            "family_id",
            "instance_id",
            "instance_sha256",
            "config_id",
            "phrasing",
            "valid",
            "failed",
        }:
            raise BlindingError("blinded trial has unknown or missing fields")
        if type(row["valid"]) is not bool or row["valid"] is not True:
            raise BlindingError("blinded trial valid must be JSON true")
        if type(row["failed"]) is not bool:
            raise BlindingError("blinded trial failed must be a JSON boolean")
        if not all(
            isinstance(row[field], str) and row[field]
            for field in (
                "blinded_group", "task_id", "family_id", "instance_id",
                "instance_sha256", "config_id", "phrasing",
            )
        ):
            raise BlindingError("blinded trial text fields must be non-empty strings")
        groups.add(row["blinded_group"])
        _require_hex(row["instance_sha256"], field="instance_sha256")
        coordinate = (
            row["blinded_group"],
            row["config_id"],
            row["task_id"],
            row["family_id"],
            row["instance_id"],
            row["phrasing"],
        )
        coordinate_counts[coordinate] = coordinate_counts.get(coordinate, 0) + 1
    if groups != {f"E{i:02d}" for i in range(1, 6)}:
        raise BlindingError("blinded trial group roster is not exactly E01-E05")
    expected_coordinates = {
        (group, config, task_id, family_id, instance_id, phrasing)
        for group in {f"E{i:02d}" for i in range(1, 6)}
        for config in {"CFG1", "CFG2"}
        for task_id, family_id, instance_id, phrasing, _ in expected_variants
    }
    expected_counts = {
        (group, config, task_id, family_id, instance_id, phrasing): count
        for group in {f"E{i:02d}" for i in range(1, 6)}
        for config in {"CFG1", "CFG2"}
        for task_id, family_id, instance_id, phrasing, count in expected_variants
    }
    if set(coordinate_counts) != expected_coordinates or coordinate_counts != expected_counts:
        raise BlindingError("blinded trial multiset is not the exact frozen pilot roster")
    metadata = {
        "source_plan_digest": raw["source_plan_digest"],
        "source_plan_schema_version": raw["source_plan_schema_version"],
        "source_trial_schema_version": raw["source_trial_schema_version"],
        "export_digest": digest,
        "source_manifest_digest": raw["source_manifest_digest"],
        "commitment_digest": raw["commitment_digest"],
        "commitment_artifact_sha256": raw["commitment_artifact_sha256"],
        "commitment_public_key_b64": commitment.public_key_b64,
    }
    return trials, metadata, _sha256_bytes(raw_bytes)


def load_blinded_export(
    path: Path,
    commitment_path: Path,
) -> list[dict[str, object]]:
    """Load and integrity-check the only accepted pilot-sizing input form."""
    try:
        raw_bytes = path.read_bytes()
        commitment_bytes = commitment_path.read_bytes()
    except OSError as exc:
        raise BlindingError(f"cannot read blinded sizing input: {exc}") from exc
    trials, _, _ = load_blinded_export_bytes(raw_bytes, commitment_bytes)
    return trials
