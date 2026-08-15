# Collection scheduler

`python -m harness schedule` retains the historical V1 phases and now builds
the accepted V2 pilot matrix while leaving the existing one-cell runner as
the only trial-execution path. It is
serial by design: the time saving comes from removing manual cell launches,
not from multiplexing vendor sessions or racing agy's shared settings file.

The scheduler is outcome-blind. During pilot and confirmatory collection it
prints only valid/invalid record counts; PASS/FAIL and failure-mode evidence
remain sealed in the immutable trial logs.

## Safety properties

- Status is read-only by default. Paid execution requires `--execute`.
- Real execution refuses to start with the repository (or a descendant) as
  the current working directory. Use an external control directory.
- Pilot, optional vendor mini-pilots, and confirmatory collection use separate
  output roots, each bound to exactly one immutable plan digest.
- V2 plans additionally embed the complete seven-configuration projection and
  substantive SHA-256 digest of an independently supplied `frozen` runtime
  matrix. V2 execution requires that same matrix again and fails before any
  child invocation if it is missing or different.
- Plans lock the complete ordered matrix, family/instance/task IDs, instance
  and task hashes, trial-record schema, target valid N, and expected CLI
  versions before trial 1.
- V2 plans also lock all 720 valid slots in the accepted two-round task-blocked
  order. Each scheduled child carries exactly one valid-slot index. Invalid
  infrastructure attempts retain that index; only a valid attempt advances
  the cell to its next slot.
- Every scheduled child receives a hashed schedule token and validates its
  phase, plan, cell/configuration, task bytes, trial coordinates, schema,
  target N, and CLI-version expectation before constructing an agent adapter.
  The same identity is written into every attempt event and final trial; the
  scanner rejects missing, copied, or foreign identities even under a
  manually matching path.
- Every plan cell carries its matrix-selected CLI version, which is checked
  before each child batch. Historical V1 phases retain their registered legacy
  constants; V2 never falls back to them.
- Resume counts only `validity.valid`. Infrastructure-invalid trials are
  preserved and replaced at new, monotonic trial indices. Valid failures,
  timeouts, and agent-caused damage are never rerun by the scheduler.
- A cell stops after three consecutive all-invalid batches by default. Fix
  the infrastructure, then resume; no immutable log is removed.
- One scheduler lock is allowed per output root. A stale lock is never removed
  automatically.
- Every selected agent requires an explicit inter-trial delay, including an
  explicit zero when the operations log justifies zero. This prevents an
  accidental unthrottled launch.

The collection-start checklist in `data/operations-log.md` still gates the
first real trial. The scheduler does not replace vendor-policy confirmation,
account/authentication checks, VM setup, updater blocking, or the required
preflight shakedowns.

Before creating a pilot plan, run the zero-quota path audit and the
analysis-excluded resource shakedown in
`docs/PRECOLLECTION_SHAKEDOWN.md`. Those tools exercise real adapter paths and
bind shakedown artifacts without treating them as pilot data. They do not
override the G1-G4 gates in `docs/PRE_DATA_REMEDIATION.md`.

## 1. Use an external control directory

PowerShell example:

```powershell
$benchRoot = "C:\path\to\agent-shell-context-bench"
$controlRoot = "C:\tmp\pstax-control"
New-Item -ItemType Directory -Force -Path $controlRoot | Out-Null
Set-Location $controlRoot
$env:PYTHONPATH = $benchRoot
```

The scheduler also prepends the benchmark root to each child's `PYTHONPATH`,
so `python -m harness run` remains importable while the child stays outside
the methodology checkout. `--schedule-token` is an internal scheduler/child
boundary; do not construct it manually or invoke outcome-blind collection by
calling the one-cell runner directly.

## 2. Freeze the accepted V2 pilot plan

