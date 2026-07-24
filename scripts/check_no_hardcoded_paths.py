"""Reject user-specific absolute paths in portable project files.

The guard scans source, configuration, automation, documentation, tests,
reports, container declarations, and root metadata. Generic placeholders such
as ``/home/<user>/run`` remain portable.
"""

from __future__ import annotations

import argparse
import re
from collections.abc import Iterable
from pathlib import Path

SCAN_DIRECTORIES = (
    ".github",
    "configs",
    "containers",
    "docs",
    "reports",
    "scripts",
    "src",
    "tests",
    "workflow",
)
SCAN_ROOT_FILES = (
    ".gitignore",
    ".pre-commit-config.yaml",
    "AGENTS.md",
    "environment.lock.yml",
    "environment.yml",
    "LICENSE",
    "pyproject.toml",
    "README.md",
)
WINDOWS_USER_PATH = re.compile(
    r"(?i)\b[a-z]:[\\/]+Users[\\/]+"
    r"(?!<(?:user|username)>[\\/]|%USERNAME%(?:[\\/]|$)|\$env:USERNAME(?:[\\/]|$))"
    r"[^\\/\s\"']+"
)
POSIX_USER_PATH = re.compile(
    r"(?<![A-Za-z0-9_:])/(?:home|Users)/"
    r"(?!<(?:user|username)>(?:/|$)|\$USER(?:/|$)|\$\{USER\}(?:/|$))"
    r"[^/\s\"']+"
)


def _iter_scan_files(root: Path, script_path: Path) -> Iterable[Path]:
    """Yield project files in scope, excluding this checker's own patterns."""
    for directory_name in SCAN_DIRECTORIES:
        directory = root / directory_name
        if not directory.is_dir():
            continue
        for candidate in sorted(directory.rglob("*")):
            if candidate.is_file() and candidate.resolve() != script_path:
                yield candidate
    for file_name in SCAN_ROOT_FILES:
        candidate = root / file_name
        if candidate.is_file() and candidate.resolve() != script_path:
            yield candidate


def find_hardcoded_paths(root: Path, *, script_path: Path) -> list[tuple[Path, int, str]]:
    """Return every user-specific absolute path found in the scan scope."""
    findings: list[tuple[Path, int, str]] = []
    for path in _iter_scan_files(root, script_path):
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for line_number, line in enumerate(text.splitlines(), start=1):
            for pattern in (WINDOWS_USER_PATH, POSIX_USER_PATH):
                for match in pattern.finditer(line):
                    findings.append((path, line_number, match.group(0)))
    return findings


def main() -> int:
    """Run the portable-path check and return a process-appropriate status."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="Project root to scan")
    arguments = parser.parse_args()

    root = arguments.root.resolve()
    findings = find_hardcoded_paths(root, script_path=Path(__file__).resolve())
    if not findings:
        print("No hard-coded user-specific absolute paths found.")
        return 0

    print(f"{len(findings)} hard-coded path(s) found:")
    for path, line_number, value in findings:
        print(f"{path.relative_to(root)}:{line_number}: {value}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
