# D-005 independent implementation review and repair

**Status:** INDEPENDENTLY RE-ACCEPTED — N=36 target accepted subject to cap;
methodology freeze remains open
**Date:** 2026-08-22
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

Both the candidate interval and the standalone point estimator now require
the fully validated `SchedulePlan` itself before constructing any leaf or
weight. They derive the configuration, family, instance, target-count, and
cell-membership roster from that plan, verify every row's plan digest and cell
identity, and invoke the same digest, exact phase-roster, task-hash,
Cartesian-product, runtime, and blocked-order checks as `load_plan()`.
Missing/extra configurations, instances, observations, a count-preserving
instance swap, a row/plan digest mismatch, and a recomputed forged replacement
digest all reject.

Focused evidence:

```text
python -m pytest tests/test_v2_finite_roster.py \
  tests/test_v2_analysis_dataset.py tests/test_scheduler.py \
  tests/test_d005_h1_recovery_envelope.py -q
99 passed
```

The final isolated re-review accepted the implementation boundary and the
previously reviewed CP-MOVER/fallback mechanics. It explicitly leaves exact
N, the selected-N recovery grid, broad-model sensitivity disposition, and
researcher methodology freeze as separate decisions.
