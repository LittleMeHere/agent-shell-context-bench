"""Run a private, analysis-excluded D-006 coder-backend shakedown."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.irr_cli_backends import ClaudeCliBackend, CodexCliBackend
from scripts.irr_code import _blind_user_content, _parse_code, check_prompt_frozen


SCHEMA_VERSION = "1.0.0"


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def _load_object(path: Path) -> Mapping[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, Mapping):
        raise ValueError(f"expected JSON object: {path}")
    return value


def _select_strata(provenance: Mapping[str, object]) -> tuple[Mapping[str, object], ...]:
    raw_cases = provenance.get("cases")
    if not isinstance(raw_cases, list):
        raise ValueError("timing provenance cases must be a JSON array")
    selected: dict[str, Mapping[str, object]] = {}
    for raw in raw_cases:
        if not isinstance(raw, Mapping):
            raise ValueError("timing provenance case must be a JSON object")
        stratum = raw.get("stratum")
        if not isinstance(stratum, str):
            raise ValueError("timing provenance case lacks stratum")
        selected.setdefault(stratum, raw)
    if len(selected) != 5:
        raise ValueError(f"expected five workload strata, found {sorted(selected)}")
    return tuple(selected[stratum] for stratum in sorted(selected))


def run_shakedown(
    *,
    provenance_path: Path,
    output_path: Path,
    backend_name: str,
    coder_id: str,
    model_id: str,
    backend_version: str,
    codex_auth: Path | None = None,
) -> Mapping[str, object]:
    output = output_path.resolve()
    if _is_relative_to(output, _REPO_ROOT):
        raise ValueError("coder shakedown output must use an external private path")
    if output.exists():
        raise ValueError(f"refusing to overwrite coder shakedown: {output}")
    provenance = _load_object(provenance_path)
    if provenance.get("analysis_excluded") is not True:
        raise ValueError("coder shakedown provenance must be analysis-excluded")
    cases = _select_strata(provenance)
    if backend_name == "claude-cli":
        if codex_auth is not None:
            raise ValueError("codex_auth applies only to codex-cli")
        backend = ClaudeCliBackend(
            coder_id, model_id=model_id, cli_version=backend_version
        )
    elif backend_name == "codex-cli":
        backend = CodexCliBackend(
            coder_id,
            model_id=model_id,
            cli_version=backend_version,
            auth_path=codex_auth,
        )
    else:
        raise ValueError(f"unsupported coder shakedown backend {backend_name!r}")

    prompt = check_prompt_frozen()
    receipts: list[dict[str, object]] = []
    for case in cases:
        source_path = Path(str(case.get("source_path"))).resolve()
        source_bytes = source_path.read_bytes()
        if _sha256(source_bytes) != case.get("source_sha256"):
            raise ValueError(f"coder shakedown source digest mismatch: {source_path}")
        source = json.loads(source_bytes)
        if not isinstance(source, Mapping):
            raise ValueError(f"coder shakedown source is not an object: {source_path}")
        response = backend.code_one(prompt, _blind_user_content(source))
        code, rationale = _parse_code(response.raw_response)
        receipts.append(
            {
                "case_id": case.get("case_id"),
                "stratum": case.get("stratum"),
                "source_sha256": case.get("source_sha256"),
                "model_pin": backend.model_pin,
                "observed_model_id": response.observed_model_id,
                "request_id": response.request_id,
                "refused": response.refused,
                "code": code,
                "rationale": rationale,
                "raw_response": response.raw_response,
                "backend_metadata": response.backend_metadata,
            }
        )
    payload: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "purpose": "D-006 analysis-excluded coder backend shakedown",
        "analysis_excluded": True,
        "timing_packet_digest": provenance.get("packet_digest"),
        "backend": backend_name,
        "coder_id": coder_id,
        "model_pin": backend.model_pin,
        "automatic_retries": 0,
        "fallback_model": None,
        "receipts": receipts,
    }
    payload["shakedown_digest"] = _sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return payload


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="coder_backend_shakedown")
    parser.add_argument("--provenance", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--backend", choices=["claude-cli", "codex-cli"], required=True)
    parser.add_argument("--coder", choices=["coder1", "coder2"], required=True)
    parser.add_argument("--model-id", required=True)
    parser.add_argument("--backend-version", required=True)
    parser.add_argument("--codex-auth", type=Path)
    args = parser.parse_args(argv)
    payload = run_shakedown(
        provenance_path=args.provenance,
        output_path=args.out,
        backend_name=args.backend,
        coder_id=args.coder,
        model_id=args.model_id,
        backend_version=args.backend_version,
        codex_auth=args.codex_auth,
    )
    print(
        f"wrote {len(payload['receipts'])} analysis-excluded coder calls; "
        f"digest={payload['shakedown_digest']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
