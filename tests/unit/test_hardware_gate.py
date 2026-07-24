"""Tests for the privacy-preserving CPU-only hardware gate."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from canospar.utils import hardware_gate
from canospar.utils.hardware_gate import collect_hardware_gate, evaluate_hardware_gate


def test_evaluate_hardware_gate_preserves_original_result_after_ram_waiver() -> None:
    result = evaluate_hardware_gate(
        {"cpu_logical_cores": 4, "available_ram_gib": 2.5, "free_disk_gib": 20.0},
        waived_checks=("available_ram_gib",),
    )

    assert result["gate_passed"] is False
    assert result["effective_gate_passed"] is True
    assert result["waived_checks"] == ["available_ram_gib"]
    assert result["blocking_reasons"] == [
        "available_ram_gib was below the required minimum of 6.0 GiB."
    ]


def test_evaluate_hardware_gate_does_not_waive_unrelated_failure() -> None:
    result = evaluate_hardware_gate(
        {"cpu_logical_cores": 1, "available_ram_gib": 2.5, "free_disk_gib": 20.0},
        waived_checks=("available_ram_gib",),
    )

    assert result["gate_passed"] is False
    assert result["effective_gate_passed"] is False
    assert result["failed_checks"] == ["cpu_logical_cores", "available_ram_gib"]


def test_collect_hardware_gate_is_cpu_only_and_does_not_expose_paths_or_identity(
    tmp_path: Path,
) -> None:
    record = collect_hardware_gate(project_root=tmp_path)
    serialized = json.dumps(record).casefold()

    assert {
        "checked_at_utc",
        "operating_system",
        "architecture",
        "python_version",
        "cpu_physical_cores",
        "cpu_logical_cores",
        "total_ram_gib",
        "available_ram_gib",
        "available_ram_gib_samples",
        "free_disk_gib",
        "gpu_detected",
        "cuda_available",
        "git_available",
        "conda_or_venv_available",
        "docker_available",
        "apptainer_available",
        "gate_passed",
        "effective_gate_passed",
        "waived_checks",
        "blocking_reasons",
    }.issubset(record)
    assert record["device"] == "cpu"
    assert record["cuda_available"] is False
    assert "username" not in serialized
    assert "hostname" not in serialized
    assert "token" not in serialized
    assert "cwd" not in serialized
    assert tmp_path.as_posix().casefold() not in serialized
    assert "c:\\users\\" not in serialized


def test_memory_collector_uses_posix_sysconf_when_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    values = {"SC_PAGE_SIZE": 1024, "SC_PHYS_PAGES": 2048, "SC_AVPHYS_PAGES": 1024}
    monkeypatch.setattr(
        hardware_gate,
        "os",
        SimpleNamespace(name="posix", sysconf=values.__getitem__),
    )
    monkeypatch.setattr(hardware_gate.platform, "system", lambda: "Linux")

    assert hardware_gate._memory_gib() == (2048 * 1024 / 1024**3, 1024 * 1024 / 1024**3)


def test_windows_memory_collector_converts_bytes_to_gib(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class SuccessfulKernel32:
        @staticmethod
        def GlobalMemoryStatusEx(pointer: object) -> int:
            status = pointer._obj  # type: ignore[attr-defined]
            status.total_physical = 16 * 1024**3
            status.available_physical = 6 * 1024**3
            return 1

    values = {"SC_PAGE_SIZE": 1024, "SC_PHYS_PAGES": 2048, "SC_AVPHYS_PAGES": 1024}
    monkeypatch.setattr(
        hardware_gate,
        "os",
        SimpleNamespace(name="posix", sysconf=values.__getitem__),
    )
    monkeypatch.setattr(hardware_gate.platform, "system", lambda: "Windows")
    monkeypatch.setattr(
        hardware_gate.ctypes,
        "windll",
        SimpleNamespace(kernel32=SuccessfulKernel32()),
        raising=False,
    )

    assert hardware_gate._memory_gib() == (16.0, 6.0)


def test_windows_memory_collector_returns_nulls_when_os_query_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FailingKernel32:
        @staticmethod
        def GlobalMemoryStatusEx(_pointer: object) -> int:
            return 0

    values = {"SC_PAGE_SIZE": 1024, "SC_PHYS_PAGES": 2048, "SC_AVPHYS_PAGES": 1024}
    monkeypatch.setattr(
        hardware_gate,
        "os",
        SimpleNamespace(name="posix", sysconf=values.__getitem__),
    )
    monkeypatch.setattr(hardware_gate.platform, "system", lambda: "Windows")
    monkeypatch.setattr(
        hardware_gate.ctypes,
        "windll",
        SimpleNamespace(kernel32=FailingKernel32()),
        raising=False,
    )

    assert hardware_gate._memory_gib() == (None, None)


def test_gpu_detector_handles_an_absent_utility(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(hardware_gate.shutil, "which", lambda _name: None)

    assert hardware_gate._gpu_detected() is False
