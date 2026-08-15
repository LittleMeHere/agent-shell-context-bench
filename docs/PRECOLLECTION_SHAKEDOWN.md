# Precollection qualification and resource shakedown

**Status:** IN PROGRESS — 79/82 current-manifest calls recorded; macOS pending
**Work items:** D-004, D-007, D-009, R-010, G4
**Analysis status:** every artifact described here is excluded from pilot and
confirmatory inference

## Purpose

This runbook turns precollection checks into manifest-bound evidence without
silently starting the study. It has three distinct layers:

1. zero-quota version and environment-path qualification;
2. a deterministic 82-call resource and transport shakedown; and
3. the separate day-one agy freeze immediately before its compact collection
   epoch.

Passing this runbook is necessary but not sufficient for the pilot. G1-G3 in
`docs/PRE_DATA_REMEDIATION.md` must also be complete.

## Safety boundary

- Never execute from the methodology checkout.
- Never execute a bypass-enabled agent on the researcher's ordinary
  workstation. Use disposable collection VMs or the registered ephemeral
  runner path.
- Keep raw shakedown output in an external private operational root. The
  executor refuses output below this public repository.
- Dry run is the default. A model call requires the explicit `--execute` flag.
- Do not call a shakedown an official agy day-one pin. The day-one
  manifest/hash/archive/re-smoke/updater block happens only when G1-G3 are
  closed and the agy collection epoch is ready to start.

## 1. Zero-quota path audit

`scripts/collection_preflight.py` uses the real environment adapters to run an
environment probe and `<agent> --version`. It never supplies a prompt and
never invokes a model. It also checks the controller's Claude hygiene
variables without recording their values.

For V2, use the explicit candidate or frozen runtime matrix from an external
control directory:

```powershell
$benchRoot = "C:\path\to\agent-shell-context-bench"
$env:PYTHONPATH = $benchRoot
$env:DISABLE_TELEMETRY = "1"
$env:DISABLE_ERROR_REPORTING = "1"
$env:DISABLE_FEEDBACK_COMMAND = "1"
$env:CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC = "1"
$env:DISABLE_AUTOUPDATER = "1"

# E4 only: bind transport identity as well as target/key/port. Generate this
# private file from the provisioned VM before preflight; do not commit it.
$env:PSTAX_GCP_SSH = "user@127.0.0.1"
$env:PSTAX_GCP_SSH_KEY = "C:\private-ops\gcp-key"
$env:PSTAX_GCP_SSH_PORT = "2200"
$env:PSTAX_GCP_SSH_KNOWN_HOSTS = "C:\private-ops\e4-known-hosts"

python "$benchRoot\scripts\collection_preflight.py" `
  --env windows_powershell `
  --env windows_pwsh7 `
  --env windows_wsl2 `
  --matrix "$benchRoot\config\v2-runtime-matrix.candidate.json" `
  --output "C:\private-ops\preflight-windows.json"
```

Run the matching command separately for `linux_native` and on the
`macos_actions` runner. A PASS is scoped only to the named paths in that JSON
artifact. The tool intentionally fails on a prefix collision such as expected
`0.147.0` versus observed `0.147.00`.

For E4 collection evidence, `PSTAX_GCP_SSH_KNOWN_HOSTS` is required by the
operational runbook even though the adapter retains an `accept-new` fallback
for development. When supplied, the adapter sets
`StrictHostKeyChecking=yes`; a missing or changed host identity then fails
closed instead of depending on the controller's personal SSH state.

E4 agent commands run through non-login SSH. Before qualification, the exact
`node`, `claude`, `codex`, and `agy` executables must therefore resolve on that
non-login PATH (for example through explicit `/usr/local/bin` symlinks to the
pinned installation). A successful interactive or `bash -lc` version check is
not sufficient. The zero-quota preflight calls the production environment path
and must pass all four versions before an authenticated smoke.

All production environment process seams close inherited stdin with
`stdin=DEVNULL`. This is part of the non-interactive contract: Codex otherwise
may wait for additional input until the task timeout without emitting an event.

The artifact also binds the matrix status and SHA-256 digest. The legacy
`--agy-cli-version` mode uses the frozen V1 model and CLI constants and is
diagnostic only; it is not a V2 qualification path.

The native Windows environment resolves a bare executable to a
CreateProcess-compatible PATHEXT sibling. This prevents an extensionless npm
POSIX shim from being selected ahead of its Windows `.cmd` launcher. Focused
tests preserve both PATH and extension precedence.

## 2. Resource-shakedown design

Generate the V2 manifest from the same explicit matrix used by preflight:

```powershell
python "$benchRoot\scripts\resource_shakedown_plan.py" `
  --matrix "$benchRoot\config\v2-runtime-matrix.candidate.json" `
  --output "C:\private-ops\resource-shakedown.json"
