"""Sanitized preflight for metadata-only work; never reads private records."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from collections.abc import Callable
from dataclasses import asdict, dataclass
from enum import StrEnum
from hashlib import sha256
from pathlib import Path
from typing import cast


class PreflightOutcome(StrEnum):
    OK = "OK"
    DATA_GOVERNANCE_BLOCKED = "DATA_GOVERNANCE_BLOCKED"
    REPOSITORY_BLOCKED = "REPOSITORY_BLOCKED"
    COMPUTE_BLOCKED = "COMPUTE_BLOCKED"


@dataclass(frozen=True)
class PreflightReport:
    outcome: PreflightOutcome
    issues: tuple[str, ...]
    repository: dict[str, object]
    data_governance: dict[str, object]
    compute: dict[str, object]
    memory_gate: dict[str, object]

    def to_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":"))


_IMAGING_SUFFIXES = (".nii", ".nii.gz", ".dcm", ".mgh", ".mgz")
_CREDENTIAL_MARKERS = ("credential", "secret", "token", "password", ".env")


def _git(root: Path, *args: str) -> tuple[int, str]:
    environment = {name: value for name, value in os.environ.items() if not name.startswith("GIT_")}
    completed = subprocess.run(
        ["git", *args],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
        env=environment,
    )
    return completed.returncode, completed.stdout


def _available_memory_gib() -> float | None:
    if os.name == "nt":
        import ctypes

        class MemoryStatus(ctypes.Structure):
            _fields_ = [("length", ctypes.c_ulong), ("memory_load", ctypes.c_ulong)] + [
                (name, ctypes.c_ulonglong)
                for name in (
                    "total_phys",
                    "avail_phys",
                    "total_page_file",
                    "avail_page_file",
                    "total_virtual",
                    "avail_virtual",
                    "avail_extended_virtual",
                )
            ]

        status = MemoryStatus()
        status.length = ctypes.sizeof(status)
        windows_api = getattr(ctypes, "windll", None)
        if windows_api is not None and windows_api.kernel32.GlobalMemoryStatusEx(
            ctypes.byref(status)
        ):
            return round(float(status.avail_phys) / 1024**3, 2)
        return None
    try:
        sysconf = cast(Callable[[str], int], os.__dict__["sysconf"])
        available_pages = int(sysconf("SC_AVPHYS_PAGES"))
        page_size = int(sysconf("SC_PAGE_SIZE"))
        return round(available_pages * page_size / 1024**3, 2)
    except (AttributeError, OSError, ValueError):
        return None


def _repository_baseline(root: Path, *, repository_available: bool) -> dict[str, object]:
    if not repository_available:
        return {
            "git_repository": False,
            "worktree_id": None,
            "head_sha": None,
            "head_status": "unavailable",
            "dirty": None,
        }
    _, worktree_output = _git(root, "rev-parse", "--show-toplevel")
    worktree = worktree_output.strip()
    worktree_id = sha256(worktree.encode("utf-8")).hexdigest()[:16] if worktree else None
    head_code, head_output = _git(root, "rev-parse", "HEAD")
    _, dirty_output = _git(root, "status", "--porcelain")
    return {
        "git_repository": True,
        "worktree_id": worktree_id,
        "head_sha": head_output.strip() if head_code == 0 else None,
        "head_status": "available" if head_code == 0 else "unavailable",
        "dirty": bool(dirty_output.strip()),
    }


def _metadata_summary(metadata_root: Path) -> tuple[int, tuple[str, ...], bool]:
    if not metadata_root.is_dir():
        return 0, (), False
    total = 0
    suffixes: set[str] = set()
    imaging = False
    for item in metadata_root.rglob("*"):
        if item.is_file():
            total += item.stat().st_size
            name = item.name.casefold()
            suffixes.add(
                ".nii.gz" if name.endswith(".nii.gz") else item.suffix.casefold() or "[none]"
            )
            imaging = imaging or name.endswith(_IMAGING_SUFFIXES)
    return total, tuple(sorted(suffixes)), imaging


def run_preflight(
    project_root: Path, *, metadata_root: Path, memory_gate_waived: bool
) -> PreflightReport:
    """Check safety boundaries and return a report that contains no source paths or rows."""
    root = project_root.resolve()
    repository_issues: list[str] = []
    returncode, inside = _git(root, "rev-parse", "--is-inside-work-tree")
    if returncode != 0 or inside.strip() != "true":
        repository_issues.append("repository identity is unavailable")
        tracked: list[str] = []
        history: list[str] = []
    else:
        _, tracked_output = _git(root, "ls-files")
        _, staged_output = _git(root, "diff", "--cached", "--name-only")
        _, history_output = _git(root, "log", "--all", "--name-only", "--pretty=format:")
        tracked = tracked_output.splitlines() + staged_output.splitlines()
        history = history_output.splitlines()
    repository = _repository_baseline(root, repository_available=not repository_issues)
    metadata_resolved = metadata_root.resolve()
    metadata_is_project_data = metadata_resolved.is_relative_to(root / "data")
    if metadata_is_project_data and not repository_issues:
        ignored_code, _ = _git(
            root,
            "check-ignore",
            "-q",
            "--",
            metadata_resolved.relative_to(root).as_posix(),
        )
        metadata_git_ignored: bool | None = ignored_code == 0
    else:
        metadata_git_ignored = None
    private_tracked = any(
        path.replace("\\", "/").casefold().startswith("data/") for path in tracked + history
    )
    credential_indicator = any(
        marker in path.casefold() for path in tracked + history for marker in _CREDENTIAL_MARKERS
    )
    if private_tracked:
        data_issues = ["private-data path appears in Git tracked, staged, or history state"]
    else:
        data_issues = []
    if credential_indicator:
        data_issues.append("credential/path indicator appears in Git state")
    if metadata_git_ignored is False:
        data_issues.append("private metadata root is not ignored by Git")
    size_bytes, file_types, imaging_found = _metadata_summary(metadata_root.resolve())
    compute_issues = ["imaging volume detected in metadata inventory"] if imaging_found else []
    disk_free_gib = round(shutil.disk_usage(root).free / 1024**3, 2) if root.exists() else None
    if data_issues:
        outcome = PreflightOutcome.DATA_GOVERNANCE_BLOCKED
    elif repository_issues:
        outcome = PreflightOutcome.REPOSITORY_BLOCKED
    elif compute_issues:
        outcome = PreflightOutcome.COMPUTE_BLOCKED
    else:
        outcome = PreflightOutcome.OK
    return PreflightReport(
        outcome=outcome,
        issues=tuple(data_issues + repository_issues + compute_issues),
        repository=repository,
        data_governance={
            "git_private_paths": private_tracked,
            "credential_indicator": credential_indicator,
            "metadata_root_present": metadata_root.is_dir(),
            "metadata_git_ignored": metadata_git_ignored,
        },
        compute={
            "cpu_count": os.cpu_count(),
            "disk_free_gib": disk_free_gib,
            "input_size_bytes": size_bytes,
            "file_types": file_types,
            "imaging_volumes_absent": not imaging_found,
            "gpu_work_authorized": False,
            "mri_work_authorized": False,
        },
        memory_gate={
            "status": "waived" if memory_gate_waived else "not_waived",
            "available_gib": _available_memory_gib(),
            "does_not_authorize": ["MRI", "GPU"],
        },
    )
