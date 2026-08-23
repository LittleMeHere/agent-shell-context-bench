# V2 analysis-source, H1 reconstruction, and coder-input boundary

**Status:** IMPLEMENTED CANDIDATE — H1 interval, paid coder-backend
qualification/assignment, r005 evidence join, staged audit, confirmatory
design lock, and A2-A4/reporting candidate implemented; final acceptance and
external anchoring remain open
**Date:** 2026-08-16
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
tool-use gates. Codex CLI 0.147.0 / GPT-5.6 Terra is frozen as population-wide
Coder 1; Claude Code 2.1.231 / Sonnet 4.6 is frozen as probability-sampled
Coder 2. The rationale is recorded in `docs/D006_CODER_ASSIGNMENT.md`.

The r005 boundary sends a digest-bound evidence packet without explicit
identity labels and does not claim identity blindness: evidential commands,
paths, shell syntax, and wrappers can still reveal agent/environment identity.
It preserves raw and final codes and applies the accepted deterministic D/E
evidence join. Both pinned AI coders passed all 12 current r005 goldens. The
human golden and exact probability-sample manifest remain open.

## Still open

The executable D-005 candidate now includes the finite-roster H1 point
estimate, Clopper-Pearson-MOVER interval, boundary-safe companion RR envelope,
five-point decision classification, and simultaneous exact sparse fallback.
The prospective H1 dependence/drift recovery envelope now passes all 32
tested cells at N=24; attrition remains fail-closed as an incomplete roster,
not a complete-case analysis branch. The interval remains unaccepted pending
independent re-acceptance after repair of the whole-configuration-roster
counterexample, broad-model sensitivity disposition, and researcher freeze.
Planned-epoch sensitivity reports every epoch
separately, fails closed on incomplete crossings, and marks no-capability
epochs not applicable rather than pooling unlike tasks. A2-A4 models, staged
human-audit sampling, coder join, and generated reporting now exist as
candidates. Independent review blocked A2-A4 acceptance on exact phase and
design-lock binding, H1 coherence, A3 multiplicity, scarcity and epoch rules,
reporting firewalls, audit/provenance sensitivities, and evidence-transition
retention. The candidate is therefore not frozen and must not be used for
confirmatory claims until those gaps are repaired and independently accepted.
