# Pinned Versions — reproducibility manifest

Every number in the paper is tied to specific tool/model versions. This
file is the single aggregated record. Two states per entry:

- **CONFIRMED** — verified now, frozen.
- **PIN-AT-START** — must be filled in and frozen *before* the
  `pre-registration-v1` tag, then never changed (a change after data
  collection is a logged DEVIATION).

> **Hard gate:** the `pre-registration-v1` tag MUST NOT be cut until every
> PIN-AT-START row in the **V1 primary** tables below is filled with an
> exact version and a "verified on" date. Re-verify CONFIRMED rows at the
> same time — toolchains drift. PIN-AT-START rows in the **Extension
> candidates** table are V2 obligations under SAP S5 promotion, NOT V1
> tag-gating: extension cells are excluded from V1 primary H1-H4
> inference (see SAP "Configuration eligibility" and DECISIONS.md
> 2026-05-25), so their model pins do not gate the V1 tag.

> **V1 pre-tag gate status (2026-05-25 (later) — superseded the same-day narrowing):**
> Per `docs/DECISIONS.md` 2026-05-25 (later), pre-reg locks the
> **methodology** of the V1 matrix — not the *implementation* of every
> cell. PIN-AT-START is a legitimate pre-reg state for V1 cells whose
> adapters land post-tag. The hard gate is satisfied when every CONFIRMED
> row that backs the methodology is CONFIRMED *and* every PIN-AT-START
> row has a frozen pin value (model label + CLI version), even if the
> adapter implementing that row is post-tag work.
>
> - Harness host environment — **CONFIRMED**.
> - Windows shell pin (PS 5.1) — **CONFIRMED** (5.1.26100.8457, D2).
> - Windows shell pin (pwsh 7) — **CONFIRMED** (7.5.5 already installed).
> - Primary V1 matrix (7 configs × 5 envs) — **PINS CONFIRMED at the
>   methodology layer; adapter implementation per-row status below.**
> - IRR coders — **CONFIRMED**.
> - **V1 hard gate is SATISFIED at the methodology layer.** The per-row
>   "adapter pending" entries below are implementation work scheduled
>   post-tag; per the methodology-vs-implementation distinction in
>   DECISIONS.md, this is not a tag-blocker.

## Harness host environment — CONFIRMED 2026-05-18

| Component | Version |
|---|---|
| Python | 3.11.9 |
| PyYAML | 6.0.3 |
| numpy | 2.4.2 |
| scipy | 1.17.1 |
| statsmodels | 0.14.6 |

(Power analysis `scripts/power_analysis.py` is deterministic under these;
RNG seed 20260515.)

## Windows shell pins — CONFIRMED

