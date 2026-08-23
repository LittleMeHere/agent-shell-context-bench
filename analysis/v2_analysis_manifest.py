"""Immutable source manifest for the V2 analysis dataset.

The manifest fixes the complete trial-record byte set before analysis.  Its
digest must be anchored externally (for example in the pre-data repository
tag or a timestamped custody record); a public self-hash is integrity evidence,
not authentication.  Loading re-enumerates the source root, verifies every
byte digest, then invokes the independent record reconstruction.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from contextlib import contextmanager
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Iterator, Mapping

from analysis.v2_analysis_dataset import (
    AnalysisDatasetError,
    AnalysisTrial,
    build_analysis_dataset,
    derive_analysis_trial,
)
from harness.scheduler import SchedulePlan


MANIFEST_SCHEMA_VERSION = "1.0.0"
SOURCE_LOCK_NAME = ".scheduler.lock"


class AnalysisManifestError(ValueError):
    """The frozen source manifest or its bound bytes are invalid."""


@dataclass(frozen=True)
class TrialSource:
    relative_path: str
    sha256: str
    cell_id: str
    trial_index: int
    attempt_id: str
    valid_analysis_trial: bool

    def as_dict(self) -> dict[str, object]:
        return {
            "relative_path": self.relative_path,
            "sha256": self.sha256,
            "cell_id": self.cell_id,
            "trial_index": self.trial_index,
            "attempt_id": self.attempt_id,
            "valid_analysis_trial": self.valid_analysis_trial,
        }


@dataclass(frozen=True)
class AnalysisManifest:
    schema_version: str
    purpose: str
    plan_digest: str
    trial_schema_version: str
    sources: tuple[TrialSource, ...]
    manifest_digest: str

    def payload(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "purpose": self.purpose,
            "plan_digest": self.plan_digest,
            "trial_schema_version": self.trial_schema_version,
            "sources": [source.as_dict() for source in self.sources],
        }

    def as_dict(self) -> dict[str, object]:
        return {**self.payload(), "manifest_digest": self.manifest_digest}


@dataclass(frozen=True)
class AnalysisSourceSnapshot:
    """One manifest-bound source captured from a single locked byte snapshot."""

    source: TrialSource
    raw_bytes: bytes
    record: Mapping[str, object]
    analysis_trial: AnalysisTrial


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical_json(value)).hexdigest()


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _trial_paths(source_root: Path) -> tuple[Path, ...]:
    return tuple(sorted(path for path in source_root.rglob("trial_*.json") if path.is_file()))


@contextmanager
def _stable_source_root(source_root: Path) -> Iterator[None]:
    """Exclude a compliant scheduler/exporter while source bytes are frozen."""

    lock_path = source_root / SOURCE_LOCK_NAME
    try:
        with lock_path.open("x", encoding="utf-8", newline="\n") as handle:
            json.dump(
                {
                    "purpose": "v2_analysis_manifest_snapshot",
                    "pid": os.getpid(),
                },
                handle,
                sort_keys=True,
            )
            handle.write("\n")
    except FileExistsError as exc:
        raise AnalysisManifestError(
            f"analysis source root is locked: {lock_path}"
        ) from exc
    except OSError as exc:
        raise AnalysisManifestError(
            f"cannot lock analysis source root {source_root}: {exc}"
        ) from exc
    try:
        yield
    finally:
        lock_path.unlink(missing_ok=True)


def _read_record(path: Path) -> tuple[bytes, Mapping[str, object]]:
    try:
        data = path.read_bytes()
        raw = json.loads(data.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AnalysisManifestError(f"cannot read trial source {path}: {exc}") from exc
    if not isinstance(raw, Mapping):
        raise AnalysisManifestError(f"trial source is not a JSON object: {path}")
    return data, raw


def _expected_relative_path(row: AnalysisTrial) -> Path:
    return Path(
        row.env_id,
        row.agent_id,
        row.model_id,
        row.task_id,
        row.phrasing,
    )


def build_analysis_manifest(
    plan: SchedulePlan,
    source_root: Path,
) -> AnalysisManifest:
    """Snapshot a complete collection root into a canonical source manifest."""

    root = source_root.resolve()
    if not root.is_dir():
        raise AnalysisManifestError(f"analysis source root is not a directory: {root}")
    with _stable_source_root(root):
        paths = _trial_paths(root)
        if not paths:
            raise AnalysisManifestError("analysis source root contains no trial records")

        raw_records: list[Mapping[str, object]] = []
        sources: list[TrialSource] = []
        for path in paths:
            data, raw = _read_record(path)
            try:
                row = derive_analysis_trial(raw)
            except AnalysisDatasetError as exc:
                raise AnalysisManifestError(f"invalid trial source {path}: {exc}") from exc
            relative = path.relative_to(root)
            if relative.parent != _expected_relative_path(row):
                raise AnalysisManifestError(f"trial source is under the wrong coordinate path: {relative}")
            raw_records.append(raw)
            sources.append(
                TrialSource(
                    relative_path=relative.as_posix(),
                    sha256=_sha256(data),
                    cell_id=row.cell_id,
                    trial_index=row.trial_index,
                    attempt_id=row.attempt_id,
                    valid_analysis_trial=row.valid_analysis_trial,
                )
            )
        try:
            build_analysis_dataset(plan, raw_records)
        except AnalysisDatasetError as exc:
            raise AnalysisManifestError(f"analysis source roster is invalid: {exc}") from exc
        if _trial_paths(root) != paths:
            raise AnalysisManifestError("analysis source file roster changed during freeze")
        for path, source in zip(paths, sources, strict=True):
            if _sha256(path.read_bytes()) != source.sha256:
                raise AnalysisManifestError(
                    f"analysis source changed during freeze: {source.relative_path}"
                )

    provisional = AnalysisManifest(
        schema_version=MANIFEST_SCHEMA_VERSION,
        purpose="v2_frozen_analysis_trial_sources",
        plan_digest=plan.digest,
        trial_schema_version=plan.trial_schema_version,
        sources=tuple(sources),
        manifest_digest="",
    )
    return AnalysisManifest(
        **{
            **provisional.__dict__,
            "manifest_digest": _digest(provisional.payload()),
        }
    )


def write_analysis_manifest(
    manifest: AnalysisManifest,
    path: Path,
    *,
    source_root: Path,
) -> None:
    """Write the externally anchored artifact without mutating the source root."""

    output = path.resolve()
    root = source_root.resolve()
    if _is_relative_to(output, root):
        raise AnalysisManifestError("analysis manifest must be outside the source root")
    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        with output.open("x", encoding="utf-8", newline="\n") as handle:
            json.dump(manifest.as_dict(), handle, indent=2, ensure_ascii=False)
            handle.write("\n")
    except FileExistsError as exc:
        raise AnalysisManifestError(f"refusing to overwrite manifest: {output}") from exc


def analysis_manifest_from_dict(raw: object) -> AnalysisManifest:
    expected = {
        "schema_version",
        "purpose",
        "plan_digest",
        "trial_schema_version",
        "sources",
        "manifest_digest",
    }
    if not isinstance(raw, dict) or set(raw) != expected:
        raise AnalysisManifestError("analysis manifest has unknown or missing fields")
    if (
        raw["schema_version"] != MANIFEST_SCHEMA_VERSION
        or raw["purpose"] != "v2_frozen_analysis_trial_sources"
        or not isinstance(raw["plan_digest"], str)
        or re.fullmatch(r"[0-9a-f]{64}", raw["plan_digest"]) is None
        or not isinstance(raw["trial_schema_version"], str)
        or not raw["trial_schema_version"]
        or not isinstance(raw["sources"], list)
        or not raw["sources"]
    ):
        raise AnalysisManifestError("analysis manifest identity is invalid")
    sources: list[TrialSource] = []
    fields = {
        "relative_path",
        "sha256",
        "cell_id",
        "trial_index",
        "attempt_id",
        "valid_analysis_trial",
    }
    for item in raw["sources"]:
        if not isinstance(item, dict) or set(item) != fields:
            raise AnalysisManifestError("analysis source entry has unknown or missing fields")
        if (
            not isinstance(item["relative_path"], str)
            or not item["relative_path"]
            or Path(item["relative_path"]).is_absolute()
            or ".." in Path(item["relative_path"]).parts
            or not isinstance(item["sha256"], str)
            or re.fullmatch(r"[0-9a-f]{64}", item["sha256"]) is None
            or not isinstance(item["cell_id"], str)
            or re.fullmatch(r"[0-9a-f]{16}", item["cell_id"]) is None
            or isinstance(item["trial_index"], bool)
            or not isinstance(item["trial_index"], int)
            or item["trial_index"] < 0
            or not isinstance(item["attempt_id"], str)
            or re.fullmatch(r"[0-9a-f]{32}", item["attempt_id"]) is None
            or type(item["valid_analysis_trial"]) is not bool
        ):
            raise AnalysisManifestError("analysis source entry is malformed")
        sources.append(TrialSource(**item))
    paths = [source.relative_path for source in sources]
    if len(paths) != len(set(paths)) or paths != sorted(paths):
        raise AnalysisManifestError("analysis source paths must be unique and sorted")
    manifest = AnalysisManifest(
        schema_version=raw["schema_version"],
        purpose=raw["purpose"],
        plan_digest=raw["plan_digest"],
        trial_schema_version=raw["trial_schema_version"],
        sources=tuple(sources),
        manifest_digest=raw["manifest_digest"],
    )
    if (
        not isinstance(manifest.manifest_digest, str)
        or not re.fullmatch(r"[0-9a-f]{64}", manifest.manifest_digest)
        or manifest.manifest_digest != _digest(manifest.payload())
    ):
        raise AnalysisManifestError("analysis manifest digest mismatch")
    return manifest


def load_analysis_snapshot(
    plan: SchedulePlan,
    source_root: Path,
    manifest_path: Path,
) -> tuple[AnalysisManifest, tuple[AnalysisSourceSnapshot, ...]]:
    """Verify and capture every manifest source under one shared source lock."""

    try:
        raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AnalysisManifestError(f"cannot read analysis manifest: {exc}") from exc
    manifest = analysis_manifest_from_dict(raw)
    if (
        manifest.plan_digest != plan.digest
        or manifest.trial_schema_version != plan.trial_schema_version
    ):
        raise AnalysisManifestError("analysis manifest is foreign to the supplied plan")
    root = source_root.resolve()
    if not root.is_dir():
        raise AnalysisManifestError(f"analysis source root is not a directory: {root}")
    with _stable_source_root(root):
        current_paths = tuple(path.relative_to(root).as_posix() for path in _trial_paths(root))
        expected_paths = tuple(source.relative_path for source in manifest.sources)
        if current_paths != expected_paths:
            raise AnalysisManifestError("analysis source file roster changed after freeze")

        records: list[Mapping[str, object]] = []
        snapshots: list[AnalysisSourceSnapshot] = []
        for source in manifest.sources:
            path = (root / Path(source.relative_path)).resolve()
            if not _is_relative_to(path, root):
                raise AnalysisManifestError("analysis source path escapes its root")
            data, raw_record = _read_record(path)
            if _sha256(data) != source.sha256:
                raise AnalysisManifestError(f"analysis source digest mismatch: {source.relative_path}")
            row = derive_analysis_trial(raw_record)
            if (
                row.cell_id,
                row.trial_index,
                row.attempt_id,
                row.valid_analysis_trial,
            ) != (
                source.cell_id,
                source.trial_index,
                source.attempt_id,
                source.valid_analysis_trial,
            ):
                raise AnalysisManifestError("analysis source entry contradicts record bytes")
            records.append(raw_record)
            snapshots.append(
                AnalysisSourceSnapshot(
                    source=source,
                    raw_bytes=data,
                    record=raw_record,
                    analysis_trial=row,
                )
            )
        final_paths = tuple(path.relative_to(root).as_posix() for path in _trial_paths(root))
        if final_paths != current_paths:
            raise AnalysisManifestError("analysis source file roster changed during load")
    try:
        validated = build_analysis_dataset(plan, records)
    except AnalysisDatasetError as exc:
        raise AnalysisManifestError(f"analysis dataset reconstruction failed: {exc}") from exc
    validated_by_identity = {row.identity: row for row in validated}
    bound: list[AnalysisSourceSnapshot] = []
    for snapshot in snapshots:
        if snapshot.source.valid_analysis_trial:
            validated_row = validated_by_identity.get(snapshot.analysis_trial.identity)
            if validated_row is None:
                raise AnalysisManifestError(
                    "valid analysis source is absent from reconstructed dataset"
                )
            snapshot = replace(snapshot, analysis_trial=validated_row)
        bound.append(snapshot)
    return manifest, tuple(bound)


def load_analysis_dataset(
    plan: SchedulePlan,
    source_root: Path,
    manifest_path: Path,
) -> tuple[AnalysisTrial, ...]:
    """Verify the frozen source snapshot and return its valid analysis rows."""

    _manifest, snapshots = load_analysis_snapshot(plan, source_root, manifest_path)
    rows = [
        snapshot.analysis_trial
        for snapshot in snapshots
        if snapshot.source.valid_analysis_trial
    ]
    return tuple(
        sorted(
            rows,
            key=lambda row: (
                row.execution_position
                if row.execution_position is not None
                else float("inf"),
                row.trial_index,
            ),
        )
    )
