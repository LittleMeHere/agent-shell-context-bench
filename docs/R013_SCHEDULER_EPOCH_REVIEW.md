# R-013 scheduler order and epoch review

**Status:** REVIEW COMPLETE — final freeze evidence pending
**Date:** 2026-08-15
**Invariant:** calendar order, host partition, configuration, environment, and
task composition must be prospectively bound and inspectable without using
outcomes; incomplete rosters cannot become decision-bearing analyses

## Independent review result

The production scheduler implements the accepted D-009 valid-slot unit and
one global task-blocked order. The manifest binds all 720 positions; each
host-filtered execution is a stable subsequence, not a new randomization. Four
fixed 180-position epochs each contain 18 complete blocks, 36 positions per
environment, and 90 per configuration. Epoch four contains only the registered
seeded-error repeats, so the H1 sensitivity explicitly reports it as not
applicable rather than comparing unlike task compositions.

The review attempted missing, duplicated, and forged slot coordinates;
repeated-cell adjacency; caller-chosen prefix boundaries; partial epoch
crossings; and unregistered epoch identities. The scheduler or analysis
candidate rejected each invalid construction. The reviewed 92-test slice also
includes the independent linear-combination interval oracle and sparse-cell
fallback boundaries, but it does not substitute for final D-005 acceptance.

```text
python -m pytest tests/test_d009_blocked_rounds.py tests/test_scheduler.py \
  tests/test_v2_analysis_dataset.py tests/test_v2_finite_roster.py -q
92 passed in 25.93s
```

## Current candidate no-call partition exercise

A temporary copy of the current candidate runtime matrix was marked frozen
outside the repository solely to exercise plan construction. No model call or
benchmark trial ran, and this did not accept or publish the matrix. The
resulting current-candidate V2 pilot plan contained 540 cells and 720 valid
slots. Side-effect-free scheduler status was then evaluated independently for
all five host partitions:

| Host partition | Selected cells | Planned valid slots | Execution positions |
|---|---:|---:|---:|
| Windows PowerShell | 108 | 144 | 144 |
| Windows pwsh 7 | 108 | 144 | 144 |
| WSL2 | 108 | 144 | 144 |
| Linux native | 108 | 144 | 144 |
| macOS Actions | 108 | 144 | 144 |

Every partition reported zero existing attempts and created no output root.
Together they reproduce the complete 540-cell/720-slot plan without changing
global order.

## Remaining acceptance boundary

R-013 remains IMPLEMENTED, not VERIFIED. The accepted criterion still needs:

1. final D-005 interval/fallback acceptance;
2. the final frozen runtime-matrix and V2 plan digests; and
3. an outcome-blind dry run of that exact final plan through the authenticated
   host/model partitions with boundary runtime checks.

The independent implementation review and current-candidate no-call partition
exercise are complete and need not be repeated unless scheduler, task, epoch,
or runtime-binding bytes change.