Both Windows shells are pinned. V1 measures across both as parallel
Windows environments — the within-Windows comparison is a built-in
mechanism check ("does upgrading the shell close the cross-context
gap?"). The original D2 (2026-05-23) pinned PS 5.1 as the modal Windows
experience; the 2026-05-25 (later) scope correction added pwsh 7 as the
second Windows cell because pwsh-7-default adoption is expected to grow
materially during the writeup's reading window.

| Component | Version | State |
|---|---|---|
| Windows PowerShell (`powershell.exe`) — V1 cell E1 | **5.1.26100.8457** on Windows 11 Home (verified 2026-05-23 via `powershell.exe -NoProfile -Command "$PSVersionTable.PSVersion.ToString()"`) | CONFIRMED — V1 Windows-5.1 shell; `PowerShellEnvironment` invokes `powershell.exe -NoProfile -NonInteractive` |
| PowerShell 7 (`pwsh.exe`) — V1 cell E2 | **7.5.5** on Windows 11 Home (already installed) | CONFIRMED — V1 Windows-7 shell; env adapter is a subclass of `PowerShellEnvironment` pointing at `pwsh.exe`, ~2h post-tag implementation |

Seeded-error tasks T01-T09 (renamed from "trap tasks" per
`docs/DECISIONS.md` 2026-05-30 — TRAP acronym taken by
arXiv:2512.23128; the file path `tasks/trap/` is retained as an
internal legacy identifier) are annotated per-shell. The full
per-task shell-applicability table is below (added 2026-05-26 per
pre-tag audit Q3, `docs/DECISIONS.md`): T01 is the only
PS-version-specific seeded error (pwsh 7 added `&&` in 7.0); T02-T09
all trigger identically on both PS 5.1 and pwsh 7 because their
underlying bash-vs-PowerShell semantic gap is unchanged across the
PowerShell major versions.

| Task | Underlying bash idiom | PS 5.1 triggers? | pwsh 7.5.5 triggers? | Pre-registered shell-upgrade signal |
|---|---|---|---|---|
| T01 | `cmd1 && cmd2` chain | yes (no `&&` parser) | **no** (pwsh 7.0 added `&&` / `\|\|` pipeline-chain operators) | **positive** — shell upgrade closes the gap |
| T02 | `touch {a,b,c}.txt` brace expansion | yes (literal filename) | yes (no brace expansion in any PS version) | null — upgrade does not help |
| T03 | `cat > f <<EOF ... EOF` heredoc | yes (no `<<` operator) | yes (no heredoc in any PS version; here-strings `@'...'@` only) | null — upgrade does not help |
| T04 | `chmod 755 file` | yes (NTFS uses ACLs, not POSIX mode bits) | yes (filesystem semantics unchanged in pwsh 7) | null — upgrade does not help |
| T05 | `find . -name X -exec rm {} \;` | yes (GNU `find` not present) | yes (no GNU find bundled with pwsh 7) | null — upgrade does not help |
| T06 | `cat \| grep X \| head -5` pipe | yes (no `grep` alias; object pipeline) | yes (no grep, same object pipeline semantics) | null — upgrade does not help |
| T07 | `VAR=value cmd` inline env prefix | yes (parsed as assignment, not env-scoped invocation) | yes (parsing behaviour unchanged) | null — upgrade does not help |
| T08 | `cmd 2>/dev/null` stderr discard | yes (creates literal `null` file artefact) | yes (no `/dev/null`; bit-bucket is `$null` in both versions) | null — upgrade does not help |
| T09 | `cp f f.$(date +%Y-%m-%d)` date substitution | yes (`date` aliased to Get-Date; doesn't accept `+%fmt`) | yes (same alias + same .NET formatter semantics) | null — upgrade does not help |

**Pre-registered expectation for the PS-5.1-vs-pwsh-7 mechanism check.**
Of the 9 seeded-error-task within-Windows shell contrasts, **1 is
pre-registered positive (T01) and 8 are pre-registered null
(T02-T09)**. The mechanism-check finding is therefore "does shell
upgrade close the gap?" → "only for chain operators (T01); not for any
of the other 8 seeded-error-class mechanisms." This is the
pre-registered expected pattern, auditable here before data collection.
A null result on T02-T09 is **confirmatory of the design's
expectation**, not a measurement failure; a positive result on any of
T02-T09 would be a finding that contradicts the per-task design notes
and should be flagged for follow-up. The per-task design notes inside
each `tasks/trap/*.yaml` carry the same information per-task; this
table is the consolidated cross-task view.

The capability tasks (C01-C05) do not have shell-version-specific
expectations; they probe general agent reliability on both shells and
any PS-5.1-vs-pwsh-7 gap on capability tasks would be exploratory.

## V1 primary confirmatory matrix — 7 configs × 5 environments × 14 tasks

Per `docs/DECISIONS.md` 2026-05-25 (later). The 3 CLI versions below are all
**CONFIRMED via real smoke trials on 2026-05-25** (each CLI was invoked
with its harness-equivalent flag set and produced parseable structured
output — see DECISIONS.md and the trial artifacts under
`data/pre-registration/smoke_trials/`). Per-row "adapter pending" notes
flag implementation work that ships post-tag; methodology is locked
either way.

### Configurations (7)

| # | Agent | CLI version | Model | Role | State |
|---|---|---|---|---|---|
| 1 | Claude Code | **2.1.159** (re-verified 2026-06-09 via `claude --version`; was 2.1.150/2026-05-24 and 2.1.143/2026-05-18; all six pinned flags re-confirmed unchanged against `claude --help` on 2026-06-09 — see VERSION PIN block in `harness/adapters/claude_code.py`) | **`claude-opus-4-8`** (upgraded from `claude-opus-4-7` per 2026-05-30 DECISIONS — Anthropic released Opus 4.8 as the current frontier) | Anthropic frontier | adapter CONFIRMED / parser CONFIRMED on 2.1.143 fixture (schema unchanged through 2.1.150; 12 regression tests pass 2026-06-09; live stream-json re-smoke on 2.1.159 recommended before tag) / flags CONFIRMED 2026-06-09 / model CONFIRMED |
| 2 | Claude Code | **2.1.159** (same as above) | **`claude-sonnet-4-6`** | Anthropic workhorse | adapter CONFIRMED / parser CONFIRMED / model CONFIRMED |
| 3 | Codex CLI | `codex-cli` **0.133.0** (verified via `codex --version` 2026-05-23; was 0.130.0/2026-05-18; `codex doctor` clean 2026-05-25 — auth configured, websocket connected, default model `gpt-5.5`) | **`gpt-5.5`** (xhigh reasoning, default per `~/.codex/config.toml`) | OpenAI frontier | model PIN CONFIRMED / adapter PIN-AT-START — `codex exec --json` schema characterised via smoke on 2026-05-25 (`item.completed.command` / `item.completed.exit_code` / `item.completed.aggregated_output` are structured); adapter is ~6h post-tag work |
| 4 | Codex CLI | same as above | **`gpt-5.4-mini`** | OpenAI workhorse | model PIN CONFIRMED / adapter PIN-AT-START (same adapter as #3) |
| 5 | Antigravity CLI (`agy`) | **1.0.4** (re-verified 2026-06-09 via `agy --version`; `-p`/`--print` non-interactive flags re-confirmed via `agy --help` the same day; the 2026-05-25 transcript-schema smoke ran on 1.0.2 — re-smoke on 1.0.4 recommended before adapter build; originally 1.0.2 installed 2026-05-23 via `irm https://antigravity.google/cli/install.ps1 \| iex`; binary at `%LOCALAPPDATA%\agy\bin\agy.exe`; PATH-configured via `agy install`; smoke 2026-05-25 confirmed: tool_calls in `transcript_full.jsonl` are structured; model pin works via `settings.json` write; `agy --help` verified 2026-05-27 exposes `--print` as non-interactive prompt mode). **Auth path for V1 data collection: official subscription `agy` / Antigravity SDK on Google AI Ultra** per docs/DECISIONS.md 2026-05-27. | **`Gemini 3.1 Pro (High)`** (pin via `~/.gemini/antigravity-cli/settings.json` `model` field write; subscription availability confirmed through the installed first-party agy surface / model label workflow) | Google frontier | model PIN CONFIRMED / adapter PIN-AT-START — needs (a) brain-snapshot diff to locate per-trial conversation, (b) PLANNER_RESPONSE.tool_calls extraction, (c) regex parse of RUN_COMMAND.content for exit code / stdout, (d) prompt-injected Cwd directive (SAP "Outcome construction" — agy-specific rules), (e) official-subscription `agy --print` / SDK invocation wiring |
| 6 | Antigravity CLI (`agy`) | same as #5 | **`Gemini 3.5 Flash (Medium)`** (settings-UI label confirmed 2026-05-25; the workhorse counterpart to Pro (High) — Medium reasoning effort matches realistic cost-sensitive use rather than over- or under-spending; symmetric with Codex's `gpt-5.4-mini` at default reasoning) | Google workhorse | model PIN CONFIRMED / adapter PIN-AT-START (same adapter as #5) |
| 7 | Antigravity CLI (`agy`) | same as #5 | **`Claude Sonnet 4.6 (Thinking)`** (settings label CONFIRMED via 2026-05-23 verification — exact-case label that propagates Sonnet; lowercase `(thinking)` falls back to Gemini) | **same-model harness-control vs #2** (Claude Sonnet 4.6 in two harnesses across all 5 envs — pre-registered S6 analysis) | model PIN CONFIRMED / adapter PIN-AT-START (same adapter as #5) |

### Environments (5)

| ID | Environment | State |
|---|---|---|
| E1 | Windows 11 + **PowerShell 5.1** (`powershell.exe` 5.1.26100.8457) | env adapter CONFIRMED (`PowerShellEnvironment`) |
| E2 | Windows 11 + **pwsh 7.5.5** (`pwsh.exe`) | env adapter PIN-AT-START — subclass of `PowerShellEnvironment` pointing at `pwsh.exe`, ~2h post-tag implementation |
| E3 | Windows 11 + **WSL2 Ubuntu 22.04** | env adapter PIN-AT-START — `wsl -d Ubuntu-22.04 --` wrapper, ~3h post-tag implementation |
| E4 | **Linux native** (GCP Ubuntu 22.04 on `e2-small`) | env adapter PIN-AT-START — SSH wrapper, ~4h post-tag implementation |
| E5 | **macOS** (GitHub Actions `macos-14` runner) | env adapter PIN-AT-START — Actions YAML + harness self-invocation, ~4h post-tag implementation |

### Notes on the roster

- **Claude Code is the V1-runnable cell at tag time.** Adapter built, parser verified against real stream-json output (2026-05-18 smoke trial caught + fixed the PowerShell-tool parser bug; refreshed 2026-05-25 smoke confirmed 2.1.150 schema unchanged), fixture frozen with PII-clean assertion + 12 regression tests in `tests/test_claude_code_parser.py`.

- **Codex is V1 primary with adapter post-tag.** 2026-05-25 smoke (`codex exec -m gpt-5.4-mini --dangerously-bypass-approvals-and-sandbox --ephemeral --json -C <sandbox> "..."`) returned exit 0 with parseable JSONL: `item.completed.command`, `item.completed.exit_code`, `item.completed.aggregated_output` are structured fields (cleaner schema than Claude Code's tool_use_id pairing). `-C <dir>` binds the sandbox correctly (subprocess CWD inheritance also works as backup). Token usage on `turn.completed.usage`. Adapter is the obvious next implementation after Claude Code's pattern.

- **agy is V1 primary with adapter post-tag.** 2026-05-25 smoke confirmed `~/.gemini/antigravity-cli/brain/<conv-id>/.system_generated/logs/transcript_full.jsonl` carries structured `PLANNER_RESPONSE.tool_calls[]` with `CommandLine`, `Cwd`, args. Model pinning works via `~/.gemini/antigravity-cli/settings.json` write (`model` field). **V1 data collection uses official subscription `agy` / Antigravity SDK on Google AI Ultra** per docs/DECISIONS.md 2026-05-27, superseding the earlier Vertex-on-alt-GCP plan for V1. Local `agy --help` exposes `--print` as non-interactive prompt mode, and Google documents Antigravity SDK as a first-party programmatic surface. Config #7 (`Claude Sonnet 4.6 (Thinking)`) is available directly through subscription `agy`; no separate cloud quota or billing path is needed for V1. Cwd-binding is unique to agy and uses the prompt-injected directive strategy with measured per-trial compliance (see SAP "Outcome construction" — agy-specific rules); a `~/.gemini/antigravity-cli/scratch/.pstax_canary_agy_scratch` canary is added per agy trial to detect destructive actions in scratch. The earlier same-day narrowing entry's "Antigravity excluded from V1" assessment was based on incomplete inspection (the `.antigravitycli` working-dir is empty, but the brain/ path under USERPROFILE carries the actual transcript); it has been superseded.

- **Cursor and the Antigravity IDE remain excluded** from the matrix per 2026-05-18 (no headless `cursor-agent`; the Antigravity desktop IDE is GUI-bound — distinct from `agy` the CLI, which is V1 primary).

## IRR coders (SAP S4 — layered design)

| Role | Identity | State |
|---|---|---|
| AI Coder 1 (primary) | **`claude-opus-4-8`** (Anthropic, frontier) — pinned 2026-05-23, upgraded from `claude-opus-4-7` per 2026-05-30 DECISIONS to track the current Anthropic frontier release | PIN CONFIRMED — re-verify model availability at IRR-run-time |
| AI Coder 2 (independent) | **`gpt-5.5`** (OpenAI, frontier; different lineage from Coder 1) — pinned 2026-05-23 | PIN CONFIRMED — re-verify model availability at IRR-run-time |
| Human anchor | the researcher (stratified random ≥50 subset, per SAP S4) | n/a (human) |
| Optional premium audit | Deep Think (web-only, manual, ≤~20 hardest cases) | optional, not load-bearing |

**Substitution rule (pre-registered).** If a pinned IRR coder model is
unavailable at IRR runtime — vendor deprecation, API access change, or
any other reason the exact pinned model ID can no longer be invoked —
the substitute is the **next-frontier-tier model from the same vendor
at the same approximate reasoning level** (e.g. `gpt-5.5` → its
successor at the same reasoning tier; `claude-opus-4-8` → its successor
at the same tier). Same-vendor substitution is required (not preferred,
required), because the SAP S4 same-vendor-bias check is a
lineage-coverage design: swapping a coder to a different vendor would
silently change which configurations have a same-lineage coder, breaking
the bias-check's interpretation. The substitution event is logged in
`DEVIATIONS.md` with: (a) the original pin, (b) the substitute model
ID + version + verified-on date, (c) the date the original became
unavailable, and (d) explicit verification that the substitute is the
same-vendor next-frontier-tier model at the same approximate reasoning
level. If no same-vendor substitute exists at IRR runtime (the vendor
has exited the frontier-model market entirely), IRR coding proceeds
with the remaining single AI coder plus the human anchor; this collapses
AI–AI κ to undefined and **automatically triggers the SAP S4 Interpretation
rule's demotion of H2 from confirmatory to descriptive/exploratory** —
no separate decision is required, and the demotion is logged in the
paper exactly as it would be under a κ_AI < 0.6 outcome.

The exact Coder 1 / Coder 2 model IDs **and the verbatim grading prompt**
(`scripts/irr_code.py` + its frozen prompt file) are committed before
coding begins so the labeling is reproducible.

**Lineage-coverage status (revised 2026-05-25 (later)):** the SAP S4
design pre-registers a same-vendor-bias check (does an AI coder rate
transcripts from its own-lineage agent-under-test more leniently?). With
the 2026-05-25 (later) full-matrix restoration:

- Coder 1 (`claude-opus-4-8`) is same-vendor for Claude Code configs (#1 and #2) and same-vendor for the harness-control agy × Claude Sonnet (#7).
- Coder 2 (`gpt-5.5`) is same-vendor for Codex configs (#3 and #4).
- Neither coder is Google-lineage. The agy × Gemini configs (#5 and #6) have **no same-lineage coder available** — both coders are out-of-lineage. The same-vendor-bias check is therefore reported only for the four configs (#1, #2, #3, #4, #7) where a same-vendor coder exists. The two Gemini-bearing configs (#5, #6) get a no-same-lineage-coder disclosure rather than a bias check. This is a residual limitation, not a methodological failure — Google's frontier coder model is not API-accessible in a form that meets S4's reproducibility requirements (Gemini 3.1 Pro is API-accessible but the Antigravity-CLI-via-agy is the agent-under-test, not the coder; using it as coder would conflate roles).

## Environments (captured per run, not pinned here)

Windows/PowerShell, Windows/WSL2, Linux native (small GCP instance), macOS
(GitHub Actions). Exact OS/shell/toolchain versions are captured at run
time by `EnvironmentAdapter.probe()` and written into every trial log —
that per-trial capture, not this file, is the authoritative environment
record (machine-specific identifiers are intentionally not hard-coded here).

## Change log

- 2026-05-18 — file created; harness host + Claude Code CLI CONFIRMED;
  agent models, IRR coder models set PIN-AT-START.
- 2026-05-18 — Claude Code re-verified 2.1.119 → 2.1.143 (flags unchanged).
  Codex CLI 0.130.0 and Gemini CLI 0.41.2 OBSERVED (flags not yet
  verified). Cursor `cursor-agent` not installed → A4 blocked/likely
  dropped from v1.
- 2026-05-18 (later) — C01 smoke trial run; Claude Code parser bug
  (PowerShell≠Bash) found & FIXED, fixture frozen + 5 regression tests.
  Codex confirmed 0.130.0 (latest); Gemini updated 0.41.2 → 0.42.0.
  Historical roster at this point: Claude Code + Codex + Gemini (later
  superseded before pre-registration). Cursor DROPPED. Antigravity desktop IDE
  re-investigated conclusively (VS Code 1.107 Electron fork, GUI-bound
  `chat`, no structured/headless output, no headless-env support) →
  excluded from the automated matrix; external-validity limitation.
  RESOLVED: v1 = CLI-only, no GUI-IDE arm; documented as limitation +
  observability meta-finding; dedicated GUI-IDE study parked
  (RESEARCH_AGENDA Thread 10).
- **2026-05-23 — pre-registration finalization pass (see DECISIONS.md
  2026-05-23, D1-D5 + V1 strategy β):**
  - CLI versions ticked: Claude Code 2.1.143→**2.1.150**; Codex
    0.130.0→**0.133.0**; Gemini CLI 0.42.0→**0.43.0** (Gemini will be
    deprecated within ~30 days, not used in V1).
  - **Historical A3 cell switched from Gemini CLI to Antigravity CLI (`agy` 1.0.2)**
    after Google's announced Gemini CLI sunset. `agy` installed via
    `irm https://antigravity.google/cli/install.ps1 | iex`; headless
    mode + dangerous-skip-permissions confirmed; model pin / structured
    output / session persistence UNVERIFIED — V2 adapter-build
    prerequisites.
  - **Windows shell pinned to PowerShell 5.1** (D2): the default Windows
    shell, present on this machine as `5.1.26100.8457`. pwsh 7.5.5 also
    installed but NOT used in V1. PowerShellEnvironment will invoke
    `powershell.exe`, not `pwsh.exe`.
  - **Model tiers pinned (D3):** Claude V1-ready (`opus-4-7` + `sonnet-4-6`,
    CONFIRMED); Codex V2 PIN-AT-START (`gpt-5.5` + `gpt-5.4-mini`,
    pinned but adapter pending); Antigravity V2 PIN-AT-START (models
    TBD pending adapter investigation).
  - **IRR coders pinned** to `claude-opus-4-7` (lineage A) and `gpt-5.5`
    (lineage B); disclosed lineage-coverage gap for the Google-lineage
    then-planned A3 cell.
  - **Historical config count revised 10 → 6** propagated to HYPOTHESIS.md, SAP.md,
    benchmark/RESEARCH_PLAN.md (superseded 2026-05-25 by the 2-config
    Claude Code primary matrix); `scripts/power_analysis.py` left
    UNCHANGED as audit-frozen artifact with a header note explaining
    the count revision (qualitative power conclusion unchanged).
  - **Cursor row dropped** from this table (was a DROP placeholder;
    redundant clutter).
- **2026-05-24 — Claude Code flag re-verification at 2.1.150 (V1 pre-tag gate):**
  all six pinned flags re-checked against `claude --help` on the
  data-collection machine (Claude Code 2.1.150 on Windows 11 Home,
  PowerShell 5.1.26100.8457). Verified unchanged: `-p / --print`,
  `--output-format <format>` (with `stream-json` still in the choice
  list), `--verbose`, `--dangerously-skip-permissions`, `--model <model>`,
  `--no-session-persistence`. No `DEVIATIONS.md` entry needed — flags are
  byte-identical to the pin used by `harness/adapters/claude_code.py`.
  Parser fixture (`tests/fixtures/claude_code_streamjson_C01.jsonl`) was
  captured on 2.1.143 and remains valid: the schema is unchanged across
  the 7 patch bumps in 2.1.x, and the existing `tests/test_claude_code_parser.py`
  suite (12 tests, including PII-clean assertion + `is_error` pairing +
  `tool_name` tagging) passes against it.
- **2026-05-25 — feasibility-preserving pre-registration revision:**
  - Primary V1 confirmatory matrix narrowed to Claude Code × two model
    tiers (`claude-opus-4-7`, `claude-sonnet-4-6`) because this is the only
    agent surface already qualified for H1-H4 measurement.
  - Codex CLI and Antigravity CLI moved to SAP S5 extension-candidate
    status; they are excluded from primary H1-H4 pooled inference unless a
    future pre-registered version promotes them after measurement
    qualification.
  - Antigravity smoke tests recorded: `--add-dir` is required for workspace
    file action; `Claude Sonnet 4.6 (Thinking)` is the exact settings label
    that propagates Sonnet; `--print` stdout and structured transcript
    extraction remain unqualified.
  - **Extension-candidate model pins are no longer V1 tag-gating.** Their
    PIN-AT-START requirements gate the future SAP S5 extension-promotion
    tag, not `pre-registration-v1`. The V1 pre-tag hard gate is
    SATISFIED as of this entry (see header for the per-row status).
  - **`benchmark/docs/DECISIONS.md`** created as the extraction-safe
    subset of the project-root `docs/DECISIONS.md` so the citations from
    inside `benchmark/` resolve both at project root and after
    extraction.
- **2026-05-25 (later) — pre-reg scope correction (see DECISIONS.md
  2026-05-25 (later)):** the earlier same-day narrowing entry above is
  SUPERSEDED. Pre-reg locks methodology, not implementation; PIN-AT-START
  is a valid pre-reg state for cells whose adapters land post-tag.
  - V1 confirmatory matrix RESTORED to the full methodological scope and
    EXTENDED to a same-model harness-control: **7 model-harness configs
    × 5 environments × 14 tasks**. Configs are 3 vendors × 2 tiers
    (Claude Code × {Opus 4.7, Sonnet 4.6}; Codex × {gpt-5.5, gpt-5.4-mini};
    agy × {Gemini 3.1 Pro (High), Gemini 3.5 Flash (Medium)}) plus 1
    cross-vendor control (agy × Claude Sonnet 4.6 (Thinking)).
    Environments add pwsh 7.5.5 as parallel Windows cell E2, in addition
    to the original PS 5.1 / WSL2 / Linux / macOS.
  - **Codex (configs #3, #4)** promoted from extension-candidate to V1
    primary: 2026-05-25 smoke via `codex exec -m gpt-5.4-mini
    --dangerously-bypass-approvals-and-sandbox --ephemeral --json -C
    <sandbox> "..."` returned exit 0 with parseable JSONL events
    (`item.completed.command` / `exit_code` / `aggregated_output` as
    structured fields, cleaner than Claude Code's tool_use_id pairing).
    Adapter ~6h post-tag work.
  - **agy (configs #5, #6, #7)** promoted from extension-candidate to V1
    primary: 2026-05-25 smoke confirmed structured `PLANNER_RESPONSE.tool_calls[]`
    in `~/.gemini/antigravity-cli/brain/<id>/.system_generated/logs/transcript_full.jsonl`
    (with `CommandLine`, `Cwd`, args), and model pinning via
    `~/.gemini/antigravity-cli/settings.json` write of the `model` field.
    SAP "Outcome construction" extended with agy-specific rules
    (prompt-injected Cwd directive + per-command Cwd tagging + scratch
    canary + transcript-based rubric coding). Adapter ~12-20h post-tag work.
  - **pwsh 7.5.5 (env E2)** added as a parallel Windows environment to
    answer the "does upgrading the shell close the gap?" mechanism check
    natively rather than parking it in RESEARCH_AGENDA. Trap tasks
    annotated per-shell (some trap on both, some only on PS 5.1 — the
    no-trap result on pwsh 7 is itself an informative finding). Env
    adapter ~2h post-tag work (subclass of `PowerShellEnvironment`).
  - **IRR coders unchanged:** `claude-opus-4-7` (lineage A) and
    `gpt-5.5` (lineage B). The same-vendor-bias check is now reported for
    5 of 7 configs; the 2 Gemini-bearing configs (#5, #6) get a
    no-same-lineage-coder disclosure (see "Lineage-coverage status"
    above for the rationale).
  - **`scripts/power_analysis.py`** remains UNCHANGED as audit-frozen
    artifact (the historical "10 configs" reference is left as-is per
    the audit-immutability convention; the qualitative power conclusion
    is unaffected by config-count revisions).
- **2026-06-09 — pre-tag evidence pass + CLI pin re-verification (see
  DECISIONS.md 2026-06-09):**
  - CLI pins re-verified on the data-collection machine per this file's
    hard gate: Claude Code 2.1.150→**2.1.159** (`claude --version`; all
    six pinned flags re-confirmed against `claude --help`; the 12 parser
    regression tests pass against the frozen 2.1.143-era fixture; a live
    stream-json re-smoke on 2.1.159 is queued pre-tag); Codex
    **0.133.0** unchanged; agy 1.0.2→**1.0.4** (`agy --version`;
    `-p`/`--print` re-confirmed via `agy --help`; the 2026-05-25
    transcript-schema smoke ran on 1.0.2, re-smoke queued before adapter
    build). Pre-tag pin advances are not deviations, per the 2026-05-30
    Opus 4.8 convention.
  - Shell pins (PS 5.1.26100.8457, pwsh 7.5.5) NOT re-verified in this
    pass — researcher re-verifies at tag time.
  - TOS evidence pass executed: verbatim operative clauses + retrieval
    dates + archive.org snapshot URLs recorded in
    `docs/TOS_COMPLIANCE.md` for all three arms; remaining capture work
    is listed in that file's Evidence Status section.
- **2026-06-10 — agy measurement-qualification re-inspection (read-only,
  on-disk 2026-05-25/27 smoke transcripts; agy 1.0.2-era data read under
  agy 1.0.4):**
  - CONFIRMED for the adapter design: `PLANNER_RESPONSE.tool_calls[]`
    entries carry `name` + `args.CommandLine` + `args.Cwd`; every
    transcript event carries `status` (observed `DONE` / `ERROR`);
    `RUN_COMMAND.content` carries Created/Completed timestamps, an
    outcome sentence ("The command completed successfully."), and an
    `Output:` block; one UUID directory per conversation under `brain/`
    (per-trial isolation via directory diff works); model pin via
    `settings.json` confirmed present with the exact config #5 label.
  - CAVEATS pre-registered for the adapter (to verify in the 1.0.4
    re-smoke, which must include a deliberately failing command):
    (i) long command output is truncated in the transcript (literal
    "<truncated N lines>" marker) — binary task success must come from
    filesystem `binary_success_predicate` checks (already the design),
    and output-dependent diagnostics are bounded by the truncation;
    (ii) no numeric exit code was observed in successful RUN_COMMAND
    content — the failure-case content format is unverified, so the
    A1b command-error signal rests on event `status` + the outcome
    sentence until a failing-command sample is captured;
    (iii) no per-response served-model field exists in the transcript —
    model verification is the `settings.json` pin plus the transcript's
    model-selection-change notices (logged as user-visible text when
    the setting changes);
    (iv) transcripts embed real local filesystem paths and
    git-identity output — agy transcripts require their own redaction
    pass before any publication (the existing redaction-review policy
    applies; this notes the agy-specific surface).
  - **Antigravity SDK ruled out for V1** per researcher decision
    2026-06-10 (API-key-only documented auth; no API budget) — see
    DECISIONS.md 2026-06-10 and the TOS_COMPLIANCE invocation-surface
    note. Subscription `agy --print` is the sole planned Google-arm
    surface for V1.
  - agy 1.0.4 `--help` additionally documents `--sandbox` ("Run in a
    sandbox with terminal restrictions enabled"), `--add-dir`,
    `--conversation <id>` resume, and `--print-timeout` — candidate
    defense-in-depth options for the adapter, to be evaluated at
    adapter-build time (not added to pre-registered compliance
    measures).
