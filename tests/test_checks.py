"""Regression tests for harness.checks.evaluate_checks.

evaluate_checks is the load-bearing function behind every H1 number — it
maps a FilesystemSnapshot + task YAML success_checks list to (passed,
per-check-results). A subtle bug here (path normalization, off-by-one in
no_extra_files, wrong type-dispatch) would silently corrupt every trial.

Tests added 2026-05-23 per the pre-registration finalization (D, item 7 of
the workplan). Coverage: positive C01-style success, no_extra_files
triggering on an unexpected file, file_is_empty failing on non-zero content,
path normalization (./ prefix, backslashes, forward slashes),
unknown-check-type fails closed.

Run: python -m pytest tests/ -q   (or: python tests/test_checks.py)
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

_BENCH = Path(__file__).resolve().parents[1]
if str(_BENCH) not in sys.path:
    sys.path.insert(0, str(_BENCH))

from harness.checks import evaluate_checks, requires_agent_trace
from harness.fs import local_snapshot
from harness.types import FileFingerprint, FilesystemSnapshot, ProcessResult


def _fp(size: int, content_hash: str = "x" * 64) -> FileFingerprint:
    return FileFingerprint(size=size, mtime=0.0, sha256=content_hash)


def _snap(files: dict[str, FileFingerprint], dirs: tuple[str, ...] = ()) -> FilesystemSnapshot:
    return FilesystemSnapshot(files=files, dirs=dirs)


def _write_sandbox(layout: dict[str, str]) -> Path:
    """Write `layout` (relative path -> text content) into a fresh temp
    sandbox; return the root. Used by content-based check tests."""
    root = Path(tempfile.mkdtemp(prefix="checks_test_"))
    for rel, content in layout.items():
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    return root


def _snap_from_disk(root: Path) -> FilesystemSnapshot:
    """Minimal snapshot built by walking `root` — enough for the existence /
    no_extra_files checks to operate on the same layout the content checks
    read from disk. Hashes are stubbed; the content tests don't depend on them."""
    files: dict[str, FileFingerprint] = {}
    for p in root.rglob("*"):
        if p.is_file():
            rel = p.relative_to(root).as_posix()
            files[rel] = FileFingerprint(size=p.stat().st_size, mtime=0.0, sha256="stub")
    return FilesystemSnapshot(files=files)


# -- positive case: a C01-shaped success ---------------------------------

def test_c01_shaped_success_passes_all_checks():
    """A snapshot containing exactly the C01 expected files should pass."""
    snap = _snap({
        "alpha.txt": _fp(0),
        "beta.txt": _fp(0),
        "level_1/alpha.txt": _fp(0),
        "level_1/beta.txt": _fp(0),
    })
    specs = [
        {"type": "file_exists", "path": "alpha.txt"},
        {"type": "file_exists", "path": "beta.txt"},
        {"type": "file_exists", "path": "level_1/alpha.txt"},
        {"type": "file_exists", "path": "level_1/beta.txt"},
        {"type": "file_is_empty", "path": "alpha.txt"},
        {"type": "no_extra_files", "description": "no surprises"},
    ]
    passed, results = evaluate_checks(snap, specs)
    assert passed, f"expected overall pass, got results: {[(r.check_type, r.passed, r.detail) for r in results]}"
    assert all(r.passed for r in results)
    assert len(results) == len(specs)


# -- no_extra_files triggers on unexpected file --------------------------

def test_no_extra_files_fails_when_unexpected_file_present():
    """A snapshot with a file outside the expected set must fail no_extra_files."""
    snap = _snap({
        "alpha.txt": _fp(0),
        "STRAY.tmp": _fp(10),  # not asserted by any check below
    })
    specs = [
        {"type": "file_exists", "path": "alpha.txt"},
        {"type": "no_extra_files", "description": "should fail"},
    ]
    passed, results = evaluate_checks(snap, specs)
    assert not passed
    no_extra = next(r for r in results if r.check_type == "no_extra_files")
    assert not no_extra.passed
    assert "STRAY.tmp" in no_extra.evidence


def test_no_extra_files_passes_when_only_expected_files_present():
    snap = _snap({"alpha.txt": _fp(0), "beta.txt": _fp(0)})
    specs = [
        {"type": "file_exists", "path": "alpha.txt"},
        {"type": "file_exists", "path": "beta.txt"},
        {"type": "no_extra_files"},
    ]
    passed, _ = evaluate_checks(snap, specs)
    assert passed


# -- file_is_empty fails on non-zero content -----------------------------

def test_file_is_empty_fails_on_non_zero_content():
    snap = _snap({"data.txt": _fp(42)})
    specs = [
        {"type": "file_exists", "path": "data.txt"},
        {"type": "file_is_empty", "path": "data.txt"},
    ]
    passed, results = evaluate_checks(snap, specs)
    assert not passed
    empty_check = next(r for r in results if r.check_type == "file_is_empty")
    assert not empty_check.passed
    assert "42 bytes" in empty_check.detail


def test_file_is_empty_fails_when_file_missing():
    snap = _snap({})
    specs = [{"type": "file_is_empty", "path": "ghost.txt"}]
    passed, results = evaluate_checks(snap, specs)
    assert not passed
    assert not results[0].passed
    assert "not found" in results[0].detail


# -- path normalization edge cases ---------------------------------------

def test_path_with_leading_dot_slash_normalized():
    """Task YAML may write './alpha.txt'; the snapshot stores 'alpha.txt'."""
    snap = _snap({"alpha.txt": _fp(0)})
    specs = [{"type": "file_exists", "path": "./alpha.txt"}]
    passed, results = evaluate_checks(snap, specs)
    assert passed, f"./prefix should normalize, got: {results[0].detail}"


def test_path_with_backslash_normalized_to_forward():
    """Windows-style backslashes in YAML must be normalized to POSIX before lookup."""
    snap = _snap({"build/output.txt": _fp(0)})
    specs = [{"type": "file_exists", "path": "build\\output.txt"}]
    passed, results = evaluate_checks(snap, specs)
    assert passed, f"backslash should normalize to forward, got: {results[0].detail}"


def test_path_with_mixed_separators_normalized():
    snap = _snap({"a/b/c.txt": _fp(0)})
    specs = [{"type": "file_exists", "path": "./a\\b/c.txt"}]
    passed, _ = evaluate_checks(snap, specs)
    assert passed


# -- directory_exists semantics ------------------------------------------

def test_directory_exists_via_explicit_dir():
    snap = _snap(files={}, dirs=("build",))
    specs = [{"type": "directory_exists", "path": "build"}]
    passed, _ = evaluate_checks(snap, specs)
    assert passed


def test_directory_exists_via_contained_file():
    """A directory that holds a file should satisfy directory_exists even
    when the dir itself isn't explicitly snapshotted."""
    snap = _snap({"build/output.txt": _fp(0)})
    specs = [{"type": "directory_exists", "path": "build"}]
    passed, _ = evaluate_checks(snap, specs)
    assert passed


def test_directory_exists_fails_when_neither_dir_nor_files():
    snap = _snap({})
    specs = [{"type": "directory_exists", "path": "ghost"}]
    passed, _ = evaluate_checks(snap, specs)
    assert not passed


# -- unknown check type fails closed -------------------------------------

def test_unknown_check_type_fails_closed():
    """A typo in a task YAML must NOT silently pass — it must fail loudly."""
    snap = _snap({"alpha.txt": _fp(0)})
    specs = [
        {"type": "file_exists", "path": "alpha.txt"},
        {"type": "file_does_exist_maybe", "path": "alpha.txt"},  # typo
    ]
    passed, results = evaluate_checks(snap, specs)
    assert not passed, "an unknown check type must NOT pass the overall trial"
    bogus = next(r for r in results if r.check_type == "file_does_exist_maybe")
    assert not bogus.passed
    assert "unknown check type" in bogus.detail


def test_trace_dependency_detection_is_exact():
    assert requires_agent_trace([{"type": "file_exists", "path": "x"}]) is False
    assert requires_agent_trace(
        [
            {"type": "file_exists", "path": "x"},
            {"type": "agent_any_command_stdout_equals", "expected": "ok"},
        ]
    ) is True


def test_missing_type_field_fails_closed():
    snap = _snap({})
    specs = [{"path": "alpha.txt"}]  # no 'type' field at all
    passed, results = evaluate_checks(snap, specs)
    assert not passed
    assert results[0].check_type == "<missing>"


def test_stop_on_failure_skips_later_environment_command():
    calls = []

    def executor(argv, *, cwd, timeout, env):
        calls.append((argv, cwd, timeout, env))
        raise AssertionError("executor must not run after a prior failure")

    passed, results = evaluate_checks(
        _snap({}),
        [
            {"type": "file_exists", "path": "missing.txt"},
            {"type": "environment_command", "argv": ["python", "-V"]},
        ],
        environment_exec=executor,
        environment_cwd="sandbox",
        stop_on_failure=True,
    )

    assert not passed
    assert len(results) == 1
    assert calls == []


def test_environment_command_bypasses_proxies_for_loopback():
    captured = {}

    def executor(argv, *, cwd, timeout, env):
        captured.update(argv=argv, cwd=cwd, timeout=timeout, env=env)
        return ProcessResult(
            argv=tuple(argv),
            returncode=0,
            stdout="",
            stderr="",
            duration_seconds=0.0,
            timed_out=False,
        )

    passed, results = evaluate_checks(
        _snap({}),
        [{"type": "environment_command", "argv": ["python", "-V"]}],
        environment_exec=executor,
        environment_cwd="sandbox",
    )

    assert passed, results
    assert captured["env"] == {
        "ALL_PROXY": "",
        "HTTPS_PROXY": "",
        "HTTP_PROXY": "",
        "NO_PROXY": "127.0.0.1,localhost,::1",
        "all_proxy": "",
        "https_proxy": "",
        "http_proxy": "",
        "no_proxy": "127.0.0.1,localhost,::1",
    }


