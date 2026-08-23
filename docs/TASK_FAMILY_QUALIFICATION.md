# D-013 candidate task-family qualification protocol

**Status:** PARTIAL — FIVE-HOST ORACLES AND EXECUTABLE Q2 PASS; HUMAN/Q3/Q4 REMAIN
**Created:** 2026-08-01
**Decision:** D-013
**Finding:** R-022
**Applies to:** proposed V2 capability-task development only
**Does not modify:** frozen V1 YAMLs, `harness/scheduler.py`, the
preregistration, or any collection plan

## 1. Purpose

This protocol converts the construct audit into a reviewable admission gate
for candidate capability-task families. Its purpose is to prevent task
authors, future agents, and reviewers from treating “the YAML runs” or “a
frontier model failed” as sufficient evidence that a task belongs in the
confirmatory bank.

A task family is not V2-qualified until D-013 accepts the applicable rules and
the family has evidence for every required gate below. Prototype code and
development attempts remain non-confirmatory evidence.

## 2. Units and status vocabulary

- **Family:** an independently authored workflow with a shared goal and
  scoring logic.
- **Instance:** frozen input state within one family.
- **Repetition:** one stochastic agent attempt on an assigned instance.
- **Historical V1 fixture:** one of C01-C05; it does not automatically qualify
  the corresponding three-instance V2 family.
- **Candidate instance:** an authored V2 YAML that remains amendable until Q4
  and is excluded from confirmatory inference until all gates pass.

Qualification states are `NOT ASSESSED`, `PARTIAL`, `PASS`, and `REJECT`.
`PARTIAL` never satisfies an admission gate. `PASS` means the recorded
evidence meets the rule D-013 eventually accepts; it does not mean that an
agent usually succeeds.

## 3. Candidate content bank

| Domain | Authored candidate families | Instances |
|---|---|---:|
| A. Filesystem/artifacts | C01, C04 | 6 |
| B. Data/config/text | C02, C05 | 6 |
| C. Repository/code change | C03, C06 | 6 |
| D. Version control | C07, C08 | 6 |
| E. Build/test/package | C09, C10 | 6 |
| F. Runtime/system operations | C11, C12 | 6 |
| **Total** | **12** | **36** |

This is the accepted V2 content scaffold. Acceptance does not itself prove
that the six domains are representative or that any family has passed Q0–Q4.
The exact accepted family definitions, planned instance IDs, oracle summaries,
counter-policies, demand map, and harness prerequisites are frozen in
`config/v2-family-slate.accepted.json` and explained in
`docs/D013_ACCEPTED_FAMILY_SLATE.md`. The accepted-slate file retains its
pre-authoring `NOT_ASSESSED` labels. Current implementation evidence is
tracked here: all families are `PARTIAL`, never `PASS`.

## 4. Cross-cutting demand map

Each family must be labeled against these demands:

1. environment discovery and localization;
2. command and shell composition;
3. diagnosis and recovery;
4. preservation and scope control;
5. output verification and test use;
6. environment-aware tool adaptation.

Use three exposure labels:

- `STRONG`: the task creates an authentic need and observable opportunity for
  the demand under multiple reasonable solution policies;
- `CONDITIONAL`: exposure depends materially on tool or solution policy;
- `ABSENT`: the family does not meaningfully elicit the demand.

These labels describe task affordances, not observed agent behavior and not a
causal mechanism. A successful agent may still avoid a `STRONG` affordance,
and a lucky output does not prove verification behavior.

Before D-013 acceptance, publish the full family-by-demand matrix. The current
candidate recurrence rule is that every demand appears in at least two
independently authored families spanning at least two content domains, with at
least one `STRONG` exposure where compatible with free tool choice. This rule
is accepted as the minimum recurrence rule and must still be challenged
during task authoring; free tool choice
must not be covertly replaced by mandatory shell use merely to satisfy it.

## 5. Family admission gates

### Q0 — identity, independence, and construct fit

Required record:

