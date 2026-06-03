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
  * Coders receive ONLY the task prompt, the transcript, and the binary
    outcome — never the environment id / probe. (Residual, disclosed
    limitation: a transcript often reveals its own shell; see SAP S4.)
  * Each label is written with the prompt hash and the pinned model id, so
    any third party can re-run and reproduce the exact labels.

The actual model API call is intentionally a PINNED STUB (see RaterBackend).
Like the Claude Code adapter, exact model ids + SDK are pinned at experiment
start, not guessed here. `--dry-run` exercises all plumbing with no API.

Usage:
  python scripts/irr_code.py --emit-frozen-prompt        # one-time, then commit
  python scripts/irr_code.py --check-prompt              # CI / pre-reg gate
  python scripts/irr_code.py --coder coder1 --data data/ --dry-run
  python scripts/irr_code.py --coder coder1 --data data/ --out analysis/irr/
"""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import sys
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path

_BENCH_ROOT = Path(__file__).resolve().parents[1]
if str(_BENCH_ROOT) not in sys.path:
    sys.path.insert(0, str(_BENCH_ROOT))

from harness.classifier.rubric import RUBRIC, SpiralCode  # noqa: E402

_FROZEN_PROMPT = _BENCH_ROOT / "scripts" / "irr_prompt.frozen.md"
_VALID_CODES = {c.value for c in SpiralCode}


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

class RaterBackend(ABC):
    coder_id: str
    model_pin: str  # exact model id+version, frozen at experiment start

    @abstractmethod
    def code_one(self, system_prompt: str, user_content: str) -> str:
        """Return the raw model response (expected: the strict JSON object)."""


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

    def code_one(self, system_prompt: str, user_content: str) -> str:
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

    coder_id = "dryrun"
    model_pin = "DRYRUN-not-a-model"

    def code_one(self, system_prompt: str, user_content: str) -> str:
        return json.dumps({"code": "A", "rationale": "DRY RUN — not a real label"})


# --------------------------------------------------------------------------
# Coding loop
# --------------------------------------------------------------------------

def _blind_user_content(trial: dict) -> str:
    """Everything the rater sees. Deliberately excludes env id / probe."""
    return (
        f"TASK PROMPT:\n{trial.get('prompt','')}\n\n"
        f"OUTCOME: {'success' if trial.get('outcome',{}).get('success') else 'failure'}\n\n"
        f"TRANSCRIPT:\n{trial.get('agent',{}).get('transcript','')}\n"
    )


def _parse_code(raw: str) -> tuple[str, str]:
    try:
        obj = json.loads(raw)
        code = str(obj["code"]).strip().upper()
        rationale = str(obj.get("rationale", ""))
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        raise ValueError(f"unparseable rater output: {exc}: {raw[:200]!r}")
    if code not in _VALID_CODES:
        raise ValueError(f"invalid code {code!r}; must be one of {_VALID_CODES}")
    return code, rationale


def run_coder(
    backend: RaterBackend, data_root: Path, out_root: Path, dry_run: bool
) -> int:
    prompt = check_prompt_frozen()
    p_hash = prompt_sha256(prompt)
    # NOTE 2026-05-23: explicitly exclude `data/pre-registration/` per
    # data hygiene policy. Smoke trials run before pre-registration tag
    # live under that subtree and must not enter analysis. See
    # `data/pre-registration/README.md`.
    trial_files = sorted(
        tf for tf in data_root.rglob("trial_*.json")
        if "pre-registration" not in tf.parts
    )
    if not trial_files:
        raise SystemExit(
            f"no trial_*.json under {data_root} "
            "(pre-registration smoke trials are excluded by policy)"
        )

    out_dir = out_root / backend.coder_id
    out_dir.mkdir(parents=True, exist_ok=True)
    n = 0
    for tf in trial_files:
        trial = json.loads(tf.read_text(encoding="utf-8"))
        raw = backend.code_one(prompt, _blind_user_content(trial))
        code, rationale = _parse_code(raw)
        rec = {
            "trial_file": tf.name,
            "task_id": trial.get("trial", {}).get("task_id"),
            "coder_id": backend.coder_id,
            "model_pin": backend.model_pin,
            "prompt_sha256": p_hash,
            "code": code,
            "rationale": rationale,
            "dry_run": dry_run,
            "coded_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ"),
        }
        (out_dir / f"{tf.stem}__{backend.coder_id}.json").write_text(
            json.dumps(rec, indent=2), encoding="utf-8"
        )
        n += 1
    return n


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="irr_code")
    ap.add_argument("--emit-frozen-prompt", action="store_true",
                    help="write scripts/irr_prompt.frozen.md, then commit it")
    ap.add_argument("--check-prompt", action="store_true",
                    help="fail if rubric/prompt drifted (pre-reg gate)")
    ap.add_argument("--coder", choices=["coder1", "coder2"],
                    help="which pinned AI coder to run")
    ap.add_argument("--data", default=str(_BENCH_ROOT / "data"))
    ap.add_argument("--out", default=str(_BENCH_ROOT / "analysis" / "irr"))
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

    if args.dry_run:
        backend: RaterBackend = DryRunBackend()
    else:
        # Pinned at experiment start (SAP S4) — different lineages.
        pins = {
            "coder1": ("coder1", "PIN-AT-START:lineage-A-model@version"),
            "coder2": ("coder2", "PIN-AT-START:lineage-B-model@version"),
        }
        backend = PinnedAPIBackend(*pins[args.coder])

    n = run_coder(backend, Path(args.data), Path(args.out), args.dry_run)
    tag = " (DRY RUN — invalid)" if args.dry_run else ""
    print(f"coded {n} trials with {backend.coder_id}{tag} -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