def test_environment_command_adds_macos_python_compat(monkeypatch):
    captured = {}

    def executor(argv, *, cwd, timeout, env):
        captured.update(argv=argv, cwd=cwd, timeout=timeout, env=env)
        return ProcessResult(
            argv=tuple(argv),
            returncode=0,
            stdout="",
            stderr="",
            duration_seconds=0.0,
            timed_out=False,
        )

    monkeypatch.setattr("harness.checks.sys.platform", "darwin")
    passed, results = evaluate_checks(
        FilesystemSnapshot(files=frozenset(), dirs=frozenset()),
        [{"type": "environment_command", "argv": ["python", "-V"]}],
        environment_exec=executor,
        environment_cwd="/sandbox",
    )

    assert passed, results
    assert Path(captured["env"]["PYTHONPATH"]).name == "python_compat"


# -- spec mutation safety ------------------------------------------------

def test_no_extra_files_does_not_mutate_input_specs():
    """evaluate_checks internally injects _expected_files into the
    no_extra_files spec; this must NOT mutate the caller's spec dict."""
    spec = {"type": "no_extra_files"}
    specs = [
        {"type": "file_exists", "path": "alpha.txt"},
        spec,
    ]
    snap = _snap({"alpha.txt": _fp(0)})
    evaluate_checks(snap, specs)
    # _expected_files must not have leaked into the caller's dict
    assert "_expected_files" not in spec


# -- overall AND semantics -----------------------------------------------

def test_overall_pass_requires_every_check_to_pass():
    snap = _snap({"alpha.txt": _fp(0)})
    specs = [
        {"type": "file_exists", "path": "alpha.txt"},
        {"type": "file_exists", "path": "beta.txt"},  # missing
    ]
    passed, _ = evaluate_checks(snap, specs)
    assert not passed


def test_empty_specs_passes_vacuously():
    """No checks = no failures. Edge case; document the behavior."""
    snap = _snap({})
    passed, results = evaluate_checks(snap, [])
    assert passed and results == []


# -- __pycache__ / *.pyc filtering ---------------------------------------

def test_no_extra_files_ignores_pycache_directory_artifacts():
    """An agent that runs `python -c "import lib"` to verify its work
    creates __pycache__/*.pyc. Those must not register as 'extras' or the
    diligent agent is penalised relative to the lazy one."""
    snap = _snap({
        "lib/__init__.py": _fp(10),
        "lib/__pycache__/__init__.cpython-311.pyc": _fp(200),
        "lib/__pycache__/processor.cpython-311.pyc": _fp(500),
    })
    specs = [
        {"type": "file_exists", "path": "lib/__init__.py"},
        {"type": "no_extra_files"},
    ]
    passed, _ = evaluate_checks(snap, specs)
    assert passed, "pycache files must not count as extras"


def test_no_extra_files_ignores_bare_pyc_files():
    snap = _snap({
        "lib/__init__.py": _fp(10),
        "lib/processor.pyc": _fp(500),  # standalone .pyc, not under __pycache__
        "lib/processor.pyo": _fp(500),
    })
    specs = [
        {"type": "file_exists", "path": "lib/__init__.py"},
        {"type": "no_extra_files"},
    ]
    passed, _ = evaluate_checks(snap, specs)
    assert passed


def test_no_files_matching_ignores_pycache():
    snap = _snap({
        "src/__pycache__/foo.cpython-311.pyc": _fp(100),
        "src/note.txt": _fp(5),
    })
    specs = [
        {"type": "file_exists", "path": "src/note.txt"},
        {"type": "no_files_matching", "pattern": "*.pyc"},
    ]
    passed, results = evaluate_checks(snap, specs)
    assert passed, (
        "no_files_matching must ignore cache artefacts, even when the "
        "pattern would textually match them"
    )
    nfm = next(r for r in results if r.check_type == "no_files_matching")
    assert nfm.passed


# -- no_files_matching positive / negative -------------------------------

def test_no_files_matching_fails_on_actual_match():
    snap = _snap({
        "lib/__init__.py": _fp(10),
        "lib/processor.py.bak": _fp(500),
    })
    specs = [
        {"type": "file_exists", "path": "lib/__init__.py"},
        {"type": "no_files_matching", "pattern": "*.bak"},
    ]
    passed, results = evaluate_checks(snap, specs)
    assert not passed
    nfm = next(r for r in results if r.check_type == "no_files_matching")
    assert not nfm.passed
    assert "processor.py.bak" in nfm.evidence


def test_no_files_matching_requires_pattern_field():
    snap = _snap({"a.txt": _fp(0)})
    specs = [{"type": "no_files_matching"}]
    passed, results = evaluate_checks(snap, specs)
    assert not passed
    assert "pattern" in results[0].detail


# -- python_parses check -------------------------------------------------

def test_python_parses_passes_on_valid_python():
    root = _write_sandbox({"mod.py": "def f(x):\n    return x + 1\n"})
    snap = _snap_from_disk(root)
    passed, results = evaluate_checks(
        snap,
        [{"type": "python_parses", "path": "mod.py"}],
        sandbox_host_root=root,
    )
    assert passed, results[0].detail


def test_python_parses_fails_on_syntax_error():
    root = _write_sandbox({"mod.py": "def f(:\n  pass\n"})  # invalid syntax
    snap = _snap_from_disk(root)
    passed, results = evaluate_checks(
        snap,
        [{"type": "python_parses", "path": "mod.py"}],
        sandbox_host_root=root,
    )
    assert not passed
    assert "does not parse" in results[0].detail


def test_python_parses_fails_closed_without_sandbox_host_root():
    """A content check called without sandbox_host_root must fail closed,
    not silently pass — otherwise a runner-wiring bug would invisibly
    convert every content check into a free success."""
    snap = _snap({"mod.py": _fp(20)})
    passed, results = evaluate_checks(
        snap,
        [{"type": "python_parses", "path": "mod.py"}],
    )
    assert not passed
    assert "sandbox host root" in results[0].detail


def test_python_parses_fails_when_file_missing_on_disk():
    root = _write_sandbox({"other.py": "pass\n"})
    snap = _snap_from_disk(root)
    passed, results = evaluate_checks(
        snap,
        [{"type": "python_parses", "path": "ghost.py"}],
        sandbox_host_root=root,
    )
    assert not passed
    assert "not found on disk" in results[0].detail


# -- file_contains_substring_count check ---------------------------------

def test_substring_count_exact_match_passes():
    root = _write_sandbox({"a.py": "foo foo bar foo\n"})
    snap = _snap_from_disk(root)
    passed, _ = evaluate_checks(
        snap,
        [{
            "type": "file_contains_substring_count",
            "path": "a.py",
            "substring": "foo",
            "count": 3,
        }],
        sandbox_host_root=root,
    )
    assert passed


def test_substring_count_mismatch_fails():
    root = _write_sandbox({"a.py": "foo foo bar\n"})
    snap = _snap_from_disk(root)
    passed, results = evaluate_checks(
        snap,
        [{
            "type": "file_contains_substring_count",
            "path": "a.py",
            "substring": "foo",
            "count": 3,
        }],
        sandbox_host_root=root,
    )
    assert not passed
    assert "2 time(s)" in results[0].detail and "expected 3" in results[0].detail


def test_substring_count_zero_passes_when_absent():
    """Asserting count=0 is the 'forbidden identifier' pattern — used in
    C03 to check that `process_data` no longer appears in lib/__init__.py."""
    root = _write_sandbox({"a.py": "no occurrences here\n"})
    snap = _snap_from_disk(root)
    passed, _ = evaluate_checks(
        snap,
        [{
            "type": "file_contains_substring_count",
            "path": "a.py",
            "substring": "process_data",
            "count": 0,
        }],
        sandbox_host_root=root,
    )
    assert passed


def test_substring_count_requires_non_empty_substring():
    root = _write_sandbox({"a.py": "x\n"})
    snap = _snap_from_disk(root)
    passed, results = evaluate_checks(
        snap,
        [{
            "type": "file_contains_substring_count",
            "path": "a.py",
            "substring": "",
            "count": 0,
        }],
        sandbox_host_root=root,
    )
    assert not passed
    assert "non-empty" in results[0].detail


def test_substring_count_rejects_negative_count():
    root = _write_sandbox({"a.py": "x\n"})
    snap = _snap_from_disk(root)
    passed, results = evaluate_checks(
        snap,
        [{
            "type": "file_contains_substring_count",
            "path": "a.py",
            "substring": "x",
            "count": -1,
        }],
        sandbox_host_root=root,
    )
    assert not passed
    assert "non-negative" in results[0].detail


# -- construct validity: C01 wrong-content must fail ----------------------

C01_REQUIRED_PATHS = [
    "alpha.txt", "beta.txt",
    "level_1/alpha.txt", "level_1/beta.txt",
    "level_1/level_2/alpha.txt", "level_1/level_2/beta.txt",
    "level_1/level_2/level_3/alpha.txt", "level_1/level_2/level_3/beta.txt",
    "level_1/level_2/level_3/level_4/alpha.txt",
    "level_1/level_2/level_3/level_4/beta.txt",
    "level_1/level_2/level_3/level_4/level_5/alpha.txt",
    "level_1/level_2/level_3/level_4/level_5/beta.txt",
]


def _c01_specs() -> list[dict]:
    """Reproduce C01's success_checks shape (file_exists + file_is_empty
    per path, plus no_extra_files) so this test pins what the YAML promises."""
    specs: list[dict] = []
    for p in C01_REQUIRED_PATHS:
        specs.append({"type": "file_exists", "path": p})
        specs.append({"type": "file_is_empty", "path": p})
    specs.append({"type": "no_extra_files"})
    return specs


def test_c01_correct_agent_passes():
    """An agent that creates exactly the 12 empty files should pass."""
    snap = _snap({p: _fp(0) for p in C01_REQUIRED_PATHS})
    passed, _ = evaluate_checks(snap, _c01_specs())
    assert passed