- stable family ID and version;
- content-domain label and cross-cutting-demand labels;
- real workflow analogue and why context could plausibly affect success when
  the agent retains free tool choice;
- important simplifications and what the family does not measure;
- provenance, author, and independence from other families;
- explanation of why instances share one family rather than representing
  independent workflows.

Reject when the task is a cosmetic variation of an admitted family, tests a
mandatory shell syntax policy instead of bundle reliability, or has no
plausible link between execution context and end-to-end success.

### Q1 — semantic equivalence and solvability

Required record:

- platform-neutral outcome specification;
- identical information and success semantics in all five environments;
- portable oracle completion for every frozen instance in every environment;
- required-tool availability or an explicit environment-independent setup;
- fresh-human completion by someone who did not author the family;
- review of time, permissions, paths, line endings, encodings, locale, ports,
  process lifetime, and cleanup where relevant.

Reject when a context makes the requested outcome impossible, materially
changes the task, or adds incidental difficulty unrelated to the intended
bundle treatment. Platform-specific commands may differ; the requested
outcome and available affordances must remain substantively comparable.

The number of fresh-human attempts remains an open D-013 resource decision.
At least one successful fresh-human attempt per family is the candidate
minimum, not an approved threshold or a population-level human baseline.

### Q2 — outcome and grader validity

Required record:

- one canonical executable mapping from every prompt requirement to the H1
  predicate or an explicit H2/H4-only exclusion;
- known-positive oracle fixtures;
- no-op, partially correct, malformed, extra-artifact, destructive, and
  environment-specific counter-policies;
- evidence that functionally valid alternate solutions pass regardless of
  irrelevant implementation detail;
- evidence that shortcut and incomplete solutions fail;
- task-level false-positive and false-negative adjudication over development
  attempts;
- manual review of successful and failed agent transcripts.

Reject when hidden requirements exceed the prompt, tests enforce an
unimportant implementation detail, incomplete work can pass, or legitimate
solutions fail. A difficult but defective grader is not a hard task.

### Q3 — difficulty and information calibration

Required record:

- human completion time and structural difficulty notes;
- aggregate, context-label-masked development-agent success and invalid-attempt
  counts;
- transcript-supported failure mechanisms;
- blinded simulations of the candidate ceiling/floor rule;
- evidence that no task was selected because it produced a favorable named
  context effect;
- a declared response if the pilot is all-success or all-failure.

Difficulty is not defined by one target model’s pass rate. Routine tasks may
remain if they represent the construct; hard tasks may remain if their
difficulty is intrinsic and fair. Selection based only on producing failures
would convert the bank into an adversarial stress test.

The accepted pilot rule requires at least five failures and five successes,
with each outcome represented in at least two families. Fewer than five
failures is `CEILING`; fewer than five successes is `FLOOR`; an outcome found
in only one family is `CONCENTRATED`. Those three branches stop confirmatory
collection. Any outcome-relevant task repair requires a V2 amendment, a new
task-bank digest, and a fresh pilot. Concentration within one domain while at
least two families contribute is a reported diagnostic, not an automatic
stop. The allowed development models, fixed attempt count, and transcript
adjudication batch remain to be frozen; no family is selected or rejected
solely for being easy or for producing C/D/E labels.

### Q4 — freeze, assignment, and auditability

Required record:

- frozen prompt, preconditions, success predicate, notes, and task digest;
- frozen instance IDs, contents, and digests;
- deterministic family/configuration/environment/repetition assignment;
- proof that paired context cells receive identical instances;
- separate immutable attempt identity and target valid-slot identity;
- an invalid-attempt replacement rule that retries the same valid slot and
  instance, while an agent-caused valid failure consumes the slot;
- a retry-cap and missing-slot rule that fails visibly rather than silently
  substituting another instance or renormalizing the completed slots;
- declared analysis weights for unequal instance counts;
- an analysis rule that preserves family, instance, and matched-slot
  dependence rather than treating weighted trials as independent;
- versioned oracle and counter-policy results;
- amendment rule requiring new qualification and fresh pilot data after any
  outcome-relevant change;
