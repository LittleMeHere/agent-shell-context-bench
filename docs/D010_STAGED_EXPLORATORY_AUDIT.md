# D-010 staged exploratory human-audit design

**Status:** EXACT PARAMETERS ACCEPTED PRE-DATA — production integration and
golden qualification remain
**Accepted constraint:** routine human review must not imply a 600–700-label
commitment; any expansion beyond the frozen routine cap requires a separate
researcher go/no-go decision
**Applies to:** exploratory H2/H4 measurement validation
**Does not apply to:** primary programmatic H1/H3 outcomes

## 1. Decision

Use a fixed small label-masked anchor followed, only when a pre-specified
measurement-informativeness gate passes, by one bounded focal audit. There is
no automatic third stage and no near-census rescue of an unusable AI judge.

The routine candidate envelope is:

| Component | Candidate labels | Role |
|---|---:|---|
| Omnibus anchor | 50 | Always drawn; probability sample for workflow, overall A–F agreement, refusal/malformed behavior, and gross shared-error detection |
| Focal audit | 150 additional | One fixed context-stratified SRS of valid failed trials when the frozen gate passes; census if fewer than 150 exist after scarcity minima pass |
| Routine maximum | 200 total | Fixed cap; no automatic third stage |
| Larger audit | none automatically | Requires a separate explicit decision and is preferably a dedicated follow-up study |

At five active minutes per label plus 10% operational overhead, 150 total
labels imply about 13.8 hours and 200 imply about 18.3 hours. At eight minutes
per label they imply about 22.0 and 29.3 hours. The 600–700 focal-label region
plus the anchor would require roughly 36–110 hours under the earlier timing
assumptions and is not the routine V2 design.

## 2. Why this is statistically honest

The existing D-010 simulations show that 50–200 human labels cannot validate
a confirmatory H2 threshold under shared AI error. The response is not to
pretend that a small audit is stronger than it is. V2 instead makes H2/H4
exploratory and uses the bounded audit for:

- detecting gross coder or evidence-contract failure;
- estimating overall and focal agreement with design-based uncertainty;
- checking for missed D/E cases in probability-sampled agreed non-D/E cases;
- reporting coder-specific exploratory estimates and sensitivity; and
- deciding whether a separately preregistered mechanism follow-up is worth
  the human time.

A small or null audited result cannot be described as evidence that spiral
asymmetry is absent. That negative claim was the reason the 600–700-label
region appeared necessary.

## 3. Label masking and sampling

The human rater is not shown explicit environment, configuration, agent/model,
AI-label, Windows/Linux-contrast, or hypothesis-favoring aggregate fields. This
is **label masking**, not a claim that identity is unknowable: evidential shell
syntax can reveal environment, and raw vendor wrappers can reveal the agent.
The production renderer must normalize non-evidential vendor wrappers, but it
must not redact command evidence merely to create artificial blindness.
Identity inferability and any rater recognition are reported as limitations.
The rater receives the frozen task/evidence packet needed to apply the A–F
contract.

Every sampled record has a known nonzero inclusion probability. The anchor
is stratified prospectively by programmatic outcome and task/domain so it is
not consumed almost entirely by successful trials. The focal audit is a
context-stratified simple random sample of valid failed trials; sampling code
may know the blinded context stratum, but the human does not receive it.

No hand-picked “interesting,” difficult, or disagreement-only case may enter
a load-bearing estimate. Qualitative examples may be reviewed separately and
must be labeled non-probability evidence.

## 4. Expansion gate

The gate is computed only after the complete primary-coder output and the
fixed 50-case anchor are immutable. It may use:

- total valid failure and success denominators;
- primary-coder completeness, refusal, and malformed-output rates;
- golden-case/evidence-contract qualification status;
- aggregate D/E candidate prevalence without named context effects;
- probability-weighted anchor disagreement and missed-D/E diagnostics; and
- whether a 100–150-case focal audit is capable of producing the predeclared
  exploratory precision target for the realized finite population.

