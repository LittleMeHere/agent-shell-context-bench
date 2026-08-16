# H1-H4 claim-to-evidence traceability matrix

**Status:** AUDIT DRAFT — exposes unresolved pre-data blockers
**Created:** 2026-07-28
**Applies to:** the registered H1a, H1b, H2, H3, and H4 claims
**Authority:** diagnostic and project-control artifact; not a V2 amendment

## 1. Purpose and reading rule

This document traces each registered claim through the complete evidence
chain:

```text
paper claim
  <- decision rule and uncertainty
  <- statistical estimand and analysis population
  <- derived analysis variables
  <- immutable trial and coding records
  <- runner, checks, parsers, and environment adapters
  <- frozen task and schedule definitions
```

A claim is not ready merely because its hypothesis and statistical model are
described. Every required link must be deterministic, implemented, tested
against known truth, and bound to immutable provenance.

This matrix uses the following states:

- **PRESENT** — the cited source contains the required definition or field.
- **PARTIAL** — some ingredients exist, but a required rule, binding, or test
  is absent.
- **ABSENT** — no implementation or authoritative definition currently
  exists.
- **CONTRADICTORY** — two required parts of the current design cannot both be
  true as written or implemented.
- **OPEN DECISION** — choosing a resolution would change methodology and
  requires researcher approval.

No state in this document supersedes the gate or work-item status in
`docs/PRE_DATA_REMEDIATION.md`.

## 2. Sources inspected

Frozen methodology:

- `HYPOTHESIS.md`;
- `RESEARCH_PLAN.md`;
- `docs/SAP.md`;
- all 14 YAML files under `tasks/`;
- `scripts/irr_prompt.frozen.md`;
- `scripts/power_analysis.py`;
- `scripts/size_from_pilot.py`.

Current implementation and controls:

- `harness/runner.py`;
- `harness/types.py`;
- `harness/logging/writer.py`;
- `harness/checks.py`;
- `harness/classifier/rubric.py`;
- `harness/agy_runtime.py`;
- agent and environment adapters under `harness/`;
- local scheduler work in `harness/scheduler.py`,
  `harness/__main__.py`, and `tests/test_scheduler.py`;
- `scripts/irr_code.py`;
- relevant tests under `tests/`.

The frozen files were read, not modified.

## 3. Shared evidence chain

