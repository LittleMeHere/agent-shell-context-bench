# R-014/R-019 external falsification review

**Status:** ACCEPTED WITH REPAIR — reviewer accepted both registered
invariants; one reachable analysis exception was repaired before verification
**Date:** 2026-08-15
**Reviewer:** Claude Sonnet 4.6 through Claude Code 2.1.231, tools disabled,
session persistence disabled
**Scope:** public methodology and implementation excerpts only; no benchmark
outcomes or private operational records were transmitted

## Protected invariants

- **R-014:** a valid timed-out or otherwise incomplete run is a binary failure
  even when its checks or partial artifacts resemble success. The writer and
  analysis reconstruction must reject contradictory records independently.
- **R-019 / D-011:** agy uses the same observable H1 outcome as every other
  agent. Brain and Cwd evidence controls transcript-analysis eligibility and
  diagnostics, but cannot rewrite H1; contradictory nested evidence fails
  closed.

These are already accepted research-design choices. The review tested their
implementation and did not reopen the scientific rule.

## Review custody and disposition

The first packet was malformed by PowerShell array coercion. Every code
section arrived as `System.Object[]`; the reviewer returned `insufficient` and
no result from that call is accepted. Its Claude result UUID was
`82e0690e-66be-4693-82b0-bfb7b84158a7`.

The corrected compact packet serialized the registered hypothesis excerpt,
canonical outcome constructor, writer checks, independent analysis
reconstruction, and the executed 35-test evidence summary. The reviewer
returned `accept` for both R-014 and R-019. Its Claude result UUID was
`a75eb82f-c175-45aa-91b4-d5fea18121f7`.

The reviewer attempted these counterexamples:

1. forged success on a timed-out trial;
2. forged `incomplete` reason on a timed-out trial;
3. Cwd tags supplied with unavailable brain evidence;
4. nested agy H1 success contradicting the top-level timeout result; and
5. forged all-in-sandbox status with no shell commands.

The writer or analysis reconstruction rejected each one through independently
derived evidence.

## Defect found and repaired

The reviewer identified a reachable combination: post-invocation
agent-induced filesystem measurement loss after an agy process returned
incomplete. The registered binary precedence correctly chose `incomplete`,
while the measurement channel separately recorded
`agent_induced_measurement_loss`. The analysis-side agy reconstruction had
incorrectly inferred the measurement-loss flag from the primary binary reason
and could raise a raw `ValueError` instead of accepting the two simultaneous
evidence channels.

`analysis/v2_analysis_dataset.py` now passes the independently reconstructed
measurement status into the agy evidence reconstruction. An adversarial test
constructs the exact incomplete-plus-measurement-loss record and requires one
shared H1 failure plus preserved transcript/Cwd eligibility. This does not
change outcome precedence or methodology.

The review also questioned exact comparison of the serialized Cwd compliance
fraction. Writer and analysis compute the same integer-count ratio, and JSON's
round trip preserves the Python binary float used for that ratio. This remains
a deliberately strict contradiction check, not an inferential calculation.

## Acceptance evidence

```text
python -m pytest tests/test_outcomes.py tests/test_d011_agy_outcome.py \
  tests/test_v2_analysis_dataset.py tests/test_attempt_preservation.py -q
468 passed in 3.03s
```

R-014 and R-019 satisfy their implementation acceptance criteria. Remaining
cross-host collection qualification belongs to R-013/R-016 and does not
reopen these outcome rules.