```

The manifest binds the matrix digest and status. Regenerate it whenever any
candidate model, executable, or environment pin changes; old schema-1.0
diagnostic manifests without that binding are superseded and cannot execute
under the current runner.

The fixed design contains 82 calls:

| Stage | Design | Calls |
|---|---|---:|
| Resource core | 7 configurations × 5 task strata × 2 repeats in Windows PowerShell 5.1 | 70 |
| Transport qualification | workhorse config for each of 3 agents × C01 × 4 non-core environments | 12 |

The five resource-core strata are:

- C01, short capability;
- C05, long capability;
- T01 formal, simple shell-syntax error;
- T05 colloquial, destructive-recovery risk; and
- T09 formal, subtle wrong-output/verification risk.

This is not a power sample. It estimates wall time, surfaced usage, invalid
and retry behavior, rate-limit/routing messages, and whether each real
transport is executable. Two repeats are deliberately modest; heavy tails or
invalids trigger a documented follow-up sample rather than an automatic
claim of precision.

## 3. Dry run and execute

Inspect a provider/path slice first:

```powershell
python "$benchRoot\scripts\resource_shakedown_run.py" `
  --manifest "C:\private-ops\resource-shakedown.json" `
  --output "C:\private-ops\resource-shakedown-output" `
  --stage transport-qualification `
  --env windows_wsl2 `
  --agent claude_code `
  --agent codex
```

On the disposable qualified host, repeat the identical command with
`--execute`. The executor:

- verifies the manifest digest and every task-file hash;
- binds an empty output root to exactly one manifest;
- obtains an exclusive output lock;
- runs one selected call at a time through `python -m harness run`;
- passes the exact CLI version and hides outcomes;
- passes a deterministic schedule identity that binds the child record to the
  shakedown-manifest digest, call, task bytes, configuration, and runtime;
- writes a per-call receipt containing artifact hashes; and
- refuses a duplicate call directory rather than overwriting evidence.

If execution returns nonzero, stop that slice. Do not delete the receipt or
raw artifacts. Diagnose the infrastructure failure, decide whether a new
manifested retry is required, and record it as retry-tail evidence.

As of 2026-08-15, current candidate manifest
`ee6f15cf6b677d24bb2612b4202468ffb2ae41086d68e6f2c8389b895020e023`
has 79/82 private, analysis-excluded receipts: all 70 resource-core calls and
all nine transport calls for pwsh 7, WSL2, and Linux native. The remaining
three calls are the macOS transport slice. The first execution attempt failed
before model invocation because the shakedown child lacked the schedule token
required by R-016; that receipt is preserved, the manifest-bound token path is
covered by regression tests, and the fresh retry completed every attempted
slice.

## 4. What remains manual

Before D-004 can close, the private operational record still needs:

- provider usage-meter observations immediately before and after each block;
- any rate-limit, routing, or model-substitution message;
- active-versus-wait wall time and invalid-attempt tails;
- a 30-50-transcript human timing exercise after these non-analysis
  transcripts exist; and
- evidence that the proposed provider block fits its accepted window with the
  retry reserve intact.

The AI-coder shakedown is separate because D-006 has not selected two
reproducible backends. Do not substitute an agent-under-test call for a coder
cost measurement.

The current candidate selection and exact freeze rule are in
`docs/V2_RUNTIME_PINNING.md`. Candidate status is suitable for this
analysis-excluded shakedown. Pilot and confirmatory collection require the
same matrix to be frozen and propagated into the accepted V2 scheduler.