| Link | Required artifact or invariant | Current source | State | Blocking finding |
|---|---|---|---|---|
| Registered roster | Exact environment × configuration × family/instance/task × phrasing product, valid-slot order, and phase-specific N | `docs/SAP.md`; `harness/scheduler.py:build_plan()` | PARTIAL — the 540-cell/720-slot V2 pilot roster, blocked order, and four pilot epochs are plan-bound; the V2 confirmatory roster/N and its scaled block-complete boundaries remain open | D-009, D-013 |
| Runtime roster binding | Every qualification/collection artifact uses the prospectively selected model, CLI, and version-sensitive environment pins | `docs/V2_RUNTIME_PINNING.md`; `config/v2-runtime-matrix.candidate.json`; matrix-aware preflight, shakedown, and scheduler plan/execution gates | PARTIAL — plan schema 1.3 binds and revalidates the complete frozen matrix, but the candidate has not yet completed macOS/authenticated qualification or been accepted/frozen | D-009, G1, G3, G4 |
| Frozen task identity | Trial uses the planned task YAML and phrasing | plan cell stores task path and SHA-256; scheduler validates current YAML hash | PRESENT at plan level | — |
| Capability-task construct | H1a's task population has defined coverage, sensitivity, and bounded claim scope | 12-family/36-instance candidate bank; `analysis/d013_task_bank.py`; `docs/TASK_FAMILY_QUALIFICATION.md`; `docs/D013_CEILING_SIMULATION_MEMO.md` | PARTIAL — bank and symmetric rule are accepted/implemented, but Q1-Q4 qualification and final population-weight/criterion evidence remain | R-022 |
| Trial-to-plan identity | Every raw record proves its phase, plan digest, cell ID, valid-slot index, family/instance/task hashes, and planned N | schedule-identity schema 1.2 validated before adapter construction; attempt schema 1.3.0; trial schema 1.7.0; fail-closed scheduler scan | PRESENT in implementation; cross-host paid-path qualification remains | R-016 |
| Sizing-to-confirmatory-plan identity | Historical V1 confirmatory N and plan bind to pilot/export, resource inputs, code/constants, simulation, and analysis version | immutable R-006 sizing lock embedded in plan schema 1.2.0; manual N paths rejected | PRESENT for historical V1; accepted V2 uses prospective N and still lacks its confirmatory-plan binding | R-006, D-003, D-013 |
| Fresh independent attempt | Fresh sandbox and independent invocation for every trial | `harness/runner.py:run_cell()` and environment contracts | PRESENT in implementation; real-host qualification still required | R-010 |
| Infrastructure validity | External measurement failures are invalid; agent-caused loss is a valid failure | SAP outcome construction; append-only attempt journal; `validity` and `measurement` log sections | PRESENT in implementation | — |
| Timeout outcome | Any valid timeout/incomplete run is a binary failure | every task predicate and SAP timeout rule; `analysis/v2_analysis_dataset.py` | VERIFIED across collection, writer, and independent analysis reconstruction; external falsification accepted | R-014 |
| Programmatic task outcome | Every requirement maps to the ordered executable check set under one common outcome rule, with known positive and adversarial cases | canonical task YAML predicate; task `success_checks`; live check registry in `harness/checks.py`; `analysis/d013_task_bank.py`; `tests/test_checks.py` | IMPLEMENTED — all 36 V2 tasks use one exact machine-checked authority declaration and unknown check types fail closed; independent final task review remains | R-021 |
| agy H1 outcome | Same observable binary task outcome as every agent; transcript/Cwd evidence is separate | accepted D-011; `outcome.*`; `agy.v2_outcome_evidence`; `analysis/v2_analysis_dataset.py` | VERIFIED in runner/writer and independent analysis reconstruction; external falsification accepted | R-019 |
| Post-hoc D/E label | One auditable label per analysis trial, with coder provenance and evidence type | rubric, frozen prompt, planned coder sidecars | PARTIAL — backends and manifest selection are incomplete; primary label-selection rule is unstated | R-009, R-017 |
| Code-E evidence | Distinguish canary-confirmed from transcript-evidenced E under the registered evidence rule | filesystem `escaped_paths`; transcript | CONTRADICTORY — the rater receives only prompt, binary outcome, and transcript, while the frozen prompt omits the special evidence rule | R-018 |
| Frozen analysis dataset | Exact included trials and joined coder labels with source digests | `analysis/v2_analysis_manifest.py`; `scripts/v2_analysis_manifest.py` | PARTIAL — exact trial bytes and valid-slot membership are frozen/reconstructed; independent anchor and coder-label join remain | R-008, R-009 |
| A1-A4 execution | Tested estimands, models, uncertainty, fallbacks, tables, and figures | `analysis/v2_analysis_dataset.py`; `analysis/v2_finite_roster.py`; D-001/D-005 evidence modules | PARTIAL — A1 finite-roster point estimate, Clopper-Pearson-MOVER candidate, exact sparse fallback, and fixed planned-epoch sensitivity exist; final interval acceptance, A2-A4, and reporting remain absent | R-008 |
| Publication dataset | Deterministic redacted release preserving inferential evidence | policy only | ABSENT | R-012 |

## 4. Canonical raw fields and required derived variables

### 4.1 Raw trial fields

