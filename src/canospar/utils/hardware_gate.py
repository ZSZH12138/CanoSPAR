"""Collect and evaluate a CPU-only hardware gate without private machine data."""

from __future__ import annotations

import ctypes
import os
import platform
import shutil
import subprocess
import sys
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import TypeAlias, cast

JsonPrimitive: TypeAlias = str | int | float | bool | None
JsonValue: TypeAlias = JsonPrimitive | list["JsonValue"] | dict[str, "JsonValue"]

_GIB = 1024**3
_MINIMUMS = {
    "cpu_logical_cores": 2,
    "available_ram_gib": 6.0,
    "free_disk_gib": 12.0,
}


def _utc_timestamp() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _memory_gib() -> tuple[float | None, float | None]:
    """Return total and available RAM using OS APIs without recording host details."""
    if platform.system() == "Windows":

        class MemoryStatus(ctypes.Structure):
            _fields_ = [
                ("length", ctypes.c_ulong),
                ("memory_load", ctypes.c_ulong),
                ("total_physical", ctypes.c_ulonglong),
                ("available_physical", ctypes.c_ulonglong),
                ("total_page_file", ctypes.c_ulonglong),
                ("available_page_file", ctypes.c_ulonglong),
                ("total_virtual", ctypes.c_ulonglong),
                ("available_virtual", ctypes.c_ulonglong),
                ("available_extended_virtual", ctypes.c_ulonglong),
            ]

        status = MemoryStatus()
        status.length = ctypes.sizeof(MemoryStatus)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)) == 0:
            return None, None
        return status.total_physical / _GIB, status.available_physical / _GIB

    possible_sysconf: object = getattr(os, "sysconf", None)
    if not callable(possible_sysconf):
        return None, None
    sysconf = cast(Callable[[str], int], possible_sysconf)
    try:
        page_size = sysconf("SC_PAGE_SIZE")
        total = sysconf("SC_PHYS_PAGES")
        available = sysconf("SC_AVPHYS_PAGES")
    except (AttributeError, OSError, ValueError):
        return None, None
    return total * page_size / _GIB, available * page_size / _GIB


def _physical_cpu_cores() -> int | None:
    try:
        import psutil  # type: ignore[import-untyped]
    except ImportError:
        return None
    core_count = psutil.cpu_count(logical=False)
    return core_count if isinstance(core_count, int) else None


def _gpu_detected() -> bool:
    executable = shutil.which("nvidia-smi")
    if executable is None:
        return False
    try:
        completed = subprocess.run(
            [executable, "-L"], capture_output=True, check=False, text=True, timeout=5
        )
    except OSError:
        return False
    return completed.returncode == 0 and bool(completed.stdout.strip())


def _as_number(report: Mapping[str, JsonValue], key: str) -> float | None:
    value = report.get(key)
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return float(value)


def evaluate_hardware_gate(
    report: Mapping[str, JsonValue], waived_checks: Sequence[str] = ()
) -> dict[str, JsonValue]:
    """Add raw and waiver-adjusted conclusions without changing measurements."""
    failures = [
        key
        for key, minimum in _MINIMUMS.items()
        if (measured := _as_number(report, key)) is None or measured < minimum
    ]
    accepted_waivers = list(dict.fromkeys(check for check in waived_checks if check in failures))
    blocking_reasons = [
        f"{key} was below the required minimum of {minimum:.1f} "
        f"{'GiB' if key.endswith('_gib') else 'logical cores'}."
        for key, minimum in _MINIMUMS.items()
        if key in failures
    ]
    result: dict[str, JsonValue] = {
        **dict(report),
        "gate_passed": not failures,
        "effective_gate_passed": all(check in accepted_waivers for check in failures),
        "waived_checks": cast(list[JsonValue], accepted_waivers),
        "failed_checks": cast(list[JsonValue], failures),
        "blocking_reasons": cast(list[JsonValue], blocking_reasons),
    }
    return result


def collect_hardware_gate(project_root: Path) -> dict[str, JsonValue]:
    """Collect the machine-independent fields of the Week 1 gate report."""
    total_ram_gib, available_ram_gib = _memory_gib()
    disk_usage = shutil.disk_usage(Path(project_root))
    report: dict[str, JsonValue] = {
        "checked_at_utc": _utc_timestamp(),
        "operating_system": f"{platform.system()} {platform.release()}",
        "architecture": platform.architecture()[0],
        "python_version": platform.python_version(),
        "cpu_physical_cores": _physical_cpu_cores(),
        "cpu_logical_cores": os.cpu_count(),
        "total_ram_gib": total_ram_gib,
        "available_ram_gib": available_ram_gib,
        "available_ram_gib_samples": ([] if available_ram_gib is None else [available_ram_gib]),
        "free_disk_gib": disk_usage.free / _GIB,
        "gpu_detected": _gpu_detected(),
        "device": "cpu",
        "cuda_available": False,
        "git_available": shutil.which("git") is not None,
        "conda_or_venv_available": bool(
            os.environ.get("CONDA_PREFIX") or sys.prefix != sys.base_prefix
        ),
        "docker_available": shutil.which("docker") is not None,
        "apptainer_available": shutil.which("apptainer") is not None,
    }
    return evaluate_hardware_gate(report)
