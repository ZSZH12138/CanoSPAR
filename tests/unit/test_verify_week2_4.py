"""Tests for the Week 2-4 acceptance runner and its privacy boundary."""

from __future__ import annotations

import json
import os
import subprocess
from collections.abc import Sequence
from pathlib import Path

from scripts import verify_week2_4


def test_default_checks_make_dataset_contract_format_and_build_observable() -> None:
    names = [check.name for check in verify_week2_4.CHECKS]

    assert "dataset_contract_tests" in names
    assert "ruff_format" in names
    assert "build" in names
    dataset_check = verify_week2_4.CHECKS[names.index("dataset_contract_tests")]
    assert "tests/unit/data/test_hcp_manifest.py" in dataset_check.command
    assert "tests/unit/data/test_ppmi_manifest.py" in dataset_check.command
    assert "tests/unit/data/test_ppmi_targets.py" in dataset_check.command
    assert "tests/unit/data/test_task_gate.py" in dataset_check.command
    fixture_check = verify_week2_4.CHECKS[names.index("fixture_pipeline")]
    assert fixture_check.command[-2:] == ("--cores", "1")
    build_check = verify_week2_4.CHECKS[names.index("build")]
    assert build_check.command[-1] == "--no-isolation"


def test_branch_coverage_total_is_recorded() -> None:
    output = "TOTAL 2848 333 1064 232 85.25%\n"

    assert verify_week2_4._coverage(output) == 85.25


def test_success_records_commands_counts_coverage_resources_and_governance(
    tmp_path: Path,
) -> None:
    def runner(
        command: Sequence[str],
        *,
        cwd: Path,
        capture_output: bool,
        text: bool,
        check: bool,
    ) -> subprocess.CompletedProcess[str]:
        assert cwd == tmp_path
        assert capture_output and text and not check
        stdout = "3 passed, 1 skipped in 0.20s\nTOTAL 100 15 85%\n"
        return subprocess.CompletedProcess(command, 0, stdout=stdout, stderr="")

    report = tmp_path / "verification_results.json"
    exit_code = verify_week2_4.run_verification(
        project_root=tmp_path,
        report_path=report,
        checks=(verify_week2_4.CheckSpec("synthetic", ("python", "-m", "pytest")),),
        runner=runner,
        clock=lambda: 1.0,
        governance_probe=lambda _root: {
            "real_metadata_git_tracked_count": 0,
            "real_metadata_git_staged_count": 0,
        },
    )

    record = json.loads(report.read_text(encoding="utf-8"))
    assert exit_code == 0
    assert record["overall_status"] == "PASS"
    assert record["summary"] == {"failed": 0, "passed": 1, "skipped": 0}
    assert record["coverage_percent"] == 85.0
    assert record["checks"][0]["command"] == ["python", "-m", "pytest"]
    assert record["checks"][0]["exit_code"] == 0
    assert record["checks"][0]["test_counts"] == {"failed": 0, "passed": 3, "skipped": 1}
    assert record["resources"]["cpu_only"] is True
    assert record["resources"]["gpu_used"] is False
    assert record["governance"]["private_metadata_read"] is False
    assert record["governance"]["network_access"] is False


def test_required_failure_returns_nonzero_and_redacts_absolute_paths(tmp_path: Path) -> None:
    private_path = "C:" + "\\Us" + "ers\\Research User\\private\\metadata.csv"

    def runner(
        command: Sequence[str],
        *,
        cwd: Path,
        capture_output: bool,
        text: bool,
        check: bool,
    ) -> subprocess.CompletedProcess[str]:
        del cwd, capture_output, text, check
        return subprocess.CompletedProcess(command, 7, stdout="", stderr=private_path)

    report = tmp_path / "verification_results.json"
    exit_code = verify_week2_4.run_verification(
        project_root=tmp_path,
        report_path=report,
        checks=(verify_week2_4.CheckSpec("required", (private_path,)),),
        runner=runner,
        clock=lambda: 1.0,
        governance_probe=lambda _root: {
            "real_metadata_git_tracked_count": 0,
            "real_metadata_git_staged_count": 0,
        },
    )

    serialized = report.read_text(encoding="utf-8")
    assert exit_code != 0
    assert private_path not in serialized
    assert "Research User" not in serialized
    assert "<path>" in serialized


def test_required_failure_redacts_embedded_windows_unc_path(tmp_path: Path) -> None:
    private_path = "\\\\" + "private-server\\restricted-share\\Research User\\metadata.csv"

    def runner(
        command: Sequence[str],
        *,
        cwd: Path,
        capture_output: bool,
        text: bool,
        check: bool,
    ) -> subprocess.CompletedProcess[str]:
        del cwd, capture_output, text, check
        diagnostic = f"failed to read network source {private_path}"
        return subprocess.CompletedProcess(command, 7, stdout="", stderr=diagnostic)

    report = tmp_path / "verification_results.json"
    exit_code = verify_week2_4.run_verification(
        project_root=tmp_path,
        report_path=report,
        checks=(verify_week2_4.CheckSpec("required", ("python",)),),
        runner=runner,
        clock=lambda: 1.0,
        governance_probe=lambda _root: {
            "real_metadata_git_tracked_count": 0,
            "real_metadata_git_staged_count": 0,
        },
    )

    serialized = report.read_text(encoding="utf-8")
    assert exit_code != 0
    assert "private-server" not in serialized
    assert "restricted-share" not in serialized
    assert "Research User" not in serialized
    assert "<path>" in serialized


def test_governance_probe_ignores_inherited_git_context(
    tmp_path: Path,
    monkeypatch: object,
) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    isolated_git_environment = {
        name: value for name, value in os.environ.items() if not name.startswith("GIT_")
    }
    subprocess.run(
        ("git", "init", "-q"),
        cwd=repository,
        check=True,
        env=isolated_git_environment,
    )
    monkeypatch.setenv("GIT_DIR", str(tmp_path / "contaminating-git-dir"))  # type: ignore[attr-defined]
    monkeypatch.setenv("GIT_INDEX_FILE", str(tmp_path / "contaminating-index"))  # type: ignore[attr-defined]

    counts = verify_week2_4.probe_governance(repository)

    assert counts == {
        "real_metadata_git_tracked_count": 0,
        "real_metadata_git_staged_count": 0,
        "real_metadata_git_history_commit_count": 0,
    }


def test_governance_failure_is_required_even_when_commands_pass(tmp_path: Path) -> None:
    def runner(
        command: Sequence[str],
        *,
        cwd: Path,
        capture_output: bool,
        text: bool,
        check: bool,
    ) -> subprocess.CompletedProcess[str]:
        del cwd, capture_output, text, check
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    report = tmp_path / "verification_results.json"
    exit_code = verify_week2_4.run_verification(
        project_root=tmp_path,
        report_path=report,
        checks=(verify_week2_4.CheckSpec("pass", ("python",)),),
        runner=runner,
        clock=lambda: 1.0,
        governance_probe=lambda _root: {
            "real_metadata_git_tracked_count": 1,
            "real_metadata_git_staged_count": 0,
        },
    )

    assert exit_code != 0
    assert json.loads(report.read_text(encoding="utf-8"))["overall_status"] == "FAIL"


def test_dry_run_lists_checks_without_writing_report(tmp_path: Path, capsys: object) -> None:
    output = tmp_path / "reports"

    assert verify_week2_4.main(["--output-dir", str(output), "--dry-run"]) == 0
    assert not output.exists()
    assert "fixture" in capsys.readouterr().out.casefold()  # type: ignore[attr-defined]
