# Adapter contract — environment & agent authors' guide

This is the guide for adding an `EnvironmentAdapter` (a new execution
context) or an `AgentAdapter` (a new agent CLI) to the harness. It exists so
that several adapters can be built in parallel without diverging into
near-duplicate, subtly-incompatible implementations. The benchmark depends on
every cell measuring the *same* thing, so that "Windows vs Linux" is the only
variable; divergent adapters would quietly break that.

The authoritative contracts are the base-class docstrings
(`harness/environments/base.py`, `harness/adapters/base.py`); this guide ties
them together, states the cross-adapter **equivalence invariants**, and gives
the rules for building adapters in parallel.

---

## Prime directive

**Implement the existing contract. Do not change it.**

An adapter is a *subclass* plus a *test*. That is the entire surface you add.
The base classes, `harness/types.py`, `harness/checks.py`,
`harness/classifier/rubric.py`, and the canary system are the
**pre-registered measurement apparatus** (see the locked-surface list in
`DEVIATIONS.md`). Adding an adapter is implementation and is free.
*Modifying* any of those shared files is a methodology change.

> If your adapter seems to *require* a change to a base class, `types.py`,
> `checks.py`, or the rubric — **stop and surface it to the researcher.**
> Do not "make it work" by editing the shared contract. Usually the adapter
> can satisfy the contract as written; if it genuinely can't, that is a
> pre-registration decision (clarification vs. `DEVIATIONS.md` deviation),
> not an implementation call — a silent contract edit changes every number
> downstream of it.

---

## What an environment owns

Subclass `EnvironmentAdapter`. Set the two class vars and implement six
methods (full semantics in the base docstrings):

| Member | Obligation |
|---|---|
| `env_id` / `description` | `env_id` **must** equal the pre-registered matrix id (`docs/VERSIONS.md`). |
| `__init__` | Call `super().__init__()` (initialises canary state). |
| `probe()` | Fingerprint the context for the log header: OS, shell+version, locale, tool versions. Must include `env_id`. Runs once per cell. |
| `setup_sandbox()` | Fresh isolated dir; materialise `initial_files`; **raise** if a `required_tools` entry is missing. New sandbox every trial. |
| `teardown_sandbox()` | Destroy it. Safe to call after a failed setup, and twice. |
| `exec()` | Run an arbitrary executable (the agent CLI). The single process seam. Timeout ⇒ `ProcessResult(timed_out=True)`, never raise. |
| `run_shell()` | Run a snippet in the context's native shell (used by `probe`). |
| `snapshot()` | Fingerprint the sandbox; **populate `escaped_paths` from `check_canaries()`** (see the reference `snapshot` in `powershell.py`). |

Free from the base class, override only with cause:
`diff()` (override only for a remote server-side diff), the canary lifecycle
(`canary_paths()` is the usual override; override `_write_canary` only for
non-local write semantics like WSL path translation), and `trial_sandbox()`
(do not override).

## What an agent owns

Subclass `AgentAdapter`. Set `agent_id`, implement four methods:

| Member | Obligation |
|---|---|
| `agent_id` | Must equal the pre-registered matrix id. |
| `_default_cli_path()` | Executable name resolved on PATH. |
| `build_invocation()` | argv that runs the agent **once**, headless, autonomous (no approval gate, so a spiral can unfold). Flags are reproducibility-critical — pin and record them in the module docstring + `docs/VERSIONS.md`. |
| `parse_transcript()` | `(transcript, [CommandRecord])`. **Must never raise** — degrade to a best-effort partial on garbled/truncated output. A crashed run with three good events is still three events of data. |
| `cli_version()` | Version string of the CLI as installed in the given environment. |

`run()` is a template method. **Never override it.** It wires the adapter to
the environment, times the call, captures harness errors, and packages the
result. Overriding it re-introduces per-adapter divergence in the exact path
that must be identical across cells.

---

## Equivalence invariants

These are what keep every cell measuring the same thing. The conformance
battery (`tests/conformance.py`) enforces each; the parenthetical is *why*.

