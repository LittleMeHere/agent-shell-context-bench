# Deviations log — agent-shell-context-bench

This file records every meaningful deviation from the pre-registered
methodology (`HYPOTHESIS.md` + `docs/SAP.md` + task YAMLs + harness
contracts + `docs/VERSIONS.md`) after the `pre-registration-v1` tag.

The deviation-vs-clarification policy is defined in `docs/SAP.md`
section "Deviation vs. clarification policy". Briefly: changes to
methodology go here as dated entries; implementation bug fixes go
in commit messages with a `Clarification:` prefix in the subject
line and do NOT require an entry here.

When a deviation occurs:
1. Add a new dated entry below this header section (newest at the
   top, above existing entries).
2. State concretely what was pre-registered, what was changed, and
   the reason for the change.
3. State whether the change affects already-collected data and how
   that data is handled (re-analyzed under the new rule; excluded;
   re-run).
4. Reference the commit hash that implemented the deviation.

Entry format (per the existing `docs/DECISIONS.md` convention):

```
## YYYY-MM-DD — <deviation title>

**Pre-registered rule:** <quote or cite the original methodology>
**Deviation:** <what was changed>
**Reason:** <why>
**Effect on collected data:** <re-analyzed / excluded / re-run / no effect yet>
**Implementing commit:** <hash>
```

---

## 2026-08-15 — add an isolated candidate V2 capability task bank

**Pre-registered rule:** V1 registers five capability-task YAMLs (C01-C05)
and nine seeded-error task families (T01-T09). The registered task files are
frozen after `pre-registration-v1`.

**Deviation:** Thirty-six candidate V2 capability-instance YAMLs are added
under the separate `tasks/v2/` namespace: three instances in each of twelve
families spanning six declared domains. No registered V1 task YAML is edited,
and the V2 files remain ineligible for paid collection until the V2 amendment,
qualification gates, frozen runtime matrix/plan, and new pre-data tag are
accepted.

**Reason:** The remediation audit showed that five purposively selected
capability probes omit intended workflow domains and cannot support the stated
broad finite-roster interpretation. The isolated candidate bank permits
outcome-blind construct, predicate, portability, and operating-characteristic
qualification without rewriting the historical V1 task definitions.

**Effect on collected data:** none. No pilot or confirmatory data have been
collected. All current task-bank oracle, counter-policy, and shakedown records
are analysis-excluded qualification evidence.

**Implementing commit:** the commit introducing this entry; candidate tasks,
validators, qualification evidence, scheduler/analysis identities, tests, and
this record land together so the deviation and implementation share one hash.

---

## 2026-08-15 — bind the frozen V1 sizing wrapper to the signed blinded export

**Pre-registered rule:** `scripts/size_from_pilot.py` is the frozen V1 sizing
implementation. Its command-line wrapper accepted a caller-supplied JSON list
of blinded trial rows, while the registered sizing constants and numerical
algorithm operated on those rows.

**Deviation:** The wrapper now accepts pilot input only through the signed,
plan-bound R-005 blinded export plus its pre-outcome commitment. Ad-hoc JSON
lists and a pilot export without the matching commitment fail closed. The
registered sizing constants, task-class filter, numerical algorithm, budget
cap, and output calculation are unchanged.

**Reason:** An unbound list allowed omission, duplication, substitution, or
relabeling of pilot rows before the otherwise frozen sizing calculation. The
R-005 exporter now supplies the exact 460-row roster, sealed-label mapping,
source-manifest digest, signature, and commitment needed to verify that
boundary. Requiring it prevents provenance replacement from silently changing
the confirmatory N.

**Effect on collected data:** none. No blinded pilot or confirmatory data have
been collected. Historical pre-registration smoke records are not analysis
inputs and are unaffected.

**Implementing commit:** the commit introducing this entry; the wrapper,
export/commitment validator, sizing-lock boundary, tests, and this record land
together so the deviation and implementation share one hash.

## 2026-07-05 — agy tool-version pin converted to PIN-AT-COLLECTION-START

