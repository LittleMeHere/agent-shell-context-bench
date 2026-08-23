from __future__ import annotations

from pathlib import Path

from harness.environments.powershell import _resolve_windows_executable


def test_prefers_createprocess_extension_over_extensionless_npm_shim(
    tmp_path: Path,
) -> None:
    (tmp_path / "codex").write_text("#!/bin/sh\n", encoding="utf-8")
    cmd = tmp_path / "codex.cmd"
    cmd.write_text("@echo off\n", encoding="utf-8")

    resolved = _resolve_windows_executable(
        "codex",
        search_dirs=[str(tmp_path)],
        pathext=".COM;.EXE;.BAT;.CMD",
    )

    assert resolved == str(cmd)


def test_honors_pathext_precedence(tmp_path: Path) -> None:
    exe = tmp_path / "tool.exe"
    cmd = tmp_path / "tool.cmd"
    exe.write_bytes(b"MZ")
    cmd.write_text("@echo off\n", encoding="utf-8")

    resolved = _resolve_windows_executable(
        "tool",
        search_dirs=[str(tmp_path)],
        pathext=".CMD;.EXE",
    )

    assert resolved == str(cmd)


def test_honors_path_precedence_before_extension_precedence(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()
    preferred = first / "tool.cmd"
    preferred.write_text("@echo off\n", encoding="utf-8")
    (second / "tool.exe").write_bytes(b"MZ")

    resolved = _resolve_windows_executable(
        "tool",
        search_dirs=[str(first), str(second)],
        pathext=".EXE;.CMD",
    )

    assert resolved == str(preferred)


def test_explicit_createprocess_compatible_path_is_unchanged(tmp_path: Path) -> None:
    command = str(tmp_path / "custom.exe")
    assert _resolve_windows_executable(command, search_dirs=[]) == command


def test_explicit_extensionless_path_uses_sibling_cmd(tmp_path: Path) -> None:
    raw = tmp_path / "codex"
    raw.write_text("#!/bin/sh\n", encoding="utf-8")
    cmd = tmp_path / "codex.cmd"
    cmd.write_text("@echo off\n", encoding="utf-8")

    resolved = _resolve_windows_executable(
        str(raw),
        search_dirs=[],
        pathext=".EXE;.CMD",
    )

    assert resolved == str(cmd)


def test_missing_command_remains_visible_for_normal_failure() -> None:
    assert (
        _resolve_windows_executable(
            "missing-tool", search_dirs=[], pathext=".EXE;.CMD"
        )
        == "missing-tool"
    )
