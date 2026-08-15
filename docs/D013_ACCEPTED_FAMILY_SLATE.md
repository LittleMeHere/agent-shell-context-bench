# D-013 accepted V2 family slate

**Status:** ACCEPTED DESIGN; 36-INSTANCE CANDIDATE BANK AUTHORED — Q0/Q2/Q4 PARTIAL
**Accepted:** 2026-08-09
**Machine contract:** `config/v2-family-slate.accepted.json`
**Validator:** `analysis/d013_family_slate.py`

## What is fixed

V2 targets practitioner-facing agent-bundle reliability across execution
contexts. It uses six equally weighted content domains, two independently
authored families per domain, and three frozen instances per family. The slate
fixes content coverage before development outcomes are observed; it does not
select tasks because a named environment happened to fail.

| Domain | Family 1 | Family 2 |
|---|---|---|
| Filesystem/artifacts | C01 precise nested artifacts | C04 recursive artifact inventory |
| Data/config/text | C02 quoted CSV normalization | C05 recursive configuration merge |
| Repository/code change | C03 semantic symbol rename | C06 cross-file behavioral bug repair |
| Version control | C07 semantic merge-conflict resolution | C08 selective bad-change recovery |
| Build/test/package | C09 failing test/build repair | C10 deterministic local package assembly |
| Runtime/system operations | C11 local-service health recovery | C12 bounded batch-job execution |

The machine contract also fixes each family's workflow analogue, plausible
context link, excluded construct, three canonical instance IDs, oracle, at
least four counter-policies, and six-demand exposure map. Its validator
requires every cross-cutting demand to recur in at least two families across
at least two domains with a `STRONG` exposure somewhere.

## What has now been implemented

- `tasks/v2/` contains all 36 distinct candidate instances. The structural
  validator in `analysis/d013_task_bank.py` binds their IDs and byte digests
  to the accepted 12-by-3 slate. The current candidate-bank digest is
  `528b70694d29e22cf54fc487f2df64b016251f5a318c9691df0d57ece2f3c47b`.
- C07/C08 use real Git repository, graph, index, worktree, and merge-conflict
  fixtures plus argv-based semantic Git-state oracles. C11 uses a fixture-
  assigned free loopback port and fails when the assigned listener remains
  occupied. These are not filesystem-only imitations.
- Every instance has a known-positive completion and a no-op failure test.
  Every instance also rejects an unexpected artifact and corrupted protected
  content; Git tasks assert the complete allowed porcelain status, and C11
  has a live leftover-listener adversary.
- C06 and C09 behavioral predicates include unseen inputs rather than only
  prompt-visible examples. Six independently written valid implementations
  pass those predicates, while six implementations that special-case only
  the visible examples fail.
- Schedule-plan schema 1.3, schedule-identity schema 1.2, attempt schema 1.3,
  and trial schema 1.7 carry family ID, instance ID, and instance SHA-256.
  The accepted V2 pilot plan is executable as a deterministic 540-cell,
  720-valid-trial roster: one trial per capability instance and two per
  seeded variant in each Claude configuration/environment.
- Blinded-export schema 1.1 signs those instance identities and validates the
  exact V1 or V2 roster. A synthetic signed 720-row V2 export round-trip is
  covered by regression tests.

## What is deliberately not claimed

The candidate bank is not yet admitted and the digest above is not a Q4 final
freeze. The 217-check executable Q2 audit covers all 36 independently authored
valid alternates and every accepted H1-visible counter-policy, but it does not
establish five-environment equivalence, fresh-human solvability, transcript-
level grader adjudication, or calibrated difficulty. No development-agent
outcome has been used to select or modify an instance.

Q1 still requires clean completion on macOS and fresh-human review. Q2 still
requires transcript adjudication over development attempts. Q3 requires context-blinded development
calibration and the accepted symmetric gate. Q4 still requires the final
D-005 interval/epoch contract, independent H1-builder review, and a final
digest after any Q1-Q3 repair. The exact 720-slot blocked order is now
production-bound and the equal-weight H1 point estimator is implemented;
neither makes the current bank a final Q4 freeze.

## Next qualification batch

1. Execute portable oracle completions on macOS and record tool/version,
   duration, cleanup, and instance-level failures.
2. Run fresh-human prompt/predicate review and transcript-level adjudication
   over the executable Q2 development cases.
3. Freeze the Q3 development envelope, then run only the accepted blinded
   calibration; do not select instances for a named context effect.
4. Complete D-005 interval/epoch recovery, freeze final digests, and rerun the
   full V2 pilot dry-run before
   any paid attempt.

This order is load-bearing. Running development agents before the family and
oracle contracts are fixed would allow observed effects to influence item
selection. Running a paid pilot before the 12-family bank is qualified would
only repeat the V1 construct problem at greater cost.
