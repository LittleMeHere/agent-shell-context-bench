# D-009 blocked-round candidate evidence

**Status:** ACCEPTED ORDER AND EPOCH CONTRACT IMPLEMENTED — D-005 sensitivity remains
**Date:** 2026-08-12
**Code:** `analysis/d009_blocked_rounds.py`
**Tests:** `tests/test_d009_blocked_rounds.py`

## Result

The current accepted V2 pilot roster expands to exactly 720 valid-trial
slots. The candidate order uses the valid slot—not a raw attempt or completed
cell—as the execution unit. Infrastructure-invalid retries stay attached to
the same slot and cannot change the planned instance or position.

For each valid-slot round, the candidate groups the exact task/phrasing
variant into a block containing its complete configuration-by-environment
crossing. Block order is deterministically shuffled from the registered order
seed. Within-block order is rotated. The resulting current artifact has:

- 720 exact slots in 72 blocks and two rounds;
- zero incomplete configuration/environment block crossings;
- zero configuration imbalances within any host-partition block;
- zero adjacent repetitions of the same cell, versus 180 under whole-cell
  expansion; and
- a deterministic order digest bound to the exact plan inputs.

The previously recorded order digest
`acf77346a107d7bbbd7176e17d7389150e60ee9e75106a01dd847a209af7bb7e`
and plan digest
`47cd68e8348ac511aba06f44de9afed0a5315d98f6f3c18a0381aadae78bd2f0`
are superseded by the 2026-08-14 task-byte changes. They remain historical
evidence for the algorithm but must not identify the final plan. The current
plan/order digests will be recomputed only after the runtime matrix is frozen.

Tests prove exact multiset preservation, deterministic seeding, digest
binding, host-block balance, explicit prefix/epoch reporting, and rejection
of missing, duplicated, or coordinate-forged slots.

Plan schema 1.3 now embeds this exact 720-slot sequence. The production
scheduler executes one V2 valid slot at a time, preserves the registered
subsequence under host/configuration/task filters, and keeps every
infrastructure-invalid retry on the same slot until one valid attempt consumes
it. Schedule-identity schema 1.2 writes the valid-slot index into every child
token, attempt event, and final record; the scanner and independent analysis
builder reject skipped, duplicated, reassigned, or out-of-order slots.

## What this does not decide

The valid-slot randomization unit and production order are now implemented.
D-009 now fixes the pre-specified epoch boundary, single-global-order
cross-host rule, periodic runtime checks, observed-change boundaries, and
incomplete-slot authority. Qualified hosts and the D-005 interval for the
epoch-specific context sensitivity remain open.

`D009_EPOCH_CONTRACT.md` records the accepted exact rule and its
machine-checked 180-slot balance. Its epoch-specific interval still depends on
D-005.

The displayed candidate digest is a reproducibility identifier, not
inferential randomization and not a final frozen V2 artifact. It will change
if any plan-bound task, runtime, or ordering input changes before freeze.