**Pre-registered rule:** `docs/VERSIONS.md` pins Antigravity CLI (`agy`)
1.0.7 for configs #5–#7, with a brain-schema re-smoke on the pinned build
(including a deliberately failing command) as a hard PRE-DATA gate.

**Deviation:** The agy version pin changes from a fixed number to
PIN-AT-COLLECTION-START, with an enforceable in-window freeze. On the
first collection day: (a) the probe-observed agy version AND the
`sha512` from the vendor's release manifest are recorded in the
operations log; (b) the manifest URL is snapshotted to archive.org that
same day, creating third-party timestamped proof of what the channel
served (no historical capture of this manifest exists anywhere — the
Wayback CDX index has zero entries for it); (c) the brain-schema
re-smoke (with a deliberately failing command) is repeated that day on
that exact build; (d) the updater host — a domain separate from the
model-serving API — is blocked on the collection VMs, so the build
provably cannot change inside the window, and the binary hash can be
re-verified at any time; (e) the researcher retains a private copy of
the binary for later re-verification (vendor licensing does not permit
public redistribution). Every trial record additionally captures the
actual CLI version (`agent_cli_version`), so any anomaly is visible in
the data itself.

**Reason:** A fixed pin is unenforceable on agy's distribution channel
and pretending otherwise would falsify provenance. Demonstrated
empirically while discharging the gate: the tag-eve pin was 1.0.7; the
installed CLI had self-updated to 1.0.9 when the gate re-smoke ran on
2026-07-04 (PASS, all eight criteria — evidence in
`data/pre-registration/2026-07-04T04-11-01Z-agy-resmoke/`); by
2026-07-05 the CLI had self-updated again to 1.0.16. Google's installer
serves only the latest build, self-updates in place, and documents no
version archive, so no chosen number can be installed or held. Codex
(versioned release artifacts, no self-update; pin 0.139.0 verified
exactly) and Claude Code (version-addressable install +
`DISABLE_AUTOUPDATER`; pin 2.1.176 enforceable at collection-VM setup)
keep their fixed pins — the discipline differs per channel because
enforceability differs per channel. The gate's schema evidence stands:
the parser held unchanged from the 1.0.2 characterisation through real
1.0.9 output, so schema drift across vendor self-updates has been low;
the day-one re-smoke re-verifies this on whatever build collection
actually runs.

On replicability: a fixed number never provided binary obtainability
for agy — no reader could install 1.0.7 under the old pin either, since
the vendor serves only the latest build to everyone. The day-one record
(exact version + binary hash + third-party-archived manifest + frozen
in-window binary) is strictly more verifiable than the fixed number it
replaces. Binary obtainability remains vendor-constrained and is
disclosed as a limitation — the same class as the served-model
non-replicability that all three vendor arms already carry, since every
CLI is a thin client to a remotely served model.

**Effect on collected data:** none; no benchmark data has been collected.

**Implementing commit:** the commit introducing this entry (also updates
the `docs/VERSIONS.md` roster row and change log).

## 2026-07-03 — Pre-collection audit: fix construct-validity defects in success checks

A pre-collection adversarial audit (red-team of all 14 task YAMLs against
the exact `checks.py` semantics, plus empirical verification on real
PowerShell 5.1 and the real recorded Claude Code capture) found defects
that would have forced mid-collection deviations. All fixes land before
any benchmark data exists.

**Pre-registered rule → deviation, per finding:**

1. **Content checks read strict UTF-8.** Now: BOM-sniffed decode
   accepting UTF-8 (with or without BOM) and BOM-marked UTF-16.
   Verified on real PS 5.1: `>` writes UTF-16LE+BOM and
   `Set-Content -Encoding UTF8` writes a UTF-8 BOM, so a byte-correct
   answer written with the environment's default idioms failed — and
   only on the PS 5.1 arm, i.e. measurement error correlated with the
   treatment variable, biasing H1 toward the hypothesis. No prompt
   constrains encoding, so encoding is not part of any task's construct.

