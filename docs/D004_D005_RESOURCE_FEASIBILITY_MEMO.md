# D-004/D-005 joint resource-feasibility memo

**Status:** EVIDENCE DRAFT — no N, resource cap, model, audit budget, coder
backend, task bank, or hypothesis scope is approved
**Created:** 2026-08-06
**Decisions informed:** D-002, D-004, D-005, D-006, D-010, and D-013
**Code:** `analysis/d004_resource_feasibility.py`,
`analysis/d005_finite_roster_irr.py`, and
`analysis/d010_enriched_audit.py`
**Tests:** `tests/test_d004_resource_feasibility.py`,
`tests/test_d005_finite_roster_irr.py`, and
`tests/test_d010_enriched_audit.py`

## 1. Bottom line

This pass joins the previously separate human-audit and repeated-study layers,
then puts their operating characteristics beside the literal collection and
coding workload. It yields six conclusions.

1. **The full four-hypothesis design is subscription-heavy even at the
   floor.** The candidate broad split-N matrix contains 5,040 agent trials at
   base N=6 and 19,320 at N=24. The current two-full-sample-coder rule adds
   10,080 and 38,640 rubric calls, respectively, before pilot, development,
   invalid attempts, or retries.
2. **The target claim determines the D-005 result.** A pooled two-phase
   interval can be calibrated for the exact fixed roster under independent
   fresh trials. Treating tasks and configurations as sampled clusters from
   wider populations is much less decisive because only seven purposively
   selected configurations exist; repeating those configurations does not buy
   broad configuration-population evidence.
3. **One plausible fixed-cell variance attempt is falsified.** Applying a
   Jeffreys pseudo-count separately to 210 sparse task-variant-by-configuration
   cells per context produces only 66-70% coverage and 11-19% threshold
   clearing at the RR=2 boundary. It remains in the code only as a negative
   comparator.
4. **The pooled fixed-roster candidate passes its first calibration.** At
   base N=24 and a focal-failure census, coverage is 95.1% and threshold
   clearing is 1.7% when the scenario human-reference RR is exactly 2. Across
   B=400-1,000, coverage is 95.0-96.0% and coupled threshold clearing is
   0.1-2.2% in the independent/shared RR=2 boundary mechanisms.
5. **B=600-700 is the useful human-review region at N=24, but H2 is still not
   separately powered.** B=700 plus the 50-case anchor is 750 labels and is
   close to the full-human ceiling. Coupled support for a synthetic true 3x
   effect is about 64-67% with perfect labels and about 49% with a 98%-accurate
   human reference. This is below 80% even before broader model uncertainty.
6. **Near-census review is not justified by the broader sensitivity.** The
   task-by-configuration sandwich with a t(6) critical value is calibrated but
   supports the N=24 3x effect in only roughly 18-30% of census runs. Even at
   N=96 it reaches only about 23-43%, while requiring 77,280 agent trials and a
   human census of roughly 3,500 focal failures in the simulated scenario.

The evidence supports carrying a narrow fixed-roster pooled candidate and a
broader multiway sensitivity forward. It does not approve either as the final
D-005 analysis. H2 should remain exploratory unless empirical resource
shakedowns make N=24/B approximately 700 acceptable and the sub-80% operating
characteristic is judged sufficient for its role.

## 2. Workload identities

The candidate 12-family broad split-N design has five environments, seven
configurations, twelve capability families, and eighteen seeded prompt
variants. Capability repetitions are `ceil(5 * base_N / 12)`; seeded variants
retain `base_N`.

| Base N | Capability trials | Seeded trials | Full agent trials | `agy` agent trials | Two full-sample coder calls | Agent + coder calls |
|---:|---:|---:|---:|---:|---:|---:|
| 6 | 1,260 | 3,780 | 5,040 | 2,160 | 10,080 | 15,120 |
| 12 | 2,100 | 7,560 | 9,660 | 4,140 | 19,320 | 28,980 |
| 24 | 4,200 | 15,120 | 19,320 | 8,280 | 38,640 | 57,960 |

The `agy` column contains CFG5-CFG7 because those three configurations use the
same subscription execution surface. AI-coder provider assignment is open
under D-006 and is intentionally not charged to an arbitrary provider here.

Calls are not quota units. Agent and rubric calls differ in input length,
output length, tool use, wall time, and vendor accounting. D-004 still needs
provider-specific non-analysis measurements before any call count can become a
resource cap.