1. **Snapshot keys are sandbox-relative POSIX paths** — `build/output.txt`,
   never `build\output.txt`, never absolute, never leading `/`. (`checks.py`
   is frozen and looks up these exact keys; a different key shape silently
   misfires every check. The local helper does this via `Path.as_posix()`;
   a remote env must produce the identical shape itself.)

2. **`host_root` is a locally-readable directory holding the sandbox files
   at their relative paths, at check time.** (`checks.py` content checks read
   `Path(host_root) / rel`. A remote context with no shared mount must sync
   or mount the sandbox back to a local `host_root` before `snapshot()` /
   checks run, or every content check fails closed. `SandboxHandle.root` is
   the path the *agent* sees, env-native; `host_root` is the path the
   *harness* inspects. For a local env they are equal; for WSL/GCP they
   differ — and only `host_root` must be locally readable.)

3. **`snapshot()` populates `escaped_paths` from `check_canaries()`.**
   (Sandbox-escape detection — rubric code E — is wired in at snapshot time
   per env. An env that forgets this is blind to catastrophic actions, the
   highest-stakes thing H2 measures.)

4. **The agent CLI runs only through `environment.exec`; adapters never
   shell out.** (So the execution context is the only cross-cell variable.
   No `subprocess`, `os.system`, or `os.popen` inside an adapter.)

5. **Timeouts are data, not errors:** `ProcessResult(timed_out=True)`, never
   a raised exception. (A hung agent is rubric F — a signal, not a harness
   failure.)

6. **Missing `required_tools` raises** in `setup_sandbox`. (A tool silently
   absent would degrade the run and confound the cell. Refuse it loudly.)

7. **The command list preserves order and tags `tool_name`.** (The ordered
   commands *are* the spiral H2 is scored on; dropping or reordering them
   undercounts escalation. `tool_name` feeds the SAP A1b per-tool analysis.)

8. **`types.py` field names are the on-disk log schema — additive only.**
   (A second researcher re-derives every number from the raw log. Renaming
   or removing a field after data collection is a `DEVIATIONS.md` event, not
   a refactor.)

---

## The conformance battery

`tests/conformance.py` exposes two importable assertion batteries:

```python
from tests.conformance import (
    assert_environment_conforms,
    assert_agent_adapter_conforms,
)
```

Every adapter ships a `tests/test_<id>_conformance.py` that calls the
relevant battery against a real instance. The agent battery is
infrastructure-free (synthetic transcripts) and runs in CI immediately. The
environment battery has a structural mode (default, no infra) and a
`live=True` mode that exercises sandbox/snapshot/exec against the real
context — gate `live=True` on infra availability (e.g. skip when the GCP
credentials or the WSL distro are absent) so CI stays green on machines
that can't reach that context, exactly as the Windows reference env is only
fully exercised on a Windows host.

Passing the battery is the **merge gate**, together with one capability-task
smoke trial in a sandbox (never a `tasks/trap/*` task — see below).

---

## Building adapters in parallel — the rules

The reference implementations are `environments/powershell.py` and
`adapters/claude_code.py`. **Match them.** Reuse the base-class helpers and
`harness/fs.py`; do not reinvent snapshotting, diffing, or process spawning.

- **One adapter = one subclass + one conformance test + a registry entry.**
  Nothing else. If you find yourself adding a helper module or a new
  abstraction, stop — it almost certainly belongs in the base class (which
  you may not edit) or doesn't earn its place.
- **Never run the harness against `tasks/trap/*` with this repo as the
  working directory.** Those tasks are designed to trigger agent spirals;
  pointing them at this checkout is the self-harm failure mode `CLAUDE.md`
  warns about. Verify adapters with capability tasks or synthetic
  preconditions, in a sandbox.
- **Register in `harness/registry.py`** by moving the id from the
  `_PLANNED_*` set into the `_ENVIRONMENTS` / `_AGENTS` map. Keep the planned
  sets in sync with `docs/VERSIONS.md`.
- **Pin and record CLI flags / shell versions** in the module docstring and
  `docs/VERSIONS.md` — a wrong `--output-format` silently corrupts H2.

When a fact would land in both an adapter and the shared contract, the
shared contract wins and you leave the adapter thin.