2. **`file_content_equals` and `agent_any_command_stdout_equals`
   compared trailing newlines exactly.** Now: both sides are compared
   with trailing newlines stripped. The real Claude Code capture trims
   the final newline from recorded stdout while every YAML `expected`
   block ends with one — exact comparison failed every real trial of
   T06/T07/T08 regardless of agent behaviour. Same class: heredoc/echo/
   `Set-Content` append a file-final newline, `printf`/Python `write`
   don't, and no prompt pins the convention.

3. **T06/T08 used `agent_all_command_stderrs_empty` (all commands).**
   Now: `require_empty_stderr: true` on the stdout check — the
   answer-producing command must be stderr-clean. The all-commands form
   contradicted the pre-registered `required_final_stderr_exact: ""`
   (final, not all) and scored the canonical fire-then-recover
   trajectory (classification code B) as H1 failure, mechanically
   inflating the hypothesized effect.

4. **T08 seeded `noisy.ps1` with `[Console]::Error.WriteLine`.** Now:
   `Write-Error`. Verified empirically on PS 5.1 (2026-07-03): the
   .NET call bypasses PowerShell stream redirection in-process, so the
   task's own canonical solution (`.\noisy.ps1 2>$null`) still leaked
   stderr — the task was near-unpassable by its intended answer. With
   `Write-Error`, `2>$null` suppresses fully and the unsuppressed trap
   still fires.

5. **T07/T08 `command_regex` accepted only bare `.\`/`./` invocations;
   the echo-forbid regex matched any use of an echo verb.** Now: the
   invocation regex also accepts quoted call-operator (`& '.\run.ps1'`),
   absolute/variable-prefixed paths, and `-File` forms (all
   regex-verified); the forbid regex only disqualifies an echo verb
   whose argument is a quoted literal or here-string, so a legitimate
   `... | ForEach-Object { Write-Output $_.Line }` is no longer
   disqualified. Command-text constraints are applied to
   comment-stripped command text (closes the `"..." # app.log` smuggle).

6. **C03 prompt told agents to leave string-literal content unchanged
   while the checks required renaming inside `__all__ = [...]`.** Now:
   the prompt states the `__all__` entry is a code export to rename.
   The contradiction penalized exactly the careful (AST-based) agents.
   Additionally, location anchors (exact post-rename lines) were added:
   the cardinality-only counts accepted renaming the right NUMBER of
   wrong occurrences.

