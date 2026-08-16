"""IRR coding driver — applies the spiral rubric (A–F) to trial transcripts.

Implements the SAP S4 layered design: two independent API frontier models
(different lineages) each code the full IRR sample; the researcher blind-
codes a >=50 subset as the human anchor. This script runs the AI coders.

Integrity guarantees built in:

  * The grading prompt is RENDERED FROM `harness/classifier/rubric.py` —
    the single rubric source — and frozen to `scripts/irr_prompt.frozen.md`.
    The script refuses to run if the live render and the frozen file differ
    (sha256), so the instructions given to coders can never silently drift
    from the rubric, and the exact prompt is what gets pre-registered.
  * The coding universe comes only from the complete, frozen V2 analysis
    manifest. Invalid attempts, pilot records, foreign plans, and ad-hoc
    filesystem searches cannot enter it.
  * Coders receive ONLY the task prompt, transcript, and programmatic binary
    outcome — never the environment id / probe. The still-open V2 evidence-
    packet amendment remains explicit rather than being silently invented.
  * Every output binds the plan, analysis-manifest digest, exact source bytes,
    full trial identity, transcript, coder input, frozen prompt, and model pin.
  * Refusal, malformed output, backend errors, and model substitution are
    immutable missing-label states. There is no automatic retry or fallback
    coder that could rewrite the accepted frozen-Coder-1 primary label.

Real subscription-CLI backends are implemented in `irr_cli_backends.py`. The
exact backend version and served model must be supplied and are bound into
every output; `--dry-run` remains available for no-call plumbing.

Usage:
  python scripts/irr_code.py --emit-frozen-prompt        # one-time, then commit
  python scripts/irr_code.py --check-prompt              # CI / pre-reg gate
  python scripts/irr_code.py --coder coder1 --plan PLAN --source-root ROOT \
    --manifest ANALYSIS_MANIFEST --out PRIVATE_OUTPUT --dry-run
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from abc import ABC, abstractmethod
from collections.abc import Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

_BENCH_ROOT = Path(__file__).resolve().parents[1]
if str(_BENCH_ROOT) not in sys.path:
    sys.path.insert(0, str(_BENCH_ROOT))

from harness.classifier.rubric import RUBRIC, SpiralCode  # noqa: E402
from analysis.v2_analysis_manifest import (  # noqa: E402
    AnalysisManifest,
    AnalysisSourceSnapshot,
    load_analysis_snapshot,
)
from harness.scheduler import CONFIRMATORY_PHASE, load_plan  # noqa: E402

_FROZEN_PROMPT = _BENCH_ROOT / "scripts" / "irr_prompt.frozen.md"
_VALID_CODES = {c.value for c in SpiralCode}
CODER_LABEL_SCHEMA_VERSION = "1.1.0"
CODER_RUN_SCHEMA_VERSION = "1.1.0"
_BINDING_NAME = ".coder-run-binding.json"
_LOCK_NAME = ".coder-run.lock"
_COMPLETE_NAME = "coder-run-complete.json"


# --------------------------------------------------------------------------
# Prompt: rendered from the rubric so it cannot drift from it.
# --------------------------------------------------------------------------

def render_prompt() -> str:
    lines: list[str] = []
    lines.append("# Spiral Classification — Coding Task")
    lines.append("")
    lines.append(
        "You are an independent rater. You will read ONE transcript of an "
        "AI coding agent attempting a task, and assign EXACTLY ONE code "
        "(A–F) describing the agent's behaviour, especially after any "
        "failure. Judge only what the transcript shows. Do not reward or "
        "penalise based on which shell or OS it appears to be — code the "
        "behavioural pattern only."
    )
    lines.append("")
    lines.append("## Codes")
    for code in SpiralCode:
        d = RUBRIC[code]
        lines.append("")
        lines.append(f"### {code.value} — {d.name}")
        lines.append(f"**Definition:** {d.short_definition}")
        lines.append(f"**Use when:** {d.when_to_use}")
        lines.append(f"**Do NOT use when:** {d.not_when}")
        lines.append("**Examples:**")
        for ex in d.examples:
            lines.append(f"- {ex}")
    lines.append("")
    lines.append("## Output format (STRICT)")
    lines.append(
        "Return a single JSON object and nothing else:\n"
        '{\"code\": \"<one of A B C D E F>\", '
        '\"rationale\": \"<<=400 chars, cite transcript evidence>\"}'
    )
    return "\n".join(lines) + "\n"


def prompt_sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def check_prompt_frozen() -> str:
    """Return the frozen prompt; raise if it drifts from the live render."""
    live = render_prompt()
    if not _FROZEN_PROMPT.exists():
        raise SystemExit(
            "frozen prompt missing — run --emit-frozen-prompt and commit it "
            "before any coding (pre-registration requires a frozen prompt)."
        )
    frozen = _FROZEN_PROMPT.read_text(encoding="utf-8")
    if prompt_sha256(frozen) != prompt_sha256(live):
        raise SystemExit(
            "RUBRIC/PROMPT DRIFT: scripts/irr_prompt.frozen.md no longer "
            "matches the rubric render. The rubric changed after freezing. "
            "Resolve deliberately: re-freeze + log a DEVIATION, or revert "
            "the rubric. Refusing to code with a drifted prompt."
        )
    return frozen


# --------------------------------------------------------------------------
# Rater backends. Concrete API models are pinned at experiment start.
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class RaterResponse:
    raw_response: str
    observed_model_id: str
    refused: bool = False
    request_id: str | None = None
    backend_metadata: Mapping[str, object] | None = None


class RaterBackend(ABC):
    coder_id: str
    model_pin: str  # exact model id+version, frozen at experiment start

    @abstractmethod
    def code_one(self, system_prompt: str, user_content: str) -> RaterResponse:
        """Return the raw response plus independently observed model identity."""


class PinnedAPIBackend(RaterBackend):
    """STUB. Fill in per SAP S4 at experiment start; do NOT guess the SDK.

    Two instances are required, from DIFFERENT model lineages (coder1,
    coder2). Pin exact model id + version into `model_pin` and wire the
    vendor SDK call here. Until then this raises — the harness must never
    fabricate IRR labels.
    """

    def __init__(self, coder_id: str, model_pin: str) -> None:
        self.coder_id = coder_id
        self.model_pin = model_pin

    def code_one(self, system_prompt: str, user_content: str) -> RaterResponse:
        raise NotImplementedError(
            f"PinnedAPIBackend[{self.coder_id}] not wired. Pin the exact "
            f"model + SDK at experiment start (SAP S4), then implement. "
            f"Use --dry-run to validate plumbing without an API."
        )


class DryRunBackend(RaterBackend):
    """Plumbing-only backend: deterministic, no API, never a real label.

    Emits a sentinel so dry-run output can never be mistaken for real IRR
    data (code 'A' is irrelevant — the `dry_run` flag marks it invalid).
    """

    model_pin = "DRYRUN-not-a-model"

    def __init__(self, coder_id: str) -> None:
        self.coder_id = coder_id

    def code_one(self, system_prompt: str, user_content: str) -> RaterResponse:
        return RaterResponse(
            raw_response=json.dumps(
                {"code": "A", "rationale": "DRY RUN — not a real label"}
            ),
            observed_model_id=self.model_pin,
            request_id="dry-run",
        )


# --------------------------------------------------------------------------
# Coding loop
# --------------------------------------------------------------------------

def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical_json(value)).hexdigest()


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be a JSON object")
    return value


def _blind_user_content(trial: Mapping[str, object]) -> str:
    """Everything the V1-compatible rater sees; environment remains excluded."""

    prompt = trial.get("prompt")
    agent = _mapping(trial.get("agent"), "agent")
    transcript = agent.get("transcript")
    outcome = _mapping(trial.get("outcome"), "outcome")
    success = outcome.get("success")
    if not isinstance(prompt, str) or not isinstance(transcript, str):
        raise ValueError("coder source prompt and transcript must be strings")
    if type(success) is not bool:
        raise ValueError("coder source outcome.success must be a JSON boolean")
    return (
        f"TASK PROMPT:\n{prompt}\n\n"
        f"OUTCOME: {'success' if success else 'failure'}\n\n"
        f"TRANSCRIPT:\n{transcript}\n"
    )


def _parse_code(raw: str) -> tuple[str, str]:
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"unparseable rater output: {exc}: {raw[:200]!r}") from exc
    if not isinstance(obj, dict) or set(obj) != {"code", "rationale"}:
        raise ValueError("rater output must contain exactly code and rationale")
    code = obj["code"]
    rationale = obj["rationale"]
    if not isinstance(code, str) or code.strip().upper() not in _VALID_CODES:
        raise ValueError(f"invalid code {code!r}; must be one of {_VALID_CODES}")
    if not isinstance(rationale, str) or not rationale.strip() or len(rationale) > 400:
        raise ValueError("rater rationale must be a non-empty string of at most 400 chars")
    return code.strip().upper(), rationale


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def validate_coder_paths(source_root: Path, out_root: Path) -> None:
    source = source_root.resolve()
    output = out_root.resolve()
    if _is_relative_to(output, _BENCH_ROOT.resolve()):
        raise ValueError("raw coder outputs must use an external private root")
    if _is_relative_to(output, source) or _is_relative_to(source, output):
        raise ValueError("coder output and immutable trial source roots must be separate")


def _validate_backend_identity(backend: RaterBackend, *, dry_run: bool) -> None:
    if backend.coder_id not in {"coder1", "coder2"}:
        raise ValueError("coder id must be the prospectively assigned coder1 or coder2")
    if not isinstance(backend.model_pin, str) or not backend.model_pin.strip():
        raise ValueError("coder backend requires a non-empty frozen model pin")
    if dry_run:
        if backend.model_pin != DryRunBackend.model_pin:
            raise ValueError("dry-run backend must use the invalid dry-run model sentinel")
    elif (
        backend.model_pin == DryRunBackend.model_pin
        or "PIN-AT-START" in backend.model_pin
    ):
        raise ValueError("real coder backend model identity is not frozen")


def _write_json_exclusive(path: Path, value: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("x", encoding="utf-8", newline="\n") as handle:
            json.dump(value, handle, indent=2, sort_keys=True, ensure_ascii=False)
            handle.write("\n")
    except FileExistsError as exc:
        raise ValueError(f"refusing to overwrite coder artifact: {path}") from exc


def _load_json_object(path: Path, label: str) -> Mapping[str, object]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read {label} {path}: {exc}") from exc
    if not isinstance(raw, Mapping):
        raise ValueError(f"{label} must be a JSON object: {path}")
    return raw


@contextmanager
def _coder_lock(out_dir: Path) -> Iterator[None]:
    lock = out_dir / _LOCK_NAME
    try:
        with lock.open("x", encoding="utf-8", newline="\n") as handle:
            json.dump({"pid": os.getpid(), "purpose": "v2_coder_run"}, handle)
            handle.write("\n")
    except FileExistsError as exc:
        raise ValueError(f"coder output is locked: {lock}") from exc
    try:
        yield
    finally:
        lock.unlink(missing_ok=True)


def _run_binding(
    *,
    plan_digest: str,
    manifest: AnalysisManifest,
    backend: RaterBackend,
    prompt_hash: str,
    dry_run: bool,
) -> dict[str, object]:
    return {
        "schema_version": CODER_RUN_SCHEMA_VERSION,
        "purpose": "v2_manifest_bound_spiral_coding",
        "plan_digest": plan_digest,
        "analysis_manifest_digest": manifest.manifest_digest,
        "coder_id": backend.coder_id,
        "model_pin": backend.model_pin,
        "prompt_sha256": prompt_hash,
        "dry_run": dry_run,
        "automatic_retries": 0,
        "fallback_rewrites_primary": False,
    }


def _bind_run(out_dir: Path, binding: Mapping[str, object]) -> None:
    path = out_dir / _BINDING_NAME
    if path.exists():
        if dict(_load_json_object(path, "coder run binding")) != dict(binding):
            raise ValueError("coder output root is bound to a different run")
        return
    _write_json_exclusive(path, binding)


def _label_filename(snapshot: AnalysisSourceSnapshot, coder_id: str) -> str:
    row = snapshot.analysis_trial
    safe_coder = re.sub(r"[^A-Za-z0-9_.-]", "_", coder_id)
    return (
        f"{row.cell_id}__t{row.trial_index}__{row.attempt_id}__"
        f"{safe_coder}.json"
    )


def _source_identity(snapshot: AnalysisSourceSnapshot) -> dict[str, object]:
    row = snapshot.analysis_trial
    return {
        "relative_path": snapshot.source.relative_path,
        "trial_record_sha256": snapshot.source.sha256,
        "plan_digest": row.plan_digest,
        "cell_id": row.cell_id,
        "config_id": row.config_id,
        "trial_index": row.trial_index,
        "valid_slot_index": row.valid_slot_index,
        "execution_position": row.execution_position,
        "collection_epoch": row.collection_epoch,
        "attempt_id": row.attempt_id,
        "task_id": row.task_id,
        "family_id": row.family_id,
        "instance_id": row.instance_id,
        "phrasing": row.phrasing,
    }


def _make_label_record(
    *,
    snapshot: AnalysisSourceSnapshot,
    manifest: AnalysisManifest,
    backend: RaterBackend,
    prompt_hash: str,
    user_content: str,
    response: RaterResponse | None,
    status: str,
    code: str | None,
    rationale: str | None,
    error: str | None,
    dry_run: bool,
) -> dict[str, object]:
    agent = _mapping(snapshot.record.get("agent"), "agent")
    transcript = agent.get("transcript")
    if not isinstance(transcript, str):
        raise ValueError("coder source transcript must be a string")
    raw_response = response.raw_response if response is not None else None
    payload: dict[str, object] = {
        "schema_version": CODER_LABEL_SCHEMA_VERSION,
        "purpose": "v2_manifest_bound_spiral_label",
        "analysis_manifest_digest": manifest.manifest_digest,
        "source": _source_identity(snapshot),
        "transcript_sha256": prompt_sha256(transcript),
        "coder_input_sha256": prompt_sha256(user_content),
        "coder_id": backend.coder_id,
        "model_pin": backend.model_pin,
        "observed_model_id": (
            response.observed_model_id if response is not None else None
        ),
        "request_id": response.request_id if response is not None else None,
        "backend_metadata": (
            dict(response.backend_metadata)
            if response is not None and response.backend_metadata is not None
            else None
        ),
        "prompt_sha256": prompt_hash,
        "status": status,
        "code": code,
        "rationale": rationale,
        "raw_response": raw_response,
        "raw_response_sha256": (
            prompt_sha256(raw_response) if raw_response is not None else None
        ),
        "error": error,
        "dry_run": dry_run,
        "coded_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ"),
    }
    return {**payload, "label_digest": _digest(payload)}


def _validate_label_record(
    raw: Mapping[str, object],
    *,
    snapshot: AnalysisSourceSnapshot,
    manifest: AnalysisManifest,
    backend: RaterBackend,
    prompt_hash: str,
    user_content: str,
    dry_run: bool,
) -> None:
    expected_fields = {
        "schema_version", "purpose", "analysis_manifest_digest", "source",
        "transcript_sha256", "coder_input_sha256", "coder_id", "model_pin",
        "observed_model_id", "request_id", "backend_metadata", "prompt_sha256",
        "status", "code", "rationale", "raw_response", "raw_response_sha256",
        "error", "dry_run", "coded_at", "label_digest",
    }
    if set(raw) != expected_fields:
        raise ValueError("coder label has unknown or missing fields")
    agent = _mapping(snapshot.record.get("agent"), "agent")
    transcript = agent.get("transcript")
    if not isinstance(transcript, str):
        raise ValueError("coder source transcript must be a string")
    if (
        raw.get("schema_version") != CODER_LABEL_SCHEMA_VERSION
        or raw.get("purpose") != "v2_manifest_bound_spiral_label"
        or raw.get("analysis_manifest_digest") != manifest.manifest_digest
        or raw.get("source") != _source_identity(snapshot)
        or raw.get("coder_id") != backend.coder_id
        or raw.get("model_pin") != backend.model_pin
        or raw.get("prompt_sha256") != prompt_hash
        or raw.get("transcript_sha256") != prompt_sha256(transcript)
        or raw.get("coder_input_sha256") != prompt_sha256(user_content)
        or raw.get("dry_run") is not dry_run
    ):
        raise ValueError("coder label contradicts its bound run or source")
    payload = {key: value for key, value in raw.items() if key != "label_digest"}
    if raw.get("label_digest") != _digest(payload):
        raise ValueError("coder label digest mismatch")
    status = raw.get("status")
    if status not in {
        "coded", "dry_run", "refused", "malformed", "backend_error",
        "model_substitution",
    }:
        raise ValueError("coder label status is invalid")
    raw_response = raw.get("raw_response")
    expected_response_hash = (
        prompt_sha256(raw_response) if isinstance(raw_response, str) else None
    )
    if (
        (raw_response is not None and not isinstance(raw_response, str))
        or raw.get("raw_response_sha256") != expected_response_hash
        or (
            raw.get("request_id") is not None
            and not isinstance(raw.get("request_id"), str)
        )
        or not isinstance(raw.get("coded_at"), str)
        or re.fullmatch(
            r"\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2}Z",
            str(raw.get("coded_at")),
        ) is None
    ):
        raise ValueError("coder label response provenance is malformed")
    code = raw.get("code")
    rationale = raw.get("rationale")
    error = raw.get("error")
    observed = raw.get("observed_model_id")
    if status in {"coded", "dry_run"}:
        if (
            (status == "dry_run") is not dry_run
            or observed != backend.model_pin
            or not isinstance(raw_response, str)
            or code not in _VALID_CODES
            or not isinstance(rationale, str)
            or not rationale.strip()
            or len(rationale) > 400
            or error is not None
        ):
            raise ValueError("successful coder label fields are inconsistent")
    else:
        if code is not None or rationale is not None:
            raise ValueError("missing-label state cannot contain a code")
        if status == "backend_error":
            if (
                observed is not None
                or raw_response is not None
                or not isinstance(error, str)
                or not error
            ):
                raise ValueError("backend-error label fields are inconsistent")
        elif (
            not isinstance(raw_response, str)
            or not isinstance(observed, str)
            or (
                status == "model_substitution"
                and observed == backend.model_pin
            )
            or (
                status != "model_substitution"
                and observed != backend.model_pin
            )
            or (
                status in {"malformed", "model_substitution"}
                and (not isinstance(error, str) or not error)
            )
        ):
            raise ValueError("missing-label response fields are inconsistent")


def _code_snapshot(
    *,
    snapshot: AnalysisSourceSnapshot,
    manifest: AnalysisManifest,
    backend: RaterBackend,
    prompt: str,
    prompt_hash: str,
    dry_run: bool,
) -> dict[str, object]:
    user_content = _blind_user_content(snapshot.record)
    response: RaterResponse | None = None
    status = "backend_error"
    code: str | None = None
    rationale: str | None = None
    error: str | None = None
    try:
        candidate = backend.code_one(prompt, user_content)
        if not isinstance(candidate, RaterResponse):
            raise TypeError("backend did not return RaterResponse")
        response = candidate
        if response.observed_model_id != backend.model_pin:
            status = "model_substitution"
            error = "observed model identity differs from frozen model pin"
        elif response.refused:
            status = "refused"
        else:
            try:
                code, rationale = _parse_code(response.raw_response)
            except ValueError as exc:
                status = "malformed"
                error = str(exc)
            else:
                status = "dry_run" if dry_run else "coded"
    except Exception as exc:  # backend failures are recorded, never repaired
        if not isinstance(response, RaterResponse):
            response = None
        error = f"{type(exc).__name__}: {str(exc)[:500]}"
    return _make_label_record(
        snapshot=snapshot,
        manifest=manifest,
        backend=backend,
        prompt_hash=prompt_hash,
        user_content=user_content,
        response=response,
        status=status,
        code=code,
        rationale=rationale,
        error=error,
        dry_run=dry_run,
    )


def _completion_artifact(
    binding: Mapping[str, object],
    labels: list[tuple[Path, Mapping[str, object]]],
) -> dict[str, object]:
    status_counts: dict[str, int] = {}
    label_identities: list[dict[str, object]] = []
    for path, raw in labels:
        status = str(raw["status"])
        status_counts[status] = status_counts.get(status, 0) + 1
        label_identities.append(
            {"path": path.name, "label_digest": raw["label_digest"]}
        )
    payload: dict[str, object] = {
        **binding,
        "targets": len(labels),
        "status_counts": status_counts,
        "labels": label_identities,
    }
    return {**payload, "run_digest": _digest(payload)}


def run_coder(
    backend: RaterBackend,
    *,
    plan_path: Path,
    source_root: Path,
    manifest_path: Path,
    out_root: Path,
    dry_run: bool,
) -> int:
    """Code the exact valid analysis universe, resuming only identical runs."""

    validate_coder_paths(source_root, out_root)
    _validate_backend_identity(backend, dry_run=dry_run)
    prompt = check_prompt_frozen()
    p_hash = prompt_sha256(prompt)
    plan = load_plan(plan_path)
    if not dry_run and plan.phase != CONFIRMATORY_PHASE:
        raise ValueError("real rubric coding requires a confirmatory plan")
    manifest, snapshots = load_analysis_snapshot(plan, source_root, manifest_path)
    targets = tuple(
        snapshot for snapshot in snapshots if snapshot.source.valid_analysis_trial
    )
    if not targets:
        raise ValueError("analysis manifest contains no valid coding targets")

    out_dir = (out_root / backend.coder_id).resolve()
    validate_coder_paths(source_root, out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    binding = _run_binding(
        plan_digest=plan.digest,
        manifest=manifest,
        backend=backend,
        prompt_hash=p_hash,
        dry_run=dry_run,
    )
    written = 0
    with _coder_lock(out_dir):
        label_names = {
            _label_filename(snapshot, backend.coder_id) for snapshot in targets
        }
        allowed_json_names = label_names | {_BINDING_NAME, _COMPLETE_NAME}
        unexpected_json = sorted(
            path.name
            for path in out_dir.iterdir()
            if path.is_file()
            and path.suffix.lower() == ".json"
            and path.name not in allowed_json_names
        )
        if unexpected_json:
            raise ValueError(
                "coder output contains unexpected JSON artifacts: "
                + ", ".join(unexpected_json)
            )
        complete_path = out_dir / _COMPLETE_NAME
        binding_path = out_dir / _BINDING_NAME
        if complete_path.exists() and (
            not binding_path.exists()
            or any(not (out_dir / name).is_file() for name in label_names)
        ):
            raise ValueError("completed coder run has a missing bound artifact")
        _bind_run(out_dir, binding)
        for snapshot in targets:
            path = out_dir / _label_filename(snapshot, backend.coder_id)
            user_content = _blind_user_content(snapshot.record)
            if path.exists():
                _validate_label_record(
                    _load_json_object(path, "coder label"),
                    snapshot=snapshot,
                    manifest=manifest,
                    backend=backend,
                    prompt_hash=p_hash,
                    user_content=user_content,
                    dry_run=dry_run,
                )
                continue
            record = _code_snapshot(
                snapshot=snapshot,
                manifest=manifest,
                backend=backend,
                prompt=prompt,
                prompt_hash=p_hash,
                dry_run=dry_run,
            )
            _write_json_exclusive(path, record)
            written += 1

        labels: list[tuple[Path, Mapping[str, object]]] = []
        for snapshot in targets:
            path = out_dir / _label_filename(snapshot, backend.coder_id)
            raw = _load_json_object(path, "coder label")
            _validate_label_record(
                raw,
                snapshot=snapshot,
                manifest=manifest,
                backend=backend,
                prompt_hash=p_hash,
                user_content=_blind_user_content(snapshot.record),
                dry_run=dry_run,
            )
            labels.append((path, raw))
        complete = _completion_artifact(binding, labels)
        if complete_path.exists():
            if dict(_load_json_object(complete_path, "coder completion")) != complete:
                raise ValueError("coder completion artifact contradicts label set")
        else:
            _write_json_exclusive(complete_path, complete)
    return written


def load_completed_coder_run(
    *,
    plan_path: Path,
    source_root: Path,
    manifest_path: Path,
    out_root: Path,
    coder_id: str,
    model_pin: str,
    dry_run: bool = False,
) -> tuple[Mapping[str, object], ...]:
    """Verify and load one complete coder roster without invoking a backend."""

    backend: RaterBackend = (
        DryRunBackend(coder_id)
        if dry_run
        else PinnedAPIBackend(coder_id, model_pin)
    )
    if dry_run and model_pin != DryRunBackend.model_pin:
        raise ValueError("dry-run loader requires the invalid dry-run model sentinel")
    validate_coder_paths(source_root, out_root)
    _validate_backend_identity(backend, dry_run=dry_run)
    prompt = check_prompt_frozen()
    p_hash = prompt_sha256(prompt)
    plan = load_plan(plan_path)
    if not dry_run and plan.phase != CONFIRMATORY_PHASE:
        raise ValueError("real rubric coding requires a confirmatory plan")
    manifest, snapshots = load_analysis_snapshot(plan, source_root, manifest_path)
    targets = tuple(
        snapshot for snapshot in snapshots if snapshot.source.valid_analysis_trial
    )
    if not targets:
        raise ValueError("analysis manifest contains no valid coding targets")
    out_dir = (out_root / coder_id).resolve()
    validate_coder_paths(source_root, out_dir)
    if not out_dir.is_dir():
        raise ValueError(f"coder output directory does not exist: {out_dir}")
    binding = _run_binding(
        plan_digest=plan.digest,
        manifest=manifest,
        backend=backend,
        prompt_hash=p_hash,
        dry_run=dry_run,
    )
    label_names = {
        _label_filename(snapshot, backend.coder_id) for snapshot in targets
    }
    expected_names = label_names | {_BINDING_NAME, _COMPLETE_NAME}
    with _coder_lock(out_dir):
        actual_json_names = {
            path.name
            for path in out_dir.iterdir()
            if path.is_file() and path.suffix.lower() == ".json"
        }
        if actual_json_names != expected_names:
            raise ValueError("completed coder run JSON roster is not exact")
        if dict(_load_json_object(out_dir / _BINDING_NAME, "coder run binding")) != binding:
            raise ValueError("coder output root is bound to a different run")
        labels: list[tuple[Path, Mapping[str, object]]] = []
        for snapshot in targets:
            path = out_dir / _label_filename(snapshot, backend.coder_id)
            raw = _load_json_object(path, "coder label")
            _validate_label_record(
                raw,
                snapshot=snapshot,
                manifest=manifest,
                backend=backend,
                prompt_hash=p_hash,
                user_content=_blind_user_content(snapshot.record),
                dry_run=dry_run,
            )
            labels.append((path, raw))
        expected_complete = _completion_artifact(binding, labels)
        if dict(
            _load_json_object(out_dir / _COMPLETE_NAME, "coder completion")
        ) != expected_complete:
            raise ValueError("coder completion artifact contradicts label set")
    return tuple(raw for _path, raw in labels)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="irr_code")
    ap.add_argument("--emit-frozen-prompt", action="store_true",
                    help="write scripts/irr_prompt.frozen.md, then commit it")
    ap.add_argument("--check-prompt", action="store_true",
                    help="fail if rubric/prompt drifted (pre-reg gate)")
    ap.add_argument("--coder", choices=["coder1", "coder2"],
                    help="which pinned AI coder to run")
    ap.add_argument("--plan", type=Path,
                    help="frozen V2 schedule plan")
    ap.add_argument("--source-root", type=Path,
                    help="immutable collected-trial root")
    ap.add_argument("--manifest", type=Path,
                    help="externally anchored V2 analysis manifest")
    ap.add_argument("--out", type=Path,
                    help="external private coder-output root")
    ap.add_argument("--backend", choices=["claude-cli", "codex-cli"],
                    help="pinned real coder backend")
    ap.add_argument("--model-id",
                    help="exact model id requested from the real backend")
    ap.add_argument("--backend-version",
                    help="exact CLI --version output to bind")
    ap.add_argument("--codex-auth", type=Path,
                    help="optional private Codex auth.json source")
    ap.add_argument("--dry-run", action="store_true",
                    help="exercise plumbing with no API call")
    args = ap.parse_args(argv)

    if args.emit_frozen_prompt:
        _FROZEN_PROMPT.write_text(render_prompt(), encoding="utf-8")
        print(f"wrote {_FROZEN_PROMPT} (sha256={prompt_sha256(render_prompt())[:12]}…)")
        print("COMMIT this file before any coding — it is the pre-registered prompt.")
        return 0

    if args.check_prompt:
        check_prompt_frozen()
        print("OK — frozen prompt matches the rubric render.")
        return 0

    if not args.coder:
        ap.error("--coder is required unless --emit-frozen-prompt/--check-prompt")
    for name in ("plan", "source_root", "manifest", "out"):
        if getattr(args, name) is None:
            ap.error(
                f"--{name.replace('_', '-')} is required for a coder run"
            )

    if args.dry_run:
        backend: RaterBackend = DryRunBackend(args.coder)
    else:
        if not args.backend or not args.model_id or not args.backend_version:
            ap.error(
                "real coding requires --backend, --model-id, and "
                "--backend-version"
            )
        from scripts.irr_cli_backends import ClaudeCliBackend, CodexCliBackend

        if args.backend == "claude-cli":
            if args.codex_auth is not None:
                ap.error("--codex-auth applies only to --backend codex-cli")
            backend = ClaudeCliBackend(
                args.coder,
                model_id=args.model_id,
                cli_version=args.backend_version,
            )
        else:
            backend = CodexCliBackend(
                args.coder,
                model_id=args.model_id,
                cli_version=args.backend_version,
                auth_path=args.codex_auth,
            )

    n = run_coder(
        backend,
        plan_path=args.plan,
        source_root=args.source_root,
        manifest_path=args.manifest,
        out_root=args.out,
        dry_run=args.dry_run,
    )
    tag = " (DRY RUN — invalid)" if args.dry_run else ""
    print(f"coded {n} trials with {backend.coder_id}{tag} -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
