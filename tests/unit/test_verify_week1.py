from __future__ import annotations

import json
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

from scripts import verify_week1

EXPECTED_CHECK_NAMES = [
    "python_version",
    "repository_structure",
    "cpu_torch",
    "core_imports",
    "hydra_config",
    "data_contracts",
    "smoke_execution",
    "smoke_artifacts",
    "provenance",
    "git_ignore",
    "hardcoded_path_scan",
    "ruff",
    "mypy",
    "unit_tests",
    "integration_tests",
    "coverage",
    "snakemake_dry_run",
]


def test_check_specs_have_the_required_order_and_module_invocations() -> None:
    assert [check.name for check in verify_week1.CHECKS] == EXPECTED_CHECK_NAMES
    assert len(verify_week1.CHECKS) == 17
    assert verify_week1.CHECKS[11].command[:3] == (sys.executable, "-m", "ruff")
    assert verify_week1.CHECKS[12].command[:3] == (sys.executable, "-m", "mypy")
    assert verify_week1.CHECKS[13].command[:3] == (sys.executable, "-m", "pytest")
    assert verify_week1.CHECKS[14].command[:3] == (sys.executable, "-m", "pytest")
    assert verify_week1.CHECKS[15].command[:3] == (sys.executable, "-m", "pytest")
    assert "--cov=canospar" in verify_week1.CHECKS[15].command
    assert "--cov-fail-under=80" in verify_week1.CHECKS[15].command
    assert verify_week1.CHECKS[16].command[:3] == (sys.executable, "-m", "snakemake")
    assert all(
        argument not in {"scripts/verify_week1.py", "verify_week1.py"}
        for check in verify_week1.CHECKS
        for argument in check.command
    )
    required_paths = (
        "README.md",
        "environment.lock.yml",
        ".github/workflows/ci.yml",
        "containers/model.def",
        "configs/paths/local.example.yaml",
        "docs/experiment_contract.md",
        "docs/decisions/0001-hcp-unrelated-cohort-and-output-boundaries.md",
        "src/canospar/data/contracts.py",
        "src/canospar/utils/smoke_test.py",
        "scripts/bootstrap.ps1",
        "tests/integration/test_smoke_cli.py",
        "tests/regression",
        "reports/week1/WEEK1_IMPLEMENTATION_REPORT.md",
    )
    assert all(path in verify_week1._STRUCTURE_CHECK for path in required_paths)
    assert '"platform"' in verify_week1._PROVENANCE_CHECK
    assert (
        'record["contract_version"] == resolved_config.contract_version == "1.1.0"'
        in verify_week1._PROVENANCE_CHECK
    )
    assert (
        'smoke_report["contract_version"] == resolved_config.contract_version == "1.1.0"'
        in verify_week1._ARTIFACT_CHECK
    )
    assert "WINDOWS_USER_PATH" in verify_week1._PROVENANCE_CHECK
    assert "POSIX_USER_PATH" in verify_week1._PROVENANCE_CHECK
    assert "data/example.nii.gz" in verify_week1._GITIGNORE_CHECK
    assert (
        verify_week1._REPORT_PATH.relative_to(verify_week1._PROJECT_ROOT).as_posix()
        == "reports/week1/verification_results.json"
    )
    ci_workflow = (
        Path(__file__).resolve().parents[2] / ".github" / "workflows" / "ci.yml"
    ).read_text(encoding="utf-8")
    assert 'output="$(python -m pytest -q tests/unit 2>&1)"' in ci_workflow
    assert "run: python -m pytest -q tests/integration" in ci_workflow