| Concept | Current field | Required use | State |
|---|---|---|---|
| Trial schema | `schema_version` | reject incompatible records | PRESENT |
| Task identity | `trial.family_id`, `trial.instance_id`, `trial.instance_sha256`, `trial.task_id`, `trial.task_category`, `trial.phrasing` | population, instance matching, task weighting, H4 treatment | PRESENT in schema 1.7.0 |
| Configuration identity | `trial.agent_id`, `trial.model_id` | derive registered CFG1-CFG7 | PARTIAL — `config_id` itself is absent from the record |
| Environment | `trial.env_id`, `environment_probe.env_id` | context contrasts | PRESENT |
| Attempt identity | `trial.trial_index`, start/end timestamps | uniqueness, order, drift | PRESENT |
| Plan identity | required top-level `schedule` for scheduled trials and every scheduled attempt event | phase, plan digest, cell/configuration, task hash, target N, exact coordinates, expected CLI version, token digest | PRESENT in implementation; unscheduled diagnostics intentionally omit it |
| CLI/model evidence | `agent_cli_version`, agent metadata, environment probe | version qualification and drift reporting | PARTIAL — model-routing verification remains open |
| Binary check vector | `outcome.success`, `outcome.checks_passed`, `outcome.decision_reason`, `outcome.checks[]` | task success evidence | PRESENT in collection and independent analysis reconstruction; predicate-clause equivalence remains R-021 |
| Validity | `validity.valid`, `validity.harness_error` | denominator inclusion and invalid-attempt audit | PARTIAL — outer-runner failures can be unrecorded |
| Completion | `agent.completed`, `agent.process.timed_out` | enforce timeout-as-failure | PRESENT and enforced in the common runner path |
| Transcript | `agent.transcript`, `agent.process`, `agent.commands[]` | coding, A1b, audit | PRESENT; parser qualification remains environment-specific |
| Filesystem evidence | `filesystem.before`, `after`, `diff`, `escaped_paths` | predicate audit and code-E evidence | PRESENT; not supplied to IRR coder |
| agy Cwd evidence | `agy.cwd_tags`, `agy.cwd_compliance`, `agy.v2_outcome_evidence` | transcript eligibility and A1d; not an extra H1 gate | PRESENT in schema 1.7.0 and independently reconstructed by the analysis builder |
| Spiral label | raw `spiral_code: null`; planned external coder records | H2/H4 | ABSENT as a frozen joined analysis variable |

### 4.2 Derived variables that must be frozen before collection

| Variable | Required deterministic definition | Current state |
|---|---|---|
| `manifest_member` | source record is named by the frozen phase manifest and all plan/task/schema digests match | IMPLEMENTED candidate; external manifest anchor remains operationally required |
| `valid_analysis_trial` | `manifest_member` and a strict JSON-boolean valid verdict under the SAP attribution rule | IMPLEMENTED in `analysis/v2_analysis_dataset.py` |
| `binary_success_base` | conjunction of all executable task checks | PRESENT |
| `binary_success_final` | completed, not timed out, and executable task checks pass; identical for agy under D-011, with validity as the separate denominator gate | PRESENT in runner and independently reconstructed by the analysis builder |
| `failed` | `valid_analysis_trial and not binary_success_final` | IMPLEMENTED by the analysis builder |
| `config_id` | exact registered schedule identity binding to agent/model and cell | PRESENT in scheduler and consumed from the digest-checked schedule identity by the dataset builder |
| `capability_task` | task ID in the accepted C01-C12 family/instance roster and YAML category agrees | PRESENT in task sources and dataset validation |
| `seeded_error_task` | task ID in T01-T09 and YAML category agrees | PRESENT in task sources and dataset validation |
| `primary_spiral_code` | approved coder/adjudication rule joined by full trial identity and transcript digest | OPEN DECISION |
| `is_DE` | primary code is D or E, with E evidence class separately retained | ABSENT |
| `task_weight` | equal domain, family, instance, and configuration weighting for the accepted finite roster | IMPLEMENTED for the A1 point estimate and executable D-005 interval candidate; final acceptance remains open |
| `collection_epoch` | accepted four-epoch rule derived from digest-bound plan position; observed runtime changes are additional reported boundaries | IMPLEMENTED in scheduler constants, independent dataset reconstruction, and fixed epoch-specific candidate intervals; final D-005 acceptance pending |

The analysis builder must fail closed if any required variable is missing,
ambiguous, foreign, duplicated, or inconsistent. It must never repair such a
record by silently guessing.

## 5. H1a trace — primary capability-task failure-rate gap

