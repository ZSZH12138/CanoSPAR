"""Run fixture-only Week 2-4 acceptance checks and write sanitized evidence."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PureWindowsPath
from typing import Literal, Protocol, TypeAlias

Status: TypeAlias = Literal["PASS", "FAIL", "SKIP_WITH_REASON"]

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_OUTPUT_DIR = _PROJECT_ROOT / "reports" / "data_qc" / "week02_04"
_WINDOWS_ABSOLUTE_PATH = re.compile(r"(?i)\b[a-z]:[\\/][^\r\n\"']+")
_WINDOWS_UNC_PATH = re.compile(r"(?i)(?<![:/\\])(?:\\\\|//)[^\\/\r\n\"']+[\\/][^\r\n\"']+")
_POSIX_ABSOLUTE_PATH = re.compile(r"(?<![A-Za-z0-9_:])/[^\r\n\"']+")
_COVERAGE = re.compile(r"(?m)^TOTAL(?:\s+\d+){2,4}\s+(\d+(?:\.\d+)?)%")
_PYTEST_COUNT = re.compile(r"(\d+)\s+(passed|failed|skipped)")


@dataclass(frozen=True)
class CheckSpec:
    """One ordered acceptance command."""

    name: str
    command: tuple[str, ...]
    required: bool = True


@dataclass(frozen=True)
class CheckResult:
    """Sanitized outcome for one acceptance command."""

    name: str
    command: tuple[str, ...]
    status: Status
    required: bool
    exit_code: int | None
    duration_seconds: float
    test_counts: Mapping[str, int]
    coverage_percent: float | None
    diagnostic: str | None

    def as_record(self) -> dict[str, object]:
        return {
            "name": self.name,
            "command": list(self.command),
            "status": self.status,
            "required": self.required,
            "exit_code": self.exit_code,
            "duration_seconds": self.duration_seconds,
            "test_counts": dict(self.test_counts),
            "coverage_percent": self.coverage_percent,
            "diagnostic": self.diagnostic,
        }


class Runner(Protocol):
    def __call__(
        self,
        command: Sequence[str],
        *,
        cwd: Path,
        capture_output: bool,
        text: bool,
        check: bool,
    ) -> subprocess.CompletedProcess[str]: ...


def _runner(
    command: Sequence[str],
    *,
    cwd: Path,
    capture_output: bool,
    text: bool,
    check: bool,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd,
        capture_output=capture_output,
        text=text,
        check=check,
    )


CHECKS: tuple[CheckSpec, ...] = (
    CheckSpec(
        "fixture_pipeline",
        (
            sys.executable,
            "-m",
            "snakemake",
            "-s",
            "workflow/Snakefile",
            "metadata_fixture",
            "--cores",
            "1",
        ),
    ),
    CheckSpec(
        "fixture_determinism",
        (
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "tests/integration/data/test_week2_4_pipeline.py",
        ),
    ),
    CheckSpec(
        "dataset_contract_tests",
        (
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "tests/unit/data/test_hcp_manifest.py",
            "tests/unit/data/test_ppmi_manifest.py",
            "tests/unit/data/test_ppmi_targets.py",
            "tests/unit/data/test_task_gate.py",
            "tests/unit/data/test_manifest_validation.py",
        ),
    ),
    CheckSpec(
        "unit_tests",
        (sys.executable, "-m", "pytest", "-q", "tests/unit"),
    ),
    CheckSpec(
        "integration_tests",
        (sys.executable, "-m", "pytest", "-q", "tests/integration"),
    ),
    CheckSpec(
        "coverage",
        (
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "--cov=canospar",
            "--cov-report=term",
            "--cov-fail-under=80",
            "tests",
        ),
    ),
    CheckSpec(
        "ruff",
        (sys.executable, "-m", "ruff", "check", "src", "tests", "scripts"),
    ),
    CheckSpec(
        "ruff_format",
        (sys.executable, "-m", "ruff", "format", "--check", "src", "tests", "scripts"),
    ),
    CheckSpec(
        "mypy",
        (sys.executable, "-m", "mypy", "src/canospar"),
    ),
    CheckSpec("week1_acceptance", (sys.executable, "scripts/verify_week1.py")),
    CheckSpec(
        "snakemake_dry_run",
        (sys.executable, "-m", "snakemake", "-n", "-s", "workflow/Snakefile"),
    ),
    CheckSpec(
        "build",
        (sys.executable, "-m", "build", "--no-isolation"),
    ),
)


def _sanitize(text: str) -> str:
    without_unc = _WINDOWS_UNC_PATH.sub("<path>", text)
    return _POSIX_ABSOLUTE_PATH.sub(
        "<path>",
        _WINDOWS_ABSOLUTE_PATH.sub("<path>", without_unc),
    )


def _safe_command(command: Sequence[str]) -> tuple[str, ...]:
    result: list[str] = []
    for index, token in enumerate(command):
        if index == 0 and Path(token).name.casefold().startswith("python"):
            result.append("python")
        elif PureWindowsPath(token).is_absolute() or Path(token).is_absolute():
            result.append("<path>")
        else:
            result.append(_sanitize(token))
    return tuple(result)


def _counts(output: str) -> dict[str, int]:
    parsed = {"failed": 0, "passed": 0, "skipped": 0}
    for count, name in _PYTEST_COUNT.findall(output):
        parsed[name] = int(count)
    return parsed


def _coverage(output: str) -> float | None:
    match = _COVERAGE.search(output)
    return float(match.group(1)) if match is not None else None


def execute_check(
    spec: CheckSpec,
    project_root: Path,
    runner: Runner,
    clock: Callable[[], float],
) -> CheckResult:
    """Run one command and retain only aggregate, path-sanitized evidence."""
    started = clock()
    try:
        completed = runner(
            spec.command,
            cwd=project_root,
            capture_output=True,
            text=True,
            check=False,
        )
        duration = max(0.0, clock() - started)
    except Exception as error:
        status: Status = "FAIL" if spec.required else "SKIP_WITH_REASON"
        return CheckResult(
            spec.name,
            _safe_command(spec.command),
            status,
            spec.required,
            None,
            max(0.0, clock() - started),
            {"failed": 0, "passed": 0, "skipped": 0},
            None,
            _sanitize(f"{type(error).__name__}: {error}"),
        )
    combined = f"{completed.stdout}\n{completed.stderr}"
    if completed.returncode == 0:
        status = "PASS"
        diagnostic = None
    else:
        status = "FAIL" if spec.required else "SKIP_WITH_REASON"
        diagnostic = _sanitize(completed.stderr or completed.stdout or "command failed")
    return CheckResult(
        spec.name,
        _safe_command(spec.command),
        status,
        spec.required,
        completed.returncode,
        round(duration, 6),
        _counts(combined),
        _coverage(combined),
        diagnostic,
    )


def probe_governance(project_root: Path) -> dict[str, int]:
    """Inspect Git's index only; never read private metadata contents."""
    commands = {
        "real_metadata_git_tracked_count": (
            "git",
            "ls-files",
            "--",
            "data/metadata",
        ),
        "real_metadata_git_staged_count": (
            "git",
            "diff",
            "--cached",
            "--name-only",
            "--",
            "data/metadata",
        ),
        "real_metadata_git_history_commit_count": (
            "git",
            "log",
            "--all",
            "--format=%H",
            "--",
            "data/metadata",
        ),
    }
    result: dict[str, int] = {}
    isolated_git_environment = {
        name: value for name, value in os.environ.items() if not name.startswith("GIT_")
    }
    for name, command in commands.items():
        completed = subprocess.run(
            command,
            cwd=project_root,
            capture_output=True,
            text=True,
            check=False,
            env=isolated_git_environment,
        )
        result[name] = (
            sum(bool(line.strip()) for line in completed.stdout.splitlines())
            if completed.returncode == 0
            else -1
        )
    return result


