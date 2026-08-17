# D-006/D-010 production coder assignment

**Status:** ACCEPTED PRE-DATA ASSIGNMENT
**Accepted:** 2026-08-16 under the researcher's authorization to complete the
remaining non-timing work
**Applies to:** exploratory H2/H4 A-F coding

## Assignment

| Role | Frozen backend candidate | Use |
|---|---|---|
| Coder 1 (primary) | Codex CLI `0.147.0`, served model `GPT-5.6 Terra` | One immutable label attempt for every eligible analysis record |
| Coder 2 (independent audit) | Claude Code `2.1.231`, served model `Sonnet 4.6` | Frozen probability sample only; never substitutes for Coder 1 |

Both the exact CLI version and independently observed served-model identity
must match. Drift, refusal, malformed output, backend failure, or model
substitution produces the already-defined immutable missing-label state. It
does not trigger a retry, fallback, role swap, or adjudication rewrite.

## Evidence and rationale

Five matched analysis-excluded calls per backend covered all five workload
strata. Both produced 5/5 parseable labels, exact served-model matches, no
refusals, no prohibited tool calls, and the same five A-F labels. This is
transport qualification, not an accuracy estimate.

Coder 1 runs on the full eligible population, so the faster qualified path is
primary: Codex took 38.397 seconds total (p50 7.445, p90 8.981) versus Claude
at 80.482 seconds (p50 15.304, p90 19.742). Claude remains the independent
different-lineage audit source. The choice uses only pre-data operational
evidence and cannot be changed after outcomes to favor a hypothesis.

This assignment does not freeze the human-anchor/focal-audit sizes, expansion
gate, or routine cap. Those still depend on the registered human timing
exercise and prospective simulation.