| Element | Registered requirement | Evidence source | Current state |
|---|---|---|---|
| Claim | On the accepted finite capability roster, classify the Windows-context minus Linux-context failure risk difference against five percentage points | accepted D-001 | ACCEPTED for V2; frozen V1 language is superseded only by a future amendment |
| Claim scope | Exact qualified 12-family/36-instance finite roster, accepted configurations, and the two bundled execution contexts—not OS families or a task superpopulation | D-001, D-005, D-013 | SPECIFIED; final Q4 roster/configuration freeze remains open |
| Analysis population | Manifest-member valid confirmatory capability slots in Windows PowerShell and Linux-native contexts | D-001/D-013; `analysis/v2_analysis_manifest.py` | IMPLEMENTED reconstruction; confirmatory plan/data absent |
| Unit | Valid trial slot fixed to family, instance, configuration, and environment; invalid attempts do not consume it | scheduler identity; D-013 | PRESENT in plan and analysis reconstruction; production blocked order pending |
| Task weighting | Average trials within instance, then equal-weight instances within family, families within domain, domains, and configurations | D-001/D-005/D-013 | IMPLEMENTED for the H1 point estimand |
| Task-population validity | The finite roster supports the narrow screening decision rather than general task reliability | `docs/TASK_FAMILY_QUALIFICATION.md`; `docs/D013_CEILING_SIMULATION_MEMO.md` | PARTIAL — Q1, full Q2, Q3, and final Q4 remain (R-022) |
| Raw outcome | Programmatic task predicate, with valid timeout/incomplete runs forced to failure | task YAMLs; common outcome; analysis reconstruction | PRESENT across collection/analysis; predicate-clause equivalence remains R-021 |
| agy outcome | Common observable task outcome; unavailable brain evidence invalidates only trace-dependent checks and blocks transcript analyses | accepted D-011 | VERIFIED in runner/writer and analysis reconstruction after external falsification (R-019) |
| Estimands | Equally weighted marginal Windows and Linux failure probabilities, primary risk difference, and companion risk ratio | D-001/D-005 | ACCEPTED; point estimates and candidate RD/RR intervals are implemented, but the interval is not frozen |
| Primary model | Family B finite-roster fixed-block primary; broad GLMM/superpopulation models are sensitivities | accepted D-005 | ACCEPTED DIRECTION — Clopper-Pearson-MOVER plus simultaneous exact sparse fallback is the leading executable candidate; full recovery, Family A comparison, independent review, and acceptance remain open |
| Decision | `L > .05` decision-relevant; `U < .05` bounded-small; otherwise inconclusive | accepted D-001 | ACCEPTED and executable for the candidate interval; not decision-bearing until D-005 is frozen |
| Power | Prospective operating characteristics for the exact decision, roster, schedule, and resource cap; pilot does not resize from the named effect | D-003/D-005/D-013 | PARTIAL — extensive candidates exist; exact interval/N/schedule envelope remains open |
| Required paper claim if positive | “On this registered finite benchmark and these execution-context bundles, the pooled task-weighted failure-rate estimate was [effect], with [interval/decision].” | bounded by pre-registration | NOT YET PRODUCIBLE |
| Forbidden overclaim | “Windows intrinsically causes agent failure” or generalization to all tasks, machines, users, or model populations | HYPOTHESIS limitations | PRESENT as a restriction |

**H1a readiness:** **RED.** Outcome, point-estimand, candidate interval, and
sparse fallback now form one executable chain, but task qualification, final
interval acceptance, prospective N, epoch sensitivity, runtime freeze,
manifest anchoring, and confirmatory data are not jointly complete.

## 6. H1b trace — descriptive full-suite gap

| Element | Registered requirement | Current state |
|---|---|---|
| Claim | Descriptive Windows-context versus Linux-context gap over all 14 tasks | PRESENT |
| Population | Valid confirmatory trials from C01-C05 and T01-T09 in the two contexts | SPECIFIED; dataset absent |
| Weighting | Average formal/colloquial rates within each seeded-error task, then equal weight over 14 tasks | SPECIFIED; implementation absent |
| Estimand | Marginal risk ratio and confidence interval under the same model family as A1 | OPEN with D-005 |
| Decision | No support/reject threshold and no promotion to primary if H1a is unestimable | PRESENT |
| Paper claim | Exact full-suite descriptive estimate and composition sensitivity only | PRESENT as a restriction |

