# R-016 scheduler-to-record binding review

**Status:** VERIFIED
**Date:** 2026-08-15
**Invariant:** every scheduled child, attempt event, final trial, output scan,
and downstream reconstruction is bound to the same immutable plan coordinate
before any outcome can enter a roster
**Scope:** implementation, falsification tests, and analysis-excluded
cross-host receipts; no benchmark outcome was inspected or collected

## Independent implementation review

The review traced the registered provenance boundary through:

1. `harness/scheduler.py`, which derives the plan-owned identity and passes a
   base64url token to each child;
2. `harness/schedule_identity.py`, which validates the closed schema, field
   types, slot bounds, and canonical payload digest;
3. `harness/runner.py`, which checks task bytes and requested coordinates
   before constructing an environment or agent adapter;
4. `harness/attempts.py` and `harness/logging/writer.py`, which carry the same
   validated identity into every immutable attempt event and final record;
5. the scheduler output scanner, which compares the record identity to the
   plan-owned identity rather than trusting paths or a self-consistent token;
   and
6. `analysis/v2_analysis_dataset.py`, which again reconstructs the plan-owned
   identity before accepting an analysis row.

The token is tamper-evident provenance, not a security signature. A child
cannot independently know the outer plan's phase/digest/cell, so the outer
scanner's exact comparison is load-bearing. The implementation preserves that
separation: child validation blocks coordinate/task corruption before launch,
while scanner and analysis validation block a validly re-hashed foreign token.

## Counterexamples and focused evidence

The reviewed tests reject:

- wrong phase, plan digest, cell, task hash, family/instance, schema, and N;
- copied records under another plan;
- a foreign cell token placed under a matching visible output path;
- missing schedule identity in either a trial or attempt event;
- corrupted token bytes and validly re-hashed foreign identities;
- child task/environment mismatch before adapter construction;
- duplicate indices, overcollection, incomplete slots, and stale schemas; and
- scheduler/exporter disagreement about commitment-bearing evidence.

The focused provenance suite completed with:

```text
124 passed in 159.74s
```

## Independent cross-host receipt reconstruction

`scripts/r016_receipt_audit.py` reconstructs the expected schedule identity
directly from the immutable analysis-excluded shakedown manifest. It validates
the exact receipt artifact inventory and hashes, one final trial, all four
attempt lifecycle events, every repeated schedule identity, trial coordinates,
and the terminal event's path/hash link. Receipt-root precedence is explicit;
duplicates within one root and incomplete compositions fail closed. The tool
emits aggregate evidence only and never raw paths or model output.

Applied to the corrected accepted composition, it independently found:

```text
manifest ee6f15cf6b677d24bb2612b4202468ffb2ae41086d68e6f2c8389b895020e023
82 calls; 410 artifacts; 328 attempt events
windows_powershell 70; windows_pwsh7 3; windows_wsl2 3;
linux_native 3; macos_actions 3
CFG1 10; CFG2 14; CFG3 10; CFG4 14; CFG5 10; CFG6 14; CFG7 10
composition 92519494dabb68efda1ef89607880bf4234f2095b5a2cd9ba8dfcb48869a9f23
```

The audit's own adversarial test re-hashes the enclosing receipt after
corrupting the trial's schedule phase; schedule validation still rejects it.
This demonstrates that receipt integrity cannot conceal a contradictory child
identity.

## Remaining boundary

These calls prove the cross-host child/record mechanism against the current
runtime and task bytes, but they are analysis-excluded shakedown slots rather
than the final V2 pilot roster. Freezing the final V2 plan/runtime digest and
running its outcome-blind host-partition dry run remain D-009/R-013/G3 work.
They do not reopen R-016's binding implementation.
