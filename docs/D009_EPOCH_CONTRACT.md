# D-009 epoch and incomplete-roster contract

**Status:** ACCEPTED
**Accepted:** 2026-08-13
**Evidence:** `analysis/d009_blocked_rounds.py`; `tests/test_d009_blocked_rounds.py`

## Accepted contract

1. The prospectively registered valid slot remains the collection unit.
   Infrastructure-invalid attempts retry the same slot and never advance the
   schedule.
2. Execute the single global plan order. Remote hosts follow that order through
   their adapters; separately launched host-filtered runs are recovery tools,
   not independent schedules.
3. Define four outcome-blind planned epochs at positions 180, 360, 540, and
   720. Each epoch contains 18 complete task blocks, 36 slots from every
   environment, and 90 slots from each configuration. Thus calendar position
   is not confounded with environment or configuration by construction.
4. Run the frozen zero-quota runtime check before slot 0, at every 180-slot
   boundary, and after any pause longer than six hours or quota reset. A pin
   mismatch stops collection before another paid invocation.
5. Record actual start/finish times and runtime evidence for every attempt.
   Record any externally observed provider routing/model event as an additional
   boundary; it does not retroactively replace the four planned epochs.
6. The primary confirmatory result requires every registered valid slot. No
   complete-case subset, imputation, reweighting, or silent target reduction is
   allowed. If the exact roster cannot be completed under the frozen runtime,
   the confirmatory collection is incomplete and has no decision-bearing A1
   result.
7. The fixed sensitivity reports the context contrast separately in each
   planned epoch using only the task/configuration blocks present in that
   epoch. It also reports any externally observed change boundary. The primary
   estimator is unchanged; a materially incompatible epoch pattern must be
   described as temporal fragility rather than removed after inspecting
   outcomes.

## Exact balance evidence

The current 720-slot order partitions as follows:

| Epoch | Positions | Complete blocks | Each environment | CFG1 | CFG2 | Capability | Seeded error |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 0 | 0–179 | 18 | 36 | 90 | 90 | 120 | 60 |
| 1 | 180–359 | 18 | 36 | 90 | 90 | 120 | 60 |
| 2 | 360–539 | 18 | 36 | 90 | 90 | 120 | 60 |
| 3 | 540–719 | 18 | 36 | 90 | 90 | 0 | 180 |

The fourth epoch contains the registered repeat slots and therefore only
seeded-error tasks. Epoch comparisons must preserve this task composition;
raw across-epoch failure-rate differences are not interpretable as drift.

## Remaining implementation boundary

This contract closes the epoch-boundary and incomplete-slot policy portions of
D-009. Production scheduler constants and the independent analysis builder
derive the epoch directly from the digest-bound execution position. The exact
statistical interval for epoch-specific context contrasts remains part of
D-005, and authenticated host/model qualification remains an execution gate.
