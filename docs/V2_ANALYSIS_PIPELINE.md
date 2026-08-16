# V2 analysis-source, H1 reconstruction, and coder-input boundary

**Status:** IMPLEMENTED CANDIDATE — H1 interval and paid coder-backend
qualification implemented; acceptance, A2-A4, and external anchoring remain
open
**Date:** 2026-08-15
**Code:** `analysis/v2_analysis_dataset.py`,
`analysis/v2_analysis_manifest.py`, `scripts/v2_analysis_manifest.py`,
`scripts/irr_code.py`, `scripts/irr_cli_backends.py`,
`scripts/coder_backend_shakedown.py`

## Implemented boundary

The analysis path now independently reconstructs every scheduled trial before
it can enter a denominator. It verifies:

- trial schema and the complete digest-checked schedule identity;
- trial, family, instance, configuration, model, environment, and phrasing
  agreement with the plan;
- strict validity, completion, timeout, measurement-loss, and executable-
  check evidence;
- the canonical `binary_success_final` and failure indicator;
- accepted D-011 agy transcript eligibility, FIFO-derived parse status, Cwd
  tags/counts/status, and equality between nested and top-level H1 evidence;
- unique attempt/trial identities, no excess valid slots, and exact valid-slot
  completion for every plan cell; and
- the equal-domain, equal-family, equal-instance, equal-configuration finite-
  roster H1 marginal rates, risk difference, and companion risk ratio.

The source-manifest layer records the exact relative path and SHA-256 of every
valid or invalid trial record, refuses to write inside the collection root,
uses the scheduler's exclusive source-root lock during create/load, rechecks
the file roster and byte digests across snapshot passes, and rejects modified,
added, removed, duplicated, foreign, incomplete, or contradictory records.
The CLI self-locates from an external control directory:

```powershell
python "$benchRoot\scripts\v2_analysis_manifest.py" create `
  --plan "$benchRoot\data\v2-plan.json" `
  --source-root C:\immutable-collection\v2 `
  --output C:\pre-data-anchor\v2-analysis-manifest.json

python "$benchRoot\scripts\v2_analysis_manifest.py" verify `
  --plan "$benchRoot\data\v2-plan.json" `
  --source-root C:\immutable-collection\v2 `
  --manifest C:\pre-data-anchor\v2-analysis-manifest.json
```

The manifest's public digest detects accidental or post-freeze changes only
when the manifest is independently anchored. A caller who can replace both
the collection bytes and manifest can recompute a public hash. The real run
must therefore commit the manifest digest outside the mutable collection root
before outcome analysis.

## Implemented coder-input and label boundary

The IRR driver no longer discovers inputs with a filesystem-wide trial glob.
It loads the frozen analysis manifest under the same source-root lock, verifies
the exact file roster and byte digests, independently reconstructs every
record, and selects only manifest-declared valid analysis trials. Real labels
also require a confirmatory plan. Pilot, invalid, unplanned, foreign, added,
removed, and byte-modified records therefore cannot silently enter the coding
universe.

Every exclusive coder artifact binds:

- plan and analysis-manifest digests;
- source path and source-byte digest;
- cell, configuration, trial, valid-slot, execution-position, epoch, attempt,
  task, family, instance, and phrasing identity;
- transcript, blinded coder-input, frozen-prompt, and raw-response hashes; and
- logical coder, frozen model/backend pin, independently observed model id,
  request id, status, code, rationale, and backend usage/timing receipt.

The output root must be external to this public repository and separate from
the immutable collection root. A run-level binding prevents reuse for another
plan, manifest, prompt, coder, model, or dry-run state. Resume accepts only
labels whose complete provenance and self-digest validate, then produces a
deterministic label-set completion digest. Refusal, malformed output, backend
failure, and model substitution are immutable missing-label states: the driver
makes no automatic retry and has no fallback coder. Dry-run output is marked
invalid. Real subscription-CLI execution requires explicit exact model and CLI
version pins. The Claude path disables tools/session persistence and verifies
the requested model in the provider receipt. The Codex path uses a temporary
OAuth home and read-only isolated workspace, rejects tool events, and verifies
the served model from the isolated session record before deleting that home.
Neither backend retries or falls back. Five paid analysis-excluded calls per
backend span all five workload strata and passed model, parse, refusal, and
tool-use gates; exact primary/secondary assignment remains a pre-data choice.

This boundary intentionally sends only the V1-compatible task prompt, binary
outcome, and transcript, with no environment id. It hashes the exact packet
but does not claim to resolve R-018: the V2 canary/filesystem evidence packet,
capability-failure rule, code-E evidence class, and any deterministic post-
coder join remain pre-data decisions.

## Still open

The executable D-005 candidate now includes the finite-roster H1 point
estimate, Clopper-Pearson-MOVER interval, boundary-safe companion RR envelope,
five-point decision classification, and simultaneous exact sparse fallback.
It remains unaccepted pending the full dependence/attrition recovery envelope
and independent review. Planned-epoch sensitivity now reports every epoch
separately, fails closed on incomplete crossings, and marks no-capability
epochs not applicable rather than pooling unlike tasks. A2-A4 models, exact coder
assignment, staged human-audit sampler/threshold/cap, coder join, FDR families,
final tables/figures, and the V2 confirmatory plan remain open. The implemented
boundaries do not decide those remaining statistical or measurement choices
by implication.
