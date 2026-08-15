# D-013 task-bank evidence and design options

**Status:** EVIDENCE BASIS — D-013C split-N 12-family direction accepted 2026-08-09; exact N remains open
**Created:** 2026-08-01
**Decision:** D-013
**Finding:** R-022
**Depends on:** D-001 through D-005 estimand, H2, operating-characteristic,
resource, and confirmatory-model decisions
**Scope:** H1a/H3 capability-task population, criterion bridge, collection
cost, and consequences for the all-task H1b/H2 analyses

## 1. Recommendation in one paragraph

Do not interpret the present five-task average as a calibrated measure of
general environment-mediated coding-agent reliability. For D-013, compare the
registered five-probe design with a **12-family, six-domain bank** that retains
all five current tasks and adds seven independently authored families. Treat
diagnosis, shell composition, verification, and adaptation as cross-cutting
demands that recur across domains. Freeze multiple instances within families
and rotate them inside repetitions; do not count minor seeded variants as
independent coverage. The broader bank can cost 30.4% more at a common `N`, or
approximately the same as the present matrix by reducing repetitions per
capability family while preserving the seeded-task `N`. This is the leading
candidate for simulation and validation, not an authorization to change the
frozen tasks.

## 2. What external benchmarks do and do not validate

No reviewed benchmark supplies a canonical taxonomy for the narrow treatment
in this study: an agent with free tool choice operating under different
Windows-context bundles. The external evidence does support several design
principles.

### 2.1 Coverage must match the intended claim