At base N=24 under the moderate-failure scenario, the mean focal Windows/Linux
failure population is approximately 865. H2-only failure coding would
therefore be far smaller than the registered full-sample coding surface. H4's
all-seeded-transcript outcome is the principal reason the full coding burden
cannot simply be restricted to H2 failures without a V2 scope change.

## 3. Three inferential candidates

### 3.1 Pooled fixed-roster two-phase candidate

The existing probability-sample estimator combines known full-sample Coder-1
labels with inverse-probability-weighted human-minus-Coder residuals. Its
repeated-study normal interval includes its analytic audit-design variance and
the pooled conditional-binomial term. Confirmatory threshold clearing in this
memo additionally requires:

1. the registered IRR gate;
2. the exact Bonferroni-hypergeometric finite-human lower bound above 2; and
3. the repeated-study pooled lower bound above 2.

This is a candidate for a claim explicitly bounded to the registered tasks and
configurations. It assumes fresh trials are independent conditional on their
fixed cells and does not justify generalization to new task or configuration
populations.

### 3.2 Task-by-configuration multiway sensitivity

The new sandwich comparator calculates trial influence for
`log(q_Windows/q_Linux)`, sums it independently by task and configuration,
subtracts the task-by-configuration intersection, applies `G/(G-1)`
corrections, and uses `min(G_task, G_config)-1 = 6` degrees of freedom.

It represents a broader superpopulation-oriented sensitivity, not the
registered GLMM. With only seven configurations, its variance has a
heterogeneity floor: more repetitions of the same configurations do not make
the wider configuration-population claim precise.

### 3.3 Falsified cellwise Jeffreys delta comparator

The attempted fixed-cell delta interval modeled success, failed non-D/E, and
failed D/E as three outcomes and applied a Dirichlet(1/2, 1/2, 1/2) plug-in in
every task-variant-by-configuration cell. The pseudo-count is small per cell
but large when repeated across 210 sparse cells per context. It dramatically
underestimates repeated-study uncertainty and is rejected.

This negative result is retained because it is exactly the kind of locally
reasonable sparse-cell repair that can appear stable while invalidating the
decision rule.

## 4. Boundary calibration

The 1,000-replicate perfect-reference grid uses seed `28660806`. Maximum
single-cell Monte Carlo standard error is approximately 1.58 percentage
points.

| Scenario | B | Repeated-study coverage | Audit-only finite RR>2 | Coupled threshold clearing |
|---|---:|---:|---:|---:|
| independent RR=2 | 400 | 95.4% | 0.9% | 0.8% |
| independent RR=2 | 600 | 95.8% | 11.6% | 1.4% |
| independent RR=2 | 700 | 95.6% | 30.9% | 1.7% |
| independent RR=2 | 800 | 95.6% | 43.0% | 1.7% |
| independent RR=2 | census | 95.6% | 52.2% | 1.6% |
| shared D/E-to-C RR=2 | 400 | 96.0% | 0.1% | 0.1% |
| shared D/E-to-C RR=2 | 600 | 95.0% | 2.2% | 1.3% |
| shared D/E-to-C RR=2 | 700 | 95.1% | 17.1% | 2.0% |
| shared D/E-to-C RR=2 | 800 | 95.8% | 32.7% | 1.8% |
| shared D/E-to-C RR=2 | census | 95.4% | 50.1% | 2.2% |

The audit-only quantity approaches 50% at census because it targets the
randomly realized finite human roster. The repeated-study layer restores the
scenario-level boundary behavior. This is the empirical distinction the
previous audit memo said D-005 had to supply.

## 5. Strong-effect human-review frontier

The following 500-replicate grid uses seed `27660806`; maximum single-cell
Monte Carlo standard error is approximately 2.24 percentage points. Values are
the probability that the IRR gate, exact audit lower bound, and pooled
repeated-study lower bound all clear.

| Mechanism / human mode | B=400 (450 labels) | B=600 (650 labels) | B=700 (750 labels) | B=800 (about 850 labels) | Census (about 915 labels) | Full-human pooled ceiling |
|---|---:|---:|---:|---:|---:|---:|
| independent 3x / perfect | 49.0% | 65.0% | 67.4% | 67.6% | 68.6% | 71.4% |
| independent 3x / 98% | 27.0% | 46.8% | 49.4% | 50.4% | 51.0% | 53.8% |
| shared D/E-to-C 3x / perfect | 11.2% | 53.2% | 64.2% | 68.0% | 69.0% | 69.6% |
| shared D/E-to-C 3x / 98% | 6.2% | 36.8% | 48.8% | 51.0% | 51.4% | 52.0% |