- public/private artifact classification and redaction review.

Reject when the task or instance can drift after scheduling, instance identity
is absent from the trial record, or a change can reuse pilot data as though
the instrument were unchanged.

`analysis/d013_task_bank_design.py` is an executable candidate for the
instance-assignment part of Q4. It is evidence code only. The frozen V1
scheduler must not import it. The prototype fails closed unless it receives
the exact registered seven-configuration and five-environment rosters.

## 6. Candidate instance-assignment invariant

For a multi-instance family:

1. freeze at least three instances;
2. require enough repetitions to exercise every instance within every
   family-by-configuration-by-environment cell;
3. reuse the same instance at a given family/configuration/repetition
   coordinate in all five environments;
4. rotate remainder repetitions over configurations when `N_cap` is not a
   multiple of the instance count;
5. average trials to equal-weight instances within family, rather than giving
   the remainder instance more estimand weight;
6. then weight families within domains and domains according to the D-013
   estimand.

Here “repetition” means a target valid-trial slot, not a raw attempt index.
Infrastructure-invalid attempts receive unique immutable attempt IDs but do
not advance the valid slot. Their replacements remain bound to the same
instance. This prevents replacement patterns from changing the frozen
instance mixture. A valid agent-caused failure is outcome data and consumes
the slot normally.

If a retry cap expires before a slot receives a valid attempt, the candidate
schedule is incomplete. D-013/D-009 must pre-specify whether that triggers
additional replacement authority, a cell-level integrity failure, or a
study-level stop. It must not be repaired by silently dropping the slot,
substituting another instance, or renormalizing the surviving trials.

The stable family hash and configuration rotation are deterministic binding
devices, not randomized treatment assignment and not a basis for
randomization inference. This prototype does not set trial execution order or
counterbalance time, cache, host, configuration-order, or agent-order effects;
those remain D-009 scheduler responsibilities. The accepted D-001/D-003/D-005
analysis must also preserve the matched family/instance/slot structure when
estimating uncertainty.

One fixed fixture is allowed only when D-013 explicitly defines that fixed
fixture as the family’s population. Two instances are disallowed by the
candidate prototype because the audit’s stated minimum is either a fixed
fixture or at least three frozen instances. This is an open design rule, not a
claim that three instances establish external validity.

## 7. Current candidate-bank qualification audit

| Family | Domain | Q0 | Q1 | Q2 | Q3 | Q4 | Principal remaining gap |
|---|---|---|---|---|---|---|---|
| C01 | A | PARTIAL | PARTIAL | PARTIAL | PARTIAL | PARTIAL | fresh-human and transcript criterion review |
| C02 | B | PARTIAL | PARTIAL | PARTIAL | PARTIAL | PARTIAL | fresh-human and transcript quoting/encoding review |
| C03 | C | PARTIAL | PARTIAL | PARTIAL | PARTIAL | PARTIAL | transcript alternate-renames and human criterion review |
| C04 | A | PARTIAL | PARTIAL | PARTIAL | PARTIAL | PARTIAL | transcript hidden-file/hash and human review |
| C05 | B | PARTIAL | PARTIAL | PARTIAL | PARTIAL | PARTIAL | transcript merge-semantics and human review |
| C06 | C | PARTIAL | PARTIAL | PARTIAL | PARTIAL | PARTIAL | fresh-human and transcript shortcut review |
| C07 | D | PARTIAL | PARTIAL | PARTIAL | PARTIAL | PARTIAL | fresh-human and transcript conflict review |
| C08 | D | PARTIAL | PARTIAL | PARTIAL | PARTIAL | PARTIAL | fresh-human and transcript reset review |
| C09 | E | PARTIAL | PARTIAL | PARTIAL | PARTIAL | PARTIAL | fresh-human and transcript test-tamper review |
| C10 | E | PARTIAL | PARTIAL | PARTIAL | PARTIAL | PARTIAL | fresh-human and transcript alternate review |
| C11 | F | PARTIAL | PARTIAL | PARTIAL | PARTIAL | PARTIAL | fresh-human port/process and transcript review |
| C12 | F | PARTIAL | PARTIAL | PARTIAL | PARTIAL | PARTIAL | fresh-human environment/secret and transcript review |