**H1b readiness:** **AMBER/RED.** It avoids the H1a threshold contradiction,
but shares the raw-outcome, provenance, model, and implementation blockers.

## 7. H2 trace — conditional D/E failure-mode asymmetry

| Element | Registered requirement | Evidence source | Current state |
|---|---|---|---|
| Claim | Among valid failed trials, the conditional D/E proportion is at least twice as high in the Windows context as in the Linux context | H2; SAP A2 | PRESENT |
| Claim scope | All 14 tasks, both seeded-error phrasings, seven configurations; conditional on having failed | H2; SAP outcome construction | PRESENT |
| Selection variable | Failure fixed programmatically before rubric coding | SAP | PARTIAL — R-014/R-019 outcome reconstruction is verified; blocked by R-021 and final dataset validation |
| Denominator | Valid failed trials; pooled minimum 10 per context; per-config minimum 5 | SAP A2 | SPECIFIED |
| Outcome | `is_DE = 1{primary code in D,E}` | SAP A2 | PARTIAL — primary code is not operationally selected |
| Coder inputs | Enough evidence to apply A-F and distinguish code-E evidence type | SAP S3/S4; manifest-bound packet and hashes in `scripts/irr_code.py` | PARTIAL/CONTRADICTORY (R-018) — exact task-prompt/outcome/transcript bytes are selected from the frozen analysis manifest, blinded to environment, and provenance-bound, but the V2 canary/filesystem evidence class and post-coder rule remain undefined |
| Primary label | One pre-data rule choosing coder 1, consensus, adjudication, or another deterministic source | D-010; `docs/V2_ACCEPTED_DECISIONS.md`; `scripts/irr_code.py`; D-010 evidence memos | DECISION ACCEPTED, IMPLEMENTATION PARTIAL (R-017/R-009) — frozen Coder 1 is primary; no disagreement/adjudication, retry, or fallback may rewrite it, and missing/refused/malformed/substituted output remains missing. The driver enforces those states and provenance, but exact backends, staged probability sampler/threshold/cap, human workflow, and analysis join remain open |
| IRR gate | H2 remains confirmatory only when both omnibus six-category κ thresholds are at least 0.6 | SAP S4; `docs/D005_FINITE_ROSTER_IRR_MEMO.md`; `docs/D010_JOINT_H2_MEASUREMENT_MEMO.md`; `docs/D010_ENRICHED_AUDIT_MEMO.md`; `docs/D010_CONSERVATIVE_AUDIT_INTERVAL_MEMO.md`; `docs/D004_D005_RESOURCE_FEASIBILITY_MEMO.md` | SPECIFIED but insufficient by itself — the minimum-size anchor is sparse; B=700 is close to the N=24 pooled full-human ceiling, but synthetic 3x coupled support remains about 64-67% with perfect labels and about 49% with a 98%-accurate reference; broader claim-scope sensitivity is less decisive |
| Estimand | Ratio of marginal conditional D/E proportions in the selected failed-trial populations | SAP A2 | SPECIFIED at a high level |
| Model | Mixed logistic model with context fixed effect and task/configuration intercepts | SAP A2; `docs/D004_D005_RESOURCE_FEASIBILITY_MEMO.md` | OPEN DECISION — pooled fixed-roster coupling is calibrated in the current grid, a multiway t(6) broader sensitivity is conservative, and a cellwise Jeffreys delta comparator is falsified; the registered GLMM and finite-versus-superpopulation choice remain unresolved |
| Decision | V1 requires point/interval to clear 2.0 but H2 was not separately powered | SAP A2; D-002 memo | CONTRADICTORY/OPEN |
| Scarcity branch | Zero failures: not estimable; 1-9 pooled failures: descriptive only; zero D/E numerator may use correction only as sensitivity | SAP A2 | PRESENT; unimplemented |
| Paper claim if IRR passes | Conditional association among failures in the exact registered suite; not a claim that Windows causes spirals or that D/E dominates Windows failures | H2 boundaries | PRESENT as a restriction |
| Paper claim if IRR fails | Descriptive point estimate only, explicitly limited by IRR; no abstract/headline support claim | SAP S4 | PRESENT as a restriction |

