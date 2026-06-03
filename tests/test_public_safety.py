"""Public repository hygiene checks.

These tests intentionally avoid the private sentinel-token list used by the
local commit/push hooks. They enforce public, structural invariants only.
"""

from __future__ import annotations

import fnmatch
import subprocess
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]


def _public_candidate_files() -> list[str]:
    out = subprocess.check_output(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        cwd=REPO,
        text=True,
        encoding="utf-8",
    )
    return [line for line in out.splitlines() if line]


def test_no_common_secret_filenames_are_tracked():
    forbidden = [
        ".env",
        ".env.*",
        "*.key",
        "*.pem",
        "credentials.json",
        "client_secret*.json",
        "service-account*.json",
        "*-api-key*",
        "*token*.json",
    ]
    offenders = [
        path
        for path in _public_candidate_files()
        for pattern in forbidden
        if fnmatch.fnmatch(Path(path).name.lower(), pattern)
    ]
    assert offenders == []


def test_raw_pre_registration_smoke_trials_are_not_tracked():
    offenders = [
        path
        for path in _public_candidate_files()
        if path.startswith("data/pre-registration/smoke_trials/")
        or (
            path.startswith("data/pre-registration/")
            and Path(path).name.startswith("trial_")
            and Path(path).suffix == ".json"
        )
    ]
    assert offenders == []


def test_generated_artifacts_are_not_tracked():
    forbidden_patterns = [
        "__pycache__/*",
        "*.pyc",
        "*.pyo",
        ".pytest_cache/*",
        ".mypy_cache/*",
        ".ruff_cache/*",
        "tmp_*/*",
    ]
    offenders = [
        path
        for path in _public_candidate_files()
        for pattern in forbidden_patterns
        if fnmatch.fnmatch(path, pattern) or fnmatch.fnmatch(Path(path).name, pattern)
    ]
    assert offenders == []


def test_line_ending_policy_is_tracked():
    attrs = (REPO / ".gitattributes").read_text(encoding="utf-8")
    assert "* text=auto eol=lf" in attrs
