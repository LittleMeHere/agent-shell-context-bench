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
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


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


# --- 5. Implementation-status TABLES agree with the registry ---
#
# The drift the 2026-06-26 reconciliation fixed: five adapters were built and
# registered (empty _PLANNED sets) while README/VERSIONS status tables still
# labelled them "PIN-AT-START". This gate ties the two together so the same
# drift cannot silently return. Scoped to State/Status TABLES only and gated on
# the registry having nothing planned, so the legitimate uses of "PIN-AT-START"
# (the VERSIONS legend, dated change-log entries, and any genuinely-planned
# future cell) are never punished -- consistent with this file's "no naive
# token blacklist" design note.


def _status_table_data_rows(text: str) -> list[str]:
    """Data rows of every markdown table whose header names a State/Status column.

    A markdown table is a run of consecutive lines starting with '|' whose
    second line is a '---' separator. Only tables whose header row mentions
    'State' or 'Status' are returned (the implementation-status tables), so
    prose, the legend, and change-log bullets -- where 'PIN-AT-START' is valid
    provenance -- are never matched.
    """
    rows: list[str] = []
    lines = text.splitlines()
    i, n = 0, len(lines)
    while i < n:
        if not lines[i].lstrip().startswith("|"):
            i += 1
            continue
        block = []
        while i < n and lines[i].lstrip().startswith("|"):
            block.append(lines[i])
            i += 1
        if len(block) >= 2 and "---" in block[1]:
            header = block[0].lower()
            if "state" in header or "status" in header:
                rows.extend(block[2:])  # data rows only (skip header + separator)
    return rows


def test_status_tables_have_no_stale_pin_at_start_when_nothing_planned():
    from harness.registry import _PLANNED_AGENTS, _PLANNED_ENVIRONMENTS

    if _PLANNED_ENVIRONMENTS or _PLANNED_AGENTS:
        return  # a planned cell may legitimately show PIN-AT-START; nothing to assert
    for rel in ("README.md", "docs/VERSIONS.md"):
        for row in _status_table_data_rows(read(rel)):
            assert "PIN-AT-START" not in row, (
                f"{rel} implementation-status table still marks a row "
                f"'PIN-AT-START' while harness.registry lists no planned "
                f"adapters (empty _PLANNED sets) -- stale status/registry "
                f"drift: {row.strip()}"
            )


# --- 6. Active V2 readiness docs agree with executable candidate artifacts ---

V2_RUNTIME_DOCS = (
    "docs/V2_RUNTIME_PINNING.md",
    "docs/PRE_DATA_REMEDIATION.md",
)
V2_BANK_DOCS = (
    "docs/V2_RUNTIME_PINNING.md",
    "docs/TASK_FAMILY_QUALIFICATION.md",
    "docs/D013_ACCEPTED_FAMILY_SLATE.md",
    "docs/PRE_DATA_REMEDIATION.md",
)
V2_SHAKEDOWN_DOCS = (
    "docs/V2_RUNTIME_PINNING.md",
    "docs/PRECOLLECTION_SHAKEDOWN.md",
    "docs/PRE_DATA_REMEDIATION.md",
)
CURRENT_SHAKEDOWN_DIGEST = (
    "ee6f15cf6b677d24bb2612b4202468ffb2ae41086d68e6f2c8389b895020e023"
)


def test_active_v2_runtime_digest_and_versions_match_candidate_matrix():
    from scripts.configuration_matrix import load_matrix

    matrix = load_matrix(REPO / "config" / "v2-runtime-matrix.candidate.json")
    assert matrix.status == "candidate"
    for rel in V2_RUNTIME_DOCS:
        text = read(rel)
        assert matrix.digest in text, (
            f"{rel} must name the current executable V2 matrix digest "
            f"{matrix.digest}"
        )
        for configuration in matrix.configurations:
            assert configuration.expected_cli_version in text, (
                f"{rel} omits current CLI version "
                f"{configuration.expected_cli_version} for "
                f"{configuration.config_id}"
            )
        for version in (
            matrix.node_version,
            matrix.pwsh_version,
        ):
            assert version in text, f"{rel} omits current runtime version {version}"


def test_active_v2_task_bank_digest_matches_current_task_bytes():
    from analysis.d013_task_bank import validate_task_bank

    evidence = validate_task_bank(
        slate_path=REPO / "config" / "v2-family-slate.accepted.json",
        tasks_root=REPO / "tasks" / "v2",
    )
    assert evidence.task_count == 36
    for rel in V2_BANK_DOCS:
        assert evidence.bank_digest in read(rel), (
            f"{rel} must name current V2 task-bank digest "
            f"{evidence.bank_digest}"
        )


def test_all_registered_tasks_have_one_executable_predicate_authority():
    from analysis.task_predicate_authority import validate_predicate_authority

    evidence = validate_predicate_authority(
        tasks_root=REPO / "tasks",
        overlay_path=REPO / "config" / "v2-legacy-predicate-authority.json",
    )
    assert evidence.task_count == 50
    assert evidence.inline_canonical_tasks == 36
    assert evidence.legacy_overlay_tasks == 14
    assert evidence.authority_digest in read("docs/R021_TASK_PREDICATE_REVIEW.md")


def test_active_v2_shakedown_status_is_consistent():
    for rel in V2_SHAKEDOWN_DOCS:
        text = read(rel)
        assert CURRENT_SHAKEDOWN_DIGEST in text, (
            f"{rel} must name the current 82-call shakedown manifest"
        )
        assert "82/82" in text, f"{rel} must report the current receipt count"


def test_historical_v1_readme_routes_current_work_to_v2_handoff():
    handoff = "docs/PRE_DATA_REMEDIATION.md"
    readme = read("README.md")
    assert handoff in readme
    assert "historical V1" in readme
    assert (
        "remaining **pre-data obligations** (real-CLI / brain re-smokes"
        not in readme
    )