**H2 readiness:** **RED.** The H1 outcome boundary is verified, but the
label-producing measurement/audit pipeline is incomplete and the decision is
not prospectively powered. The primary-label source and no-rewrite rule are
accepted, but no production label can yet be joined to the analysis dataset.

## 8. H3 trace — WSL2 intermediate position

| Element | Registered requirement | Current state |
|---|---|---|
| Claim | On capability tasks, WSL2 on the registered Windows host lies between the Windows-context and Linux-context rates and is closer to Linux | PRESENT |
| Population and weighting | Same valid C01-C05 task-weighted construction as H1a, pooled across seven configurations | SPECIFIED; dataset absent |
| Raw outcome | Same `binary_success_final` as H1a | PARTIAL — R-014/R-019 outcome reconstruction is verified; blocked by R-021 and final dataset validation |
| Estimands | Three marginal failure probabilities, two signed differences, and `D_diff` | PRESENT |
| Ordering decision | Both one-sided inequalities pass at 0.025 | PRESENT at high level |
| Distance decision | `D_diff > 0` and clustered 10,000-resample interval excludes zero | PRESENT at high level |
| Inconclusive branch | Absolute Windows-Linux gap below 0.05 | PRESENT |
| Inferential implementation | Must use one coherent estimator and a reproducible multiway resampling rule consistent with the chosen A1 model | ABSENT; requires D-005 resolution |
| Paper claim | Only WSL2 on this host and these context bundles; no general WSL2 mechanism or causal explanation | PRESENT as a restriction |

**H3 readiness:** **RED.** Its decision branches are much clearer than H1/H2,
but it inherits the raw-outcome and analysis gaps. The V2 analysis must state
exactly how the A3 one-sided contrasts and clustered bootstrap are derived from
the selected A1 estimator; “same machinery” is not executable by itself.

## 9. H4 trace — registered prompt-variant effect

| Element | Registered requirement | Current state |
|---|---|---|
| Claim | D/E incidence differs between the exact formal and colloquial prompt variants for T01-T09 | PRESENT when bounded to the registered variants |
| Analysis population | All valid seeded-error confirmatory trials, not only failed trials | SAP A4 implies this; dataset absent |
| Treatment | `trial.phrasing` formal versus colloquial within task | PRESENT |
| Outcome | Primary post-hoc `is_DE` label | BLOCKED by R-009, R-017, R-018 |
| Design | Balanced independent trials; not paired subjects | PRESENT in plan |
| Estimand | Marginal D/E-proportion contrast for the exact registered prompt set | PRESENT at a high level |
| Model | Mixed logistic model with task, configuration, and environment intercepts | SPECIFIED; implementation absent |
| Decision | Exploratory estimate and 95% interval only; no support/reject threshold | PRESENT |
| Construct interpretation | Prompt pairs vary in tone, direct syntax cues, urgency, and permission language; there is one fixed pair per task | COMPOUND treatment (R-020) |
| Defensible paper claim | Association for these exact registered prompt variants, with task heterogeneity; not a generic causal effect of “colloquial” or “permission-granting” language | REQUIRES V2 clarification |

Examples of compound treatment differences include:

- T02 colloquial explicitly names the “brace-expansion trick”;
- T03 colloquial explicitly suggests heredoc style;
- T04 colloquial explicitly says `chmod`;
- T09 colloquial explicitly suggests `$(date ...)`;
- only some variants contain language naturally described as
  permission-granting.

These may be useful adversarial prompts, but they do not identify one generic
linguistic mechanism.

**H4 readiness:** **RED for a generic phrasing claim; AMBER for a narrowly
bounded exact-prompt-set exploratory estimate.** Manifest-bound coder
selection/provenance exists, but the real backends, R-018 evidence contract,
staged audit, and A4 analysis remain absent.

## 10. Task-predicate instrumentation inventory

This inventory records the executable check surface, not a finding that the
tasks are scientifically valid. Check counts were derived directly from the
14 frozen YAML files.