def test_c01_wrong_content_agent_fails():
    """REGRESSION GUARD for the construct-validity hole flagged in the
    pre-reg review: an agent that creates the right paths with non-empty
    content used to pass C01 (file_exists alone). With file_is_empty
    asserted per path, the same agent must now fail."""
    snap = _snap({p: _fp(5) for p in C01_REQUIRED_PATHS})  # 5 bytes each
    passed, results = evaluate_checks(snap, _c01_specs())
    assert not passed, "wrong-content agent on C01 must NOT pass"
    failing_empties = [
        r for r in results
        if r.check_type == "file_is_empty" and not r.passed
    ]
    assert len(failing_empties) == 12, (
        "every file_is_empty check should have fired; got "
        f"{len(failing_empties)}"
    )


def test_c01_no_op_agent_fails():
    """A no-op agent on C01 leaves the sandbox empty — every file_exists
    should fire."""
    snap = _snap({})
    passed, results = evaluate_checks(snap, _c01_specs())
    assert not passed
    failing_exists = [
        r for r in results if r.check_type == "file_exists" and not r.passed
    ]
    assert len(failing_exists) == 12


# -- construct validity: C03 no-op must fail ------------------------------

C03_SEED = {
    "lib/processor.py": (
        '"""Process incoming data records.\n\n'
        "Historical note: this module originally exposed `process_data` as a\n"
        "single entrypoint. As of the 2024 refactor, callers should prefer\n"
        "the per-record helpers.\n"
        '"""\n\n'
        "def process_data(record):\n"
        '    """Process one record. Returns the transformed dict."""\n'
        '    return {"id": record["id"], "ok": True}\n\n'
        "def _internal_helper(record):\n"
        "    # Note: do not call process_data from here.\n"
        "    return record\n"
    ),
    "lib/__init__.py": (
        "from .processor import process_data\n\n"
        '__all__ = ["process_data"]\n'
    ),
    "app/main.py": (
        "from lib import process_data\n\n"
        "def main():\n"
        '    sample = {"id": 1}\n'
        "    result = process_data(sample)\n"
        "    print(result)\n"
        "    # legacy: the old process_data behavior is preserved for backcompat\n"
        "    return result\n\n"
        'if __name__ == "__main__":\n'
        "    main()\n"
    ),
    "app/utils.py": (
        "from lib.processor import process_data\n\n"
        'ERROR_MESSAGE = "process_data failed for record"\n\n'
        "def safe_process(record):\n"
        "    try:\n"
        "        return process_data(record)\n"
        "    except Exception as e:\n"
        '        return {"error": ERROR_MESSAGE, "detail": str(e)}\n'
    ),
    "tests/test_processor.py": (
        "from lib.processor import process_data\n\n\n"
        "def test_process_data_returns_ok():\n"
        '    """Verify process_data returns an ok flag (was named process_data '
        'for historical reasons)."""\n'
        '    assert process_data({"id": 1})["ok"] is True\n'
    ),
}

# The substring-count checks the C03 YAML registers, kept in lockstep with
# the YAML so a future YAML edit that violates this contract trips the test.
C03_COUNT_SPECS: list[tuple[str, str, int]] = [
    ("lib/processor.py", "process_data", 2),
    ("lib/processor.py", "process_record", 1),
    ("lib/__init__.py", "process_data", 0),
    ("lib/__init__.py", "process_record", 2),
    ("app/main.py", "process_data", 1),
    ("app/main.py", "process_record", 2),
    ("app/utils.py", "process_data", 1),
    ("app/utils.py", "process_record", 2),
    ("tests/test_processor.py", "process_data", 3),
    ("tests/test_processor.py", "process_record", 2),
]


def _c03_specs() -> list[dict]:
    py_files = list(C03_SEED.keys())
    specs: list[dict] = []
    for p in py_files:
        specs.append({"type": "file_exists", "path": p})
    for p in py_files:
        specs.append({"type": "python_parses", "path": p})
    for path, sub, n in C03_COUNT_SPECS:
        specs.append({
            "type": "file_contains_substring_count",
            "path": path,
            "substring": sub,
            "count": n,
        })
    specs.extend([
        {"type": "no_files_matching", "pattern": "*.bak"},
        {"type": "no_files_matching", "pattern": "*process_data_old*"},
        {"type": "no_files_matching", "pattern": "*refactor-log*"},
        {"type": "no_extra_files"},
    ])
    return specs


def _apply_correct_rename(content: str, file_rel: str) -> str:
    """Apply C03's intended rename: code refs become process_record;
    docstrings / comments / string literals retain process_data. The map
    below mirrors the per-file expectation in the C03 YAML."""
    if file_rel == "lib/processor.py":
        return content.replace("def process_data", "def process_record")
    if file_rel == "lib/__init__.py":
        return content.replace("process_data", "process_record")
    if file_rel == "app/main.py":
        return (
            content
            .replace("from lib import process_data", "from lib import process_record")
            .replace("result = process_data(sample)", "result = process_record(sample)")
        )
    if file_rel == "app/utils.py":
        return (
            content
            .replace(
                "from lib.processor import process_data",
                "from lib.processor import process_record",
            )
            .replace("return process_data(record)", "return process_record(record)")
        )
    if file_rel == "tests/test_processor.py":
        return (
            content
            .replace(
                "from lib.processor import process_data",
                "from lib.processor import process_record",
            )
            .replace(
                'assert process_data({"id": 1})',
                'assert process_record({"id": 1})',
            )
        )
    return content


def test_c03_no_op_agent_fails():
    """REGRESSION GUARD for the worst finding in the pre-reg review:
    a no-op agent on C03 used to pass success_checks because preloaded
    files satisfied file_exists and no_extra_files. With substring-count
    checks asserting the post-rename pattern, the same no-op must fail."""
    root = _write_sandbox(C03_SEED)
    snap = _snap_from_disk(root)
    passed, results = evaluate_checks(
        snap, _c03_specs(), sandbox_host_root=root
    )
    assert not passed, "no-op agent on C03 must NOT pass"
    failed_counts = [
        r for r in results
        if r.check_type == "file_contains_substring_count" and not r.passed
    ]
    # Every count is wrong: process_data is over-count, process_record is 0.
    assert len(failed_counts) == len(C03_COUNT_SPECS), (
        f"expected all {len(C03_COUNT_SPECS)} substring counts to fail on "
        f"a no-op, got {len(failed_counts)}"
    )


def test_c03_correct_rename_passes():
    """A correctly-applied rename — code refs swapped, non-code refs
    preserved — must pass the full C03 check suite end to end."""
    renamed = {
        path: _apply_correct_rename(content, path)
        for path, content in C03_SEED.items()
    }
    root = _write_sandbox(renamed)
    snap = _snap_from_disk(root)
    passed, results = evaluate_checks(
        snap, _c03_specs(), sandbox_host_root=root
    )
    if not passed:
        failing = [(r.check_type, r.detail) for r in results if not r.passed]
        raise AssertionError(f"correct rename should pass; failures: {failing}")


def test_c03_naive_global_replace_fails():
    """A naive `sed s/process_data/process_record/g` also rewrites the
    preserved strings — the count checks must catch that."""
    sed_replaced = {
        path: content.replace("process_data", "process_record")
        for path, content in C03_SEED.items()
    }
    root = _write_sandbox(sed_replaced)
    snap = _snap_from_disk(root)
    passed, results = evaluate_checks(
        snap, _c03_specs(), sandbox_host_root=root
    )
    assert not passed, "naive global replace must NOT pass C03"
    # In particular: the preserved process_data mentions are now gone,
    # so the (path, 'process_data', N) checks with N>0 should fire.
    failing_preserve_checks = [
        r for r in results
        if (
            r.check_type == "file_contains_substring_count"
            and not r.passed
            and "process_data" in r.detail
            and "expected 0" not in r.detail
        )
    ]
    assert failing_preserve_checks, (
        "checks pinning preserved process_data mentions should fire under "
        "a global s/process_data/process_record/g"
    )


def test_c03_with_pycache_artifacts_still_passes():
    """An agent that runs `python -c "from lib import process_record"` to
    self-verify creates __pycache__ entries; those must not flip a
    correctly-renamed trial into failure (denominator-bias guard)."""
    renamed = {
        path: _apply_correct_rename(content, path)
        for path, content in C03_SEED.items()
    }
    renamed["lib/__pycache__/__init__.cpython-311.pyc"] = "stub-bytecode"
    renamed["lib/__pycache__/processor.cpython-311.pyc"] = "stub-bytecode"
    renamed["app/__pycache__/main.cpython-311.pyc"] = "stub-bytecode"
    root = _write_sandbox(renamed)
    snap = _snap_from_disk(root)
    passed, results = evaluate_checks(
        snap, _c03_specs(), sandbox_host_root=root
    )
    if not passed:
        failing = [(r.check_type, r.detail) for r in results if not r.passed]
        raise AssertionError(
            f"pycache artefacts should not fail a correct rename; failures: {failing}"
        )


# -- file_content_equals --------------------------------------------------

def test_file_content_equals_passes_on_exact_match():
    root = _write_sandbox({"a.txt": "hello\nworld\n"})
    snap = _snap_from_disk(root)
    passed, _ = evaluate_checks(
        snap,
        [{"type": "file_content_equals", "path": "a.txt", "content": "hello\nworld\n"}],
        sandbox_host_root=root,
    )
    assert passed


def test_file_content_equals_fails_on_byte_mismatch():
    root = _write_sandbox({"a.txt": "hello\nworld\n"})
    snap = _snap_from_disk(root)
    passed, results = evaluate_checks(
        snap,
        [{"type": "file_content_equals", "path": "a.txt", "content": "hello\nWORLD\n"}],
        sandbox_host_root=root,
    )
    assert not passed
    assert "diverges at byte" in results[0].detail


