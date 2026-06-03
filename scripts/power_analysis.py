"""A-priori power analysis for agent-shell-context-bench (formerly
"PowerShell-tax benchmark"; renamed 2026-05-25 per the H1-split rationale
and the empirical Bash-on-Windows finding from the parser fixture
re-capture — the colloquial name was overspecifying the conclusion).

==============================================================================
NOTE — AUDIT-FROZEN ARTIFACT, DO NOT INTERPRET AS THE CURRENT PLAN:
==============================================================================
This script and its output tables are preserved UNCHANGED from the
original 2026-05-23 a-priori power analysis as a historical-record
artifact. The numbers below describe a SUPERSEDED design:

    Superseded design (this script's tables):
      - fixed N = 6 trials/cell
      - 19 tasks
      - 10 model-harness configs
      - Bonferroni across configs (α/config = 0.005)
      - estimand: Windows PowerShell vs Linux failure-rate ratio ≥ 1.5x

    CURRENT design (see docs/SAP.md, authoritative):
      - pilot-derived N per cell (capability-only sizing per H1a primary)
      - 14 tasks (5 capability + 9 seeded-error, with seeded-error phrasings averaged
        within task; n_cells in confirmatory matrix = 7 configs × 5 envs
        × 23 task-prompt variants = 805)
      - 7 model-harness configs (3 vendors × 2 tiers + 1 harness control)
      - Pooled-primary test at α=0.05, per-config secondary under
        Benjamini-Hochberg FDR at q=0.05
      - D1 hybrid framing: "Windows context vs Linux context" (free tool
        choice), H1 split into H1a (cap-only inferential) + H1b
        (full-suite descriptive)
      - See docs/SAP.md "Pre-registration power decision (RESOLVED
        2026-05-17 — option a + d)" and docs/DECISIONS.md 2026-05-25
        (latest) for the rationale chain that moved from this script's
        plan to the current SAP.

The qualitative conclusion that drove the methodology revision — the
original fixed-N design was underpowered for small absolute gaps, hence
pooled-primary + FDR + blinded two-stage adaptive design — is unchanged
by the matrix revisions; the original tables remain valid evidence for
why that revision happened. They are NOT current power numbers. A reader
who wants current power should fit the cluster-robust / mixed model on
the actual confirmatory data, as specified in the SAP.
==============================================================================

Question this answers: with the pre-registered design (6 trials/cell, 19
tasks, 10 model-harness configs, comparing Windows PowerShell vs Linux
failure rates), what size of effect can we actually detect — and is the
plan adequately powered for H1's "ratio >= 1.5x"?

Run:  python scripts/power_analysis.py
Deterministic (fixed RNG seed) so the printed numbers are reproducible and
can be pasted into docs/SAP.md and the paper verbatim.

Three estimates are reported on purpose:

  (1) per-task single cell, n=6 vs 6   -- the rawest unit; expected to be
      badly underpowered, which is *why* the SAP aggregates.
  (2) aggregated, trial-as-unit, n=114 -- optimistic: treats all 19x6
      trials in a config as i.i.d. Ignores task-to-task base-rate
      heterogeneity, so it OVERSTATES power.
  (3) aggregated, task-as-unit, n=19   -- conservative: treats each task's
      mean as one observation. UNDERSTATES power (throws away within-task
      trials). Truth is between (2) and (3); the paper will use a
      cluster-robust / mixed model and report it honestly.

Also: a Monte-Carlo Fisher's-exact power for n=6 cells, because the normal
approximation is unreliable at n=6 and would flatter us.
"""

from __future__ import annotations

import numpy as np
from scipy.stats import fisher_exact
from statsmodels.stats.power import NormalIndPower
from statsmodels.stats.proportion import proportion_effectsize

RNG = np.random.default_rng(20260515)
_POWER = NormalIndPower()

# Plausible Linux-bash failure base rates to scan. We do not know the true
# value pre-data; H1 is evaluated across whatever it turns out to be.
LINUX_BASE_RATES = [0.05, 0.10, 0.20, 0.30, 0.40]
H1_RATIO = 1.5  # PowerShell failure rate hypothesised >= 1.5x Linux's


def _power_z(p1: float, p2: float, n: float, alpha: float) -> float:
    """Two-sided two-proportion z-test power via Cohen's h effect size."""
    if p1 == p2:
        return alpha  # no effect: rejection rate == nominal alpha
    h = abs(proportion_effectsize(p1, p2))
    return float(
        _POWER.solve_power(
            effect_size=h, nobs1=n, alpha=alpha, ratio=1.0,
            alternative="two-sided",
        )
    )