- [SWE-bench](https://arxiv.org/abs/2310.06770) uses 2,294 real GitHub issues
  from 12 Python repositories. It provides strong repository-maintenance
  realism, but its authors and later users describe a bounded software-
  engineering scope rather than a general workflow sample.
- [TheAgentCompany](https://arxiv.org/abs/2412.14161) broadens coverage with
  175 tasks in a simulated software company. Its tasks cross job roles and
  interfaces such as web applications, code, terminals, and coworker
  communication. That breadth is part of the construct, not merely a larger
  count of near-duplicate fixtures.
- [HCAST](https://metr.org/hcast.pdf) reports 189 tasks in 78 families, split
  into four domains and finer subdomains. It explicitly distinguishes task
  families from individual tasks and reports meaningful variation within and
  across families.
- [Terminal-Bench 2](https://arxiv.org/abs/2601.11868) uses 89 hard terminal
  tasks inspired by real workflows. Its
  [official task gallery](https://www.tbench.ai/benchmarks/terminal-bench-2)
  spans software engineering, version control, build/debugging, system
  administration, data processing, security, and scientific workflows.

These suites validate the need to define coverage and independent task
families. They do **not** establish that the six candidate domains below are
representative, exhaustive, or equally prevalent in real agent use.

### 2.2 A realistic source does not guarantee a valid item

- The original SWE-bench Verified project used 93 professional developers to
  annotate 1,699 randomly selected issue/test pairs and produced a 500-task
  human-validated subset
  ([OpenAI methodology](https://openai.com/index/introducing-swe-bench-verified/)).
- A later OpenAI audit found fundamental design and contamination problems in
  SWE-bench Verified. A subsequent audit estimated that roughly 30% of
  SWE-Bench Pro tasks were broken, especially through overly strict tests,
  underspecified prompts, low-coverage tests, and misleading prompts
  ([2026 audit](https://openai.com/index/separating-signal-from-noise-coding-evaluations/)).
- HCAST uses fresh-human QA, gold solutions where feasible, five agent attempts
  per task followed by manual transcript review, and relevant-human baselines.
  Its report says both human and agent QA continued to reveal shortcuts,
  incidental difficulty, and scoring bugs.
- The
  [Terminal-Bench task rubric](https://github.com/harbor-framework/terminal-bench-science/blob/main/rubrics/task-implementation.toml)
  requires realistic professional workflows, outcome-based tests, an oracle
  solution, and intrinsic rather than model-pass-rate difficulty.

The implication for this study is strict: neither “taken from real work” nor
“a frontier agent failed it” establishes validity. Prompts, oracles, graders,
shortcut policies, and observed failure traces require separate review.

### 2.3 Difficulty is evidence only when calibrated against a use case

HCAST labels subdomain, expertise, human completion time, and other difficulty
dimensions. Its task success falls as human time increases, but the authors
also disclose that some items are closer to exercises than economically
realistic work. Terminal-Bench targets difficult, multi-step terminal work.
TheAgentCompany includes both simpler and long-horizon workplace tasks.

The lesson is not “make every task hard.” A useful bank should include
workflows where the environment could plausibly change success, avoid a
complete ceiling at the tested agent level, and retain enough routine work to
support the intended practitioner-facing claim. Selection solely for model
failure would change the construct to adversarial stress testing.

## 3. Proposed construct frame

The target construct remains:

> End-to-end success on bounded coding and software-workflow tasks when an
> agent may use its normal tool palette under the registered execution-context
> bundles.

It is not PowerShell syntax knowledge conditional on mandatory shell use.
Successful use of Python, direct file tools, or another context-robust route is
valid under this construct.

### 3.1 Content domains

| Domain | Included workflow content | Current independent families |
|---|---|---:|
| A. Filesystem/artifacts | paths, naming, traversal, copying, generated artifacts | C01, C04 |
| B. Data/config/text | structured data, configuration, text, newline/encoding behavior | C02, C05 |
| C. Repository/code change | inspection, localization, scoped edits, refactors | C03 |
| D. Version control | status/diff, branch/merge, history, conflict-safe recovery | none |
| E. Build/test/package | build systems, tests, package managers, dependencies, executable discovery | none |
| F. Runtime/system operations | processes, services, environment variables, permissions, ports, logs | none |

The current bank therefore touches three of six proposed domains. Only A and
B have two families. C has one; D-F have none.

### 3.2 Cross-cutting demands

Each demand should appear in multiple content domains:

1. environment discovery and localization;
2. command, quoting, pipeline, redirection, and subprocess composition;
3. diagnosis and recovery after authentic feedback;
4. preservation, non-destruction, and scope control;
5. output verification and test use;
6. environment-aware tool selection and legitimate route-around behavior.

This separation prevents one “recovery task” or one “shell task” from standing
in for recovery or shell demands across the bank. It also permits an explicit
coverage matrix before task selection.

### 3.3 Proposed minimum content fill

The 12-family candidate can retain the five existing families and add:

- one independently authored repository/code-change family;
- two version-control families;
- two build/test/package/dependency families;
- two runtime/service/process/system families.

That gives two families per content domain and requires seven new families.
It is a minimum replication rule, not proof of representativeness. Each new
family must be reviewed for semantic equivalence across all five contexts; a
task whose goal is impossible or materially different in one context is not a
valid treatment probe.

## 4. Family, instance, and repetition are different units

The design should distinguish:

- **family:** an independently authored workflow and scoring logic;
- **instance:** frozen input state within a family;
- **repetition:** a stochastic agent attempt on an assigned instance.

Changing filenames, values, or seeds within one scoring template improves
resistance to memorization and fixture luck, but it does not create the same
construct breadth as another family. Conversely, treating every instance as a
new matrix row would make collection cost explode.

The leading candidate is to freeze at least three instances per family, bind
one deterministic assignment schedule across all five environments and seven
configurations, and rotate instances inside the family-cell repetitions. The
target estimand would weight frozen instances equally within family, families
equally within domain, and domains according to the weights accepted in
D-013. Within every family-by-configuration-by-environment cell, instance
counts must differ by at most one; remainder assignments when `N_cap` is not a
multiple of the instance count must be counterbalanced over configurations and
reused identically across all five environments for every configuration.

The existing tasks must either receive the accepted multi-instance structure
or be explicitly treated as fixed-fixture families. D-013 cannot silently mix
fixed-fixture and instance-average interpretations. D-001 defines the
estimand, D-003 simulates its operating characteristics, and D-005 implements
the accepted nested hierarchy. This candidate is only viable when
`N_cap >= 3`; any other minimum requires a separately specified instance
schedule. None of these assignment or weighting rules is approved here.

## 5. Exact matrix-cost comparison

Let:

- `C` = number of capability families;
- `S = 18` = existing seeded-error variants;
- `K = 7 * 5 = 35` configuration-by-environment cells;
- `N_cap` = repetitions per capability-family cell;
- `N_seed` = repetitions per seeded-variant cell.

Then confirmatory valid trials are:

```text
35 * (C * N_cap + 18 * N_seed)
```

Under the current common-`N` design this reduces to `35 * (C + 18) * N`.
With two pilot configurations, five environments, and two pilot repetitions,
the current pilot cost is `20 * (C + 18)` valid trials.

The tables exclude invalid-attempt replacement, development runs, human QA,
VM/Actions overhead, and provider-specific token cost. Under the current
full-transcript IRR proposal, two AI coders require two grading calls per
confirmatory transcript.

### 5.1 Retain five families versus add 12 at the same `N`

| Design | Capability families | Matrix rows (`C + S`) | Pilot valid trials | Confirmatory at N=6 | N=12 | N=24 |
|---|---:|---:|---:|---:|---:|---:|
| A: current probe bank | 5 | 23 | 460 | 4,830 | 9,660 | 19,320 |
| B: six domains, two families each | 12 | 30 | 600 | 6,300 | 12,600 | 25,200 |

At the same `N`, Design B adds 30.4% to both confirmatory trials and AI-grader
calls. At `N=6`, for example, the grader count rises from 9,660 to 12,600.

The 600-trial B pilot preserves two collection attempts per family cell. If
all three frozen capability instances must each be exercised once in every
pilot configuration-by-environment cell, use three capability attempts and
two seeded attempts instead: `5 * 2 * (12 * 3 + 18 * 2) = 720` valid trials.

`docs/D013_CEILING_SIMULATION_MEMO.md` evaluates candidate gates on that
720-trial full-instance pilot and compares the common-N and split-N designs
under diffuse and domain-concentrated effects.

### 5.2 Approximately budget-matched breadth-for-repetition design

Preserve the current seeded-task repetition count `N_seed = N0`, but choose:

```text
N_cap = ceiling(5 * N0 / 12)
```

This approximately preserves the total number of capability observations per
configuration-by-environment cell while distributing them across 12 rather
than five families.

| Present common N0 | Proposed N_cap | Proposed N_seed | Current confirmatory | Proposed confirmatory | Change |
|---:|---:|---:|---:|---:|---:|
| 6 | 3 | 6 | 4,830 | 5,040 | +4.3% |
| 12 | 5 | 12 | 9,660 | 9,660 | 0.0% |
| 24 | 10 | 24 | 19,320 | 19,320 | 0.0% |

Including the minimal collection pilot, total valid trials become 5,640,
10,260, and 19,920, compared with 5,290, 10,120, and 19,780 under Design A.
The total increases are 6.6%, 1.4%, and 0.7%, respectively.

This arithmetic does **not** establish equal power. Broader family sampling
reduces repeated observations per family, changes the task/instance hierarchy,
and may change event rates and heterogeneity. D-003 must compare decision
error and interval behavior under both designs, including sparse and
domain-concentrated effects. The split-`N` design also requires a methodology
amendment and scheduler support; it cannot be silently substituted.

It also changes the task-class mixture entering H1b and H2. H2 is conditional
on failures over capability and seeded tasks at the trial level, so preserving
`N_seed` while reducing `N_cap` does not preserve the H2 estimand's empirical
weighting or its failed-trial denominator. D-002 must jointly simulate H2
estimability and decision behavior, and D-005 must support the accepted
family/instance hierarchy, before split `N` is viable.

### 5.3 Why not multiply three instances into separate matrix rows

Counting three instances for each of 12 families as 36 capability rows would
produce 54 total rows. That would require 1,890 matrix cells and 11,340
confirmatory trials even at `N=6`, versus 805 cells and 4,830 trials now.
Instances should improve within-family robustness without masquerading as 36
independent families or automatically increasing cost by 2.35 times.

## 6. What would make a null decision-informing

A bounded-small average can justify not prioritizing a **broad** context-gap
investigation only if all of the following are true before outcomes are seen:

1. the target construct and content domains are frozen;
2. each claimed domain has more than one independent family;
3. the bank demonstrates nontrivial difficulty without being selected solely
   for model failure;
4. platform-neutral oracles pass and context-sensitive counter-policies fail
   in the expected direction;
5. fresh-human attempts establish solvability, instruction clarity, and
   realistic workflow structure;
6. independent transcript review finds no common reward hack, grader gap, or
   incidental platform impossibility;
7. the sparse-safe estimator bounds the absolute effect below the registered
   decision threshold;
8. the conclusion survives registered domain-concentration diagnostics.

If the pilot is all-success and the pre-specified ceiling gate declares the
instrument insufficiently informative, the result is **instrument
redevelopment**, not evidence of no environment effect. Any revised tasks
require a fresh pilot.

Even a validated 12-family bank supports content validity, not demonstrated
criterion validity. A stronger claim that its score predicts performance on
real projects would require a separately authored realistic holdout or an
external workflow sample. That bridge should be developed without selecting
items based on observed treatment effects and should be reported separately
unless D-013 prospectively makes it part of the primary population.

## 7. Pre-data validation package for each candidate family

Before a family can enter a revised frozen bank, record:

- domain and cross-cutting-demand labels with written inclusion rationale;
- the real workflow analogue and important ways the fixture simplifies it;
- semantic-equivalence review for all five contexts;
- at least three frozen instances or a written reason one fixed instance is
  the intended population;
- a context-portable oracle and expected-score record;
- bash-dependent, PowerShell-dependent, no-op, malformed, shortcut, and
  destructive counter-policy results where applicable;
- fresh-human completion attempts by someone who did not author the task;
- repeated development-agent attempts with manual success and failure review;
- an explicit difficulty label based on human work and task structure, not a
  target model pass rate alone;
- grader sensitivity/specificity evidence against the adjudicated attempts;
- time, token, transcript-size, and invalid-attempt measurements;
- a signed/frozen family manifest and instance assignment rule.

`docs/TASK_FAMILY_QUALIFICATION.md` turns these requirements into accepted
Q0-Q4 gates and provisionally maps C01-C05. The isolated assignment prototype
in `analysis/d013_task_bank_design.py` makes the matching, balancing, and
equal-instance-weight invariants executable without changing the V1
scheduler. The direction is accepted; no family is admitted until its
evidence passes every applicable gate.

The QA evidence should be kept outside the confirmatory outcome stream. If QA
changes an item after collection begins, the family is amended and receives
fresh pilot data.

## 8. Decision alternatives for D-013

### D-013A — retain five probes

Use the present bank, keep a sparse-safe absolute-risk estimand, and constrain
every decision statement to the exact roster. Cheapest, but a null should not
deprioritize investigation of unsampled domains.

### D-013B — validate the 12-family bank at common `N`

Best breadth and replication among the costed options. Costs 30.4% more before
invalid replacements and development/QA.

### D-013C — validate the 12-family bank with split `N`

Leading resource-constrained candidate. Preserves approximately the current
trial budget by trading repetitions for independent family coverage. Requires
joint H1/H2 operating-characteristic simulation, an instance schedule, and
scheduler/model changes before approval.

### D-013D — retain the primary probe bank plus a separate realistic holdout

Adds a criterion-validity bridge without pretending the holdout is sampled
from the same population. Useful as validation or follow-up, but it does not
repair the meaning of the five-task primary average by itself.

## 9. Confidence and open questions

- **High confidence:** five purposive fixtures do not validate a broad null.
- **High confidence:** task-family breadth and item validity are separate;
  more tasks do not help if prompts or graders are defective.
- **High confidence:** all-success outcomes can bound exact-roster absolute
  risk but cannot establish missing-domain coverage.
- **Moderate-to-high confidence:** a two-axis content/demand frame is more
  defensible than using “recovery” or “shell” as single content buckets.
- **Moderate confidence:** two families in each of six domains is the minimum
  viable V2 expansion. It is a reasoned scaffold, not an empirically estimated
  task distribution.
- **Moderate confidence:** split-`N` Design C is likely the best resource
  tradeoff, conditional on simulation showing acceptable decision behavior.
- **Low confidence:** the bank will avoid a ceiling, or correlate with real
  project outcomes, until blinded development attempts and a separately
  designed criterion bridge are run.

Open D-013 questions are the domain weights, family inclusion rules, instance
count, ceiling/floor gate, human-QA minimum, holdout role, and whether the
resource envelope supports common or split repetitions.

No frozen task, preregistration, threshold, estimand, or collection schedule
is changed by this memo.