def test_file_content_equals_normalises_crlf():
    """An agent writing \\r\\n on Windows should still pass when the expected
    content uses \\n (universal-newlines normalisation on both sides)."""
    root = Path(tempfile.mkdtemp(prefix="checks_test_crlf_"))
    (root / "a.txt").write_bytes(b"line1\r\nline2\r\n")
    snap = _snap_from_disk(root)
    passed, results = evaluate_checks(
        snap,
        [{"type": "file_content_equals", "path": "a.txt", "content": "line1\nline2\n"}],
        sandbox_host_root=root,
    )
    assert passed, results[0].detail


def test_file_content_equals_fails_closed_without_sandbox_host_root():
    snap = _snap({"a.txt": _fp(10)})
    passed, results = evaluate_checks(
        snap,
        [{"type": "file_content_equals", "path": "a.txt", "content": "x"}],
    )
    assert not passed
    assert "sandbox host root" in results[0].detail


def test_file_content_equals_accepts_ps51_redirect_utf16():
    """PS 5.1 `>` / `Out-File` write UTF-16LE with BOM — the exact bytes
    below were captured from a real PS 5.1 `'5' > file` on 2026-07-03.
    Which encoding a shell's redirect writes varies BY ENVIRONMENT (the
    treatment variable), so a strict-UTF-8 read would concentrate false
    failures on the PS 5.1 arm and bias the cross-environment comparison.
    The BOM-sniffing reader must decode this to a passing '5'."""
    root = Path(tempfile.mkdtemp(prefix="checks_test_utf16_"))
    (root / "answer.txt").write_bytes(b"\xff\xfe5\x00\r\x00\n\x00")
    snap = _snap_from_disk(root)
    passed, results = evaluate_checks(
        snap,
        [{"type": "file_content_equals", "path": "answer.txt", "content": "5\n"}],
        sandbox_host_root=root,
    )
    assert passed, results[0].detail


def test_file_content_equals_accepts_utf8_bom():
    """PS 5.1 `Set-Content -Encoding UTF8` writes a UTF-8 BOM (captured:
    b'\\xef\\xbb\\xbf5\\r\\n'); the BOM must be stripped, not compared."""
    root = Path(tempfile.mkdtemp(prefix="checks_test_bom_"))
    (root / "answer.txt").write_bytes(b"\xef\xbb\xbf5\r\n")
    snap = _snap_from_disk(root)
    passed, results = evaluate_checks(
        snap,
        [{"type": "file_content_equals", "path": "answer.txt", "content": "5\n"}],
        sandbox_host_root=root,
    )
    assert passed, results[0].detail


def test_file_content_equals_fails_closed_on_undecodable_bytes():
    root = Path(tempfile.mkdtemp(prefix="checks_test_junk_"))
    (root / "a.txt").write_bytes(b"\x81\x82\xff binary junk")
    snap = _snap_from_disk(root)
    passed, results = evaluate_checks(
        snap,
        [{"type": "file_content_equals", "path": "a.txt", "content": "x"}],
        sandbox_host_root=root,
    )
    assert not passed
    assert "not decodable" in results[0].detail


def test_file_content_equals_tolerates_trailing_newline_difference():
    """`printf '5'` / Python write('5') omit the final newline; heredocs,
    echo, and Set-Content append one. No prompt pins the convention, so
    the comparison strips trailing newlines on both sides."""
    root = _write_sandbox({"a.txt": "5"})
    snap = _snap_from_disk(root)
    passed, results = evaluate_checks(
        snap,
        [{"type": "file_content_equals", "path": "a.txt", "content": "5\n"}],
        sandbox_host_root=root,
    )
    assert passed, results[0].detail
    # ...but content differences beyond the trailing newline still fail.
    root2 = _write_sandbox({"a.txt": "6"})
    passed2, _ = evaluate_checks(
        _snap_from_disk(root2),
        [{"type": "file_content_equals", "path": "a.txt", "content": "5\n"}],
        sandbox_host_root=root2,
    )
    assert not passed2


# -- json_content_equals --------------------------------------------------

def test_json_content_equals_passes_on_structural_match():
    root = _write_sandbox({
        "a.json": '{\n  "name": "x",\n  "items": [1, 2, 3]\n}\n'
    })
    snap = _snap_from_disk(root)
    passed, _ = evaluate_checks(
        snap,
        [{
            "type": "json_content_equals",
            "path": "a.json",
            "value": {"name": "x", "items": [1, 2, 3]},
        }],
        sandbox_host_root=root,
    )
    assert passed


def test_json_content_equals_ignores_whitespace_differences():
    """Compact JSON and pretty JSON with the same structure must compare equal."""
    root = _write_sandbox({"a.json": '{"items":[1,2,3]}'})  # compact
    snap = _snap_from_disk(root)
    passed, _ = evaluate_checks(
        snap,
        [{
            "type": "json_content_equals",
            "path": "a.json",
            "value": {"items": [1, 2, 3]},
        }],
        sandbox_host_root=root,
    )
    assert passed


def test_json_content_equals_fails_on_structural_mismatch():
    root = _write_sandbox({"a.json": '{"items":[1,2,3]}'})
    snap = _snap_from_disk(root)
    passed, results = evaluate_checks(
        snap,
        [{
            "type": "json_content_equals",
            "path": "a.json",
            "value": {"items": [1, 2, 4]},  # last element differs
        }],
        sandbox_host_root=root,
    )
    assert not passed
    assert "does not match" in results[0].detail


def test_json_content_equals_fails_on_unparseable_json():
    root = _write_sandbox({"a.json": "{not valid json"})
    snap = _snap_from_disk(root)
    passed, results = evaluate_checks(
        snap,
        [{
            "type": "json_content_equals",
            "path": "a.json",
            "value": {},
        }],
        sandbox_host_root=root,
    )
    assert not passed
    assert "not valid JSON" in results[0].detail


# -- file_count_matching --------------------------------------------------

def test_file_count_matching_fnmatch_exact_count():
    snap = _snap({
        "a.tmp": _fp(0), "b.tmp": _fp(0), "c.txt": _fp(0),
    })
    passed, _ = evaluate_checks(
        snap,
        [{"type": "file_count_matching", "pattern": "*.tmp", "count": 2}],
        sandbox_host_root="/unused",  # not needed for fnmatch-only
    )
    assert passed


def test_file_count_matching_regex_anchored():
    snap = _snap({
        "app.log.2026-05-25": _fp(20),
        "app.log.": _fp(20),  # malformed — must NOT match anchored regex
    })
    passed, results = evaluate_checks(
        snap,
        [{
            "type": "file_count_matching",
            "regex": r"^app\.log\.\d{4}-\d{2}-\d{2}$",
            "count": 1,
        }],
        sandbox_host_root="/unused",
    )
    assert passed, results[0].detail


def test_file_count_matching_regex_count_mismatch():
    snap = _snap({"app.log.2026-05-25": _fp(20), "app.log.2026-05-26": _fp(20)})
    passed, results = evaluate_checks(
        snap,
        [{
            "type": "file_count_matching",
            "regex": r"^app\.log\.\d{4}-\d{2}-\d{2}$",
            "count": 1,
        }],
        sandbox_host_root="/unused",
    )
    assert not passed
    assert "expected 1" in results[0].detail


def test_file_count_matching_content_same_as_passes():
    root = _write_sandbox({
        "app.log": "production log\nrows\n",
        "app.log.2026-05-25": "production log\nrows\n",
    })
    snap = _snap_from_disk(root)
    passed, results = evaluate_checks(
        snap,
        [{
            "type": "file_count_matching",
            "regex": r"^app\.log\.\d{4}-\d{2}-\d{2}$",
            "count": 1,
            "content_same_as": "app.log",
        }],
        sandbox_host_root=root,
    )
    assert passed, results[0].detail


def test_file_count_matching_content_same_as_fails_on_content_drift():
    root = _write_sandbox({
        "app.log": "production log\nrows\n",
        "app.log.2026-05-25": "different content\n",
    })
    snap = _snap_from_disk(root)
    passed, results = evaluate_checks(
        snap,
        [{
            "type": "file_count_matching",
            "regex": r"^app\.log\.\d{4}-\d{2}-\d{2}$",
            "count": 1,
            "content_same_as": "app.log",
        }],
        sandbox_host_root=root,
    )
    assert not passed
    assert "differs from reference" in results[0].detail


def test_file_count_matching_requires_exactly_one_of_pattern_or_regex():
    snap = _snap({"a.tmp": _fp(0)})
    for spec in (
        {"type": "file_count_matching", "count": 1},  # neither
        {  # both
            "type": "file_count_matching",
            "pattern": "*.tmp",
            "regex": r"^a\.tmp$",
            "count": 1,
        },
    ):
        passed, results = evaluate_checks(
            snap, [spec], sandbox_host_root="/unused"
        )
        assert not passed
        assert "exactly one of 'pattern' or 'regex'" in results[0].detail


def test_file_count_matching_ignores_pycache_in_match_set():
    snap = _snap({
        "lib/__pycache__/foo.cpython-311.pyc": _fp(200),
        "lib/processor.py": _fp(10),
    })
    passed, _ = evaluate_checks(
        snap,
        [{"type": "file_count_matching", "pattern": "*.pyc", "count": 0}],
        sandbox_host_root="/unused",
    )
    assert passed


# -- agent_any_command_stdout_equals --------------------------------------

class _StubCommand:
    """Duck-typed CommandRecord for tests."""
    def __init__(
        self,
        index: int,
        command: str = "",
        stdout: str = "",
        stderr: str = "",
    ) -> None:
        self.index = index
        self.command = command
        self.stdout = stdout
        self.stderr = stderr


def test_agent_any_command_stdout_equals_passes_when_one_matches():
    snap = _snap({})
    commands = [
        _StubCommand(0, stdout="ls output\n"),
        _StubCommand(1, stdout="real answer\n"),
        _StubCommand(2, stdout="verification output\n"),
    ]
    passed, _ = evaluate_checks(
        snap,
        [{"type": "agent_any_command_stdout_equals", "expected": "real answer\n"}],
        agent_commands=commands,
    )
    assert passed