B=700 is the first tested point consistently near the full-human ceiling in
all four cells. It is not selected: its operational value depends on actual
review speed and subscription feasibility, and its 98%-reference support is
still only about one half.

With 10% generic operational overhead, 650, 750, and 850 labels imply:

| Total labels | 3 minutes each | 5 minutes each | 8 minutes each |
|---:|---:|---:|---:|
| 650 | 35.8 h | 59.6 h | 95.3 h |
| 750 | 41.3 h | 68.8 h | 110.0 h |
| 850 | 46.8 h | 77.9 h | 124.7 h |

These are explicit assumptions, not observed timings.

## 6. Claim-scope consequence

The two calibrated analyses answer different questions:

- **Pooled fixed roster:** how large is the conditional D/E ratio on these
  registered tasks, configurations, contexts, and collection epoch, assuming
  fresh independent trials within the fixed design?
- **Multiway sensitivity:** would the result survive treating the observed
  tasks and configurations as clusters standing in for wider populations?

The benchmark does not randomly sample configurations, and the candidate task
bank is content-validated rather than probability-sampled from real coding
work. A broad superpopulation claim is therefore not automatically more
scientific; it may simply be unsupported by the design. If the pooled
candidate is selected, paper language must remain explicitly finite-roster and
the multiway result must be reported as a sensitivity, not hidden because it
is less decisive.

Time/epoch and provider-routing dependence remain D-009 problems. They are not
made harmless by calling tasks or configurations fixed.

## 7. Decision implications

- Do not approve the cellwise Jeffreys delta interval.
- Carry the pooled exact-audit coupling as the leading narrow candidate.
- Carry the multiway t(6) interval as a broader claim-scope sensitivity, not a
  substitute GLMM.
- Treat B=600 and B=700 as the only current N=24 resource points worth further
  empirical costing. B=400 is vulnerable to shared wrong agreement; B=800 and
  census add little beyond B=700.
- Do not describe N=24/B=700 as 80%-powered for H2; it is not under the tested
  3x mechanisms.
- Cost H4 separately. The current all-transcript two-coder rule dominates
  subscription workload and is not required merely to estimate H2 among focal
  failures.
- Do not begin the pilot based on call arithmetic. D-004 and D-006 still need
  observed provider usage, wall time, invalid-attempt tails, sustainable
  concurrency, and coder-backend availability.

## 8. Required empirical shakedowns

Before a resource decision:

1. measure representative capability and seeded-error agent calls in every
   configuration, including usage units and wall time;
2. measure the proposed AI-coder calls separately rather than treating one
   grader call as one agent call;
3. record invalid-attempt and retry tails;
4. time 30-50 stratified non-analysis human classifications and report active
   p50, p90, uncertain-case frequency, and evidence-loading time;
5. prove that each version-sensitive provider block fits its accepted plan
   window before confirmatory collection starts; and
6. pre-specify the stop/split rule for a model-label or routing-evidence change.

Researcher-specific account limits and operating reserves belong in the
private operational record, not this public methodology repository.

The no-quota qualification and agent-under-test shakedown paths are now
implemented in `scripts/collection_preflight.py`,
`scripts/resource_shakedown_plan.py`, and
`scripts/resource_shakedown_run.py`, with the operator sequence in
`docs/PRECOLLECTION_SHAKEDOWN.md`. The deterministic manifest contains 70
resource-core calls and 12 nonduplicative transport calls.

### 8.1 Corrected paid agent-under-test evidence (2026-08-15)

The current semantic audit replaces receipt-only success with four required
conditions: valid trial, process return code zero, no recognized pre-model
authentication envelope, and exact artifact path/byte/hash agreement. After
correcting Windows/macOS `agy` authentication and WSL2/Linux-native Claude
authentication, all 82/82 manifest calls pass that rule. The composition has
410 receipt-bound artifacts and 328 immutable attempt-state artifacts with no
integrity mismatch.

Ten authenticated resource calls per configuration produced these agent-
process wall times (seconds):

