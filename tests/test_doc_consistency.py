"""Cross-document consistency gate for the pre-registration record.

These tests catch the *duplicated-fact drift* class of error: the same fact
stated in several docs, where one copy is updated and a sibling is left stale
(what the pre-registration-v1 finalization pass surfaced -- a stale README CLI
pin, RESEARCH_PLAN's H1a scope saying "Claude Code" while SAP said "7 configs",
requirements.txt loose bounds vs VERSIONS frozen pins, unreconciled placeholder
tag dates).

Design choice: these are *positive* assertions (the current value is present /
restatements agree), not a blacklist of retired tokens. Retired values
legitimately appear in current docs as provenance notes ("pin ticked from
7.5.5", "advanced from macos-14"), and those notes are good practice -- a naive
token blacklist would punish them. The one negative check below targets an
exact retired *phrase* that never appears as a provenance note.

Privacy: this asserts only PUBLIC facts (versions, scope wording, the tag SHA).
The forbidden-identity-token gate is a separate concern owned by
tests/test_public_safety.py; do NOT add private tokens here.

Run: python -m pytest tests/test_doc_consistency.py -q
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def read(rel: str) -> str:
    return (REPO / rel).read_text(encoding="utf-8")


# --- 1. requirements.txt exact pins match the docs/VERSIONS.md host-deps table ---
#
# VERSIONS.md is the single aggregated record; it freezes these for the
# deterministic power analysis (RNG seed 20260515). requirements.txt must
# enforce that freeze with == pins rather than >= lower bounds.

FROZEN_DEPS = ("PyYAML", "numpy", "scipy", "statsmodels")


def _versions_pins() -> dict:
    text = read("docs/VERSIONS.md")
    pins = {}
    for dep in FROZEN_DEPS:
        m = re.search(rf"\|\s*{re.escape(dep)}\s*\|\s*([0-9][0-9A-Za-z.\-]*)\s*\|", text)
        if m:
            pins[dep] = m.group(1)
    return pins


def _requirements_exact_pins() -> dict:
    pins = {}
    for line in read("requirements.txt").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        m = re.match(r"([A-Za-z0-9_.\-]+)==([0-9][0-9A-Za-z.\-]*)", line)
        if m:
            pins[m.group(1)] = m.group(2)
    return pins


def test_requirements_match_versions_pins():
    vpins = _versions_pins()
    rpins = _requirements_exact_pins()
    missing = [d for d in FROZEN_DEPS if d not in vpins]
    assert not missing, f"docs/VERSIONS.md host-deps table is missing rows for: {missing}"
    for dep in FROZEN_DEPS:
        assert dep in rpins, (
            f"{dep} must be an == pin in requirements.txt to enforce the "
            f"docs/VERSIONS.md freeze (power-analysis determinism)."
        )
        assert rpins[dep] == vpins[dep], (
            f"{dep} pin mismatch: requirements.txt=={rpins[dep]} vs "
            f"docs/VERSIONS.md table {vpins[dep]}. These must agree "
            f"(RNG seed 20260515)."
        )


def test_frozen_deps_are_not_loose_bounds():
    text = read("requirements.txt")
    for dep in FROZEN_DEPS:
        assert not re.search(rf"^{re.escape(dep)}\s*>=", text, re.MULTILINE), (
            f"{dep} uses a >= lower bound; it must be an == exact pin matching "
            f"docs/VERSIONS.md."
        )


# --- 2. H1a primary scope is stated consistently across the locked docs ---
#
# Operative spec: SAP A1 / HYPOTHESIS pool the H1a primary test across the 7
# model-harness configurations. RESEARCH_PLAN restates the hypotheses for a
# general reader and must agree.

SCOPE_DOCS = ("HYPOTHESIS.md", "docs/SAP.md", "RESEARCH_PLAN.md")


def test_h1a_pools_across_seven_configs_everywhere():
    phrase = "7 model-harness configurations"
    for rel in SCOPE_DOCS:
        assert phrase in read(rel), (
            f"{rel} should state H1a pools across the '{phrase}' "
            f"(operative spec: SAP A1 / HYPOTHESIS)."
        )


def test_retired_h1a_claude_only_phrasing_absent():
    # Exact pre-expansion wording (predates the 2026-05-25 V1 expansion to 3
    # vendors). Unlike a version token, this phrase never appears as a
    # provenance note, so a negative assertion is safe here.
    stale = "pooled across the primary Claude Code model configurations"
    for rel in SCOPE_DOCS:
        assert stale not in read(rel), (
            f"{rel} contains retired pre-expansion H1a wording '{stale}'; "
            f"H1a pools across the 7 configs (SAP A1)."
        )


# --- 3. (removed) FDR-threshold-explicitness check ---
#
# We previously asserted every "Benjamini-Hochberg FDR" mention in HYPOTHESIS.md
# carried an explicit (q=0.05). That required EDITING HYPOTHESIS.md, which violates
# its own author pledge ("I will not edit this file after the tag"). HYPOTHESIS.md
# is therefore left at its frozen tagged form; the FDR threshold q=0.05 is canonical
# in SAP A1/A2. No invariant is enforced against the frozen pre-registration file.


# --- 4. Tag coordinates are stamped, and the pre-tag placeholder is gone ---

TAG_SHA = "34104be"


def test_tag_sha_stamped_in_record_docs():
    # HYPOTHESIS.md is intentionally NOT in this list: it is frozen per its own
    # author pledge ("I will not edit this file after the tag"), so the tag
    # coordinates live in the other record docs, not in HYPOTHESIS.
    for rel in ("README.md", "docs/SAP.md", "DEVIATIONS.md"):
        assert TAG_SHA in read(rel), (
            f"{rel} should record the pre-registration-v1 tag commit {TAG_SHA} "
            f"(see the README tag stamp)."
        )


def test_pretag_placeholder_status_absent():
    stale = "Ready for `pre-registration-v1` tag"
    assert stale not in read("docs/SAP.md"), (
        "docs/SAP.md still carries the pre-tag placeholder status line; it "
        "should read PRE-REGISTERED with the tag coordinates."
    )
