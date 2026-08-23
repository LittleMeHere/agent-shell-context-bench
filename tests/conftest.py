"""Shared analysis-excluded test fixtures."""

from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest

from scripts.configuration_matrix import load_matrix


@pytest.fixture(scope="session")
def frozen_runtime_binding():
    candidate = load_matrix(
        Path(__file__).resolve().parents[1]
        / "config"
        / "v2-runtime-matrix.candidate.json"
    )
    return dataclasses.replace(candidate, status="frozen").scheduler_binding()
