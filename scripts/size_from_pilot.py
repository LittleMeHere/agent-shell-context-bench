"""size_from_pilot.py — turn blinded pilot data into the confirmatory N/cell.

Implements the pre-registered closed-form sizing rule in
`benchmark/docs/SAP.md` ("Pilot-sizing formula"). The author runs this
script ONCE after the blinded pilot completes and BEFORE unblinding;
its output (the integer `n_per_cell`) is locked in for the confirmatory
run.

The script is intentionally:
  * stdlib-only on the hot path (math + json + argparse) so the pre-reg
    formula in SAP.md is reproducible without scipy/statsmodels. A
    `--verify-against-statsmodels` flag is available for cross-checking
    the closed form against statsmodels' NormalIndPower.
  * deterministic and parameter-free at run time — alpha, beta, the
    1.5x ratio floor, and the n=6 floor are hardcoded constants
    matching SAP.md. The only inputs are pilot data + a budget cap.
  * blinding-preserving — it does NOT print per-group, per-environment,
    per-configuration, or per-task failure rates, even with --verbose.
    Its outputs are p_hat_pool, ICC components, the design effect, and
    the final N. Anything finer would defeat the blinding the SAP
    promises.

**Task-class filtering (added 2026-05-25 (latest), review-driven pass #2):**
The H1 primary inferential test was split into H1a (capability tasks only)
and H1b (full-suite descriptive). Sizing for the H1a primary therefore
operates on the capability-task subset of pilot trials. The
`--task-class {capability,seeded-error,all}` flag controls which subset
feeds the sizing computation; default is `capability` (matches H1a
primary). The filter relies on the task_id prefix convention: `C*` for
capability tasks (C01–C05), `T*` for seeded-error tasks (T01–T09; the
"T" prefix and the `tasks/trap/` folder path are retained as legacy
internal identifiers per 2026-05-30 DECISIONS — the concept renamed
from "trap" to "seeded-error" but the identifiers did not). The output
JSON records the chosen task_class so the sizing record is
self-describing.

Usage modes:

  1. Pilot mode — read blinded trial outcomes from JSON (H1a primary
     sizing uses capability tasks only, which is the default):

       python scripts/size_from_pilot.py \\
           --pilot-json data/pre-registration/pilot_blinded.json \\
           --compute-budget 50.00 --per-trial-cost 0.06 --n-cells 805 \\
           --output data/pre-registration/pilot_sizing_lock.json

     For the historical pre-split full-suite sizing (e.g. sensitivity check
     against the prior plan, or sizing for an H1b-style descriptive
     analysis), use `--task-class all`:

       python scripts/size_from_pilot.py \\
           --pilot-json data/pre-registration/pilot_blinded.json \\
           --task-class all \\
           --compute-budget 50.00 --per-trial-cost 0.06 --n-cells 805

  2. Calculator mode — direct inputs for sensitivity checks BEFORE the
     pilot exists (useful for reviewers). The task_class filter does not
     apply in calculator mode because inputs are already aggregated:

       python scripts/size_from_pilot.py \\
           --p-hat-pool 0.30 --icc 0.05 --n-bar 4 \\
           --compute-budget 50.00 --per-trial-cost 0.06 --n-cells 805

     (`--n-cells 805` matches the locked V1 confirmatory matrix per
     `benchmark/docs/SAP.md` "Pilot-sizing formula": 7 configs × 5
     environments × 23 task-prompt variants. The historical example
     `--n-cells 336` (6 configs × 4 envs × 14 tasks, pre-phrasing-split,
     pre-pwsh-7) is superseded.)

  3. Self-test — verifies the formula and the task-class filter:

       python scripts/size_from_pilot.py --self-test

Pilot-input JSON schema:

    [
      {"blinded_group": "E01",          # sealed env label, NOT name
       "task_id":       "T01",          # public, clusters base rate;
                                        # prefix "C" = capability,
                                        # "T" = seeded-error (legacy)
       "config_id":     "CFG01",        # public, clusters base rate
       "valid":         true,
       "failed":        false},         # only meaningful when valid=true
      ...
    ]

Output JSON keys (printed to stdout or --output):
    n_per_cell                  the locked integer (CONFIRMATORY-N)
    n_raw                       formula output before floor/cap clamps
    n_floor_applied             true if raw < 6 and floor bound
    budget_cap_bound            true if budget < n_floored
    task_class                  filter applied: "capability" (default,
                                H1a primary), "seeded-error", or "all"
    n_trials_after_filter       count of valid trials feeding the formula
    p_hat_pool                  pooled failure proportion (filtered valid trials)
    icc_task / icc_config       one-way ICCs by clustering source
    icc_combined                sum of the two (crossed-RE additivity), <=1
    design_effect_D             1 + (n_bar - 1) * icc_combined
    n_bar_pilot                 mean filtered valid trials per (task, config) cell
    achieved_power_at_locked_n  power at the clamped N (honesty check)
    constants                   the locked alpha/beta/ratio_floor/etc.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections import defaultdict
from collections.abc import Sequence
from pathlib import Path
from typing import Any

# --------------------------------------------------------------------------
# Pre-registered constants (locked in SAP.md "Pilot-sizing formula")
# --------------------------------------------------------------------------

ALPHA = 0.05                # two-sided primary test
BETA = 0.20                 # 80% power
RATIO_FLOOR = 1.5           # H1a's ≥1.5x ratio is the effect-size floor
N_FLOOR_PER_CELL = 6        # never size below 6/cell, even on tiny p_pool

# Task-class filter values. H1a primary uses capability-only (default).
# See module docstring and SAP.md "Pilot-sizing formula".
TASK_CLASS_CAPABILITY = "capability"
TASK_CLASS_TRAP = "seeded-error"  # value renamed 2026-05-30 per DECISIONS (TRAP acronym collision); Python identifier kept for code stability
TASK_CLASS_ALL = "all"
TASK_CLASS_CHOICES = (TASK_CLASS_CAPABILITY, TASK_CLASS_TRAP, TASK_CLASS_ALL)
DEFAULT_TASK_CLASS = TASK_CLASS_CAPABILITY  # H1a primary

# Verified against scipy.stats.norm.ppf(0.975) and (0.80) at 16 digits.
# Hardcoded here so the script has no scipy dependency on the hot path.
Z_975 = 1.9599639845400545
Z_80 = 0.8416212335729143
TWO_Z_SUM_SQ = 2.0 * (Z_975 + Z_80) ** 2  # ≈ 15.6978


# --------------------------------------------------------------------------
# Building blocks
# --------------------------------------------------------------------------


def filter_by_task_class(
    trials: Sequence[dict], task_class: str
) -> list[dict]:
    """Filter trials by task_class using the C*/T* task_id prefix convention.

    Capability tasks have task_id starting with "C" (C01–C05);
    seeded-error tasks have task_id starting with "T" (T01–T09; the "T"
    prefix is legacy per the 2026-05-30 rename — see module docstring). The "all" task_class is a
    pass-through. Trials missing a task_id, or with an unrecognized prefix,
    are excluded with a clear error rather than silently miscounted — a
    silent miscount here would bias the sizing input.

    Added 2026-05-25 (latest) per review-driven pass #2 (the H1 split).
    H1a primary sizing uses task_class="capability"; the historical
    pre-split full-suite sizing is preserved as task_class="all".
    """
    if task_class not in TASK_CLASS_CHOICES:
        raise ValueError(
            f"task_class {task_class!r} not in {TASK_CLASS_CHOICES}"
        )
    if task_class == TASK_CLASS_ALL:
        return list(trials)
    prefix = "C" if task_class == TASK_CLASS_CAPABILITY else "T"
    filtered: list[dict] = []
    unknown: set[str] = set()
    for t in trials:
        tid = t.get("task_id")
        if not isinstance(tid, str) or not tid:
            raise ValueError(
                "trial missing or empty task_id; cannot apply task_class filter"
            )
        head = tid[:1].upper()
        if head == prefix:
            filtered.append(t)
        elif head not in ("C", "T"):
            unknown.add(tid)
    if unknown:
        raise ValueError(
            f"task_ids with unrecognized prefix (expected C* or T*): "
            f"{sorted(unknown)}"
        )
    return filtered


def compute_p_pool(trials: Sequence[dict]) -> float:
    """Pooled failure proportion across VALID pilot trials.

    SAP.md "p̂_pool — trial-level failure proportion pooled across all four
    blinded environment groups (no per-group rate is read out)."
    """
    valid = [t for t in trials if t.get("valid")]
    if not valid:
        raise ValueError("pilot contains zero valid trials; cannot size")
    return sum(1 for t in valid if t.get("failed")) / len(valid)


def compute_one_way_icc(trials: Sequence[dict], cluster_key: str) -> float:
    """ANOVA-method one-way ICC on the binary failure outcome, clustering
    on `cluster_key` ("task_id" or "config_id"). Clamped at 0; negative
    estimates are sampling noise around a true ICC of 0.

    Standard formula (Shrout & Fleiss 1979 ICC(1,1)):
        ICC = (MSB - MSW) / (MSB + (n_bar - 1) * MSW)
    """
    valid = [t for t in trials if t.get("valid")]
    groups: dict[Any, list[float]] = defaultdict(list)
    for t in valid:
        groups[t[cluster_key]].append(1.0 if t.get("failed") else 0.0)
    k = len(groups)
    if k < 2:
        return 0.0
    n_total = sum(len(v) for v in groups.values())
    grand_mean = sum(sum(v) for v in groups.values()) / n_total
    n_bar = n_total / k
    cluster_means = {key: sum(v) / len(v) for key, v in groups.items()}
    ss_between = sum(
        len(groups[key]) * (m - grand_mean) ** 2
        for key, m in cluster_means.items()
    )
    ss_within = sum(
        (x - cluster_means[key]) ** 2
        for key, v in groups.items()
        for x in v
    )
    df_between = k - 1
    df_within = n_total - k
    if df_within <= 0:
        return 0.0
    ms_between = ss_between / df_between
    ms_within = ss_within / df_within
    denom = ms_between + (n_bar - 1) * ms_within
    if denom <= 0:
        return 0.0
    return max(0.0, (ms_between - ms_within) / denom)


def compute_n_bar_per_cell(trials: Sequence[dict]) -> float:
    """Mean number of VALID trials per (task_id, config_id) cell in the
    pilot. This is the n̄ in the SAP's design-effect formula
    D = 1 + (n̄ − 1)·ICC."""
    valid = [t for t in trials if t.get("valid")]
    cells: dict[tuple, int] = defaultdict(int)
    for t in valid:
        cells[(t["task_id"], t["config_id"])] += 1
    if not cells:
        return 0.0
    return sum(cells.values()) / len(cells)


def n_per_cell_formula(p_pool: float, design_effect: float) -> int:
    """The pre-registered closed-form sizing rule (SAP.md):

        δ_min   = (RATIO_FLOOR − 1) · p̂_pool   = 0.5 · p̂_pool
        σ²_eff  = D · p̂_pool · (1 − p̂_pool)
        n/cell  = ceil( 2 · σ²_eff · (z_{1-α/2} + z_{1-β})² / δ_min² )

    This is the standard two-proportion sample-size formula with the
    cluster-inflation design effect D layered on top.
    """
    if not (0.0 < p_pool < 1.0):
        raise ValueError(f"p_pool {p_pool!r} out of (0, 1); cannot size")
    if design_effect < 1.0:
        raise ValueError(f"design_effect {design_effect!r} < 1; check ICC computation")
    delta_min = (RATIO_FLOOR - 1.0) * p_pool
    sigma_sq_eff = design_effect * p_pool * (1.0 - p_pool)
    n_raw = TWO_Z_SUM_SQ * sigma_sq_eff / (delta_min ** 2)
    return math.ceil(n_raw)


def _normal_cdf(z: float) -> float:
    """Φ(z) via math.erf. Stdlib-only — no scipy dependency."""
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def achieved_power(
    p_pool: float, design_effect: float, n_per_cell: int
) -> float:
    """Two-proportion power at the locked N — reported honestly in the
    writeup whether the budget cap bound or not. Inverts the sizing
    formula for z_β, then returns Φ(z_β).
    """
    if not (0.0 < p_pool < 1.0):
        return float("nan")
    delta_min = (RATIO_FLOOR - 1.0) * p_pool
    sigma_sq_eff = design_effect * p_pool * (1.0 - p_pool)
    if sigma_sq_eff <= 0.0:
        return 1.0
    z_beta = (
        math.sqrt(n_per_cell * delta_min ** 2 / (2.0 * sigma_sq_eff)) - Z_975
    )
    return _normal_cdf(z_beta)


# --------------------------------------------------------------------------
# Top-level orchestration
# --------------------------------------------------------------------------


def _constants_record() -> dict[str, Any]:
    return {
        "alpha": ALPHA,
        "beta": BETA,
        "ratio_floor": RATIO_FLOOR,
        "n_floor_per_cell": N_FLOOR_PER_CELL,
        "z_975": Z_975,
        "z_80": Z_80,
        "two_z_sum_sq": TWO_Z_SUM_SQ,
    }


def _apply_floor_and_cap(
    n_raw: int, cap_per_cell: int | None
) -> tuple[int, bool, bool]:
    """Return (final, floor_was_binding, cap_was_binding)."""
    floor_binding = n_raw < N_FLOOR_PER_CELL
    n_floored = max(N_FLOOR_PER_CELL, n_raw)
    cap_binding = cap_per_cell is not None and n_floored > cap_per_cell
    n_final = cap_per_cell if cap_binding else n_floored  # type: ignore[assignment]
    return n_final, floor_binding, cap_binding


def size_from_trials(
    trials: Sequence[dict],
    *,
    cap_per_cell: int | None = None,
    task_class: str = DEFAULT_TASK_CLASS,
) -> dict[str, Any]:
    """End-to-end: blinded pilot trials → locked sizing record.

    `task_class` selects which trials feed the sizing computation.
    Default is "capability" (matches H1a primary inferential test, per
    the 2026-05-25 (latest) H1 split). See `filter_by_task_class` and
    SAP.md "Pilot-sizing formula".
    """
    filtered = filter_by_task_class(trials, task_class)
    if not filtered:
        raise ValueError(
            f"no trials remain after task_class={task_class!r} filter; "
            f"cannot size"
        )
    p_pool = compute_p_pool(filtered)
    icc_task = compute_one_way_icc(filtered, "task_id")
    icc_config = compute_one_way_icc(filtered, "config_id")
    # Crossed random effects: variance components add (Searle 1971 §11.7).
    # Capped at 1.0 (an ICC > 1 is an estimation artefact).
    icc_combined = min(1.0, icc_task + icc_config)
    n_bar = compute_n_bar_per_cell(filtered)
    design_effect = 1.0 + max(0.0, n_bar - 1.0) * icc_combined
    n_raw = n_per_cell_formula(p_pool, design_effect)
    n_final, floor_b, cap_b = _apply_floor_and_cap(n_raw, cap_per_cell)
    return {
        "n_per_cell": n_final,
        "n_raw": n_raw,
        "n_floor_applied": floor_b,
        "budget_cap_bound": cap_b,
        "cap_per_cell": cap_per_cell,
        "task_class": task_class,
        "n_trials_after_filter": len(filtered),
        "p_hat_pool": p_pool,
        "icc_task": icc_task,
        "icc_config": icc_config,
        "icc_combined": icc_combined,
        "design_effect_D": design_effect,
        "n_bar_pilot": n_bar,
        "achieved_power_at_locked_n": achieved_power(
            p_pool, design_effect, n_final
        ),
        "mode": "pilot",
        "constants": _constants_record(),
    }


def size_from_aggregate(
    p_pool: float,
    icc: float,
    n_bar: float,
    *,
    cap_per_cell: int | None = None,
) -> dict[str, Any]:
    """Calculator mode for reviewer sensitivity-checking."""
    design_effect = 1.0 + max(0.0, n_bar - 1.0) * icc
    n_raw = n_per_cell_formula(p_pool, design_effect)
    n_final, floor_b, cap_b = _apply_floor_and_cap(n_raw, cap_per_cell)
    return {
        "n_per_cell": n_final,
        "n_raw": n_raw,
        "n_floor_applied": floor_b,
        "budget_cap_bound": cap_b,
        "cap_per_cell": cap_per_cell,
        "p_hat_pool": p_pool,
        "icc_combined": icc,
        "n_bar_pilot": n_bar,
        "design_effect_D": design_effect,
        "achieved_power_at_locked_n": achieved_power(
            p_pool, design_effect, n_final
        ),
        "mode": "calculator",
        "constants": _constants_record(),
    }


# --------------------------------------------------------------------------
# Self-test (locks the formula against three hand-derived cases)
# --------------------------------------------------------------------------


def _self_test() -> int:
    """Verify the closed-form rule against three hand-derived cases.

    Each case is a complete trace of the SAP.md formula:
      delta_min  = 0.5 * p_pool
      sigma_sq   = D * p_pool * (1 - p_pool)
      n_raw      = TWO_Z_SUM_SQ * sigma_sq / delta_min^2
      n_per_cell = ceil(n_raw)
    """
    cases = [
        # (p_pool, D, expected_n)
        # p=0.30, D=1: delta=0.15, sigma=0.21,
        #   n = 15.6978 * 0.21 / 0.0225 ≈ 146.51 → 147
        (0.30, 1.0, 147),
        # p=0.30, D=2: doubles sigma; n ≈ 293.03 → 294
        (0.30, 2.0, 294),
        # p=0.05, D=1: tiny absolute gap, n explodes
        #   delta=0.025, sigma=0.0475,
        #   n = 15.6978 * 0.0475 / 0.000625 ≈ 1193.03 → 1194
        (0.05, 1.0, 1194),
    ]
    failures: list[str] = []
    for p, D, expected in cases:
        got = n_per_cell_formula(p, D)
        marker = "OK " if got == expected else "FAIL"
        print(f"  {marker}  p_pool={p}  D={D}  expected={expected}  got={got}")
        if got != expected:
            failures.append(f"p={p},D={D}: expected {expected} got {got}")
    # Smoke-check ICC and ANOVA path with a tiny synthetic pilot.
    # Synthetic task_ids use the C*/T* prefix convention so the
    # task_class filter path is exercised end-to-end.
    synth = [
        {"blinded_group": "E01", "task_id": "C01", "config_id": "CFGA",
         "valid": True, "failed": True},
        {"blinded_group": "E01", "task_id": "C01", "config_id": "CFGA",
         "valid": True, "failed": False},
        {"blinded_group": "E02", "task_id": "C02", "config_id": "CFGB",
         "valid": True, "failed": True},
        {"blinded_group": "E02", "task_id": "C03", "config_id": "CFGA",
         "valid": True, "failed": False},
        {"blinded_group": "E03", "task_id": "T01", "config_id": "CFGB",
         "valid": True, "failed": False},
        {"blinded_group": "E04", "task_id": "T02", "config_id": "CFGA",
         "valid": True, "failed": True},
    ]
    p_hat = compute_p_pool(synth)
    if not (0.0 < p_hat < 1.0):
        failures.append(f"synth p_hat out of (0,1): {p_hat}")
    n_bar = compute_n_bar_per_cell(synth)
    if n_bar <= 0:
        failures.append(f"synth n_bar non-positive: {n_bar}")
    icc_t = compute_one_way_icc(synth, "task_id")
    icc_c = compute_one_way_icc(synth, "config_id")
    if icc_t < 0 or icc_c < 0:
        failures.append(f"ICC < 0: task={icc_t} config={icc_c}")
    # End-to-end shouldn't crash on the synthetic pilot. Default task_class
    # is capability — exercises the filter path.
    rec = size_from_trials(synth, cap_per_cell=10_000)
    if rec["n_per_cell"] < N_FLOOR_PER_CELL:
        failures.append(f"final N below floor: {rec['n_per_cell']}")
    if rec["task_class"] != TASK_CLASS_CAPABILITY:
        failures.append(f"default task_class wrong: {rec['task_class']!r}")
    if rec["n_trials_after_filter"] != 4:  # 4 C* trials in synth
        failures.append(
            f"capability filter count wrong: expected 4, got "
            f"{rec['n_trials_after_filter']}"
        )
    print(
        f"  OK   synthetic-pilot end-to-end (capability filter, default): "
        f"p={p_hat:.3f}  n_bar={n_bar:.2f}  "
        f"icc_task={icc_t:.3f}  icc_cfg={icc_c:.3f}  "
        f"D={rec['design_effect_D']:.3f}  n/cell={rec['n_per_cell']}  "
        f"n_trials_filt={rec['n_trials_after_filter']}"
    )
    # task_class="seeded-error" path.
    rec_trap = size_from_trials(
        synth, cap_per_cell=10_000, task_class=TASK_CLASS_TRAP
    )
    if rec_trap["n_trials_after_filter"] != 2:  # 2 T* trials in synth
        failures.append(
            f"seeded-error filter count wrong: expected 2, got "
            f"{rec_trap['n_trials_after_filter']}"
        )
    print(
        f"  OK   synthetic-pilot seeded-error filter: "
        f"n_trials_filt={rec_trap['n_trials_after_filter']}  "
        f"p={rec_trap['p_hat_pool']:.3f}  "
        f"n/cell={rec_trap['n_per_cell']}"
    )
    # task_class="all" path (pre-split full-suite sizing).
    rec_all = size_from_trials(
        synth, cap_per_cell=10_000, task_class=TASK_CLASS_ALL
    )
    if rec_all["n_trials_after_filter"] != 6:
        failures.append(
            f"all filter count wrong: expected 6, got "
            f"{rec_all['n_trials_after_filter']}"
        )
    print(
        f"  OK   synthetic-pilot all filter: "
        f"n_trials_filt={rec_all['n_trials_after_filter']}  "
        f"p={rec_all['p_hat_pool']:.3f}  "
        f"n/cell={rec_all['n_per_cell']}"
    )
    # Filter rejects unknown task_id prefix.
    bad = synth + [{"blinded_group": "E01", "task_id": "X99",
                    "config_id": "CFGA", "valid": True, "failed": False}]
    try:
        filter_by_task_class(bad, TASK_CLASS_CAPABILITY)
        failures.append("filter accepted unknown task_id prefix")
    except ValueError:
        print("  OK   unknown task_id prefix rejected")
    # Filter rejects unknown task_class value.
    try:
        filter_by_task_class(synth, "bogus")
        failures.append("filter accepted unknown task_class value")
    except ValueError:
        print("  OK   unknown task_class value rejected")
    # Filter raises when nothing remains.
    only_trap = [t for t in synth if t["task_id"].startswith("T")]
    try:
        size_from_trials(
            only_trap, cap_per_cell=10_000, task_class=TASK_CLASS_CAPABILITY
        )
        # not necessarily a failure — synth has seeded-error trials, sizing on
        # capability filter would yield zero filtered trials and raise.
        failures.append(
            "size_from_trials accepted zero-filtered-trials state silently"
        )
    except ValueError:
        print("  OK   zero-filtered-trials raises in size_from_trials")
    # Floor + cap clamp check.
    floored = _apply_floor_and_cap(2, cap_per_cell=None)
    assert floored == (N_FLOOR_PER_CELL, True, False), f"floor clamp wrong: {floored}"
    capped = _apply_floor_and_cap(1000, cap_per_cell=50)
    assert capped == (50, False, True), f"cap clamp wrong: {capped}"
    print("  OK   floor and cap clamps")
    if failures:
        print(f"\nself-test FAILED ({len(failures)} issue(s)):")
        for f in failures:
            print(f"  - {f}")
        return 1
    print(f"\nself-test PASS (all {len(cases)} formula cases + synthetic pilot)")
    return 0


# --------------------------------------------------------------------------
# Optional statsmodels cross-check (off the hot path)
# --------------------------------------------------------------------------


def _verify_against_statsmodels(p_pool: float, design_effect: float) -> None:
    try:
        from statsmodels.stats.power import NormalIndPower
        from statsmodels.stats.proportion import proportion_effectsize
    except ImportError:
        print("statsmodels not installed; skipping cross-check")
        return
    p1 = p_pool
    p2 = (RATIO_FLOOR - 1.0) * p_pool + p_pool  # = ratio * p
    h = proportion_effectsize(p1, p2)
    n_naive = NormalIndPower().solve_power(
        effect_size=h, alpha=ALPHA, power=1 - BETA, alternative="two-sided"
    )
    n_inflated_for_clustering = n_naive * design_effect
    n_closed_form = n_per_cell_formula(p_pool, design_effect)
    print(
        f"  closed-form n/cell = {n_closed_form}  |  "
        f"statsmodels (naive) = {n_naive:.1f}  |  "
        f"statsmodels * D = {n_inflated_for_clustering:.1f}"
    )


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def _budget_to_cap_per_cell(
    compute_budget: float | None,
    per_trial_cost: float | None,
    n_cells: int | None,
) -> int | None:
    if compute_budget is None or per_trial_cost is None or n_cells is None:
        return None
    if per_trial_cost <= 0 or n_cells <= 0:
        raise SystemExit("--per-trial-cost and --n-cells must be positive")
    return int(math.floor((compute_budget / per_trial_cost) / n_cells))


def main(argv: Sequence[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="size_from_pilot.py",
        description=(
            "Compute the locked confirmatory N/cell from blinded pilot "
            "data using the SAP.md pilot-sizing formula."
        ),
    )
    p.add_argument("--pilot-json", type=Path, help="blinded pilot trials JSON")
    p.add_argument("--task-class",
                   choices=TASK_CLASS_CHOICES,
                   default=DEFAULT_TASK_CLASS,
                   help=(
                       "which task subset feeds the sizing computation; "
                       f"default {DEFAULT_TASK_CLASS!r} matches H1a primary "
                       "(capability-only) per the 2026-05-25 H1 split. "
                       "'all' restores the pre-split full-suite sizing."
                   ))
    p.add_argument("--p-hat-pool", type=float,
                   help="calculator mode: pooled failure rate")
    p.add_argument("--icc", type=float,
                   help="calculator mode: combined ICC across task+config")
    p.add_argument("--n-bar", type=float,
                   help="calculator mode: mean pilot trials per cell")
    p.add_argument("--compute-budget", type=float,
                   help="total compute budget cap (USD or trials)")
    p.add_argument("--per-trial-cost", type=float,
                   help="expected cost per trial (USD or trials per trial = 1)")
    p.add_argument("--n-cells", type=int,
                   help="number of cells in the confirmatory matrix")
    p.add_argument("--output", type=Path, help="write sizing-lock record here")
    p.add_argument("--self-test", action="store_true",
                   help="verify the closed form against hand-derived cases")
    p.add_argument("--verify-against-statsmodels", action="store_true",
                   help="cross-check the closed form vs statsmodels NormalIndPower")
    args = p.parse_args(argv)

    if args.self_test:
        return _self_test()

    cap = _budget_to_cap_per_cell(
        args.compute_budget, args.per_trial_cost, args.n_cells
    )

    if args.pilot_json is not None:
        trials = json.loads(args.pilot_json.read_text(encoding="utf-8"))
        record = size_from_trials(
            trials, cap_per_cell=cap, task_class=args.task_class
        )
    elif (
        args.p_hat_pool is not None
        and args.icc is not None
        and args.n_bar is not None
    ):
        # Calculator mode: task_class filter doesn't apply (inputs are
        # already aggregated). If the user set --task-class explicitly,
        # warn them it's a no-op here so the sizing record isn't
        # misleading about what subset was sized.
        if args.task_class != DEFAULT_TASK_CLASS:
            print(
                f"note: --task-class={args.task_class!r} ignored in "
                f"calculator mode (inputs are pre-aggregated; pass the "
                f"already-filtered rate via --p-hat-pool)",
                file=sys.stderr,
            )
        record = size_from_aggregate(
            args.p_hat_pool, args.icc, args.n_bar, cap_per_cell=cap
        )
    else:
        p.error(
            "provide either --pilot-json PATH "
            "or (--p-hat-pool X --icc Y --n-bar Z)"
        )
        return 2  # unreachable; argparse exits

    if args.verify_against_statsmodels:
        _verify_against_statsmodels(
            record["p_hat_pool"], record["design_effect_D"]
        )

    serialised = json.dumps(record, indent=2)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(serialised + "\n", encoding="utf-8")
        print(f"sizing record written to {args.output}")
        print(f"  n_per_cell = {record['n_per_cell']}")
    else:
        print(serialised)
    return 0


if __name__ == "__main__":
    sys.exit(main())