def test_agent_any_command_stdout_equals_fails_when_none_match():
    snap = _snap({})
    commands = [_StubCommand(0, stdout="wrong\n")]
    passed, results = evaluate_checks(
        snap,
        [{"type": "agent_any_command_stdout_equals", "expected": "right\n"}],
        agent_commands=commands,
    )
    assert not passed
    assert "no command among 1" in results[0].detail


def test_agent_any_command_stdout_equals_fails_on_empty_command_list():
    """A no-op agent (zero commands) must fail this check — no command
    means no answer."""
    snap = _snap({})
    passed, results = evaluate_checks(
        snap,
        [{"type": "agent_any_command_stdout_equals", "expected": "x\n"}],
        agent_commands=[],
    )
    assert not passed
    assert "no command among 0" in results[0].detail


def test_agent_any_command_stdout_equals_fails_closed_without_commands_kwarg():
    snap = _snap({})
    passed, results = evaluate_checks(
        snap,
        [{"type": "agent_any_command_stdout_equals", "expected": "x"}],
    )
    assert not passed
    assert "agent command trace" in results[0].detail


def test_agent_any_command_stdout_equals_normalises_crlf():
    snap = _snap({})
    commands = [_StubCommand(0, stdout="line\r\n")]
    passed, _ = evaluate_checks(
        snap,
        [{"type": "agent_any_command_stdout_equals", "expected": "line\n"}],
        agent_commands=commands,
    )
    assert passed


def test_agent_any_command_stdout_equals_can_require_command_text():
    snap = _snap({})
    commands = [
        _StubCommand(0, command="Write-Output 'real answer'", stdout="real answer\n"),
        _StubCommand(1, command="Get-Content app.log | Select-String ERROR", stdout="real answer\n"),
    ]
    passed, _ = evaluate_checks(
        snap,
        [{
            "type": "agent_any_command_stdout_equals",
            "expected": "real answer\n",
            "command_contains": ["app.log", "ERROR"],
            "command_not_regex": r"(?i)\b(write-output|echo|printf)\b",
        }],
        agent_commands=commands,
    )
    assert passed


def test_agent_any_command_stdout_equals_rejects_matching_stdout_from_wrong_command():
    snap = _snap({})
    commands = [
        _StubCommand(0, command="Write-Output 'real answer'", stdout="real answer\n"),
    ]
    passed, results = evaluate_checks(
        snap,
        [{
            "type": "agent_any_command_stdout_equals",
            "expected": "real answer\n",
            "command_contains": ["app.log", "ERROR"],
            "command_not_regex": r"(?i)\b(write-output|echo|printf)\b",
        }],
        agent_commands=commands,
    )
    assert not passed
    assert "failed command-text constraints" in results[0].detail


def test_agent_any_command_stdout_equals_tolerates_trailing_newline():
    """Adapters record stdout with the final newline trimmed (see the real
    fixture capture); the YAML expected blocks end with one. Both sides
    are trailing-newline-stripped, in either direction."""
    snap = _snap({})
    commands = [_StubCommand(0, command="cmd", stdout="real answer")]
    passed, _ = evaluate_checks(
        snap,
        [{"type": "agent_any_command_stdout_equals", "expected": "real answer\n"}],
        agent_commands=commands,
    )
    assert passed
    commands2 = [_StubCommand(0, command="cmd", stdout="real answer\n")]
    passed2, _ = evaluate_checks(
        snap,
        [{"type": "agent_any_command_stdout_equals", "expected": "real answer"}],
        agent_commands=commands2,
    )
    assert passed2


def test_agent_any_command_stdout_equals_require_empty_stderr():
    """With require_empty_stderr, only a stderr-clean matching command
    passes; a noisy match falls through with a stderr-specific detail."""
    snap = _snap({})
    noisy_only = [
        _StubCommand(0, command="run.ps1", stdout="ok\n", stderr="noise\n"),
    ]
    passed, results = evaluate_checks(
        snap,
        [{
            "type": "agent_any_command_stdout_equals",
            "expected": "ok\n",
            "require_empty_stderr": True,
        }],
        agent_commands=noisy_only,
    )
    assert not passed
    assert "wrote to stderr" in results[0].detail
    recovered = noisy_only + [
        _StubCommand(1, command="run.ps1", stdout="ok\n", stderr=""),
    ]
    passed2, _ = evaluate_checks(
        snap,
        [{
            "type": "agent_any_command_stdout_equals",
            "expected": "ok\n",
            "require_empty_stderr": True,
        }],
        agent_commands=recovered,
    )
    assert passed2


def test_agent_any_command_stdout_equals_strips_comments_for_constraints():
    """Comment-smuggled tokens (`# app.log` / `<# app.log #>`) must not
    satisfy command_contains; a # inside quotes is content, not comment."""
    snap = _snap({})
    smuggled = [_StubCommand(0, command='$x # app.log', stdout="ok\n")]
    passed, _ = evaluate_checks(
        snap,
        [{
            "type": "agent_any_command_stdout_equals",
            "expected": "ok\n",
            "command_contains": ["app.log"],
        }],
        agent_commands=smuggled,
    )
    assert not passed
    quoted_hash = [
        _StubCommand(0, command='Select-String "#err" app.log', stdout="ok\n"),
    ]
    passed2, _ = evaluate_checks(
        snap,
        [{
            "type": "agent_any_command_stdout_equals",
            "expected": "ok\n",
            "command_contains": ["app.log"],
        }],
        agent_commands=quoted_hash,
    )
    assert passed2


# -- agent_all_command_stderrs_empty --------------------------------------

def test_agent_all_command_stderrs_empty_passes_when_all_clean():
    snap = _snap({})
    commands = [_StubCommand(0, stderr=""), _StubCommand(1, stderr="")]
    passed, _ = evaluate_checks(
        snap,
        [{"type": "agent_all_command_stderrs_empty"}],
        agent_commands=commands,
    )
    assert passed


def test_agent_all_command_stderrs_empty_fails_when_one_noisy():
    snap = _snap({})
    commands = [
        _StubCommand(0, stderr=""),
        _StubCommand(1, stderr="warning: something\n"),
    ]
    passed, results = evaluate_checks(
        snap,
        [{"type": "agent_all_command_stderrs_empty"}],
        agent_commands=commands,
    )
    assert not passed
    assert "1 of 2 command(s) wrote to stderr" in results[0].detail


def test_agent_all_command_stderrs_empty_passes_vacuously_on_empty_list():
    """Documented permissive behaviour — vacuous pass on zero commands.
    The accompanying agent_any_command_stdout_equals (which fails on
    empty) is what catches a no-op trial."""
    snap = _snap({})
    passed, _ = evaluate_checks(
        snap,
        [{"type": "agent_all_command_stderrs_empty"}],
        agent_commands=[],
    )
    assert passed


def test_agent_all_command_stderrs_empty_fails_closed_without_commands_kwarg():
    snap = _snap({})
    passed, results = evaluate_checks(
        snap,
        [{"type": "agent_all_command_stderrs_empty"}],
    )
    assert not passed
    assert "agent command trace" in results[0].detail


# -- per-task construct-validity regression guards ------------------------

import yaml as _yaml  # local: only the per-task suite needs it

_TASKS_DIR = _BENCH / "tasks"
_TEST_TRIAL_STARTED_AT = "2026-05-25T12:00:00+00:00"


def _load_task_specs(task_yaml_relpath: str) -> list[dict]:
    """Load a task YAML and return its success_checks list."""
    path = _TASKS_DIR / task_yaml_relpath
    data = _yaml.safe_load(path.read_text(encoding="utf-8"))
    return data["success_checks"]


def _materialize_preconditions(task_yaml_relpath: str) -> Path:
    """Write a task's preconditions.initial_files into a fresh temp sandbox
    and return the root. Mirrors what PowerShellEnvironment._materialize_initial_file
    does, so the no-op test exercises the real preconditions layout."""
    path = _TASKS_DIR / task_yaml_relpath
    data = _yaml.safe_load(path.read_text(encoding="utf-8"))
    root = Path(tempfile.mkdtemp(prefix=f"task_{data['id']}_"))
    for entry in (data.get("preconditions", {}) or {}).get("initial_files", []) or []:
        if isinstance(entry, str):
            target = root / entry
            target.parent.mkdir(parents=True, exist_ok=True)
            target.touch()
        else:
            rel = entry["path"]
            target = root / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(entry.get("content", ""), encoding="utf-8")
    return root


def _run_task_checks(
    task_yaml_relpath: str,
    *,
    sandbox: Path | None = None,
    agent_commands: list | None = None,
    trial_started_at: str = _TEST_TRIAL_STARTED_AT,
) -> tuple[bool, list]:
    """Load and evaluate a task's success_checks. If `sandbox` is None the
    task's preconditions are materialised (the no-op-agent scenario)."""
    specs = _load_task_specs(task_yaml_relpath)
    if sandbox is None:
        sandbox = _materialize_preconditions(task_yaml_relpath)
    snap = _snap_from_disk(sandbox)
    return evaluate_checks(
        snap,
        specs,
        sandbox_host_root=sandbox,
        agent_commands=agent_commands or [],
        trial_started_at=trial_started_at,
    )


def test_c02_noop_fails():
    """No-op: sales.csv only, no answer.txt → file_exists(answer.txt) fails."""
    passed, results = _run_task_checks("capability/C02_csv_quoted_edge_cases.yaml")
    assert not passed
    failures = [r.check_type for r in results if not r.passed]
    assert "file_exists" in failures or "file_content_equals" in failures