**Accepted, documented, not changed:** `no_extra_files` does not see
empty directories (snapshot-files-only, uniform across arms); T09 accepts
a hardcoded-current-date backup (H1 is outcome-based by design); Codex
and agy adapters do not populate per-command stderr the way Claude Code
does — cross-agent comparability of the T06/T08 stderr requirement is
deferred to the pre-data real-CLI smoke gate already mandated by
`docs/VERSIONS.md` (Codex 0.139.0 / agy 1.0.7 re-smoke with a
deliberately failing command). Also accepted, all reachable only by
deliberate deception (agents never see `success_checks`) or already
by-design: files smuggled under ignore-listed cache dirs evade
`no_extra_files`; modify-then-restore of a protected file passes H1
(final-state equality is the pre-registered outcome; transients are
H2's job via the before/after diff); T07's leftover `$env:LOG_LEVEL`
passes H1 (already documented in the YAML as H2-rubric-only); a
wrapper-script-shadowing spoof on T07 (plant, invoke, delete before
snapshot); and PS-redirect "empty" files failing `file_is_empty`
because the redirect writes BOM bytes — judged a real measured
behavior (the file genuinely isn't empty), not a check artifact.

**Reason:** every fixed item either (a) failed correct solutions — three
of them in ways correlated with environment or agent-tooling choice, the
exact confound structure H1 measures — or (b) contradicted the
pre-registered predicate text. Discovered before any collection;
discovered during collection each would have been a data-tainting
deviation.

**Effect on collected data:** none; no benchmark data has been collected.
Regression tests were added for every fixed defect, including positive
tests using real captured bytes (PS 5.1 redirect output, BOM'd
Set-Content output, trailing-newline-trimmed adapter stdout) — the
previously missing positive tests for C02/C04 are what let the encoding
defect survive earlier review.

**Implementing commit:** the commit introducing this entry (lands
together with the 2026-06-26 hardening below in one working set, so each
entry shares its implementation's hash).

## 2026-06-26 — Harden dynamic/stdout success checks against reward-hacking

**Pre-registered rule:** T06, T07, and T08 encoded terminal-output success
with `agent_any_command_stdout_equals`; T09 encoded the dated backup
filename as any ISO-shaped `app.log.YYYY-MM-DD` matching regex plus content
equality.

**Deviation:** The agent-trace stdout check now supports command-text
constraints, and T06/T07/T08 require the stdout-producing command to be tied
to the intended input file or script rather than a direct echo of the
expected answer. T09's regex now captures the date component and compares it
to the trial-start date, with a ±1 day tolerance for UTC runner timestamp vs.
environment-local calendar date differences. Regression tests were added for
the formerly passing spoof cases.

**Reason:** Review found construct-validity gaps: agents could hard-code or
echo the expected stdout for T06/T07/T08, or create `app.log.<any ISO date>`
for T09, and still pass H1 despite not satisfying the task intent.

**Effect on collected data:** No effect yet; no post-tag benchmark data has
been collected under the weaker checks. If any pilot/smoke outputs used the
weaker rules, they should be discarded or re-evaluated with the hardened
checks before analysis.

**Implementing commit:** the commit introducing this entry — the check
hardening, task YAML updates, regression tests, and this log entry land
together so the deviation and its implementation share one hash.

## 2026-06-13 — Initial deviations log, established at the `pre-registration-v1` tag (commit `34104be`; log first scaffolded during 2026-05-25 drafting)

**No deviations from the pre-registered methodology as of this commit.**

This entry exists so the absence of deviations is legible: an empty
file would be ambiguous. This entry says explicitly that nothing has
happened.

The pre-registered methodology as of this commit is defined by:
- `HYPOTHESIS.md` (H1a, H1b, H2, H3, H4, reporting rules, IRR
  conditionality, code-E evidence requirement)
- `docs/SAP.md` (Configuration eligibility, Outcome construction,
  A1 / A1b / A1c, A2, A3a / A3b / A3c, A4, S1–S6 including the S3
  evidence requirement and the S4 hard IRR Interpretation rule,
  Stopping rules including the pilot-sizing formula and the
  variance-generalization disclosure, Deviation vs. clarification
  policy)
- `docs/VERSIONS.md` (V1 confirmatory matrix, pinned tool versions,
  IRR coders + same-vendor substitution rule, pre-tag gate status)
- The 14 task YAMLs in `tasks/capability/` (C01–C05) and
  `tasks/trap/` (seeded-error tasks T01–T09; folder path retained as
  internal legacy identifier per 2026-05-30 DECISIONS), each with its
  `binary_success_predicate`
  (split into `h1_binary_checks` vs `h2_rubric_signals` where the
  pre-registered intent exceeds what `success_checks` can verify
  from the snapshot alone)
- The harness contracts in `harness/` (`EnvironmentAdapter`,
  `AgentAdapter`, `checks.py`, `classifier/rubric.py`, the
  canary-sentinel system in `EnvironmentAdapter.canary_paths()` /
  `set_canaries()` / `check_canaries()`)
- The frozen IRR prompt at `scripts/irr_prompt.frozen.md` with its
  sha256 drift gate enforced by `scripts/irr_code.py`
  `check_prompt_frozen()`

Any change to the above after this tag is a candidate deviation per
the SAP "Deviation vs. clarification policy". Implementation bug
fixes that do not alter the methodology (e.g., adding a tool name to
the parser's `_SHELL_TOOLS` set) are clarifications, not deviations,
and are logged via commit message rather than here.