| Configuration | Total | p50 | p90 | Maximum |
|---|---:|---:|---:|---:|
| Claude Code / Opus 4.8 | 205.063 | 16.281 | 37.110 | 43.547 |
| Claude Code / Sonnet 4.6 | 211.311 | 18.937 | 43.140 | 43.734 |
| Codex / GPT-5.6 Sol | 198.906 | 18.109 | 35.578 | 40.719 |
| Codex / GPT-5.6 Terra | 142.982 | 11.921 | 21.687 | 22.531 |
| `agy` / Sonnet 4.6 | 145.688 | 12.485 | 19.109 | 19.891 |
| `agy` / Gemini 3.1 Pro High | 236.952 | 17.531 | 36.765 | 37.765 |
| `agy` / Gemini 3.6 Flash Medium | 96.546 | 8.828 | 12.984 | 15.625 |

The Claude block's displayed meters moved 4% to 7% for the current session,
12% to 13% for the all-model weekly window, and remained 21% for the displayed
model-specific weekly window. The Antigravity observation spans diagnostics
and corrected transport calls as well as the resource block, so it is a
conservative upper bound: Gemini-group weekly remaining moved 99.95% to
99.74%, while Claude/GPT-group weekly remaining moved 98.82% to 97.35%.
Five-hour Antigravity windows replenished during the observation and are not
treated as consumption deltas. Codex exposed no comparable numeric plan meter;
extra-credit balance and automatic reload remained zero/off.

These measurements close the paid agent-under-test timing and available-meter
part of D-004. They do not accept a numeric N or calendar cap. The 30-50-case
blinded human timing sample and the separate D-006 coder-backend shakedown
remain prerequisites because coder and human work cannot be costed from agent-
under-test calls. The private sanitized review containing custody, correction,
and cleanup evidence is bound by SHA-256
`a8f48c67f919d9265a9ee838d0f5789b10b1d71447c36789c83857857bbb246c`.

### 8.2 Blinded human-timing packet prepared

`scripts/human_timing_packet.py` now constructs the required costing exercise
from the corrected, analysis-excluded resource records. It requires two clean
replicates in every seven-configuration by five-workload-stratum cell, selects
one deterministic replicate per crossing, randomizes the 35-case presentation
order, and excludes explicit agent/model/environment/configuration metadata
from the worksheet. The private browser worksheet records evidence-loading
milliseconds, active coding milliseconds, A-F code, uncertainty, and a short
rationale. It refuses public-repository output, invalid trials, nonzero exits,
timeouts, incomplete crossing rosters, and overwrite of an existing packet.

The prepared private packet has packet digest
`57e64a486dfeed8d7514840200a4cede8574927d962dc177b48fb484dd53bf3d`;
its browser worksheet is bound by SHA-256
`24762da051116dd7850f951853b900447b2cc41f5c3f072bcdab04138048fab9`.
The 35-case size is an operational timing design inside the required 30-50
range, not an acceptance of the still-open production human-anchor sampler.
D-004 remains open until the researcher completes this worksheet and its
active p50/p90, evidence-loading distribution, and uncertain-case rate are
recorded.

## 9. Reproduction

Core tests:

```powershell
python -m pytest tests/test_d004_resource_feasibility.py tests/test_d005_finite_roster_irr.py tests/test_d010_enriched_audit.py tests/test_collection_preflight.py tests/test_resource_shakedown_plan.py tests/test_resource_shakedown_run.py tests/test_human_timing_packet.py -q
```

Resource identities:

```powershell
python -m analysis.d004_resource_feasibility --base-common-ns 6 12 24 --audit-budgets 600 700 800 --minutes-per-label 3 5 8
```

Boundary calibration:

```powershell
python -m analysis.d010_enriched_audit --replicates 1000 --seed 28660806 --base-common-ns 24 --budgets 400 600 700 800 1000 --human-modes perfect_reference --designs focal_failure_context_srs --scenarios high_quality_boundary shared_de_to_c_boundary
```

Strong-effect frontier:

```powershell
python -m analysis.d010_enriched_audit --replicates 500 --seed 27660806 --base-common-ns 24 --budgets 400 600 700 800 1000 --human-modes perfect_reference noisy_98_reference --designs focal_failure_context_srs --scenarios high_quality_strong shared_de_to_c_strong
```

No benchmark trial ran and no frozen V1 methodology, task, rubric prompt,
scheduler, collection rule, label rule, N, audit budget, or resource cap
changed. D-002, D-004, D-005, D-006, D-010, and D-013 remain OPEN.