def _mde_z(n: float, alpha: float, base: float, power: float = 0.80) -> float:
    """Smallest detectable PowerShell rate (>base) at target power."""
    hi = 1.0 - 1e-6
    lo = base + 1e-6
    if _power_z(base, hi, n, alpha) < power:
        return float("nan")  # not even a near-total effect is detectable
    for _ in range(60):
        mid = (lo + hi) / 2
        if _power_z(base, mid, n, alpha) < power:
            lo = mid
        else:
            hi = mid
    return hi


def _fisher_power_mc(
    p1: float, p2: float, n: int, alpha: float, iters: int = 20000
) -> float:
    """Monte-Carlo power of a two-sided Fisher's exact test at small n."""
    a = RNG.binomial(n, p1, iters)
    b = RNG.binomial(n, p2, iters)
    reject = 0
    for x, y in zip(a, b):
        table = [[x, n - x], [y, n - y]]
        if fisher_exact(table, alternative="two-sided")[1] < alpha:
            reject += 1
    return reject / iters


def _fmt(p: float) -> str:
    return "  n/a " if np.isnan(p) else f"{p:5.2f}"


def main() -> None:
    print("=" * 74)
    print("==========================================================================")
    print("AUDIT-FROZEN HISTORICAL ARTIFACT — NOT THE CURRENT POWER PLAN")
    print("See docs/SAP.md 'Pre-registration power decision (RESOLVED 2026-05-17)'")
    print("and the module docstring for the current design (7 configs, 14 tasks,")
    print("pilot-derived N, pooled-primary + FDR, H1a/H1b split).")
    print("==========================================================================")
    print()
    print("A-PRIORI POWER ANALYSIS — agent-shell-context-bench (historical: 'PowerShell-tax')")
    print("Historical design: 6 trials/cell, 19 tasks, 10 configs. H1 (historical): PS >= 1.5x Linux.")
    print("Bonferroni across 10 configs -> per-config alpha = 0.005;")
    print("aggregate-across-configs test reported at alpha = 0.05.")
    print("=" * 74)

    for alpha, label in [(0.05, "alpha=0.05 (aggregate)"),
                         (0.005, "alpha=0.005 (per-config, Bonferroni)")]:
        print(f"\n### Power to detect a 1.5x failure-rate ratio  [{label}]")
        print(
            f"{'LinuxRate':>9} {'PS@1.5x':>8} "
            f"{'cell n=6':>9} {'agg n=114':>10} {'agg n=19':>9}"
        )
        for p_l in LINUX_BASE_RATES:
            p_p = min(p_l * H1_RATIO, 0.999)
            print(
                f"{p_l:9.2f} {p_p:8.2f} "
                f"{_fmt(_power_z(p_l, p_p, 6, alpha)):>9} "
                f"{_fmt(_power_z(p_l, p_p, 114, alpha)):>10} "
                f"{_fmt(_power_z(p_l, p_p, 19, alpha)):>9}"
            )

    print("\n### Minimum detectable PowerShell rate at 80% power")
    print("(how far above the Linux rate the PS rate must be to be caught)")
    print(f"{'LinuxRate':>9} {'cell n=6':>9} {'agg n=114':>10} {'agg n=19':>9}")
    for p_l in LINUX_BASE_RATES:
        m6 = _mde_z(6, 0.005, p_l)
        m114 = _mde_z(114, 0.005, p_l)
        m19 = _mde_z(19, 0.005, p_l)
        print(
            f"{p_l:9.2f} "
            f"{('n/a' if np.isnan(m6) else f'{m6:.2f}'):>9} "
            f"{('n/a' if np.isnan(m114) else f'{m114:.2f}'):>10} "
            f"{('n/a' if np.isnan(m19) else f'{m19:.2f}'):>9}"
        )

    print("\n### Small-sample reality check (single cell, n=6)")
    print("Normal-approx vs Monte-Carlo Fisher's exact, alpha=0.05:")
    for p_l, p_p in [(0.10, 0.40), (0.20, 0.50), (0.10, 0.60), (0.05, 0.50)]:
        z = _power_z(p_l, p_p, 6, 0.05)
        f = _fisher_power_mc(p_l, p_p, 6, 0.05)
        print(
            f"  Linux={p_l:.2f} PS={p_p:.2f} -> "
            f"z-approx {z:4.2f} | Fisher exact {f:4.2f}"
        )

    print("\n" + "=" * 74)
    print("READING THIS:")
    print("- A single n=6 cell can only detect near-total effects. Per-task")
    print("  results are DESCRIPTIVE; inference is on the aggregate (per SAP).")
    print("- Truth sits between agg-n=114 (optimistic) and agg-n=19")
    print("  (conservative). If the conservative column is weak at the")
    print("  Linux base rate the pilot reveals, EXPAND trials before the")
    print("  full run (SAP already permits this, logged in DEVIATIONS.md).")
    print("- Fisher < z-approx confirms the normal approx flatters at n=6;")
    print("  small-n cell tests will use Fisher's exact, not z.")
    print("=" * 74)


if __name__ == "__main__":
    main()
