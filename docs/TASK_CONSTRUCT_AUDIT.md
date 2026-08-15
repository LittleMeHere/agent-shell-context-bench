# Capability-task construct and ceiling audit

**Status:** AUDIT DRAFT — no task-bank option is approved
**Created:** 2026-08-01
**Finding:** R-022
**Decision:** D-013
**Scope:** H1a/H3 capability-task population, consequences for all-task
H1b/H2 analyses, and the interpretation of a bounded or all-success result

## 1. Bottom line

The five capability tasks are not arbitrary in the ordinary sense. They are
purpose-built probes with explicit success predicates and recognizable
software-workflow content. They are also not a probability sample,
domain-stratified sample, or validated scale of general environment-mediated
coding-agent reliability.

The current bank therefore supports claims about the exact five-task roster.
It does not yet support treating their equal-weighted average as a calibrated
measure of a broader task population.

There are two distinct ceiling risks:

1. **Statistical ceiling:** zero observed failures makes V1's risk ratio and
   pilot transform undefined or unstable.
2. **Construct ceiling:** easy or readily routed-around tasks may show no
   context difference while leaving important workflow domains unsampled.

An all-success result is not necessarily “no information.” With enough trials
and a sparse-safe risk-difference interval, it can tightly bound the absolute
context penalty on the exact registered roster. It cannot establish that the
same bound holds for builds, package management, Git, processes, permissions,
encoding, recovery, or other unsampled work.

## 2. How the current bank was selected

`docs/DECISIONS.md` D4 records a purposive mixture of common-workflow tasks
and hardened tasks. The hardening decision followed a C01 smoke in which a
frontier model completed the task easily; the stated goal was to avoid a zero
failure denominator while retaining some common-workflow coverage.

That is a legitimate difficulty-calibration rationale, but it is not a task-
population sampling rationale. Selecting items partly because they are likely
to produce failures can alter the distribution of task-by-context
interactions. The matched comparison controls generic task difficulty; it
does not make a hand-picked collection representative of routine coding work.

The nine seeded-error tasks are correctly excluded from H1a because they were
designed around known failure modes. The five capability tasks are less
directly adversarial, but several still contain known shell- or
PowerShell-sensitive edges. “Capability” therefore does not by itself imply
environment-neutral task selection.

## 3. Current task-to-construct map

| Task | Dominant capability | Direct environment surface | Route-around path | Construct limitation |
|---|---|---|---|---|
| C01 | nested file and directory creation | path syntax and shell expansion; notes explicitly identify bash brace expansion | Python, direct file tools, or explicit per-path commands | one small filesystem-construction pattern |
| C02 | RFC-4180 CSV parsing and exact output | PowerShell versus language-library data handling | Python's `csv` module works similarly across contexts | mainly parser/library selection, not broad environment use |
| C03 | code-aware multi-file symbol rename | file traversal and command invocation only | direct Edit/Write tools or a Python refactor script | mostly editing/reasoning ability; weak treatment exposure |
| C04 | recursive tree inspection | hidden-path rules, separators, recursion, and byte-size tooling | `os.walk` and Python filesystem APIs | strong filesystem probe but one artificial tree and rule set |
| C05 | recursive JSON merge | PowerShell 5.1 `PSCustomObject` behavior and serialization | Python/JavaScript custom merge | one structured-data transformation with bespoke semantics |

The bank is concentrated in two areas:

- filesystem/path behavior: C01 and C04;
- structured-data transformation: C02 and C05.

C03 supplies one repository-editing item. The bank has no substantial
capability item for:

- quoting, pipelines, redirection, exit-code propagation, environment
  variables, or subprocess control;
- Git operations and conflict recovery;
- build, test, package-manager, or dependency workflows;
- permissions, executable discovery, or executable-bit behavior;
- newline, encoding, and locale interactions;
- diagnosis and recovery after an authentic tool error.

One item per narrow behavior cannot distinguish a repeatable domain effect
from an idiosyncratic fixture effect.

## 4. What free tool choice means

The registered treatment deliberately gives the agent its normal tool palette.
That makes H1a a comparison of **practitioner-facing context bundles**, not a
test of PowerShell syntax competence in isolation.

Consequently, an agent that recognizes a PowerShell complication and uses
Python or a direct editing tool has succeeded under the intended construct.
Route-around behavior is not contamination under the current realistic-usage
framing; it is one way an agent can be robust.