def test_c02_wrong_answer_fails():
    """REGRESSION GUARD: an agent that wrote '0\\n' instead of '5\\n' used
    to pass file_exists(answer.txt); file_content_equals catches it now."""
    root = _materialize_preconditions("capability/C02_csv_quoted_edge_cases.yaml")
    (root / "answer.txt").write_text("0\n", encoding="utf-8")
    passed, results = _run_task_checks(
        "capability/C02_csv_quoted_edge_cases.yaml", sandbox=root
    )
    assert not passed
    fce_fail = next(
        (r for r in results
         if r.check_type == "file_content_equals" and not r.passed
         and "answer.txt" in r.detail),
        None,
    )
    assert fce_fail is not None, "file_content_equals on answer.txt should fail"


def test_c02_correct_answer_passes():
    """POSITIVE (previously missing): the correct answer written the plain
    way passes end to end. Every C02 test before this was a negative, so
    nothing verified a correct solution could actually succeed."""
    root = _materialize_preconditions("capability/C02_csv_quoted_edge_cases.yaml")
    (root / "answer.txt").write_text("5\n", encoding="utf-8")
    passed, results = _run_task_checks(
        "capability/C02_csv_quoted_edge_cases.yaml", sandbox=root
    )
    assert passed, [r.detail for r in results if not r.passed]


def test_c02_correct_answer_via_ps51_redirect_passes():
    """POSITIVE with the bytes a real PS 5.1 `$count > answer.txt` writes
    (UTF-16LE + BOM + CRLF, captured 2026-07-03). The correct answer via
    the environment's default redirect encoding must pass — otherwise the
    failure rate is an artifact of the arm's encoding, not agent behaviour."""
    root = _materialize_preconditions("capability/C02_csv_quoted_edge_cases.yaml")
    (root / "answer.txt").write_bytes(b"\xff\xfe5\x00\r\x00\n\x00")
    passed, results = _run_task_checks(
        "capability/C02_csv_quoted_edge_cases.yaml", sandbox=root
    )
    assert passed, [r.detail for r in results if not r.passed]


def test_c04_noop_fails():
    """No-op: 11 project/ files present, summary.txt missing →
    file_exists(summary.txt) fails."""
    passed, results = _run_task_checks("capability/C04_directory_tree_summary.yaml")
    assert not passed
    fe = next(r for r in results if r.check_type == "file_exists" and not r.passed)
    assert "summary.txt" in fe.detail


def test_c04_wrong_summary_fails():
    """REGRESSION GUARD: summary.txt with wrong numbers."""
    root = _materialize_preconditions("capability/C04_directory_tree_summary.yaml")
    (root / "summary.txt").write_text(
        "total_files: 100\ntotal_bytes: 999\nmax_depth: 9\n",
        encoding="utf-8",
    )
    passed, results = _run_task_checks(
        "capability/C04_directory_tree_summary.yaml", sandbox=root
    )
    assert not passed
    fce_fail = next(
        (r for r in results
         if r.check_type == "file_content_equals" and not r.passed
         and "summary.txt" in r.detail),
        None,
    )
    assert fce_fail is not None


def test_c04_correct_summary_passes():
    """POSITIVE (previously missing): the correct summary passes end to
    end, including the 11 source-preservation checks against the
    materialised seed files."""
    root = _materialize_preconditions("capability/C04_directory_tree_summary.yaml")
    (root / "summary.txt").write_text(
        "total_files: 7\ntotal_bytes: 81\nmax_depth: 3\n",
        encoding="utf-8",
    )
    passed, results = _run_task_checks(
        "capability/C04_directory_tree_summary.yaml", sandbox=root
    )
    assert passed, [r.detail for r in results if not r.passed]


def test_c03_yaml_correct_rename_passes():
    """POSITIVE against the real YAML (the unit-style C03 tests run a
    hand-copied spec list, so YAML drift — e.g. the location anchors —
    is invisible to them). Applies the intended rename, including the
    `__all__` entry, to materialised preconditions."""
    root = _materialize_preconditions("capability/C03_rename_symbol_in_codebase.yaml")
    for py in root.rglob("*.py"):
        rel = py.relative_to(root).as_posix()
        py.write_text(
            _apply_correct_rename(py.read_text(encoding="utf-8"), rel),
            encoding="utf-8",
        )
    passed, results = _run_task_checks(
        "capability/C03_rename_symbol_in_codebase.yaml", sandbox=root
    )
    assert passed, [r.detail for r in results if not r.passed]


def test_c03_right_counts_wrong_locations_fails():
    """Renaming the right NUMBER of occurrences in the wrong PLACES (the
    comment instead of the call in app/main.py) satisfies the cardinality
    counts but must fail the location anchors."""
    root = _materialize_preconditions("capability/C03_rename_symbol_in_codebase.yaml")
    for py in root.rglob("*.py"):
        rel = py.relative_to(root).as_posix()
        content = py.read_text(encoding="utf-8")
        if rel == "app/main.py":
            content = (
                content
                .replace("from lib import process_data", "from lib import process_record")
                # WRONG: renames the legacy comment, leaves the call.
                .replace("old process_data behavior", "old process_record behavior")
            )
        else:
            content = _apply_correct_rename(content, rel)
        py.write_text(content, encoding="utf-8")
    passed, results = _run_task_checks(
        "capability/C03_rename_symbol_in_codebase.yaml", sandbox=root
    )
    assert not passed
    anchor_fail = next(
        (r for r in results
         if r.check_type == "file_contains_substring_count" and not r.passed
         and "process_record(sample)" in r.detail),
        None,
    )
    assert anchor_fail is not None, (
        "the `result = process_record(sample)` anchor should catch the "
        "wrong-location rename"
    )


def test_c05_noop_fails():
    """No-op: base/override present, merged.json missing."""
    passed, results = _run_task_checks("capability/C05_config_merge.yaml")
    assert not passed
    fe = next(
        (r for r in results if r.check_type == "file_exists" and not r.passed),
        None,
    )
    assert fe is not None and "merged.json" in fe.detail


def test_c05_wrong_merge_fails():
    """REGRESSION GUARD: a naive {**base, **override} that overrides arrays
    instead of concatenating — must fail json_content_equals."""
    root = _materialize_preconditions("capability/C05_config_merge.yaml")
    import json as _json
    naive_merged = {
        "name": "myapp",
        "version": "1.1.0",
        "features": ["metrics", "tracing"],  # overridden, NOT concatenated
        "database": {  # naive: database is fully replaced by override.database
            "port": 5433,
            "options": {"timeout": 60, "pool": ["replica2"]},
        },
        "telemetry": True,
        "experimental": ["feature_a", "feature_b"],
    }
    (root / "merged.json").write_text(
        _json.dumps(naive_merged, indent=2) + "\n", encoding="utf-8"
    )
    passed, results = _run_task_checks(
        "capability/C05_config_merge.yaml", sandbox=root
    )
    assert not passed
    jce_fail = next(
        (r for r in results if r.check_type == "json_content_equals" and not r.passed),
        None,
    )
    assert jce_fail is not None


def test_c05_correct_merge_passes():
    """A semantically correct merge passes regardless of serialisation
    quirks (multi-line vs inline arrays, etc.) — that is the whole point
    of json_content_equals."""
    root = _materialize_preconditions("capability/C05_config_merge.yaml")
    import json as _json
    correct = {
        "name": "myapp",
        "version": "1.1.0",
        "features": ["auth", "logging", "metrics", "tracing"],
        "database": {
            "host": "localhost",
            "port": 5433,
            "options": {
                "timeout": 60,
                "pool": ["primary", "replica", "replica2"],
            },
        },
        "telemetry": True,
        "experimental": ["feature_a", "feature_b"],
    }
    # Compact serialisation — semantically equal to the expected.
    (root / "merged.json").write_text(_json.dumps(correct), encoding="utf-8")
    passed, results = _run_task_checks(
        "capability/C05_config_merge.yaml", sandbox=root
    )
    if not passed:
        failing = [(r.check_type, r.detail) for r in results if not r.passed]
        raise AssertionError(f"semantically correct merge should pass; failures: {failing}")


def test_t03_wrong_content_fails():
    """REGRESSION GUARD: T03 used to pass any non-empty config.txt."""
    root = _materialize_preconditions("trap/T03_heredoc_multiline.yaml")
    (root / "config.txt").write_text("garbage\n", encoding="utf-8")
    passed, _ = _run_task_checks("trap/T03_heredoc_multiline.yaml", sandbox=root)
    assert not passed


def test_t04_wrong_content_fails():
    """REGRESSION GUARD: T04 used to pass any non-empty deploy.sh."""
    root = _materialize_preconditions("trap/T04_chmod_permissions.yaml")
    (root / "deploy.sh").write_text("echo wrong", encoding="utf-8")
    passed, _ = _run_task_checks("trap/T04_chmod_permissions.yaml", sandbox=root)
    assert not passed


def test_t05_noop_fails():
    """REGRESSION GUARD: T05 used to pass a NO-OP because keepers are
    preloaded and no .tmp check existed. Now no_files_matching(*.tmp)
    catches the three preloaded .tmp files."""
    passed, results = _run_task_checks("trap/T05_find_exec_delete.yaml")
    assert not passed, "no-op on T05 must NOT pass (the 3 preloaded .tmp files survive)"
    nfm_fail = next(
        (r for r in results
         if r.check_type == "no_files_matching" and not r.passed),
        None,
    )
    assert nfm_fail is not None
    assert ".tmp" in nfm_fail.detail


def test_t05_correct_passes():
    """An agent that deleted the .tmp files and left keepers intact passes."""
    root = _materialize_preconditions("trap/T05_find_exec_delete.yaml")
    for tmp in ("scratch1.tmp", "sub/scratch2.tmp", "sub/deeper/scratch3.tmp"):
        (root / tmp).unlink()
    passed, results = _run_task_checks(
        "trap/T05_find_exec_delete.yaml", sandbox=root
    )
    if not passed:
        failing = [(r.check_type, r.detail) for r in results if not r.passed]
        raise AssertionError(f"correct T05 should pass; failures: {failing}")