def _write_report(
    results: Sequence[CheckResult],
    report_path: Path,
    governance_counts: Mapping[str, int],
) -> int:
    required_failed = any(result.required and result.status == "FAIL" for result in results)
    governance_failed = any(value != 0 for value in governance_counts.values())
    coverage_values = [
        result.coverage_percent for result in results if result.coverage_percent is not None
    ]
    status_counts = {
        "passed": sum(result.status == "PASS" for result in results),
        "failed": sum(result.status == "FAIL" for result in results),
        "skipped": sum(result.status == "SKIP_WITH_REASON" for result in results),
    }
    durations = [result.duration_seconds for result in results]
    payload = {
        "contract_version": "1.1.0",
        "overall_status": "FAIL" if required_failed or governance_failed else "PASS",
        "summary": status_counts,
        "coverage_percent": max(coverage_values) if coverage_values else None,
        "checks": [result.as_record() for result in results],
        "resources": {
            "cpu_only": True,
            "gpu_used": False,
            "server_required": False,
            "peak_memory_mb": None,
            "longest_step_seconds": max(durations, default=0.0),
            "total_duration_seconds": round(sum(durations), 6),
        },
        "governance": {
            **dict(governance_counts),
            "fixture_only": True,
            "private_metadata_read": False,
            "network_access": False,
        },
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(payload, ensure_ascii=True, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    return int(required_failed or governance_failed)


def run_verification(
    *,
    project_root: Path,
    report_path: Path,
    checks: Sequence[CheckSpec] = CHECKS,
    runner: Runner = _runner,
    clock: Callable[[], float] = time.perf_counter,
    governance_probe: Callable[[Path], Mapping[str, int]] = probe_governance,
) -> int:
    """Run every check, continue after failures, and always write evidence."""
    results: list[CheckResult] = []
    for index, spec in enumerate(checks, start=1):
        result = execute_check(spec, project_root, runner, clock)
        results.append(result)
        print(f"{index:02d}. {result.name}: {result.status}")
    return _write_report(results, report_path, governance_probe(project_root))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify the Week 2-4 fixture pipeline.")
    parser.add_argument("--output-dir", type=Path, default=_DEFAULT_OUTPUT_DIR)
    parser.add_argument("--dry-run", action="store_true")
    arguments = parser.parse_args(argv)
    if arguments.dry_run:
        print("Week 2-4 fixture-only verification plan:")
        for check in CHECKS:
            print(f"- {check.name}")
        return 0
    return run_verification(
        project_root=_PROJECT_ROOT,
        report_path=arguments.output_dir / "verification_results.json",
    )


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