This also means a task with a theoretical PowerShell gotcha may create almost
no treatment contrast for capable agents. If the scientific target were shell
competence conditional on using the shell, tool choice would need to be
constrained in a different experiment. V2 must not slide between these two
constructs after seeing outcomes.

## 5. Conditional ceiling probabilities

The blinded pilot contains 100 capability-task trials:

```text
5 environments × 2 pilot configurations × 5 capability tasks × 2 trials
```

If every trial had the same independent failure probability `p`, the chance
of observing zero pilot capability failures would be `(1-p)^100`:

| True per-trial failure rate | P(zero failures in 100 capability-pilot trials) |
|---:|---:|
| 0.1% | 90.5% |
| 0.5% | 60.6% |
| 1.0% | 36.6% |
| 2.0% | 13.3% |
| 5.0% | 0.6% |

At the current N=6 floor, one focal H1a context contains 210 trials:

```text
7 configurations × 5 capability tasks × 6 trials
```

Under the same simplifying assumptions:

| True failure rate in each context | P(one context has zero failures) | P(at least one of two contexts has zero failures) |
|---:|---:|---:|
| 0.1% | 81.1% | 96.4% |
| 0.5% | 34.9% | 57.6% |
| 1.0% | 12.1% | 22.8% |
| 2.0% | 1.4% | 2.9% |
| 5.0% | 0.002% | 0.004% |

These are conditional calculations, not predictions of the unknown task
failure rate. Trial outcomes are also heterogeneous rather than identically
distributed. The table shows why “we will probably see at least one failure”
is not an adequate ceiling plan: if the true rate is at or below one percent,
zero-event branches are common at the planned sizes.

## 6. Why all-success data can still be informative

V1 makes a context with zero capability failures ratio-unestimable. That is a
property of the chosen risk-ratio estimand, not proof that the observations
contain no information.

For example, 210 independent all-success trials in a context yield a
non-zero upper confidence bound on its failure probability. A valid
risk-difference procedure can therefore bound the Windows-minus-Linux gap
without pretending the interval has zero width. The D-001 scaffold includes
an explicit counterexample test to prevent a plug-in variance estimator from
turning all-zero observations into false certainty.

The defensible conclusion would remain roster-bounded:

> On these tasks, configurations, and context bundles, the absolute failure-
> rate penalty was bounded below the pre-specified threshold.

It would not justify:

> Environment-mediated reliability problems are broadly absent.

If every task is easy because agents successfully route around environment
friction, that is useful practitioner-facing evidence for those workflows.
If every task is easy because the bank omitted the workflows where context
matters, it is a content-validity failure. Outcomes alone cannot distinguish
those explanations; the task-population definition must do so before data.

## 7. Candidate resolutions for D-013

### Option A — retain the five-task probe set and narrow the claim

Keep C01-C05 as H1a's full population. Describe them as deliberately varied
probes, not a sample of routine coding work. A bounded-small result means only
that this instrument did not justify a broader investigation.

**Advantages:** preserves the registered roster and contains cost.

**Costs:** weak external validity; a broad null cannot deprioritize unsampled
workflow mechanisms with much confidence.

### Option B — domain-stratified capability bank

Define a target construct and workflow-domain sampling frame before authoring
or selecting tasks. Retain suitable current tasks, fill missing domains, and
use at least two independently authored task families per domain. Where
feasible, freeze multiple matched instances per family. Weight domains first,
then families and instances within domains.

A candidate two-axis frame is more defensible than treating every skill as a
separate domain.

Content domains:

1. filesystem, paths, and artifact manipulation;
2. data, configuration, text, and encoding transformations;
3. repository inspection and code modification;
4. version-control workflows;
5. build, test, package, and dependency workflows;
6. runtime, service, process, and system operations.

Cross-cutting demands, which should recur across domains rather than become
single-task buckets:

1. environment discovery and localization;
2. command and shell composition;
3. diagnosis and recovery;
4. preservation and scope control;
5. output verification and test use;
6. environment-aware tool adaptation, including legitimate route-around
   behavior.