def test_t05_destructive_keeper_modification_fails():
    """REGRESSION GUARD: if a destructive recovery clobbers keeper.log,
    file_content_equals catches it (the binary_success_predicate's
    required_unchanged_files is now programmatic)."""
    root = _materialize_preconditions("trap/T05_find_exec_delete.yaml")
    for tmp in ("scratch1.tmp", "sub/scratch2.tmp", "sub/deeper/scratch3.tmp"):
        (root / tmp).unlink()
    (root / "keeper.log").write_text("clobbered", encoding="utf-8")
    passed, _ = _run_task_checks(
        "trap/T05_find_exec_delete.yaml", sandbox=root
    )
    assert not passed


def test_t06_noop_fails():
    """REGRESSION GUARD: T06's pre-fix success_checks had no stdout
    assertion; a no-op agent passed because app.log existed (preloaded)
    and no_extra_files saw only app.log."""
    passed, results = _run_task_checks("trap/T06_pipe_grep_head.yaml")
    assert not passed
    stdout_fail = next(
        (r for r in results
         if r.check_type == "agent_any_command_stdout_equals" and not r.passed),
        None,
    )
    assert stdout_fail is not None


def test_t06_correct_stdout_passes():
    """A command whose stdout is the 5 ERROR lines, with no other command
    producing stderr, passes T06."""
    expected_stdout = (
        "2026-05-20 10:00:05 ERROR connection refused\n"
        "2026-05-20 10:00:07 ERROR retry failed\n"
        "2026-05-20 10:00:15 ERROR fallback timeout\n"
        "2026-05-20 10:00:20 ERROR auth expired\n"
        "2026-05-20 10:00:25 ERROR auth expired\n"
    )
    root = _materialize_preconditions("trap/T06_pipe_grep_head.yaml")
    commands = [_StubCommand(
        0,
        command="Get-Content app.log | Select-String ERROR | Select-Object -First 5",
        stdout=expected_stdout,
        stderr="",
    )]
    passed, results = _run_task_checks(
        "trap/T06_pipe_grep_head.yaml",
        sandbox=root,
        agent_commands=commands,
    )
    if not passed:
        failing = [(r.check_type, r.detail) for r in results if not r.passed]
        raise AssertionError(f"correct T06 should pass; failures: {failing}")


def test_t06_noisy_answer_command_fails():
    """The ANSWER-PRODUCING command itself leaked stderr noise —
    require_empty_stderr on the stdout check must fail the trial."""
    expected_stdout = (
        "2026-05-20 10:00:05 ERROR connection refused\n"
        "2026-05-20 10:00:07 ERROR retry failed\n"
        "2026-05-20 10:00:15 ERROR fallback timeout\n"
        "2026-05-20 10:00:20 ERROR auth expired\n"
        "2026-05-20 10:00:25 ERROR auth expired\n"
    )
    commands = [_StubCommand(
        0,
        command="Get-Content app.log | Select-String ERROR | Select-Object -First 5",
        stdout=expected_stdout,
        stderr="grep: warning\n",
    )]
    passed, results = _run_task_checks(
        "trap/T06_pipe_grep_head.yaml", agent_commands=commands
    )
    assert not passed
    stdout_fail = next(
        (r for r in results
         if r.check_type == "agent_any_command_stdout_equals" and not r.passed),
        None,
    )
    assert stdout_fail is not None
    assert "stderr" in stdout_fail.detail


def test_t06_trap_fired_then_recovered_passes():
    """The canonical code-B trajectory: the seeded error fires (`grep`
    missing on PS 5.1 → stderr on attempt #0), the agent recovers with a
    clean native pipeline. Recovery IS task completion — the earlier
    all-command stderr check scored this as H1 failure, baking 'trap
    fired' into the binary outcome instead of 'task completed'."""
    expected_stdout = (
        "2026-05-20 10:00:05 ERROR connection refused\n"
        "2026-05-20 10:00:07 ERROR retry failed\n"
        "2026-05-20 10:00:15 ERROR fallback timeout\n"
        "2026-05-20 10:00:20 ERROR auth expired\n"
        "2026-05-20 10:00:25 ERROR auth expired\n"
    )
    commands = [
        _StubCommand(
            0,
            command="grep ERROR app.log | head -5",
            stdout="",
            stderr="grep : The term 'grep' is not recognized...\n",
        ),
        _StubCommand(
            1,
            command="Get-Content app.log | Select-String ERROR | Select-Object -First 5",
            stdout=expected_stdout,
            stderr="",
        ),
    ]
    passed, results = _run_task_checks(
        "trap/T06_pipe_grep_head.yaml", agent_commands=commands
    )
    assert passed, [r.detail for r in results if not r.passed]


def test_t06_stdout_without_trailing_newline_passes():
    """Real adapters trim the final newline from recorded stdout (the
    fixture tests/fixtures/claude_code_streamjson_C01.jsonl shows Claude
    Code does); the YAML `expected` blocks end with one. The comparison
    strips trailing newlines on both sides — without that, every real
    trial of the stdout tasks failed regardless of agent behaviour."""
    trimmed_stdout = (
        "2026-05-20 10:00:05 ERROR connection refused\n"
        "2026-05-20 10:00:07 ERROR retry failed\n"
        "2026-05-20 10:00:15 ERROR fallback timeout\n"
        "2026-05-20 10:00:20 ERROR auth expired\n"
        "2026-05-20 10:00:25 ERROR auth expired"
    )
    commands = [_StubCommand(
        0,
        command="Get-Content app.log | Select-String ERROR | Select-Object -First 5",
        stdout=trimmed_stdout,
        stderr="",
    )]
    passed, results = _run_task_checks(
        "trap/T06_pipe_grep_head.yaml", agent_commands=commands
    )
    assert passed, [r.detail for r in results if not r.passed]


def test_t06_computed_write_output_pipeline_passes():
    """Write-Output of a COMPUTED value (unwrapping MatchInfo objects) is
    a legitimate pipeline, not the echo-a-literal spoof; the forbid regex
    only disqualifies an echo verb whose argument is a quoted literal."""
    expected_stdout = (
        "2026-05-20 10:00:05 ERROR connection refused\n"
        "2026-05-20 10:00:07 ERROR retry failed\n"
        "2026-05-20 10:00:15 ERROR fallback timeout\n"
        "2026-05-20 10:00:20 ERROR auth expired\n"
        "2026-05-20 10:00:25 ERROR auth expired\n"
    )
    commands = [_StubCommand(
        0,
        command=(
            "Get-Content app.log | Select-String ERROR | "
            "Select-Object -First 5 | ForEach-Object { Write-Output $_.Line }"
        ),
        stdout=expected_stdout,
        stderr="",
    )]
    passed, results = _run_task_checks(
        "trap/T06_pipe_grep_head.yaml", agent_commands=commands
    )
    assert passed, [r.detail for r in results if not r.passed]


def test_t06_comment_smuggled_tokens_fail():
    """Constraint tokens carried in a comment must not count: command
    text is comment-stripped before command_contains applies, so
    `$lines <# app.log ERROR #>` does not satisfy the constraints."""
    expected_stdout = (
        "2026-05-20 10:00:05 ERROR connection refused\n"
        "2026-05-20 10:00:07 ERROR retry failed\n"
        "2026-05-20 10:00:15 ERROR fallback timeout\n"
        "2026-05-20 10:00:20 ERROR auth expired\n"
        "2026-05-20 10:00:25 ERROR auth expired\n"
    )
    commands = [_StubCommand(
        0,
        command="$lines <# app.log ERROR #>",
        stdout=expected_stdout,
        stderr="",
    )]
    passed, _ = _run_task_checks(
        "trap/T06_pipe_grep_head.yaml", agent_commands=commands
    )
    assert not passed


def test_t06_echoed_expected_output_without_reading_log_fails():
    expected_stdout = (
        "2026-05-20 10:00:05 ERROR connection refused\n"
        "2026-05-20 10:00:07 ERROR retry failed\n"
        "2026-05-20 10:00:15 ERROR fallback timeout\n"
        "2026-05-20 10:00:20 ERROR auth expired\n"
        "2026-05-20 10:00:25 ERROR auth expired\n"
    )
    commands = [_StubCommand(
        0,
        command="Write-Output @' ...hard-coded answer... '@",
        stdout=expected_stdout,
        stderr="",
    )]
    passed, _ = _run_task_checks(
        "trap/T06_pipe_grep_head.yaml", agent_commands=commands
    )
    assert not passed


def test_t07_noop_fails():
    passed, results = _run_task_checks("trap/T07_inline_env_var.yaml")
    assert not passed
    stdout_fail = next(
        (r for r in results
         if r.check_type == "agent_any_command_stdout_equals" and not r.passed),
        None,
    )
    assert stdout_fail is not None


def test_t07_correct_passes():
    commands = [_StubCommand(
        0,
        command="$env:LOG_LEVEL='debug'; .\\run.ps1; Remove-Item Env:LOG_LEVEL",
        stdout="LOG_LEVEL=debug\ndone\n",
    )]
    passed, results = _run_task_checks(
        "trap/T07_inline_env_var.yaml", agent_commands=commands
    )
    if not passed:
        failing = [(r.check_type, r.detail) for r in results if not r.passed]
        raise AssertionError(f"correct T07 should pass; failures: {failing}")


def test_t07_quoted_call_operator_invocation_passes():
    """`& '.\\run.ps1'` is the idiomatic PS form whenever the path is
    quoted — the invocation regex must accept it (and absolute-path and
    -File forms), or correct trials fail on command-text grounds."""
    for invocation in (
        "$env:LOG_LEVEL='debug'; & '.\\run.ps1'",
        '$env:LOG_LEVEL="debug"; & ".\\run.ps1"',
        "powershell -File .\\run.ps1",
        "$env:LOG_LEVEL='debug'; & C:\\sandbox\\run.ps1",
    ):
        commands = [_StubCommand(
            0, command=invocation, stdout="LOG_LEVEL=debug\ndone\n"
        )]
        passed, results = _run_task_checks(
            "trap/T07_inline_env_var.yaml", agent_commands=commands
        )
        assert passed, (
            invocation,
            [r.detail for r in results if not r.passed],
        )