The rows remain unadmitted because local executable evidence is not a complete
Q0-Q4 package. The current structural bank digest is recorded in
`D013_ACCEPTED_FAMILY_SLATE.md`; it remains candidate evidence until Q4.

The current bank digest
`528b70694d29e22cf54fc487f2df64b016251f5a318c9691df0d57ece2f3c47b`
has cleared a meaningful part of Q1/Q2: every untouched fixture failed and
every registered oracle passed for all 36 instances on native Windows
PowerShell 5.1, Windows pwsh 7.6.4, WSL2 Ubuntu 24.04.4, fresh GCP Ubuntu
24.04.4, and the qualified macOS ARM64 runner (180 portable oracle
completions, zero model calls). The combined four-host artifact below and the
later macOS qualification record together establish the five-host result. The
four-host analysis-excluded evidence artifact has SHA-256
`dfe021ef67f4f8ac4b79b796a7a90ab4b2548e7a35c5f795ff28bfac7fa85436`.
The executable Q2 audit passes 217 checks: 36 independently authored valid
alternates pass, every accepted H1-visible counter-policy fails, and H2/H4-
only surfaces remain excluded from H1. Fresh-human solvability and
transcript-level development-attempt adjudication remain open, so no row is
promoted to `PASS`.

### Provisional affordance map

`S` = strong, `C` = conditional on solution/tool policy, `—` = absent or not
established by the audit.

| Family | Discovery | Shell composition | Diagnosis/recovery | Scope control | Verification | Tool adaptation |
|---|---:|---:|---:|---:|---:|---:|
| C01 | — | C | — | S | C | C |
| C02 | — | C | — | S | C | C |
| C03 | S | C | C | S | S | C |
| C04 | S | C | C | S | S | C |
| C05 | C | C | C | S | S | C |

This map exposes two weaknesses. Shell composition and tool adaptation are
policy-conditional under free tool choice, which is expected. More
importantly, no current family strongly elicits diagnosis/recovery, and the
bank’s strong affordances are concentrated in scope preservation and output
construction/verification.

## 8. Required family evidence record

Every candidate family should receive one versioned record with these fields:

```text
family_id:
family_version:
status: NOT ASSESSED | PARTIAL | PASS | REJECT
content_domain:
demand_exposures:
workflow_analogue:
construct_inclusions:
construct_exclusions:
provenance_and_author:
independence_rationale:
instance_ids_and_digests:
oracle_results_by_instance_and_environment:
counter_policy_results:
fresh_human_attempts:
development_agent_attempts_blinded_summary:
transcript_adjudication:
grader_validity_summary:
difficulty_evidence:
instance_assignment_manifest:
public_private_classification:
reviewers:
review_date:
unresolved_findings:
```

The record format may later become machine-readable. Until D-013 accepts a
schema, agents must not invent default values for missing evidence or convert
`PARTIAL` to `PASS` because a task executes successfully.

## 9. Next decision evidence

This protocol makes the next work explicit:

1. complete and record fresh-human review;
2. adjudicate the complete fixed development-attempt transcript batch;
3. freeze the development-model and attempt-count QA envelope;
4. qualify the plan-bound production implementation of the symmetric pilot gate;
5. finish D-005 interval/epoch recovery and independently review the
   production-bound H1 builder; and
6. freeze final instance/plan/analysis digests before paid collection.

No family yet passes Q0-Q4. The 540-cell/720-valid V2 pilot roster is now
implemented, but implementation does not waive any admission gate.

The first prospective ceiling/floor comparison is recorded in
`docs/D013_CEILING_SIMULATION_MEMO.md`. D-013 accepts the symmetric five-
failure/five-success, two-family rule; Q3 remains PARTIAL until the blinded
calibration and exact D-005 analysis pass their operating-
characteristic grid.