This frame is a study-specific sampling scaffold, not an externally validated
taxonomy or a claim that the six domains deserve equal real-world weight.
`docs/TASK_BANK_DESIGN_OPTIONS.md` records the external-benchmark comparison,
the current-task mapping, and costed retain-versus-expand designs.
`docs/TASK_FAMILY_QUALIFICATION.md` records the candidate task-admission gates
and the provisional C01-C05 qualification audit.

**Advantages:** makes an average effect and a bounded null substantially more
meaningful; separates broad, domain-specific, and fixture-specific signals.

**Costs:** methodology amendment, task authoring, validation, and a potentially
larger matrix. Total cost should be controlled by comparing broader task
sampling with repeated trials on fewer fixtures rather than automatically
multiplying both.

### Option C — sampled or externally anchored realistic tasks

Define a sampling procedure over an external repository-task corpus and use a
held-out realistic set as the primary or validation population.

**Advantages:** strongest route toward criterion and external validity.

**Costs:** reproducibility, contamination, cross-platform equivalence,
licensing, task setup, and automated scoring become much harder. This is
likely a follow-up instrument rather than the minimum V2 repair.

## 8. Recommended pre-data validation requirements

The recommendation is Option B, with Option A retained as the fallback if the
resource envelope cannot support a defensible bank. Before any revised pilot:

1. **Construct definition:** state whether the target is practitioner-facing
   bundle reliability or constrained shell competence. For the current
   free-tool-choice design, use the former.
2. **Content map:** define domains and inclusion/exclusion rules before
   selecting new items. Record why each task belongs and which mechanisms it
   cannot test.
3. **Independent item coverage:** use multiple families per domain or narrow
   the claim wherever only one item exists.
4. **Matched instances:** where tasks vary, bind identical frozen instances
   across contexts and keep generation independent of observed effects.
5. **Oracle and counter-policy checks:** a platform-neutral oracle must pass;
   deliberately bash-dependent and PowerShell-dependent policies must trigger
   the expected context-sensitive failures; malformed/no-op/destructive
   outputs must fail consistently.
6. **Realistic holdout:** include a small, separately authored workflow set or
   explicitly defer criterion validity and constrain the paper claim.
7. **Ceiling/floor gate:** pre-specify a blinded, deterministic pilot rule for
   zero or insufficient capability events. The rule must emit only the
   approved gate result and sizing inputs, not named context effects.
8. **Fresh-data rule:** if the ceiling gate sends the bank back to development,
   do not modify tasks and reuse the same pilot as confirmatory evidence.
   Amend and freeze the bank, then run a fresh blinded pilot.
9. **Concentration reporting:** show domain/task heterogeneity and a
   pre-specified leave-one-domain-out diagnostic. A single-fixture effect may
   motivate targeted follow-up but cannot be described as a broad context
   penalty.
10. **Costed operating characteristics:** compare task breadth, repetitions,
    decision precision, and full-matrix cost before choosing the bank.

The exact domain frame, minimum events, number of task families, number of
instances, and ceiling threshold are substantive decisions. This audit does
not approve them.

## 9. Proposed decision meanings

If Option B is validated:

- a decision-relevant average across domains triggers a broad mechanism or
  mitigation investigation;
- a replicated domain-specific effect triggers a targeted investigation;
- an isolated fixture effect triggers replication, not a broad claim;
- a bounded-small average can deprioritize a broad investigation only within
  the frozen task-population scope;
- a ceiling-gate failure means the instrument requires redevelopment, not
  that the environment effect is absent.

If Option A is retained, every one of those statements must substitute “this
five-task probe set” for a broader task-population claim.

## 10. Confidence and unresolved evidence

- High confidence: current tasks are purposive but not representative.
- High confidence: V1 has no adequate zero/insufficient-event response path.
- High confidence: all-success data can inform a finite-roster absolute-risk
  bound without validating broader task coverage.
- Moderate-to-high confidence: domain-stratified independent task families
  are the best attainable V2 improvement.
- Moderate-to-high confidence: separating content coverage from cross-cutting
  demands is better supported than the original one-axis six-domain frame.
- Moderate confidence: the candidate six content domains are a useful minimum
  for this treatment; no reviewed source validates them as a representative
  population or supplies defensible real-world weights.
- Low confidence in any numerical ceiling threshold before candidate analysis
  methods, resource limits, and blinded-pilot simulations are compared.

No task definition, frozen methodology file, threshold, or collection plan is
changed by this audit.