It must not use:

- which environment appears worse;
- whether an H2/H4 estimate crosses a preferred threshold;
- whether adding human labels is forecast to create significance; or
- case-by-case investigator judgment after reading transcripts.

The frozen gate has three outcomes:

1. **STOP-SPARSE:** too few valid focal failures or D/E candidates for a
   meaningful comparative mechanism estimate. Publish denominators and the
   sparse/inconclusive branch; do not expand.
2. **STOP-INVALID:** the judge/evidence contract fails qualification or the
   anchor reveals error that the bounded audit cannot credibly characterize.
   Report H2/H4 as measurement-invalid; do not spend human time rescuing it.
3. **RUN-BOUNDED-AUDIT:** the measurement path is usable and the fixed focal
   sample can materially improve exploratory precision. Draw exactly the
   predeclared sample and stop at the routine cap.

The accepted freeze rule uses `STOP-INVALID` precedence when the evidence
contract/golden set fails, primary-Coder completeness is below 95% overall or
90% in a registered stratum, or the design-weighted AI/AI or minimum human/AI
κ is below 0.60. Otherwise it uses `STOP-SPARSE` when pooled focal failures
are below 10 or either focal context has fewer than five. Every other case is
`RUN-BOUNDED-AUDIT`. Zero AI-reported D/E is not a stop rule: the focal audit
is specifically retained to detect shared misses. These values are encoded
in `config/v2-human-audit.candidate.json` and were explicitly accepted by the
researcher on 2026-08-22 before pilot or confirmatory outcome access.

## 5. Primary and sensitivity labels

- Frozen Coder 1 is the primary H2/H4 label source.
- Missing, refused, or malformed primary output remains missing; neither
  Coder 2 nor a human substitutes a more favorable label.
- Coder 2 is applied to a frozen probability sample as independent-lineage
  sensitivity evidence.
- Human labels estimate measurement properties and audited effect
  sensitivities; they do not rewrite the primary dataset.
- Coder-specific and audited estimates are reported side by side with their
  populations, denominators, and inclusion-probability-aware uncertainty.

## 6. Go/no-go after the benchmark

An interesting, directionally coherent result that survives the bounded
audit may motivate a separate mechanism study with a larger human budget.
That follow-up should be designed around the observed failure mechanism and a
new preregistration, rather than retroactively turning this benchmark's
exploratory H2 into a confirmatory claim.

An uninteresting or measurement-invalid result ends the human work at the
routine cap. This is an informative project decision even though it is not
evidence that the mechanism is absent.

## 7. Prospective bounded-audit check

An outcome-blind 300-replicate check of the existing
`focal_failure_context_srs` implementation at base N=24 compared focal
budgets 100 and 150 under the high-quality null and shared D/E-to-C strong
mechanism, with perfect and 98%-accurate human-reference modes.

- The audit estimator was defined in 98.3–100% of runs.
- Mean absolute Coder-1 sensitivity error fell from roughly 3.8–5.9 points at
  B=100 to 3.0–4.9 points at B=150; specificity error was roughly 1.0–1.6
  points.
- Confirmatory joint support for the shared-bias strong mechanism remained
  only 3–7%, while false support in this limited null check was 0%.

With 300 replicates, a binary Monte Carlo probability has worst-case standard
error about 2.9 percentage points. These results do not select B=150 or prove
coverage. They confirm the intended role separation: B=100–150 can be useful
for exploratory measurement diagnostics, but it cannot upgrade H2 into a
confirmatory claim. The final gate still needs the complete D-005/D-013
dependence structure and prospective precision criteria.

Reproduction core:

```powershell
python -c "from analysis.d010_enriched_audit import run_enriched_audit_grid,default_audit_designs; print(run_enriched_audit_grid(replicates=300,seed=20260809,base_common_ns=(24,),budgets=(100,150),scenario_names=('high_quality_null','shared_de_to_c_strong'),designs=(default_audit_designs()[0],)))"
```