The V2 pilot plan is fixed at 540 cells and 720 valid trials. Its capability
portion is 36 instances x two Claude Code configurations x five environments
x one valid trial. Its seeded portion is 18 prompt variants x two
configurations x five environments x two valid trials.

```powershell
python -m harness schedule plan `
  --phase v2-pilot `
  --runtime-matrix "$benchRoot\config\v2-runtime-matrix.frozen.json" `
  --manifest "$benchRoot\data\v2-pilot-plan.json"
```

The command requires matrix status `frozen` and refuses to overwrite an
existing manifest. Review the manifest, embedded matrix digest, and printed
plan digest before execution. A candidate matrix can be used for preflight and
analysis-excluded shakedowns, but cannot create a collection plan.

## 3. Prepare and anchor blinding custody before attempt 1

R-005 uses a two-role boundary. Before the first pilot attempt, an independent
custodian creates an encrypted environment mapping plus Ed25519 signing key.
Only a public commitment is bound into the pilot root and passed to the sizing
analyst. The encrypted custody artifact and passphrase stay with the
custodian. The public commitment must be committed/tagged or otherwise
independently timestamped before collection; R-006 will bind its accepted
digest into the sizing lock.

Run from the external control directory. The script locates the checkout from
its own path. `prepare` loads the frozen plan, initializes and binds the pilot
root, and refuses to run after any attempt exists. All writes refuse
overwrite. It writes encrypted custody and the external commitment first; the
root commitment is the final readiness marker, so any partial failure leaves
pilot execution blocked:

```powershell
python "$benchRoot\scripts\pilot_blinding.py" prepare `
  --plan "$benchRoot\data\v2-pilot-plan.json" `
  --pilot-root "$benchRoot\data\v2-pilot" `
  --commitment-output "$benchRoot\data\pre-registration\v2-pilot-blinding-commitment.json" `
  --custody-output "C:\tmp\v2-pilot-blinding-custody.encrypted.json"
```

Pilot `schedule run --execute` independently validates the bound public
commitment while holding the same atomic lock used by the exporter. Missing,
malformed, re-bound, or wrong-plan commitments fail before child invocation or
attempt allocation. Therefore do not proceed until the external commitment is
anchored and its digest recorded.

## 4. Inspect status without executing

Omitting `--execute` performs a side-effect-free status/dry run:

```powershell
python -m harness schedule run `
  --manifest "$benchRoot\data\v2-pilot-plan.json" `
  --output "$benchRoot\data\v2-pilot"
```

Filters select the corresponding subsequence of valid slots from the
already-frozen order; they never create a new plan or reprioritize work:

```powershell
python -m harness schedule run `
  --manifest "$benchRoot\data\v2-pilot-plan.json" `
  --output "$benchRoot\data\v2-pilot" `
  --only-env windows_powershell `
  --only-config CFG1 `
  --max-cells 10
```

Available configuration IDs are:

| ID | Agent | Model |
|---|---|---|
| CFG1 | Claude Code | `claude-opus-4-8` |
| CFG2 | Claude Code | `claude-sonnet-4-6` |
| CFG3 | Codex | `gpt-5.6-sol` |
| CFG4 | Codex | `gpt-5.6-terra` |
| CFG5 | agy | `gemini-3.1-pro-high` |
| CFG6 | agy | `gemini-3.6-flash-medium` |
| CFG7 | agy | `claude-sonnet-4-6` |

## 5. Execute and resume

After completing the collection-start checklist, set the required Claude
hygiene variables and use the throttle interval recorded in the operations
log. This example intentionally uses a placeholder rather than prescribing an
account-specific rate:

