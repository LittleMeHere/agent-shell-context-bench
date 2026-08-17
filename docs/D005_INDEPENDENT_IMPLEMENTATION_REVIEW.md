# D-005 independent implementation review and repair

**Status:** BLOCKING COUNTEREXAMPLE REPAIRED; independent re-acceptance pending
**Date:** 2026-08-16
**Scope:** `analysis/v2_finite_roster.py`, its focused tests, and the
prospective D-005 recovery envelope

## Review result

An isolated, read-only Codex/GPT-5.6 Terra review rejected the candidate for
one blocking reason: `_finite_roster_cells()` inferred the configuration
roster from observed rows. Removing every `CFG2` row from both focal contexts,
or adding a complete `CFG8`, therefore changed the estimand instead of
stopping analysis.

The reviewer otherwise found the signed-coefficient CP-MOVER construction,
Clopper-Pearson limits, Bonferroni allocation, sparse fallback, and boundary-
safe risk-ratio envelope internally coherent. It also correctly noted that a
simultaneous sparse fallback need not always be inconclusive when the signal
is extreme; the implementation description no longer makes that stronger
claim.

## Repair

The estimator now requires the exact registered `CFG1`-`CFG7` roster before
constructing any leaf or weight. Missing and extra whole configurations are
reported explicitly and raise `AnalysisDatasetError`. The ordinary complete-
crossing check remains in force within that fixed roster.

Focused evidence:

```text
python -m pytest tests/test_v2_finite_roster.py \
  tests/test_d005_h1_recovery_envelope.py -q
19 passed
```

The new regression test executes both counterexamples named by the reviewer.
The original review was not converted into an acceptance after the repair;
the exact interval remains a freeze candidate until independent re-acceptance
and researcher freeze are recorded.