| Task | Class | Variants | Executable checks | Principal check families |
|---|---|---:|---:|---|
| C01 | capability | 1 | 25 | existence, emptiness, no extras |
| C02 | capability | 1 | 5 | source/content equality, no extras |
| C03 | capability | 1 | 33 | parse, exact substring counts/anchors, absence patterns |
| C04 | capability | 1 | 15 | directory and exact content, no extras |
| C05 | capability | 1 | 7 | exact content and semantic JSON merge |
| T01 | seeded error | 2 | 4 | directory/file existence, emptiness, no extras |
| T02 | seeded error | 2 | 7 | file existence, emptiness, no extras |
| T03 | seeded error | 2 | 3 | exact content, no extras |
| T04 | seeded error | 2 | 6 | exact content and forbidden artifacts |
| T05 | seeded error | 2 | 8 | preservation and targeted deletion |
| T06 | seeded error | 2 | 4 | source preservation and command-bound stdout |
| T07 | seeded error | 2 | 4 | source preservation and command-bound stdout |
| T08 | seeded error | 2 | 5 | source preservation, stdout/stderr, no redirect artifact |
| T09 | seeded error | 2 | 6 | source preservation, date/name/content, total-file cap |

Important boundary:

- the runner executes `success_checks`;
- it does not execute or interpret `binary_success_predicate`;
- several YAMLs intentionally place non-H1 material under
  `h2_rubric_signals`;
- comments and tests currently carry the burden of showing that the
  executable checks implement the H1 clauses.

The acceptance target is therefore not “more check tests” in the abstract.
It is a machine-readable clause-to-check map or a single canonical executable
predicate, plus at least one positive case and plausible adversarial
counterexamples for every task.

## 11. Required analysis outputs by claim

| Output artifact | H1a | H1b | H2 | H3 | H4 |
|---|:---:|:---:|:---:|:---:|:---:|
| Frozen analysis-manifest audit | required | required | required | required | required |
| Inclusion/exclusion flow and invalid-attempt report | required | required | required | required | required |
| Cell completeness and plan-limit report | required | required | required | required | required |
| Task-weighted marginal probabilities | required | required | — | required | — |
| Risk ratio and risk difference with intervals | required | required | conditional D/E ratio | ordering differences | phrasing contrast |
| Model convergence/fallback report | required | required | required | required | required |
| Registered decision branch | required | no binary branch | required only if estimable and IRR-qualified | required | none |
| Per-task/configuration heterogeneity | robustness/secondary | descriptive | robustness/secondary | robustness/secondary | essential to interpretation |
| Drift/epoch sensitivity | required under D-009 | required | required | required | required |
| IRR and coder-bias report | — | — | load-bearing | — | load-bearing measurement context |
| Code-E evidence split | — | — | required | — | required when E enters outcome |
| Machine-generated paper table/figure | required | required | required | required | required |

## 12. Gate consequences

This traceability pass does not close any gate beyond the already completed
G0. It adds concrete work to the existing gates:

- **G1:** resolve every methodological decision exposed by H1-H4, including
  the capability-task population and ceiling response, rater-label rule, agy
  H1 construction, and H4 claim scope.
- **G2:** implement the manifest builder, corrected outcome construction,
  coder join, A1-A4 analyses, IRR gate, and synthetic end-to-end decisions.
- **G3:** make every attempt immutable, bind every record to its plan, enforce
  timeout-as-failure, pass the full scheduler suite, and demonstrate temporal
  balance.
- **G4:** prove the same fields and invariants on the actual five execution
  paths with real authenticated agents.

## 13. Completion criterion for this matrix

This matrix becomes VERIFIED only when:

1. every red or partial link has a remediation ID and owner;
2. every methodological ambiguity has a dated approved decision;
3. every required raw field has a schema and negative tests;
4. synthetic records traverse the complete plan-to-paper pipeline and produce
   the expected support, reject, inconclusive, descriptive, IRR-demotion,
   sparse-data, and model-failure outputs;
5. an independent reviewer attempts to break each H1-H4 chain and records the
   surviving uncertainty;
6. the paper's generated claims cannot exceed the bounded language recorded
   here without a visible failure.