```powershell
$env:DISABLE_TELEMETRY = "1"
$env:DISABLE_ERROR_REPORTING = "1"
$env:DISABLE_FEEDBACK_COMMAND = "1"
$env:CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC = "1"
$env:DISABLE_AUTOUPDATER = "1"
$claudeDelaySeconds = Read-Host "Claude inter-trial delay from operations log"

python -m harness schedule run `
  --manifest "$benchRoot\data\v2-pilot-plan.json" `
  --runtime-matrix "$benchRoot\config\v2-runtime-matrix.frozen.json" `
  --output "$benchRoot\data\v2-pilot" `
  --inter-trial-delay "claude_code=$claudeDelaySeconds" `
  --max-cells 10 `
  --execute
```

Repeat the same command to resume. Completed cells are skipped. An interrupted
cell resumes from the next unused trial index and runs only its remaining
valid-trial deficit.

`--batch-size` defaults to six trials per child process. A smaller value fails
faster when infrastructure is unhealthy; a larger value amortizes CLI probes
and model-pin setup. The scheduler remains serial at every batch size.

## 6. Validate and blind the completed pilot

After all 540 cells contain their frozen one- or two-trial targets, the
custodian runs the export. The command holds an exclusive exporter lock and copies every allowed
source artifact exactly once into a private snapshot. Plan validation,
schedule/attempt-journal checks, outcome extraction, and canonical manifest
hashing all use that same snapshot:

```powershell
python "$benchRoot\scripts\pilot_blinding.py" export `
  --pilot-root "$benchRoot\data\v2-pilot" `
  --custody "C:\tmp\v2-pilot-blinding-custody.encrypted.json" `
  --commitment "$benchRoot\data\pre-registration\v2-pilot-blinding-commitment.json" `
  --output "$benchRoot\data\pre-registration\v2_pilot_blinded.json"
```

The researcher-visible export contains only blinded group labels, public
task/configuration fields, aggregate valid/invalid counts, and digests. It
contains no environment names, named rates, source paths, cell IDs, or trial
indices. It is signed by the committed Ed25519 key and verifies the exact V2
540-cell/720-row multiset. Family, instance, and instance digest remain bound
without revealing the environment mapping.
Re-digested outcome, N, budget, artifact, or key substitutions fail closed.

R-005 is currently IMPLEMENTED, not VERIFIED. Cryptography cannot make one
person unable to inspect a secret they personally hold: the actual run still
requires an independent custodian or an accepted isolated custody procedure,
pre-outcome anchoring evidence, and independent manifest/signature
reconstruction.

## 7. Historical V1 sizing/confirmatory path — not authorized for V2

The remainder of this section documents the already-tested historical V1
R-006 machinery. Do not run it for the accepted V2 design. D-003 now selects
confirmatory N prospectively from frozen simulations and the resource cap;
pilot outcomes validate the instrument and operations but do not resize N.
The V2 confirmatory plan remains open. An exact outcome-blind blocked-order
candidate and fail-closed finite-roster H1 reconstruction now exist in
`analysis/d009_blocked_rounds.py` and `analysis/v2_analysis_dataset.py`, but
the production order/epoch rule and D-005 interval are not accepted or bound
to a confirmatory plan. No V2 confirmatory command is currently authorized.

Do not create or execute the confirmatory plan until the blinded pilot sizing
lock fixes N. Pilot logs and confirmatory logs must use different roots. The
V2 wrapper calls the frozen sizing implementation but requires the accepted
budget, code, analysis, and simulation identifiers and digests. It refuses to
overwrite a prior lock:

```powershell
python "$benchRoot\scripts\create_sizing_lock.py" `
  --pilot-json "$benchRoot\data\pre-registration\pilot_blinded.json" `
  --blinding-commitment "$benchRoot\data\pre-registration\pilot-blinding-commitment.json" `
  --custody C:\secure-off-repo\pilot-blinding-custody.json `
  --passphrase-file C:\secure-off-repo\pilot-blinding-passphrase.txt `
  --compute-budget ACCEPTED_AUTHORITATIVE_BUDGET `
  --per-trial-cost ACCEPTED_COST_OR_TRIAL_UNIT `
  --n-cells ACCEPTED_CONFIRMATORY_CELL_COUNT `
  --code-version ACCEPTED_V2_CODE_VERSION `
  --analysis-version ACCEPTED_ANALYSIS_VERSION `
  --analysis-artifact ACCEPTED_ANALYSIS_ARTIFACT `
  --simulation-version ACCEPTED_SIMULATION_VERSION `
  --simulation-config ACCEPTED_SIMULATION_CONFIG `
  --output "$benchRoot\data\pre-registration\pilot_sizing_lock.json"
