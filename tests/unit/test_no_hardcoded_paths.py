"""Regression tests for the portable-path guard."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

CHECKER = Path(__file__).parents[2] / "scripts" / "check_no_hardcoded_paths.py"


def _make_repo(tmp_path: Path, content: str) -> Path:
    """Create a minimal scan target that includes the checker itself."""
    for directory in (
        ".github",
        "src",
        "configs",
        "scripts",
        "docs",
        "tests",
        "workflow",
        "containers",
        "reports",
    ):
        (tmp_path / directory).mkdir()
    (tmp_path / "src" / "example.py").write_text(content, encoding="utf-8")
    shutil.copy2(CHECKER, tmp_path / "scripts" / CHECKER.name)
    return tmp_path


def _run_checker(root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(root / "scripts" / CHECKER.name), "--root", str(root)],
        capture_output=True,
        check=False,
        text=True,
    )


def test_accepts_generic_path_placeholders_and_ignores_its_own_regex(tmp_path: Path) -> None:
    placeholders = (
        'windows_backslash = "C:' + "\\\\Us" + 'ers\\\\<user>\\\\artifacts"\n'
        'windows_slash = "C:' + "/Us" + 'ers/<username>/artifacts"\n'
        'linux = "/ho' + 'me/<user>/artifacts"\n'
        'macos = "/Us' + 'ers/${USER}/artifacts"\n'
    )
    root = _make_repo(tmp_path, placeholders)
    (root / "docs" / "project_design.md").write_text(placeholders, encoding="utf-8")
    (root / "docs" / "implementation_plan.md").write_text(placeholders, encoding="utf-8")

    result = _run_checker(root)

    assert result.returncode == 0, result.stdout + result.stderr


def test_rejects_windows_user_absolute_path_with_nonzero_exit(tmp_path: Path) -> None:
    hardcoded_path = 'output_dir = "C:' + "\\\\Us" + 'ers\\\\researcher\\\\artifacts"\n'
    root = _make_repo(tmp_path, hardcoded_path)

    result = _run_checker(root)

    assert result.returncode == 1
    assert "src/example.py" in result.stdout.replace("\\", "/")


def test_rejects_unix_and_macos_user_absolute_paths(tmp_path: Path) -> None:
    hardcoded_paths = 'linux = "/ho' + 'me/researcher/run"\nmac = "/Us' + 'ers/researcher/run"\n'
    root = _make_repo(tmp_path, hardcoded_paths)

    result = _run_checker(root)

    assert result.returncode == 1
    assert "2 hard-coded path(s)" in result.stdout


def test_rejects_forward_slash_windows_user_path(tmp_path: Path) -> None:
    hardcoded_path = 'output_dir = "C:' + "/Us" + 'ers/researcher/artifacts"\n'
    root = _make_repo(tmp_path, hardcoded_path)

    result = _run_checker(root)

    assert result.returncode == 1
    assert "C:/" in result.stdout


def test_scans_documentation_and_tests(tmp_path: Path) -> None:
    root = _make_repo(tmp_path, "portable = true\n")
    unix_path = "/ho" + "me/researcher/run"
    windows_path = "C:" + "/Us" + "ers/researcher/run"
    (root / "docs" / "guide.md").write_text(unix_path, encoding="utf-8")
    (root / "tests" / "fixture.txt").write_text(windows_path, encoding="utf-8")

    result = _run_checker(root)

    assert result.returncode == 1
    assert "docs/guide.md" in result.stdout.replace("\\", "/")
    assert "tests/fixture.txt" in result.stdout.replace("\\", "/")


def test_scans_workflow_metadata_reports_and_root_files(tmp_path: Path) -> None:
    root = _make_repo(tmp_path, "portable = true\n")
    hardcoded_path = "/ho" + "me/researcher/run"
    targets = (
        root / ".github" / "ci.yml",
        root / "workflow" / "Snakefile",
        root / "containers" / "versions.md",
        root / "reports" / "report.md",
        root / "README.md",
        root / "pyproject.toml",
        root / "environment.yml",
        root / ".pre-commit-config.yaml",
    )
    for target in targets:
        target.write_text(hardcoded_path, encoding="utf-8")

    result = _run_checker(root)

    assert result.returncode == 1
    normalized_output = result.stdout.replace("\\", "/")
    for target in targets:
        assert target.relative_to(root).as_posix() in normalized_output