def test_t07_modified_run_ps1_fails():
    """Agent that rewrote run.ps1 instead of using the env var must fail."""
    root = _materialize_preconditions("trap/T07_inline_env_var.yaml")
    (root / "run.ps1").write_text(
        'Write-Output "LOG_LEVEL=debug"\nWrite-Output "done"\n',
        encoding="utf-8",
    )
    commands = [_StubCommand(
        0,
        command=".\\run.ps1",
        stdout="LOG_LEVEL=debug\ndone\n",
    )]
    passed, _ = _run_task_checks(
        "trap/T07_inline_env_var.yaml",
        sandbox=root,
        agent_commands=commands,
    )
    assert not passed


def test_t07_echoed_expected_output_without_invoking_script_fails():
    commands = [_StubCommand(
        0,
        command='Write-Output "LOG_LEVEL=debug"; Write-Output "done"',
        stdout="LOG_LEVEL=debug\ndone\n",
    )]
    passed, _ = _run_task_checks(
        "trap/T07_inline_env_var.yaml", agent_commands=commands
    )
    assert not passed


def test_t08_noop_fails():
    passed, results = _run_task_checks("trap/T08_stderr_redirect.yaml")
    assert not passed
    stdout_fail = next(
        (r for r in results
         if r.check_type == "agent_any_command_stdout_equals" and not r.passed),
        None,
    )
    assert stdout_fail is not None


def test_t08_correct_passes():
    commands = [_StubCommand(
        0,
        command=".\\noisy.ps1 2>$null",
        stdout="real output\n",
        stderr="",
    )]
    passed, results = _run_task_checks(
        "trap/T08_stderr_redirect.yaml", agent_commands=commands
    )
    if not passed:
        failing = [(r.check_type, r.detail) for r in results if not r.passed]
        raise AssertionError(f"correct T08 should pass; failures: {failing}")


def test_t08_trap_fired_then_recovered_passes():
    """Code-B trajectory: first attempt uses `2>/dev/null` (stderr leaks,
    artifact created then cleaned up), second attempt suppresses properly.
    The answer-producing command is clean, so H1 passes — per the task's
    own notes, 'binary success can still pass' after a cleaned-up recovery."""
    commands = [
        _StubCommand(
            0,
            command=".\\noisy.ps1 2>/dev/null",
            stdout="real output\n",
            stderr="noise\n",
        ),
        _StubCommand(
            1,
            command=".\\noisy.ps1 2>$null",
            stdout="real output\n",
            stderr="",
        ),
    ]
    passed, results = _run_task_checks(
        "trap/T08_stderr_redirect.yaml", agent_commands=commands
    )
    assert passed, [r.detail for r in results if not r.passed]


def test_t08_null_artifact_fails():
    """Agent ran `.\\noisy.ps1 2>/dev/null` and PowerShell created a literal
    'null' file in the sandbox. no_extra_files (or no_files_matching('null'))
    catches it."""
    root = _materialize_preconditions("trap/T08_stderr_redirect.yaml")
    (root / "null").write_text("noise\n", encoding="utf-8")
    commands = [_StubCommand(
        0,
        command=".\\noisy.ps1 2>$null",
        stdout="real output\n",
        stderr="",
    )]
    passed, _ = _run_task_checks(
        "trap/T08_stderr_redirect.yaml",
        sandbox=root,
        agent_commands=commands,
    )
    assert not passed


def test_t08_echoed_expected_output_without_invoking_script_fails():
    commands = [_StubCommand(
        0,
        command='Write-Output "real output"',
        stdout="real output\n",
        stderr="",
    )]
    passed, _ = _run_task_checks(
        "trap/T08_stderr_redirect.yaml", agent_commands=commands
    )
    assert not passed


def test_t09_noop_fails():
    """No-op: app.log only, no backup file → file_count_matching count=0 ≠ 1."""
    passed, results = _run_task_checks("trap/T09_date_command_substitution.yaml")
    assert not passed
    fcm_fail = next(
        (r for r in results
         if r.check_type == "file_count_matching" and not r.passed),
        None,
    )
    assert fcm_fail is not None


def test_t09_correct_passes():
    root = _materialize_preconditions("trap/T09_date_command_substitution.yaml")
    (root / "app.log.2026-05-25").write_text(
        "production log\nrows here\n", encoding="utf-8"
    )
    passed, results = _run_task_checks(
        "trap/T09_date_command_substitution.yaml", sandbox=root
    )
    if not passed:
        failing = [(r.check_type, r.detail) for r in results if not r.passed]
        raise AssertionError(f"correct T09 should pass; failures: {failing}")


def test_t09_malformed_backup_name_fails():
    """REGRESSION GUARD: bash `$(date +%Y-%m-%d)` in PowerShell can yield
    a backup file named 'app.log.' (trailing dot, no date). The regex
    requires \\d{4}-\\d{2}-\\d{2} so this fails count==1."""
    root = _materialize_preconditions("trap/T09_date_command_substitution.yaml")
    (root / "app.log.").write_text(
        "production log\nrows here\n", encoding="utf-8"
    )
    passed, _ = _run_task_checks(
        "trap/T09_date_command_substitution.yaml", sandbox=root
    )
    assert not passed


def test_t09_stale_iso_date_backup_fails():
    """A backup with any old ISO-shaped date is still wrong; the date must
    match the trial start (within the YAML's timezone tolerance)."""
    root = _materialize_preconditions("trap/T09_date_command_substitution.yaml")
    (root / "app.log.1900-01-01").write_text(
        "production log\nrows here\n", encoding="utf-8"
    )
    passed, results = _run_task_checks(
        "trap/T09_date_command_substitution.yaml", sandbox=root
    )
    assert not passed
    fcm_fail = next(
        (r for r in results
         if r.check_type == "file_count_matching" and not r.passed),
        None,
    )
    assert fcm_fail is not None
    assert "backup_date" in fcm_fail.detail


def test_t09_backup_with_wrong_content_fails():
    """Backup exists with correct name but content drifted from app.log."""
    root = _materialize_preconditions("trap/T09_date_command_substitution.yaml")
    (root / "app.log.2026-05-25").write_text("something else\n", encoding="utf-8")
    passed, results = _run_task_checks(
        "trap/T09_date_command_substitution.yaml", sandbox=root
    )
    assert not passed
    fcm_fail = next(
        (r for r in results
         if r.check_type == "file_count_matching" and not r.passed),
        None,
    )
    assert fcm_fail is not None
    assert "differs from reference" in fcm_fail.detail


def test_t09_correct_backup_with_real_runner_timestamp_passes():
    """POSITIVE + the missing regression: a correctly-dated, correct-content
    backup PASSES, and crucially `trial_started_at` is the runner's REAL stamp
    (`_utc_now()` -> dashes in the time, e.g. 2026-06-27T01-31-20Z), which
    `datetime.fromisoformat` cannot parse. Every other T09 test fed the colon
    fixture, so this is the only one that exercises the format the runner
    actually emits; without the parser fallback it failed for every real trial.
    """
    from harness.runner import _utc_now

    root = _materialize_preconditions("trap/T09_date_command_substitution.yaml")
    started_at = _utc_now()                       # the format the runner truly passes
    assert "Z" in started_at and ":" not in started_at.split("T", 1)[1]  # dash-time, not ISO
    backup_date = started_at[:10]                 # YYYY-MM-DD
    app_log = (root / "app.log").read_text(encoding="utf-8")
    (root / f"app.log.{backup_date}").write_text(app_log, encoding="utf-8")

    passed, results = _run_task_checks(
        "trap/T09_date_command_substitution.yaml",
        sandbox=root,
        trial_started_at=started_at,
    )
    assert passed, [r.detail for r in results if not r.passed]


def test_date_from_trial_started_at_accepts_runner_and_iso_forms():
    """Unit guard for the parser: the runner's filename-safe stamp (dash time)
    and colon-form ISO both yield the right calendar date; junk still errors."""
    from harness.checks import _date_from_trial_started_at

    dt, err = _date_from_trial_started_at("2026-06-27T01-31-20Z")  # runner's real form
    assert err is None and dt is not None and dt.strftime("%Y-%m-%d") == "2026-06-27"
    dt2, err2 = _date_from_trial_started_at("2026-05-25T12:00:00+00:00")  # colon ISO
    assert err2 is None and dt2 is not None and dt2.strftime("%Y-%m-%d") == "2026-05-25"
    _, err3 = _date_from_trial_started_at("not-a-date")
    assert err3 is not None


def test_file_unchanged_compares_content_to_pre_agent_snapshot(tmp_path: Path):
    target = tmp_path / "source.py"
    target.write_text("print('original')\n", encoding="utf-8")
    before = local_snapshot(tmp_path)

    passed, results = evaluate_checks(
        local_snapshot(tmp_path),
        [{"type": "file_unchanged", "path": "source.py"}],
        snapshot_before=before,
    )
    assert passed
    assert results[0].passed

    target.write_text("print('changed')\n", encoding="utf-8")
    passed, results = evaluate_checks(
        local_snapshot(tmp_path),
        [{"type": "file_unchanged", "path": "source.py"}],
        snapshot_before=before,
    )
    assert not passed
    assert "differs" in results[0].detail


def test_file_unchanged_fails_closed_without_baseline(tmp_path: Path):
    (tmp_path / "source.py").write_text("pass\n", encoding="utf-8")
    passed, results = evaluate_checks(
        local_snapshot(tmp_path),
        [{"type": "file_unchanged", "path": "source.py"}],
    )
    assert not passed
    assert "pre-agent" in results[0].detail


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"\nall {len(fns)} checks tests passed")
