"""Privacy-preserving records describing a CanoSPAR execution."""

from __future__ import annotations

import json
import platform as platform_module
import re
import shlex
import subprocess
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any, TypeAlias, cast

from canospar.utils.hashing import sha256_file

JsonPrimitive: TypeAlias = str | int | float | bool | None
JsonValue: TypeAlias = JsonPrimitive | list["JsonValue"] | dict[str, "JsonValue"]

_PATH_VALUE_PATTERN = re.compile(r"^(?P<key>[^=]+)=(?P<value>.*)$")
_WINDOWS_PATH_PATTERN = re.compile(r"^[A-Za-z]:[\\/]")
_SENSITIVE_ARGUMENT_MARKERS = (
    "api-key",
    "apikey",
    "password",
    "secret",
    "token",
    "username",
    "hostname",
    "user",
    "host",
)


def _utc_timestamp(now: datetime | None) -> str:
    timestamp = now if now is not None else datetime.now(UTC)
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=UTC)
    return timestamp.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _run_git(*args: str, project_root: Path) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=project_root,
        capture_output=True,
        check=False,
        text=True,
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or "Git command failed.")
    return completed.stdout.strip()


def _is_path_value(value: str) -> bool:
    return (
        value.startswith(("/", "\\", "~"))
        or _WINDOWS_PATH_PATTERN.match(value) is not None
        or "/" in value
        or "\\" in value
    )


def _sanitize_command(command: Sequence[str] | str) -> list[str]:
    """Return a command representation that never retains paths or secrets."""
    tokens = shlex.split(command) if isinstance(command, str) else list(command)
    sanitized: list[str] = []
    redact_next = False
    for token in tokens:
        text = str(token)
        argument_name = text.split("=", maxsplit=1)[0].casefold()
        if redact_next:
            sanitized.append("<redacted>")
            redact_next = False
            continue
        match = _PATH_VALUE_PATTERN.match(text)
        if match is not None and _is_path_value(match.group("value")):
            sanitized.append(f"{match.group('key')}=<path>")
            continue
        if _is_path_value(text):
            sanitized.append("<path>")
            continue
        is_sensitive_flag = argument_name.startswith("-") and any(
            sensitive_marker in argument_name for sensitive_marker in _SENSITIVE_ARGUMENT_MARKERS
        )
        if is_sensitive_flag:
            if "=" in text:
                sanitized.append(f"{text.split('=', maxsplit=1)[0]}=<redacted>")
            else:
                sanitized.append(text)
                redact_next = True
            continue
        sanitized.append(text)
    return sanitized


def _package_version(distribution: str) -> str:
    try:
        return version(distribution)
    except PackageNotFoundError:
        return "not_installed"


def _git_details(project_root: Path) -> tuple[str | None, str, str | None, bool]:
    """Collect commit and dirty state without including repository paths."""
    try:
        commit_hash = _run_git("rev-parse", "HEAD", project_root=project_root)
    except (FileNotFoundError, RuntimeError, subprocess.CalledProcessError) as error:
        message = str(error).casefold()
        if "does not have any commits" in message or "unknown revision" in message:
            reason = "Git repository has no commits."
        else:
            reason = "No Git repository is available at the project root."
        try:
            git_dirty = bool(_run_git("status", "--porcelain", project_root=project_root))
        except (FileNotFoundError, RuntimeError, subprocess.CalledProcessError):
            git_dirty = False
        return None, "unavailable", reason, git_dirty

    try:
        git_dirty = bool(_run_git("status", "--porcelain", project_root=project_root))
    except (FileNotFoundError, RuntimeError, subprocess.CalledProcessError):
        git_dirty = False
    return commit_hash, "available", None, git_dirty


def collect_provenance(
    contract_version: str,
    config_hash: str,
    random_seed: int,
    command: Sequence[str] | str,
    project_root: Path,
    dataset_manifest_path: Path | None = None,
    container_digest: str | None = None,
    device: str = "cpu",
    *,
    now: datetime | None = None,
) -> dict[str, JsonValue]:
    """Collect the Week 1 provenance contract without personal machine data."""
    if device != "cpu":
        raise ValueError("Week 1 provenance only permits device='cpu'.")

    commit_hash, commit_status, commit_reason, git_dirty = _git_details(Path(project_root))
    manifest_hash = (
        sha256_file(dataset_manifest_path) if dataset_manifest_path is not None else None
    )
    record: dict[str, JsonValue] = {
        "timestamp_utc": _utc_timestamp(now),
        "contract_version": contract_version,
        "commit_hash": commit_hash,
        "commit_hash_status": commit_status,
        "commit_hash_reason": commit_reason,
        "git_dirty": git_dirty,
        "config_hash": config_hash,
        "dataset_manifest_hash": manifest_hash,
        "dataset_manifest_hash_status": (
            "available" if manifest_hash is not None else "not_available_in_week1"
        ),
        "dataset_manifest_hash_reason": (
            None if manifest_hash is not None else "No dataset manifest was supplied."
        ),
        "container_digest": container_digest,
        "container_digest_status": (
            "available" if container_digest is not None else "not_available_in_week1"
        ),
        "container_digest_reason": (
            None if container_digest is not None else "No container digest was supplied."
        ),
        "random_seed": random_seed,
        "python_version": platform_module.python_version(),
        "platform": platform_module.system(),
        "torch_version": _package_version("torch"),
        "torch_geometric_version": _package_version("torch-geometric"),
        "device": "cpu",
        "cuda_available": False,
        "command": cast(list[JsonValue], _sanitize_command(command)),
    }
    return record


def write_provenance(record: Mapping[str, JsonValue], destination: Path) -> None:
    """Write a stable, UTF-8 JSON provenance record."""
    serialized = json.dumps(
        cast(dict[str, Any], dict(record)),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    Path(destination).write_text(f"{serialized}\n", encoding="utf-8")