def test_successful_verification_runs_all_checks_and_always_writes_report(
    tmp_path: Path,
    capsys: object,
) -> None:
    calls: list[tuple[tuple[str, ...], Path]] = []

    def successful_runner(
        command: Sequence[str],
        *,
        cwd: Path,
        capture_output: bool,
        text: bool,
        check: bool,
    ) -> subprocess.CompletedProcess[str]:
        assert capture_output is True
        assert text is True
        assert check is False
        calls.append((tuple(command), cwd))
        return subprocess.CompletedProcess(command, 0, stdout="ok\n", stderr="")

    report_path = tmp_path / "reports" / "week1" / "verification_results.json"
    exit_code = verify_week1.run_verification(
        project_root=tmp_path,
        report_path=report_path,
        runner=successful_runner,
    )

    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert exit_code == 0
    assert len(calls) == 17
    assert all(cwd == tmp_path for _, cwd in calls)
    assert [result["name"] for result in report["checks"]] == EXPECTED_CHECK_NAMES
    assert [result["status"] for result in report["checks"]] == ["PASS"] * 17
    assert report["overall_status"] == "PASS"
    assert report["contract_version"] == "1.1.0"
    assert report["summary"] == {"FAIL": 0, "PASS": 17, "SKIP_WITH_REASON": 0}
    output = capsys.readouterr().out  # type: ignore[attr-defined]
    assert "01. python_version: PASS" in output
    assert "17. snakemake_dry_run: PASS" in output


def test_failed_required_check_preserves_returncode_continues_and_returns_nonzero(
    tmp_path: Path,
) -> None:
    call_count = 0

    def failing_runner(
        command: Sequence[str],
        *,
        cwd: Path,
        capture_output: bool,
        text: bool,
        check: bool,
    ) -> subprocess.CompletedProcess[str]:
        del cwd, capture_output, text, check
        nonlocal call_count
        call_count += 1
        returncode = 7 if call_count == 3 else 0
        return subprocess.CompletedProcess(
            command,
            returncode,
            stdout="diagnostic stdout",
            stderr="diagnostic stderr" if returncode else "",
        )

    report_path = tmp_path / "verification_results.json"
    exit_code = verify_week1.run_verification(
        project_root=tmp_path,
        report_path=report_path,
        runner=failing_runner,
    )

    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert exit_code == 1
    assert call_count == 17
    assert report["overall_status"] == "FAIL"
    assert report["checks"][2]["status"] == "FAIL"
    assert report["checks"][2]["returncode"] == 7
    assert report["checks"][3]["status"] == "PASS"


def test_unavailable_optional_check_uses_skip_with_reason(tmp_path: Path) -> None:
    optional_check = verify_week1.CheckSpec(
        name="optional_example",
        command=(sys.executable, "-m", "optional_example"),
        required=False,
    )

    def unavailable_runner(
        command: Sequence[str],
        *,
        cwd: Path,
        capture_output: bool,
        text: bool,
        check: bool,
    ) -> subprocess.CompletedProcess[str]:
        del command, cwd, capture_output, text, check
        raise FileNotFoundError("optional executable is unavailable")

    result = verify_week1.execute_check(optional_check, tmp_path, unavailable_runner)

    assert result.status == "SKIP_WITH_REASON"
    assert result.returncode is None
    assert result.reason is not None


def test_exception_and_failed_output_paths_are_redacted_from_report(tmp_path: Path) -> None:
    user_path = "C:" + "\\Us" + "ers\\Research User\\private\\tool.exe"
    call_count = 0

    def unsafe_runner(
        command: Sequence[str],
        *,
        cwd: Path,
        capture_output: bool,
        text: bool,
        check: bool,
    ) -> subprocess.CompletedProcess[str]:
        del cwd, capture_output, text, check
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise FileNotFoundError(f"missing executable {user_path}")
        return subprocess.CompletedProcess(
            command,
            9,
            stdout=f"failed while reading {user_path}",
            stderr=f"cannot execute {user_path}",
        )

    report_path = tmp_path / "verification_results.json"
    exit_code = verify_week1.run_verification(
        project_root=tmp_path,
        report_path=report_path,
        runner=unsafe_runner,
    )

    serialized_report = report_path.read_text(encoding="utf-8")
    assert exit_code == 1
    assert user_path not in serialized_report
    assert "Research User" not in serialized_report
    assert "<path>" in serialized_report