```

The custodian runs this step (or controls the isolated process that runs it).
The final lock is signed by the same Ed25519 key committed before pilot
attempt 1. The creator reads the blinded export and public commitment exactly
once, executes the exact snapshotted sizing-source bytes whose hash enters the
lock, and refuses a source change during computation. Supporting-module
hashes are stable start/end source snapshots; the externally frozen code
version/tag, not self-attestation by an already-running Python process, is
their trust root. These placeholders are
intentional: R-006 binds the decisions; it does not make them. Partial inputs,
malformed/tampered source artifacts, an existing output, or an output path
equal to an input fail closed.

The confirmatory plan embeds and validates the complete sizing lock and
derives the Claude N from it; no manual primary-N argument exists:

```powershell
python -m harness schedule plan `
  --phase confirmatory `
  --sizing-lock "$benchRoot\data\pre-registration\pilot_sizing_lock.json" `
  --blinding-commitment "$benchRoot\data\pre-registration\pilot-blinding-commitment.json" `
  --agy-cli-version DAY_ONE_AGY_VERSION `
  --manifest "$benchRoot\data\confirmatory-plan.json"
```

Manual vendor-specific N overrides now fail closed. If an accepted pre-data
procedure later authorizes a larger Codex or agy N, that value needs its own
verified lock and scheduler binding before the plan surface may accept it.

Execution requires an explicit delay for every selected agent:

```powershell
$claudeDelaySeconds = Read-Host "Claude inter-trial delay from operations log"
$codexDelaySeconds = Read-Host "Codex inter-trial delay from operations log"
$agyDelaySeconds = Read-Host "agy inter-trial delay from operations log"

python -m harness schedule run `
  --manifest "$benchRoot\data\confirmatory-plan.json" `
  --output "$benchRoot\data\confirmatory" `
  --blinding-commitment "$benchRoot\data\pre-registration\pilot-blinding-commitment.json" `
  --inter-trial-delay "claude_code=$claudeDelaySeconds" `
  --inter-trial-delay "codex=$codexDelaySeconds" `
  --inter-trial-delay "agy=$agyDelaySeconds" `
  --max-cells 10 `
  --execute
```

The optional `codex-mini-pilot` and `agy-mini-pilot` phases must be planned and
invoked explicitly; the scheduler never launches them automatically.

## Cross-host partitions

Use `--only-env` to run the same persisted plan on the appropriate collection
host. In particular, `macos_actions` must execute on the pinned macOS Actions
runner. The Actions step must change into an external runner-temp control
directory and set `PYTHONPATH` to the checkout before invoking the scheduler.
Execution fails before trial 1 when a selection contains Windows-local cells
on a non-Windows host or `macos_actions` cells on a non-macOS host, so a single
unfiltered all-environment invocation is intentionally not supported.
Do not let separate hosts write concurrently to one shared output root; merge
their immutable, plan-matched artifacts under the same phase root only after
the producing scheduler has stopped.

## Recovery rules

- Child error: fix the reported problem and rerun the identical command.
- All-invalid guard: inspect infrastructure errors without examining task
  outcomes, repair the environment, then resume.
- Stale `.scheduler.lock`: verify no scheduler process is active before
  manually removing that exact lock file.
- Plan mismatch, task hash drift, malformed/foreign logs, duplicate trial
  indices, or overcollection: stop and review. The scheduler fails closed and
  does not rewrite or delete evidence.
