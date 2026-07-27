"""Tests for privacy-preserving provenance records."""

from __future__ import annotations

import json
import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import pytest

from canospar.utils.provenance import (
    _package_version,
    _sanitize_command,
    collect_provenance,
    write_provenance,
)


def _isolated_git_environment() -> dict[str, str]:
    """Keep nested test repositories independent of an outer Git invocation."""
    return {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}


def _run_nested_git(*args: str, cwd: Path) -> None:
    subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        env=_isolated_git_environment(),
    )


def test_collect_provenance_has_required_cpu_only_fields(tmp_path: Path) -> None:
    record = collect_provenance(
        contract_version="week1-v1",
        project_root=tmp_path,
        config_hash="a" * 64,
        random_seed=17,
        command=["python", "-m", "canospar.utils.smoke_test", "paths.output_dir=C:/secret"],
        now=datetime(2026, 7, 24, 12, 30, tzinfo=UTC),
    )

    assert record["timestamp_utc"] == "2026-07-24T12:30:00Z"
    assert record["contract_version"] == "week1-v1"
    assert record["config_hash"] == "a" * 64
    assert record["random_seed"] == 17
    assert isinstance(record["python_version"], str)
    assert isinstance(record["platform"], str)
    assert isinstance(record["torch_version"], str)
    assert isinstance(record["torch_geometric_version"], str)
    assert record["device"] == "cpu"
    assert record["cuda_available"] is False
    assert isinstance(record["git_dirty"], bool)
    assert record["command"] == [
        "python",
        "-m",
        "canospar.utils.smoke_test",
        "paths.output_dir=<path>",
    ]


def test_collect_provenance_represents_absent_commit_manifest_and_container(
    tmp_path: Path,
) -> None:
    record = collect_provenance(
        contract_version="week1-v1",
        config_hash="a" * 64,
        random_seed=17,
        command="python -m canospar.utils.smoke_test",
        project_root=tmp_path,
    )

    assert record["dataset_manifest_hash"] is None
    assert record["dataset_manifest_hash_status"] == "not_available_in_week1"
    assert record["dataset_manifest_hash_reason"] == "No dataset manifest was supplied."
    assert record["container_digest"] is None
    assert record["container_digest_status"] == "not_available_in_week1"
    assert record["container_digest_reason"] == "No container digest was supplied."


def test_collect_provenance_uses_structured_null_when_repository_has_no_commit(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    def fake_git(*_args: str, **_kwargs: object) -> str:
        raise RuntimeError("fatal: your current branch 'master' does not have any commits yet")

    monkeypatch.setattr("canospar.utils.provenance._run_git", fake_git)

    record = collect_provenance(
        contract_version="week1-v1",
        config_hash="a" * 64,
        random_seed=17,
        command="python -m canospar.utils.smoke_test",
        project_root=tmp_path,
    )

    assert record["commit_hash"] is None
    assert record["commit_hash_status"] == "unavailable"
    assert record["commit_hash_reason"] == "Git repository has no commits."
    assert record["git_dirty"] is False


def test_collect_provenance_never_serializes_private_machine_data(tmp_path: Path) -> None:
    record = collect_provenance(
        contract_version="week1-v1",
        config_hash="a" * 64,
        random_seed=17,
        command="python -m canospar.utils.smoke_test",
        project_root=tmp_path,
    )
    serialized = json.dumps(record).casefold()

    assert "username" not in serialized
    assert "hostname" not in serialized
    assert "token" not in serialized
    assert "cwd" not in serialized
    assert tmp_path.as_posix().casefold() not in serialized
    assert "c:\\users\\" not in serialized


def test_collect_provenance_records_supplied_manifest_container_and_dirty_git(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    manifest = tmp_path / "manifest.csv"
    manifest.write_text("sample_id\nsubject-001\n", encoding="utf-8")

    def fake_git(*args: str, **_kwargs: object) -> str:
        return "cafebabe" if args[:2] == ("rev-parse", "HEAD") else " M file.py"

    monkeypatch.setattr("canospar.utils.provenance._run_git", fake_git)

    record = collect_provenance(
        contract_version="week1-v1",
        config_hash="a" * 64,
        random_seed=17,
        command=["runner", "--token", "secret", "C:/private/input.csv"],
        project_root=tmp_path,
        dataset_manifest_path=manifest,
        container_digest="sha256:container",
    )

    assert record["commit_hash"] == "cafebabe"
    assert record["commit_hash_status"] == "available"
    assert record["commit_hash_reason"] is None
    assert record["git_dirty"] is True
    assert isinstance(record["dataset_manifest_hash"], str)
    assert record["dataset_manifest_hash_status"] == "available"
    assert record["container_digest_status"] == "available"
    assert record["command"] == ["runner", "--token", "<redacted>", "<path>"]


def test_collect_provenance_rejects_non_cpu_device(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="device='cpu'"):
        collect_provenance(
            contract_version="week1-v1",
            config_hash="a" * 64,
            random_seed=17,
            command="runner",
            project_root=tmp_path,
            device="cuda",
        )


def test_command_sanitizer_and_package_lookup_handle_private_values() -> None:
    assert _sanitize_command("runner output=/tmp/private --api-key=secret") == [
        "runner",
        "output=<path>",
        "--api-key=<redacted>",
    ]
    assert _package_version("canospar-package-that-does-not-exist") == "not_installed"


def test_command_sanitizer_redacts_windows_and_posix_paths_without_losing_flag_state() -> None:
    windows_private_path = "".join(("C:", "\\", "Users", "\\", "alice", "\\", "foo bar.txt"))
    posix_private_path = "/".join(("", "home", "alice", "input.csv"))

    assert _sanitize_command(
        [
            "runner",
            windows_private_path,
            "--token",
            "secret",
            posix_private_path,
        ]
    ) == ["runner", "<path>", "--token", "<redacted>", "<path>"]


def test_real_git_repository_without_head_reports_dirty_worktree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    outer_index = tmp_path / "outer-index"
    monkeypatch.setenv("GIT_INDEX_FILE", str(outer_index))
    assert "GIT_INDEX_FILE" not in _isolated_git_environment()
    _run_nested_git("init", "--quiet", cwd=tmp_path)
    for key in tuple(os.environ):
        if key.startswith("GIT_"):
            monkeypatch.delenv(key)
    (tmp_path / "untracked.txt").write_text("dirty\n", encoding="utf-8")

    record = collect_provenance(
        contract_version="week1-v1",
        config_hash="a" * 64,
        random_seed=17,
        command="runner",
        project_root=tmp_path,
    )

    assert record["commit_hash"] is None
    assert record["commit_hash_status"] == "unavailable"
    assert record["commit_hash_reason"] == "Git repository has no commits."
    assert record["git_dirty"] is True


def test_write_provenance_writes_canonical_json(tmp_path: Path) -> None:
    destination = tmp_path / "provenance.json"

    write_provenance({"b": 2, "a": "value"}, destination)

    assert destination.read_text(encoding="utf-8") == '{"a":"value","b":2}\n'
