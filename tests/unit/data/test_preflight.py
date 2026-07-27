"""Synthetic tests for data governance preflight outcomes."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from canospar.data.preflight import PreflightOutcome, run_preflight


def _isolated_git_environment() -> dict[str, str]:
    return {name: value for name, value in os.environ.items() if not name.startswith("GIT_")}


def _repository(tmp_path: Path) -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["git", "init", "--quiet"],
        cwd=tmp_path,
        check=True,
        env=_isolated_git_environment(),
    )
    (tmp_path / "pyproject.toml").write_text(
        "[project]\nname='synthetic'\nversion='0'\n", encoding="utf-8"
    )
    return tmp_path


def _commit_baseline(repository: Path) -> str:
    environment = _isolated_git_environment()
    subprocess.run(
        ["git", "config", "user.email", "synthetic@example.invalid"],
        cwd=repository,
        check=True,
        env=environment,
    )
    subprocess.run(
        ["git", "config", "user.name", "Synthetic Test"],
        cwd=repository,
        check=True,
        env=environment,
    )
    (repository / "baseline.txt").write_text("synthetic\n", encoding="utf-8")
    subprocess.run(
        ["git", "add", "baseline.txt", "pyproject.toml"],
        cwd=repository,
        check=True,
        env=environment,
    )
    subprocess.run(
        ["git", "commit", "--quiet", "-m", "baseline"], cwd=repository, check=True, env=environment
    )
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
        env=environment,
    )
    return completed.stdout.strip()


def test_preflight_records_memory_waiver_and_safe_compute_inventory(tmp_path: Path) -> None:
    root = _repository(tmp_path)
    (root / ".gitignore").write_text("data/**\n", encoding="utf-8")
    metadata = root / "data" / "metadata"
    metadata.mkdir(parents=True)
    (metadata / "table.csv").write_text("id\n001\n", encoding="utf-8")

    report = run_preflight(root, metadata_root=metadata, memory_gate_waived=True)

    assert report.outcome is PreflightOutcome.OK
    assert report.memory_gate["status"] == "waived"
    assert report.memory_gate["does_not_authorize"] == ["MRI", "GPU"]
    assert report.data_governance["metadata_git_ignored"] is True


def test_preflight_records_verifiable_repository_baseline_without_absolute_path(
    tmp_path: Path,
) -> None:
    root = _repository(tmp_path)
    head = _commit_baseline(root)
    metadata = tmp_path.parent / "external_metadata"
    metadata.mkdir()

    report = run_preflight(root, metadata_root=metadata, memory_gate_waived=True)

    assert report.repository["head_sha"] == head
    assert report.repository["head_status"] == "available"
    assert report.repository["dirty"] is False
    assert isinstance(report.repository["worktree_id"], str)
    assert str(root) not in report.to_json()


@pytest.mark.parametrize(
    ("setup", "expected"),
    [
        ("tracked_private", PreflightOutcome.DATA_GOVERNANCE_BLOCKED),
        ("repository_missing", PreflightOutcome.REPOSITORY_BLOCKED),
        ("imaging_volume", PreflightOutcome.COMPUTE_BLOCKED),
    ],
)
def test_preflight_returns_explicit_blockers(
    tmp_path: Path, setup: str, expected: PreflightOutcome
) -> None:
    root = tmp_path
    metadata = tmp_path / "metadata"
    metadata.mkdir()
    if setup != "repository_missing":
        root = _repository(tmp_path)
    if setup == "tracked_private":
        private = root / "data" / "metadata" / "private.csv"
        private.parent.mkdir(parents=True)
        private.write_text("id\n001\n", encoding="utf-8")
        subprocess.run(
            ["git", "add", "data/metadata/private.csv"],
            cwd=root,
            check=True,
            env=_isolated_git_environment(),
        )
    if setup == "imaging_volume":
        (metadata / "image.nii.gz").write_bytes(b"synthetic")

    report = run_preflight(root, metadata_root=metadata, memory_gate_waived=True)

    assert report.outcome is expected
    assert report.issues


def test_preflight_uses_only_the_supplied_temporary_repository(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = _repository(tmp_path / "isolated")
    private = root / "data" / "metadata" / "private.csv"
    private.parent.mkdir(parents=True)
    private.write_text("id\n001\n", encoding="utf-8")
    subprocess.run(
        ["git", "add", "data/metadata/private.csv"],
        cwd=root,
        check=True,
        env=_isolated_git_environment(),
    )
    guard = _repository(tmp_path / "guard")
    guard_before = subprocess.run(
        ["git", "status", "--short"],
        cwd=guard,
        check=True,
        capture_output=True,
        text=True,
        env=_isolated_git_environment(),
    )
    monkeypatch.setenv("GIT_DIR", str(guard / ".git"))
    monkeypatch.setenv("GIT_WORK_TREE", str(guard))

    report = run_preflight(root, metadata_root=private.parent, memory_gate_waived=True)
    guard_status = subprocess.run(
        ["git", "status", "--short"],
        cwd=guard,
        check=True,
        capture_output=True,
        text=True,
        env=_isolated_git_environment(),
    )

    assert report.outcome is PreflightOutcome.DATA_GOVERNANCE_BLOCKED
    assert guard_status.stdout == guard_before.stdout


def test_preflight_report_never_emits_legacy_filename(tmp_path: Path) -> None:
    root = _repository(tmp_path)
    metadata = tmp_path / "metadata"
    (metadata / "legacy").mkdir(parents=True)
    secret_name = "subject-0007-private.csv"
    (metadata / "legacy" / secret_name).write_text("id\n001\n", encoding="utf-8")

    report = run_preflight(root, metadata_root=metadata, memory_gate_waived=True)

    assert secret_name not in report.to_json()
